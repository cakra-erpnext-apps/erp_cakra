"""Pending Cash (kasbon) — uang muka tunai, sebelum ada bukti biaya/tagihan. Dokumen
PEMBAYARAN, karena itu modul FICO dan menempel di sidebar Payments, bukan Expedition.

Punya DUA ARAH, ditentukan master Pending Cash Type (field Arah Uang), bukan oleh
dokumennya:
  - Cash Outflow (bawaan): uang diserahkan ke penerima (Pay To, seorang Supplier).
    Jurnal: Dr akun uang muka / Cr Bank.
  - Cash Inflow: uang diterima dari customer (Receive From) — uang muka penjualan atau
    jaminan. Jurnal kebalikannya: Dr Bank / Cr akun uang muka.

Jaminan dan uang muka penjualan TIDAK butuh jalur sendiri: keduanya cuma dua Type
berarah Masuk dengan Advance Account berbeda. Bedanya baru terasa belakangan —
jaminan dikembalikan, uang muka dipotong ke tagihan — dan itu urusan dokumen lain.

Versi pertama SENGAJA hanya pencatatan: nomor, tipe, penerima, nominal, akun bank/kas,
connection ke job, detail + lampiran, remark. BELUM ada jurnal, approval, maupun realisasi
— itu tahap berikutnya (lihat catatan di bawah), supaya bentuk formulirnya dipakai dulu.

Penomoran ikut pola dokumen lain: naming series
`PC/.cmi_type_code./.cmi_company_abbr./.cmi_yy./.####` → PC/JOB/OGM/26/0001
(lihat erp.expedition.numbering) — kode tipe dari master Pending Cash Type, kode company
dari Abbr company, dan tahun diambil dari TANGGAL DOKUMEN, bukan tanggal input.

Yang SUDAH jalan dari rencana awal:
  - Alur status Draft -> Validated -> Paid (jurnal Dr uang muka / Cr bank), tiap langkah
    punya kebalikannya: Invalidate, Unpaid, dan Void/Unvoid.
  - Tarikan ke tabel Pending Cash di Payment Entry (erpnext_custom.overrides.payment_entry):
    PE membayar hutang dengan mengkredit akun uang muka DARI JURNAL dokumen ini.

  - Refund (uang kembali ke bank, penuh maupun sebagian): jurnal BARU di tanggal
    pengembalian — kebalikan jurnal Paid — bukan pembatalan jurnal aslinya. Lihat
    _create_journal_entry / bulk_refund.

Rencana berikutnya (belum dibuat, jangan diasumsikan ada):
  - Realisasi: baris biaya manual + tarik referensi job, lalu jurnal penutup dengan
    kekurangan uang muka.
"""

import frappe
from frappe.model import no_value_fields
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from erp.expedition import numbering

# Modul yang bisa ditautkan di section Connection -> field nama customer/vendor-nya.
# Packing List sengaja None: doctype itu TIDAK punya field customer/vendor sama sekali
# (dicek di JSON maupun kolom tabelnya), jadi kolom party-nya memang kosong.
CONNECTION_PARTY_FIELD = {
    "Shipping List": "principle_name",
    "Packing List": None,
    "Sales Order": "customer_name",
    "Purchase Order": "supplier_name",
    "Purchase Invoice": "supplier_name",
    "Purchase Receipt": "supplier_name",
}

# Modul yang party-nya SUPPLIER, sama jenisnya dengan Pay To di Pending Cash. Untuk modul
# ini uang mukanya wajib atas dokumen milik supplier yang dibayar -- lihat connection_query
# (saringan dropdown) dan _sync_connection (penjaga saat Save).
NEWLINE = chr(10)

CONNECTION_SUPPLIER_FIELD = {
    "Purchase Order": "supplier",
    "Purchase Invoice": "supplier",
    "Purchase Receipt": "supplier",
}

# Cerminnya untuk arah Masuk: dokumen milik CUSTOMER yang menyetor. Modul yang tidak
# terdaftar di sini tidak disaring per party -- Shipping List memakai principle_name
# (nama principle, bukan link Customer), jadi tidak bisa dibandingkan langsung.
CONNECTION_CUSTOMER_FIELD = {
    "Sales Order": "customer",
    "Sales Invoice": "customer",
}

# Setelah VALIDATED, isi dokumen dianggap disetujui dan dikunci. Yang masih boleh berubah:
# rekening sumber dana (sering baru ditentukan/direvisi belakangan) dan jejak status itu
# sendiri. Setelah PAID bahkan bank_account ikut terkunci — jurnalnya sudah terbentuk dari
# akun rekening itu, jadi mengubahnya diam-diam membuat jurnal tidak cocok dengan dokumen.
EDITABLE_AFTER_VALIDATE = {"bank_account"}
# Diisi ulang server tiap save (bukan ketikan user), jadi jangan ikut dikunci.
# `direction` ikut di sini: nilainya cerminan master Type, dan dokumen lama yang dibuat
# sebelum field ini ada baru terisi saat save berikutnya.
DERIVED_FIELDS = {"connection_party", "direction"}
STATE_FIELDS = {
    "validated",
    "validated_by",
    "validated_date",
    "paid",
    "paid_by",
    "paid_date",
    "paid_notes",
    "void",
    "void_by",
    "void_datetime",
    "journal_entry",
    "refunded_amount",
}


# Role yang boleh melihat Pending Cash ber-centang Confidential selain pembuatnya.
CONFIDENTIAL_ROLES = {"System Manager", "Accounts Manager"}


def _may_see_confidential(user):
    return bool(CONFIDENTIAL_ROLES & set(frappe.get_roles(user)))


def get_permission_query_conditions(user=None):
    """Saringan LIST/report: dokumen Confidential milik orang lain tidak ikut terambil.

    Harus di query, bukan cuma has_permission: has_permission tidak dipanggil untuk list
    view maupun laporan, jadi tanpa ini judul & nominalnya tetap kelihatan di daftar.
    """
    user = user or frappe.session.user
    if _may_see_confidential(user):
        return ""
    return (
        "(`tabPending Cash`.confidential = 0 or `tabPending Cash`.owner = "
        f"{frappe.db.escape(user)})"
    )


def has_permission(doc, ptype=None, user=None):
    """Gerbang per-dokumen (buka lewat URL langsung, get_doc, print)."""
    if not doc.get("confidential"):
        return True
    user = user or frappe.session.user
    return doc.owner == user or _may_see_confidential(user)


class PendingCash(Document):
    def autoname(self):
        self._default_company()
        # Draft buatan agent: nama sementara, seri belum dipakai (nomor asli diberikan
        # saat Save/Confirm lewat numbering.assign_number -> make_real_number).
        if self.flags.get("agent_draft"):
            self.name = numbering.draft_name()
            return
        # Dokumen normal: JANGAN set name di sini — biarkan Frappe memakai naming series.

    def make_real_number(self):
        return numbering.make_from_series(self)

    def validate(self):
        self._default_company()
        self._default_cost_center()
        self._sync_currency()
        if flt(self.total) <= 0:
            frappe.throw("Amount Paid harus lebih dari 0.")
        # Net = yang benar-benar keluar dari bank: uang mukanya plus beban yang menempel.
        # Dihitung ulang di server, bukan dipercaya dari form: dokumen dari API/import
        # tidak lewat form script sama sekali.
        self.net_amount_paid = flt(self.total) + flt(self.admin_fee) + flt(self.stamp_duty)
        self._sync_party()
        self._sync_connection()
        self._assert_connection_required()
        self._sync_state()
        self._guard_locked_fields()

    def _guard_locked_fields(self):
        """Kunci isi dokumen yang sudah Validated (kecuali Bank Account) / Paid (semuanya).

        Dijaga di SERVER, bukan cuma read-only di form: read-only form hanya menyembunyikan
        input, sedangkan API/import/bulk edit tetap bisa mengubah dokumen yang sudah
        disetujui — dan kalau sudah Paid, jurnalnya sudah terlanjur memakai angka lama.
        """
        before = self.get_doc_before_save()
        if not before or not before.validated or self.flags.get("ignore_pending_cash_lock"):
            return

        # Confidential ikut boleh diubah kapan saja: itu soal SIAPA yang boleh melihat,
        # bukan isi akuntansi dokumennya. Dont Post to GL sengaja TIDAK ikut — mengubahnya
        # sesudah disetujui berarti jurnalnya dibuat/dihapus diam-diam.
        allowed = STATE_FIELDS | DERIVED_FIELDS | {"confidential"}
        if not before.paid:
            allowed |= EDITABLE_AFTER_VALIDATE
        # Dokumen lama (sebelum field ini ada) boleh DIISI cost_center-nya saat
        # di-Pay — tapi yang sudah terisi tetap terkunci seperti field lain.
        if not before.get("cost_center"):
            allowed |= {"cost_center"}
        changed = []
        for df in self.meta.fields:
            if df.fieldtype in no_value_fields or df.fieldname in allowed:
                continue
            if self.get(df.fieldname) != before.get(df.fieldname):
                changed.append(df.label or df.fieldname)
        if not changed:
            return

        state = "Paid" if before.paid else "Validated"
        extra = "" if before.paid else " Hanya <b>Bank Account</b> yang masih bisa direvisi."
        frappe.throw(
            f"Pending Cash <b>{self.name}</b> sudah <b>{state}</b>, isinya tidak bisa diubah lagi."
            f"{extra}<br>Field yang berubah: <b>{', '.join(changed)}</b>."
        )

    # ---- state: Draft -> Validated -> Paid (jurnal), Void ---------------
    def _sync_state(self):
        """Isi/kosongkan jejak audit mengikuti checkbox-nya."""
        user = frappe.session.user
        now = now_datetime()

        if self.validated:
            if not self.validated_by:
                self.validated_by = user
                self.validated_date = now
        else:
            self.validated_by = None
            self.validated_date = None

        if self.void:
            if not self.void_datetime:
                self.void_by = user
                self.void_datetime = now
        else:
            self.void_by = None
            self.void_datetime = None

        if self.paid:
            if not self.paid_date:
                self.paid_date = getdate()
            if not self.paid_by:
                self.paid_by = user
        else:
            self.paid_date = None
            self.paid_by = None
            self.paid_notes = None

    def on_update(self):
        self._sync_journal()

    def _sync_journal(self):
        """Jurnal Pending Cash terbentuk saat PAID, bukan saat Validate.

        Validate hanya menyetujui dokumennya; uangnya belum keluar, jadi belum ada
        yang perlu dicatat. Begitu Paid: Dr akun uang muka (Pay To) -- Cr Bank.
        Batal Paid atau Void membatalkan jurnalnya.
        """
        # Don't Post to GL: kasbon dicatat tanpa jurnal sama sekali (di luar buku).
        # Dimatikan di sini, bukan di pemanggilnya, supaya SEMUA jalur (Pay lewat form,
        # bulk action, API) ikut — dan mematikan centangnya belakangan tetap membentuk
        # jurnalnya lewat save berikutnya.
        should_post = bool(self.paid) and not bool(self.void) and not bool(self.dont_post_to_gl)
        je = self.journal_entry
        if should_post and not je:
            self.db_set("journal_entry", self._create_journal_entry())
        elif (not should_post) and je:
            self.db_set("journal_entry", None)  # putus link dulu supaya JE bisa dibatalkan
            self._cancel_journal_entry(je)

    def _direction(self):
        """Arah uang dokumen ini: "Cash Inflow" atau "Cash Outflow", sekaligus mengisi field turunannya.

        Dibaca dari master Type, BUKAN dari field di dokumen: fetch_from hanya berjalan di
        jalur form, sedangkan dokumen dari API/import/bulk edit bisa sampai ke sini dengan
        field itu masih kosong. Type lama yang dibuat sebelum kolom ini ada bernilai kosong
        dan diperlakukan Keluar -- itu perilaku Pending Cash sebelum arah Masuk ada, jadi
        arti dokumen lama tidak berubah.
        """
        arah = None
        if self.pending_cash_type:
            arah = frappe.get_cached_value("Pending Cash Type", self.pending_cash_type, "direction")
        self.direction = arah or "Cash Outflow"
        return self.direction

    def _party(self):
        """(party_type, party) sesuai arah: Customer yang menyetor, atau Supplier penerima."""
        if self._direction() == "Cash Inflow":
            return "Customer", self.receive_from
        return "Supplier", self.pay_to

    def _sync_party(self):
        """Kosongkan sisi party yang tidak terpakai, lalu pastikan sisi yang terpakai terisi.

        Wajibnya dijaga di SERVER karena mandatory_depends_on cuma berlaku di form: dokumen
        dari API/import bisa lolos tanpa party dan jurnalnya terbentuk tanpa party diam-diam.
        Pengosongan sisi lain juga bukan kerapian belaka -- kalau Type sebuah dokumen diganti
        arahnya, party lama yang tertinggal akan terbawa ke jurnal sebagai party salah jenis.
        """
        if self._direction() == "Cash Inflow":
            self.pay_to = None
            if not self.receive_from:
                frappe.throw("<b>Receive From</b> wajib diisi untuk Pending Cash <b>Cash Inflow</b>.")
        else:
            self.receive_from = None
            if not self.pay_to:
                frappe.throw("<b>Pay To</b> wajib diisi untuk Pending Cash <b>Cash Outflow</b>.")

    def _charge_lines(self):
        """[(nilai company-currency, akun, label)] untuk Biaya Admin & Materai yang terisi.

        Akunnya dari ERPNext Custom Setting > Finance > Pending Cash. Belum diset padahal
        biayanya diisi = DITOLAK, bukan diam-diam dilewatkan: jurnalnya akan timpang.
        """
        rate = flt(self.exchange_rate) or 1.0
        settings = frappe.get_single("ERPNext Custom Setting")
        lines = []
        for field, setting_field, label in (
            ("admin_fee", "pending_cash_admin_account", "Biaya Admin"),
            ("stamp_duty", "pending_cash_stamp_account", "Materai"),
        ):
            value = flt(self.get(field)) * rate
            if value <= 0:
                continue
            account = settings.get(setting_field)
            if not account:
                frappe.throw(
                    f"<b>{label}</b> diisi, tapi akunnya belum diset. Isi <b>Akun {label}</b> "
                    "di ERPNext Custom Setting > Finance > Pending Cash."
                )
            lines.append((value, account, label))
        return lines

    def _advance_account(self):
        """Akun uang muka lawan Bank. Tipe dulu, baru default Company sesuai arahnya.

        Kalau keduanya kosong, TOLAK dengan pesan jelas -- jangan menebak akun:
        salah akun berarti jurnal salah yang tidak ada yang menyadari.
        """
        acc = frappe.db.get_value("Pending Cash Type", self.pending_cash_type, "advance_account")
        if not acc:
            masuk = self._direction() == "Cash Inflow"
            company_field = "default_advance_received_account" if masuk else "default_advance_paid_account"
            acc = frappe.db.get_value("Company", self.company, company_field)
            if not acc:
                label = "Default Advance Received Account" if masuk else "Default Advance Paid Account"
                frappe.throw(
                    "Akun uang muka belum di-set. Isi <b>Advance Account</b> di Pending Cash Type "
                    f"<b>{self.pending_cash_type}</b>, atau <b>{label}</b> di Company."
                )
        return acc

    # ERPNext (accounts.party.validate_account_party_type) hanya mengizinkan party menempel
    # di akun bertipe Receivable / Payable / Equity — atau yang account_type-nya kosong.
    PARTY_ACCOUNT_TYPES = ("Receivable", "Payable", "Equity", "", None)

    def _advance_party(self, account):
        """Party (penerima kasbon) untuk baris debit uang muka — kalau akunnya mengizinkan.

        Akun uang muka yang di-set sebagai Cash/Bank/aset biasa (mis. "Kas Bon Operasional"
        bertipe Cash) DITOLAK ERPNext kalau diberi party, jadi barisnya diposting tanpa party:
        jurnalnya tetap benar, hanya saldo uang mukanya tidak terurai per penerima. Mau
        terurai per penerima? ubah account_type akunnya jadi Receivable.
        """
        if frappe.get_cached_value("Account", account, "account_type") not in self.PARTY_ACCOUNT_TYPES:
            return {}
        party_type, party = self._party()
        return {"party_type": party_type, "party": party}

    def _bank_gl_account(self):
        acc = frappe.db.get_value("Bank Account", self.bank_account, "account")
        if not acc:
            frappe.throw(
                f"Bank Account <b>{self.bank_account}</b> belum tertaut ke akun GL "
                "(field <b>Account</b> di Bank Account)."
            )
        return acc

    def _create_journal_entry(self, amount=None, posting_date=None, reverse=False, note=None, title=None):
        """Jurnal Pending Cash. Default: jurnal Paid sebesar total dokumen.

        `reverse=True` membalik sisinya = jurnal REFUND (uang kembali ke bank). Refund
        adalah jurnal BARU bertanggal pengembalian, BUKAN pembatalan jurnal Paid: uang
        memang pernah keluar, dan bulan keluarnya bisa saja sudah tutup periode.
        """
        rate = flt(self.exchange_rate) or 1.0
        base_total = flt(self.total if amount is None else amount) * rate

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        # Jurnal ini lahir dari dokumen, bukan diketik orang. Flag bawaan ERPNext ini
        # yang dipakai list Journal Entry untuk menyaring jurnal adjust manual saja.
        je.is_system_generated = 1
        je.company = self.company
        je.posting_date = posting_date or self.paid_date or self.date
        label = "Refund Pending Cash" if reverse else "Pending Cash"
        ref = title or self.name
        detail = note if reverse else self.paid_notes
        je.user_remark = f"{label} {ref}" + (f" - {detail}" if detail else "")
        advance_account = self._advance_account()
        # Keluar: uang diserahkan, kita pegang hak tagih -> Dr uang muka / Cr Bank.
        # Masuk: uang diterima, kita berutang mengembalikan/memperhitungkan -> kebalikannya.
        # Refund membalik keduanya: uang muka dikembalikan ke rekening asalnya.
        masuk = (self._direction() == "Cash Inflow") != bool(reverse)
        advance_side = "credit" if masuk else "debit"
        bank_side = "debit" if masuk else "credit"
        je.append("accounts", {
            "account": advance_account,
            **self._advance_party(advance_account),
            f"{advance_side}_in_account_currency": base_total,
            advance_side: base_total,
            "cost_center": self.cost_center,
        })
        # Biaya Admin & Materai: beban bank yang menempel pada transfer ini, bukan bagian
        # uang muka. Selalu DEBIT (beban), dan sisi banklah yang menanggungnya — uang keluar
        # jadi lebih besar dari total, uang masuk jadi lebih kecil. Hanya di jurnal Paid:
        # refund cuma mengembalikan uang mukanya, biayanya sudah terjadi dan tidak ikut balik.
        charges = 0.0
        if amount is None and not reverse:
            for value, account, label in self._charge_lines():
                je.append("accounts", {
                    "account": account,
                    "debit_in_account_currency": value,
                    "debit": value,
                    "cost_center": self.cost_center,
                })
                charges += value
        # Cash Outflow: Net Amount Paid = uang muka + beban, itu yang keluar dari bank.
        # Cash Inflow: bebannya memotong uang yang masuk, jadi tandanya kebalikannya.
        bank_total = base_total - charges if masuk else base_total + charges
        je.append("accounts", {
            "account": self._bank_gl_account(),
            f"{bank_side}_in_account_currency": bank_total,
            bank_side: bank_total,
            "cost_center": self.cost_center,
        })
        je.flags.ignore_permissions = True
        je.insert()
        # Judul diisi SESUDAH insert: JournalEntry.validate menimpa title dengan
        # get_title() selama dokumennya masih baru. Submit tidak menimpanya lagi.
        je.title = f"{ref} - {self._party()[1]}"
        je.submit()
        return je.name

    def _cancel_journal_entry(self, je_name):
        if not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.flags.ignore_permissions = True
            je.cancel()
        # Undo Paid = salah input: jurnalnya DIHAPUS setelah cancel, bukan ditinggal
        # sebagai sampah cancelled. Void beda cerita — dokumen void adalah jejak
        # historis, jadi jurnal cancel-nya sengaja dibiarkan sebagai bukti.
        # Baris GL/Payment Ledger sisa cancel (is_cancelled=1, sudah bukan saldo)
        # dibuang dulu — link check delete_doc menolak selama baris itu masih ada
        # (ERPNext sendiri membuangnya di AccountsController.on_trash).
        if self.flags.get("delete_journal"):
            for ledger in ("GL Entry", "Payment Ledger Entry"):
                frappe.db.delete(ledger, {"voucher_type": "Journal Entry", "voucher_no": je_name})
            frappe.delete_doc("Journal Entry", je_name, ignore_permissions=True)

    def _default_company(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default(
                "company"
            )

    def _default_cost_center(self):
        """Cost center wajib (ikut ke jurnal saat Pay). Dokumen lama yang dibuat sebelum
        field ini ada di-backfill dari Default Cost Center company supaya aksi Pay/save
        mereka tidak mendadak gagal mandatory."""
        if not self.cost_center:
            self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

    def _sync_currency(self):
        """Mata uang default = mata uang company; kursnya WAJIB 1 kalau sama.

        Dipaksa di server, bukan cuma di form: kurs != 1 pada mata uang yang sama membuat
        nilai company-currency-nya salah tanpa ada yang menyadari."""
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if not self.currency:
            self.currency = company_currency
        if self.currency == company_currency:
            self.exchange_rate = 1
        elif flt(self.exchange_rate) <= 0:
            frappe.throw("Exchange Rate wajib diisi untuk mata uang selain {0}.".format(company_currency))

    def _sync_connection(self):
        """connection_party = nama customer/vendor dokumen yang ditaut. Diisi di SERVER
        (bukan cuma di form) supaya benar juga saat dibuat lewat API/import."""
        if not self.modul:
            self.number = None
            self.connection_party = None
            return
        self._assert_connection_party()
        self.connection_party = get_connection_party(self.modul, self.number)

    def _assert_connection_required(self):
        """Tipe yang terdaftar di ERPNext Custom Setting > Finance WAJIB menaut dokumen.

        mandatory_depends_on di form hanya menjaga jalur UI; API/import/bulk edit lewat
        begitu saja. Dokumen yang SUDAH Validated dilewati: isinya terkunci dan aksi status
        (Pay/Void) menyimpan ulang dokumen — dokumen lama tanpa Connection tidak boleh jadi
        tidak bisa dibayar gara-gara aturan yang baru dinyalakan.
        """
        before = self.get_doc_before_save()
        if before and before.validated:
            return
        if not self.pending_cash_type or self.pending_cash_type not in connection_types():
            return
        if not (self.modul and self.number):
            frappe.throw(
                "Pending Cash tipe <b>{0}</b> harus ditaut ke dokumen lain: isi "
                "<b>Modul</b> dan <b>Number</b> di section Connection.".format(
                    self.pending_cash_type
                )
            )

    def _assert_connection_party(self):
        """Dokumen yang ditaut harus milik party dokumen ini -- supplier yang dibayar
        (arah Keluar) atau customer yang menyetor (arah Masuk). Saringan dropdown saja
        tidak cukup: nomornya bisa diketik manual, atau dibuat lewat API/import."""
        party_type, party = self._party()
        peta = CONNECTION_CUSTOMER_FIELD if party_type == "Customer" else CONNECTION_SUPPLIER_FIELD
        field = peta.get(self.modul)
        if not (field and self.number and party):
            return
        owner = frappe.db.get_value(self.modul, self.number, field)
        if owner and owner != party:
            frappe.throw(
                f"{self.modul} <b>{self.number}</b> milik <b>{owner}</b>, bukan "
                f"<b>{party}</b>. Uang muka hanya boleh ditaut ke dokumen milik "
                f"{party_type.lower()} yang bersangkutan."
            )


def connection_modules():
    """Doctype yang boleh dipilih di dropdown Modul, dari ERPNext Custom Setting > Finance.

    Kosong = daftar bawaan doctype dipakai apa adanya (Property Setter-nya dihapus).
    """
    doc = frappe.get_single("ERPNext Custom Setting")
    return [
        r.document_type
        for r in (doc.get("pending_cash_connection_modules") or [])
        if r.get("document_type")
    ]


def sync_connection_module_options(doc=None, method=None):
    """Tulis pilihan Modul ke Property Setter tiap ERPNext Custom Setting disimpan.

    `modul` tetap Select NATIVE (bukan Link) supaya validasi Select di server ikut menjaga
    nilainya — pola yang sama dengan Invoice Type di erpnext_custom.invoice_types. Setting
    dikosongkan = Property Setter dibuang, opsi kembali ke bawaan doctype.
    """
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    modules = connection_modules()
    if modules:
        make_property_setter(
            "Pending Cash", "modul", "options", NEWLINE.join([""] + modules), "Small Text",
            for_doctype=False, validate_fields_for_doctype=False,
        )
    else:
        frappe.db.delete(
            "Property Setter",
            {"doc_type": "Pending Cash", "field_name": "modul", "property": "options"},
        )
    frappe.clear_cache(doctype="Pending Cash")


def connection_types():
    """Pending Cash Type yang wajib menaut dokumen lain (section Connection).

    Sumbernya ERPNext Custom Setting > Finance > Pending Cash. Dibaca juga oleh boot
    (erpnext_custom.item_scope.boot) supaya depends_on / mandatory_depends_on di form bisa
    menyala begitu Type dipilih — keduanya dievaluasi di client dan tak bisa memanggil server.
    Kosong = section Connection disembunyikan untuk semua tipe.
    """
    doc = frappe.get_single("ERPNext Custom Setting")
    return [
        r.pending_cash_type
        for r in (doc.get("pending_cash_connection_types") or [])
        if r.get("pending_cash_type")
    ]


# ---- Aksi status (tombol form & Actions di list; semuanya bulk) ---------------------
# Tiga pasang aksi bolak-balik, tiap pasangan kebalikan persis satu sama lain:
#     Validate <-> Invalidate   (kunci isi dokumen <-> buka lagi untuk revisi)
#     Pay      <-> Unpaid       (buat jurnal <-> hapus jurnal; koreksi salah input)
#     Void     <-> Unvoid       (batalkan dokumen <-> aktifkan lagi)
# Urutan pembatalan mengikuti urutan majunya secara terbalik: dokumen Paid harus di-Unpaid
# dulu sebelum bisa di-Invalidate, sebab Paid berdiri di atas Validated (dan jurnalnya
# dibuat dari isi yang sudah disetujui itu).
def _run_bulk(names, handler, doctype="Pending Cash"):
    """Jalankan aksi untuk banyak dokumen tanpa saling menjatuhkan.

    Satu dokumen gagal (mis. Bank Account kosong) TIDAK boleh membatalkan yang lain, tapi
    juga tidak boleh diam: tiap kegagalan di-rollback ke savepoint dokumen itu saja, lalu
    dilaporkan balik ke pemanggil supaya user tahu persis mana yang tidak jadi.
    """
    names = frappe.parse_json(names) if isinstance(names, str) else names
    done, failed = [], []
    for name in names or []:
        frappe.db.savepoint("pending_cash_action")
        try:
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("write")
            handler(doc)
            done.append(name)
        except Exception as e:
            frappe.db.rollback(save_point="pending_cash_action")
            failed.append({"name": name, "error": str(e)})
    return {"done": done, "failed": failed}


def _assert_not_void(doc):
    """Dokumen Void tidak menerima aksi apa pun selain Unvoid — dia sudah dibatalkan."""
    if doc.void:
        frappe.throw(f"Pending Cash {doc.name} sudah Void. Jalankan <b>Unvoid</b> dulu.")


def _payment_entries(pc_name, submitted_only=False):
    """Payment Entry yang memakai Pending Cash ini — DRAFT ikut dihitung.

    Draft pun sudah mengklaim uang mukanya (barisnya mengurangi Sisa Penggunaan di dialog
    Add Pending Cash), jadi kolomnya harus menunjukkannya. Satu Pending Cash bisa dipakai
    di beberapa PV — uang muka Rp 2 juta boleh dipotong ke dua tagihan berbeda.

    `submitted_only` dipakai status Settled: uang muka baru benar-benar SELESAI kalau PV-nya
    sudah tervalidasi. PV draft masih bisa dibatalkan, jadi belum boleh disebut selesai.
    """
    if not pc_name:
        return []
    return frappe.get_all(
        "Payment Entry Transaction",
        parent_doctype="Payment Entry",
        filters={
            "parenttype": "Payment Entry",
            "parentfield": "custom_pending_items",
            "reference_doctype": "Pending Cash",
            "transaction": pc_name,
            "docstatus": 1 if submitted_only else ["<", 2],
        },
        distinct=True,
        pluck="parent",
    )


def sync_document_links(pc_names):
    """Isi kolom list view Payment dari PV-nya, bukan dari tulisan tangan siapa pun.

    Dipanggil dari sisi Payment Entry (tautannya memang dibuat di sana); Pending Cash-nya
    sendiri tidak ikut disave — yang sudah Paid memang terkunci. update_modified=False
    supaya tautan tidak mengubah jejak `modified` dokumen orang lain.
    """
    for pc in {n for n in (pc_names or []) if n}:
        if not frappe.db.exists("Pending Cash", pc):
            continue
        frappe.db.set_value(
            "Pending Cash",
            pc,
            {
                "payment_no": ", ".join(sorted(_payment_entries(pc))) or None,
                # Settled = ada PV TERVALIDASI yang memotong uang muka ini. Dipakai status di
                # list: "Paid" cuma berarti uangnya sudah keluar, belum tentu sudah selesai.
                "settled": 1 if _payment_entries(pc, submitted_only=True) else 0,
            },
            update_modified=False,
        )


@frappe.whitelist()
def bulk_validate(names):
    """Tandai Validated. Setelah ini isinya terkunci kecuali Bank Account."""

    def handler(doc):
        _assert_not_void(doc)
        if doc.validated:
            frappe.throw(f"Pending Cash {doc.name} sudah Validated.")
        doc.validated = 1
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_invalidate(names):
    """Batalkan Validate: dokumen kembali Draft sehingga isinya bisa direvisi lagi."""

    def handler(doc):
        _assert_not_void(doc)
        if not doc.validated:
            frappe.throw(f"Pending Cash {doc.name} masih Draft.")
        if doc.paid:
            frappe.throw(
                f"Pending Cash {doc.name} masih Paid — jalankan <b>Unpaid</b> dulu "
                "(jurnalnya dibuat dari isi yang sudah divalidasi ini)."
            )
        doc.validated = 0
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_pay(names, paid_date=None, paid_notes=None, bank_account=None):
    """Tandai Paid + buat jurnal (Dr uang muka / Cr bank) lewat on_update. Dokumen yang
    masih Draft ikut di-Validate di langkah yang sama.

    Bank Account dipilih di dialog Pay (field form-nya read-only), tapi tetap dicek DI SINI:
    tanpa rekening tidak ada akun GL yang bisa dikredit, jadi membiarkannya lolos berarti
    aksi Pay berhasil tanpa jurnal.
    """
    date = getdate(paid_date) if paid_date else getdate()

    def handler(doc):
        _assert_not_void(doc)
        # Bayar dokumen yang masih Draft = sekalian di-Validate: membayar sudah berarti
        # menyetujui isinya, dan menyuruh user menekan dua tombol berurutan tidak menambah
        # kendali apa pun. Jejaknya tetap terisi lengkap (validated_by/date lewat _sync_state),
        # dan Unpaid tetap berhenti di Validated seperti biasa.
        if not doc.validated:
            doc.validated = 1
        if doc.paid:
            frappe.throw(f"Pending Cash {doc.name} sudah Paid.")
        if bank_account:
            doc.bank_account = bank_account
        # Jurnal pembayaran tidak boleh bertanggal sebelum dokumennya — GL-nya akan
        # mendahului Pending Cash yang melahirkannya.
        if date < getdate(doc.date):
            frappe.throw(
                f"<b>Paid Date</b> ({frappe.format(date, 'Date')}) mendahului tanggal "
                f"Pending Cash {doc.name} ({frappe.format(doc.date, 'Date')})."
            )
        if not doc.bank_account:
            frappe.throw(f"Bank Account pada Pending Cash {doc.name} masih kosong.")
        doc.paid = 1
        doc.paid_date = date
        doc.paid_notes = paid_notes or None
        doc.save()

    return _run_bulk(names, handler)


def _payment_entry_rows(name):
    """Baris Pending Cash ini di Payment Entry mana pun (draft maupun tervalidasi).

    Satu-satunya sumber angka "sudah dipakai": Pending Cash belum punya ledger sendiri,
    jadi pemakaiannya hanya tercatat sebagai baris di PE (lihat _pending_cash_used di
    erpnext_custom.overrides.payment_entry — perhitungan sisanya harus sama dengan ini).
    """
    if not frappe.db.exists("DocType", "Payment Entry Transaction"):
        return []
    return frappe.get_all(
        "Payment Entry Transaction",
        parent_doctype="Payment Entry",
        filters={
            "parenttype": "Payment Entry",
            "parentfield": "custom_pending_items",
            "reference_doctype": "Pending Cash",
            "transaction": name,
            "docstatus": ["<", 2],
        },
        fields=["parent", "allocated"],
        ignore_permissions=True,
    )


def _refund_rows(pending_cash, active_only=True):
    """Baris alokasi refund satu kasbon.

    `active_only` = uang yang benar-benar kembali (void tidak dihitung) — itu yang dipakai
    hitungan sisa. Yang MENAMPILKAN justru butuh void-nya juga: dokumen void adalah jejak,
    dan tabel di form menampilkannya dicoret.

    SQL join, bukan get_all: barisnya ada di child table sedangkan void-nya di induk, dan
    get_all tidak bisa menyaring induk dari anaknya dalam satu query.
    """
    return frappe.db.sql(
        """select a.parent, a.amount, r.refund_date, r.remark, r.void, r.bank_account
           from `tabPending Cash Refund Allocation` a
           join `tabPending Cash Refund` r on r.name = a.parent
           where a.pending_cash = %s {void}
           order by a.parent""".format(void="and r.void = 0" if active_only else ""),
        pending_cash,
        as_dict=True,
    )


def refunded_total(pending_cash, exclude=None):
    """Jumlah refund AKTIF (yang void tidak dihitung — uangnya tidak jadi kembali)."""
    rows = _refund_rows(pending_cash)
    return flt(sum(flt(r.amount) for r in rows if r.parent != exclude), 2)


@frappe.whitelist()
def refund_rows(pending_cash):
    """Daftar refund satu kasbon untuk tabel di form-nya — VOID ikut, dicoret di sana.
    Lewat server karena datanya child table + induknya: satu join, bukan dua panggilan
    dari browser."""
    return _refund_rows(pending_cash, active_only=False)


def sync_refunded(pending_cash):
    """Simpan ulang rollup refund di kasbon induknya: total, bank, dan tanggal.

    Bank & tanggal diambil dari refund AKTIF yang TERAKHIR — satu kasbon bisa dikembalikan
    beberapa kali lewat rekening berbeda, dan yang berguna di kolom list adalah yang terakhir.
    Rinciannya tetap ada di tabel Refund pada form-nya.

    db_set langsung, bukan doc.save(): kasbon yang sudah Paid isinya terkunci
    (_guard_locked_fields), dan angka ini memang turunan dokumen refund — bukan ketikan user.
    """
    rows = _refund_rows(pending_cash)
    last = max(rows, key=lambda r: (getdate(r.refund_date), r.parent)) if rows else None
    frappe.db.set_value(
        "Pending Cash", pending_cash,
        {
            "refunded_amount": flt(sum(flt(r.amount) for r in rows), 2),
            "refund_bank": last.bank_account if last else None,
            "refund_date": last.refund_date if last else None,
        },
        update_modified=False,
    )


def refund_available(doc, exclude=None):
    """Sisa uang muka yang masih bisa dikembalikan = total - dipakai di PE - sudah direfund.

    `exclude` = nomor refund yang sedang disimpan (angka lamanya jangan ikut dihitung).
    """
    used = sum(flt(r.allocated) for r in _payment_entry_rows(doc.name))
    return flt(flt(doc.total) - used - refunded_total(doc.name, exclude=exclude), 2)


def _assert_not_pulled_to_payment_entry(doc):
    """Unpaid/Void dilarang bila Pending Cash sudah ditarik ke Payment Entry (draft ATAUPUN
    tervalidasi). PE membayar hutang dengan MENGKREDIT akun uang muka dari jurnal Pending
    Cash ini — membatalkan jurnalnya membuat GL PE menunjuk uang muka yang tidak pernah ada,
    dan draft PE yang menyimpannya akan gagal submit. Lepas dulu barisnya di PE."""
    refs = [r.parent for r in _payment_entry_rows(doc.name)]
    if refs:
        frappe.throw(
            f"Pending Cash {doc.name} sudah dipakai membayar di Payment Entry "
            f"<b>{', '.join(sorted(set(refs)))}</b>. Hapus dulu barisnya di sana."
        )


def _assert_not_refunded(doc):
    """Unpaid/Void dilarang bila masih ada refund aktif: jurnal refund menunjuk uang muka
    dari jurnal Paid ini. Menghapus/membatalkan jurnal Paid meninggalkan jurnal refund yang
    mengembalikan uang muka yang tidak pernah ada. Void dulu refund-nya."""
    active = {r.parent for r in _refund_rows(doc.name)}
    if active:
        frappe.throw(
            f"Pending Cash {doc.name} masih punya refund aktif "
            f"(<b>{', '.join(sorted(active))}</b>). Void dulu refund-nya."
        )


@frappe.whitelist()
def bulk_refund(names, refund_date=None, amount=None, remark=None):
    """Kembalikan uang muka ke bank — penuh (`amount` kosong = seluruh sisa) atau sebagian.

    Tiap refund adalah DOKUMEN sendiri (Pending Cash Refund) bernomor sendiri, dengan
    jurnal BARU bertanggal pengembalian: kebalikan jurnal Paid. Jurnal Paid
    TIDAK disentuh — itu sebabnya refund di bulan lain aman walau bulan pembayarannya sudah
    tutup periode, dan itu pula bedanya dengan Unpaid/Void yang membongkar jurnal aslinya.

    Yang dibuat di sini masih DRAFT: jurnalnya terbit saat dokumen refund-nya di-Validate,
    bukan saat dibuat. Menerbitkan jurnal dari tombol di dokumen lain berarti GL berubah
    tanpa ada yang membuka dokumen yang menjelaskannya.

    Boleh berkali-kali (kembalian dicicil). Salah refund? Invalidate atau Void dokumen
    refund-nya — nomornya lanjut ke urutan berikutnya, tidak menimpa yang sudah terpakai.
    """
    date = getdate(refund_date) if refund_date else getdate()
    asked = flt(amount) if amount not in (None, "") else None

    def handler(doc):
        _assert_not_void(doc)
        available = refund_available(doc)
        if available <= 0.005:
            frappe.throw(f"Pending Cash {doc.name} tidak punya sisa yang bisa direfund.")
        # Kosong = seluruh sisa. Batas atas & syarat lainnya dijaga controller Pending
        # Cash Refund, jadi refund lewat form pun terjaga sama.
        amount = available if asked is None else asked
        refund = frappe.new_doc("Pending Cash Refund")
        refund.party_type, refund.party = doc._party()
        refund.company = doc.company
        refund.currency = doc.currency
        # Kurs BUKU kasbonnya, bukan kurs hari ini: tombol ini membalik pembayaran yang
        # sudah terjadi, jadi tidak boleh memunculkan selisih kurs yang tidak diminta.
        refund.exchange_rate = doc.exchange_rate
        refund.bank_account = doc.bank_account
        refund.refund_date = date
        refund.amount = amount
        refund.remark = remark
        # Alokasi DIPAKU ke kasbon ini: dari tombol Refund di kasbonnya, yang dimaksud
        # user jelas kasbon yang sedang dibuka — bukan hasil FIFO yang bisa jatuh ke
        # kasbon lain milik party yang sama.
        refund.append("allocations", {"pending_cash": doc.name, "amount": amount})
        refund.insert()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_unpaid(names):
    """Batalkan Paid yang salah: jurnal di-cancel lalu DIHAPUS, dokumen balik ke Validated.

    Sengaja berhenti di Validated, bukan langsung Draft: Unpaid hanya membatalkan
    PEMBAYARANNYA. Kalau isi dokumennya juga mau diperbaiki, lanjutkan dengan Invalidate —
    memisahkan keduanya membuat tiap aksi punya kebalikan yang persis.
    """

    def handler(doc):
        _assert_not_void(doc)
        if not doc.paid:
            frappe.throw(f"Pending Cash {doc.name} belum Paid.")
        _assert_not_pulled_to_payment_entry(doc)
        _assert_not_refunded(doc)
        doc.paid = 0
        doc.flags.delete_journal = True
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_void(names):
    """Batalkan dokumen yang uangnya BELUM bergerak. Void hanya untuk kasbon Draft/Validated.

    Begitu dokumennya Paid, uangnya sudah keluar dan jurnalnya sudah jadi rujukan pihak
    lain (baris uang muka di Payment Entry, jurnal refund). Membatalkannya lewat Void
    berarti membongkar jurnal yang masih ditunjuk dokumen hidup — karena itu jalannya
    Unpaid dulu (yang punya penjagaannya sendiri) atau Refund, bukan Void.
    """

    def handler(doc):
        if doc.void:
            frappe.throw(f"Pending Cash {doc.name} sudah Void.")
        _assert_not_pulled_to_payment_entry(doc)
        _assert_not_refunded(doc)
        if doc.paid:
            frappe.throw(
                f"Pending Cash {doc.name} sudah Paid — jalankan <b>Unpaid</b> dulu "
                "(atau <b>Refund</b> kalau uangnya memang sudah keluar) sebelum Void."
            )
        doc.void = 1
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_unvoid(names):
    """Aktifkan lagi dokumen yang di-void. Yang statusnya Paid akan mendapat jurnal BARU
    (yang lama sudah cancel dan tidak bisa dihidupkan kembali)."""

    def handler(doc):
        if not doc.void:
            frappe.throw(f"Pending Cash {doc.name} tidak sedang Void.")
        doc.void = 0
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def get_connection_party(modul, number):
    """Nama customer/vendor satu dokumen yang ditaut (kosong untuk Packing List)."""
    field = CONNECTION_PARTY_FIELD.get(modul)
    if not (field and number):
        return None
    return frappe.db.get_value(modul, number, field)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def connection_query(doctype, txt, searchfield, start, page_len, filters):
    """Pencarian field Number di section Connection.

    Mencari pada NOMOR maupun NAMA customer/vendor, dan mengembalikan keduanya supaya
    dropdown-nya membaca "SH/00001/CMI/26 - PT ENERGI UNGGUL". Link query mengembalikan
    list-of-list: kolom pertama = nilai yang disimpan, sisanya tampil sebagai keterangan.
    """
    modul = (filters or {}).get("modul")
    if not modul:
        return []
    party_field = CONNECTION_PARTY_FIELD.get(modul)

    or_filters = None
    if txt:
        or_filters = {"name": ["like", f"%{txt}%"]}
        if party_field:
            or_filters[party_field] = ["like", f"%{txt}%"]

    doc_filters = {"docstatus": ["<", 2]}
    # Order yang sudah SELESAI (Completed = barang diterima & ditagih penuh) atau Closed
    # tidak masuk akal lagi diberi uang muka -- uang muka dibayar SEBELUM barang/tagihan.
    # Tanpa saringan ini order lama menumpuk di dropdown selamanya dan yang masih berjalan
    # justru tenggelam.
    if modul in ("Purchase Order", "Sales Order"):
        doc_filters["status"] = ["not in", ("Closed", "Completed")]
    # Uang muka hanya masuk akal atas dokumen milik supplier yang dibayar. Tanpa ini
    # dropdown menampilkan PO vendor lain dan uang muka bisa nyasar ke PO yang salah.
    sup_field = CONNECTION_SUPPLIER_FIELD.get(modul)
    cus_field = CONNECTION_CUSTOMER_FIELD.get(modul)
    pay_to = (filters or {}).get("pay_to")
    receive_from = (filters or {}).get("receive_from")
    if sup_field and pay_to:
        doc_filters[sup_field] = pay_to
    elif cus_field and receive_from:
        doc_filters[cus_field] = receive_from

    fields = ["name"] + ([party_field] if party_field else [])
    rows = frappe.get_all(
        modul,
        filters=doc_filters,
        or_filters=or_filters,
        fields=fields,
        start=start,
        page_length=page_len,
        order_by="modified desc",
    )
    if not party_field:
        return [[r.name] for r in rows]
    return [[r.name, r.get(party_field) or ""] for r in rows]

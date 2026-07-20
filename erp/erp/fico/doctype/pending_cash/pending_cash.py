"""Pending Cash (kasbon) — uang muka tunai yang diserahkan ke penerima (Pay To),
sebelum ada bukti biaya. Dokumen PEMBAYARAN, karena itu modul FICO dan menempel di
sidebar Payments, bukan Expedition.

Versi pertama SENGAJA hanya pencatatan: nomor, tipe, penerima, nominal, akun bank/kas,
connection ke job, detail + lampiran, remark. BELUM ada jurnal, approval, maupun realisasi
— itu tahap berikutnya (lihat catatan di bawah), supaya bentuk formulirnya dipakai dulu.

Penomoran ikut pola dokumen lain: naming series
`PC/.cmi_type_code./.cmi_company_abbr./.cmi_yy./.####` → PC/JOB/OGM/26/0001
(lihat erp.expedition.numbering) — kode tipe dari master Pending Cash Type, kode company
dari Abbr company, dan tahun diambil dari TANGGAL DOKUMEN, bukan tanggal input.

Yang SUDAH jalan dari rencana awal:
  - Alur status Draft -> Validated -> Paid (jurnal Dr uang muka / Cr bank) + Undo Paid.
  - Tarikan ke tabel Pending Cash di Payment Entry (erpnext_custom.overrides.payment_entry):
    PE membayar hutang dengan mengkredit akun uang muka DARI JURNAL dokumen ini.

Rencana berikutnya (belum dibuat, jangan diasumsikan ada):
  - Realisasi: baris biaya manual + tarik referensi job, lalu jurnal penutup dengan
    kembalian / kekurangan.
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
}

# Setelah VALIDATED, isi dokumen dianggap disetujui dan dikunci. Yang masih boleh berubah:
# rekening sumber dana (sering baru ditentukan/direvisi belakangan) dan jejak status itu
# sendiri. Setelah PAID bahkan bank_account ikut terkunci — jurnalnya sudah terbentuk dari
# akun rekening itu, jadi mengubahnya diam-diam membuat jurnal tidak cocok dengan dokumen.
EDITABLE_AFTER_VALIDATE = {"bank_account"}
# Diisi ulang server tiap save (bukan ketikan user), jadi jangan ikut dikunci.
DERIVED_FIELDS = {"connection_party"}
STATE_FIELDS = {
    "validated",
    "validated_by",
    "validated_date",
    "paid",
    "paid_date",
    "paid_notes",
    "void",
    "void_by",
    "void_datetime",
    "journal_entry",
}


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
            frappe.throw("Total Pending Cash harus lebih dari 0.")
        self._sync_connection()
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

        allowed = STATE_FIELDS | DERIVED_FIELDS
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
        else:
            self.paid_date = None
            self.paid_notes = None

    def on_update(self):
        self._sync_journal()

    def _sync_journal(self):
        """Jurnal Pending Cash terbentuk saat PAID, bukan saat Validate.

        Validate hanya menyetujui dokumennya; uangnya belum keluar, jadi belum ada
        yang perlu dicatat. Begitu Paid: Dr akun uang muka (Pay To) -- Cr Bank.
        Batal Paid atau Void membatalkan jurnalnya.
        """
        should_post = bool(self.paid) and not bool(self.void)
        je = self.journal_entry
        if should_post and not je:
            self.db_set("journal_entry", self._create_journal_entry())
        elif (not should_post) and je:
            self.db_set("journal_entry", None)  # putus link dulu supaya JE bisa dibatalkan
            self._cancel_journal_entry(je)

    def _advance_account(self):
        """Akun uang muka yang di-DEBIT. Tipe dulu, baru default Company.

        Kalau keduanya kosong, TOLAK dengan pesan jelas -- jangan menebak akun:
        salah akun berarti jurnal salah yang tidak ada yang menyadari.
        """
        acc = frappe.db.get_value("Pending Cash Type", self.pending_cash_type, "advance_account")
        if not acc:
            acc = frappe.db.get_value("Company", self.company, "default_advance_paid_account")
        if not acc:
            frappe.throw(
                "Akun uang muka belum di-set. Isi <b>Advance Account</b> di Pending Cash Type "
                f"<b>{self.pending_cash_type}</b>, atau <b>Default Advance Paid Account</b> di Company."
            )
        return acc

    def _bank_gl_account(self):
        acc = frappe.db.get_value("Bank Account", self.bank_account, "account")
        if not acc:
            frappe.throw(
                f"Bank Account <b>{self.bank_account}</b> belum tertaut ke akun GL "
                "(field <b>Account</b> di Bank Account)."
            )
        return acc

    def _create_journal_entry(self):
        rate = flt(self.exchange_rate) or 1.0
        base_total = flt(self.total) * rate

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = self.company
        je.posting_date = self.paid_date or self.date
        je.user_remark = f"Pending Cash {self.name}" + (f" - {self.paid_notes}" if self.paid_notes else "")
        je.append("accounts", {
            "account": self._advance_account(),
            "party_type": "Supplier",
            "party": self.pay_to,
            "debit_in_account_currency": base_total,
            "debit": base_total,
            "cost_center": self.cost_center,
        })
        je.append("accounts", {
            "account": self._bank_gl_account(),
            "credit_in_account_currency": base_total,
            "credit": base_total,
            "cost_center": self.cost_center,
        })
        je.flags.ignore_permissions = True
        je.insert()
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
        self.connection_party = get_connection_party(self.modul, self.number)


# ---- Aksi Validate / Pay (tombol form & Actions di list; keduanya bulk) --------------
def _run_bulk(names, handler):
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
            doc = frappe.get_doc("Pending Cash", name)
            doc.check_permission("write")
            handler(doc)
            done.append(name)
        except Exception as e:
            frappe.db.rollback(save_point="pending_cash_action")
            failed.append({"name": name, "error": str(e)})
    return {"done": done, "failed": failed}


def _assert_actionable(doc):
    if doc.void:
        frappe.throw(f"Pending Cash {doc.name} sudah Void.")


@frappe.whitelist()
def bulk_validate(names):
    """Tandai Validated. Setelah ini isinya terkunci kecuali Bank Account."""

    def handler(doc):
        _assert_actionable(doc)
        if doc.validated:
            frappe.throw(f"Pending Cash {doc.name} sudah Validated.")
        doc.validated = 1
        doc.save()

    return _run_bulk(names, handler)


@frappe.whitelist()
def bulk_pay(names, paid_date=None, paid_notes=None):
    """Tandai Paid + buat jurnal (Dr uang muka / Cr bank) lewat on_update.

    Bank Account dicek DI SINI, bukan hanya di form: tanpa rekening tidak ada akun GL yang
    bisa dikredit, jadi membiarkannya lolos berarti aksi Pay berhasil tanpa jurnal.
    """
    date = getdate(paid_date) if paid_date else getdate()

    def handler(doc):
        _assert_actionable(doc)
        if not doc.validated:
            frappe.throw(f"Pending Cash {doc.name} harus di-Validate dulu sebelum dibayar.")
        if doc.paid:
            frappe.throw(f"Pending Cash {doc.name} sudah Paid.")
        if not doc.bank_account:
            frappe.throw(f"Bank Account pada Pending Cash {doc.name} masih kosong.")
        doc.paid = 1
        doc.paid_date = date
        doc.paid_notes = paid_notes or None
        doc.save()

    return _run_bulk(names, handler)


def _assert_not_pulled_to_payment_entry(doc):
    """Undo Paid dilarang bila Pending Cash sudah ditarik ke Payment Entry (draft ATAUPUN
    tervalidasi). PE membayar hutang dengan MENGKREDIT akun uang muka dari jurnal Pending
    Cash ini — menghapus jurnalnya membuat GL PE menunjuk uang muka yang tidak pernah ada,
    dan draft PE yang menyimpannya akan gagal submit. Lepas dulu barisnya di PE."""
    if not frappe.db.exists("DocType", "Payment Entry Transaction"):
        return
    refs = frappe.get_all(
        "Payment Entry Transaction",
        parent_doctype="Payment Entry",
        filters={
            "parenttype": "Payment Entry",
            "parentfield": "custom_pending_items",
            "reference_doctype": "Pending Cash",
            "transaction": doc.name,
            "docstatus": ["<", 2],
        },
        pluck="parent",
        ignore_permissions=True,
    )
    if refs:
        frappe.throw(
            f"Pending Cash {doc.name} sudah dipakai membayar di Payment Entry "
            f"<b>{', '.join(sorted(set(refs)))}</b>. Hapus dulu barisnya di sana "
            "sebelum Undo Paid."
        )


@frappe.whitelist()
def bulk_undo_paid(names):
    """Batalkan Paid yang salah: jurnal di-cancel lalu DIHAPUS, dokumen kembali ke Draft
    supaya bisa direvisi, lalu di-Validate dan Pay ulang dengan isi yang benar."""

    def handler(doc):
        _assert_actionable(doc)
        if not doc.paid:
            frappe.throw(f"Pending Cash {doc.name} belum Paid.")
        _assert_not_pulled_to_payment_entry(doc)
        doc.paid = 0
        doc.validated = 0
        doc.flags.delete_journal = True
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

    fields = ["name"] + ([party_field] if party_field else [])
    rows = frappe.get_all(
        modul,
        filters={"docstatus": ["<", 2]},
        or_filters=or_filters,
        fields=fields,
        start=start,
        page_length=page_len,
        order_by="modified desc",
    )
    if not party_field:
        return [[r.name] for r in rows]
    return [[r.name, r.get(party_field) or ""] for r in rows]

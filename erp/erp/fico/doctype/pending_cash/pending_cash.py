"""Pending Cash (kasbon) — uang muka tunai yang diserahkan ke penerima (Pay To),
sebelum ada bukti biaya. Dokumen PEMBAYARAN, karena itu modul FICO dan menempel di
sidebar Payments, bukan Expedition.

Versi pertama SENGAJA hanya pencatatan: nomor, tipe, penerima, nominal, akun bank/kas,
connection ke job, detail + lampiran, remark. BELUM ada jurnal, approval, maupun realisasi
— itu tahap berikutnya (lihat catatan di bawah), supaya bentuk formulirnya dipakai dulu.

Penomoran ikut pola dokumen lain: naming series `PC/.cmi_type_code./.cmi_yy./.####`
(lihat erp.expedition.numbering) — kode tipe dari master Pending Cash Type dan tahun diambil
dari TANGGAL DOKUMEN, bukan tanggal input.

Rencana berikutnya (belum dibuat, jangan diasumsikan ada):
  - Approval: Draft -> Approved -> Paid.
  - Pencairan langsung dari dokumen ini: Dr Pending Cash (party) / Cr Bank.
  - Realisasi: baris biaya manual + tarik referensi job, lalu jurnal penutup dengan
    kembalian / kekurangan.
  - Tarikan ke tabel Pending Cash di Payment Entry (butuh jurnal dulu: outstanding-nya
    dihitung dari ledger, sama seperti Expense Note).
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

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
        self._sync_currency()
        if flt(self.total) <= 0:
            frappe.throw("Total Pending Cash harus lebih dari 0.")
        self._sync_connection()
        self._sync_state()

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

        if not self.paid:
            self.paid_date = None

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
        })
        je.append("accounts", {
            "account": self._bank_gl_account(),
            "credit_in_account_currency": base_total,
            "credit": base_total,
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

    def _default_company(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default(
                "company"
            )

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

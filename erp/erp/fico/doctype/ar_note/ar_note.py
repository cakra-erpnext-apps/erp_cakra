"""AR Note — nota debit piutang ke customer.

Cermin Expense Note tipe Tanpa Job (AP Note) di sisi piutang: baris diisi langsung di
grid (Item opsional, Account, Qty, Price), Validate memposting Journal Entry
  Dr Piutang customer (party Customer) = Net Total
  Cr akun tiap baris (pendapatan) + Cr PPN Keluaran + Cr Materai, Dr PPh dipotong customer.
Pelunasannya lewat Payment Entry Receive biasa: JE ber-party Customer itu otomatis muncul
sebagai outstanding di Get Outstanding Invoices. Status manual validated/void seperti
Expense Note, tanpa docstatus.
"""

from frappe.model.document import Document
from frappe.utils import flt, now_datetime

import frappe

from erpnext_custom.item_scope import item_account


class ARNote(Document):
    def autoname(self):
        # Token .cmi_company_abbr. di naming series butuh company terisi sebelum penamaan.
        self._default_company()

    def validate(self):
        self._guard_locked()
        if self.void and not (self.void_reason or "").strip():
            frappe.throw("Alasan Void wajib diisi.")
        self._default_company()
        self._resolve_accounts()
        self._calculate_totals()
        if self.validated and not self.void:
            missing = [it.description or it.item or str(it.idx) for it in self.items if flt(it.amount) and not it.account]
            if missing:
                frappe.throw("Belum bisa divalidasi, baris tanpa <b>Account</b>: {0}".format(", ".join(missing)))
        self._sync_state()

    def _default_company(self):
        if not self.company:
            self.company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")

    def _guard_locked(self):
        """Sama dengan Expense Note: sesudah Validate/Void terkunci; membukanya lagi hanya
        Accounts Manager / System Manager."""
        before = None if self.is_new() else self.get_doc_before_save()
        if not before:
            return
        is_mgr = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
        for flag, label in (("validated", "Tervalidasi"), ("void", "Void")):
            if before.get(flag):
                if self.get(flag):
                    frappe.throw(f"AR Note ini sudah <b>{label}</b> dan terkunci.")
                if not is_mgr:
                    frappe.throw("Hanya Accounts Manager / System Manager yang boleh membukanya lagi.")

    def _resolve_accounts(self):
        # Baris ber-Item: akun kredit ikut Default Income Account Item -> Item Group.
        for it in self.items:
            if it.item:
                it.account = item_account(it.item, self.company, "income_account") or it.account
                it.description = it.description or frappe.db.get_value("Item", it.item, "item_name")

    def _calculate_totals(self):
        total = 0.0
        for it in self.items:
            it.amount = flt(it.qty) * flt(it.price)
            total += it.amount
        self.total_amount = total
        self.tax_amount = flt(total * flt(self.tax_pct) / 100, 2)
        self.pph_amount = flt(total * flt(self.pph_pct) / 100, 2)
        self.net_total = flt(total + self.tax_amount - self.pph_amount + flt(self.materai_amount), 2)

    def _sync_state(self):
        user, now = frappe.session.user, now_datetime()
        if self.validated:
            if not self.validated_by:
                self.validated_by, self.validated_date = user, now
        else:
            self.validated_by = self.validated_date = None
        if self.void:
            if not self.void_datetime:
                self.void_by, self.void_datetime = user, now
        else:
            self.void_by = self.void_datetime = None
        self.status = "Void" if self.void else "Validated" if self.validated else "Draft"

    # ---- Jurnal: dibuat saat Validate, dibatalkan+dihapus saat un-validate / void ----
    def on_update(self):
        should_post = bool(self.validated) and not self.void
        if should_post and not self.journal_entry:
            self.db_set("journal_entry", self._create_journal_entry())
        elif not should_post and self.journal_entry:
            je = self.journal_entry
            self.db_set("journal_entry", None)
            _delete_journal_entry(je)

    def _create_journal_entry(self):
        from erpnext.accounts.party import get_party_account

        s = frappe.get_cached_doc("ERPNext Custom Setting")

        def need(field, label):
            if not s.get(field):
                frappe.throw(f"Set <b>{label}</b> di ERPNext Custom Setting > Selling.")
            return s.get(field)

        receivable = get_party_account("Customer", self.customer, self.company)
        if not receivable:
            frappe.throw(f"Customer <b>{self.customer}</b> belum punya akun Piutang default (Company).")

        credits = {}
        for it in self.items:
            if not flt(it.amount):
                continue
            # Akun party di baris kredit bakal menuntut party lain / saling meniadakan
            # dengan piutangnya sendiri di Payment Ledger -> ditolak.
            if frappe.db.get_value("Account", it.account, "account_type") in ("Receivable", "Payable"):
                frappe.throw(f"Akun <b>{it.account}</b> bertipe Receivable/Payable, tidak bisa dipakai di baris AR Note.")
            credits[it.account] = flt(credits.get(it.account)) + flt(it.amount)
        if not credits:
            frappe.throw("Tidak ada baris untuk dijurnal.")

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.is_system_generated = 1
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.ref or self.name
        je.cheque_date = self.date
        je.user_remark = f"AR Note {self.name}" + (f" - {self.remark}" if self.remark else "")
        je.name = self.name
        je.flags.name_set = True

        def add(account, drcr, amt, **extra):
            if flt(amt, 2):
                je.append("accounts", {"account": account, "cost_center": self.cost_center,
                                       f"{drcr}_in_account_currency": flt(amt, 2), **extra})

        add(receivable, "debit", self.net_total, party_type="Customer", party=self.customer)
        for acc, amt in credits.items():
            add(acc, "credit", amt)
        if flt(self.tax_amount):
            add(need("sales_tax_account", "Tax (PPN) Account"), "credit", self.tax_amount)
        if flt(self.pph_amount):
            add(need("pph23_account", "PPh 23 Account"), "debit", self.pph_amount)
        if flt(self.materai_amount):
            add(need("materai_account", "Materai Account"), "credit", self.materai_amount)
        # Sisa pembulatan (Net Total vs jumlah baris) -> Akun Pajak & Penyesuaian.
        resid = flt(sum(flt(r.debit_in_account_currency) - flt(r.credit_in_account_currency) for r in je.accounts), 2)
        if resid:
            add(need("adjustment_account", "Akun Pajak & Penyesuaian"), "credit" if resid > 0 else "debit", abs(resid))

        je.flags.ignore_permissions = True
        je.insert()
        je.title = f"{self.name} - {self.customer}"
        je.submit()
        frappe.msgprint(f"Journal Entry <b>{je.name}</b> dibuat.", alert=True)
        return je.name


def _delete_journal_entry(je_name):
    """Cancel lalu hapus JE milik AR Note (pola Expense Note: jejak audit tetap di AR Note).
    JE yang sudah dilunasi Payment Entry ditolak ERPNext saat cancel — PE-nya dulu."""
    if not frappe.db.exists("Journal Entry", je_name):
        return
    je = frappe.get_doc("Journal Entry", je_name)
    if je.docstatus == 1:
        je.flags.ignore_permissions = True
        je.cancel()
    frappe.delete_doc("Journal Entry", je_name, force=1, ignore_permissions=True, delete_permanently=True)

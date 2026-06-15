"""Expense Note — expedition / AP vendor cost note.

Mirrors the legacy ``exp_expensenote`` + ``ap_expense_note`` (see erp-blueprint.md):
a vendor cost document with item lines, optional link to a Packing List, an
optional reimburse-to-customer flag, and Indonesian tax fields (PPN / PPh / PPh-22).

This app does not (yet) post to a GL, so state is tracked with the same manual
``validated`` / ``closed`` / ``void`` triplet pattern used by Packing List rather
than the Frappe submit (docstatus) workflow.
"""

from frappe.model.document import Document
from frappe.utils import flt, now_datetime

import frappe

from erp_cmi.expedition import numbering


class ExpenseNote(Document):
    def autoname(self):
        self._default_company()
        # Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
        # numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
        if self.flags.get("agent_draft"):
            self.name = numbering.draft_name()
            return
        # EXP/{type}/{number}/{company}/{year}
        self.name = self.make_real_number()

    def make_real_number(self):
        return numbering.make_number(
            "EXP", self.expense_note_type, "Expense Note Type", company=self.company, date=self.date
        )

    def validate(self):
        self._guard_locked()
        if self.void and not (self.void_reason or "").strip():
            frappe.throw("Alasan Void wajib diisi.")
        self._default_company()
        self._calculate_totals()
        self._sync_state()

    def _guard_locked(self):
        """Setelah Validate atau Void, dokumen terkunci: isi tidak boleh diubah.
        Transisi yang diizinkan hanya un-validate / un-void oleh Accounts Manager /
        System Manager. (Untuk meng-Void dokumen yang masih tervalidasi: batalkan
        validasi dulu.)"""
        if self.is_new():
            return
        before = self.get_doc_before_save()
        if not before:
            return
        is_mgr = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
        if before.validated:
            if self.validated:
                frappe.throw(
                    "Expense Note ini sudah <b>Tervalidasi</b> dan terkunci. "
                    "Batalkan validasi dulu untuk mengubah."
                )
            if not is_mgr:
                frappe.throw("Hanya Accounts Manager / System Manager yang boleh membatalkan validasi.")
        if before.void:
            if self.void:
                frappe.throw(
                    "Expense Note ini sudah di-<b>Void</b> dan terkunci. "
                    "Batalkan Void dulu untuk mengubah."
                )
            if not is_mgr:
                frappe.throw("Hanya Accounts Manager / System Manager yang boleh membuka Void.")

    def _default_company(self):
        # Company di-hide di form — isi otomatis agar save & penomoran tetap jalan.
        if not self.company:
            self.company = (
                frappe.defaults.get_global_default("company")
                or (frappe.get_all("Company", pluck="name", limit_page_length=1) or [None])[0]
            )

    # ---- totals ---------------------------------------------------------
    def _calculate_totals(self):
        total = 0.0
        for item in self.items or []:
            item.amount = flt(item.qty) * flt(item.price)
            total += flt(item.amount)
        self.subtotal = total
        self.total_amount = total
        self.net_total = (
            flt(self.total_amount)
            + flt(self.tax_amount)
            - flt(self.pph_amount)
            - flt(self.pph22_amount)
            - flt(self.discount_amount)
        )

    # ---- state machine (boolean + actor + timestamp triplets) -----------
    def _sync_state(self):
        user = frappe.session.user
        now = now_datetime()

        if self.validated:
            if not self.validated_by:
                self.validated_by = user
                self.validated_date = now
        else:
            self.validated_by = None
            self.validated_date = None

        if self.closed:
            if not self.closed_datetime:
                self.closed_by = user
                self.closed_datetime = now
        else:
            self.closed_by = None
            self.closed_datetime = None

        if self.void:
            if not self.void_datetime:
                self.void_by = user
                self.void_datetime = now
        else:
            self.void_by = None
            self.void_datetime = None

    # ---- Journaling: Dr akun biaya (Expense Class) — Cr Hutang Supplier --------
    def on_update(self):
        self._sync_journal()

    def _sync_journal(self):
        """JE dibuat saat Validate (validated & bukan void), di-cancel saat
        un-validate / void. Dr akun biaya (per Expense Class.account_1), Cr Hutang
        Supplier (= Net Total); selisih PPN/PPh/Discount ke akun penyesuaian."""
        should_post = bool(self.validated) and not bool(self.void)
        je = self.journal_entry
        if should_post and not je:
            self.db_set("journal_entry", self._create_journal_entry())
        elif (not should_post) and je:
            self._cancel_journal_entry(je)
            self.db_set("journal_entry", None)

    def _create_journal_entry(self):
        from erpnext.accounts.party import get_party_account

        rate = flt(self.conversion_rate) or 1.0
        # Debit: jumlahkan amount item per expense_account (dari Expense Class.account_1)
        debit = {}
        for it in (self.items or []):
            acc = it.expense_account
            if not acc:
                frappe.throw(
                    f"Baris '{it.expense_class or it.description or it.container_no}' belum punya "
                    "<b>Expense Account</b>. Set <b>Account 1</b> di Expense Class terkait."
                )
            debit[acc] = flt(debit.get(acc, 0)) + flt(it.amount) * rate
        if not debit:
            frappe.throw("Tidak ada item biaya untuk dijurnal.")
        for acc in list(debit):
            debit[acc] = flt(debit[acc], 2)
        subtotal = flt(sum(debit.values()), 2)
        net = flt(flt(self.net_total) * rate, 2)

        # Credit: Hutang Supplier (akun payable default supplier / fallback setting)
        payable = get_party_account("Supplier", self.vendor, self.company)
        if not payable:
            payable = frappe.db.get_single_value("Expense Note Settings", "default_payable_account")
        if not payable:
            frappe.throw(
                f"Supplier <b>{self.vendor}</b> belum punya akun Hutang (Payable) default, dan "
                "<b>Default Hutang</b> di Expense Note Settings juga kosong."
            )

        diff = flt(subtotal - net, 2)  # >0 -> credit penyesuaian ; <0 -> debit penyesuaian
        adj_account = frappe.db.get_single_value("Expense Note Settings", "adjustment_account")
        cc = self.cost_center

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.ref or self.name
        je.cheque_date = self.date
        je.user_remark = f"Expense Note {self.name}" + (f" — {self.remark}" if self.remark else "")

        for acc, amt in debit.items():
            je.append("accounts", {"account": acc, "debit_in_account_currency": amt, "cost_center": cc})
        if abs(diff) > 0.005:
            if not adj_account:
                frappe.throw(
                    "Set <b>Akun Pajak & Penyesuaian</b> di <b>Expense Note Settings</b> dulu "
                    "(untuk menampung selisih PPN/PPh/Discount)."
                )
            line = {"account": adj_account, "cost_center": cc}
            line["credit_in_account_currency" if diff > 0 else "debit_in_account_currency"] = abs(diff)
            je.append("accounts", line)
        je.append("accounts", {
            "account": payable, "party_type": "Supplier", "party": self.vendor,
            "credit_in_account_currency": net,
        })
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        frappe.msgprint(f"Journal Entry <b>{je.name}</b> dibuat.", alert=True)
        return je.name

    def _cancel_journal_entry(self, je_name):
        if not je_name or not frappe.db.exists("Journal Entry", je_name):
            return
        je = frappe.get_doc("Journal Entry", je_name)
        if je.docstatus == 1:
            je.flags.ignore_permissions = True
            je.cancel()


@frappe.whitelist()
def get_shipping_list_bls(shipping_list):
    """BLs of a Shipping List, for the Expense Note BL picker."""
    if not shipping_list:
        return []
    return frappe.get_all(
        "Shipping List BL",
        filters={"parent": shipping_list, "parenttype": "Shipping List"},
        fields=["bl_no", "consignee"],
        order_by="idx",
    )


@frappe.whitelist()
def get_bl_containers(shipping_list, bl_no):
    """Containers of one BL within a Shipping List — to auto-fill the Expense Note
    Connection table when the user picks a BL. The user can then delete unneeded rows."""
    if not shipping_list or not bl_no:
        return []
    return frappe.get_all(
        "Shipping List Container",
        filters={"parent": shipping_list, "parenttype": "Shipping List", "bl": bl_no},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )


@frappe.whitelist()
def get_packing_containers(packing_list):
    """Distinct containers of a Packing List (from its items) — alternative container
    source for the Expense Note when the user links a Packing List instead of a BL."""
    if not packing_list:
        return []
    rows = frappe.get_all(
        "Packing List Item",
        filters={"parent": packing_list, "parenttype": "Packing List"},
        fields=["container_no", "seal_no", "container_size", "customer"],
        order_by="idx",
    )
    seen, out = set(), []
    for r in rows:
        cno = (r.container_no or "").strip()
        if not cno or cno in seen:
            continue
        seen.add(cno)
        out.append(r)
    return out

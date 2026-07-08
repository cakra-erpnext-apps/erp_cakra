"""Payment Entry — kustomisasi "Tarik Expense Note".

Expense Note (app `erp`) saat Validate memposting Journal Entry:
    Dr Akun Biaya — Cr Hutang Supplier (party_type=Supplier, party=vendor).
JE itu otomatis jadi *outstanding* di akun Hutang supplier (terlacak di Payment
Ledger Entry). Tombol "Tarik Expense Note" di Payment Entry (Pay → Supplier)
menarik JE tsb sebagai baris References, sehingga saat Payment Entry di-submit:
    Dr Hutang Usaha — Cr Bank (paid_from)   ⇒  "Hutang Usaha X Bank Mandiri"
dan sisa hutang Expense Note berkurang.

Catatan: TIDAK ada logika outstanding yang ditulis ulang di sini. Angka diambil
dari helper ERPNext `get_outstanding_on_journal_entry` — sumber kebenaran yang
SAMA dipakai Payment Entry saat menghitung/submit, jadi tak akan beda.
"""

import frappe
from frappe import _
from frappe.utils.data import flt

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry


def _is_settlement(doc):
	"""Mode settlement dipicu dari Mode of Payment bernama "Settlement"."""
	return (doc.get("mode_of_payment") or "").strip().lower() == "settlement"


def _apply_direct_and_settlement(doc):
	"""Mode tambahan Payment Entry (CMI):

	- custom_direct ("Expense / Income"): TANPA party & tanpa tarikan transaksi.
	  Nominal per baris custom_direct_items (note + account wajib + amount) diposting
	  langsung: Pay -> Dr tiap akun item, Cr Bank; Receive -> Dr Bank, Cr tiap akun
	  item. Penerima/pengirim dicatat di field teks custom_payto.
	- Mode of Payment "Settlement": sisi BANK diganti akun custom_settlement_account
	  (Pay: paid_from, Receive: paid_to) — pelunasan via akun perantara, bukan bank.
	Default (tanpa Expense/Income & mode of payment lain): perilaku native (party -> bank).
	"""
	# Settlement diproses DULUAN: sisi bank diganti akun settlement, sehingga
	# placeholder mode direct di bawah bisa menyalin akun yang sudah final.
	if _is_settlement(doc):
		if not doc.get("custom_settlement_account"):
			frappe.throw(_("Mode of Payment Settlement: pilih akun settlement (pengganti Bank)."))
		if doc.payment_type == "Pay":
			doc.paid_from = doc.custom_settlement_account
		elif doc.payment_type == "Receive":
			doc.paid_to = doc.custom_settlement_account
	if doc.get("custom_direct"):
		doc.party_type = None
		doc.party = None
		doc.party_name = None
		doc.set("references", [])
		doc.set("custom_expense_notes", [])
		items = [d for d in (doc.get("custom_direct_items") or []) if flt(d.amount)]
		if not items:
			frappe.throw(_("Mode Expense / Income: isi minimal 1 baris item (account + amount)."))
		total = sum(flt(d.amount) for d in items)
		doc.paid_amount = total
		doc.received_amount = total
		# Satu mata uang company; sisi party kosong membuat kurs target tidak terisi.
		doc.source_exchange_rate = doc.source_exchange_rate or 1
		doc.target_exchange_rate = doc.target_exchange_rate or 1
		# Skema PE mewajibkan paid_from & paid_to terisi. Sisi party tidak dipakai
		# GL pada mode direct (add_party_gl_entries kita yang jalan) — isi placeholder
		# = akun bank supaya lolos mandatory tanpa efek jurnal.
		company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		if doc.payment_type == "Pay":
			doc.paid_to = doc.paid_to or doc.paid_from
		else:
			doc.paid_from = doc.paid_from or doc.paid_to
		doc.paid_from_account_currency = doc.paid_from_account_currency or company_currency
		doc.paid_to_account_currency = doc.paid_to_account_currency or company_currency


class CMIPaymentEntry(PaymentEntry):
	"""Override controller core Payment Entry tanpa mengedit erpnext."""

	def set_missing_values(self):
		if self.get("custom_direct"):
			# Tanpa party — core melempar "Party is mandatory".
			self.references = []
			return
		super().set_missing_values()

	def set_missing_ref_details(self, *args, **kwargs):
		if self.get("custom_direct"):
			return
		return super().set_missing_ref_details(*args, **kwargs)

	def set_difference_amount(self):
		if self.get("custom_direct"):
			# Sisi party digantikan baris item: selisih = nominal bank - total item
			# - deductions (harus 0 supaya jurnal balance).
			items_total = sum(flt(d.amount) for d in self.get("custom_direct_items") or [])
			base = self.base_paid_amount if self.payment_type == "Pay" else self.base_received_amount
			total_deductions = sum(flt(d.amount) for d in self.get("deductions") or [])
			self.difference_amount = flt(
				flt(base) - items_total - total_deductions, self.precision("difference_amount")
			)
			return
		super().set_difference_amount()

	def add_party_gl_entries(self, gl_entries):
		if not self.get("custom_direct"):
			return super().add_party_gl_entries(gl_entries)
		# Mode Expense / Income: baris GL dari tiap item (lawan = sisi bank/settlement).
		against = self.paid_from if self.payment_type == "Pay" else self.paid_to
		default_cc = self.cost_center or frappe.get_cached_value("Company", self.company, "cost_center")
		for it in self.get("custom_direct_items") or []:
			amt = flt(it.amount)
			if not amt:
				continue
			row = {
				"account": it.account,
				"against": against,
				"cost_center": it.cost_center or default_cc,
				"remarks": it.note or self.remarks,
			}
			if self.payment_type == "Pay":
				row.update({"debit": amt, "debit_in_account_currency": amt})
			else:
				row.update({"credit": amt, "credit_in_account_currency": amt})
			gl_entries.append(self.get_gl_dict(row, item=it))


def before_validate(doc, method=None):
    _apply_direct_and_settlement(doc)
    _derive_references(doc)


def _derive_references(doc):
    """Turunkan baris References dari DUA tabel custom (tabel = sumber kebenaran):

    - custom_expense_notes -> reference Journal Entry (JE yang dibuat EN saat Validate),
      ditandai custom_expense_note.
    - custom_transactions  -> reference Sales/Purchase Invoice outstanding milik party,
      ditandai custom_from_transaction.
    Allocated = kolom "Dibayar" (default = sisa). References manual (tanpa tanda)
    dibiarkan. paid_amount diisi = total alokasi bila kosong.
    """
    en_rows = doc.get("custom_expense_notes") or []
    txn_rows = [r for r in (doc.get("custom_transactions") or []) if r.transaction]
    has_derived = any(
        (r.get("custom_expense_note") or r.get("custom_from_transaction"))
        for r in (doc.get("references") or [])
    )
    if not en_rows and not txn_rows and not has_derived:
        return  # tak ada tabel tarikan di dokumen ini

    # Pertahankan References manual, buang yang turunan tabel lalu bangun ulang.
    manual_refs = [
        r for r in (doc.get("references") or [])
        if not (r.get("custom_expense_note") or r.get("custom_from_transaction"))
    ]
    doc.set("references", manual_refs)

    total_alloc = 0.0
    for r in en_rows:
        if not r.expense_note:
            continue
        je = r.journal_entry or frappe.db.get_value("Expense Note", r.expense_note, "journal_entry")
        if not je:
            frappe.throw(
                f"Expense Note <b>{r.expense_note}</b> belum punya Journal Entry "
                "(belum Validate?), tidak bisa dibayar."
            )
        r.journal_entry = je
        alloc = flt(r.allocated) if flt(r.allocated) > 0 else flt(r.outstanding)
        r.allocated = alloc
        total_alloc += alloc
        doc.append("references", {
            "reference_doctype": "Journal Entry",
            "reference_name": je,
            "allocated_amount": alloc,
            "custom_expense_note": r.expense_note,
        })

    for r in txn_rows:
        alloc = flt(r.allocated) if flt(r.allocated) > 0 else flt(r.outstanding)
        r.allocated = alloc
        total_alloc += alloc
        doc.append("references", {
            "reference_doctype": r.reference_doctype,
            "reference_name": r.transaction,
            "total_amount": flt(r.grand_total),
            "outstanding_amount": flt(r.outstanding),
            "allocated_amount": alloc,
            "custom_from_transaction": 1,
        })

    # Bila user belum mengisi paid_amount, set = total alokasi (uang yang keluar dari bank).
    if total_alloc > 0 and flt(doc.paid_amount) <= 0:
        doc.paid_amount = total_alloc
        if flt(doc.source_exchange_rate or 0) in (0, 1) and flt(doc.target_exchange_rate or 0) in (0, 1):
            doc.received_amount = total_alloc


def update_expense_note_paid_status(doc, method=None):
	"""Setelah Payment Entry submit/cancel: set flag `paid` di tiap Expense Note yang
	ditarik (references ber-custom_expense_note). Paid = sisa hutang JE-nya <= 0,
	dihitung dengan helper ERPNext yang sama dipakai saat menarik EN."""
	ens = {r.get("custom_expense_note") for r in (doc.get("references") or []) if r.get("custom_expense_note")}
	if not ens:
		return
	get_outstanding_on_journal_entry = frappe.get_attr(
		"erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_on_journal_entry"
	)
	for en in ens:
		if not frappe.db.exists("Expense Note", en):
			continue
		je, vendor, validated = frappe.db.get_value(
			"Expense Note", en, ["journal_entry", "vendor", "validated"]
		)
		paid = 0
		if je and validated:
			outstanding, _total = get_outstanding_on_journal_entry(je, "Supplier", vendor)
			paid = 1 if flt(outstanding) <= 0.005 else 0
		frappe.db.set_value(
			"Expense Note",
			en,
			{"paid": paid, "paid_date": frappe.utils.now() if paid else None},
			update_modified=False,
		)


@frappe.whitelist()
def get_party_outstanding_transactions(party_type, party, company, payment_type):
    """Transaksi outstanding milik party untuk tombol "Tarik Transaksi":
    Customer -> Sales Invoice, Supplier -> Purchase Invoice. Angka dari mesin
    ERPNext (get_outstanding_reference_documents) — sumber yang SAMA dipakai
    dialog native Get Outstanding Invoices, jadi tak akan beda."""
    if not (party_type and party):
        return []

    from erpnext.accounts.party import get_party_account

    get_docs = frappe.get_attr(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents"
    )
    args = {
        "posting_date": frappe.utils.nowdate(),
        "company": company,
        "party_type": party_type,
        "party": party,
        "party_account": get_party_account(party_type, party, company),
        "payment_type": payment_type,
        "get_outstanding_invoices": 1,
    }
    want = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    out = []
    for d in get_docs(args) or []:
        if d.get("voucher_type") != want or flt(d.get("outstanding_amount")) <= 0:
            continue
        out.append({
            "reference_doctype": d.get("voucher_type"),
            "transaction": d.get("voucher_no"),
            "date": str(d.get("posting_date") or ""),
            "grand_total": flt(d.get("invoice_amount")),
            "outstanding": flt(d.get("outstanding_amount")),
        })
    return out


@frappe.whitelist()
def get_expense_note_outstanding(supplier, company=None):
    """Expense Note (Validated, belum Void) milik `supplier` yang Journal Entry-nya
    masih punya sisa hutang di akun payable supplier. Untuk dialog "Tarik Expense Note"."""
    get_outstanding_on_journal_entry = frappe.get_attr(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_on_journal_entry"
    )

    if not supplier:
        return []

    filters = {"vendor": supplier, "validated": 1, "void": 0}
    if company:
        filters["company"] = company

    ens = frappe.get_all(
        "Expense Note",
        filters=filters,
        fields=["name", "journal_entry", "net_total", "date", "currency"],
        order_by="date asc, name asc",
    )

    out = []
    for en in ens:
        if not en.journal_entry:
            continue
        outstanding, total = get_outstanding_on_journal_entry(
            en.journal_entry, "Supplier", supplier
        )
        if flt(outstanding) <= 0.005:
            continue
        out.append({
            "expense_note": en.name,
            "journal_entry": en.journal_entry,
            "posting_date": str(en.date) if en.date else None,
            "net_total": flt(en.net_total),
            "total_amount": flt(total),
            "outstanding": flt(outstanding),
            "currency": en.currency,
        })
    return out

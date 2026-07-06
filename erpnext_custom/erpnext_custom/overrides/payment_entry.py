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
from frappe.utils.data import flt


def before_validate(doc, method=None):
    """Turunkan baris References dari tabel custom_expense_notes (tabel = sumber kebenaran).

    Tiap Expense Note pada tabel → satu baris References reference_doctype="Journal Entry"
    (JE yang dibuat EN saat Validate), allocated = kolom "Dibayar" (default = Sisa Hutang).
    References milik EN ditandai dgn custom_expense_note; References lain (mis. Purchase
    Invoice yang ditambah manual) dibiarkan. paid_amount diisi = total alokasi bila kosong.
    """
    en_rows = doc.get("custom_expense_notes") or []
    has_en_refs = any((r.get("custom_expense_note") for r in (doc.get("references") or [])))
    if not en_rows and not has_en_refs:
        return  # tak ada urusan Expense Note di dokumen ini

    # Pertahankan References non-EN (ditambah manual), buang yang turunan EN lalu bangun ulang.
    non_en_refs = [r for r in (doc.get("references") or []) if not r.get("custom_expense_note")]
    doc.set("references", non_en_refs)

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

"""Cek Credit / Debit Note per baris Payment Item (tidak menyentuh DB).

Jalankan:
    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console <<'EOF'
    exec("from erpnext_custom.overrides.check_cn_dn import run; run()", {})
    EOF

Yang dijaga: arah jurnalnya (Credit Note mendebit akunnya, Debit Note mengkredit) dan
uang bank hasilnya, untuk Pay maupun Receive, termasuk dokumen retur (alokasi negatif).
"""

import frappe
from frappe.utils.data import flt

from erpnext_custom.overrides.payment_entry import _apply_items_adjustment

# (label, payment_type, alokasi, credit note, debit note, paid harapan, total deductions harapan)
CASES = [
	("PV + Debit Note (potongan)", "Pay", 10_000_000, 0, 500_000, 9_500_000, -500_000),
	("PV + Credit Note (tagihan tambahan)", "Pay", 10_000_000, 300_000, 0, 10_300_000, 300_000),
	("RV + Credit Note (diskon)", "Receive", 10_000_000, 500_000, 0, 9_500_000, 500_000),
	("RV + Debit Note (denda)", "Receive", 10_000_000, 0, 250_000, 10_250_000, -250_000),
	("PV retur + Debit Note (tanda dibalik)", "Pay", -10_000_000, 0, 500_000, -9_500_000, 500_000),
	("PV CN = DN (reklas, kas tak bergerak)", "Pay", 10_000_000, 750_000, 750_000, 10_000_000, 0),
]


def run():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	account = frappe.get_all("Account", filters={"company": company, "is_group": 0}, pluck="name")[0]

	for label, payment_type, alloc, cn, dn, want_paid, want_deductions in CASES:
		doc = frappe.new_doc("Payment Entry")
		doc.company = company
		doc.payment_type = payment_type
		doc.posting_date = frappe.utils.today()
		doc.cost_center = cost_center
		doc.append("custom_items", {
			"document_type": "Expense Note", "document_no": "CEK-001", "amount": alloc,
			"credit_amount": cn, "debit_amount": dn,
			"credit_account": account, "debit_account": account,
		})
		doc.append("references", {
			"reference_doctype": "Journal Entry", "reference_name": "CEK-JE",
			"allocated_amount": alloc,
		})
		_apply_items_adjustment(doc)
		deductions = sum(flt(d.amount) for d in doc.get("deductions") or [])
		assert abs(flt(doc.paid_amount) - want_paid) < 0.005, \
			f"{label}: paid {doc.paid_amount}, seharusnya {want_paid}"
		assert abs(deductions - want_deductions) < 0.005, \
			f"{label}: deductions {deductions}, seharusnya {want_deductions}"
		print("OK", label)
	print("Semua lulus")

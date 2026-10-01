"""Jurnal AR Note. Jalankan:

	bench --site erp.localhost execute erp.fico.doctype.ar_note.test_ar_note.run

Yang dijaga: Validate = Dr Piutang customer (ber-party, outstanding di Payment Ledger
sebesar Net Total), Cr pendapatan + PPN, Dr PPh; batal validasi menghapus jurnalnya.
Semuanya di-rollback di akhir, tidak ada data yang tertinggal.
"""

import frappe
from frappe.utils import flt


def run():
	try:
		_check()
		print("AR Note OK")
	finally:
		frappe.db.rollback()


def _check():
	company = frappe.defaults.get_global_default("company")
	income = frappe.get_all("Account", {"root_type": "Income", "is_group": 0, "company": company, "account_type": ["not in", ["Receivable", "Payable"]]}, pluck="name", limit=1)[0]
	doc = frappe.get_doc({
		"doctype": "AR Note",
		"customer": frappe.get_all("Customer", pluck="name", limit=1)[0],
		"date": frappe.utils.today(),
		"cost_center": frappe.get_all("Cost Center", {"is_group": 0, "company": company}, pluck="name", limit=1)[0],
		"tax_pct": 11,
		"pph_pct": 2,
		"materai_amount": 10000,
		"items": [
			{"description": "Klaim demurrage", "account": income, "qty": 2, "price": 500000},
			{"description": "Biaya admin", "account": income, "qty": 1, "price": 250000},
		],
	}).insert()
	assert doc.name.startswith("AR/"), doc.name
	assert flt(doc.total_amount) == 1250000
	assert flt(doc.net_total) == 1250000 + 137500 - 25000 + 10000, doc.net_total

	doc.validated = 1
	doc.save()
	assert doc.status == "Validated" and doc.journal_entry
	je = frappe.get_doc("Journal Entry", doc.journal_entry)
	assert je.docstatus == 1
	dr = [a for a in je.accounts if a.party_type == "Customer"]
	assert len(dr) == 1 and flt(dr[0].debit) == flt(doc.net_total), dr
	outstanding = frappe.db.sql(
		"select sum(amount) from `tabPayment Ledger Entry` where voucher_no=%s and delinked=0", je.name
	)[0][0]
	assert flt(outstanding) == flt(doc.net_total), outstanding

	doc.validated = 0
	doc.save()
	assert not doc.journal_entry and not frappe.db.exists("Journal Entry", je.name)

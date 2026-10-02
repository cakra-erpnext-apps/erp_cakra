"""Cek aturan menu Tax (tax_records.py). Selalu rollback.

bench --site <site> console:  from erpnext_custom import test_tax_records; test_tax_records.run()
Butuh minimal satu Purchase Invoice submit dan satu Expense Note validated.
"""

import frappe

from erpnext_custom.tax_records import permission_query, sync


def run():
	try:
		_run()
		print("test_tax_records OK")
	finally:
		frappe.db.rollback()


def _run():
	pi = frappe.get_all("Purchase Invoice", filters={"docstatus": 1}, pluck="name", limit=1)[0]
	sync(frappe.get_doc("Purchase Invoice", pi))
	rec = frappe.get_doc("Tax Purchase", pi)
	rec.db_set({"tax_no": "", "status": "Belum", "execution_date": None, "execution_by": None})

	# isi pertama: Execution & Modify dicap, Status Sudah, field Tax No di PI ikut terisi
	rec = frappe.get_doc("Tax Purchase", pi)
	rec.tax_no = " 010.000-26.00000001 "
	rec.save()
	assert rec.status == "Sudah" and rec.tax_no == "010.000-26.00000001"
	assert rec.execution_by and rec.execution_date and rec.modify_by
	assert frappe.db.get_value("Purchase Invoice", pi, "custom_tax_no") == "010.000-26.00000001"
	first = rec.execution_date

	# ubah: Execution tetap, field milik sumber/sistem tidak bisa ditimpa dari form
	rec.tax_no, rec.party, rec.execution_date, rec.status = "010.000-26.00000002", "HACK", None, "Batal"
	rec.save()
	assert rec.execution_date == first and rec.party != "HACK" and rec.status == "Sudah"

	# baris tidak bisa dibuat manual
	try:
		frappe.get_doc({"doctype": "Tax Purchase", "reference_doctype": "Purchase Invoice", "reference_name": "X"}).insert()
		raise AssertionError("insert manual harus ditolak")
	except frappe.ValidationError:
		pass

	# sumber batal: No Tax terisi -> Batal; jadi lagi -> Status dihitung ulang
	src = frappe.get_doc("Purchase Invoice", pi)
	src.docstatus = 2
	sync(src)
	assert frappe.db.get_value("Tax Purchase", pi, "status") == "Batal"
	src.docstatus = 1
	sync(src)
	assert frappe.db.get_value("Tax Purchase", pi, "status") == "Sudah"

	# EN un-validate tanpa No Tax -> baris hilang; validate lagi -> muncul lagi
	en = frappe.get_all("Expense Note", filters={"validated": 1, "void": 0}, pluck="name", limit=1)[0]
	doc = frappe.get_doc("Expense Note", en)
	sync(doc)
	frappe.db.set_value("Tax Expense", en, "tax_no", "")
	doc.validated = 0
	sync(doc)
	assert not frappe.db.exists("Tax Expense", en)
	doc.validated = 1
	sync(doc)
	assert frappe.db.exists("Tax Expense", en)

	# confidential AP/AR Note: user biasa disaring, manager tidak
	assert permission_query("Administrator") == ""
	frappe.set_user("Guest")
	try:
		assert "confidential = 0" in permission_query("Guest")
	finally:
		frappe.set_user("Administrator")

"""Menu Tax pindah dari halaman tax-register + doctype Tax Number (satu tabel untuk semua)
ke empat doctype per menu (Tax Invoice/Expense/ARAP Note/Purchase), lalu isi barisnya untuk
semua dokumen sumber yang sudah jadi. Tax Number di prod masih kosong saat diganti."""

import frappe

from erpnext_custom.tax_records import backfill


def execute():
	if frappe.db.exists("Page", "tax-register"):
		frappe.delete_doc("Page", "tax-register", force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", "Tax Number"):
		frappe.delete_doc("DocType", "Tax Number", force=True, ignore_permissions=True)
	# delete_doc DocType tidak men-drop tabelnya
	frappe.db.sql_ddl("drop table if exists `tabTax Number`")
	backfill()

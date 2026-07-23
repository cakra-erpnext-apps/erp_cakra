"""Gabungkan CMI Invoice Settings + Expense Note Settings -> ERPNext Custom Setting.

Satu Single untuk semua setting (tab Invoice Setting / Expense Note Setting / Flag).
Nilai lama disalin dari tabSingles (dibaca langsung lewat SQL supaya tetap jalan walau
meta doctype lamanya sudah hilang), lalu doctype lamanya dihapus.

Hanya `tax_account` yang bentrok antar dua setting: milik invoice (PPN Keluaran) pindah
ke `sales_tax_account`; milik Expense Note (PPN Masukan) memakai nama aslinya.
"""

import frappe

TARGET = "ERPNext Custom Setting"

# doctype lama -> {field lama: field baru}
SOURCES = {
	"CMI Invoice Settings": {
		"tax_account": "sales_tax_account",
		"pph23_account": "pph23_account",
		"materai_account": "materai_account",
		"default_tax_percent": "default_tax_percent",
		"default_pph23_percent": "default_pph23_percent",
		"purchase_tax_account": "purchase_tax_account",
		"purchase_pph_account": "purchase_pph_account",
		"purchase_materai_account": "purchase_materai_account",
	},
	"Expense Note Settings": {
		"tax_account": "tax_account",
		"pph_account": "pph_account",
		"discount_account": "discount_account",
		"link_account": "link_account",
		"adjustment_account": "adjustment_account",
		"default_payable_account": "default_payable_account",
	},
}


def execute():
	for old_dt, mapping in SOURCES.items():
		rows = frappe.db.sql(
			"""SELECT field, value FROM `tabSingles` WHERE doctype = %s""", old_dt
		)
		for field, value in rows:
			new_field = mapping.get(field)
			# Jangan timpa nilai yang sudah ada di setting baru (patch idempoten).
			if new_field and value and not frappe.db.get_single_value(TARGET, new_field):
				frappe.db.set_single_value(TARGET, new_field, value)

		frappe.delete_doc("DocType", old_dt, force=True, ignore_missing=True)
		frappe.db.sql("""DELETE FROM `tabSingles` WHERE doctype = %s""", old_dt)

	frappe.db.commit()

import frappe


def execute():
	"""Isi dua tipe bawaan yang dipakai rumus costing.

	CRM Cost Component.type dulunya Select berisi teks ini; sekarang Link ke
	CRM Cost Type. Nama recordnya sengaja dibuat identik supaya komponen yang
	sudah ada tetap menunjuk ke tipe yang benar tanpa perlu dipetakan ulang.
	"""
	for name in ("Variable Cost", "Fixed Cost"):
		if frappe.db.exists("CRM Cost Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "CRM Cost Type",
				"type_name": name,
				"behavior": name,
				"description": "Tipe bawaan costing engine.",
			}
		).insert(ignore_permissions=True)

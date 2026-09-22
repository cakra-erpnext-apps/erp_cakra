"""Cek gerbang role tab Procurement. Jalankan:

	bench --site erp.localhost execute assistant.assistant.test_crm_procurement.run

Yang dijaga: rincian Fixed/Variable per baris produk hanya keluar untuk pemegang
role "Procurement Costing" — lewat crm_procurement MAUPUN lewat baca umum
(crm_get_record), supaya assistant tidak jadi pintu belakang panel costing.
"""

import frappe

from assistant.assistant import crm_tools

BOCOR = ("fixed_cost", "variable_cost", "cost_items")


def run():
	qt = frappe.db.get_value(
		"CRM Quotation", {"total_variable_cost": [">", 0]}, "name"
	) or frappe.db.get_value("CRM Quotation", {"total_fixed_cost": [">", 0]}, "name")
	assert qt, "Tidak ada quotation ber-costing di site ini — tes dilewati."

	plain = next(
		u
		for u in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name")
		if not set(frappe.get_roles(u)) & {"Procurement Costing", "System Manager"}
	)

	me = frappe.session.user
	try:
		frappe.set_user(plain)
		out = crm_tools.procurement(qt)
		assert out["rincian_costing_per_baris"] is not True
		for row in out["revenue"]["items"]:
			assert not set(row) & set(BOCOR), row
		# Summary & Base Price memang terbuka untuk semua, sama seperti di layar.
		assert out["summary"]["total_fixed_cost"] is not None
		assert "base_price" in out["revenue"]["items"][0]

		doc = crm_tools.get_record("CRM Quotation", qt)
		assert "cost_items" not in doc
		assert all(not set(p) & set(BOCOR) for p in doc.get("products") or [])
		rows = crm_tools.list_records("CRM Products", {"parent": qt}, ["name", "fixed_cost"])
		assert all("fixed_cost" not in r for r in rows), rows
	finally:
		frappe.set_user(me)

	out = crm_tools.procurement(qt)
	assert out["rincian_costing_per_baris"] is True
	assert "fixed_cost" in out["revenue"]["items"][0]
	assert "cost_items" in crm_tools.get_record("CRM Quotation", qt)

	print(f"OK — gerbang costing utuh ({qt}, user uji: {plain})")

"""Aturan draft CRM Assistant: tidak menyimpan, quotation wajib inquiry, draft milik pembuatnya.

bench --site erp.localhost execute assistant.assistant.test_crm_draft.run
"""

import frappe

from assistant.assistant import crm, crm_tools


def run():
	frappe.set_user("Administrator")
	inq = frappe.get_all("CRM Inquiry", filters={"status": ["!=", "Lost"]}, pluck="name", limit=1)
	assert inq, "Tidak ada inquiry di site ini — tes dilewati."
	before = frappe.db.count("CRM Quotation")

	# Quotation tanpa inquiry selalu ditolak.
	assert "_error" in crm_tools.create_draft("CRM Quotation", {"attention": "x", "type": "EMKL.M"})

	# Field wajib kosong + pilihan Select salah -> tidak ada draft, daftar kekurangannya keluar.
	out = crm_tools.create_draft("CRM Inquiry", {"transportation_mode": "Truck"})
	assert out["draft_dibuat"] is False
	assert out["field_wajib_kosong"] and out["isian_tidak_valid"], out

	# Draft lengkap: ada link, tidak ada dokumen baru, hanya pembuat yang bisa membukanya.
	out = crm_tools.create_draft(
		"CRM Quotation",
		{"inquiry": inq[0], "attention": "x", "type": frappe.get_all("Packing List Type", pluck="name", limit=1)[0],
		 "cargo": "x", "packaging": "x", "products": [{"product_code": frappe.get_all("CRM Product", pluck="name", limit=1)[0], "qty": 1, "price": 1}]},
	)
	assert out.get("draft_dibuat") is True, out
	assert frappe.db.count("CRM Quotation") == before
	token = out["url"].split("draft=")[-1]
	assert crm.get_draft(token)["values"]["inquiry"] == inq[0]
	other = frappe.get_all("User", filters={"name": ["not in", ["Administrator", "Guest"]], "enabled": 1}, pluck="name", limit=1)[0]
	frappe.set_user(other)
	try:
		crm.get_draft(token)
		raise AssertionError("draft bocor ke user lain")
	except frappe.ValidationError:
		pass
	finally:
		frappe.set_user("Administrator")

	# Operator yang ditulis di dalam nilai filter tetap bekerja.
	assert crm_tools._norm_filters({"name": "like %a%", "status": "!= Lost", "x": "Won"}) == {
		"name": ["like", "%a%"], "status": ["!=", "Lost"], "x": "Won",
	}
	print("OK — draft tidak menyimpan, quotation wajib inquiry, draft per user, filter like")

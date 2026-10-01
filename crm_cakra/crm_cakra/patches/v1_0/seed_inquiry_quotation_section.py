import json

import frappe

SECTION = {
	"label": "Quotation",
	"name": "quotations_section",
	"opened": True,
	"editable": False,
	"columns": [{"name": "column_quotations", "fields": []}],
}


def execute():
	"""Pasang section Quotation di side panel Inquiry, di bawah Account Details.

	Isinya dirender komponen sendiri (QuotationsPanel), jadi section-nya memang
	tanpa field -- yang dibutuhkan cuma tempatnya ada di layout. Lewat patch
	karena layout itu data di DB, tidak ikut terbawa git pull.

	Idempoten: kalau section-nya sudah ada, layout tidak disentuh sama sekali --
	termasuk kalau user sudah memindahkannya ke urutan lain.
	"""
	row = frappe.db.exists("CRM Fields Layout", {"dt": "CRM Inquiry", "type": "Side Panel"})
	if not row:
		return

	doc = frappe.get_doc("CRM Fields Layout", row)
	layout = json.loads(doc.layout or "[]")
	if any(s.get("name") == SECTION["name"] for s in layout):
		return

	# Ditaruh tepat sesudah Organization Details (Account) kalau ada; kalau tidak,
	# di paling bawah.
	posisi = len(layout)
	for i, s in enumerate(layout):
		if s.get("name") == "organization_section":
			posisi = i + 1
			break

	layout.insert(posisi, SECTION)
	doc.layout = json.dumps(layout)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

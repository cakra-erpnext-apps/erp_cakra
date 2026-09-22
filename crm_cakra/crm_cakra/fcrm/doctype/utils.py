import json

import frappe


def add_or_remove_lost_reason_section_in_sidepanel(doc):
	doctype = doc.doctype
	if doctype not in ("CRM Inquiry", "CRM Lead"):
		return

	status_doctype = "CRM Inquiry Status" if doctype == "CRM Inquiry" else "CRM Lead Status"

	status = None
	if getattr(doc, "status", None):
		status = frappe.db.get_value(status_doctype, doc.status, "type")
	is_lost = status and status == "Lost"

	layout_doc = frappe.get_doc("CRM Fields Layout", f"{doctype}-Side Panel")
	sections = json.loads(layout_doc.layout)

	# `competitor` hanya ada di Inquiry. Lead WAJIB dikecualikan: get_sidepanel_sections
	# meninggalkan field yang tidak dikenal doctype-nya sebagai string mentah (bukan
	# objek field), dan panel Lead akan merender sampah karenanya.
	fields = ["lost_notes"]
	if doctype == "CRM Inquiry":
		fields = ["competitor", "lost_notes"]

	lost_reason_section = {
		"name": "lost_reason_section",
		"label": "Lost Reason",
		"opened": True,
		"columns": [
			{
				"name": "lost_reason_column",
				"fields": fields,
			}
		],
	}

	existing = next((s for s in sections if s.get("name") == "lost_reason_section"), None)

	if is_lost:
		# Bukan cuma "ada atau tidak": section yang sudah telanjur dibuat versi lama
		# isinya field lama, dan kalau cuma dicek keberadaannya, field baru tidak akan
		# pernah muncul di panel siapa pun. Jadi cocokkan isinya, bukan namanya.
		if existing == lost_reason_section:
			return
		if existing:
			sections = [lost_reason_section if s.get("name") == "lost_reason_section" else s for s in sections]
		elif sections and sections[0].get("name") == "contacts_section":
			sections = [*sections[:1], lost_reason_section, *sections[1:]]
		else:
			sections = [lost_reason_section, *sections]
	elif existing:
		sections = [section for section in sections if section.get("name") != "lost_reason_section"]
	else:
		return

	layout_doc.layout = json.dumps(sections)
	layout_doc.save(ignore_permissions=True)

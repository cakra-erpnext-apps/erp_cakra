import json

import frappe


def execute():
	if not frappe.db.exists("CRM Fields Layout", "CRM Inquiry-Quick Entry"):
		return

	inquiry = frappe.db.get_value("CRM Fields Layout", "CRM Inquiry-Quick Entry", "layout")

	layout = json.loads(inquiry)
	for section in layout:
		if section.get("label") in [
			"Select Organization",
			"Organization Details",
			"Select Contact",
			"Contact Details",
		]:
			section["editable"] = False

	frappe.db.set_value("CRM Fields Layout", "CRM Inquiry-Quick Entry", "layout", json.dumps(layout))

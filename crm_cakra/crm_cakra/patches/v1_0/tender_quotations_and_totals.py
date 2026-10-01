import json

import frappe


def execute():
	"""Tender: Document Date + satu tender banyak quotation; Quotation: Net Total |
	Estimation Cost | Margin sebaris.

	Link tender -> quotation dulu satu field `quotation` di Tender. Sekarang arahnya
	dibalik (field `tender` di Quotation), jadi link lama dipindahkan dan field
	`quotation` keluar dari layout Tender. Layout diubah di tempat, bukan ditimpa,
	supaya kustomisasi lain di layout yang sama tidak hilang.
	"""
	for name in ("CRM Tender-Data Fields", "CRM Tender-Side Panel"):
		update_layout(name, tender_layout)
	update_layout("CRM Quotation-Data Fields", quotation_layout)

	if frappe.db.has_column("CRM Tender", "quotation"):
		for tender, quotation in frappe.db.sql(
			"select name, quotation from `tabCRM Tender` where ifnull(quotation, '') != ''"
		):
			if frappe.db.exists("CRM Quotation", quotation) and not frappe.db.get_value(
				"CRM Quotation", quotation, "tender"
			):
				frappe.db.set_value("CRM Quotation", quotation, "tender", tender, update_modified=False)


def update_layout(name, fn):
	if not frappe.db.exists("CRM Fields Layout", name):
		return
	layout = json.loads(frappe.db.get_value("CRM Fields Layout", name, "layout") or "[]")
	fn(layout)
	frappe.db.set_value("CRM Fields Layout", name, "layout", json.dumps(layout))


def columns(layout):
	# Data Fields = daftar tab berisi sections; Side Panel = daftar sections langsung.
	for item in layout:
		for section in item.get("sections", [item]):
			yield from section.get("columns", [])


def tender_layout(layout):
	for col in columns(layout):
		fields = [f for f in col["fields"] if f != "quotation"]
		if "issue_date" in fields and "document_date" not in fields:
			fields.insert(fields.index("issue_date") + 1, "document_date")
		col["fields"] = fields


def quotation_layout(layout):
	all_fields = [f for col in columns(layout) for f in col["fields"]]
	for col in columns(layout):
		if "inquiry" in col["fields"] and "tender" not in all_fields:
			col["fields"].insert(col["fields"].index("inquiry") + 1, "tender")

	if "estimation_costing" in all_fields:
		return
	for tab in layout:
		sections = tab.get("sections", [])
		for i, section in enumerate(sections):
			for col in section.get("columns", []):
				if "net_total" in col["fields"]:
					col["fields"].remove("net_total")
					sections.insert(
						i + 1,
						{
							"label": "",
							"name": "section_totals",
							"opened": True,
							"hideLabel": True,
							"hideBorder": True,
							"columns": [
								{"name": "col_net_total", "fields": ["net_total"]},
								{"name": "col_estimation_costing", "fields": ["estimation_costing"]},
								{"name": "col_margin", "fields": ["margin"]},
							],
						},
					)
					return

import frappe
from frappe.model.document import Document


class CRMTender(Document):
	@staticmethod
	def default_list_data():
		columns = [
			{"label": "Subject", "type": "Data", "key": "subject", "width": "20rem"},
			{"label": "Type", "type": "Link", "key": "tender_type", "width": "10rem"},
			{"label": "Account", "type": "Link", "key": "organization", "width": "12rem"},
			{"label": "Assign To", "type": "Link", "key": "assigned_to", "width": "10rem"},
			{"label": "Closing Date", "type": "Date", "key": "closing_date", "width": "10rem"},
			{"label": "Estimation Value", "type": "Currency", "key": "estimation_value", "width": "10rem"},
			{"label": "Status", "type": "Select", "key": "status", "width": "8rem"},
			{"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
		]
		rows = [
			"name",
			"subject",
			"tender_type",
			"organization",
			"assigned_to",
			"contact",
			"email",
			"inquiry",
			"quotation",
			"status",
			"issue_date",
			"closing_date",
			"result_date",
			"contract_period",
			"estimation_value",
			"currency",
			"owner",
			"creation",
			"modified",
			"_assign",
		]
		return {"columns": columns, "rows": rows}


@frappe.whitelist()
def get_attachments(tender: str):
	"""Lampiran tender, xlsx duluan -- itu yang bisa dibuka di editor."""
	frappe.has_permission("CRM Tender", "read", doc=tender, throw=True)
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "CRM Tender", "attached_to_name": tender},
		fields=["name", "file_name", "file_url", "file_size", "file_type", "creation"],
		order_by="creation asc",
		limit_page_length=0,
	)
	for f in files:
		f["editable"] = (f.file_name or "").lower().endswith((".xlsx", ".xlsm"))
	return sorted(files, key=lambda f: not f["editable"])

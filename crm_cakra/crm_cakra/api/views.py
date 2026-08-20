import frappe
from pypika import Criterion


@frappe.whitelist()
def get_views(doctype: str):
	View = frappe.qb.DocType("CRM View Settings")
	query = (
		frappe.qb.from_(View)
		.select("*")
		.where(Criterion.any([View.user == "", View.user == frappe.session.user]))
	)
	if doctype:
		query = query.where(View.dt == doctype)
	views = query.run(as_dict=True)
	return views


@frappe.whitelist()
def reset_standard_views(doctype: str | None = None, all_users: bool = False):
	"""Drop the saved list/kanban state so every list falls back to its default columns.

	Only touches is_standard views (the auto-saved per-user state) - custom saved
	views keep their columns and filters.
	"""
	filters = {"is_standard": 1}
	if doctype:
		filters["dt"] = doctype

	if frappe.parse_json(all_users):
		if not frappe.has_permission("CRM View Settings", "delete"):
			frappe.throw(
				frappe._("Not allowed to reset list views of other users"), frappe.PermissionError
			)
	else:
		filters["user"] = frappe.session.user

	count = frappe.db.count("CRM View Settings", filters)
	frappe.db.delete("CRM View Settings", filters)
	return count

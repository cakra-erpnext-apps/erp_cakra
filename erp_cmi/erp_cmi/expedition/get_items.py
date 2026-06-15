"""Build Sales Invoice item rows from expedition documents (1 container = 1 row)."""

import frappe
from frappe import _


@frappe.whitelist()
def get_container_invoice_items(source_doctype, source_name, item_code=None):
	"""Return invoice item rows, one per container of a Packing List / Shipping List.

	If item_code is given, the rows are billed as that item (uom auto-filled);
	otherwise rows carry only a description + qty (item filled in manually).
	Rate is always left at 0 for the user to fill.
	"""
	if source_doctype == "Shipping List":
		containers = frappe.get_all(
			"Shipping List Container",
			filters={"parent": source_name, "parenttype": "Shipping List"},
			fields=["bl", "container_no", "goods_description"],
			order_by="idx",
		)
	elif source_doctype == "Packing List":
		containers = frappe.get_all(
			"Packing List Item",
			filters={"parent": source_name, "parenttype": "Packing List"},
			fields=["container_no", "goods_description"],
			order_by="idx",
		)
	else:
		frappe.throw(_("Sumber tidak didukung: {0}").format(source_doctype))

	item = {}
	if item_code:
		item = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom"], as_dict=True) or {}

	rows = []
	for c in containers:
		desc = _("Container {0}").format(c.get("container_no") or "-")
		if c.get("bl"):
			desc += f" (BL {c['bl']})"
		if c.get("goods_description"):
			desc += f" — {c['goods_description']}"

		row = {"qty": 1, "rate": 0, "description": desc}
		if item_code:
			row.update(
				{
					"item_code": item_code,
					"item_name": item.get("item_name"),
					"uom": item.get("stock_uom"),
					"stock_uom": item.get("stock_uom"),
					"conversion_factor": 1,
				}
			)
		rows.append(row)

	return rows

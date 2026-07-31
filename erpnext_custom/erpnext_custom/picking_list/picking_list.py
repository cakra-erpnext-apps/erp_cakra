from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def validate_stock_availability(doc, method=None):
	"""Prevent a Pick List from allocating more than the current physical stock."""
	required = defaultdict(float)

	for row in doc.get("locations"):
		if not row.item_code or not row.warehouse:
			continue

		# ERPNext fills picked_qty from stock_qty only in before_submit. Validate
		# stock_qty too so manually edited drafts cannot bypass the stock check.
		qty = flt(row.picked_qty) if flt(row.picked_qty) > 0 else flt(row.stock_qty)
		if qty > 0:
			required[(row.item_code, row.warehouse, row.batch_no or "")] += qty

	for (item_code, warehouse, batch_no), qty in required.items():
		other_filters = {
			"parent": ["!=", doc.name],
			"parenttype": "Pick List",
			"docstatus": ["<", 2],
			"item_code": item_code,
			"warehouse": warehouse,
		}
		if batch_no:
			other_filters["batch_no"] = batch_no
		else:
			other_filters["batch_no"] = ["is", "not set"]

		allocated_elsewhere = sum(
			flt(row.picked_qty) if flt(row.picked_qty) > 0 else flt(row.stock_qty)
			for row in frappe.get_all(
				"Pick List Item",
				filters=other_filters,
				fields=["stock_qty", "picked_qty"],
			)
		)

		if batch_no:
			from erpnext.stock.doctype.batch.batch import get_batch_qty

			available = flt(get_batch_qty(batch_no, warehouse, item_code))
			scope = _("batch {0} in warehouse {1}").format(
				frappe.bold(batch_no), frappe.bold(warehouse)
			)
		else:
			available = flt(
				frappe.db.get_value(
					"Bin",
					{"item_code": item_code, "warehouse": warehouse},
					"actual_qty",
				)
			)
			scope = _("warehouse {0}").format(frappe.bold(warehouse))

		total_allocated = qty + allocated_elsewhere
		if total_allocated > available:
			frappe.throw(
				_(
					"Total Pick Qty {0} for item {1} exceeds available stock {2} in {3}. "
					"Other active Pick Lists already allocate {4}."
				).format(
					total_allocated,
					frappe.bold(item_code),
					available,
					scope,
					allocated_elsewhere,
				),
				title=_("Insufficient Stock"),
			)

import frappe
from frappe import _

from erpnext_custom.selling_amounts import compute_display, inject


def before_validate(doc, method=None):
	_sync_remark(doc)
	_set_item_expense_accounts(doc)
	inject(doc)


def validate(doc, method=None):
	compute_display(doc)
	validate_mixed_item_sources(doc)


def _set_item_expense_accounts(doc):
	"""make_delivery_note dari SO tidak membawa default expense account (HPP) milik
	Item/Item Group — barisnya jatuh ke default expense account company. Tegakkan
	default Item di sini; isian manual user (selain default company) dibiarkan."""
	company_default = frappe.get_cached_value("Company", doc.company, "default_expense_account")
	for row in doc.get("items"):
		if not row.item_code:
			continue
		if row.get("expense_account") and row.expense_account != company_default:
			continue  # user sudah memilih akun sendiri
		account = frappe.db.get_value(
			"Item Default", {"parent": row.item_code, "company": doc.company}, "expense_account"
		) or frappe.db.get_value(
			"Item Default",
			{
				"parent": frappe.db.get_value("Item", row.item_code, "item_group"),
				"company": doc.company,
			},
			"expense_account",
		)
		if account:
			row.expense_account = account


def _sync_remark(doc):
	if doc.get("custom_remark"):
		doc.remarks = doc.custom_remark
	elif doc.get("remarks"):
		doc.custom_remark = doc.remarks


def validate_mixed_item_sources(doc):
	"""Do not let the same item be added once from PL and again from SO/manual."""
	rows_by_item = {}
	for row in doc.get("items"):
		if not row.item_code:
			continue
		key = (row.item_code, row.warehouse or "")
		state = rows_by_item.setdefault(key, {"pick_list": [], "other": []})
		if row.get("pick_list_item"):
			state["pick_list"].append(row.idx)
		else:
			state["other"].append(row.idx)

	for (item_code, warehouse), rows in rows_by_item.items():
		if rows["pick_list"] and rows["other"]:
			frappe.throw(
				_(
					"Item {0} in warehouse {1} was added from both Picking List "
					"(row {2}) and Sales Order/manual (row {3}). Use the Picking List "
					"row only to prevent duplicate delivery."
				).format(
					frappe.bold(item_code),
					frappe.bold(warehouse or "-"),
					", ".join(map(str, rows["pick_list"])),
					", ".join(map(str, rows["other"])),
				),
				title=_("Duplicate Delivery Source"),
			)


@frappe.whitelist()
def get_pick_list_query(doctype, txt, searchfield, start, page_len, filters):
	"""Show both SO-linked and standalone Delivery Pick Lists in the DN picker."""
	frappe.has_permission("Pick List", throw=True)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

	if not filters.get("company"):
		frappe.throw(_("Please select a Company"))

	conditions = [
		"pl.docstatus = 1",
		"pl.status IN ('Open', 'Partly Delivered')",
		"pl.purpose = 'Delivery'",
		"pl.company = %(company)s",
	]
	values = {
		"company": filters.get("company"),
		"customer": filters.get("customer") or "",
		"sales_order": filters.get("sales_order") or "",
		"txt": f"%{txt or ''}%",
		"start": int(start or 0),
		"page_len": int(page_len or 20),
	}

	if values["customer"]:
		conditions.append("pl.customer = %(customer)s")
	if values["sales_order"]:
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabPick List Item` f "
			"WHERE f.parent = pl.name AND f.sales_order = %(sales_order)s)"
		)
	if txt:
		conditions.append("(pl.name LIKE %(txt)s OR pl.customer LIKE %(txt)s)")

	return frappe.db.sql(
		f"""
			SELECT
				pl.name,
				pl.customer,
				REPLACE(GROUP_CONCAT(DISTINCT pli.sales_order), ',', '<br>') AS sales_order
			FROM `tabPick List` pl
			INNER JOIN `tabPick List Item` pli ON pli.parent = pl.name
			WHERE {' AND '.join(conditions)}
			GROUP BY pl.name, pl.customer
			ORDER BY pl.modified DESC
			LIMIT %(start)s, %(page_len)s
		""",
		values,
		as_dict=True,
	)

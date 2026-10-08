import frappe

from erpnext_custom.selling_amounts import compute_display, inject


def autoname(doc, method=None):
	"""SO/{TYPE}/{COMPANY}/{YEAR}/{####}, pola sama dengan nomor PO."""
	from erpnext_custom.purchase_order.naming import make_type_name

	doc.name = make_type_name(doc, "SO")


def before_validate(doc, method=None):
	_sync_remark(doc)
	# Branch: default dari Type, pilihan user menang (cermin fetch_if_empty di form).
	if not doc.get("branch_office") and doc.get("custom_type"):
		doc.branch_office = frappe.db.get_value("Sales Order Type", doc.custom_type, "branch")
	inject(doc)


def validate(doc, method=None):
	compute_display(doc)


def _sync_remark(doc):
	if doc.get("custom_remark"):
		doc.remarks = doc.custom_remark
	elif doc.get("remarks"):
		doc.custom_remark = doc.remarks


def on_submit(doc, method=None):
	# Kolom list Verified By / Verify Date (pola custom_validated_* di PO).
	doc.db_set({"custom_validated_by": frappe.session.user, "custom_validated_date": frappe.utils.now()})


# Kolom list "Delivery Note" / "Invoice No": nomor dokumen (draft + submitted) yang menunjuk
# SO ini, disimpan sebagai teks supaya bisa jadi kolom list (pola custom_purchases di PO).
# SQL yang sama dipakai backfill tiap migrate (install._backfill_sales_order_links).
LINK_SQL = {
	"custom_dn_nos": """select distinct parent from `tabDelivery Note Item`
		where against_sales_order = %(so)s and docstatus < 2 order by parent""",
	"custom_si_nos": """select parent from `tabSales Invoice Item`
		where sales_order = %(so)s and docstatus < 2
		union
		select r.parent from `tabInvoice Sales Order Ref` r
		join `tabSales Invoice` si on si.name = r.parent
		where r.parenttype = 'Sales Invoice' and r.sales_order = %(so)s and si.docstatus < 2
		order by 1""",
}


def refresh_links(sales_order):
	for field, sql in LINK_SQL.items():
		value = ", ".join(r[0] for r in frappe.db.sql(sql, {"so": sales_order}))
		if (frappe.db.get_value("Sales Order", sales_order, field) or "") != value:
			# update_modified=False: kolom turunan, jangan mengotori Modified SO.
			frappe.db.set_value("Sales Order", sales_order, field, value, update_modified=False)


def sync_linked_sales_orders(doc, method=None):
	"""Hook Delivery Note / Sales Invoice: hitung ulang SO yang ditunjuk dokumen ini.
	ponytail: SO yang barisnya DIHAPUS dari draft baru bersih saat migrate (backfill)."""
	names = {d.get("against_sales_order") or d.get("sales_order") for d in doc.get("items") or []}
	names |= {r.get("sales_order") for r in doc.get("custom_sales_orders") or []}
	for name in filter(None, names):
		refresh_links(name)

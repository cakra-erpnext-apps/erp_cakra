"""Sparepart langsung dipakai (aturan tipe pembelian #5).

Baris Purchase Receipt ber-Vehicle = sparepart itu dipakai langsung ke kendaraan
tersebut: barang tetap diterima ke gudang dulu (qty jujur, alur PR -> PI tetap
normal), lalu pada submit yang sama otomatis dibuat Stock Entry Material Issue
sehingga stoknya langsung nol dan nilainya jadi beban (default expense account
Item). Vehicle per BARIS — baris tanpa Vehicle jadi stok biasa.

Void/Invalidate PR membatalkan Material Issue-nya lebih dulu — kalau tidak,
pembatalan PR ditolak ERPNext karena stok akan minus.
"""

import frappe
from frappe import _


def issue_on_submit(doc, method=None):
	rows = [
		r for r in doc.items
		if r.item_code and r.get("custom_vehicle")
		and frappe.get_cached_value("Item", r.item_code, "is_stock_item")
	]
	if not rows:
		return

	vehicles = sorted({r.custom_vehicle for r in rows})
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.company = doc.company
	se.set_posting_time = 1
	se.posting_date = doc.posting_date
	se.posting_time = doc.posting_time
	se.remarks = _("Sparepart dipakai langsung dari {0}, kendaraan {1}").format(
		doc.name, ", ".join(vehicles)
	)
	for r in rows:
		se.append("items", {
			"item_code": r.item_code,
			"qty": r.stock_qty or r.qty,
			"s_warehouse": r.warehouse,
			"expense_account": _expense_account(r.item_code, doc.company),
		})
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	doc.db_set("custom_sparepart_issue", se.name, update_modified=False)


def cancel_issue_before_cancel(doc, method=None):
	se_name = doc.get("custom_sparepart_issue")
	if not se_name or not frappe.db.exists("Stock Entry", se_name):
		return
	se = frappe.get_doc("Stock Entry", se_name)
	if se.docstatus == 1:
		se.flags.ignore_permissions = True
		se.cancel()
	doc.db_set("custom_sparepart_issue", None, update_modified=False)


# Field harga/akunting di edit-row Purchase Receipt Item yang tidak dipakai user
# (rate ikut PO / price list). Disembunyikan via Property Setter (idempotent,
# dipanggil dari install.after_migrate).
PR_ITEM_HIDE = (
	"rate", "amount", "base_rate", "base_amount", "is_free_item",
	"net_rate", "net_amount", "item_tax_template",
	"base_net_rate", "base_net_amount", "landed_cost_voucher_amount",
	"amount_difference_with_purchase_invoice", "billed_amt",
)


def ensure_view_properties():
	props = [("Purchase Receipt Item", f, "hidden", "1", "Check") for f in PR_ITEM_HIDE]
	props.append(("Purchase Receipt Item", "accounting_details_section", "collapsible", "1", "Check"))
	# WMS ringan: warehouse core = lokasi posting sebenarnya, dipakai sebagai RAK
	# (custom_gudang cuma filter gudangnya — lihat install.SPAREPART_FIELDS).
	props.append(("Purchase Receipt Item", "warehouse", "label", "Rack", "Data"))
	for doc_type, field_name, prop, value, property_type in props:
		filters = {"doc_type": doc_type, "field_name": field_name, "property": prop}
		name = frappe.db.exists("Property Setter", filters)
		setter = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
		setter.update({
			"doctype_or_field": "DocField",
			**filters,
			"value": value,
			"property_type": property_type,
			"module": "ERPNext Custom",
		})
		setter.save(ignore_permissions=True)


def _expense_account(item_code, company):
	account = frappe.db.get_value(
		"Item Default", {"parent": item_code, "company": company}, "expense_account"
	) or frappe.db.get_value(
		"Item Default",
		{"parent": frappe.db.get_value("Item", item_code, "item_group"), "company": company},
		"expense_account",
	)
	if not account:
		frappe.throw(
			_("Item {0} belum punya Default Expense Account (akun beban sparepart) untuk {1}.").format(
				item_code, company
			)
		)
	return account

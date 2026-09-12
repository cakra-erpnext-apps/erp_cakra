"""Baris pembelian aset di Purchase Invoice yang belum jadi kartu Asset.

CMI sengaja TIDAK memakai `auto_create_assets`: kartu Asset dibuat manual supaya
nama/nopol tiap unit bisa diisi sendiri. Akibatnya jurnal aset (Dr Fixed Asset)
sudah masuk dari PI, tapi kartunya bisa saja lupa dibuat -- neraca punya angka,
daftar aset tidak punya barangnya. Laporan ini menutup celah itu: per baris PI
aset, berapa unit yang sudah punya kartu dan berapa yang belum.

Pencocokan aset ke baris PI pakai `purchase_invoice` + `item_code`, BUKAN
`purchase_invoice_item`, karena aset yang dibuat manual biasanya cuma mengisi
nomor invoice-nya. Karena itu baris PI dengan item yang sama digabung jadi satu.
"""

import frappe
from frappe import _
from frappe.utils import flt

STATUS_BELUM = "Belum"
STATUS_SEBAGIAN = "Sebagian"
STATUS_SUDAH = "Sudah"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_data(filters):
	invoices = _get_invoices(filters)
	if not invoices:
		return []

	rows = {}
	for item in frappe.get_all(
		"Purchase Invoice Item",
		filters={"parent": ("in", list(invoices)), "is_fixed_asset": 1, "docstatus": 1},
		fields=["parent", "item_code", "item_name", "asset_category", "qty",
		        "base_net_amount", "asset_location"],
	):
		if filters.get("item_code") and item.item_code != filters.item_code:
			continue
		pi = invoices[item.parent]
		row = rows.setdefault(
			(item.parent, item.item_code),
			{
				"purchase_invoice": item.parent,
				"posting_date": pi.posting_date,
				"supplier": pi.supplier,
				"item_code": item.item_code,
				"item_name": item.item_name,
				"asset_category": item.asset_category,
				"asset_location": item.asset_location,
				"qty": 0.0,
				"amount": 0.0,
				"company": pi.company,
			},
		)
		row["qty"] += flt(item.qty)
		row["amount"] += flt(item.base_net_amount)

	created = _created_assets(list(invoices))

	data = []
	for key, row in rows.items():
		made = created.get(key) or {}
		row["created_qty"] = flt(made.get("qty"))
		row["outstanding_qty"] = flt(row["qty"]) - row["created_qty"]
		row["draft_assets"] = made.get("draft") or 0
		row["assets"] = ", ".join(made.get("names") or [])
		if row["outstanding_qty"] <= 0:
			row["status"] = STATUS_SUDAH
		elif row["created_qty"]:
			row["status"] = STATUS_SEBAGIAN
		else:
			row["status"] = STATUS_BELUM

		if filters.get("status") == "Outstanding" and row["status"] == STATUS_SUDAH:
			continue
		if filters.get("status") in (STATUS_BELUM, STATUS_SEBAGIAN, STATUS_SUDAH) \
			and row["status"] != filters.status:
			continue
		data.append(row)

	data.sort(key=lambda r: (r["posting_date"], r["purchase_invoice"]), reverse=True)
	return data


def _get_invoices(filters):
	cond = {"docstatus": 1, "is_return": 0}
	if filters.get("company"):
		cond["company"] = filters.company
	if filters.get("supplier"):
		cond["supplier"] = filters.supplier
	if filters.get("from_date") and filters.get("to_date"):
		cond["posting_date"] = ("between", [filters.from_date, filters.to_date])

	return {
		d.name: d
		for d in frappe.get_all(
			"Purchase Invoice", filters=cond,
			fields=["name", "posting_date", "supplier", "company"],
		)
	}


def _created_assets(invoice_names):
	"""Kartu Asset yang sudah ada per (invoice, item). Draft ikut dihitung sudah dibuat.

	Aset batal (docstatus 2) tidak dihitung -- baris PI-nya kembali outstanding.
	"""
	out = {}
	for asset in frappe.get_all(
		"Asset",
		filters={"purchase_invoice": ("in", invoice_names), "docstatus": ("<", 2)},
		fields=["name", "purchase_invoice", "item_code", "asset_quantity", "docstatus"],
		order_by="name",
	):
		bucket = out.setdefault(
			(asset.purchase_invoice, asset.item_code), {"qty": 0.0, "draft": 0, "names": []}
		)
		bucket["qty"] += flt(asset.asset_quantity) or 1
		bucket["draft"] += 1 if asset.docstatus == 0 else 0
		bucket["names"].append(asset.name)
	return out


def get_columns():
	return [
		{"label": _("Purchase Invoice"), "fieldname": "purchase_invoice",
		 "fieldtype": "Link", "options": "Purchase Invoice", "width": 150},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link",
		 "options": "Supplier", "width": 170},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
		 "options": "Item", "width": 170},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 170},
		{"label": _("Asset Category"), "fieldname": "asset_category", "fieldtype": "Link",
		 "options": "Asset Category", "width": 120},
		{"label": _("Location"), "fieldname": "asset_location", "fieldtype": "Link",
		 "options": "Location", "width": 100},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 70},
		{"label": _("Created"), "fieldname": "created_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Outstanding"), "fieldname": "outstanding_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
		{"label": _("Draft"), "fieldname": "draft_assets", "fieldtype": "Int", "width": 70},
		{"label": _("Assets"), "fieldname": "assets", "fieldtype": "Data", "width": 220},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 150},
	]

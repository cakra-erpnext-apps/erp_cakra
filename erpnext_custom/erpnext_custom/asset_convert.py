"""Buat kartu Asset dari Purchase Invoice yang sudah submit, atas permintaan user.

CMI sengaja tidak memakai `auto_create_assets` (kartu dibuat manual supaya nama/nopol
tiap unit diisi sendiri). Tombol "Buat Asset" di form PI menggantikan otomatisasi itu:
memakai `BuyingController.make_asset` yang SAMA persis dengan jalur otomatis ERPNext,
cuma dipicu manual dan hanya untuk unit yang kartunya belum ada.

Sisa yang belum dibuat dihitung per (invoice, item_code), sama seperti laporan
Outstanding Asset -- aset yang dibuat manual biasanya cuma mengisi nomor invoice,
tidak sampai `purchase_invoice_item`.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_dimensions


def _created_qty(invoice, item_code):
	quantities = frappe.get_all(
		"Asset",
		filters={"purchase_invoice": invoice, "item_code": item_code, "docstatus": ("<", 2)},
		pluck="asset_quantity",
	)
	# asset_quantity kosong pada aset lama = 1 unit.
	return sum(flt(q) or 1 for q in quantities)


def _ensure_naming_series(item_code):
	"""Tanpa `asset_naming_series` di Item, ERPNext menamai aset "AST00001".

	Itu efek samping dari mematikan auto create asset, bukan pilihan penamaan.
	Jadi kalau kosong, isi sekali dengan seri bawaan doctype Asset (ACC-ASS-.YYYY.-).
	"""
	if frappe.get_cached_value("Item", item_code, "asset_naming_series"):
		return
	options = frappe.get_meta("Asset").get_field("naming_series").options or ""
	series = options.splitlines()[0].strip() if options else ""
	if not series:
		return
	frappe.db.set_value("Item", item_code, "asset_naming_series", series)
	frappe.clear_document_cache("Item", item_code)


@frappe.whitelist()
def get_outstanding(purchase_invoice):
	"""Baris aset di PI yang kartunya belum lengkap: [{item_code, qty, created, outstanding}]."""
	pi = frappe.get_doc("Purchase Invoice", purchase_invoice)
	pi.check_permission("read")

	pending = {}
	for row in pi.items:
		if not row.is_fixed_asset:
			continue
		bucket = pending.setdefault(
			row.item_code,
			{"item_code": row.item_code, "item_name": row.item_name, "qty": 0.0,
			 "location": None, "asset_category": row.asset_category},
		)
		bucket["qty"] += flt(row.qty)
		bucket["location"] = bucket["location"] or row.asset_location

	out = []
	for bucket in pending.values():
		bucket["created"] = _created_qty(purchase_invoice, bucket["item_code"])
		bucket["outstanding"] = bucket["qty"] - bucket["created"]
		if bucket["outstanding"] > 0:
			out.append(bucket)
	return out


@frappe.whitelist()
def make_assets(purchase_invoice, location=None):
	"""Bikin kartu Asset (Draft) untuk sisa unit yang belum punya kartu."""
	frappe.has_permission("Asset", "create", throw=True)

	pi = frappe.get_doc("Purchase Invoice", purchase_invoice)
	pi.check_permission("read")
	if pi.docstatus != 1:
		frappe.throw(_("Purchase Invoice harus sudah disubmit dulu."))

	pending = {b["item_code"]: b for b in get_outstanding(purchase_invoice)}
	if not pending:
		frappe.throw(_("Semua baris aset di invoice ini sudah punya kartu Asset."))

	dimensions = get_dimensions(with_cost_center_and_project=True)
	created = []
	for row in pi.items:
		bucket = pending.get(row.item_code) if row.is_fixed_asset else None
		if not bucket or bucket["outstanding"] <= 0:
			continue

		# Diubah di dokumen yang ada di MEMORI saja: PI sudah submit, tidak ikut disimpan.
		if location:
			row.asset_location = location

		_ensure_naming_series(row.item_code)
		qty = cint(bucket["outstanding"])
		if frappe.get_cached_value("Item", row.item_code, "is_grouped_asset"):
			row.qty = qty  # make_asset memakai row.qty sebagai asset_quantity untuk grouped
			created.append(pi.make_asset(row, dimensions, is_grouped_asset=True))
		else:
			for _unit in range(qty):
				created.append(pi.make_asset(row, dimensions))
		bucket["outstanding"] = 0

	return created

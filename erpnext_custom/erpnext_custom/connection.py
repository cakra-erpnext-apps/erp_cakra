"""Tab 'Connection' di Sales Invoice — penghubung PL/SL -> BL -> Container.

Alur: pilih Packing List / Shipping List  ->  muncul nomor BL  ->  pilih BL
-> container yang berhubungan otomatis termuat (bisa di-add/remove).

erp_cmi tetap steril: method ini hidup di erpnext_custom dan hanya MEMBACA
doctype expedition lewat nama (string), tanpa meng-import erp_cmi.
"""

import frappe
from frappe import _

_SOURCES = ("Packing List", "Shipping List")


@frappe.whitelist()
def sales_invoice_js():
	"""Kembalikan isi public/js/sales_invoice.js sebagai teks, untuk di-eval() Client Script.

	File /assets/erpnext_custom TIDAK tersaji di deployment ini (symlink rusak di nginx
	frontend — tanpa apps dir / bench build), jadi doctype_js tak pernah ke-load. Sebuah
	Client Script (disimpan di DB, disajikan backend) mengambil ini lalu meng-eval-nya.
	"""
	try:
		path = frappe.get_app_path("erpnext_custom", "public", "js", "sales_invoice.js")
		with open(path, encoding="utf-8") as f:
			return f.read()
	except Exception:
		return ""


def _check(source_doctype):
	if source_doctype not in _SOURCES:
		frappe.throw(_("Sumber tidak didukung: {0}").format(source_doctype))


@frappe.whitelist()
def get_bls(source_doctype, source_name):
	"""Daftar nomor BL dari sebuah Packing List / Shipping List.

	Packing List = 1 BL (header bl_no). Shipping List = banyak BL (child `bls`).
	"""
	_check(source_doctype)
	if not source_name:
		return []

	if source_doctype == "Packing List":
		bl = frappe.db.get_value("Packing List", source_name, "bl_no")
		return [{"bl_no": bl}] if bl else []

	rows = frappe.get_all(
		"Shipping List BL",
		filters={"parent": source_name, "parenttype": "Shipping List"},
		fields=["bl_no"],
		order_by="idx",
	)
	return [{"bl_no": r.bl_no} for r in rows if r.bl_no]


@frappe.whitelist()
def get_containers(source_doctype, source_name, bl_no=None):
	"""Container milik sebuah BL pada Packing List / Shipping List.

	Tiap baris dipetakan ke skema 'Invoice Container'.
	"""
	_check(source_doctype)
	if not source_name:
		return []

	if source_doctype == "Packing List":
		# Semua item Packing List berada di bawah satu BL header.
		header_bl = frappe.db.get_value("Packing List", source_name, "bl_no")
		items = frappe.get_all(
			"Packing List Item",
			filters={"parent": source_name, "parenttype": "Packing List"},
			fields=["container_no", "seal_no", "container_size", "goods_description", "customer"],
			order_by="idx",
		)
		return [
			{
				"source_doctype": "Packing List",
				"source_name": source_name,
				"bl_no": header_bl,
				"container_no": it.container_no,
				"seal_no": it.seal_no,
				"container_size": it.container_size,
				"goods_description": it.goods_description,
				"customer": it.customer,
			}
			for it in items
		]

	filters = {"parent": source_name, "parenttype": "Shipping List"}
	if bl_no:
		filters["bl"] = bl_no
	conts = frappe.get_all(
		"Shipping List Container",
		filters=filters,
		fields=["bl", "container_no", "seal_no", "container_size", "goods_description", "customer"],
		order_by="idx",
	)
	return [
		{
			"source_doctype": "Shipping List",
			"source_name": source_name,
			"bl_no": c.bl,
			"container_no": c.container_no,
			"seal_no": c.seal_no,
			"container_size": c.container_size,
			"goods_description": c.goods_description,
			"customer": c.customer,
		}
		for c in conts
	]


def _invoiced_containers(source_name, current_invoice=None):
	"""Map container_no -> nama Sales Invoice (tidak cancelled) yang sudah memuat container itu.

	Sumber kebenaran "sudah di-invoice" = tabel custom_containers (Invoice Container)
	pada Sales Invoice lain yang docstatus != 2 (bukan cancelled), selain invoice ini.
	"""
	out = {}
	rows = frappe.get_all(
		"Invoice Container",
		filters={"source_name": source_name, "parenttype": "Sales Invoice"},
		fields=["container_no", "parent"],
	)
	if not rows:
		return out
	parents = list({r.parent for r in rows})
	status = {
		s.name: s.docstatus
		for s in frappe.get_all("Sales Invoice", filters={"name": ["in", parents]}, fields=["name", "docstatus"])
	}
	for r in rows:
		if not r.container_no:
			continue
		if current_invoice and r.parent == current_invoice:
			continue
		if status.get(r.parent) == 2:  # cancelled
			continue
		out.setdefault(r.container_no, r.parent)
	return out


def _bl_dates(source_doctype, source_name):
	"""Map bl_no -> bl_date untuk sumber ini."""
	dates = {}
	if source_doctype == "Shipping List":
		for b in frappe.get_all(
			"Shipping List BL", filters={"parent": source_name, "parenttype": "Shipping List"},
			fields=["bl_no", "bl_date"],
		):
			dates[b.bl_no] = b.bl_date
	else:
		pl = frappe.get_doc("Packing List", source_name)
		bl = pl.get("bl_no")
		if bl:
			dates[bl] = pl.get("bl_date") or pl.get("date") or pl.get("etd")
	return dates


def _cargo_map(source_doctype, source_name):
	"""Map container_no -> cargo (khusus Shipping List Container yang punya field cargo)."""
	cm = {}
	if source_doctype == "Shipping List":
		for c in frappe.get_all(
			"Shipping List Container", filters={"parent": source_name, "parenttype": "Shipping List"},
			fields=["container_no", "cargo"],
		):
			cm[c.container_no] = c.cargo
	return cm


@frappe.whitelist()
def get_pickable_containers(source_doctype, source_name, current_invoice=None, include_invoiced=0):
	"""Container untuk MODAL pemilihan di Sales Invoice (Invoice Type non-Trading).

	Tiap baris diperkaya dengan ``bl_date``, ``cargo``, dan flag ``invoiced``
	(plus ``invoiced_in`` = nomor invoice pemakainya). Default hanya yang BELUM
	di-invoice; kalau ``include_invoiced`` truthy, yang sudah di-invoice ikut tampil.
	"""
	_check(source_doctype)
	if not source_name:
		return []
	include_invoiced = int(include_invoiced or 0)
	base = get_containers(source_doctype, source_name)  # semua BL
	invoiced = _invoiced_containers(source_name, current_invoice)
	bl_dates = _bl_dates(source_doctype, source_name)
	cargo = _cargo_map(source_doctype, source_name)

	out = []
	for r in base:
		cno = r.get("container_no")
		inv_in = invoiced.get(cno)
		if inv_in and not include_invoiced:
			continue
		row = dict(r)
		row["bl_date"] = str(bl_dates.get(r.get("bl_no")) or "")
		row["cargo"] = cargo.get(cno) or r.get("goods_description") or ""
		row["invoiced"] = 1 if inv_in else 0
		row["invoiced_in"] = inv_in or ""
		out.append(row)
	return out

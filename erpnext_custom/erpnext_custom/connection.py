"""Tab 'Connection' di Sales Invoice — penghubung PL/SL -> BL -> Container.

Alur: pilih Packing List / Shipping List  ->  muncul nomor BL  ->  pilih BL
-> container yang berhubungan otomatis termuat (bisa di-add/remove).

erp tetap steril: method ini hidup di erpnext_custom dan hanya MEMBACA
doctype expedition lewat nama (string), tanpa meng-import erp.
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
def get_containers(source_doctype, source_name, bl_no=None, current_invoice=None, include_invoiced=1):
	"""Container milik sebuah BL pada Packing List / Shipping List.

	Tiap baris dipetakan ke skema 'Invoice Container'. Kalau ``include_invoiced`` falsy
	(default checkbox "Re-Use Containers" mati), container yang SUDAH dimuat di Sales
	Invoice lain (non-cancelled) DIBUANG — jadi tiap invoice hanya menarik container yang
	belum di-invoice. ``include_invoiced=1`` (checkbox dicentang) memunculkan semua.
	NB: default 1 agar pemanggil lama (get_pickable_containers) tetap dapat daftar penuh.
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
		base = [
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
	else:
		filters = {"parent": source_name, "parenttype": "Shipping List"}
		if bl_no:
			filters["bl"] = bl_no
		conts = frappe.get_all(
			"Shipping List Container",
			filters=filters,
			fields=["bl", "container_no", "seal_no", "container_size", "goods_description", "customer"],
			order_by="idx",
		)
		base = [
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

	if not int(include_invoiced or 0):
		invoiced = _invoiced_containers(source_name, current_invoice)
		base = [r for r in base if r.get("container_no") not in invoiced]
	return base


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


def _invoiced_source_names(source_doctype):
	"""Set nama Master Job (Packing List / Shipping List) yang SUDAH punya Sales Invoice
	(non-cancelled). Dipakai untuk menyembunyikan Master Job yang sudah di-invoice dari
	picker source document, kecuali checkbox 'Re Use Master Job' dicentang."""
	rows = frappe.get_all(
		"Invoice Container",
		filters={"parenttype": "Sales Invoice", "source_doctype": source_doctype},
		fields=["source_name", "parent"],
	)
	if not rows:
		return set()
	parents = list({r.parent for r in rows})
	cancelled = set(
		frappe.get_all("Sales Invoice", filters={"name": ["in", parents], "docstatus": 2}, pluck="name")
	)
	return {r.source_name for r in rows if r.source_name and r.parent not in cancelled}


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


# --- Filter source documents (Connection tab) by the invoice's Customer -------
# Aturan user: sebuah Shipping List "milik" customer kalau consignee (BL) ATAU
# customer (container) = customer itu. Packing List milik customer kalau salah satu
# item-nya bercustomer itu. Dipakai sebagai Link `query` agar picker source document
# hanya menawarkan dokumen untuk customer yang dipilih di invoice.


def _name_conditions(names, txt):
	conds = []
	if names is not None:
		conds.append(["name", "in", list(names)])
	if txt:
		conds.append(["name", "like", f"%{txt}%"])
	return conds or None


@frappe.whitelist()
def shipping_lists_for_customer(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: Shipping List yang consignee (BL) ATAU customer (container) = filters.customer."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	customer = filters.get("customer")
	reuse = int(filters.get("reuse") or 0)
	txt = (txt or "").strip()
	names = None
	# Re Use Master Job: abaikan filter customer supaya SEMUA Master Job (termasuk yang
	# sudah di-invoice / beda penamaan customer) bisa dipilih lagi.
	if customer and not reuse:
		names = set(frappe.get_all("Shipping List BL", {"consignee": customer, "parenttype": "Shipping List"}, pluck="parent"))
		names |= set(frappe.get_all("Shipping List Container", {"customer": customer, "parenttype": "Shipping List"}, pluck="parent"))
		if not names:
			return []
	# Default: sembunyikan Master Job yang sudah punya invoice. Re Use Master Job = tampilkan semua.
	invoiced = set() if reuse else _invoiced_source_names("Shipping List")
	if names is not None:
		names -= invoiced
		if not names:
			return []
	conds = []
	if names is not None:
		conds.append(["name", "in", list(names)])
	elif invoiced:
		conds.append(["name", "not in", list(invoiced)])
	if txt:
		conds.append(["name", "like", f"%{txt}%"])
	rows = frappe.get_all(
		"Shipping List",
		filters=conds or None,
		fields=["name"],
		limit_start=int(start or 0),
		limit_page_length=int(page_len or 20),
		order_by="modified desc",
	)
	return [[r.name, customer or ""] for r in rows]


@frappe.whitelist()
def packing_lists_for_customer(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: Packing List yang salah satu item-nya bercustomer = filters.customer."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	customer = filters.get("customer")
	reuse = int(filters.get("reuse") or 0)
	txt = (txt or "").strip()
	names = None
	# Re Use Master Job: abaikan filter customer (lihat shipping_lists_for_customer).
	if customer and not reuse:
		names = set(frappe.get_all("Packing List Item", {"customer": customer, "parenttype": "Packing List"}, pluck="parent"))
		if not names:
			return []
	invoiced = set() if reuse else _invoiced_source_names("Packing List")
	if names is not None:
		names -= invoiced
		if not names:
			return []
	conds = []
	if names is not None:
		conds.append(["name", "in", list(names)])
	elif invoiced:
		conds.append(["name", "not in", list(invoiced)])
	if txt:
		conds.append(["name", "like", f"%{txt}%"])
	rows = frappe.get_all(
		"Packing List",
		filters=conds or None,
		fields=["name"],
		limit_start=int(start or 0),
		limit_page_length=int(page_len or 20),
		order_by="modified desc",
	)
	return [[r.name, customer or ""] for r in rows]


@frappe.whitelist()
def bl_invoices(shipping_list):
    """Map bl_no -> daftar nomor Sales Invoice (non-cancelled) yang menarik container
    dari BL itu. Untuk kolom 'Invoice' di tabel Bills of Lading (Shipping List).
    1 BL bisa muncul di beberapa invoice."""
    if not shipping_list:
        return {}
    rows = frappe.get_all(
        "Invoice Container",
        filters={"source_name": shipping_list, "source_doctype": "Shipping List", "parenttype": "Sales Invoice"},
        fields=["bl_no", "parent"],
    )
    if not rows:
        return {}
    parents = list({r.parent for r in rows})
    cancelled = {
        s.name
        for s in frappe.get_all("Sales Invoice", filters={"name": ["in", parents]}, fields=["name", "docstatus"])
        if s.docstatus == 2
    }
    out = {}
    for r in rows:
        if not r.bl_no or r.parent in cancelled:
            continue
        lst = out.setdefault(r.bl_no, [])
        if r.parent not in lst:
            lst.append(r.parent)
    return out

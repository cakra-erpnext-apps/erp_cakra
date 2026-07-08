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


def _invoiced_container_map(source_doctype, target_dt="Sales Invoice"):
	"""Map source_name -> set(container_no) yang SUDAH terpakai di dokumen target
	(Sales Invoice / lain) non-cancelled. Dipakai hitung 'any/fully invoiced'."""
	rows = frappe.get_all(
		"Invoice Container",
		filters={"parenttype": target_dt, "source_doctype": source_doctype},
		fields=["source_name", "container_no", "parent"],
	)
	if not rows:
		return {}
	parents = list({r.parent for r in rows})
	cancelled = set(frappe.get_all(target_dt, filters={"name": ["in", parents], "docstatus": 2}, pluck="name"))
	out = {}
	for r in rows:
		if r.source_name and r.container_no and r.parent not in cancelled:
			out.setdefault(r.source_name, set()).add(r.container_no)
	return out


def _all_container_map(source_doctype):
	"""Map source_name -> set(semua container_no) di dokumen sumber itu."""
	out = {}
	if source_doctype == "Shipping List":
		rows = frappe.get_all("Shipping List Container", filters={"parenttype": "Shipping List"}, fields=["parent", "container_no"])
	else:
		rows = frappe.get_all("Packing List Item", filters={"parenttype": "Packing List"}, fields=["parent", "container_no"])
	for r in rows:
		if r.container_no:
			out.setdefault(r.parent, set()).add(r.container_no)
	return out


def _invoiced_source_names(source_doctype):
	"""Set Master Job yang punya >=1 container terpakai di Sales Invoice (non-cancelled)."""
	return set(_invoiced_container_map(source_doctype).keys())


def _fully_invoiced_source_names(source_doctype):
	"""Set Master Job yang SEMUA container-nya sudah terpakai di Sales Invoice (non-cancelled)."""
	used = _invoiced_container_map(source_doctype)
	allc = _all_container_map(source_doctype)
	fully = set()
	for name, conts in allc.items():
		if conts and conts <= used.get(name, set()):
			fully.add(name)
	return fully


def _principle_source_names(source_doctype):
	"""Shipping List ber-Principle (principle_name terisi). Packing List: tidak ada (kosong)."""
	if source_doctype != "Shipping List":
		return set()
	return set(frappe.get_all("Shipping List", filters={"principle_name": ["is", "set"]}, pluck="name"))


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
	"""Link query Shipping List untuk Sales Invoice. Aturan:

	- Milik customer: consignee (BL) ATAU customer (container) = filters.customer.
	- Principle (principle_name terisi): HANYA muncul kalau Invoice Type No = C/EA;
	  di tipe lain disembunyikan.
	- Reuse OFF (default): sembunyikan SL yang SEMUA container-nya sudah di-invoice
	  (fully invoiced). SL yang baru sebagian di-invoice tetap muncul.
	- Reuse ON ("Re Use Master Job"): tampilkan HANYA SL yang sudah pernah di-invoice
	  (punya >=1 container terpakai) — untuk menarik ulang container.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	customer = filters.get("customer")
	reuse = int(filters.get("reuse") or 0)
	type_no = (filters.get("type_no") or "").strip()
	txt = (txt or "").strip()

	# Kandidat by customer (kalau ada & bukan reuse).
	names = None
	if customer and not reuse:
		names = set(frappe.get_all("Shipping List BL", {"consignee": customer, "parenttype": "Shipping List"}, pluck="parent"))
		names |= set(frappe.get_all("Shipping List Container", {"customer": customer, "parenttype": "Shipping List"}, pluck="parent"))
		if not names:
			return []

	fully = _fully_invoiced_source_names("Shipping List")
	principle = _principle_source_names("Shipping List") if type_no != "C/EA" else set()

	if reuse:
		# Hanya SL yang sudah pernah di-invoice.
		allow = _invoiced_source_names("Shipping List")
		names = (names & allow) if names is not None else set(allow)
	else:
		# Sembunyikan yang sudah FULLY invoiced.
		if names is not None:
			names -= fully

	# Principle hanya untuk C/EA.
	if principle and names is not None:
		names -= principle

	if names is not None and not names:
		return []

	conds = []
	if names is not None:
		conds.append(["name", "in", list(names)])
	else:
		if fully:
			conds.append(["name", "not in", list(fully)])
		if principle:
			conds.append(["name", "not in", list(principle)])
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
def make_invoice_from_bl(source_doctype, source_name, bl_no):
	"""Buat Sales Invoice DRAFT (belum disimpan) dari sebuah BL pada Packing/Shipping List.

	Yang dibawa otomatis:
	  - Customer   : consignee BL (Shipping List) / customer item (Packing List).
	  - Alamat     : default address customer -> custom_customer_address + display.
	  - Connection : custom_shipping_list / custom_packing_list, custom_bl_no,
	                 dan semua container BL itu ke custom_containers (Invoice Container).
	  - Invoice Type: Expedition / C/E (default).
	Kembalikan doc.as_dict() untuk di-`frappe.model.sync` + route di client (form baru).
	erp tetap steril: hanya membaca doctype expedition lewat nama.
	"""
	_check(source_doctype)
	if not source_name or not bl_no:
		frappe.throw(_("Sumber / BL belum lengkap."))

	conts = get_containers(source_doctype, source_name, bl_no=bl_no, include_invoiced=1)

	# Customer: consignee BL (SL) dulu, fallback ke customer container pertama.
	customer = None
	if source_doctype == "Shipping List":
		customer = frappe.db.get_value(
			"Shipping List BL", {"parent": source_name, "bl_no": bl_no, "parenttype": "Shipping List"}, "consignee"
		)
	if not customer:
		for c in conts:
			if c.get("customer"):
				customer = c["customer"]
				break

	inv = frappe.new_doc("Sales Invoice")
	# Tanggal invoice = hari ini (invoice_date -> posting_date via before_validate).
	inv.invoice_date = frappe.utils.today()
	inv.set_posting_time = 1
	inv.posting_date = inv.invoice_date
	if customer:
		inv.customer = customer
	if source_doctype == "Shipping List":
		inv.custom_shipping_list = source_name
	else:
		inv.custom_packing_list = source_name
	inv.custom_bl_no = bl_no
	if inv.meta.has_field("custom_invoice_type"):
		inv.custom_invoice_type = "Expedition"
	if inv.meta.has_field("custom_invoice_type_no"):
		inv.custom_invoice_type_no = "C/E"

	for c in conts:
		inv.append("custom_containers", {
			"source_doctype": c.get("source_doctype"),
			"source_name": c.get("source_name"),
			"bl_no": c.get("bl_no"),
			"container_no": c.get("container_no"),
			"seal_no": c.get("seal_no"),
			"container_size": c.get("container_size"),
			"goods_description": c.get("goods_description"),
			"customer": c.get("customer"),
		})

	# Alamat customer (default) -> field custom + display, biar langsung tampil di form baru.
	if customer:
		try:
			from frappe.contacts.doctype.address.address import get_default_address, get_address_display

			addr = get_default_address("Customer", customer)
			if addr:
				inv.custom_customer_address = addr
				inv.customer_address = addr
				disp = get_address_display(frappe.get_doc("Address", addr).as_dict())
				inv.address_display = disp
				if inv.meta.has_field("custom_address_display"):
					inv.custom_address_display = disp
		except Exception:
			frappe.log_error(frappe.get_traceback(), "make_invoice_from_bl address")

	return inv.as_dict()


@frappe.whitelist()
def make_expense_from_bl(source_doctype, source_name, bl_no):
	"""Buat Expense Note DRAFT (belum disimpan) dari sebuah BL pada Packing/Shipping List.

	- Supplier (vendor) sengaja DIKOSONGKAN — diisi user.
	- Tanggal (date) = hari ini.
	- Connection: shipping_list / packing_list + bl_no, dan container BL itu ke bl_containers.
	- Cost Center ikut dari dokumen sumber (kalau ada), company = default.
	Kembalikan doc.as_dict() untuk di-`frappe.model.sync` + route di client (form baru).
	"""
	_check(source_doctype)
	if not source_name or not bl_no:
		frappe.throw(_("Sumber / BL belum lengkap."))

	conts = get_containers(source_doctype, source_name, bl_no=bl_no, include_invoiced=1)

	en = frappe.new_doc("Expense Note")
	en.date = frappe.utils.today()          # tanggal expense = hari ini
	# vendor sengaja dibiarkan kosong (diisi user)
	en.company = frappe.defaults.get_global_default("company")
	cc = frappe.db.get_value(source_doctype, source_name, "cost_center")
	if cc:
		en.cost_center = cc
	if source_doctype == "Shipping List":
		en.shipping_list = source_name
		en.bl_no = bl_no
	else:
		en.packing_list = source_name

	for c in conts:
		en.append("bl_containers", {
			"container_no": c.get("container_no"),
			"seal_no": c.get("seal_no"),
			"container_size": c.get("container_size"),
			"customer": c.get("customer"),
		})

	return en.as_dict()


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

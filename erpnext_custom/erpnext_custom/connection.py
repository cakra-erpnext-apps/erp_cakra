"""Tab 'Connection' di Sales Invoice — penghubung PL/SL -> BL -> Container.

Alur: pilih Packing List / Shipping List  ->  muncul nomor BL  ->  pilih BL
-> container yang berhubungan otomatis termuat (bisa di-add/remove).

erp tetap steril: method ini hidup di erpnext_custom dan hanya MEMBACA
doctype expedition lewat nama (string), tanpa meng-import erp.
"""

import frappe
from frappe import _

_SOURCES = ("Packing List", "Shipping List")


def boot(bootinfo):
	"""Flag tampil field Shipping/Packing List di tab Connection (depends_on, dievaluasi di
	client). Default sama dgn erp.expedition.menu_visibility: Packing List nyala, Shipping List tidak."""
	es = frappe.db.get_singles_dict("ERPNext Custom Setting")
	flag = lambda k, d: frappe.utils.cint(es[k]) if es.get(k) is not None else d  # noqa: E731
	bootinfo.cmi_conn_flags = {
		"shipping_list": flag("show_shipping_list", 0),
		"packing_list": flag("show_packing_list", 1),
	}


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


def _as_bl_list(bl_no):
	"""Normalkan argumen BL jadi list bersih tanpa duplikat, urutan dipertahankan.

	Menerima: list Python, string JSON list (dari client), atau string tunggal
	(pemanggil lama / dipisah koma). Dipakai supaya satu invoice bisa mencakup
	beberapa BL tanpa memecah pemanggil yang sudah ada.
	"""
	if isinstance(bl_no, str):
		s = bl_no.strip()
		if s.startswith("["):
			try:
				bl_no = frappe.parse_json(s)
			except Exception:
				bl_no = [s]
		else:
			bl_no = s.split(",")
	if not isinstance(bl_no, (list, tuple)):
		bl_no = [bl_no]
	out = []
	for b in bl_no:
		b = (b or "").strip() if isinstance(b, str) else b
		if b and b not in out:
			out.append(b)
	return out


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
		return [{"bl_no": bl, "consignee": None}] if bl else []

	# consignee ikut dikembalikan: satu invoice boleh memuat beberapa BL, TAPI semuanya
	# harus milik customer yang sama. Client memakainya untuk menandai & mencegah campur
	# sejak di modal; server tetap yang menegakkan (lihat _sync_bls).
	rows = frappe.get_all(
		"Shipping List BL",
		filters={"parent": source_name, "parenttype": "Shipping List"},
		fields=["bl_no", "consignee"],
		order_by="idx",
	)
	return [{"bl_no": r.bl_no, "consignee": r.consignee} for r in rows if r.bl_no]


@frappe.whitelist()
def get_containers(source_doctype, source_name, bl_no=None, current_invoice=None, include_invoiced=1, behavior=None):
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
			fields=["container_no", "seal_no", "container_size", "customer"],
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
		invoiced = _invoiced_containers(source_name, current_invoice, behavior)
		base = [r for r in base if r.get("container_no") not in invoiced]
	return base


def _invoiced_containers(source_name, current_invoice=None, behavior=None):
	"""Map container_no -> nama Sales Invoice EXPEDITION (non-Reimburse, tidak cancelled)
	yang sudah memuat container itu, selain invoice ini.

	Invoice Reimburse (IR) tidak menghitung container sama sekali: tagihannya mengikuti
	Expense Note yang belum ditagih (lihat _reimburse_sources), jadi untuk IR hasilnya
	selalu kosong. Container yang dipakai IR juga tidak menghalangi invoice Expedition.
	"""
	out = {}
	if behavior == "Reimburse":
		return out
	rows = frappe.get_all(
		"Invoice Container",
		filters={"source_name": source_name, "parenttype": "Sales Invoice"},
		fields=["container_no", "parent"],
	)
	live = _expedition_invoices({r.parent for r in rows})
	for r in rows:
		if not r.container_no or r.parent not in live:
			continue
		if current_invoice and r.parent == current_invoice:
			continue
		out.setdefault(r.container_no, r.parent)
	return out


def _expedition_invoices(names):
	"""Subset `names` yang Sales Invoice non-cancelled dan BUKAN Reimburse.

	IR dan invoice Expedition dihitung terpisah walau satu Master Job: container yang
	sudah ditagih lewat IR tetap boleh ditagih lewat C/E, dan sebaliknya."""
	if not names:
		return set()
	rows = frappe.get_all(
		"Sales Invoice", filters={"name": ["in", list(names)], "docstatus": ["!=", 2]},
		fields=["name", "custom_invoice_behavior"],
	)
	return {r.name for r in rows if r.custom_invoice_behavior != "Reimburse"}


def _invoiced_container_map(source_doctype, target_dt="Sales Invoice"):
	"""Map source_name -> set(container_no) yang SUDAH terpakai di Sales Invoice
	Expedition (non-Reimburse, non-cancelled). Dipakai hitung 'any/fully invoiced'."""
	rows = frappe.get_all(
		"Invoice Container",
		filters={"parenttype": target_dt, "source_doctype": source_doctype},
		fields=["source_name", "container_no", "parent"],
	)
	live = _expedition_invoices({r.parent for r in rows})
	out = {}
	for r in rows:
		if r.source_name and r.container_no and r.parent in live:
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
	"""Set Master Job yang punya >=1 container terpakai di Sales Invoice Expedition."""
	return set(_invoiced_container_map(source_doctype).keys())


def _fully_invoiced_source_names(source_doctype):
	"""Set Master Job yang SEMUA container-nya sudah terpakai di Sales Invoice Expedition."""
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
def get_pickable_containers(source_doctype, source_name, current_invoice=None, include_invoiced=0, behavior=None):
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
	invoiced = _invoiced_containers(source_name, current_invoice, behavior)
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


def used_reimburse_keys(current_invoice=None):
	"""{(Expense Note, item, expense_class)} yang sudah ditagih di Sales Invoice Reimburse.

	Hanya Sales Invoice yang tidak cancelled: baris milik Proforma (tabel anaknya dipakai
	bersama) dan invoice yang dibatalkan tidak mengunci Expense Note. Baris milik
	`current_invoice` diabaikan supaya invoice ini tidak mengunci dirinya sendiri."""
	rows = frappe.get_all(
		"Sales Invoice Reimburse", filters={"parenttype": "Sales Invoice"},
		fields=["parent", "expense_note", "item", "expense_class"],
	)
	parents = {r.parent for r in rows if r.parent != current_invoice}
	live = set(frappe.get_all(
		"Sales Invoice", filters={"name": ["in", list(parents)], "docstatus": ["!=", 2]}, pluck="name"
	)) if parents else set()
	return {(r.expense_note, r.item, r.expense_class) for r in rows if r.parent in live}


def _reimburse_sources(source_field, customer, reuse, current_invoice=None):
	"""Master Job (Packing/Shipping List) untuk invoice Reimburse: yang masih punya
	Expense Note reimburse ke customer ini yang BELUM ditagih. Semua EN-nya sudah ditagih
	-> tidak muncul; tambah EN baru di Master Job itu -> muncul lagi.
	Re Use Master Job: semua Master Job yang punya EN reimburse customer ini."""
	cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
	ens = frappe.get_all(
		"Expense Note",
		filters={"is_reimburse": 1, "void": ["!=", 1], source_field: ["is", "set"],
		         "reimburse_to_customer": ["in", list({customer, cust_name})]},
		fields=["name", source_field],
	)
	if reuse or not ens:
		return {e[source_field] for e in ens}
	used = used_reimburse_keys(current_invoice)
	open_ens = {
		r.parent
		for r in frappe.get_all(
			"Expense Note Item", filters={"parent": ["in", [e.name for e in ens]]},
			fields=["parent", "item", "expense_class"],
		)
		if (r.parent, r.item, r.expense_class) not in used
	}
	return {e[source_field] for e in ens if e.name in open_ens}


def _open_conds(doctype):
	"""Hanya Master Job yang masih Open: Void/Closed tidak ditawarkan di picker invoice.
	Dicek per field supaya doctype yang belum punya Void/Closed (Shipping List) tidak error."""
	meta = frappe.get_meta(doctype)
	return [[f, "=", 0] for f in ("void", "closed") if meta.has_field(f)]


def _name_rows(doctype, names, txt, start, page_len, customer):
	if not names:
		return []
	conds = [["name", "in", list(names)]] + _open_conds(doctype)
	if txt:
		conds.append(["name", "like", f"%{txt}%"])
	rows = frappe.get_all(
		doctype, filters=conds, fields=["name"], order_by="modified desc",
		limit_start=int(start or 0), limit_page_length=int(page_len or 20),
	)
	return [[r.name, customer or ""] for r in rows]


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
	if not customer:
		return []  # customer wajib dipilih dulu (form memberi peringatan)
	if filters.get("behavior") == "Reimburse":
		names = _reimburse_sources("shipping_list", customer, reuse, filters.get("current_invoice"))
		return _name_rows("Shipping List", names, txt, start, page_len, customer)

	# SL yang Principle-nya = customer invoice ini ikut jadi "milik" customer:
	# penagihan ke principle terpisah dari penagihan container ke consignee.
	# Sekali tarik per SL: yang SUDAH dirujuk invoice customer ini (custom_shipping_list,
	# non-cancelled) tidak ditawarkan lagi — kecuali Re Use Master Job dicentang.
	by_principle = set()
	used_principle = set()
	if customer:
		by_principle = set(frappe.get_all("Shipping List", {"principle_name": customer}, pluck="name"))
		if by_principle:
			# Semua SL invoice (tabel multi-pilih), bukan cuma SL utamanya.
			used_principle = set(frappe.db.sql_list(
				"""select distinct r.shipping_list from `tabInvoice Shipping List Ref` r
				   join `tabSales Invoice` si on si.name = r.parent
				   where r.parenttype = 'Sales Invoice' and r.parentfield = 'custom_shipping_lists'
				     and si.customer = %(c)s and si.docstatus != 2
				     and ifnull(si.custom_invoice_behavior, '') != 'Reimburse'
				     and r.shipping_list in %(sl)s""",
				{"c": customer, "sl": list(by_principle)},
			))  # IR dihitung terpisah

	# Kandidat by customer (kalau ada & bukan reuse).
	names = None
	if customer and not reuse:
		names = set(frappe.get_all("Shipping List BL", {"consignee": customer, "parenttype": "Shipping List"}, pluck="parent"))
		names |= set(frappe.get_all("Shipping List Container", {"customer": customer, "parenttype": "Shipping List"}, pluck="parent"))

	fully = _fully_invoiced_source_names("Shipping List")
	principle = _principle_source_names("Shipping List") if type_no != "C/EA" else set()
	# Gate C/EA tidak berlaku untuk SL yang principle-nya customer ini sendiri.
	principle -= by_principle

	if reuse:
		# Hanya SL yang sudah pernah di-invoice; tarikan principle sebelumnya ikut
		# ditawarkan lagi ("bisa pilih berkali-kali" saat Re Use).
		allow = _invoiced_source_names("Shipping List") | used_principle
		names = (names & allow) if names is not None else set(allow)
	else:
		if names is not None:
			# Sembunyikan yang sudah FULLY invoiced, lalu tambahkan SL principle yang
			# belum pernah ditarik customer ini — SL principle tetap muncul walau
			# container-nya sudah habis di-invoice ke consignee (tagihannya terpisah).
			names -= fully
			names |= (by_principle - used_principle)
			if not names:
				return []

	# Principle (milik customer lain) hanya untuk C/EA.
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
	conds += _open_conds("Shipping List")
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
	"""Link query: Packing List yang salah satu item-nya bercustomer = filters.customer,
	masih Open, dan masih punya container yang belum ditagih (kecuali Re Use Master Job)."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	customer = filters.get("customer")
	reuse = int(filters.get("reuse") or 0)
	txt = (txt or "").strip()
	if not customer:
		return []  # customer wajib dipilih dulu (form memberi peringatan)
	if filters.get("behavior") == "Reimburse":
		names = _reimburse_sources("packing_list", customer, reuse, filters.get("current_invoice"))
		return _name_rows("Packing List", names, txt, start, page_len, customer)
	names = None
	# Re Use Master Job: abaikan filter customer (lihat shipping_lists_for_customer).
	if customer and not reuse:
		names = set(frappe.get_all("Packing List Item", {"customer": customer, "parenttype": "Packing List"}, pluck="parent"))
		if not names:
			return []
	# Sekali pakai per container: PL hilang hanya kalau SEMUA container-nya sudah ditagih
	# invoice Expedition (sama dgn Shipping List); yang baru sebagian tetap muncul supaya
	# sisanya bisa ditagih. Re Use Master Job -> semua muncul lagi.
	invoiced = set() if reuse else _fully_invoiced_source_names("Packing List")
	if names is not None:
		names -= invoiced
		if not names:
			return []
	conds = []
	if names is not None:
		conds.append(["name", "in", list(names)])
	elif invoiced:
		conds.append(["name", "not in", list(invoiced)])
	conds += _open_conds("Packing List")
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


# ---- Trading: Sales Order / Delivery Note -----------------------------------------------
# Qty yang sudah "terpakai" = baris Sales Invoice (draft + submitted, bukan cancelled, selain
# invoice ini) yang menautkan baris sumbernya (so_detail / dn_detail). Draft ikut dihitung
# supaya satu SO/DN tidak ditarik dua invoice sekaligus.
_BILLED_QTY = """ifnull((select sum(sii.qty) from `tabSales Invoice Item` sii
	join `tabSales Invoice` si on si.name = sii.parent
	where sii.{link} = {row}.name and si.docstatus < 2 and si.name != %(cur)s), 0)"""


def _trading_args(txt, start, page_len, filters):
	from erpnext_custom.invoice_types import allowed_item_groups

	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	# Item Category tipe invoice: SO/DN hanya muncul kalau punya baris belum ditagih dari
	# kategori itu ([] = tanpa batasan; "" di SQL supaya `in` tetap sah).
	return filters, {
		"groups": allowed_item_groups(filters.get("invoice_type")) or [""],
		"any_group": 0 if allowed_item_groups(filters.get("invoice_type")) else 1,
		"customer": filters.get("customer"),
		"currency": filters.get("currency"),
		"cur": filters.get("current_invoice") or "",
		"txt": f"%{(txt or '').strip()}%",
		"start": int(start or 0),
		"page_len": int(page_len or 20),
	}


@frappe.whitelist()
def sales_orders_for_invoice(doctype, txt, searchfield, start, page_len, filters):
	"""Sales Order submitted milik customer + currency invoice ini yang:
	- BELUM punya Delivery Note (draft pun dihitung) -- sudah ber-DN berarti ditagih lewat DN;
	- masih punya qty yang belum ditagih;
	- tidak Closed / On Hold / Completed."""
	filters, a = _trading_args(txt, start, page_len, filters)
	if not a["customer"] or not a["currency"]:
		return []  # customer & currency wajib (form memberi peringatan)
	return frappe.db.sql(
		f"""select so.name, so.transaction_date from `tabSales Order` so
		where so.docstatus = 1 and so.customer = %(customer)s and so.currency = %(currency)s
		  and so.status not in ('Closed', 'On Hold', 'Completed') and so.name like %(txt)s
		  and not exists (select 1 from `tabDelivery Note Item` dni
		      join `tabDelivery Note` dn on dn.name = dni.parent
		      where dni.against_sales_order = so.name and dn.docstatus < 2)
		  and exists (select 1 from `tabSales Order Item` soi where soi.parent = so.name
		      and (%(any_group)s or soi.item_group in %(groups)s)
		      and soi.qty > {_BILLED_QTY.format(link="so_detail", row="soi")})
		order by so.transaction_date desc, so.name desc
		limit %(start)s, %(page_len)s""",
		a,
	)


@frappe.whitelist()
def delivery_notes_for_invoice(doctype, txt, searchfield, start, page_len, filters):
	"""Delivery Note submitted (bukan retur) milik customer + currency invoice ini yang masih
	punya qty belum ditagih: begitu qty DN = qty di Sales Invoice, DN tidak muncul lagi."""
	filters, a = _trading_args(txt, start, page_len, filters)
	if not a["customer"] or not a["currency"]:
		return []
	return frappe.db.sql(
		f"""select dn.name, dn.posting_date from `tabDelivery Note` dn
		where dn.docstatus = 1 and ifnull(dn.is_return, 0) = 0
		  and dn.customer = %(customer)s and dn.currency = %(currency)s
		  and dn.status not in ('Closed', 'Cancelled') and dn.name like %(txt)s
		  and exists (select 1 from `tabDelivery Note Item` dni where dni.parent = dn.name
		      and (%(any_group)s or dni.item_group in %(groups)s)
		      and dni.qty > {_BILLED_QTY.format(link="dn_detail", row="dni")})
		order by dn.posting_date desc, dn.name desc
		limit %(start)s, %(page_len)s""",
		a,
	)


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

	# bl_no boleh string tunggal (pemanggil lama) ATAU list/JSON list (pilih banyak BL).
	bl_list = _as_bl_list(bl_no)
	if not bl_list:
		frappe.throw(_("Sumber / BL belum lengkap."))

	conts = []
	for b in bl_list:
		conts.extend(get_containers(source_doctype, source_name, bl_no=b, include_invoiced=1))

	# Customer: consignee BL (SL) dulu, fallback ke customer container pertama.
	# Banyak BL -> consignee-nya WAJIB sama; satu invoice hanya punya satu customer.
	customer = None
	if source_doctype == "Shipping List":
		consignees = []
		for b in bl_list:
			c = frappe.db.get_value(
				"Shipping List BL", {"parent": source_name, "bl_no": b, "parenttype": "Shipping List"}, "consignee"
			)
			if c and c not in consignees:
				consignees.append(c)
		if len(consignees) > 1:
			frappe.throw(_(
				"BL yang dipilih milik customer berbeda: <b>{0}</b>. Satu invoice hanya untuk satu customer, "
				"jadi pilih BL dengan consignee yang sama."
			).format(", ".join(consignees)))
		customer = consignees[0] if consignees else None
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
	inv.due_date = inv.invoice_date  # cegah "Payment Due Date wajib" saat field tak ter-hide
	if customer:
		inv.customer = customer
	if source_doctype == "Shipping List":
		inv.custom_shipping_list = source_name
		inv.append("custom_shipping_lists", {"shipping_list": source_name})
	else:
		inv.custom_packing_list = source_name
		inv.append("custom_packing_lists", {"packing_list": source_name})
	for b in bl_list:
		inv.append("custom_bls", {
			"source_doctype": source_doctype,
			"source_name": source_name,
			"bl_no": b,
		})
	inv.custom_bl_no = ", ".join(bl_list)  # ringkasan; disegarkan lagi di before_validate
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

	# Alamat customer (default) -> field custom, biar langsung tampil di form baru.
	# Display sebagai TEKS newline (bukan HTML get_address_display yang pakai <br>,
	# supaya tidak muncul "<br>" literal di field teks).
	if customer:
		try:
			from frappe.contacts.doctype.address.address import get_default_address

			addr = get_default_address("Customer", customer)
			if addr:
				inv.custom_customer_address = addr
				inv.customer_address = addr
				a = frappe.db.get_value(
					"Address", addr,
					["address_line1", "address_line2", "city", "state", "pincode", "country"],
					as_dict=True,
				) or {}
				parts = [
					a.get("address_line1"), a.get("address_line2"),
					" ".join(x for x in [a.get("city"), a.get("pincode")] if x),
					a.get("state"), a.get("country"),
				]
				disp = "\n".join(p for p in parts if p)
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

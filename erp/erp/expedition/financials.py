import json

import frappe

# Ringkasan finansial batch untuk list view Shipping List / Packing List
# (baris "Inv / Exp / Margin" di bawah tiap row list).

# source doctype -> (field link di Expense Note, custom field di Sales Invoice)
_SOURCES = {
	"Shipping List": ("shipping_list", "custom_shipping_list"),
	"Packing List": ("packing_list", "custom_packing_list"),
}


def _company_currency():
	company = frappe.defaults.get_global_default("company")
	if company:
		cur = frappe.get_cached_value("Company", company, "default_currency")
		if cur:
			return cur
	return frappe.db.get_default("currency") or "IDR"


@frappe.whitelist()
def list_financials(source_doctype, names):
	"""Per dokumen sumber: daftar Sales Invoice (non-cancelled; draft ditandai),
	daftar Expense Note (non-void; reimburse ditandai, tidak dihitung), total
	revenue/expense (DPP, mata uang perusahaan) dan margin.

	Konsisten dengan tab Summary Shipping List: revenue hanya dari invoice
	Submitted; expense = total_amount * kurs; reimburse = pass-through.
	"""
	if source_doctype not in _SOURCES:
		frappe.throw(frappe._("Unsupported source doctype"))
	if not frappe.has_permission(source_doctype, "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	en_field, inv_field = _SOURCES[source_doctype]

	if isinstance(names, str):
		names = json.loads(names)
	names = [n for n in (names or []) if n][:500]
	if not names:
		return {}

	currency = _company_currency()
	out = {n: {"invoices": [], "expenses": [], "revenue": 0.0, "expense": 0.0} for n in names}

	# EN reimburse tetap ditampilkan (ditandai) tapi TIDAK dihitung ke expense/margin.
	ens = frappe.get_all(
		"Expense Note",
		filters={en_field: ["in", names], "void": ["!=", 1]},
		fields=["name", en_field, "total_amount", "conversion_rate", "is_reimburse"],
		order_by="date asc, name asc",
	)
	for e in ens:
		o = out.get(e.get(en_field))
		if o is None:
			continue
		o["expenses"].append({"name": e.name, "reimburse": bool(e.is_reimburse)})
		if not e.is_reimburse:
			o["expense"] += (e.total_amount or 0) * (e.conversion_rate or 1)

	# Invoice terhubung: union dari child Invoice Container (per container yang
	# ditarik) dan custom field koneksi di Sales Invoice (mis. invoice reimburse
	# yang tidak menarik container). erp tetap steril: dibaca via string saja.
	inv_sources = {}
	ic = frappe.get_all(
		"Invoice Container",
		filters={"source_doctype": source_doctype, "source_name": ["in", names], "parenttype": "Sales Invoice"},
		fields=["parent", "source_name"],
	)
	for r in ic:
		if r.parent:
			inv_sources.setdefault(r.parent, set()).add(r.source_name)
	if frappe.get_meta("Sales Invoice").has_field(inv_field):
		for r in frappe.get_all(
			"Sales Invoice",
			filters={inv_field: ["in", names], "docstatus": ["!=", 2]},
			fields=["name", inv_field],
		):
			inv_sources.setdefault(r.name, set()).add(r.get(inv_field))

	if inv_sources:
		invs = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list(inv_sources)], "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "base_total"],
			order_by="posting_date asc, name asc",
		)
		for iv in invs:
			for src in inv_sources.get(iv.name, ()):
				o = out.get(src)
				if o is None:
					continue
				o["invoices"].append({"name": iv.name, "draft": iv.docstatus == 0})
				# Draft (docstatus 0) & Submitted (1) sama-sama dihitung ke revenue — invoice
				# yang belum divalidasi tetap masuk margin. (Cancelled sudah difilter di query.)
				o["revenue"] += iv.base_total or 0

	for o in out.values():
		o["margin"] = o["revenue"] - o["expense"]
		o["margin_pct"] = round(o["margin"] / o["revenue"] * 100, 1) if o["revenue"] else None
		o["currency"] = currency
	return out


@frappe.whitelist()
def bl_financials(shipping_list):
	"""Per BL (bl_no) sebuah Shipping List: invoice, expense, margin — untuk kolom
	Invoice / Expense / Margin di tabel Bills of Lading.

	- Revenue per BL: base_total invoice Submitted. Bila 1 invoice mencakup
	  beberapa BL, di-prorata menurut jumlah container per BL di child Invoice
	  Container (item invoice memang dibuat 1 per container).
	- Expense per BL: hanya Expense Note yang BL No-nya diisi (EN tanpa BL No
	  dianggap level Shipping List, tidak diatribusikan ke BL). Reimburse
	  ditampilkan tapi tidak dihitung.
	"""
	if not shipping_list:
		return {}
	if not frappe.has_permission("Shipping List", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	out = {}

	def bucket(bl):
		return out.setdefault(bl, {"invoices": [], "expenses": [], "revenue": 0.0, "expense": 0.0})

	rows = frappe.get_all(
		"Invoice Container",
		filters={"source_name": shipping_list, "source_doctype": "Shipping List", "parenttype": "Sales Invoice"},
		fields=["bl_no", "parent"],
	)
	by_inv = {}
	for r in rows:
		if r.parent and r.bl_no:
			by_inv.setdefault(r.parent, []).append(r.bl_no)
	if by_inv:
		invs = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list(by_inv)], "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "base_total", "posting_date"],
			order_by="posting_date asc, name asc",
		)
		for iv in invs:
			bls = by_inv.get(iv.name, [])
			total_containers = len(bls) or 1
			counts = {}
			for b in bls:
				counts[b] = counts.get(b, 0) + 1
			for b, cnt in counts.items():
				d = bucket(b)
				# Net per BL untuk invoice ini = base_total diprorata jml container BL.
				net = (iv.base_total or 0) * cnt / total_containers
				d["invoices"].append({
					"name": iv.name, "draft": iv.docstatus == 0, "net": net,
					"date": str(iv.posting_date or ""),
				})
				# Draft & Submitted sama-sama dihitung ke revenue per BL (prorata container).
				d["revenue"] += net

	ens = frappe.get_all(
		"Expense Note",
		filters={"shipping_list": shipping_list, "void": ["!=", 1], "bl_no": ["is", "set"]},
		fields=["name", "bl_no", "total_amount", "conversion_rate", "is_reimburse", "date",
		        "vendor", "expense_classes"],
		order_by="date asc, name asc",
	)
	for e in ens:
		d = bucket(e.bl_no)
		en_net = (e.total_amount or 0) * (e.conversion_rate or 1)
		d["expenses"].append({
			"name": e.name, "reimburse": bool(e.is_reimburse),
			"net": 0 if e.is_reimburse else en_net,
			"date": str(e.date or ""),
			"vendor": e.vendor or "",
			"classes": e.expense_classes or "",
		})
		if not e.is_reimburse:
			d["expense"] += en_net

	for d in out.values():
		d["margin"] = d["revenue"] - d["expense"]
	return out


# ---- Indeks pencarian Inv/Exp -------------------------------------------------------
# Field tersembunyi `fin_index` di Shipping/Packing List berisi kumpulan nomor Sales
# Invoice + Expense Note terkait (dipisah spasi), supaya bisa dicari lewat "standard
# filter" list (kotak "Cari Inv/Exp", pencarian LIKE). Dijaga sinkron oleh hook:
#  - Sales Invoice: on_update/on_submit/on_cancel + on_trash/after_delete (didaftarkan
#    di erpnext_custom karena Sales Invoice doctype core).
#  - Expense Note : on_update/after_delete (didaftarkan di erp).


def _fin_index_names(source_doctype, source_name):
	"""Kumpulan nomor Sales Invoice (non-cancelled) + Expense Note (non-void) yang
	terhubung ke satu dokumen sumber. Sama jalur koneksinya dgn list_financials."""
	en_field, inv_field = _SOURCES[source_doctype]
	inv = set()
	for r in frappe.get_all(
		"Invoice Container",
		filters={"source_doctype": source_doctype, "source_name": source_name, "parenttype": "Sales Invoice"},
		fields=["parent"],
	):
		if r.parent:
			inv.add(r.parent)
	if frappe.get_meta("Sales Invoice").has_field(inv_field):
		inv.update(frappe.get_all(
			"Sales Invoice", filters={inv_field: source_name, "docstatus": ["!=", 2]}, pluck="name"
		))
	if inv:
		# buang yang cancelled / sudah tak ada (Invoice Container bisa menyisakan nama lama)
		inv = set(frappe.get_all(
			"Sales Invoice", filters={"name": ["in", list(inv)], "docstatus": ["!=", 2]}, pluck="name"
		))
	exp = set(frappe.get_all(
		"Expense Note", filters={en_field: source_name, "void": ["!=", 1]}, pluck="name"
	))
	return sorted(inv) + sorted(exp)


def rebuild_fin_index(source_doctype, source_name):
	"""Hitung ulang & simpan `fin_index` sebuah dokumen sumber (lightweight db_set,
	tidak memicu save/validate)."""
	if source_doctype not in _SOURCES or not source_name:
		return
	if not frappe.get_meta(source_doctype).has_field("fin_index"):
		return
	if not frappe.db.exists(source_doctype, source_name):
		return
	text = " ".join(_fin_index_names(source_doctype, source_name))
	frappe.db.set_value(source_doctype, source_name, "fin_index", text, update_modified=False)


def _safe_rebuild(targets, label):
	for source_doctype, source_name in set(targets):
		try:
			rebuild_fin_index(source_doctype, source_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"rebuild_fin_index {label}")


def _invoice_targets(doc):
	"""Semua (source_doctype, source_name) yang terhubung ke satu Sales Invoice —
	via custom field koneksi + child Invoice Container."""
	targets = set()
	for source_doctype, inv_field in (("Shipping List", "custom_shipping_list"),
	                                  ("Packing List", "custom_packing_list")):
		if doc.get(inv_field):
			targets.add((source_doctype, doc.get(inv_field)))
	for r in frappe.get_all(
		"Invoice Container", filters={"parent": doc.name, "parenttype": "Sales Invoice"},
		fields=["source_doctype", "source_name"],
	):
		if r.source_doctype in _SOURCES and r.source_name:
			targets.add((r.source_doctype, r.source_name))
	return targets


def _invoice_expense_notes(doc):
	"""Expense Note yang ditarik invoice ini — baris SEKARANG maupun SEBELUM disave.

	Yang lama ikut dihitung supaya EN yang baru saja DIHAPUS dari invoice kolomnya ikut
	dibersihkan; kalau hanya baris sekarang, EN itu selamanya terlihat masih ter-invoice.
	"""
	rows = list(doc.get("custom_reimburse_items") or [])
	before = doc.get_doc_before_save() if not doc.is_new() else None
	if before:
		rows += list(before.get("custom_reimburse_items") or [])
	return {r.get("expense_note") for r in rows if r.get("expense_note")}


def on_sales_invoice_change(doc, method=None):
	"""Hook Sales Invoice (create/update/submit/cancel) — didaftarkan di erpnext_custom."""
	_safe_rebuild(_invoice_targets(doc), "Sales Invoice")
	_sync_expense_note_links(_invoice_expense_notes(doc), "Sales Invoice")


def on_sales_invoice_trash(doc, method=None):
	# Simpan target SEBELUM baris Invoice Container ikut terhapus; rebuild di after_delete.
	doc.flags._fin_targets = list(_invoice_targets(doc))
	doc.flags._fin_expense_notes = list(_invoice_expense_notes(doc))


def after_sales_invoice_delete(doc, method=None):
	_safe_rebuild(doc.flags.get("_fin_targets") or [], "Sales Invoice delete")
	_sync_expense_note_links(doc.flags.get("_fin_expense_notes") or [], "Sales Invoice delete")


def _sync_expense_note_links(en_names, label):
	"""Kolom Invoice/Payment di list Expense Note. Sengaja tidak boleh menjatuhkan
	penyimpanan invoice/PV kalau gagal — ini kolom informasi, bukan angka pembukuan."""
	if not en_names:
		return
	from erp.expedition.doctype.expense_note.expense_note import sync_document_links

	try:
		sync_document_links(en_names)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"sync_document_links {label}")


def on_expense_note_change(doc, method=None):
	"""Hook Expense Note (create/update/void/delete) — segarkan indeks di Shipping/
	Packing List terkait (termasuk nilai LAMA bila link-nya berpindah)."""
	targets = set()
	before = None
	try:
		before = doc.get_doc_before_save()
	except Exception:
		before = None
	for field, source_doctype in (("shipping_list", "Shipping List"), ("packing_list", "Packing List")):
		if doc.get(field):
			targets.add((source_doctype, doc.get(field)))
		if before and before.get(field):
			targets.add((source_doctype, before.get(field)))
	_safe_rebuild(targets, "Expense Note")

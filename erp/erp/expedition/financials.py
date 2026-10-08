import json

import frappe

# Ringkasan finansial batch untuk list view Shipping List / Packing List
# (baris "Inv / Exp / Margin" di bawah tiap row list).

# source doctype -> (field link di Expense Note, custom field di Sales Invoice)
_SOURCES = {
	"Shipping List": ("shipping_list", "custom_shipping_list"),
	"Packing List": ("packing_list", "custom_packing_list"),
}


# source doctype -> (tabel multi-pilih SL/PL di Sales Invoice, field Link-nya). Tabelnya milik
# erpnext_custom; dibaca via string dan dicek ada-tidaknya supaya erp tetap steril.
_REF_TABLES = {
	"Shipping List": ("Invoice Shipping List Ref", "shipping_list"),
	"Packing List": ("Invoice Packing List Ref", "packing_list"),
}


def linked_invoices(source_doctype, names):
	"""{(invoice, source_name)} invoice yang memilih source di tab Connection: tabel
	multi-pilih + field tunggal lama. Belum difilter docstatus (pemanggil yang menyaring)."""
	names = [n for n in (names or []) if n]
	if not names:
		return set()
	out = set()
	child, fld = _REF_TABLES[source_doctype]
	if frappe.db.table_exists(child):
		out |= set(frappe.db.sql(
			f"""select parent, `{fld}` from `tab{child}`
			   where parenttype = 'Sales Invoice' and `{fld}` in %(n)s""",
			{"n": names},
		))
	inv_field = _SOURCES[source_doctype][1]
	if frappe.get_meta("Sales Invoice").has_field(inv_field):
		out |= {
			(r.name, r.get(inv_field))
			for r in frappe.get_all("Sales Invoice", filters={inv_field: ["in", names]}, fields=["name", inv_field])
		}
	return out


def item_source_shares(invoices):
	"""{invoice: {source_name: porsi 0..1}} dari kolom Source baris Items: porsi = jumlah
	base_amount item source itu / jumlah base_amount semua item ber-Source. Invoice tanpa
	item ber-Source (dokumen lama) TIDAK ada di hasil -> pemanggil memakai cara lamanya."""
	invoices = [i for i in (invoices or []) if i]
	if not invoices or not frappe.db.has_column("Sales Invoice Item", "custom_source"):
		return {}
	per = {}
	for inv, src, amt in frappe.db.sql(
		"""select parent, custom_source, sum(base_amount) from `tabSales Invoice Item`
		   where parenttype = 'Sales Invoice' and parent in %(p)s and ifnull(custom_source, '') != ''
		   group by parent, custom_source""",
		{"p": invoices},
	):
		per.setdefault(inv, {})[src] = amt or 0
	out = {}
	for inv, amts in per.items():
		total = sum(amts.values())
		out[inv] = {s: (a / total if total else 1 / len(amts)) for s, a in amts.items()}
	return out


def _company_currency():
	company = frappe.defaults.get_global_default("company")
	if company:
		cur = frappe.get_cached_value("Company", company, "default_currency")
		if cur:
			return cur
	return frappe.db.get_default("currency") or "IDR"


def _refund_base_by_en(en_names):
	"""{expense_note: total refund_amount (DPP saja, tanpa PPN/PPh/Materai)} dari Expense
	Refund yang Validated & non-void — dipakai mengurangi `total_amount` (DPP) di summary
	margin, konsisten dengan basis total_amount itu sendiri (tanpa komponen pajak)."""
	names = [n for n in (en_names or []) if n]
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select i.expense_note en, sum(i.refund_amount) amt
		   from `tabExpense Refund Item` i
		   join `tabExpense Refund` er on er.name = i.parent
		   where er.validated = 1 and er.void = 0 and i.expense_note in %(ens)s
		   group by i.expense_note""",
		{"ens": names}, as_dict=True,
	)
	return {r.en: (r.amt or 0) for r in rows}


def _invoice_container_totals(invoices):
	"""{sales_invoice: jumlah baris Invoice Container dari SEMUA job} — penyebut prorata."""
	if not invoices:
		return {}
	return dict(frappe.db.sql(
		"""select parent, count(*) from `tabInvoice Container`
		   where parenttype = 'Sales Invoice' and parent in %(p)s group by parent""",
		{"p": invoices},
	))


@frappe.whitelist()
def list_financials(source_doctype, names):
	"""Per dokumen sumber: daftar Sales Invoice (non-cancelled; draft ditandai),
	daftar Expense Note (non-void; reimburse ditandai, tidak dihitung), total
	revenue/expense (DPP, mata uang perusahaan) dan margin.

	Konsisten dengan tab Summary Shipping List: revenue hanya dari invoice
	Submitted; expense = total_amount * kurs. EN reimburse IKUT dihitung sebagai
	expense — invoice IR-nya juga masuk revenue penuh, jadi reimburse saling
	meniadakan di margin (kalau dinolkan, margin naik palsu sebesar reimburse).
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

	# EN reimburse ditandai di daftar, tapi tetap dihitung ke expense/margin.
	ens = frappe.get_all(
		"Expense Note",
		filters={en_field: ["in", names], "void": ["!=", 1]},
		fields=["name", en_field, "total_amount", "conversion_rate", "is_reimburse"],
		order_by="date asc, name asc",
	)
	refund_base = _refund_base_by_en([e.name for e in ens])
	for e in ens:
		o = out.get(e.get(en_field))
		if o is None:
			continue
		o["expenses"].append({"name": e.name, "reimburse": bool(e.is_reimburse)})
		o["expense"] += ((e.total_amount or 0) - refund_base.get(e.name, 0)) * (e.conversion_rate or 1)

	# Invoice terhubung: union dari child Invoice Container (per container yang
	# ditarik) dan custom field koneksi di Sales Invoice (mis. invoice reimburse
	# yang tidak menarik container). erp tetap steril: dibaca via string saja.
	# invoice -> {source: jumlah container yang ditarik dari source itu}
	inv_sources = {}
	ic = frappe.get_all(
		"Invoice Container",
		filters={"source_doctype": source_doctype, "source_name": ["in", names], "parenttype": "Sales Invoice"},
		fields=["parent", "source_name"],
	)
	for r in ic:
		if r.parent:
			s = inv_sources.setdefault(r.parent, {})
			s[r.source_name] = s.get(r.source_name, 0) + 1
	for inv, src in linked_invoices(source_doctype, names):
		inv_sources.setdefault(inv, {}).setdefault(src, 0)

	if inv_sources:
		invs = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list(inv_sources)], "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "base_total"],
			order_by="posting_date asc, name asc",
		)
		totals = _invoice_container_totals([iv.name for iv in invs])
		shares = item_source_shares([iv.name for iv in invs])
		for iv in invs:
			total = totals.get(iv.name, 0)
			share = shares.get(iv.name)
			for src, cnt in inv_sources.get(iv.name, {}).items():
				o = out.get(src)
				if o is None:
					continue
				o["invoices"].append({"name": iv.name, "draft": iv.docstatus == 0})
				# Draft (docstatus 0) & Submitted (1) sama-sama dihitung ke revenue — invoice
				# yang belum divalidasi tetap masuk margin. (Cancelled sudah difilter di query.)
				# 1 invoice menarik beberapa job: bagian tiap job = nilai item ber-Source job
				# itu. Invoice lama tanpa Source: base_total diprorata jumlah container per
				# job; tanpa container (mis. reimburse) masuk penuh ke job-nya.
				if share is not None:
					frac = share.get(src, 0)
				else:
					frac = cnt / total if total else 1
				o["revenue"] += (iv.base_total or 0) * frac

	# Dispatch Order (1 PL = 1 DPO) — kolom di list view Packing List, ikut batch ini
	# supaya list tidak perlu round-trip kedua.
	if source_doctype == "Packing List":
		for r in frappe.get_all(
			"Dispatch Order", filters={"packing_list": ["in", names]}, fields=["name", "packing_list"]
		):
			o = out.get(r.packing_list)
			if o is not None and not o.get("dpo"):
				o["dpo"] = r.name

	# Nomor BL untuk kolom list Shipping List: dihitung di sini (child table tidak ikut
	# query list) supaya list tetap satu round-trip.
	if source_doctype == "Shipping List":
		for r in frappe.get_all(
			"Shipping List BL",
			filters={"parenttype": "Shipping List", "parent": ["in", names]},
			fields=["parent", "bl_no"],
			order_by="parent asc, idx asc",
		):
			o = out.get(r.parent)
			if o is not None and r.bl_no:
				o.setdefault("bls", []).append(r.bl_no)

	for o in out.values():
		o["margin"] = o["revenue"] - o["expense"]
		o["margin_pct"] = round(o["margin"] / o["revenue"] * 100, 1) if o["revenue"] else None
		o["currency"] = currency
	return out


def _add_header_bl_invoices(shipping_list, seen, bucket):
	"""Invoice yang menaut Shipping List ini hanya di header / tab Connection, TANPA baris
	Invoice Container untuk job ini -- terutama impor legacy (dibuat sebelum invoice menarik
	container). Tanpa ini revenue-nya tidak sampai ke BL mana pun dan margin tiap BL terbaca 0,
	walau invoice-nya sendiri menyebut BL-nya di custom_bl_no ("A, B" kalau lebih dari satu).

	Hanya BL yang memang ada di Shipping List ini yang dipakai; invoice dengan beberapa BL
	dibagi rata (tak ada data container untuk prorata). Invoice yang sudah punya baris
	container (`seen`) tidak disentuh -- jalurnya yang lama lebih akurat.
	"""
	invs = {inv for inv, _src in linked_invoices("Shipping List", [shipping_list])} - seen
	if not invs:
		return
	bl_table = frappe.get_meta("Shipping List").get_field("bls").options
	sl_bls = set(frappe.get_all(bl_table, filters={"parent": shipping_list, "parenttype": "Shipping List"},
	                            pluck="bl_no"))
	for iv in frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", list(invs)], "docstatus": ["!=", 2]},
		fields=["name", "docstatus", "base_total", "posting_date", "currency", "conversion_rate",
		        "status", "outstanding_amount", "custom_bl_no"],
		order_by="posting_date asc, name asc",
	):
		bls = [b.strip() for b in (iv.custom_bl_no or "").split(",") if b.strip() in sl_bls]
		for b in bls:
			net = (iv.base_total or 0) / len(bls)
			d = bucket(b)
			d["invoices"].append({
				"name": iv.name, "draft": iv.docstatus == 0, "net": net,
				"date": str(iv.posting_date or ""),
				"currency": iv.currency or "", "rate": iv.conversion_rate or 1,
				"paid": iv.docstatus == 1 and (iv.status == "Paid" or (iv.outstanding_amount or 0) <= 0),
			})
			d["revenue"] += net


@frappe.whitelist()
def bl_financials(shipping_list):
	"""Per BL (bl_no) sebuah Shipping List: invoice, expense, margin — untuk kolom
	Invoice / Expense / Margin di tabel Bills of Lading.

	- Revenue per BL: base_total invoice. Bila 1 invoice mencakup beberapa BL
	  (atau beberapa Shipping List), di-prorata menurut jumlah container per BL di
	  child Invoice Container (item invoice memang dibuat 1 per container).
	- Expense per BL: hanya Expense Note yang BL No-nya diisi (EN tanpa BL No
	  dianggap level Shipping List, tidak diatribusikan ke BL). EN reimburse ikut
	  dihitung (ditandai saja di daftar) — pasangan invoice IR-nya juga masuk
	  revenue penuh, jadi keduanya saling meniadakan di margin.
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
	sl_rows = {}
	for r in rows:
		if r.parent:
			sl_rows[r.parent] = sl_rows.get(r.parent, 0) + 1
		if r.parent and r.bl_no:
			by_inv.setdefault(r.parent, []).append(r.bl_no)
	if by_inv:
		invs = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", list(by_inv)], "docstatus": ["!=", 2]},
			fields=["name", "docstatus", "base_total", "posting_date", "currency", "conversion_rate",
			        "status", "outstanding_amount"],
			order_by="posting_date asc, name asc",
		)
		totals = _invoice_container_totals([iv.name for iv in invs])
		shares = item_source_shares([iv.name for iv in invs])
		for iv in invs:
			bls = by_inv.get(iv.name, [])
			total_containers = len(bls) or 1
			# Bagian Shipping List ini dari invoice yang juga menarik job lain: dari Source
			# item; invoice lama tanpa Source -> prorata jumlah container.
			if iv.name in shares:
				sl_share = shares[iv.name].get(shipping_list, 0)
			else:
				sl_share = sl_rows[iv.name] / (totals.get(iv.name) or sl_rows[iv.name])
			counts = {}
			for b in bls:
				counts[b] = counts.get(b, 0) + 1
			for b, cnt in counts.items():
				d = bucket(b)
				# Net per BL untuk invoice ini = base_total diprorata jml container BL.
				net = (iv.base_total or 0) * sl_share * cnt / total_containers
				d["invoices"].append({
					"name": iv.name, "draft": iv.docstatus == 0, "net": net,
					"date": str(iv.posting_date or ""),
					# Mata uang dokumen + kursnya: `net` sudah IDR (base_total), tapi kolom
					# tabel ikut menampilkan nominal aslinya biar tidak terbaca sebagai Rupiah.
					"currency": iv.currency or "", "rate": iv.conversion_rate or 1,
					# Lunas: invoice tervalidasi yang tidak menyisakan outstanding.
					"paid": iv.docstatus == 1 and (iv.status == "Paid" or (iv.outstanding_amount or 0) <= 0),
				})
				# Draft & Submitted sama-sama dihitung ke revenue per BL (prorata container).
				d["revenue"] += net

	_add_header_bl_invoices(shipping_list, set(by_inv), bucket)

	ens = frappe.get_all(
		"Expense Note",
		filters={"shipping_list": shipping_list, "void": ["!=", 1], "bl_no": ["is", "set"]},
		fields=["name", "bl_no", "total_amount", "conversion_rate", "currency", "is_reimburse", "date",
		        "vendor", "expense_classes", "validated", "paid"],
		order_by="date asc, name asc",
	)
	refund_base = _refund_base_by_en([e.name for e in ens])
	for e in ens:
		d = bucket(e.bl_no)
		en_net = ((e.total_amount or 0) - refund_base.get(e.name, 0)) * (e.conversion_rate or 1)
		d["expenses"].append({
			"name": e.name, "reimburse": bool(e.is_reimburse),
			# Label status EN: Paid > Validated > Draft (EN tidak punya field status).
			"status": "Paid" if e.paid else ("Validated" if e.validated else "Draft"),
			"net": en_net,
			"date": str(e.date or ""),
			"currency": e.currency or "", "rate": e.conversion_rate or 1,
			"vendor": e.vendor or "",
			"classes": e.expense_classes or "",
		})
		d["expense"] += en_net

	for d in out.values():
		d["margin"] = d["revenue"] - d["expense"]
		# None (bukan 0) kalau belum ada revenue — biar bisa dibedakan dari margin 0%.
		d["margin_pct"] = round(d["margin"] / d["revenue"] * 100, 1) if d["revenue"] else None
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
	inv.update(i for i, _src in linked_invoices(source_doctype, [source_name]))
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
		# Semua SL/PL tabel multi-pilih, termasuk yang baru dilepas (versi sebelum save).
		child_field = inv_field + "s"
		fld = _REF_TABLES[source_doctype][1]
		for src in (doc, doc.get_doc_before_save() if not doc.is_new() else None):
			for r in (src.get(child_field) if src else None) or []:
				if r.get(fld):
					targets.add((source_doctype, r.get(fld)))
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
	names = {r.get("expense_note") for r in rows if r.get("expense_note")}

	# EN satu job ikut disegarkan bukan supaya kolom Invoice-nya terisi — invoice job
	# memang TIDAK dihitung (lihat sync_document_links) — melainkan supaya nilai LAMA
	# ikut dibersihkan saat invoice berpindah job atau baris reimburse-nya dicabut.
	jobs = {"shipping_list": set(), "packing_list": set()}
	for src in (doc, before):
		if not src:
			continue
		if src.get("custom_shipping_list"):
			jobs["shipping_list"].add(src.get("custom_shipping_list"))
		if src.get("custom_packing_list"):
			jobs["packing_list"].add(src.get("custom_packing_list"))
		for r in src.get("custom_shipping_lists") or []:
			if r.get("shipping_list"):
				jobs["shipping_list"].add(r.shipping_list)
		for r in src.get("custom_packing_lists") or []:
			if r.get("packing_list"):
				jobs["packing_list"].add(r.packing_list)
	for field, values in jobs.items():
		if values:
			names |= set(
				frappe.get_all("Expense Note", filters={field: ["in", list(values)]}, pluck="name")
			)
	return names


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
	# EN yang baru dibuat / pindah job harus langsung memungut invoice job-nya, karena
	# invoice-nya sudah ada lebih dulu dan tidak akan disave lagi.
	_sync_expense_note_links([doc.name], "Expense Note")

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
				if iv.docstatus == 1:
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
			fields=["name", "docstatus", "base_total"],
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
				d["invoices"].append({"name": iv.name, "draft": iv.docstatus == 0})
				if iv.docstatus == 1:
					d["revenue"] += (iv.base_total or 0) * cnt / total_containers

	ens = frappe.get_all(
		"Expense Note",
		filters={"shipping_list": shipping_list, "void": ["!=", 1], "bl_no": ["is", "set"]},
		fields=["name", "bl_no", "total_amount", "conversion_rate", "is_reimburse"],
		order_by="date asc, name asc",
	)
	for e in ens:
		d = bucket(e.bl_no)
		d["expenses"].append({"name": e.name, "reimburse": bool(e.is_reimburse)})
		if not e.is_reimburse:
			d["expense"] += (e.total_amount or 0) * (e.conversion_rate or 1)

	for d in out.values():
		d["margin"] = d["revenue"] - d["expense"]
	return out

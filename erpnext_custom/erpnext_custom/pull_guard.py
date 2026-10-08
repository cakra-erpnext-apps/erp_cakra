"""Dokumen yang ditarik/dipanggil transaksi harus masih boleh dipakai.

Satu aturan untuk semua doctype (doc_events "*" validate), supaya tidak tergantung
setiap picker/set_query ingat menyaringnya -- dropdown bawaan Frappe memang sudah
menyembunyikan master `disabled`, tapi query custom, import, API, dan draft agent tidak.

    Master (field disabled / enabled)   -> harus Enabled
    Shipping List, Packing List         -> tidak Closed dan tidak Void (tanpa Validate)
    Sales Order, Purchase Order         -> Validated dan tidak Closed

Yang dicek hanya tautan BARU dibanding versi tersimpan. Dokumen lama yang menunjuk master
yang belakangan di-disable / Master Job yang belakangan di-Close tetap bisa disimpan dan
dilanjutkan -- Close/Disable menutup tarikan BARU, bukan membatalkan yang sudah jalan.
"""

import frappe
from frappe import _

# Tautan balik/riwayat, bukan "menarik" dokumen untuk dipakai.
SKIP_FIELDS = {"amended_from", "return_against"}


def _app(doctype):
	cache = getattr(frappe.local, "cmi_pull_app", None)
	if cache is None:
		cache = frappe.local.cmi_pull_app = {}
	if doctype not in cache:
		cache[doctype] = frappe.get_doctype_app(doctype)
	return cache[doctype]


def _rule(doctype):
	"""(fields, fungsi baris -> alasan|None) untuk doctype tujuan, atau None bila bebas."""
	if doctype in ("Shipping List", "Packing List"):
		return ["closed", "void"], lambda r: (
			_("Void") if r.void else _("Closed") if r.closed else None)
	if doctype in ("Sales Order", "Purchase Order"):
		return ["docstatus", "status"], lambda r: (
			_("belum Validated") if r.docstatus != 1 else _("Closed") if r.status == "Closed" else None)
	# Master bawaan Frappe (User, Currency, Print Format, ...) bukan urusan aturan ini.
	if _app(doctype) == "frappe":
		return None
	meta = frappe.get_meta(doctype)
	if meta.is_submittable:
		return None
	if (f := meta.get_field("disabled")) and f.fieldtype == "Check":
		return ["disabled"], lambda r: _("Disabled") if r.disabled else None
	if (f := meta.get_field("enabled")) and f.fieldtype == "Check":
		return ["enabled"], lambda r: _("Disabled") if not r.enabled else None
	return None


def _refs(doc):
	"""{(doctype tujuan, nama)} dari semua Link/Dynamic Link di header dan child table."""
	out = set()
	if not doc:
		return out
	for d in [doc, *doc.get_all_children()]:
		for df in d.meta.get_link_fields() + d.meta.get_dynamic_link_fields():
			if df.fieldname in SKIP_FIELDS:
				continue
			value = d.get(df.fieldname)
			target = df.options if df.fieldtype == "Link" else d.get(df.options)
			if value and target and isinstance(value, str):
				out.add((target, value))
	out.discard((doc.doctype, doc.name))
	return out


def guard(doc, method=None):
	if (
		doc.flags.get("ignore_pull_guard")
		or frappe.flags.in_migrate
		or frappe.flags.in_install
		or frappe.flags.in_patch
		or doc.meta.istable
		# Buku besar / log yang ditulis kode (GL/Stock Ledger, Bin Ledger, Tax ...): mereka
		# mencatat transaksi yang sudah lolos penjaga ini, mis. stok keluar dari bin yang
		# baru di-disable -- menolaknya justru membuat isi bin itu tak bisa dikosongkan.
		or doc.meta.in_create
		or _app(doc.doctype) == "frappe"
	):
		return

	new = _refs(doc) - _refs(doc.get_doc_before_save())
	by_dt = {}
	for dt, name in new:
		by_dt.setdefault(dt, set()).add(name)

	problems = []
	for dt, names in by_dt.items():
		rule = _rule(dt)
		if not rule:
			continue
		fields, why = rule
		for r in frappe.get_all(dt, filters={"name": ["in", list(names)]}, fields=["name", *fields]):
			reason = why(r)
			if reason:
				problems.append(f"{_(dt)} <b>{r.name}</b> ({reason})")

	if problems:
		frappe.throw(
			_("Dokumen berikut tidak bisa dipakai di transaksi ini:<br>{0}<br><br>"
			  "Master harus Enabled, Shipping/Packing List tidak boleh Closed/Void, "
			  "Sales/Purchase Order harus Validated dan tidak Closed.").format("<br>".join(sorted(problems))),
			title=_("Tidak Bisa Ditarik"),
		)

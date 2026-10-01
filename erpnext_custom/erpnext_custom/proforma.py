"""Cermin Proforma Invoice <- Sales Invoice.

Doctype `Proforma Invoice` punya TABEL SENDIRI, tapi field-nya tidak ditulis ulang: file
doctype-nya cuma cangkang (satu field `amended_from`), sisanya dibuat di sini sebagai
Custom Field dari meta Sales Invoice yang SEDANG BERLAKU — standard field, custom field,
sampai Property Setter (hidden/label/options) semuanya sudah ikut terhitung di meta.

Artinya: tambah/ubah field di Sales Invoice, lalu `bench migrate`, dan proforma ikut
berubah sendiri. Tidak ada daftar field kembar yang harus dirawat, dan form proforma
otomatis tampil persis seperti form invoice.

Tabel ANAK dipakai bersama (Sales Invoice Item, Invoice Container, ...). Yang dipisah
dokumen induk & penomorannya; baris anak cukup dibedakan `parenttype`.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "ERPNext Custom"
SOURCE = "Sales Invoice"
TARGET = "Proforma Invoice"

# Field yang TIDAK ikut dicermin.
#   amended_from  : sudah ada di cangkang doctype (options-nya harus Proforma Invoice)
#   proforma_ref  : arah tautannya justru sebaliknya (Sales Invoice -> Proforma Invoice)
#   section Tax (Tax No + Kode Transaksi Coretax) : proforma bukan faktur pajak
SKIP = {"amended_from", "proforma_ref",
        "custom_tax_sb", "custom_tax_no", "custom_tax_cb", "custom_coretax_trx_code"}

# Pola nomor bawaan. Diubah user lewat Document Naming Settings (Property Setter, jadi
# tidak tertimpa migrate). Counter-nya dihitung controller: lihat ProformaInvoice.autoname.
NAMING_SERIES = "PR-INV/.custom_invoice_type_no./.####./.cmi_company_abbr./.cmi_yy."

# Properti yang ditimpa setelah disalin dari Sales Invoice.
OVERRIDE = {
	"naming_series": {"options": NAMING_SERIES, "default": NAMING_SERIES},
	# Judul print out (template: print_settings.invoice_title or doc.custom_invoice_title).
	# Default Sales Invoice "INVOICE"; di proforma harus PROFORMA INVOICE. Tetap bisa diganti
	# dari sidebar print.
	"custom_invoice_title": {"default": "PROFORMA INVOICE"},
}

# Field yang ikut dicermin (kolomnya tetap ada supaya impor per-nama-field tidak pincang)
# tapi DISEMBUNYIKAN: tidak berlaku untuk dokumen yang memang tidak pernah menjurnal.
HIDE = {"dont_post_to_gl",
        # Section Customer Paid: proforma tidak pernah dibayar. Section break yang di-hide
        # TIDAK menyembunyikan isinya, jadi semua field-nya ikut disebut.
        "custom_paid_sb", "custom_customer_paid", "custom_paid_date", "custom_payment_no",
        "custom_paid_cb1", "custom_paid_note", "custom_paid_cb2", "custom_paid_attachment"}

# Kolom list view yang dilepas di proforma: sebagian butuh formatter khusus dari
# public/js/sales_invoice_list.js (pill Paid, tautan RV, Created By/Assign To yang
# diturunkan dari owner/_assign) — list proforma tidak memuat file itu, jadi kolomnya
# akan tampil sebagai angka mentah/kosong. Sisanya memang urusan piutang, bukan proforma.
NO_LIST_COLUMN = {"custom_customer_paid", "custom_paid_date", "custom_payment_no",
                  "custom_created_by", "custom_assigned_to"}

# Field KHUSUS proforma (tidak ada di Sales Invoice): {field cermin sesudahnya: definisi}.
# Ikut dibuat & dijaga di sini supaya tidak dibuang _drop_stale.
#   custom_invoice_no : Sales Invoice yang memakai proforma ini (diisi hook invoice,
#                       sales_invoice/mapping.sync_proforma_invoice_no). Di form tampil di
#                       posisi "From Proforma" milik Sales Invoice.
EXTRA = {
	"custom_payment_term": {
		"fieldname": "custom_invoice_no", "fieldtype": "Link", "options": "Sales Invoice",
		"label": "Invoice No", "read_only": 1, "no_copy": 1, "in_list_view": 1,
		"in_standard_filter": 1, "depends_on": "custom_invoice_no",
	},
}

# Properti yang disalin apa adanya. permlevel/unique/search_index SENGAJA tidak ikut:
# permlevel butuh baris izin sendiri (kalau tidak, field jadi terkunci untuk semua orang),
# sedangkan unique & index cuma membebani tabel dokumen yang tidak pernah dicari lewat itu.
PROPS = (
	"fieldtype", "label", "options", "default", "description", "precision", "length",
	"reqd", "hidden", "read_only", "bold", "collapsible", "allow_on_submit", "no_copy",
	"print_hide", "print_hide_if_no_value", "print_width", "width", "columns",
	"non_negative", "translatable", "in_list_view", "in_standard_filter", "in_preview",
	"depends_on", "mandatory_depends_on", "read_only_depends_on", "collapsible_depends_on",
	"fetch_from", "fetch_if_empty", "ignore_user_permissions", "allow_in_quick_entry",
	"remember_last_selected_value", "hide_border", "hide_days", "hide_seconds",
	"sort_options", "link_filters", "ignore_xss_filter", "allow_bulk_edit",
	"make_attachment_public",
)


def _mirror_fields():
	"""[{...definisi custom field...}] urut sesuai form Sales Invoice."""
	out = []
	prev = "amended_from"  # satu-satunya field bawaan di cangkang doctype
	for df in frappe.get_meta(SOURCE).fields:
		if df.fieldname in SKIP or not df.fieldname:
			continue
		d = {"fieldname": df.fieldname, "insert_after": prev, "module": MODULE, "permlevel": 0}
		for p in PROPS:
			v = df.get(p)
			if v not in (None, ""):
				d[p] = v
		# Deskripsi yang DIKOSONGKAN di Sales Invoice harus ikut kosong di sini: tanpa ini
		# nilai kosong dilewati dan deskripsi lama di custom field proforma tertinggal.
		d["description"] = df.get("description") or ""
		if df.fieldname in HIDE:
			d["hidden"] = 1
		if df.fieldname in NO_LIST_COLUMN:
			d["in_list_view"] = 0
		d.update(OVERRIDE.get(df.fieldname, {}))
		# Hidden + wajib + tanpa default (company, price list, total) ditolak validasi
		# DocType setiap Property Setter disimpan, mis. dari Document Naming Settings.
		# Field ini diisi otomatis (form/mesin hitung); company dicek di controller.
		if d.get("hidden") and d.get("reqd") and not d.get("default"):
			d["reqd"] = 0
		out.append(d)
		prev = df.fieldname
		if df.fieldname in EXTRA:
			extra = dict(EXTRA[df.fieldname], insert_after=prev, module=MODULE, permlevel=0)
			out.append(extra)
			prev = extra["fieldname"]
	return out


def _drop_stale(keep):
	"""Field yang sudah tidak ada lagi di Sales Invoice ikut dibuang dari proforma —
	kalau tidak, kolom yatim menumpuk tiap kali invoice dirapikan."""
	stale = frappe.get_all(
		"Custom Field", filters={"dt": TARGET, "fieldname": ["not in", list(keep)]}, pluck="name"
	)
	for name in stale:
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	return stale


def _ensure_field_order(order):
	"""Kunci urutan field lewat Property Setter, sama seperti Customize Form.

	Tanpa ini urutannya bergantung pada rantai `insert_after` ratusan custom field, dan
	satu mata rantai putus = form berantakan. Frappe MEMBUANG field_order yang panjangnya
	tak sama dengan jumlah field, jadi ditulis hanya kalau cocok."""
	frappe.clear_cache(doctype=TARGET)
	names = [f.fieldname for f in frappe.get_meta(TARGET).fields]
	if sorted(names) != sorted(order):
		frappe.log_error(
			"Proforma mirror: %d field vs %d urutan" % (len(names), len(order)),
			"ensure_proforma_mirror",
		)
		return
	name = frappe.db.exists("Property Setter", {"doc_type": TARGET, "property": "field_order"})
	ps = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
	ps.update({
		"doctype_or_field": "DocType", "doc_type": TARGET, "property": "field_order",
		"property_type": "Text", "value": json.dumps(order),
	})
	ps.flags.ignore_permissions = True
	ps.flags.validate_fields_for_doctype = False
	ps.save()
	frappe.clear_cache(doctype=TARGET)


def ensure_mirror():
	"""Bangun/segarkan cermin field. Idempotent — dipanggil tiap migrate."""
	if not frappe.db.exists("DocType", TARGET):
		return
	fields = _mirror_fields()
	create_custom_fields({TARGET: fields}, ignore_validate=True)
	keep = {f["fieldname"] for f in fields}
	_drop_stale(keep)
	_ensure_field_order(["amended_from"] + [f["fieldname"] for f in fields])
	_backfill_extra()


def _backfill_extra():
	"""Isi Invoice No & Source No untuk proforma yang dibuat sebelum kolom itu ada.
	Idempoten; lewat db.set_value supaya proforma yang sudah dipakai (terkunci) ikut terisi."""
	from erpnext_custom.overrides.sales_invoice import backfill_source_nos

	used = dict(frappe.get_all(
		"Sales Invoice", filters={"proforma_ref": ["is", "set"], "docstatus": ["!=", 2]},
		fields=["proforma_ref", "name"], as_list=True,
	))
	for name, current in frappe.get_all(TARGET, fields=["name", "custom_invoice_no"], as_list=True):
		if (current or "") != (used.get(name) or ""):
			frappe.db.set_value(TARGET, name, "custom_invoice_no", used.get(name) or "", update_modified=False)
	backfill_source_nos(TARGET)


# ---- Print format ------------------------------------------------------------------
PRINT_FORMAT = "Proforma Print Out"
_SOURCE_PRINT_FORMAT = "Invoice Print Out"
# Penanda proforma di atas template invoice: judul default, dan watermark diagonal yang
# SELALU tampil bertuliskan PROFORMA (di invoice: PAID, hanya saat Customer Paid).
_PRINT_REPLACE = (
	('doc.custom_invoice_title or "INVOICE"', 'doc.custom_invoice_title or "PROFORMA INVOICE"'),
	('{%- set show_watermark = (_wm == "1") or (_wm is none and doc.custom_watermark_paid) -%}',
	 '{%- set show_watermark = True -%}'),
	("<b>PAID</b>", "<b>PROFORMA</b>"),
)


def ensure_print_format():
	"""Salin print out invoice jadi print out proforma (judulnya PROFORMA INVOICE).

	Disalin di sini, bukan di-fork jadi file kedua: isinya membaca field yang sama persis,
	jadi satu perubahan di print out invoice cukup, proforma ikut saat migrate."""
	if not frappe.db.exists("Print Format", _SOURCE_PRINT_FORMAT):
		return
	# SEMUA properti disalin, bukan daftar pilihan: dulu `custom_format` tertinggal (0) dan
	# Frappe diam-diam merender layout standar alih-alih HTML print out.
	src = frappe.get_doc("Print Format", _SOURCE_PRINT_FORMAT).as_dict(no_default_fields=True)
	html = src.html or ""
	for old, new in _PRINT_REPLACE:
		if old not in html:
			# Template invoice berubah: salinan tetap dibuat, tapi penanda proforma hilang.
			frappe.log_error("Proforma print out: teks %r tidak ada di %s" % (old, _SOURCE_PRINT_FORMAT),
			                 "ensure_proforma_print_format")
		html = html.replace(old, new)
	values = dict(src, html=html, doc_type=TARGET, module=MODULE, standard="No", disabled=0)
	if frappe.db.exists("Print Format", PRINT_FORMAT):
		pf = frappe.get_doc("Print Format", PRINT_FORMAT)
		pf.update(values)
		pf.flags.ignore_permissions = True
		pf.save()
		return
	pf = frappe.new_doc("Print Format")
	pf.name = PRINT_FORMAT  # autoname "Prompt": nama harus diisi sendiri sebelum insert
	pf.update(values)
	pf.flags.ignore_permissions = True
	pf.insert()

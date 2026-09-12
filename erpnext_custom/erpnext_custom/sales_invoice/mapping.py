import frappe


@frappe.whitelist()
def make_sales_invoice_from_delivery_note(source_name, target_doc=None, args=None):
	"""Map DN items while preserving the CMI invoice classification header."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	if isinstance(target_doc, str):
		target_doc = frappe.get_doc(frappe.parse_json(target_doc))

	preserved = {}
	if target_doc:
		for fieldname in (
			"custom_invoice_type",
			"custom_invoice_type_no",
			"custom_invoice_behavior",
		):
			preserved[fieldname] = target_doc.get(fieldname)

	mapped = make_sales_invoice(source_name, target_doc=target_doc, args=args)
	defaults = {
		"custom_invoice_type": "Trading",
		"custom_invoice_type_no": "C/T",
		"custom_invoice_behavior": "Normal",
	}
	for fieldname, default in defaults.items():
		mapped.set(fieldname, preserved.get(fieldname) or default)
	return mapped


# ---- Import from Proforma Invoice ---------------------------------------------------
# Proforma Invoice adalah doctype (dan tabel) TERPISAH, tapi field-nya cermin Sales Invoice
# dan tabel anaknya sama persis — jadi "impor" di sini cukup menyalin per nama field, tanpa
# daftar mapping yang harus dirawat tiap ada field baru.
# 1:1: invoice hasil impor menyimpan `proforma_ref`, dan proforma yang sudah dirujuk tidak
# muncul lagi di pemilihan.

# Kolom identitas baris anak — harus dibuang, kalau ikut tersalin baris barunya menimpa
# baris milik proformanya.
_ROW_IDENTITY = {
	"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
	"parent", "parentfield", "parenttype", "doctype", "__islocal", "__unsaved",
}


@frappe.whitelist()
def get_taken_proformas():
	"""Nomor Proforma Invoice yang SUDAH diimpor ke sebuah Sales Invoice (non-cancelled).

	Dipakai client sebagai filter negatif dropdown — lebih murah daripada mengirim daftar
	proforma yang tersedia (Link field mencari & memuatnya sendiri).
	"""
	if not frappe.has_permission("Proforma Invoice", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
	return sorted({
		r.proforma_ref
		for r in frappe.get_all(
			"Sales Invoice",
			filters={"proforma_ref": ["is", "set"], "docstatus": ["!=", 2]},
			fields=["proforma_ref"],
		)
		if r.proforma_ref
	})


@frappe.whitelist()
def import_from_proforma(source_name, target_doc=None):
	"""Salin sebuah Proforma Invoice ke Sales Invoice yang sedang dibuka (invoice BARU).

	Penyalinannya per nama field, dibatasi oleh meta Sales Invoice: field ber-`no_copy`
	(nomor, status, audit, Don't Post to GL, outstanding) SENGAJA dilewati — itu yang
	menjaga invoice hasil impor tetap dokumen baru yang bersih, bukan tiruan proformanya.

	`target_doc` (doc form yang sedang dibuka) WAJIB dipertahankan namanya: client
	me-`frappe.model.sync` hasilnya ke form yang sama.
	"""
	if not frappe.has_permission("Sales Invoice", "create"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	src = frappe.get_doc("Proforma Invoice", source_name)
	if src.docstatus == 2:
		frappe.throw(frappe._("Proforma {0} sudah dibatalkan.").format(source_name))
	taken = frappe.db.get_value(
		"Sales Invoice", {"proforma_ref": source_name, "docstatus": ["!=", 2]}, "name"
	)
	if taken:
		frappe.throw(
			frappe._("Proforma {0} sudah diimpor ke invoice {1}.").format(source_name, taken)
		)

	target_meta = frappe.get_meta("Sales Invoice")
	data = {}
	for df in src.meta.fields:
		tdf = target_meta.get_field(df.fieldname)
		if not tdf or tdf.no_copy or tdf.fieldtype != df.fieldtype:
			continue
		value = src.get(df.fieldname)
		# Tabel DULUAN: "Table" termasuk no_value_fields, jadi kalau filter di bawah
		# dijalankan lebih dulu semua tabel anak diam-diam tidak ikut tersalin.
		if tdf.fieldtype in ("Table", "Table MultiSelect"):
			if tdf.options != df.options:
				continue
			data[df.fieldname] = [
				{k: v for k, v in row.as_dict().items() if k not in _ROW_IDENTITY}
				for row in (value or [])
			]
		elif tdf.fieldtype in frappe.model.no_value_fields:
			continue
		elif value not in (None, ""):
			data[df.fieldname] = value
	data["proforma_ref"] = source_name

	if isinstance(target_doc, str):
		target_doc = frappe.parse_json(target_doc)
	target = frappe.get_doc(target_doc) if target_doc else frappe.new_doc("Sales Invoice")
	name = target.name
	target.update(data)
	target.name = name  # update() bisa ikut menimpa name; kembalikan ke nama doc form
	return target

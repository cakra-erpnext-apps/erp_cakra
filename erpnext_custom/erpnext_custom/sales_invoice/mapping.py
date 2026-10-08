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


def guard_proforma_once(doc, method=None):
	"""validate Sales Invoice: satu Proforma hanya untuk SATU invoice (non-cancelled).

	Dialog & tombol Import sudah menyaring, tapi dua invoice baru yang mengimpor proforma
	sama sebelum salah satunya tersimpan akan lolos keduanya -> ditegakkan saat simpan."""
	if not doc.get("proforma_ref"):
		return
	other = frappe.db.get_value(
		"Sales Invoice",
		{"proforma_ref": doc.proforma_ref, "docstatus": ["!=", 2], "name": ["!=", doc.name]},
		"name",
	)
	if other:
		frappe.throw(
			frappe._("Proforma {0} sudah dipakai invoice {1}. Satu proforma hanya untuk satu invoice.")
			.format(doc.proforma_ref, other),
			title=frappe._("Proforma sudah dipakai"),
		)


def sync_proforma_invoice_no(doc, method=None):
	"""Kolom Invoice No di Proforma = Sales Invoice (non-cancelled) yang merujuknya.

	Dipanggil saat invoice disimpan / dibatalkan / dihapus. Proforma lama (sebelum
	proforma_ref diubah) ikut disegarkan supaya tidak tertinggal menunjuk invoice ini.
	db.set_value, bukan save: proforma yang sudah dipakai terkunci (downstream lock)."""
	refs = {doc.get("proforma_ref")}
	before = doc.get_doc_before_save() if method != "after_delete" else None
	if before:
		refs.add(before.get("proforma_ref"))
	for ref in filter(None, refs):
		if not frappe.db.exists("Proforma Invoice", ref):
			continue
		# Sesudah invoice dihapus, query ini memang sudah tidak menemukannya.
		used = frappe.db.get_value(
			"Sales Invoice", {"proforma_ref": ref, "docstatus": ["!=", 2]}, "name"
		)
		frappe.db.set_value("Proforma Invoice", ref, "custom_invoice_no", used or "", update_modified=False)


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


# ---- Import from SO / DN (tab Connection > Trading) ---------------------------------------
_TRADING_MAPPERS = {
	"Sales Order": ("erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice", "sales_order"),
	"Delivery Note": ("erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice", "delivery_note"),
}
# Header CMI yang tidak boleh ditimpa mapper ERPNext.
_KEEP_HEADER = ("custom_invoice_type", "custom_invoice_type_no", "custom_invoice_behavior",
	"custom_invoice_connection", "naming_series", "invoice_date", "posting_date", "set_posting_time")


@frappe.whitelist()
def import_trading(source_doctype, source_names, target_doc):
	"""Tarik item SO/DN terpilih ke Sales Invoice yang sedang dibuka lewat mapper ERPNext
	(qty = sisa yang belum ditagih; baris tertaut so_detail/dn_detail). Sumber yang barisnya
	sudah ada di invoice dilewati supaya tidak dobel. Kembali {doc, imported, skipped}."""
	if source_doctype not in _TRADING_MAPPERS:
		frappe.throw(frappe._("Sumber tidak didukung: {0}").format(source_doctype))
	method, link = _TRADING_MAPPERS[source_doctype]
	mapper = frappe.get_attr(method)
	names = frappe.parse_json(source_names) if isinstance(source_names, str) else (source_names or [])
	target = frappe.get_doc(frappe.parse_json(target_doc) if isinstance(target_doc, str) else target_doc)
	if target.doctype != "Sales Invoice":
		frappe.throw(frappe._("Import from SO/DN hanya untuk Sales Invoice."))
	kept = {f: target.get(f) for f in _KEEP_HEADER if target.meta.has_field(f)}
	target.set("items", [i for i in target.get("items") or [] if i.get("item_code")])  # baris kosong
	present = {i.get(link) for i in target.get("items")}
	imported, skipped = [], []
	for src in names:
		if src in present:
			skipped.append(src)
			continue
		target = mapper(src, target)
		imported.append(src)
	for f, v in kept.items():
		if v:
			target.set(f, v)
	# Item Category tipe invoice: baris di luar kategori tidak ikut diimport (sisanya tetap
	# belum ditagih di SO/DN-nya).
	from erpnext_custom.invoice_types import allowed_item_groups, item_query_type

	groups = allowed_item_groups(item_query_type(target))
	dropped = []
	if groups:
		keep = []
		for it in target.get("items") or []:
			if it.get(link) in imported and frappe.get_cached_value("Item", it.item_code, "item_group") not in groups:
				dropped.append(it.item_code)
			else:
				keep.append(it)
		target.set("items", keep)
	# Model harga CMI: Price per baris (custom_item_price) x kurs = rate. Baris hasil mapper
	# cuma punya rate -> Price diisi dari rate (mata uang header) supaya grid tampil benar.
	for it in target.get("items") or []:
		if not it.get("custom_item_price") and it.get("rate"):
			it.custom_item_price = it.rate
			it.custom_currency = it.get("custom_currency") or target.currency
			it.custom_exchange_rate = it.get("custom_exchange_rate") or 1
	return {"doc": target.as_dict(), "imported": imported, "skipped": skipped, "dropped": dropped}

"""Cek Proforma Invoice: tabel & penomoran sendiri, hitungan total jalan, dan impor 1:1
ke Sales Invoice. Dokumen uji dibuat lalu DI-ROLLBACK — tidak ada data yang tertinggal.

    bench --site erp.localhost console
    >>> from erpnext_custom.test_proforma import run; run()
"""

import frappe

from erpnext_custom.sales_invoice.mapping import get_taken_proformas, import_from_proforma

_ROW_SKIP = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
             "parent", "parentfield", "parenttype", "doctype"}


def _proforma_from_invoice(si):
	"""Salin Sales Invoice -> Proforma Invoice per nama field (arah kebalikan tombol Import)."""
	pf = frappe.new_doc("Proforma Invoice")
	for df in pf.meta.fields:
		sdf = si.meta.get_field(df.fieldname)
		if not sdf or sdf.fieldtype != df.fieldtype:
			continue
		value = si.get(df.fieldname)
		# Tabel DULUAN: "Table" termasuk no_value_fields.
		if df.fieldtype in ("Table", "Table MultiSelect"):
			if sdf.options != df.options:
				continue
			for row in value or []:
				pf.append(df.fieldname, {k: v for k, v in row.as_dict().items() if k not in _ROW_SKIP})
		elif df.fieldtype in frappe.model.no_value_fields:
			continue
		elif value not in (None, ""):
			pf.set(df.fieldname, value)
	return pf


def run():
	src_name = frappe.db.get_value(
		"Sales Invoice", {"docstatus": 1}, "name", order_by="modified desc"
	)
	assert src_name, "butuh minimal satu Sales Invoice tervalidasi sebagai contekan"
	si = frappe.get_doc("Sales Invoice", src_name)

	# Tabel & penomoran sendiri.
	pf = _proforma_from_invoice(si)
	pf.insert(ignore_permissions=True)
	assert frappe.db.exists("Proforma Invoice", pf.name)
	assert not frappe.db.exists("Sales Invoice", pf.name), "proforma bocor ke tabel invoice"
	# Pola nomor diatur user di Document Naming Settings; yang dicek cuma kuncinya:
	# Type No tidak bisa diganti setelah bernomor.
	other = next(n for n in ("C/E", "C/T", "IR") if n != pf.custom_invoice_type_no)
	pf.custom_invoice_type_no = other
	try:
		pf.save(ignore_permissions=True)
		raise AssertionError("Type No proforma bernomor masih bisa diganti")
	except frappe.ValidationError:
		pf.reload()

	# Hitungan total jalan (mesin ERPNext dipanggil controller proforma).
	assert pf.items, "baris item tidak ikut tersalin"
	assert pf.grand_total, "grand total proforma tidak terhitung"
	assert pf.in_words, "terbilang proforma kosong"

	# Proforma tidak pernah menjurnal dan tidak di-submit (tanpa Validate).
	assert not pf.meta.is_submittable, "proforma masih submittable"
	assert not frappe.db.exists("GL Entry", {"voucher_type": "Proforma Invoice", "voucher_no": pf.name})

	# Impor ke Sales Invoice baru: nama doc form dipertahankan (client men-sync ke form itu).
	target = {"doctype": "Sales Invoice", "name": "new-sales-invoice-1", "__islocal": 1, "docstatus": 0}
	inv = import_from_proforma(pf.name, target_doc=dict(target))
	assert inv.name == target["name"], "nama doc form tidak dipertahankan: %s" % inv.name
	assert inv.proforma_ref == pf.name
	assert not inv.dont_post_to_gl, "field no_copy ikut tersalin"
	assert inv.customer == pf.customer and len(inv.items) == len(pf.items)
	assert inv.custom_packing_list == pf.custom_packing_list

	inv.insert(ignore_permissions=True)
	assert inv.name != pf.name, "invoice hasil impor ikut bernomor proforma"
	assert pf.name in get_taken_proformas(), "proforma terpakai masih muncul di pilihan"
	# Kolom list proforma: Invoice No (diisi hook invoice) & Source No (SL + PL).
	assert frappe.db.get_value("Proforma Invoice", pf.name, "custom_invoice_no") == inv.name, 		"Invoice No proforma tidak terisi"
	for src in (pf.custom_shipping_list, pf.custom_packing_list):
		assert not src or src in (pf.custom_shipping_list_nos or ""), "Source No tanpa %s" % src

	# 1:1 saat SIMPAN: invoice kedua yang merujuk proforma sama ditolak walau lolos impor.
	inv2 = frappe.get_doc(frappe.copy_doc(inv).as_dict())
	inv2.proforma_ref = pf.name
	try:
		inv2.insert(ignore_permissions=True)
		raise AssertionError("invoice kedua dengan proforma sama seharusnya ditolak")
	except frappe.ValidationError as e:
		assert "sudah dipakai" in str(e), "ditolak karena hal lain: %s" % e
		frappe.clear_last_message()

	# 1:1 — proforma yang sama tidak bisa diimpor dua kali.
	try:
		import_from_proforma(pf.name, target_doc=dict(target))
		raise AssertionError("impor kedua seharusnya ditolak")
	except frappe.ValidationError:
		frappe.clear_last_message()

	frappe.db.rollback()
	print("Proforma OK: %s (total %s) -> %s (rolled back)" % (pf.name, pf.grand_total, inv.name))

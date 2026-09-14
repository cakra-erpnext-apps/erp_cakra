import json

import frappe
from frappe.desk.reportview import get_match_cond
from frappe.utils import flt
from erpnext.buying.doctype.purchase_order.purchase_order import (
	make_purchase_invoice as erpnext_make_purchase_invoice,
)

from erpnext_custom.overrides.purchasing import _compute_display


PURCHASE_AMOUNT_FIELDS = (
	"custom_discount_input",
	"custom_discount_percent",
	"custom_discount_amount",
	"custom_pph_input",
	"custom_pph_percent",
	"custom_pph_amount",
	"custom_tax_input",
	"custom_tax_percent",
	"custom_tax_amount",
	"custom_materai",
	"custom_ignore_tax",
)


@frappe.whitelist()
def make_purchase_invoice(source_name, target_doc=None, args=None):
	"""Tarik baris PO ke Purchase Invoice, dibatasi sisa qty yang belum difakturkan.

	Dulu di sini ada penjaga "PO ini sudah pernah ditarik -> kembalikan target apa
	adanya".  Itu memblokir penarikan SISA qty yang sah: PO 10, sudah ditarik 5 ke
	invoice ini, user memilih PO yang sama untuk 5 sisanya -> tidak terjadi apa-apa
	dan tabel Items tampak tidak berubah.  Perlindungan dari qty dobel sepenuhnya
	dipegang _apply_active_pi_remaining_qty, yang kini juga menghitung baris yang
	sudah ada di dokumen ini (termasuk yang belum tersimpan).
	"""
	target = _as_document(target_doc)
	# Amount settings belong to the first PO used to create the invoice.  Do not
	# overwrite user-entered PI amounts when another PO is appended later.
	copy_amounts = not target or not target.get("items")
	# Baris lama dikenali dari POSISI, bukan dari `name`: baris yang belum tersimpan
	# name-nya None, jadi kalau dipakai sebagai kunci semuanya saling tabrak dan baris
	# baru ikut dikira baris lama (lolos dari pembatasan qty).  get_mapped_doc selalu
	# menambahkan baris hasil pemetaan di BELAKANG baris yang sudah ada.
	existing_count = len(target.get("items", [])) if target else 0
	mapped = erpnext_make_purchase_invoice(source_name, target_doc, args)
	_apply_active_pi_remaining_qty(mapped, existing_count)
	if len(mapped.get("items", [])) <= existing_count:
		# Tanpa pesan ini user cuma melihat dialog tertutup dan tabel Items tak berubah.
		frappe.msgprint(
			frappe._("{0} sudah difakturkan penuh, tidak ada sisa qty yang bisa ditarik.")
			.format(source_name)
		)
	if copy_amounts:
		_copy_purchase_amounts(frappe.get_doc("Purchase Order", source_name), mapped)
	return mapped


def _as_document(target_doc):
	if not target_doc:
		return None
	if hasattr(target_doc, "doctype"):
		return target_doc
	if isinstance(target_doc, str):
		target_doc = json.loads(target_doc)
	return frappe.get_doc(target_doc)


def _copy_purchase_amounts(source, target):
	for fieldname in PURCHASE_AMOUNT_FIELDS:
		target.set(fieldname, source.get(fieldname))

	# Native tax rows have already been mapped by ERPNext. Recalculate them and
	# refresh the CMI display without requiring GL-account setup during import;
	# the normal before_validate hook rebuilds/checks CMI rows when PI is saved.
	target.calculate_taxes_and_totals()
	_compute_display(target)


def _apply_active_pi_remaining_qty(target, existing_count):
	"""Batasi baris PO yang BARU dipetakan dengan sisa qty yang belum difakturkan.

	Jatah terpakai = baris di PI LAIN yang masih hidup (docstatus < 2) DITAMBAH baris
	yang sudah ada di dokumen ini.  Baris dokumen ini sengaja dihitung dari memori,
	bukan dari DB, supaya dua hal ikut terhitung: baris yang belum tersimpan (mapper
	ERPNext bisa terpanggil dua kali dalam satu klik) dan qty yang baru saja diubah
	user tapi belum disimpan.  Karena itu PI ini dikecualikan dari hitungan SQL —
	kalau tidak, baris tersimpannya terhitung dua kali.
	"""
	allocated = {}
	remove = []
	for index, row in enumerate(target.get("items", [])):
		po_detail = row.get("po_detail")
		if not po_detail:
			continue

		if po_detail not in allocated:
			allocated[po_detail] = flt(
				frappe.db.sql(
					"""
					select sum(pii.qty)
					from `tabPurchase Invoice Item` pii
					inner join `tabPurchase Invoice` pi on pi.name = pii.parent
					where pii.po_detail = %s and pi.docstatus < 2 and pi.name != %s
					""",
					(po_detail, target.get("name") or ""),
				)[0][0]
			)

		if index < existing_count:
			allocated[po_detail] += flt(row.qty)
			continue

		ordered_qty = flt(frappe.db.get_value("Purchase Order Item", po_detail, "qty"))
		remaining_qty = ordered_qty - allocated[po_detail]
		if remaining_qty <= 0:
			remove.append(row)
		else:
			row.qty = min(flt(row.qty), remaining_qty)
			allocated[po_detail] += flt(row.qty)

	for row in remove:
		target.remove(row)

	target.calculate_taxes_and_totals()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def purchase_order_query(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	filters,
	as_dict=False,
	**kwargs,
):
	"""Show POs with quantity still available across Draft and submitted PIs."""
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else filters or {})
	params = {
		"txt": f"%{txt}%",
		"company": filters.get("company"),
		"supplier": filters.get("supplier"),
		"start": start,
		"page_len": page_len,
	}
	company_condition = "and po.company = %(company)s" if params["company"] else ""
	supplier_condition = "and po.supplier = %(supplier)s" if params["supplier"] else ""

	return frappe.db.sql(
		f"""
		select po.name, po.supplier, po.schedule_date, 'Validate' as status
		from `tabPurchase Order` po
		where po.docstatus = 1
			and po.status not in ('Closed', 'On Hold')
			and (po.name like %(txt)s or po.supplier like %(txt)s)
			{company_condition}
			{supplier_condition}
			and exists (
				select 1
				from `tabPurchase Order Item` poi
				where poi.parent = po.name
					and poi.qty > coalesce((
						select sum(pii.qty)
						from `tabPurchase Invoice Item` pii
						inner join `tabPurchase Invoice` pi on pi.name = pii.parent
						where pii.po_detail = poi.name
							and pi.docstatus < 2
					), 0) + 0.000001
			)
			{get_match_cond("Purchase Order")}
		order by po.modified desc
		limit %(start)s, %(page_len)s
		""",
		params,
		as_dict=as_dict,
	)

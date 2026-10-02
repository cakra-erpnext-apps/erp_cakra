import frappe

from crm_cakra.patches.v1_0.seed_procurement_email_template import NAMA, SUBJEK


def _add_rows(parenttype, header):
	"""Rute header lama -> baris pertama tabel routes (dokumen yang belum punya tabel)."""
	o, d = header["origin"], header["destination"]
	extra = f", {header['detail']} as detail" if header.get("detail") else ", null as detail"
	docs = frappe.db.sql(
		f"""select p.name, p.{o} as origin, p.{d} as destination{extra}
		from `tab{parenttype}` p
		where ifnull(p.{o}, '') != '' and ifnull(p.{d}, '') != ''
		and not exists (select 1 from `tabCRM Shipment Route` r
			where r.parent = p.name and r.parenttype = %s)""",
		parenttype,
		as_dict=True,
	)
	for doc in docs:
		frappe.get_doc(
			{
				"doctype": "CRM Shipment Route",
				"parent": doc.name,
				"parenttype": parenttype,
				"parentfield": "routes",
				"idx": 1,
				"origin": doc.origin,
				"destination": doc.destination,
				"detail_address": doc.detail,
			}
		).db_insert()
	return len(docs)


def execute():
	frappe.reload_doc("fcrm", "doctype", "crm_shipment_route")
	for dt in ("crm_inquiry", "crm_quotation", "crm_estimation"):
		frappe.reload_doc("fcrm", "doctype", dt)

	_add_rows(
		"CRM Inquiry",
		{"origin": "origin", "destination": "destination", "detail": "port_pol_destination_detail_address"},
	)
	_add_rows("CRM Quotation", {"origin": "loading", "destination": "unloading"})
	_add_rows("CRM Estimation", {"origin": "loading", "destination": "unloading"})
	frappe.db.sql(
		"""update `tabCRM Quotation` set loading_route = loading, unloading_route = unloading
		where ifnull(loading, '') != '' and ifnull(loading_route, '') = ''"""
	)
	frappe.db.sql(
		"""update `tabCRM Quotation` set margin_pct = margin / estimation_costing * 100
		where ifnull(estimation_costing, 0) != 0"""
	)

	# Communication Status inquiry kini murni dari diskusi procurement.
	frappe.db.sql("update `tabCRM Inquiry` set communication_status = 'Open'")
	frappe.db.sql(
		"""update `tabCRM Inquiry` i
		join `tabCRM Procurement` p on p.inquiry = i.name
		set i.communication_status = 'Replied'
		where exists (select 1 from `tabComment` c where c.reference_doctype = 'CRM Procurement'
			and c.reference_name = p.name and c.comment_type = 'Comment')"""
	)

	# Subject email Submit to Procurement: hanya kalau masih bawaan lama.
	if frappe.db.get_value("Email Template", NAMA, "subject") == "Request Procurement: {{ inquiry }}":
		frappe.db.set_value("Email Template", NAMA, "subject", SUBJEK)

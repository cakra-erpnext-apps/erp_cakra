"""Daftar faktur pajak keluaran untuk impor Coretax + status kelengkapan datanya.

XML-nya dibangun di erpnext_custom.coretax; report ini cuma jendela lihat-dulu supaya
ketahuan invoice mana yang datanya belum lengkap sebelum file diupload ke Coretax.
"""

import frappe

from erpnext_custom.coretax import collect

COLUMNS = [
	{"label": "Invoice", "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
	{"label": "Tanggal", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
	{"label": "Pembeli", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
	{"label": "NPWP", "fieldname": "buyer_tin", "fieldtype": "Data", "width": 140},
	{"label": "NITKU", "fieldname": "buyer_nitku", "fieldtype": "Data", "width": 170},
	{"label": "Kode Trx", "fieldname": "trx_code", "fieldtype": "Data", "width": 70},
	{"label": "DPP", "fieldname": "dpp", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
	{"label": "DPP Nilai Lain", "fieldname": "dpp_other", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 130},
	{"label": "PPN", "fieldname": "ppn", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
	{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 320},
]


def execute(filters=None):
	filters = filters or {}
	if not (filters.get("company") and filters.get("from_date") and filters.get("to_date")):
		return COLUMNS, []

	company, _vat_rate, entries = collect(filters)
	data = []
	for e in entries:
		si = e["si"]
		data.append(
			{
				"invoice": si.name,
				"company": company.name,
				"posting_date": si.posting_date,
				"customer_name": si.customer_name,
				"buyer_tin": si.tax_id,
				"buyer_nitku": frappe.db.get_value("Customer", si.customer, "custom_nitku"),
				"trx_code": si.get("custom_coretax_trx_code"),
				"dpp": e["dpp"],
				"dpp_other": sum(r["other"] for r in e["rows"]),
				"ppn": e["ppn"],
				"status": "Siap" if not e["missing"] else "Kurang: " + ", ".join(e["missing"]),
			}
		)
	return COLUMNS, data

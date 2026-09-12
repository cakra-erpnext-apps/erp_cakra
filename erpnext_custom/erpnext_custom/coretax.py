"""Export faktur pajak keluaran ke XML impor Coretax DJP.

Skema mengikuti template RESMI DJP "Sample Faktur PK Template v.1.4.xml"
(https://www.pajak.go.id/en/node/112031): TaxInvoiceBulk > TIN + ListOfTaxInvoice >
TaxInvoice > ListOfGoodService > GoodService. DJP sudah beberapa kali merevisi skema
ini, jadi sebelum dipakai massal cocokkan lagi versinya di halaman itu -- kalau berubah,
yang diubah cukup _invoice_xml()/_item_xml() di bawah.

Nomor faktur (NSFP) TIDAK dikirim di sini: Coretax yang memberikannya saat file ini
diimpor dan ditandatangani.
"""

import json
from xml.sax.saxutils import escape

import frappe
from frappe.utils import flt, getdate

# Tarif yang dianggap baris PPN di tabel taxes. Baris PPh bertarif lain (dan negatif),
# jadi tidak ikut terbawa.
PPN_RATES = (10, 11, 12)

CUSTOM_FIELDS = {
	"Company": [
		{
			"fieldname": "custom_nitku",
			"fieldtype": "Data",
			"label": "NITKU",
			"insert_after": "tax_id",
			"module": "ERPNext Custom",
			"description": "22 digit. Dipakai sebagai SellerIDTKU saat export XML Coretax.",
		}
	],
	"Customer": [
		{
			"fieldname": "custom_nitku",
			"fieldtype": "Data",
			"label": "NITKU",
			"insert_after": "tax_id",
			"module": "ERPNext Custom",
			"description": "22 digit. Dipakai sebagai BuyerIDTKU saat export XML Coretax.",
		}
	],
	"Sales Invoice": [
		{
			"fieldname": "custom_coretax_trx_code",
			"fieldtype": "Data",
			"label": "Kode Transaksi Coretax",
			"insert_after": "tax_id",
			"default": "01",
			"module": "ERPNext Custom",
			"description": "2 digit, mis. 01 umum, 02 bendahara, 07 tidak dipungut, 08 dibebaskan.",
		}
	],
	"Item": [
		{
			"fieldname": "custom_coretax_code",
			"fieldtype": "Data",
			"label": "Kode Barang/Jasa Coretax",
			"insert_after": "item_group",
			"default": "000000",
			"module": "ERPNext Custom",
		}
	],
	"UOM": [
		{
			"fieldname": "custom_coretax_unit",
			"fieldtype": "Data",
			"label": "Kode Satuan Coretax",
			"insert_after": "uom_name",
			"module": "ERPNext Custom",
			"description": "Kode UM.xxxx sesuai daftar satuan Coretax, mis. UM.0018 untuk Piece.",
		}
	],
}


def ensure_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def _digits(value):
	return "".join(c for c in str(value or "") if c.isdigit())


def _num(value):
	"""Rupiah: bulat kalau memang bulat, kalau tidak dua desimal."""
	value = flt(value, 2)
	return str(int(value)) if value == int(value) else f"{value:.2f}"


def _ppn_per_item(si):
	"""item_code -> PPN dalam mata uang invoice, dari item_wise_tax_detail baris PPN."""
	out = {}
	for tax in si.taxes:
		if flt(tax.rate) <= 0 or round(flt(tax.rate)) not in PPN_RATES:
			continue
		try:
			detail = json.loads(tax.item_wise_tax_detail or "{}")
		except ValueError:
			continue
		for code, val in detail.items():
			amount = val[1] if isinstance(val, (list, tuple)) and len(val) > 1 else 0
			out[code] = out.get(code, 0) + flt(amount)
	return out


def _rows(si, vat_rate):
	"""Baris GoodService + DPP/PPN per item, dalam rupiah."""
	ppn = _ppn_per_item(si)
	kurs = flt(si.conversion_rate) or 1
	# item_wise_tax_detail menggabung item yang sama; dibagi lagi menurut porsi nilainya
	total_per_code = {}
	for it in si.items:
		total_per_code[it.item_code] = total_per_code.get(it.item_code, 0) + flt(it.base_net_amount)

	rows = []
	for it in si.items:
		base = flt(it.base_net_amount)
		total = total_per_code.get(it.item_code) or 0
		share = base / total if total else 0
		vat = flt(ppn.get(it.item_code, 0)) * kurs * share
		# DPP Nilai Lain diturunkan dari PPN yang BENAR-BENAR ditagih, jadi otomatis jadi
		# 11/12 x DPP kalau invoice memungut 11% tapi dilaporkan dengan tarif 12%.
		other = vat * 100 / vat_rate if vat_rate else base
		rows.append({"item": it, "base": base, "vat": vat, "other": other})
	return rows


def _missing(si, company, rows):
	"""Data master yang belum terisi. Invoice tidak ikut diexport sampai ini beres."""
	miss = []
	if not _digits(company.tax_id):
		miss.append("NPWP perusahaan")
	if not _digits(company.get("custom_nitku")):
		miss.append("NITKU perusahaan")
	if not _digits(si.tax_id):
		miss.append("NPWP pembeli")
	if not _digits(frappe.db.get_value("Customer", si.customer, "custom_nitku")):
		miss.append("NITKU pembeli")
	if not (si.get("custom_coretax_trx_code") or "").strip():
		miss.append("kode transaksi")
	if not sum(r["vat"] for r in rows):
		miss.append("baris PPN")
	for r in rows:
		if not frappe.db.get_value("UOM", r["item"].uom, "custom_coretax_unit"):
			miss.append(f"satuan {r['item'].uom}")
			break
	return miss


def collect(filters):
	"""Invoice pada masa pajak ini + status kelengkapannya."""
	filters = frappe._dict(filters or {})
	vat_rate = flt(filters.vat_rate) or 12
	company = frappe.get_doc("Company", filters.company)

	names = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"company": filters.company,
			"is_return": 0,
			"posting_date": ("between", [getdate(filters.from_date), getdate(filters.to_date)]),
		},
		order_by="posting_date, name",
		pluck="name",
	)

	out = []
	for name in names:
		si = frappe.get_doc("Sales Invoice", name)
		rows = _rows(si, vat_rate)
		out.append(
			{
				"si": si,
				"rows": rows,
				"missing": _missing(si, company, rows),
				"dpp": sum(r["base"] for r in rows),
				"ppn": sum(r["vat"] for r in rows),
			}
		)
	return company, vat_rate, out


def _item_xml(row, vat_rate):
	it = row["item"]
	unit = frappe.db.get_value("UOM", it.uom, "custom_coretax_unit") or ""
	code = frappe.db.get_value("Item", it.item_code, "custom_coretax_code") or "000000"
	is_stock = frappe.db.get_value("Item", it.item_code, "is_stock_item")
	fields = [
		("Opt", "A" if is_stock else "B"),
		("Code", code),
		("Name", it.item_name),
		("Unit", unit),
		# rate ERPNext sudah bersih diskon, jadi TotalDiscount 0 dan Price x Qty = TaxBase
		("Price", _num(flt(it.base_net_rate))),
		("Qty", _num(flt(it.qty))),
		("TotalDiscount", "0"),
		("TaxBase", _num(row["base"])),
		("OtherTaxBase", _num(row["other"])),
		("VATRate", _num(vat_rate)),
		("VAT", _num(row["vat"])),
		("STLGRate", "0"),
		("STLG", "0"),
	]
	inner = "".join("\n\t\t\t\t\t<%s>%s</%s>" % (k, escape(str(v)), k) for k, v in fields)
	return "\n\t\t\t\t<GoodService>%s\n\t\t\t\t</GoodService>" % inner


def _invoice_xml(entry, company, vat_rate):
	si = entry["si"]
	buyer_nitku = frappe.db.get_value("Customer", si.customer, "custom_nitku") or ""
	fields = [
		("TaxInvoiceDate", str(getdate(si.posting_date))),
		("TaxInvoiceOpt", "Normal"),
		("TrxCode", (si.get("custom_coretax_trx_code") or "").strip()),
		("AddInfo", ""),
		("CustomDoc", ""),
		("CustomDocMonthYear", ""),
		("RefDesc", si.name),
		("FacilityStamp", ""),
		("SellerIDTKU", _digits(company.get("custom_nitku"))),
		("BuyerTin", _digits(si.tax_id)),
		("BuyerDocument", "TIN"),
		("BuyerCountry", "IND"),
		("BuyerDocumentNumber", ""),
		("BuyerName", si.customer_name),
		("BuyerAdress", (si.address_display or "").replace("<br>", " ").strip()),
		("BuyerEmail", si.contact_email or ""),
		("BuyerIDTKU", _digits(buyer_nitku)),
	]
	head = "".join("\n\t\t\t<%s>%s</%s>" % (k, escape(str(v)), k) for k, v in fields)
	items = "".join(_item_xml(r, vat_rate) for r in entry["rows"])
	return "\n\t\t<TaxInvoice>%s\n\t\t\t<ListOfGoodService>%s\n\t\t\t</ListOfGoodService>\n\t\t</TaxInvoice>" % (
		head,
		items,
	)


def build_xml(filters):
	company, vat_rate, entries = collect(filters)
	siap = [e for e in entries if not e["missing"]]
	if not siap:
		frappe.throw(frappe._("Tidak ada faktur yang siap diexport pada periode ini."))
	body = "".join(_invoice_xml(e, company, vat_rate) for e in siap)
	xml = (
		'<?xml version="1.0" encoding="utf-8" ?>\n'
		'<TaxInvoiceBulk xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xsi:noNamespaceSchemaLocation="TaxInvoice.xsd">\n'
		"\t<TIN>%s</TIN>\n"
		"\t<ListOfTaxInvoice>%s\n\t</ListOfTaxInvoice>\n"
		"</TaxInvoiceBulk>\n"
	) % (_digits(company.tax_id), body)
	return xml, len(siap), len(entries) - len(siap)


@frappe.whitelist()
def export_xml(filters):
	if isinstance(filters, str):
		filters = json.loads(filters)
	frappe.has_permission("Sales Invoice", throw=True)
	xml, ok, skipped = build_xml(filters)
	stamp = "%s_%s" % (
		getdate(filters["from_date"]).strftime("%Y%m%d"),
		getdate(filters["to_date"]).strftime("%Y%m%d"),
	)
	return {"filename": "FakturKeluaran_%s.xml" % stamp, "xml": xml, "ok": ok, "skipped": skipped}

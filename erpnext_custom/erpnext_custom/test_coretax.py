"""Cek export XML Coretax: susunan tag HARUS sama persis dengan template resmi DJP,
dan DPP Nilai Lain harus jatuh di 11/12 x DPP saat invoice memungut 11% tapi dilaporkan
bertarif 12%. Tidak menyentuh data -- semua dokumennya karangan.

    bench --site erp.localhost console
    >>> from erpnext_custom.test_coretax import run; run()
"""

import xml.etree.ElementTree as ET
from types import SimpleNamespace

import frappe

from erpnext_custom.coretax import _invoice_xml, _rows

# Urutan tag pada "Sample Faktur PK Template v.1.4.xml" (pajak.go.id/en/node/112031).
# Kalau DJP merevisi skemanya, di sinilah ketahuannya.
TAX_INVOICE_TAGS = [
	"TaxInvoiceDate",
	"TaxInvoiceOpt",
	"TrxCode",
	"AddInfo",
	"CustomDoc",
	"CustomDocMonthYear",
	"RefDesc",
	"FacilityStamp",
	"SellerIDTKU",
	"BuyerTin",
	"BuyerDocument",
	"BuyerCountry",
	"BuyerDocumentNumber",
	"BuyerName",
	"BuyerAdress",
	"BuyerEmail",
	"BuyerIDTKU",
	"ListOfGoodService",
]

GOOD_SERVICE_TAGS = [
	"Opt",
	"Code",
	"Name",
	"Unit",
	"Price",
	"Qty",
	"TotalDiscount",
	"TaxBase",
	"OtherTaxBase",
	"VATRate",
	"VAT",
	"STLGRate",
	"STLG",
]


class _Doc(SimpleNamespace):
	"""Pengganti Document. Bukan frappe._dict: `si.items` di _dict malah kena method
	dict.items(), bukan tabel itemnya."""

	def get(self, key, default=None):
		return getattr(self, key, default)


def _fake_invoice(vat_amount):
	"""Invoice 1 baris: DPP 1.000.000, PPN sebesar vat_amount."""
	return _Doc(
		name="SI-TEST-0001",
		posting_date="2026-09-30",
		customer="CUST-TEST",
		customer_name="PT Contoh",
		tax_id="0012345678901234",
		address_display="Jl. Contoh No. 1<br>Jakarta",
		contact_email="a@contoh.id",
		conversion_rate=1,
		custom_coretax_trx_code="01",
		items=[
			frappe._dict(
				item_code="ITEM-TEST",
				item_name="Barang Contoh",
				uom="Unit",
				qty=1,
				base_net_rate=1_000_000,
				base_net_amount=1_000_000,
			)
		],
		taxes=[
			frappe._dict(
				rate=11,
				item_wise_tax_detail=frappe.as_json({"ITEM-TEST": [11, vat_amount]}),
			)
		],
	)


def run(verbose=True):
	si = _fake_invoice(110_000)
	rows = _rows(si, vat_rate=12)
	entry = {"si": si, "rows": rows}
	company = _Doc(name="PT Test", tax_id="0011223344556677", custom_nitku="0011223344556677000000")

	xml = _invoice_xml(entry, company, vat_rate=12)
	inv = ET.fromstring(xml)

	assert [c.tag for c in inv] == TAX_INVOICE_TAGS, [c.tag for c in inv]
	good = inv.find("ListOfGoodService").find("GoodService")
	assert [c.tag for c in good] == GOOD_SERVICE_TAGS, [c.tag for c in good]

	# PPN 11% dilaporkan bertarif 12% -> DPP Nilai Lain = 11/12 x DPP, PPN tetap utuh
	assert good.findtext("TaxBase") == "1000000", good.findtext("TaxBase")
	assert good.findtext("OtherTaxBase") == "916666.67", good.findtext("OtherTaxBase")
	assert good.findtext("VATRate") == "12"
	assert good.findtext("VAT") == "110000"
	# NPWP/NITKU selalu angka saja, pemisahnya dibuang
	assert inv.findtext("BuyerTin") == "0012345678901234"
	assert inv.findtext("SellerIDTKU") == "0011223344556677000000"

	# Invoice yang memang memungut 12% tidak digeser: DPP Nilai Lain = DPP
	rows12 = _rows(_fake_invoice(120_000), vat_rate=12)
	assert round(rows12[0]["other"]) == 1_000_000, rows12[0]["other"]

	if verbose:
		print(xml)
	print("OK")

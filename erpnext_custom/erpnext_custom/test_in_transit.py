"""Cek penjualan mode In Transit (in_transit.py). Semua dokumen di-rollback.

bench --site erp.localhost execute erpnext_custom.test_in_transit.run
"""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice as so_to_si
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice, make_sales_return
from frappe.utils import flt, nowdate

COMPANY = "PT CMI"
TRANSIT = "1130.006 - Persediaan In Transit - PC"


def _gl(doc):
	rows = frappe.get_all("GL Entry", filters={"voucher_no": doc.name, "is_cancelled": 0},
	                      fields=["account", "debit", "credit"])
	out = {}
	for r in rows:
		out[r.account] = flt(out.get(r.account, 0) + r.debit - r.credit, 2)
	return out


def _dn(customer, item, warehouse, qty):
	dn = frappe.get_doc({"doctype": "Delivery Note", "company": COMPANY, "customer": customer,
	                     "posting_date": nowdate(),
	                     "items": [{"item_code": item, "qty": qty, "rate": 1000, "warehouse": warehouse}]})
	dn.insert()
	dn.submit()
	return dn


def _submit_si(si):
	si.update({"custom_invoice_type": "Trading", "custom_invoice_type_no": "C/T", "invoice_date": nowdate()})
	si.insert()
	si.flags.cmi_action_ok = True
	si.submit()
	return si


def run(customer="PT Tunggul Persada", item="Glycerin", warehouse="Gudang Jakarta - CMI"):
	frappe.set_user("Administrator")
	frappe.db.set_value("Company", COMPANY, "custom_in_transit_account", TRANSIT)
	frappe.clear_cache(doctype="Company")
	try:
		# 1. Delivery Note: Dr In Transit / Cr Persediaan, tanpa HPP.
		dn = _dn(customer, item, warehouse, 10)
		g = _gl(dn)
		value = g.get(TRANSIT)
		assert value and value > 0, g
		assert len(g) == 2 and round(sum(g.values()), 2) == 0, g

		# 2. Invoice sebagian (4 dari 10): Dr HPP / Cr In Transit = 4/10 nilai DN.
		si = make_sales_invoice(dn.name)
		si.items[0].qty = 4
		si = _submit_si(si)
		g = _gl(si)
		assert g.get(TRANSIT) == -flt(value * 0.4, 2), (g, value)
		hpp = [a for a, v in g.items() if v == flt(value * 0.4, 2)]
		assert hpp, g

		# 3. Sisa 6 ditagih: In Transit untuk DN ini habis.
		si2 = _submit_si(make_sales_invoice(dn.name))
		assert round(value + _gl(si).get(TRANSIT) + _gl(si2).get(TRANSIT), 2) == 0

		# 4. Retur 2 + Credit Note-nya: In Transit kembali nol, HPP dibalik.
		ret = make_sales_return(dn.name)
		ret.items[0].qty = -2
		ret.insert()
		ret.submit()
		g_ret = _gl(ret)
		assert g_ret.get(TRANSIT) < 0, g_ret
		cn = make_sales_invoice(ret.name)
		cn = _submit_si(cn)
		assert round(g_ret.get(TRANSIT) + _gl(cn).get(TRANSIT), 2) == 0, (g_ret, _gl(cn))

		# 5. Pengaman: invoice barang stok tanpa DN dan tanpa Update Stock ditolak.
		so = frappe.get_doc({"doctype": "Sales Order", "company": COMPANY, "customer": customer,
		                     "transaction_date": nowdate(), "delivery_date": nowdate(),
		                     "items": [{"item_code": item, "qty": 1, "rate": 1000, "warehouse": warehouse}]})
		so.insert()
		so.flags.cmi_action_ok = True
		so.submit()
		try:
			_submit_si(so_to_si(so.name))
			raise AssertionError("invoice tanpa DN seharusnya ditolak")
		except frappe.ValidationError as e:
			assert "Delivery Note" in str(e), e

		print(f"OK: DN {value:,.2f} ke In Transit, invoice sebagian/sisa/retur seimbang, pengaman jalan")
	finally:
		frappe.db.rollback()
		frappe.set_user("Administrator")

"""Penjualan barang ala Ascend: HPP diakui saat INVOICE, bukan saat barang keluar.

Ascend (data AS_CAKRA, mis. SJ/1720 + C/T/1617):
  Surat Jalan  : Dr Persediaan In Transit / Cr Persediaan
  Invoice      : Dr Piutang, Dr HPP / Cr Persediaan In Transit, Cr PPN, Cr Penjualan

Di sini:
  Delivery Note: baris item stok memakai akun In Transit sebagai "expense account",
                 jadi ERPNext sendiri yang menulis Dr In Transit / Cr Persediaan.
  Sales Invoice: tiap baris yang ditarik dari DN mode ini menambah Dr HPP / Cr In Transit
                 senilai stok DN-nya (proporsional qty yang ditagih). Credit Note dari DN
                 retur membalik arahnya sendiri karena qty-nya negatif.

Aktif per company lewat Company.custom_in_transit_account; kosong = perilaku lama
(HPP saat Delivery Note). DN lama yang sudah membukukan HPP tidak disentuh: invoice
hanya menambah baris untuk DN yang barisnya memang memakai akun In Transit.
"""

import frappe
from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from frappe import _
from frappe.utils import flt

from erpnext_custom.item_scope import item_account


def transit_account(company):
	return frappe.get_cached_value("Company", company, "custom_in_transit_account") if company else None


def cogs_account(item_code, company):
	"""HPP item: Default COGS -> Default Expense (Item lalu Item Group) -> default Company."""
	return (item_account(item_code, company, "default_cogs_account")
	        or item_account(item_code, company, "expense_account")
	        or frappe.get_cached_value("Company", company, "default_expense_account"))


def set_delivery_note_accounts(doc):
	"""Dipanggil dari delivery_note.before_validate. True kalau mode In Transit aktif."""
	account = transit_account(doc.company)
	if not account:
		return False
	for row in doc.get("items"):
		if row.item_code and frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			row.expense_account = account
	return True


class CMIDeliveryNote(DeliveryNote):
	def check_expense_account(self, item):
		# Core menolak akun non laba-rugi di DN; akun In Transit company ini sengaja neraca.
		if item.get("expense_account") and item.expense_account == transit_account(self.company):
			return
		return super().check_expense_account(item)


def _dn_unit_values(dn_details):
	"""{dn_detail: nilai stok per satuan stok} dari Stock Ledger DN (selalu positif)."""
	if not dn_details:
		return {}
	qty, value = {}, {}
	for r in frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": "Delivery Note", "voucher_detail_no": ["in", list(dn_details)],
		         "is_cancelled": 0},
		fields=["voucher_detail_no", "actual_qty", "stock_value_difference"],
	):
		qty[r.voucher_detail_no] = qty.get(r.voucher_detail_no, 0) + flt(r.actual_qty)
		value[r.voucher_detail_no] = value.get(r.voucher_detail_no, 0) + flt(r.stock_value_difference)
	return {d: abs(value[d] / q) for d, q in qty.items() if q}


def sales_invoice_gl_entries(doc):
	"""Baris tambahan Dr HPP / Cr In Transit untuk Sales Invoice (tanpa Update Stock)."""
	account = transit_account(doc.company)
	if not account or doc.get("update_stock"):
		return []
	rows = [r for r in doc.get("items") if r.get("dn_detail")]
	if not rows:
		return []
	dn_accounts = dict(frappe.get_all(
		"Delivery Note Item", filters={"name": ["in", [r.dn_detail for r in rows]]},
		fields=["name", "expense_account"], as_list=True))
	rows = [r for r in rows if dn_accounts.get(r.dn_detail) == account]
	unit = _dn_unit_values({r.dn_detail for r in rows})
	precision = frappe.get_precision("GL Entry", "debit")
	gl = []
	for r in rows:
		# qty negatif (Credit Note dari DN retur) -> arah terbalik dengan sendirinya.
		amount = flt(unit.get(r.dn_detail, 0) * flt(r.stock_qty), precision)
		if not amount:
			continue
		hpp = cogs_account(r.item_code, doc.company)
		dr, cr = (hpp, account) if amount > 0 else (account, hpp)
		for acc, against, side in ((dr, cr, "debit"), (cr, dr, "credit")):
			gl.append(doc.get_gl_dict({
				"account": acc,
				"against": against,
				side: abs(amount),
				side + "_in_account_currency": abs(amount),
				"cost_center": r.cost_center,
				"remarks": _("HPP {0} dari {1}").format(r.item_code, r.delivery_note),
			}, item=r))
	return gl


def guard_stock_rows(doc):
	"""Barang stok di invoice harus lewat Delivery Note atau Update Stock, kalau tidak HPP
	dan stoknya tidak pernah tercatat. Credit Note dikecualikan (bisa sekadar potongan harga)."""
	if doc.docstatus != 1 or doc.get("update_stock") or doc.get("is_return"):
		return
	bad = [r for r in doc.get("items")
	       if r.item_code and not r.get("dn_detail")
	       and frappe.get_cached_value("Item", r.item_code, "is_stock_item")]
	if bad:
		frappe.throw(_(
			"Baris {0}: barang stok harus ditagih dari Delivery Note, atau centang Update Stock. "
			"Tanpa itu stok dan HPP-nya tidak pernah tercatat."
		).format(", ".join(str(r.idx) for r in bad)))

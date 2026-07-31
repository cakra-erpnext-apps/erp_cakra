"""Shared smart amounts for Sales Order and Delivery Note."""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_custom.overrides.sales_invoice import _apply_smart_inputs

TAX_DESC = "CMI: Tax"
PPH_DESC = "CMI: PPh"
MATERAI_DESC = "CMI: Materai"
CMI_DESCRIPTIONS = (TAX_DESC, PPH_DESC, MATERAI_DESC)


def _need(account, label):
	if not account:
		frappe.throw(_("Set akun '{0}' (bagian Sales) di ERPNext Custom Setting.").format(label))
	return account


def inject(doc):
	"""Map smart inputs into native discount and Sales Taxes and Charges."""
	_apply_smart_inputs(doc)
	doc.apply_discount_on = "Net Total"
	if flt(doc.get("custom_discount_percent")):
		doc.additional_discount_percentage = flt(doc.custom_discount_percent)
		doc.discount_amount = 0
	else:
		doc.additional_discount_percentage = 0
		doc.discount_amount = flt(doc.get("custom_discount_amount"))

	settings = frappe.get_cached_doc("ERPNext Custom Setting")
	kept = [
		row for row in (doc.get("taxes") or [])
		if (row.get("description") or "") not in CMI_DESCRIPTIONS
	]
	doc.set("taxes", kept)

	def add_percent(account, description, percent, sign=1):
		doc.append("taxes", {
			"charge_type": "On Net Total",
			"account_head": account,
			"description": description,
			"rate": sign * abs(flt(percent)),
		})

	def add_amount(account, description, amount, sign=1):
		doc.append("taxes", {
			"charge_type": "Actual",
			"account_head": account,
			"description": description,
			"rate": 0,
			"tax_amount": sign * abs(flt(amount)),
		})

	if not doc.get("custom_ignore_tax"):
		if flt(doc.get("custom_tax_percent")):
			add_percent(_need(settings.sales_tax_account, "Tax (PPN)"), TAX_DESC, doc.custom_tax_percent)
		elif flt(doc.get("custom_tax_amount")):
			add_amount(_need(settings.sales_tax_account, "Tax (PPN)"), TAX_DESC, doc.custom_tax_amount)

	if flt(doc.get("custom_pph_percent")):
		add_percent(_need(settings.pph23_account, "PPh 23"), PPH_DESC, doc.custom_pph_percent, -1)
	elif flt(doc.get("custom_pph_amount")):
		add_amount(_need(settings.pph23_account, "PPh 23"), PPH_DESC, doc.custom_pph_amount, -1)

	if flt(doc.get("custom_materai")):
		add_amount(_need(settings.materai_account, "Materai"), MATERAI_DESC, doc.custom_materai)


def compute_display(doc):
	total = flt(doc.get("total"))
	if flt(doc.get("custom_discount_percent")):
		doc.custom_discount_amount = total * flt(doc.custom_discount_percent) / 100
	discount = flt(doc.get("custom_discount_amount"))
	dpp = total - discount

	if doc.get("custom_ignore_tax"):
		doc.custom_tax_amount = 0
	elif flt(doc.get("custom_tax_percent")):
		doc.custom_tax_amount = dpp * flt(doc.custom_tax_percent) / 100

	if flt(doc.get("custom_pph_percent")):
		doc.custom_pph_amount = dpp * flt(doc.custom_pph_percent) / 100

	doc.custom_amount_total = total
	doc.custom_net_total = flt(doc.get("grand_total"))

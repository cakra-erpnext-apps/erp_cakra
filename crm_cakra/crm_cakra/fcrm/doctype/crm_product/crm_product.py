# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component import FIXED, resolve


class CRMProduct(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.TextEditor | None
		disabled: DF.Check
		image: DF.AttachImage | None
		naming_series: DF.Literal["CRM-PROD-.YYYY.-"]
		product_code: DF.Data
		product_name: DF.Data | None
		standard_rate: DF.Currency
	# end: auto-generated types

	def validate(self):
		self.set_product_name()
		# Fixed cost per hari = jumlah total komponen bertipe Fixed Cost. Angka
		# inilah yang ditarik costing quotation lalu dikali Duration (Day) tiap
		# baris produk. Komponen Variable Cost tidak dijumlah di sini -- itu
		# template, angkanya baru berarti setelah disalin ke quotation dan
		# disesuaikan Procurement.
		self.fixed_cost_per_day = sum(
			(c.total_amount or 0) for c in resolve(self.cost_components, FIXED)
		)

	def set_product_name(self):
		if not self.product_name:
			self.product_name = self.product_code
		else:
			self.product_name = self.product_name.strip()

	@staticmethod
	def default_list_data():
		columns = [
			{"label": "Product Code", "type": "Data", "key": "name", "width": "12rem"},
			{"label": "Product Name", "type": "Data", "key": "product_name", "width": "18rem"},
			{"label": "Standard Rate", "type": "Currency", "key": "standard_rate", "width": "10rem"},
			{"label": "Cost Components", "type": "Data", "key": "cost_components", "width": "20rem"},
			{"label": "Disabled", "type": "Check", "key": "disabled", "width": "6rem"},
			{"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
		]
		rows = [
			"name",
			"product_code",
			"product_name",
			"standard_rate",
			"cost_components",
			"disabled",
			"modified",
		]
		return {"columns": columns, "rows": rows}

	@staticmethod
	def parse_list_data(products):
		# cost_components itu Table MultiSelect -- get_list diam-diam melewatinya
		# (bukan kolom di tabel induk), jadi isinya ditempel di sini.
		if not products:
			return products

		links = frappe.get_all(
			"CRM Cost Component Link",
			filters={"parenttype": "CRM Product", "parent": ["in", [p.name for p in products]]},
			fields=["parent", "cost_component"],
			order_by="idx asc",
		)
		by_product = {}
		for link in links:
			by_product.setdefault(link.parent, []).append(link.cost_component)

		for product in products:
			product["cost_components"] = ", ".join(by_product.get(product.name, []))
		return products

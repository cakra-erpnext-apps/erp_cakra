# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


def _component(name, cost_type, items):
	if not frappe.db.exists("CRM Cost Component", name):
		frappe.get_doc(
			{
				"doctype": "CRM Cost Component",
				"component_name": name,
				"type": cost_type,
				"items": items,
			}
		).insert(ignore_permissions=True)
	return name


class IntegrationTestCRMQuotation(IntegrationTestCase):
	"""
	Integration tests for CRMQuotation.
	Use this class for testing interactions between multiple components.
	"""

	def test_costing_base_price(self):
		"""Base Price = (fixed/day x duration) + variable + margin.

		Sekaligus menjaga aturan yang gampang hilang saat kode dirapikan: rincian
		komponen Variable Cost tersalin sekali, baris tanpa costing tidak
		dinolkan, dan biaya milik baris produk yang dihapus ikut terbuang.
		"""
		armada = _component(
			"_TEST Armada Tetap",
			"Fixed Cost",
			[
				{"item_name": "Penyusutan armada", "qty": 1, "rate": 300000},
				{"item_name": "Gaji driver", "qty": 1, "rate": 200000},
			],
		)
		jalan = _component(
			"_TEST Biaya Jalan",
			"Variable Cost",
			[
				{"item_name": "BBM", "qty": 3, "rate": 250000},
				{"item_name": "Tol", "qty": 1, "rate": 150000},
			],
		)

		code = "_TEST_COSTING_PRODUCT"
		if not frappe.db.exists("CRM Product", code):
			frappe.get_doc(
				{
					"doctype": "CRM Product",
					"product_code": code,
					"cost_components": [{"cost_component": armada}, {"cost_component": jalan}],
				}
			).insert(ignore_permissions=True)
		# Hanya komponen Fixed Cost yang masuk biaya tetap per hari.
		self.assertEqual(frappe.db.get_value("CRM Product", code, "fixed_cost_per_day"), 500000)

		quo = frappe.new_doc("CRM Quotation")
		quo.append("products", {"product_code": code, "qty": 1, "duration": 2, "margin_percent": 10})
		quo.append("products", {"product_code": None, "qty": 1, "procurement_price": 777})
		quo.calculate_costing()

		# Rincian komponen Variable tersalin: BBM 750rb + Tol 150rb = 900rb.
		# Fixed 500rb x 2 hari = 1jt. Margin 10% dari 1,9jt = 190rb.
		row = quo.products[0]
		self.assertEqual(len(quo.cost_items), 2)
		self.assertEqual(quo.cost_items[0].source_component, jalan)
		self.assertEqual(row.fixed_cost, 1000000)
		self.assertEqual(row.variable_cost, 900000)
		self.assertEqual(row.procurement_price, 2090000)

		# Baris 2 tanpa costing sama sekali -> harga manualnya tidak diutak-atik.
		self.assertEqual(quo.products[1].procurement_price, 777)

		# Save ulang tidak menyalin rincian untuk kedua kalinya.
		quo.calculate_costing()
		self.assertEqual(len(quo.cost_items), 2)

		# Procurement menghapus semua baris lalu save -> tidak muncul lagi.
		quo.set("cost_items", [])
		quo.calculate_costing()
		self.assertEqual(len(quo.cost_items), 0)
		self.assertEqual(row.procurement_price, 1100000)

		# Baris produknya dihapus -> baris biayanya ikut hilang, bukan jadi yatim.
		quo.append("cost_items", {"cost_key": row.cost_key, "item_name": "BBM", "qty": 1, "rate": 5000})
		quo.products.pop(0)
		quo.calculate_costing()
		self.assertEqual(len(quo.cost_items), 0)

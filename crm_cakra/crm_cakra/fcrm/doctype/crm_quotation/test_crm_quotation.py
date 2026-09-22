# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


def _item(name):
	"""Item ERPNext seadanya. `item_name` di CRM Cost Item kini Link ke Item, jadi
	nama karangan tidak lagi lolos validasi."""
	if not frappe.db.exists("Item", name):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": name,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": frappe.db.get_value("UOM", {}, "name"),
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _component(name, cost_type, items):
	"""Komponen siap pakai. Wajib Validated -- resolve() hanya menghitung yang itu."""
	if not frappe.db.exists("CRM Cost Component", name):
		doc = frappe.get_doc(
			{
				"doctype": "CRM Cost Component",
				"component_name": name,
				"type": cost_type,
				"items": items,
			}
		).insert(ignore_permissions=True)
		doc.db_set("status", "Validated")
		frappe.clear_document_cache("CRM Cost Component", doc.name)
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
				{"item_name": _item("_TEST Penyusutan armada"), "qty": 1, "rate": 300000},
				{"item_name": _item("_TEST Gaji driver"), "qty": 1, "rate": 200000},
			],
		)
		jalan = _component(
			"_TEST Biaya Jalan",
			"Variable Cost",
			[
				{"item_name": _item("_TEST BBM"), "qty": 3, "rate": 250000},
				{"item_name": _item("_TEST Tol"), "qty": 1, "rate": 150000},
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

		# Rincian komponen Variable tersalin: BBM 750rb + Tol 150rb = 900rb (bukan per hari).
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
		quo.append("cost_items", {"cost_key": row.cost_key, "item_name": _item("_TEST BBM"), "qty": 1, "rate": 5000})
		quo.products.pop(0)
		quo.calculate_costing()
		self.assertEqual(len(quo.cost_items), 0)

	def test_convert_to_estimation_carries_quotation_data(self):
		"""Convert -> Estimation membawa Branch, Expired Date, dan Fixed + Variable Cost.

		Tiga hal yang sebelumnya harus diketik ulang orang: Office quotation, ujung
		rentang Validity (Expired Date estimasi cuma satu tanggal, jadi ambil yang
		terakhir), dan kedua tabel biaya tab Procurement -> baris Expense.
		"""
		office = frappe.db.get_value("CMI Office", {}, "name")
		loc = frappe.get_all("Fleet Location", pluck="name", limit=2)
		quo = frappe.new_doc("CRM Quotation")
		quo.branch_office = office
		quo.loading, quo.unloading, quo.distance_km = loc[0], loc[-1], 100
		quo.validity_date = "2026-09-01"
		quo.validity_date_to = "2026-09-02"
		quo.append("products", {"product_code": None, "qty": 1, "amount": 5000})
		quo.flags.ignore_mandatory = True
		quo.insert(ignore_permissions=True)

		# Dua tabel datar per quotation, bukan per baris produk: satu baris = satu pos
		# biaya. Item yang sama muncul dua kali di Variable supaya tes ini gagal kalau
		# barisnya suatu hari digabung lagi -- menggabungkan berarti menghapus uang.
		quo.append(
			"fixed_cost_items",
			{"item_name": _item("_TEST Gaji driver"), "qty": 2, "uom": "Nos", "rate": 200000},
		)
		quo.append(
			"variable_cost_items",
			{"item_name": _item("_TEST BBM"), "qty": 3, "uom": "Nos", "rate": 250000},
		)
		quo.append(
			"variable_cost_items",
			{"item_name": _item("_TEST BBM"), "qty": 1, "uom": "Nos", "rate": 50000},
		)
		quo.save(ignore_permissions=True)
		quo.db_set("state", "Win")
		quo.reload()

		from crm_cakra.fcrm.doctype.crm_quotation.crm_quotation import convert_to_estimation

		est = frappe.get_doc("CRM Estimation", convert_to_estimation(quo.name))

		self.assertEqual(est.branch_office, office)
		# Rentang 01-02 Sept -> ambil ujung terakhirnya.
		self.assertEqual(str(est.expired_date), "2026-09-02")
		# Semua baris terbawa apa adanya, dan totalnya wajib sama dengan kotak Summary
		# quotation: expense estimasi yang meleset dari situ berarti uang hilang.
		self.assertEqual(len(est.expense_items), 3)
		self.assertEqual(
			sum(e.amount for e in est.expense_items),
			quo.total_fixed_cost + quo.total_variable_cost,
		)

	def test_price_floor_blocks_print_not_save(self):
		"""Harga di bawah Base Price: simpan tetap boleh, cetak yang ditolak.

		Menawar harga itu pekerjaan setengah jadi yang wajar; yang tidak boleh
		beredar adalah dokumen resminya.
		"""
		loc = frappe.get_all("Fleet Location", pluck="name", limit=2)
		quo = frappe.new_doc("CRM Quotation")
		quo.loading, quo.unloading, quo.distance_km = loc[0], loc[-1], 100
		quo.append(
			"products",
			{"product_code": None, "qty": 1, "price": 500, "procurement_price": 1000},
		)
		quo.flags.ignore_mandatory = True
		quo.insert(ignore_permissions=True)

		# Simpan kedua kalinya (bukan dokumen baru lagi) juga tidak ditolak.
		quo.save(ignore_permissions=True)
		self.assertEqual(quo.products[0].price, 500)

		with self.assertRaises(frappe.ValidationError):
			quo.run_method("before_print")

		quo.products[0].price = 1000
		quo.save(ignore_permissions=True)
		quo.run_method("before_print")

	def test_convert_keeps_product_without_matching_item(self):
		"""Produk CRM tanpa Item berkode sama tidak menggagalkan convert.

		Katalog CRM Product berdiri sendiri; kodenya jarang punya Item padanan.
		Yang dibawa ke baris Revenue adalah product_id, type_id dibiarkan kosong.
		"""
		code = "_TEST_NO_ITEM_PRODUCT"
		self.assertFalse(frappe.db.exists("Item", code))
		if not frappe.db.exists("CRM Product", code):
			frappe.get_doc({"doctype": "CRM Product", "product_code": code}).insert(
				ignore_permissions=True
			)

		loc = frappe.get_all("Fleet Location", pluck="name", limit=2)
		quo = frappe.new_doc("CRM Quotation")
		quo.loading, quo.unloading, quo.distance_km = loc[0], loc[-1], 100
		quo.append("products", {"product_code": code, "qty": 1, "amount": 5000})
		quo.flags.ignore_mandatory = True
		quo.insert(ignore_permissions=True)
		quo.db_set("state", "Win")
		quo.reload()

		from crm_cakra.fcrm.doctype.crm_quotation.crm_quotation import convert_to_estimation

		est = frappe.get_doc("CRM Estimation", convert_to_estimation(quo.name))
		self.assertEqual(est.revenue_items[0].product_id, code)
		self.assertFalse(est.revenue_items[0].type_id)

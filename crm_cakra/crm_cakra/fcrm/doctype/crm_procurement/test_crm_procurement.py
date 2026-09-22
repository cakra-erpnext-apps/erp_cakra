# Copyright (c) 2026, Cakra Mandiri Indonesia and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from crm_cakra.fcrm.doctype.crm_quotation.test_crm_quotation import _item

def _inquiry(net_total):
	inq = frappe.new_doc("CRM Inquiry")
	inq.subject = "_TEST Procurement"
	inq.net_total = net_total
	inq.flags.ignore_mandatory = True
	inq.insert(ignore_permissions=True)
	return inq


class IntegrationTestCRMProcurement(IntegrationTestCase):
	def test_costing_mirrors_to_inquiry_and_quotation(self):
		"""Jalur uangnya utuh: dua tabel -> total -> inquiry -> quotation.

		Tiga kaitan yang gampang putus tanpa terlihat: total dihitung dari baris
		(bukan dari kiriman browser), totalnya tercermin ke Fixed/Variable Cost di
		inquiry, dan quotation dari inquiry itu menyalin barisnya supaya
		summary_margin -- gerbang persetujuan margin -- tetap punya angka.
		"""
		inq = _inquiry(3_000_000)

		prc = frappe.new_doc("CRM Procurement")
		prc.inquiry = inq.name
		prc.append("fixed_cost_items", {"item_name": _item("_TEST Gaji driver"), "qty": 2, "rate": 200_000})
		prc.append("variable_cost_items", {"item_name": _item("_TEST BBM"), "qty": 3, "rate": 250_000})
		prc.insert(ignore_permissions=True)

		self.assertEqual(prc.total_fixed_cost, 400_000)
		self.assertEqual(prc.total_variable_cost, 750_000)
		self.assertEqual(prc.marketing_cost, 3_000_000)
		self.assertEqual(prc.margin, 1_850_000)

		# Inquiry ikut memegang angkanya (field "Fixed Cost" / "Variable Cost").
		self.assertEqual(frappe.db.get_value("CRM Inquiry", inq.name, "estimasi_tarif"), 400_000)
		self.assertEqual(frappe.db.get_value("CRM Inquiry", inq.name, "costing_procurement"), 750_000)

		# Satu inquiry satu dokumen procurement.
		dup = frappe.new_doc("CRM Procurement")
		dup.inquiry = inq.name
		self.assertRaises(frappe.UniqueValidationError, dup.insert, ignore_permissions=True)

		# Loading/Unloading/Branch dilempar validate() sendiri, jadi tidak ikut
		# dilewati ignore_mandatory.
		loc = frappe.get_all("Fleet Location", pluck="name", limit=2)
		quo = frappe.new_doc("CRM Quotation")
		quo.inquiry = inq.name
		quo.branch_office = frappe.db.get_value("CMI Office", {}, "name")
		quo.loading, quo.unloading, quo.distance_km = loc[0], loc[-1], 100
		quo.append("products", {"product_code": None, "qty": 1, "price": 3_000_000, "rate": 1})
		quo.flags.ignore_mandatory = True
		quo.insert(ignore_permissions=True)

		self.assertEqual(len(quo.fixed_cost_items), 1)
		self.assertEqual(len(quo.variable_cost_items), 1)
		self.assertEqual(quo.total_fixed_cost, 400_000)
		self.assertEqual(quo.total_variable_cost, 750_000)
		self.assertEqual(quo.summary_margin, 1_850_000)

		# Simpan lagi tidak menyalin untuk kedua kalinya -- kalau tidak, biaya
		# quotation menggelembung tiap kali dokumennya disentuh.
		quo.save(ignore_permissions=True)
		self.assertEqual(len(quo.fixed_cost_items), 1)

		# Biaya quotation beku: Procurement menaikkan rate, quotation tidak ikut.
		prc.variable_cost_items[0].rate = 400_000
		prc.save(ignore_permissions=True)
		quo.save(ignore_permissions=True)
		self.assertEqual(quo.total_variable_cost, 750_000)

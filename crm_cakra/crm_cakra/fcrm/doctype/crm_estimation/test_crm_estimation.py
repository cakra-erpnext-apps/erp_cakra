# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestCRMEstimation(IntegrationTestCase):
	"""
	Integration tests for CRMEstimation.
	Use this class for testing interactions between multiple components.
	"""

	def test_validate_invalidate_disable_roundtrip(self):
		"""Estimation lewat alur bulk di list view: Validate -> Invalidate -> Disable -> Enable.

		Yang dijaga di sini: cap validated_by ikut terisi/terhapus, dan total memakai
		amount x rate (rate 0 pada baris lama diperlakukan sebagai 1, kalau tidak seluruh
		estimasi lama akan berjumlah nol saat disimpan ulang).
		"""
		import erpnext_custom.workflow as workflow

		est = frappe.get_doc(
			{
				"doctype": "CRM Estimation",
				"purpose": "Customer",
				"estimation_type": "Expedition",
				"customer_id": frappe.db.get_value("Customer", {}, "name"),
				"expired_date": frappe.utils.add_days(frappe.utils.today(), 30),
				"revenue_items": [
					{"type_id": frappe.db.get_value("Item", {}, "name"), "csize": "20FT",
					 "status": "Per Doc", "amount": 1000, "rate": 0},
				],
			}
		).insert(ignore_permissions=True)
		# rate 0 -> dianggap 1, jadi total = amount apa adanya
		self.assertEqual(est.rev_inc_tax, 1000)
		self.assertEqual(est.revenue_items[0].rate, 1)
		self.assertEqual(est.revenue_items[0].currency, frappe.defaults.get_global_default("currency"))

		workflow.validate_doc("CRM Estimation", est.name)
		validated, by = frappe.db.get_value("CRM Estimation", est.name, ["validated", "validated_by"])
		self.assertEqual((validated, by), (1, frappe.session.user))

		workflow.invalidate_doc("CRM Estimation", est.name)
		validated, by = frappe.db.get_value("CRM Estimation", est.name, ["validated", "validated_by"])
		self.assertEqual((validated, by), (0, None))

		workflow.bulk_set_disabled("CRM Estimation", [est.name], 1)
		self.assertEqual(frappe.db.get_value("CRM Estimation", est.name, "disabled"), 1)
		# panggilan kedua: sudah pada keadaan itu -> tidak dihitung berhasil, tidak error
		self.assertEqual(workflow.bulk_set_disabled("CRM Estimation", [est.name], 1)["ok"], [])
		workflow.bulk_set_disabled("CRM Estimation", [est.name], 0)
		self.assertEqual(frappe.db.get_value("CRM Estimation", est.name, "disabled"), 0)

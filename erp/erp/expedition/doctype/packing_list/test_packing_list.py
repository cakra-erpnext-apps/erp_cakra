# Copyright (c) 2026, CMI and Contributors
# See license.txt

import frappe
from frappe.tests import UnitTestCase

from erp.expedition.doctype.packing_list.packing_list import summary


class UnitTestPackingList(UnitTestCase):
	def test_summary_shape(self):
		"""Tab Summary: query-nya jalan & angkanya konsisten.

		UnitTestCase (bukan Integration): tidak menyemai _Test Item dkk — site ini
		mewajibkan Item Category, jadi fixture bawaan ERPNext gagal dibuat. Diuji
		atas Packing List yang sudah ada (di-skip kalau situsnya kosong). Yang dijaga:
		nama field di semua doctype yang dibaca summary() masih ada, dan Net Total /
		Margin dihitung dari komponennya.
		"""
		names = frappe.get_all("Packing List", limit=1, pluck="name")
		if not names:
			self.skipTest("no Packing List on this site")
		d = summary(names[0])
		self.assertEqual(set(d), {"expenses", "reimburse", "invoices", "totals"})
		for row in d["expenses"]:
			self.assertAlmostEqual(row["net"], row["amount"] - row["discount"] + row["tax"], places=2)
		# Reimburse = himpunan bagian Expense yang dicentang reimburse.
		self.assertTrue(all(r["reimburse"] for r in d["reimburse"]))
		self.assertLessEqual(len(d["reimburse"]), len(d["expenses"]))
		t = d["totals"]
		self.assertAlmostEqual(t["margin"], t["invoice"] - t["expense"], places=2)

# Copyright (c) 2026, Cakra Mandiri Indonesia
"""Cek Expense Note Report.

Dua lapis: hitungan murni (net / status / bucket aging) dan eksekusi tiap view ke
database — yang terakhir menangkap SQL rusak, kolom hilang, dan escaping `%%`
di group by Month, tanpa perlu data Expense Note.
"""

import unittest

import frappe

from erp.expedition.report.expense_note_report.expense_note_report import (
	GROUP_BY,
	execute,
	_bucket,
	_net,
	_status,
)


class TestExpenseNoteReport(unittest.TestCase):
	def test_net_formula(self):
		row = frappe._dict(amount=1000, discount=100, tax=90, pph=20, materai=10)
		self.assertEqual(_net(row), 980)  # 1000 - 100 + 90 - 20 + 10

	def test_status_priority(self):
		void = frappe._dict(void=1, closed=1, paid=1, validated=1)
		self.assertEqual(_status(void), "Void")
		self.assertEqual(_status(frappe._dict(void=0, closed=1, paid=1, validated=1)), "Closed")
		self.assertEqual(_status(frappe._dict(void=0, closed=0, paid=1, validated=1)), "Paid")
		self.assertEqual(_status(frappe._dict(void=0, closed=0, paid=0, validated=1)), "Validated")
		self.assertEqual(_status(frappe._dict(void=0, closed=0, paid=0, validated=0)), "Draft")

	def test_status_from_payment(self):
		"""Status ikut alokasi PV: sebagian -> Partial, penuh (boleh dari >1 PV) -> Paid."""
		base = {"void": 0, "closed": 0, "paid": 0, "validated": 1, "net_base": 10_000_000}
		self.assertEqual(_status(frappe._dict(base, en_paid=0)), "Validated")
		self.assertEqual(_status(frappe._dict(base, en_paid=4_000_000)), "Half Paid")
		self.assertEqual(_status(frappe._dict(base, en_paid=9_999_999.999)), "Paid")  # sisa pembulatan
		self.assertEqual(_status(frappe._dict(base, en_paid=10_000_000)), "Paid")
		# EN belum divalidasi tapi entah bagaimana ada alokasi: tetap tampak terbayar sebagian
		self.assertEqual(_status(frappe._dict(base, validated=0, en_paid=1_000)), "Half Paid")

	def test_aging_buckets(self):
		self.assertEqual(_bucket(-5), "b_0_30")  # belum jatuh tempo
		self.assertEqual(_bucket(30), "b_0_30")
		self.assertEqual(_bucket(31), "b_31_60")
		self.assertEqual(_bucket(60), "b_31_60")
		self.assertEqual(_bucket(61), "b_61_90")
		self.assertEqual(_bucket(90), "b_61_90")
		self.assertEqual(_bucket(91), "b_90_plus")

	def test_every_view_runs(self):
		for view in ("Detail", "Summary", "Outstanding", "Per Job"):
			columns, rows = execute({"view": view, "from_date": "2000-01-01", "to_date": "2099-12-31"})
			self.assertTrue(columns, f"{view} tanpa kolom")
			self.assertIsInstance(rows, list)

	def test_every_group_by_runs(self):
		for dimension in GROUP_BY:
			columns, _rows = execute({"view": "Summary", "group_by": dimension})
			self.assertEqual(columns[0]["label"], dimension)

	def test_all_filters_at_once(self):
		"""Semua kondisi WHERE ikut terpasang sekaligus (termasuk status & packing list)."""
		_columns, rows = execute(
			{
				"view": "Detail",
				"company": "PT CMI",
				"from_date": "2024-01-01",
				"to_date": "2026-12-31",
				"vendor": "__none__",
				"expense_note_type": "__none__",
				"expense_class": "__none__",
				"cost_center": "__none__",
				"branch_office": "__none__",
				"shipping_list": "__none__",
				"packing_list": "__none__",
				"status": "Half Paid",
			}
		)
		self.assertEqual(rows, [])

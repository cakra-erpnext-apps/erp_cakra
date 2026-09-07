# Copyright (c) 2026, CMI and Contributors
# See license.txt

# import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]

_MOD = "erp.expedition.doctype.expense_note.expense_note"



class IntegrationTestExpenseNote(IntegrationTestCase):
	"""
	Integration tests for ExpenseNote.
	Use this class for testing interactions between multiple components.
	"""

	pass


class UnitTestExpenseNote(UnitTestCase):
	"""Helper murni (tanpa DB)."""

	def test_row_key_prefers_item_over_expense_class(self):
		"""Baris biaya baru berkunci Item; baris LAMA tetap jatuh ke Expense Class."""
		from erp.expedition.doctype.expense_note.expense_note import _row_key, _row_label

		self.assertEqual(_row_key({"item": "ITM-1", "expense_class": "CLS-1"}), "ITM-1")
		self.assertEqual(_row_key({"expense_class": "CLS-1"}), "CLS-1")
		self.assertEqual(_row_key({}), "")
		# Label untuk pesan error / remark jurnal: key -> description -> container -> "?"
		self.assertEqual(_row_label({"item": "ITM-1"}), "ITM-1")
		self.assertEqual(_row_label({"description": "biaya lain"}), "biaya lain")
		self.assertEqual(_row_label({"container_no": "CONT-1"}), "CONT-1")
		self.assertEqual(_row_label({}), "?")

	def test_estimation_label_per_doc_vs_by_qty(self):
		"""Per Doc dinilai dari akumulasi container; By Qty dinilai per container."""
		from erp.expedition.doctype.expense_note.expense_note import budget_left, estimation_label

		per_doc = {"amount": 100, "per_doc": True}
		by_qty = {"amount": 100, "per_doc": False}
		dua = {"C1": 60, "C2": 60}

		# Akumulasi 120 > 100 -> Melebihi, walau tiap container di bawah plafon.
		self.assertEqual(estimation_label(per_doc, dua), "Melebihi Estimation")
		# Plafon per container: 60 dan 60 dua-duanya <= 100 -> Sesuai.
		self.assertEqual(estimation_label(by_qty, dua), "Sesuai Estimation")
		# Satu container lewat sudah cukup untuk Melebihi.
		self.assertEqual(estimation_label(by_qty, {"C1": 60, "C2": 101}), "Melebihi Estimation")
		# Pas di plafon masih Sesuai (toleransi pembulatan).
		self.assertEqual(estimation_label(per_doc, {"C1": 100}), "Sesuai Estimation")
		self.assertEqual(estimation_label(by_qty, {"C1": 100}), "Sesuai Estimation")
		# Item tak ada di estimasi -> spec None.
		self.assertEqual(estimation_label(None, {"C1": 1}), "Di luar Estimation")

		# Sisa plafon (grup dropdown): Per Doc habis terpakai, By Qty selalu punya
		# jatah untuk container berikutnya.
		self.assertEqual(budget_left(per_doc, {"C1": 100}), 0)
		self.assertEqual(budget_left(per_doc, {"C1": 40}), 60)
		self.assertEqual(budget_left(by_qty, {"C1": 100, "C2": 100}), 100)

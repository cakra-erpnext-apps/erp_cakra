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

	def test_items_fit_estimation(self):
		"""Auto validate hanya kalau SEMUA baris Expense Item masih di dalam plafon."""
		import frappe
		from unittest.mock import patch

		from erp.expedition.doctype.expense_note.expense_note import items_fit_estimation

		doc = frappe._dict(name="EN-1", packing_list="PL-1", items=[
			frappe._dict(item="ITM-1", container_no="C1", amount=60),
			frappe._dict(item="ITM-1", container_no="C2", amount=30),
		])
		budget = {"PL-1": {"ITM-1": {"amount": 100, "per_doc": True}}}
		with patch(_MOD + "._pl_budget", return_value=budget):
			with patch(_MOD + "._pl_spent", return_value={}):
				self.assertTrue(items_fit_estimation(doc))
			# Realisasi Expense Note LAIN di PL yang sama ikut dihitung: 90 + 20 > 100.
			with patch(_MOD + "._pl_spent", return_value={"PL-1": {"ITM-1": {"C3": 20}}}):
				self.assertFalse(items_fit_estimation(doc))
			# Item tanpa plafon = "Di luar Estimation" -> jangan auto validate.
			with patch(_MOD + "._pl_budget", return_value={"PL-1": {}}):
				with patch(_MOD + "._pl_spent", return_value={}):
					self.assertFalse(items_fit_estimation(doc))
		# Tanpa baris item (mis. tipe Cost Items) tidak ada yang bisa dinilai.
		self.assertFalse(items_fit_estimation(frappe._dict(name="EN-2", packing_list="PL-1", items=[])))
		# Baris tanpa Packing List tidak punya plafon sama sekali.
		self.assertFalse(items_fit_estimation(frappe._dict(
			name="EN-3", packing_list=None,
			items=[frappe._dict(item="ITM-1", container_no="C1", amount=1)])))

	def test_debit_account_rejects_receivable(self):
		"""Akun debit boleh Payable (angsuran hutang sendiri, barisnya diberi party vendor),
		tapi Receivable ditolak — itu piutang customer, party-nya bukan supplier EN."""
		import frappe
		from types import SimpleNamespace
		from unittest.mock import patch

		from erp.expedition.doctype.expense_note.expense_note import ExpenseNote

		# SimpleNamespace, bukan frappe._dict: atribut `items` di _dict kebentur method
		# dict.items bawaan, jadi self.items bukan daftar barisnya.
		doc = SimpleNamespace(
			company="PT CMI", conversion_rate=1, is_reimburse=0, flags=frappe._dict(),
			items=[frappe._dict(item=None, expense_class=None, description="Leasing",
				expense_account="1150.001 - Piutang Dagang IDR - PC", amount=100)],
		)
		with patch("frappe.db.get_value", return_value="Receivable"):
			with self.assertRaises(frappe.ValidationError):
				ExpenseNote._create_journal_entry(doc)
		# Payable lolos guard (eksekusi lanjut sampai butuh DB, jadi cukup pastikan
		# bukan pesan guard yang muncul).
		with patch("frappe.db.get_value", return_value="Payable"):
			try:
				ExpenseNote._create_journal_entry(doc)
			except Exception as e:
				self.assertNotIn("tidak bisa dipakai sebagai akun debit", str(e))

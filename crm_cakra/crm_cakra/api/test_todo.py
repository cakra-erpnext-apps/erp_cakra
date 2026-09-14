# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

"""Test aturan prioritas tab To Do.

Hanya bagian yang murni logika -- yang menentukan urutan kerja orang. Querinya
sendiri tidak dites di sini: itu SQL biasa yang gagalnya kelihatan langsung,
sementara salah ambang prioritas gagal dalam diam (pekerjaan mendesak turun ke
bawah dan tidak ada yang sadar).
"""

import unittest

from crm_cakra.api.dashboard import PRIORITY_RANK, _todo_priority

IDLE = 3  # FCRM Settings.quotation_idle_days, nilai bawaan


class TestTodoPriority(unittest.TestCase):
	def test_lewat_tenggat_paling_mendesak(self):
		self.assertEqual(_todo_priority(-5, 0, IDLE), "High")

	def test_tenggat_besok_masih_high(self):
		self.assertEqual(_todo_priority(1, 0, IDLE), "High")

	def test_tenggat_minggu_ini_medium(self):
		self.assertEqual(_todo_priority(7, 0, IDLE), "Medium")

	def test_tenggat_jauh_low(self):
		self.assertEqual(_todo_priority(30, 0, IDLE), "Low")

	def test_tanpa_tenggat_ikut_lama_diam(self):
		# Tanpa tenggat, yang menaikkan prioritas hanya lamanya dokumen diam.
		self.assertEqual(_todo_priority(None, 0, IDLE), "Low")
		self.assertEqual(_todo_priority(None, IDLE, IDLE), "Medium")
		self.assertEqual(_todo_priority(None, IDLE * 2, IDLE), "High")

	def test_diam_lama_menaikkan_walau_tenggat_jauh(self):
		self.assertEqual(_todo_priority(30, IDLE * 2, IDLE), "High")

	def test_urutan_rank(self):
		self.assertEqual(
			sorted(["Low", "High", "Medium"], key=PRIORITY_RANK.get),
			["High", "Medium", "Low"],
		)


if __name__ == "__main__":
	unittest.main()

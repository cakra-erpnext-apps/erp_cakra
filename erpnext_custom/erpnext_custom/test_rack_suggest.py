"""Cek pembacaan nama bin + tingkat pohon gudang (rack_suggest).

Jalankan:  bench --site erp.localhost run-tests --module erpnext_custom.test_rack_suggest

Yang dijaga: urutan saran rak. custom_rack_order/level lahir dari NAMA bin, jadi
kalau regex-nya bergeser, Suggest Rack diam-diam menyarankan rak yang salah —
tidak error, cuma salah. Contoh diambil dari data asli (Bin Location: Gudang
Jakarta pakai AA0101A, Gudang KIM pakai AB4A/AE7).
"""

import unittest

import frappe

from erpnext_custom.rack_suggest import BIN, GUDANG, RAK, _level_of, _set_position_from_name


def _pos(warehouse_name):
	doc = frappe._dict(warehouse_name=warehouse_name, custom_rack_order=0, custom_rack_level=0)
	_set_position_from_name(doc)
	return doc.custom_rack_order, doc.custom_rack_level


class TestBinName(unittest.TestCase):
	def test_level_from_trailing_letter(self):
		# A = paling bawah, E = paling atas; bay yang sama -> urutan jarak sama
		self.assertEqual(_pos("AA0101A")[1], 1)
		self.assertEqual(_pos("AA0101E")[1], 5)
		self.assertEqual(_pos("AA0101A")[0], _pos("AA0101E")[0])

	def test_distance_orders_rack_then_bay(self):
		# rak AA sebelum AB, dan di dalam satu rak bay kecil lebih dekat
		self.assertLess(_pos("AA1304A")[0], _pos("AB0101A")[0])
		self.assertLess(_pos("AA0101A")[0], _pos("AA0301A")[0])

	def test_dialek_kim_dan_skema_lama(self):
		self.assertEqual(_pos("AB4A")[1], 1)      # huruf rak + bay + tingkat
		self.assertEqual(_pos("AE7")[1], 0)       # tanpa huruf tingkat = tak diketahui
		self.assertEqual(_pos("A-AA-01")[1], 1)   # skema lama masih terbaca

	def test_nama_tak_terbaca_tidak_meledak(self):
		self.assertEqual(_pos("Staging Area"), (0, 0))
		self.assertEqual(_pos("BULKY"), (0, 0))

	def test_manual_tidak_ditimpa(self):
		doc = frappe._dict(warehouse_name="AA0101A", custom_rack_order=5, custom_rack_level=9)
		_set_position_from_name(doc)
		self.assertEqual((doc.custom_rack_order, doc.custom_rack_level), (5, 9))


class TestTreeLevel(unittest.TestCase):
	"""Gudang > Rak > Bin ditentukan posisi di pohon, bukan diketik user."""

	def test_levels(self):
		root = frappe.db.get_value("Warehouse", {"parent_warehouse": ["is", "not set"]}, "name")
		self.assertIsNotNone(root, "akar company tidak ada")
		self.assertIsNone(_level_of(None, 1))            # akar sendiri
		self.assertEqual(_level_of(root, 1), GUDANG)     # anak akar
		self.assertEqual(_level_of(root, 0), GUDANG)     # gudang tanpa rak tetap gudang

	def test_dalam_gudang(self):
		# disimulasikan lewat record sungguhan supaya get_cached_value terpakai
		root = frappe.db.get_value("Warehouse", {"parent_warehouse": ["is", "not set"]}, "name")
		company = frappe.db.get_value("Warehouse", root, "company")
		g = frappe.get_doc(dict(doctype="Warehouse", warehouse_name="ZZ Test Gudang",
			company=company, parent_warehouse=root, is_group=1)).insert(ignore_permissions=True)
		try:
			self.assertEqual(g.warehouse_type, GUDANG)
			r = frappe.get_doc(dict(doctype="Warehouse", warehouse_name="ZZ", company=company,
				parent_warehouse=g.name, is_group=1)).insert(ignore_permissions=True)
			b = frappe.get_doc(dict(doctype="Warehouse", warehouse_name="ZZ0101A", company=company,
				parent_warehouse=r.name)).insert(ignore_permissions=True)
			staging = frappe.get_doc(dict(doctype="Warehouse", warehouse_name="ZZ Staging",
				company=company, parent_warehouse=g.name)).insert(ignore_permissions=True)
			self.assertEqual(r.warehouse_type, RAK)
			self.assertEqual(b.warehouse_type, BIN)
			self.assertEqual(staging.warehouse_type, BIN)  # daun langsung di gudang
			for d in (b, staging, r):
				d.delete(ignore_permissions=True)
		finally:
			frappe.delete_doc("Warehouse", g.name, force=1, ignore_permissions=True)
			frappe.db.rollback()

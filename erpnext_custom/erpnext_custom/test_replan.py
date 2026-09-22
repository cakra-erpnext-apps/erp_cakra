"""Cek Replan: instruksi turun tingkat / barang tua, kunci bin, dan berlaku saat disetujui.

    bench --site erp.localhost run-tests --module erpnext_custom.test_replan

Master uji dibuat di gudang sendiri lalu di-rollback, supaya 546 bin hasil impor
legacy tidak ikut jadi kandidat dan bikin hasilnya berubah-ubah.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, nowdate

from erpnext_custom import bin_layout, bin_ledger, replan


class TestReplan(FrappeTestCase):
	def setUp(self):
		company = frappe.get_all("Company", limit=1, fields=["name"])[0]
		self.gudang = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Replan",
				"company": company.name,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		# ZA nempel pick area, ZB lebih jauh -- itu yang bikin "lebih gampang digapai"
		# bisa diuji lewat JARAK, bukan cuma lewat tingkat.
		self.rak_dekat, self.rak_jauh = (
			frappe.get_doc(
				{
					"doctype": "Rack",
					"gudang": self.gudang.name,
					"rack_code": code,
					"distance_order": order,
				}
			).insert(ignore_permissions=True)
			for code, order in (("ZA", 1), ("ZB", 2))
		)
		self.bawah, self.atas = (
			frappe.get_doc(
				{"doctype": "Bin Location", "rack": self.rak_dekat.name, "bin_code": code}
			).insert(ignore_permissions=True)
			for code in ("ZA0101A", "ZA0101D")
		)
		self.jauh = frappe.get_doc(
			{"doctype": "Bin Location", "rack": self.rak_jauh.name, "bin_code": "ZB0101A"}
		).insert(ignore_permissions=True)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZ-REPLAN-TEST",
				"item_name": "ZZ Replan Test",
				"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"weight_per_unit": 10,
				"weight_uom": "Kg",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	# ------------------------------------------------------------- bantu

	def _layer(self, bin_location, qty=5, umur_hari=0):
		"""Tulis lapisan langsung ke buku besar bin: itu keadaan awal yang dibaca plan().

		Jauh lebih murah daripada menyubmit dokumen stok betulan, dan yang diuji di
		sini memang aturan penataannya.
		"""
		bin_ledger._write(
			self.item.name,
			bin_location,
			qty,
			voucher=None,
			received_on=get_datetime(add_days(nowdate(), -umur_hari)),
			qty_left=qty,
		)

	def _replan(self, **extra):
		hasil = replan.plan(self.gudang.name, **extra)
		return hasil["rows"], hasil["skipped"]

	def _draft(self, rows):
		return frappe.get_doc(
			{
				"doctype": "Bin Replan",
				"gudang": self.gudang.name,
				"max_level": 2,
				"min_age_days": 90,
				"items": rows,
			}
		).insert(ignore_permissions=True)

	def _qty(self, bin_location):
		return bin_layout.bin_usage([bin_location])[bin_location]["qty"]

	# ------------------------------------------------------------- saran

	def test_barang_di_tingkat_atas_diusulkan_turun(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["from_bin_location"], self.atas.name)
		self.assertEqual(rows[0]["bin_location"], self.bawah.name)  # tingkat A rak yang sama
		self.assertEqual(rows[0]["qty"], 5)
		self.assertIn("Tingkat", rows[0]["reason"])

	def test_barang_tua_dimajukan_ke_rak_terdekat(self):
		self._layer(self.jauh.name, 5, umur_hari=200)
		rows, _ = self._replan(max_level=0, min_age_days=90)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["from_bin_location"], self.jauh.name)
		self.assertEqual(rows[0]["bin_location"], self.bawah.name)
		self.assertIn("Umur", rows[0]["reason"])
		self.assertGreaterEqual(rows[0]["age_days"], 200)

	def test_barang_baru_di_tingkat_bawah_tidak_diusulkan(self):
		self._layer(self.bawah.name, 5)
		rows, skipped = self._replan(max_level=2, min_age_days=90)
		self.assertEqual(rows, [])
		self.assertEqual(skipped, [])

	def test_tidak_menyuruh_pindah_ke_tempat_yang_sama_susahnya(self):
		# barangnya tua, tapi sudah di bin paling dekat dan paling bawah: tidak ada
		# tempat yang lebih baik, jadi replan tidak boleh mengarang pindahan.
		self._layer(self.bawah.name, 5, umur_hari=200)
		rows, skipped = self._replan(max_level=0, min_age_days=90)
		self.assertEqual(rows, [])
		self.assertTrue(any("lebih gampang" in s for s in skipped))

	def test_staging_bukan_urusan_replan(self):
		# barang yang masih di penampung dinaikkan lewat Goods Receive (ada nomor
		# notanya); replan cuma menata yang sudah di rak.
		self._layer(bin_ledger.staging_bin(self.gudang.name), 5, umur_hari=400)
		rows, _ = self._replan(max_level=2, min_age_days=90)
		self.assertEqual(rows, [])

	# ------------------------------------------------------------- kunci bin

	def test_draft_mengunci_bin_asal_dan_tujuan(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		doc = self._draft(rows)

		terkunci = replan.locked_bins()
		self.assertEqual(terkunci.get(self.atas.name), doc.name)
		self.assertEqual(terkunci.get(self.bawah.name), doc.name)

		# tidak pernah disarankan lagi
		kandidat = [b.name for b in bin_layout.candidate_bins(self.gudang.name, self.item.name)]
		self.assertNotIn(self.bawah.name, kandidat)
		self.assertNotIn(self.atas.name, kandidat)

		# dan ditolak kalau ada yang mengetiknya sendiri di Goods Receive
		self._layer(bin_ledger.staging_bin(self.gudang.name), 1)
		gr = frappe.get_doc(
			{
				"doctype": "Goods Receive",
				"gudang": self.gudang.name,
				"items": [{"item_code": self.item.name, "bin_location": self.bawah.name, "qty": 1}],
			}
		)
		self.assertRaises(frappe.ValidationError, gr.insert)

	def test_kunci_lepas_setelah_disetujui(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		doc = self._draft(rows)
		for row in doc.items:
			row.done = 1
		doc.save(ignore_permissions=True)
		doc.submit()
		self.assertEqual(replan.locked_bins(), {})

	# ------------------------------------------------------------- berlaku saat disetujui

	def test_draft_belum_memindahkan_apa_pun(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		self._draft(rows)
		self.assertEqual(self._qty(self.atas.name), 5)
		self.assertEqual(self._qty(self.bawah.name), 0)

	def test_semua_baris_harus_dicentang_dulu(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		doc = self._draft(rows)
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_disetujui_langsung_memindahkan_barangnya(self):
		self._layer(self.atas.name, 5, umur_hari=120)
		rows, _ = self._replan(max_level=2, min_age_days=90)
		doc = self._draft(rows)
		for row in doc.items:
			row.done = 1
		doc.save(ignore_permissions=True)
		doc.submit()

		self.assertEqual(self._qty(self.atas.name), 0)
		self.assertEqual(self._qty(self.bawah.name), 5)
		self.assertEqual(doc.approved_by, frappe.session.user)
		self.assertTrue(doc.approved_on)

		# umur barang IKUT PINDAH: kalau direset, FIFO jadi bohong dan replan
		# berikutnya tidak akan pernah mengenalinya sebagai barang tua lagi.
		layers = bin_ledger.fifo_layers(self.item.name, self.gudang.name, self.bawah.name)
		self.assertEqual(len(layers), 1)
		self.assertLessEqual(get_datetime(layers[0].received_on), get_datetime(add_days(nowdate(), -119)))

	def test_batal_mengembalikan_barangnya(self):
		self._layer(self.atas.name, 5)
		rows, _ = self._replan(max_level=2, min_age_days=0)
		doc = self._draft(rows)
		for row in doc.items:
			row.done = 1
		doc.save(ignore_permissions=True)
		doc.submit()
		doc.cancel()
		self.assertEqual(self._qty(self.atas.name), 5)
		self.assertEqual(self._qty(self.bawah.name), 0)

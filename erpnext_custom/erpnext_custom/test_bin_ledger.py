"""Cek buku besar bin: barang masuk, barang keluar, dan urutan FIFO.

    bench --site erp.localhost run-tests --module erpnext_custom.test_bin_ledger

Master uji dibuat di gudang sendiri lalu di-rollback, supaya bin hasil impor
legacy tidak ikut jadi kandidat dan hasilnya tidak berubah-ubah.

Lapisan ditulis langsung lewat bin_ledger, tanpa Purchase Invoice/Delivery Note,
supaya yang diuji memang mesinnya -- bukan mesin plus seluruh akuntansi ERPNext.
Penyambungan ke dokumen aslinya dijaga hooks.py dan diperiksa manual.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, get_datetime, nowdate

from erpnext_custom import bin_ledger


class TestBinLedger(FrappeTestCase):
	def setUp(self):
		company = frappe.get_all("Company", limit=1, fields=["name"])[0]
		self.gudang = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Ledger",
				"company": company.name,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		self.rack = frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZL", "distance_order": 5}
		).insert(ignore_permissions=True)
		self.bin_a, self.bin_b = (
			frappe.get_doc(
				{"doctype": "Bin Location", "rack": self.rack.name, "bin_code": code}
			).insert(ignore_permissions=True)
			for code in ("ZL0101A", "ZL0102A")
		)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZ-LEDGER-TEST",
				"item_name": "ZZ Ledger Test",
				"item_group": frappe.get_all(
					"Item Group", filters={"is_group": 0}, limit=1, pluck="name"
				)[0],
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	# ------------------------------------------------------------- bantu

	def _lapis(self, bin_location, qty, umur):
		"""Taruh satu lapisan langsung, dengan umur yang ditentukan."""
		return bin_ledger._write(
			self.item.name, bin_location, qty, voucher=None, received_on=umur, qty_left=qty
		)

	def _sisa(self, bin_location):
		return sum(
			flt(l.qty_left)
			for l in bin_ledger.fifo_layers(self.item.name, self.gudang.name, bin_location)
		)

	# ------------------------------------------------------------- tes

	def test_saldo_cache_ikut_buku_besar(self):
		"""Item Bin Qty adalah cache turunan, bukan catatan yang berdiri sendiri."""
		self._lapis(self.bin_a.name, 10, get_datetime("2026-01-01 08:00:00"))
		saldo = frappe.db.get_value(
			"Item Bin Qty",
			{"item_code": self.item.name, "bin_location": self.bin_a.name},
			"qty",
		)
		self.assertEqual(flt(saldo), 10)
		self.assertEqual(bin_ledger.bin_total(self.item.name, self.gudang.name), 10)

	def test_barang_lama_keluar_duluan(self):
		"""INI pertanyaan intinya: urutan keluar, barang lama duluan.

		Lapisan BARU sengaja ditaruh di bin yang LEBIH DEKAT pintu. Kalau yang
		dipakai urutan jarak (perilaku lama), yang termakan justru yang baru.
		"""
		self._lapis(self.bin_b.name, 5, get_datetime("2026-01-01 08:00:00"))  # tua, jauh
		self._lapis(self.bin_a.name, 5, get_datetime("2026-06-01 08:00:00"))  # baru, dekat
		bin_ledger.consume(self.item.name, self.gudang.name, 3, voucher=None)
		self.assertEqual(self._sisa(self.bin_b.name), 2)  # yang tua termakan
		self.assertEqual(self._sisa(self.bin_a.name), 5)  # yang baru utuh

	def test_umur_dari_tanggal_posting_bukan_saat_dibuat(self):
		"""Penerimaan yang dimundurkan tanggalnya harus duduk di urutan yang benar.

		Ini persis yang salah di FIFO batch bawaan, yang memakai Batch.creation.
		"""
		kemarin = frappe._dict(
			{"doctype": "Stock Entry", "name": "ZZ-MUNDUR", "posting_date": add_days(nowdate(), -30),
			 "posting_time": "08:00:00", "docstatus": 1}
		)
		self.assertEqual(
			bin_ledger._posting_dt(kemarin),
			get_datetime("{0} 08:00:00".format(add_days(nowdate(), -30))),
		)

	def test_umur_kosong_diurutkan_paling_belakang(self):
		"""Lapisan tanpa tanggal tidak boleh menyamar jadi barang paling tua.

		`received_on` itu mandatory, jadi kode kita tidak bisa menghasilkan NULL.
		Yang masih bisa: tulisan DB langsung atau impor data -- persis cara NULL
		itu dibuat di sini.
		"""
		kosong = self._lapis(self.bin_a.name, 4, get_datetime("2026-01-01 08:00:00"))
		frappe.db.set_value(
			"Bin Ledger Entry", kosong, "received_on", None, update_modified=False
		)
		self._lapis(self.bin_b.name, 4, get_datetime("2026-03-01 08:00:00"))
		bin_ledger.consume(self.item.name, self.gudang.name, 4, voucher=None)
		self.assertEqual(self._sisa(self.bin_b.name), 0)  # yang bertanggal jalan duluan
		self.assertEqual(self._sisa(self.bin_a.name), 4)

	def test_pindah_bin_mempertahankan_umur(self):
		"""Invarian paling rapuh: put-away tidak boleh mereset umur barang.

		Staging adalah tempat mendarat default, jadi kalau umur ter-reset di sini,
		FIFO jadi bohong untuk hampir semua barang.
		"""
		umur = get_datetime("2026-02-02 07:30:00")
		self._lapis(self.bin_a.name, 6, umur)
		bin_ledger.move(self.item.name, self.bin_a.name, self.bin_b.name, 6, voucher=None)
		layers = bin_ledger.fifo_layers(self.item.name, self.gudang.name, self.bin_b.name)
		self.assertEqual(len(layers), 1)
		self.assertEqual(get_datetime(layers[0].received_on), umur)
		self.assertEqual(self._sisa(self.bin_a.name), 0)

	def test_pindah_lebih_dari_isi_ditolak(self):
		self._lapis(self.bin_a.name, 2, get_datetime("2026-01-01 08:00:00"))
		with self.assertRaises(frappe.ValidationError):
			bin_ledger.move(self.item.name, self.bin_a.name, self.bin_b.name, 5, voucher=None)

	def test_kurang_lapisan_tercatat_bukan_hilang(self):
		"""Kalau lapisan habis, selisihnya dibukukan minus -- bukan dibuang diam-diam.

		Sistem lama memangkas bin sampai nol dan selisihnya lenyap tanpa jejak.
		"""
		self._lapis(self.bin_a.name, 2, get_datetime("2026-01-01 08:00:00"))
		bin_ledger.consume(self.item.name, self.gudang.name, 5, voucher=None)
		# 2 masuk - 2 keluar - 3 kurang = -3, dan angkanya tetap utuh secara aritmetika
		self.assertEqual(bin_ledger.bin_total(self.item.name, self.gudang.name), -3)
		self.assertTrue(
			frappe.db.exists(
				"Bin Ledger Entry", {"item_code": self.item.name, "is_short": 1}
			)
		)

	def test_gudang_tanpa_bin_dilewati(self):
		"""81 gudang non-group di site ini; yang tak punya bin tidak boleh ketularan."""
		polos = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Tanpa Bin",
				"company": frappe.get_all("Company", limit=1, pluck="name")[0],
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		self.assertFalse(bin_ledger.is_tracked(polos.name))
		self.assertTrue(bin_ledger.is_tracked(self.gudang.name))

	def test_item_batch_dilewati(self):
		"""Item ber-batch punya FIFO bawaan ERPNext; dua mesin = dua jawaban."""
		self.assertTrue(bin_ledger.is_ledgered_item(self.item.name))
		self.item.db_set("has_batch_no", 1)
		frappe.clear_cache(doctype="Item")
		self.assertFalse(bin_ledger.is_ledgered_item(self.item.name))

	def test_staging_memakai_rak_yang_sudah_ada(self):
		"""Rak Staging yang sudah dibuat operator dipakai ulang, bukan digandakan."""
		punya = frappe.get_doc(
			{
				"doctype": "Rack",
				"gudang": self.gudang.name,
				"rack_code": "ZL-STG",
				"kind": "Staging",
			}
		).insert(ignore_permissions=True)
		loc = bin_ledger.staging_bin(self.gudang.name)
		self.assertEqual(frappe.db.get_value("Bin Location", loc, "rack"), punya.name)
		self.assertEqual(
			frappe.db.count("Rack", {"gudang": self.gudang.name, "kind": "Staging"}), 1
		)

	def test_audit_menemukan_selisih(self):
		"""Jaring yang tidak dipunyai sistem lama: selisih harus kelihatan, bukan hilang."""
		self._lapis(self.bin_a.name, 7, get_datetime("2026-01-01 08:00:00"))
		frappe.get_doc(
			{
				"doctype": "Bin",
				"item_code": self.item.name,
				"warehouse": self.gudang.name,
				"actual_qty": 10,
				"stock_uom": "Nos",
			}
		).insert(ignore_permissions=True)
		selisih = {r["item_code"]: r["selisih"] for r in bin_ledger.audit(self.gudang.name)}
		self.assertEqual(selisih.get(self.item.name), 3)

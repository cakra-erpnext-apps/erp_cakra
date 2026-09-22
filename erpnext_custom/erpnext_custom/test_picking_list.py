"""Cek pemetik rak Pick List: urutan ambil, pemecahan baris, dan pindah ke staging keluar.

    bench --site erp.localhost run-tests --module erpnext_custom.test_picking_list

Master uji dibuat di gudang sendiri lalu di-rollback, supaya bin hasil impor legacy
tidak ikut jadi kandidat dan hasilnya tidak berubah-ubah.

Lapisan ditulis langsung lewat bin_ledger dan Pick List-nya dipalsukan dengan
frappe._dict: yang diuji mesin binnya, bukan mesin bin plus seluruh alur penjualan
ERPNext. Penyambungan ke dokumen aslinya dijaga hooks.py.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, get_datetime, nowdate

from erpnext_custom import bin_ledger
from erpnext_custom.picking_list import picking_list


class TestPickingList(FrappeTestCase):
	def setUp(self):
		company = frappe.get_all("Company", limit=1, fields=["name"])[0]
		self.gudang = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Pick",
				"company": company.name,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		# Dua rak dengan jarak berbeda: ZD nempel pick area, ZJ paling jauh.
		self.rak_dekat, self.rak_jauh = (
			frappe.get_doc(
				{
					"doctype": "Rack",
					"gudang": self.gudang.name,
					"rack_code": kode,
					"distance_order": jarak,
				}
			).insert(ignore_permissions=True)
			for kode, jarak in (("ZD", 1), ("ZJ", 9))
		)
		self.bin_dekat = frappe.get_doc(
			{"doctype": "Bin Location", "rack": self.rak_dekat.name, "bin_code": "ZD0101A"}
		).insert(ignore_permissions=True)
		self.bin_jauh = frappe.get_doc(
			{"doctype": "Bin Location", "rack": self.rak_jauh.name, "bin_code": "ZJ0101A"}
		).insert(ignore_permissions=True)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZ-PICK-TEST",
				"item_name": "ZZ Pick Test",
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
		return bin_ledger._write(
			self.item.name,
			bin_location,
			qty,
			voucher=None,
			received_on=get_datetime(umur),
			qty_left=qty,
		)

	def _layers(self):
		return bin_ledger.fifo_layers(self.item.name, self.gudang.name)

	def _sisa(self, bin_location):
		return sum(
			flt(l.qty_left)
			for l in bin_ledger.fifo_layers(self.item.name, self.gudang.name, bin_location)
		)

	def _minta(self, qty, **extra):
		return picking_list.suggest_bins(
			[{"item_code": self.item.name, "warehouse": self.gudang.name, "qty": qty, **extra}]
		)[0]

	def _pick_list(self, qty, bin_location):
		# name=None disengaja: Bin Ledger Entry memvalidasi voucher_no sebagai link,
		# dan yang diuji di sini perpindahan binnya, bukan penyambungan dokumennya.
		return frappe._dict(
			doctype="Pick List",
			name=None,
			purpose="Delivery",
			docstatus=1,
			posting_date=nowdate(),
			locations=[
				frappe._dict(
					item_code=self.item.name,
					warehouse=self.gudang.name,
					custom_bin_location=bin_location,
					picked_qty=qty,
					stock_qty=qty,
				)
			],
		)

	# ------------------------------------------------------------- urutan ambil

	def test_fifo_keras_menang_walau_raknya_jauh(self):
		"""Toleransi 0 = umur tidak boleh ditawar, walau raknya di ujung gudang."""
		self._lapis(self.bin_jauh.name, 10, "2026-01-01 08:00:00")
		self._lapis(self.bin_dekat.name, 10, "2026-01-05 08:00:00")

		urut = picking_list._pick_order(self._layers(), 0)

		self.assertEqual(urut[0].bin_location, self.bin_jauh.name)

	def test_toleransi_umur_mendahulukan_rak_terdekat(self):
		"""Dalam rentang toleransi umur dianggap seri, dan kemudahan yang memutus."""
		self._lapis(self.bin_jauh.name, 10, "2026-01-01 08:00:00")
		self._lapis(self.bin_dekat.name, 10, "2026-01-05 08:00:00")

		urut = picking_list._pick_order(self._layers(), 30)

		self.assertEqual(urut[0].bin_location, self.bin_dekat.name)

	def test_toleransi_tidak_melompati_barang_yang_jauh_lebih_tua(self):
		"""Toleransi itu jendela, bukan izin mengabaikan umur sama sekali."""
		self._lapis(self.bin_jauh.name, 10, "2026-01-01 08:00:00")
		self._lapis(self.bin_dekat.name, 10, "2026-06-01 08:00:00")

		urut = picking_list._pick_order(self._layers(), 30)

		self.assertEqual(urut[0].bin_location, self.bin_jauh.name)

	# ------------------------------------------------------------- pembagian

	def test_satu_rak_tidak_cukup_barisnya_dipecah(self):
		self._lapis(self.bin_jauh.name, 4, "2026-01-01 08:00:00")
		self._lapis(self.bin_dekat.name, 10, "2026-01-05 08:00:00")

		hasil = self._minta(10)

		self.assertEqual(
			[(a["bin_location"], a["qty"]) for a in hasil["allocations"]],
			[(self.bin_jauh.name, 4), (self.bin_dekat.name, 6)],
		)
		self.assertFalse(hasil["shortage"])

	def test_stok_kurang_dilaporkan_bukan_didiamkan(self):
		self._lapis(self.bin_dekat.name, 3, "2026-01-01 08:00:00")

		hasil = self._minta(10)

		self.assertEqual(hasil["shortage"], 7)

	def test_staging_keluar_tidak_pernah_disarankan(self):
		"""Isinya sudah dipetik untuk pengiriman lain; menawarkannya = janji ganda."""
		keluar = bin_ledger.staging_bin(self.gudang.name, bin_ledger.KELUAR)
		self._lapis(keluar, 10, "2026-01-01 08:00:00")
		self._lapis(self.bin_dekat.name, 10, "2026-06-01 08:00:00")

		hasil = self._minta(10)

		self.assertEqual([a["bin_location"] for a in hasil["allocations"]], [self.bin_dekat.name])

	def test_baris_berbatch_dilewati_bukan_ditebak(self):
		"""Buku besar bin tidak menyimpan batch, jadi raknya tidak bisa dijanjikan."""
		self._lapis(self.bin_dekat.name, 10, "2026-01-01 08:00:00")

		hasil = self._minta(10, batch_no="ZZ-BATCH-1")

		self.assertEqual(hasil["allocations"], [])
		self.assertIn("batch", hasil["skip"])

	# ------------------------------------------------------------- petunjuk bin

	def test_petunjuk_banyak_bin_dipatuhi_batasnya(self):
		"""Tanpa batas per bin, bin pertama menelan seluruh qty dokumen."""
		self._lapis(self.bin_dekat.name, 10, "2026-01-01 08:00:00")
		self._lapis(self.bin_jauh.name, 10, "2026-01-01 08:00:00")

		bin_ledger.consume(
			self.item.name,
			self.gudang.name,
			10,
			voucher=None,
			hint_bin=[(self.bin_dekat.name, 4), (self.bin_jauh.name, 6)],
		)

		self.assertEqual(self._sisa(self.bin_dekat.name), 6)
		self.assertEqual(self._sisa(self.bin_jauh.name), 4)

	# ------------------------------------------------------------- rak -> staging keluar

	def test_submit_menurunkan_barang_ke_staging_keluar(self):
		self._lapis(self.bin_dekat.name, 10, "2026-01-01 08:00:00")

		picking_list.move_to_pick_staging(self._pick_list(6, self.bin_dekat.name))

		keluar = bin_ledger.staging_bin(self.gudang.name, bin_ledger.KELUAR)
		self.assertEqual(self._sisa(self.bin_dekat.name), 4)
		self.assertEqual(self._sisa(keluar), 6)

	def test_pindah_ke_staging_keluar_tidak_mengubah_total_gudang(self):
		"""Invarian yang menopang semuanya: bin_total == Bin.actual_qty di setiap titik."""
		self._lapis(self.bin_dekat.name, 10, "2026-01-01 08:00:00")
		sebelum = bin_ledger.bin_total(self.item.name, self.gudang.name)

		picking_list.move_to_pick_staging(self._pick_list(6, self.bin_dekat.name))

		self.assertEqual(bin_ledger.bin_total(self.item.name, self.gudang.name), sebelum)

	def test_batal_mengembalikan_ke_rak_asal_dengan_umur_aslinya(self):
		"""Umur direset = FIFO bohong untuk semua barang sesudahnya."""
		umur = "2026-01-01 08:00:00"
		self._lapis(self.bin_dekat.name, 10, umur)
		doc = self._pick_list(6, self.bin_dekat.name)
		picking_list.move_to_pick_staging(doc)

		picking_list.move_back_from_pick_staging(doc)

		self.assertEqual(self._sisa(self.bin_dekat.name), 10)
		self.assertEqual(
			{get_datetime(l.received_on) for l in self._layers()}, {get_datetime(umur)}
		)

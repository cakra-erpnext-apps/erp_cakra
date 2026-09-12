"""Cek layout gudang: kapasitas bin, pembagian saran, dan batas stok.

    bench --site erp.localhost run-tests --module erpnext_custom.test_bin_layout

Semua master uji dibuat di gudang sendiri lalu di-rollback, supaya bin hasil impor
legacy (546 bin Gudang Jakarta) tidak ikut jadi kandidat dan bikin hasil berubah-ubah.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext_custom import bin_layout


class TestBinLayout(FrappeTestCase):
	def setUp(self):
		company = frappe.get_all("Company", limit=1, fields=["name", "abbr"])[0]
		self.gudang = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Layout",
				"company": company.name,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		self.rack = frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZZ"}
		).insert(ignore_permissions=True)
		# dua bin 100 kg; ZZ0101A lebih dekat pintu keluar daripada ZZ0102A
		self.bin_a, self.bin_b = (
			frappe.get_doc(
				{
					"doctype": "Bin Location",
					"rack": self.rack.name,
					"bin_code": code,
					"capacity_weight": 100,
				}
			).insert(ignore_permissions=True)
			for code in ("ZZ0101A", "ZZ0102A")
		)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZ-BIN-TEST",
				"item_name": "ZZ Bin Test",
				"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, limit=1, pluck="name")[0],
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"weight_per_unit": 10,
				"weight_uom": "Kg",
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_posisi_dari_nama_bin(self):
		# ZZ0101A: urutan dari huruf rak + bay, tingkat dari huruf terakhir (A = 1)
		self.assertEqual(self.bin_a.rack_order, bin_layout._letters_index("ZZ") * 10000 + 101)
		self.assertEqual(self.bin_a.rack_level, 1)
		# bay berikutnya dianggap lebih jauh dari pintu
		self.assertLess(self.bin_a.rack_order, self.bin_b.rack_order)

	def test_fits_dibatasi_yang_paling_ketat(self):
		# sisa 100 kg / 10 kg per unit = 10; sisa 2 m3 / 0.5 = 4 -> yang menang 4
		self.assertEqual(bin_layout.fits(100, 2, 10, 0.5), 4)
		# tanpa kapasitas sama sekali = tak terbatas
		self.assertIsNone(bin_layout.fits(None, None, 10, 0.5))
		# item tanpa ukuran tidak memakan kapasitas, bukan malah memblokir bin
		self.assertIsNone(bin_layout.fits(100, 100, 0, 0))
		self.assertEqual(bin_layout.fits(0, None, 10, 0), 0)  # sudah penuh

	def test_ukuran_item_dari_master(self):
		self.item.db_set({"custom_length": 1, "custom_width": 0.5, "custom_height": 0.2})
		frappe.clear_cache(doctype="Item")
		weight, volume = bin_layout.item_size(self.item.name)
		self.assertEqual(weight, 10)
		self.assertAlmostEqual(volume, 0.1)  # 1,0 x 0,5 x 0,2 m = 0,1 m3

	def test_suggest_memecah_ke_bin_berikutnya_saat_penuh(self):
		# 15 unit x 10 kg = 150 kg; satu bin cuma muat 100 kg -> harus pecah dua
		result = bin_layout.suggest(self.gudang.name, [{"item_code": self.item.name, "qty": 15}])[0]
		allocations = {a["bin_location"]: a["qty"] for a in result["allocations"]}
		self.assertEqual(sum(allocations.values()), 15)
		self.assertEqual(allocations.get(self.bin_a.name), 10)  # bin terdekat diisi penuh
		self.assertEqual(allocations.get(self.bin_b.name), 5)
		self.assertNotIn("shortage", result)

	def test_suggest_melaporkan_sisa_saat_semua_bin_penuh(self):
		# kapasitas total 200 kg = 20 unit; minta 25 -> 5 tidak kebagian
		result = bin_layout.suggest(self.gudang.name, [{"item_code": self.item.name, "qty": 25}])[0]
		self.assertEqual(sum(a["qty"] for a in result["allocations"]), 20)
		self.assertEqual(result["shortage"], 5)

	def test_tidak_boleh_menempatkan_lebih_dari_stok(self):
		# stok item uji nol, jadi penempatan apa pun harus ditolak
		doc = frappe.get_doc(
			{
				"doctype": "Goods Receive",
				"gudang": self.gudang.name,
				"items": [{"item_code": self.item.name, "bin_location": self.bin_a.name, "qty": 1}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_kapasitas_bin_ikut_default_tingkat_rak(self):
		# bin tanpa kapasitas sendiri ikut baris tingkat di master Rak
		self.rack.append("levels", {"level": "A", "capacity_weight": 250, "slot_length": 3})
		self.rack.save(ignore_permissions=True)
		frappe.clear_document_cache("Rack", self.rack.name)
		bin_c = frappe.get_doc(
			{"doctype": "Bin Location", "rack": self.rack.name, "bin_code": "ZZ0103A"}
		).insert(ignore_permissions=True)
		caps = bin_layout.bin_caps_map(self.gudang.name)
		self.assertEqual(caps[bin_c.name][0], 250)
		self.assertEqual(caps[bin_c.name][2], 3)  # panjang slot: meter
		# bin yang kapasitasnya diisi sendiri tetap menang atas default tingkat
		self.assertEqual(caps[self.bin_a.name][0], 100)

	def test_bin_gabungan_menyerahkan_kapasitas_ke_induknya(self):
		self.bin_a.db_set("slot_length", 1.2)
		self.bin_b.db_set("slot_length", 1.2)
		self.bin_b.db_set("merged_into", self.bin_a.name)
		caps = bin_layout.bin_caps_map(self.gudang.name)
		self.assertEqual(caps[self.bin_a.name][0], 200)  # 100 + 100 kg
		self.assertAlmostEqual(caps[self.bin_a.name][2], 2.4)  # 1,2 + 1,2 m
		self.assertNotIn(self.bin_b.name, caps)  # tidak berdiri sendiri lagi

	def test_barang_kepanjangan_butuh_bin_gabungan(self):
		self.item.db_set({"custom_length": 2})  # meter
		frappe.clear_cache(doctype="Item")
		self.bin_a.db_set("slot_length", 1.2)
		self.bin_b.db_set("slot_length", 1.2)
		# 2 m tidak muat di slot 1,2 m -> tidak ada bin yang ditawarkan
		self.assertEqual(bin_layout.candidate_bins(self.gudang.name, self.item.name), [])
		# gabungkan bin sebelahnya: slot jadi 2,4 m, barangnya muat
		self.bin_b.db_set("merged_into", self.bin_a.name)
		bins = bin_layout.candidate_bins(self.gudang.name, self.item.name)
		self.assertEqual([b.name for b in bins], [self.bin_a.name])

	def test_daftar_item_khusus_mengunci_rak(self):
		lain = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "ZZ-BIN-TEST-2",
				"item_name": "ZZ Bin Test 2",
				"item_group": self.item.item_group,
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		self.rack.append("allowed_items", {"item_code": self.item.name})
		self.rack.save(ignore_permissions=True)
		frappe.clear_document_cache("Rack", self.rack.name)
		self.assertTrue(bin_layout.item_allowed(self.rack.name, self.item.name))
		self.assertFalse(bin_layout.item_allowed(self.rack.name, lain.name))
		self.assertEqual(bin_layout.candidate_bins(self.gudang.name, lain.name), [])

	def test_bin_yang_digabung_tidak_boleh_diisi_langsung(self):
		self.bin_b.db_set("merged_into", self.bin_a.name)
		doc = frappe.get_doc(
			{
				"doctype": "Goods Receive",
				"gudang": self.gudang.name,
				"items": [{"item_code": self.item.name, "bin_location": self.bin_b.name, "qty": 1}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	# ---------------------------------------------- tarik dari Purchase Invoice

	def _baris_pi(self, pi, qty, gudang=None):
		"""Satu baris nota, ditulis langsung ke tabel child.

		ponytail: melewati validasi Purchase Invoice. Yang diuji di sini cuma
		pembacaan baris + pemotongan qty; PI sungguhan butuh supplier, akun, dan
		valuasi yang tidak ada hubungannya dengan itu. Kalau nanti perlu menguji
		alur PI utuh, pakai dokumen betulan.
		"""
		row = frappe.get_doc(
			{
				"doctype": "Purchase Invoice Item",
				"parent": pi,
				"parenttype": "Purchase Invoice",
				"parentfield": "items",
				"idx": 1,
				"docstatus": 1,
				"item_code": self.item.name,
				"warehouse": gudang or self.gudang.name,
				"stock_qty": qty,
				"stock_uom": "Nos",
			}
		)
		row.name = frappe.generate_hash(length=10)
		row.db_insert()

	def _goods_receive_submitted(self, pi, qty):
		"""Goods Receive yang sudah submit untuk nota itu (lihat ponytail di _baris_pi)."""
		doc = frappe.get_doc(
			{
				"doctype": "Goods Receive",
				"purchase_invoice": pi,
				"gudang": self.gudang.name,
				"docstatus": 1,
				"items": [{"item_code": self.item.name, "bin_location": self.bin_a.name, "qty": qty}],
			}
		)
		doc.name = "ZZ-GRC-" + frappe.generate_hash(length=6)
		doc.db_insert()
		for child in doc.items:
			child.parent, child.parenttype, child.parentfield = doc.name, "Goods Receive", "items"
			child.docstatus, child.name = 1, frappe.generate_hash(length=10)
			child.db_insert()

	def test_tarik_pi_menurunkan_gudang_dari_notanya(self):
		self._baris_pi("ZZ-PI-001", 10)
		out = bin_layout.pull_purchase_invoice("ZZ-PI-001")
		self.assertEqual(out["gudang"], self.gudang.name)
		self.assertEqual(out["rows"], [{"item_code": self.item.name, "qty": 10, "stock_uom": "Nos"}])

	def test_tarik_pi_memotong_yang_sudah_diterima(self):
		# nota 10, sudah diterima 4 lewat Goods Receive lain -> sisa 6
		self._baris_pi("ZZ-PI-002", 10)
		self._goods_receive_submitted("ZZ-PI-002", 4)
		rows = bin_layout.pull_purchase_invoice("ZZ-PI-002")["rows"]
		self.assertEqual(rows, [{"item_code": self.item.name, "qty": 6, "stock_uom": "Nos"}])

	def test_tarik_pi_habis_tidak_menyisakan_baris(self):
		self._baris_pi("ZZ-PI-003", 10)
		self._goods_receive_submitted("ZZ-PI-003", 10)
		self.assertEqual(bin_layout.pull_purchase_invoice("ZZ-PI-003")["rows"], [])

	def test_tarik_pi_dua_gudang_minta_dipilih(self):
		lain = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Layout 2",
				"company": self.gudang.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		self._baris_pi("ZZ-PI-004", 10)
		self._baris_pi("ZZ-PI-004", 5, gudang=lain.name)
		# tanpa gudang: ambigu, harus ditolak
		self.assertRaises(frappe.ValidationError, bin_layout.pull_purchase_invoice, "ZZ-PI-004")
		# dengan gudang: hanya baris gudang itu yang ikut
		rows = bin_layout.pull_purchase_invoice("ZZ-PI-004", lain.name)["rows"]
		self.assertEqual(rows, [{"item_code": self.item.name, "qty": 5, "stock_uom": "Nos"}])

	def test_tarik_pi_kosong_ditolak(self):
		self.assertRaises(frappe.ValidationError, bin_layout.pull_purchase_invoice, "ZZ-PI-KOSONG")

	def test_rak_dekat_pick_area_didahulukan(self):
		# abjad bilang ZY duluan, tapi ZZ-lah yang nempel pick area -> ZZ menang
		self.rack.db_set("distance_order", 1)
		frappe.clear_document_cache("Rack", self.rack.name)
		jauh = frappe.get_doc(
			{
				"doctype": "Rack",
				"gudang": self.gudang.name,
				"rack_code": "ZY",
				"distance_order": 9,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Bin Location",
				"rack": jauh.name,
				"bin_code": "ZY0101A",
				"capacity_weight": 100,
			}
		).insert(ignore_permissions=True)
		result = bin_layout.suggest(self.gudang.name, [{"item_code": self.item.name, "qty": 5}])[0]
		self.assertEqual(result["allocations"][0]["bin_location"], self.bin_a.name)

	def test_tingkat_yang_gampang_digapai_didahulukan(self):
		# tingkat B biasanya kalah dari A (makin bawah makin gampang), tapi kalau
		# B dinyatakan paling enak digapai, B yang dipakai duluan
		bin_b2 = frappe.get_doc(
			{
				"doctype": "Bin Location",
				"rack": self.rack.name,
				"bin_code": "ZZ0101B",
				"capacity_weight": 100,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_single_value("Stock Settings", "custom_level_pick_order", "B,A")
		frappe.clear_document_cache("Stock Settings", "Stock Settings")
		result = bin_layout.suggest(self.gudang.name, [{"item_code": self.item.name, "qty": 5}])[0]
		self.assertEqual(result["allocations"][0]["bin_location"], bin_b2.name)

	def test_pintu_dan_kantor_tidak_boleh_punya_bin(self):
		pintu = frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZP", "kind": "Pintu"}
		).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{"doctype": "Bin Location", "rack": pintu.name, "bin_code": "ZP0101A"}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_jarak_rak_dihitung_dari_pintu_terdekat(self):
		# rak ZZ di x=0, rak ZY jauh di x=64 m, pintu nempel ZZ -> ZZ peringkat 1.
		# Ukuran kotak = ukuran fisik rak (meter), tidak ada angka denah tersendiri.
		self.rack.db_set({"map_x": 0, "map_y": 0, "panjang": 8, "lebar": 5})
		jauh = frappe.get_doc(
			{
				"doctype": "Rack",
				"gudang": self.gudang.name,
				"rack_code": "ZY",
				"map_x": 64,
				"map_y": 0,
				"panjang": 8,
				"lebar": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Rack",
				"gudang": self.gudang.name,
				"rack_code": "ZPINTU",
				"kind": "Pintu",
				"map_x": 0,
				"map_y": 8,
				"panjang": 3,
				"lebar": 3,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(bin_layout.distance_from_map(self.gudang.name), 2)  # pintu tidak ikut
		self.assertEqual(frappe.db.get_value("Rack", self.rack.name, "distance_order"), 1)
		self.assertEqual(frappe.db.get_value("Rack", jauh.name, "distance_order"), 2)

	# ---------------------------------------------------- rapikan denah otomatis

	def test_rapikan_denah_berpasangan_tanpa_tumpang_tindih(self):
		# rak kedua dibuat supaya jadi sepasang dengan self.rack
		frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZY"}
		).insert(ignore_permissions=True)
		pintu = frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZPINTU", "kind": "Pintu"}
		).insert(ignore_permissions=True)
		# pintu sengaja ditaruh DI JALUR kolom lorong: lorongnya harus mengalah,
		# pintunya sendiri tidak boleh bergeser
		pintu.db_set({"map_x": 5, "map_y": 0, "panjang": 5, "lebar": 3})

		bin_layout.arrange(self.gudang.name)
		kotak = frappe.get_all(
			"Rack",
			filters={"gudang": self.gudang.name},
			fields=["rack_code", "kind", "map_x", "map_y", "panjang", "lebar"],
		)
		pos = {k.rack_code: k for k in kotak}

		# pintu yang sudah ditaruh tangan tidak boleh digeser
		self.assertEqual((pos["ZPINTU"].map_x, pos["ZPINTU"].map_y), (5, 0))
		# dan lorongnya mulai di bawah pintu itu
		self.assertGreaterEqual(pos["ZZ"].map_y, 3)
		# sepasang = punggung ke punggung: x sama, y beda persis setinggi satu rak
		self.assertEqual(pos["ZY"].map_x, pos["ZZ"].map_x)
		self.assertAlmostEqual(abs(pos["ZY"].map_y - pos["ZZ"].map_y), pos["ZZ"].lebar)
		# tidak ada kotak yang tumpang tindih
		for a, b in ((x, y) for i, x in enumerate(kotak) for y in kotak[i + 1 :]):
			tumpang_x = min(a.map_x + a.panjang, b.map_x + b.panjang) - max(a.map_x, b.map_x)
			tumpang_y = min(a.map_y + a.lebar, b.map_y + b.lebar) - max(a.map_y, b.map_y)
			self.assertFalse(
				tumpang_x > 0 and tumpang_y > 0,
				"{0} dan {1} tumpang tindih".format(a.rack_code, b.rack_code),
			)

	def test_bin_nonaktif_tidak_boleh_diisi(self):
		self.bin_a.db_set("disabled", 1)
		frappe.clear_document_cache("Bin Location", self.bin_a.name)
		doc = frappe.get_doc(
			{
				"doctype": "Goods Receive",
				"gudang": self.gudang.name,
				"items": [{"item_code": self.item.name, "bin_location": self.bin_a.name, "qty": 1}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_rak_nonaktif_tidak_pernah_disarankan(self):
		self.rack.db_set("disabled", 1)
		frappe.clear_document_cache("Rack", self.rack.name)
		self.assertEqual(bin_layout.candidate_bins(self.gudang.name, self.item.name), [])

	def test_mengeluarkan_lebih_dari_isi_bin_ditolak(self):
		bin_layout.move(self.item.name, self.bin_a.name, 2)
		# dulu dipotong diam-diam jadi nol; sekarang ditolak
		self.assertRaises(
			frappe.ValidationError, bin_layout.move, self.item.name, self.bin_a.name, -5
		)
		self.assertEqual(bin_layout.placed_qty(self.item.name, self.gudang.name), 2)
		# kecuali saat membatalkan dokumen: saldonya boleh sudah dipangkas reconcile
		bin_layout.move(self.item.name, self.bin_a.name, -5, allow_short=True)
		self.assertEqual(bin_layout.placed_qty(self.item.name, self.gudang.name), 0)

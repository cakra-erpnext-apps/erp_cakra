"""Kembalikan skala denah gudang yang dikecilkan dua kali oleh rack_size_to_meter.

Patch itu menganggap isi tabel Rack masih sentimeter (ukuran) dan piksel (posisi).
Padahal halaman Layout yang baru sudah menyimpan METER, jadi yang dikonversi adalah
angka yang SUDAH meter: panjang/lebar/tinggi dibagi 100 lagi dan map_x/map_y dikali
0,08 lagi. Hasilnya rak 20 m tercatat 0,2 m -- denah berskala itu jadi bintik di
pojok layar.

Kebalikannya persis: ukuran x100, posisi /0,08. Aman diulang: kalau rak terpanjang
sudah >= 1 m, tidak ada yang perlu dibesarkan.
"""

import frappe

_PX_TO_M = 0.08


def execute():
	if not frappe.db.table_exists("Rack"):
		return
	# gudang tidak punya rak sependek 1 meter; kalau ada yang >= 1 m, tabelnya waras
	if (frappe.db.sql("select max(ifnull(panjang, 0)) from `tabRack`")[0][0] or 0) >= 1:
		return

	frappe.db.sql(
		"""update `tabRack`
		   set panjang = panjang * 100, lebar = lebar * 100, tinggi = tinggi * 100,
		       map_x = map_x / %s, map_y = map_y / %s""",
		(_PX_TO_M, _PX_TO_M),
	)
	frappe.db.sql(
		"""update `tabRack`
		   set volume = ifnull(panjang, 0) * ifnull(lebar, 0) * ifnull(tinggi, 0)"""
	)
	frappe.clear_cache(doctype="Rack")

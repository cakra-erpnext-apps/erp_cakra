"""Ukuran rak & bin: sentimeter (dan piksel denah) -> METER.

Satu satuan untuk semuanya supaya tidak ada lagi angka yang harus dibagi 100 di kepala:
panjang/lebar/tinggi rak, panjang slot bin, dan koordinat denah.

Denah lama digambar 1 px = 8 cm, dan ukuran kotaknya disimpan TERPISAH dari ukuran fisik
rak (map_w/map_h). Dua sumber ukuran itu dihapus: kotak di denah sekarang MEMANG panjang x
lebar raknya. Rak yang ukuran fisiknya belum pernah diisi mewarisi ukuran kotak yang dulu
digeser tangan, jadi denahnya tidak berubah bentuk sesudah patch ini.
"""

import frappe

_PX_TO_M = 0.08  # denah lama: 1 piksel = 8 cm


def execute():
	if not frappe.db.table_exists("Rack"):
		return
	cols = set(frappe.db.get_table_columns("Rack"))

	frappe.db.sql(
		"""update `tabRack`
		   set panjang = panjang / 100, lebar = lebar / 100, tinggi = tinggi / 100"""
	)
	frappe.db.sql(
		"update `tabRack` set map_x = map_x * %s, map_y = map_y * %s", (_PX_TO_M, _PX_TO_M)
	)
	# Kotak yang dulu digeser tangan jadi ukuran fisik — hanya kalau ukuran fisiknya kosong,
	# angka yang diukur orang gudang tidak boleh ditimpa gambar.
	for kolom, field in (("map_w", "panjang"), ("map_h", "lebar")):
		if kolom in cols:
			frappe.db.sql(
				"""update `tabRack` set {field} = {kolom} * %s
				   where ifnull({field}, 0) = 0 and ifnull({kolom}, 0) > 0""".format(
					field=field, kolom=kolom
				),
				_PX_TO_M,
			)
	frappe.db.sql(
		"""update `tabRack`
		   set volume = ifnull(panjang, 0) * ifnull(lebar, 0) * ifnull(tinggi, 0)"""
	)

	for doctype in ("Rack Level", "Bin Location"):
		if frappe.db.table_exists(doctype):
			frappe.db.sql(
				"update `tab{0}` set slot_length = slot_length / 100 where ifnull(slot_length, 0) > 0".format(
					doctype
				)
			)

	# Field-nya CUSTOM FIELD yang dibuat after_migrate, sedangkan patch jalan di
	# post_model_sync -- yaitu SEBELUM after_migrate. Di site yang baru pertama kali
	# memasang app ini field itu belum ada dan get_single_value melempar error, menggagalkan
	# seluruh migrate. Kalau belum ada, memang belum ada nilai yang perlu dikonversi.
	if frappe.db.exists(
		"Custom Field", {"dt": "Stock Settings", "fieldname": "custom_bin_slot_length"}
	):
		default_slot = frappe.db.get_single_value("Stock Settings", "custom_bin_slot_length")
	else:
		default_slot = None
	if default_slot:
		frappe.db.set_single_value("Stock Settings", "custom_bin_slot_length", default_slot / 100.0)

	frappe.clear_cache(doctype="Rack")
	frappe.clear_cache(doctype="Bin Location")

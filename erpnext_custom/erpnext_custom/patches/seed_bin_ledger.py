"""Isi Bin Ledger Entry dari keadaan yang ada sekarang, lalu buang sampah lamanya.

Sebelum ini, Item Bin Qty adalah catatan utama dan tidak punya buku besar. Patch
ini membangun lapisan awal supaya FIFO punya titik mulai, dan supaya invarian
`bin_total == Bin.actual_qty` benar sejak hari pertama.

Tiga hal yang dikerjakan:

1. Baris Item Bin Qty YATIM dihapus. Di site ini semuanya yatim: 20 baris yang
   (item, gudang)-nya tidak punya baris tabBin sama sekali -- sisa impor lama.
   Kalau dibiarkan, saldonya ikut terhitung dan tiap gerakan berikutnya akan
   memicu koreksi yang tidak pernah selesai.
2. Saldo bin yang MASIH sah dijadikan lapisan pembuka.
3. Stok yang ada di ERPNext tapi belum punya tempat didaratkan ke bin penampung
   (staging), bukan dibiarkan tak tercatat -- supaya muncul di daftar kerja
   put-away alih-alih menghilang.

Umur lapisan pembuka memakai `creation` baris Item Bin Qty-nya kalau ada; kalau
tidak, waktu patch ini jalan. Keduanya tebakan, tapi jujur: yang penting urutan
relatifnya masuk akal dan barang yang datang SESUDAH ini selalu lebih muda.
"""

import frappe
from frappe.utils import flt, now_datetime

from erpnext_custom import bin_ledger


def execute():
	frappe.reload_doc("erpnext_custom", "doctype", "bin_ledger_entry")
	frappe.reload_doc("erpnext_custom", "doctype", "goods_receive_item")

	if frappe.db.count("Bin Ledger Entry"):
		return

	dibuang = _buang_yatim()
	dari_bin = _lapisan_dari_item_bin_qty()
	ke_staging = _daratkan_sisa()

	frappe.db.commit()
	print(
		"seed_bin_ledger: {0} baris Item Bin Qty yatim dibuang, "
		"{1} lapisan dibuat dari saldo bin, {2} didaratkan ke staging.".format(
			dibuang, dari_bin, ke_staging
		)
	)


def _buang_yatim():
	"""Item Bin Qty yang (item, gudang)-nya tidak punya baris Bin sama sekali."""
	n = 0
	for row in frappe.get_all("Item Bin Qty", fields=["name", "item_code", "gudang"]):
		if not frappe.db.exists("Bin", {"item_code": row.item_code, "warehouse": row.gudang}):
			frappe.delete_doc("Item Bin Qty", row.name, ignore_permissions=True, force=True)
			n += 1
	return n


def _lapisan_dari_item_bin_qty():
	"""Saldo bin yang tersisa jadi lapisan pembuka, dengan umur = creation barisnya."""
	n = 0
	for row in frappe.get_all(
		"Item Bin Qty",
		filters={"qty": [">", 0]},
		fields=["item_code", "bin_location", "gudang", "qty", "creation"],
	):
		if not bin_ledger.is_ledgered_item(row.item_code):
			continue
		bin_ledger._write(
			row.item_code,
			row.bin_location,
			flt(row.qty),
			voucher=None,
			received_on=row.creation or now_datetime(),
			qty_left=flt(row.qty),
		)
		n += 1
	return n


def _daratkan_sisa():
	"""Stok yang ada di ERPNext tapi belum punya bin -> bin penampung gudangnya."""
	n = 0
	for b in frappe.get_all(
		"Bin", filters={"actual_qty": [">", 0]}, fields=["item_code", "warehouse", "actual_qty"]
	):
		if not bin_ledger.is_tracked(b.warehouse) or not bin_ledger.is_ledgered_item(b.item_code):
			continue
		kurang = flt(b.actual_qty) - bin_ledger.bin_total(b.item_code, b.warehouse)
		if kurang <= 0.0001:
			continue
		bin_ledger._write(
			b.item_code,
			bin_ledger.staging_bin(b.warehouse),
			kurang,
			voucher=None,
			received_on=now_datetime(),
			qty_left=kurang,
		)
		n += 1
	return n

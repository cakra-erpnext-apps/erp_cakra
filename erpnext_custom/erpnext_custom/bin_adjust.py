"""Koreksi isi bin: kurangi qty, kosongkan item, atau ganti itemnya.

Bedanya dengan dua dokumen bin yang lain
----------------------------------------
Goods Receive dan Bin Replan MEMINDAHKAN barang -- total per gudang tidak berubah,
jadi keduanya tidak menyentuh stok maupun jurnal. Adjustment tidak begitu: yang
dikoreksi adalah barang yang memang TIDAK ADA lagi di gudang (susut, rusak,
salah hitung) atau ternyata item lain sejak awal. Itu selisih stok betulan.

Makanya tiap Adjustment yang disetujui otomatis membuat + menyubmit satu
**Stock Reconciliation**. Tanpa itu koreksinya membatalkan diri sendiri: buku
besar bin akan bilang 7, tabBin tetap bilang 10, dan begitu item itu bergerak
lagi `bin_ledger.doc_hook` mengukur selisih 3 lalu MENGEMBALIKANNYA ke staging.
Kalau yang dicari cuma "barangnya pindah bin", pakai Replan -- bukan dokumen ini.

Urutan pada submit
------------------
Buku besar bin ditulis DULU, Stock Reconciliation-nya belakangan. Alasannya
`doc_hook` bekerja dengan mengukur `Bin.actual_qty - bin_total()`: kalau buku
besarnya sudah lebih dulu benar, pengukuran di ujung SR hasilnya nol dan dia
tidak menempatkan apa-apa sendiri -- letak barang tetap ditentukan dokumen ini,
bukan ditebak mesin penempatan. `sle_hook` sengaja dimatikan selama itu (lihat
flag `bin_adjustment`), karena SLE disubmit SEBELUM tabBin ikut naik sehingga
pengukurannya membaca saldo lama.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, nowtime

from erpnext.stock.utils import get_stock_balance

from erpnext_custom import bin_ledger


@frappe.whitelist()
def bin_contents(bin_location):
	"""Isi bin ini sekarang, siap jadi baris dokumen.

	`qty_after` sengaja diisi sama dengan `qty_before`: yang ditarik adalah
	keadaan menurut catatan, lalu orang gudang mengubah baris yang memang beda
	dengan kenyataan. Baris yang tidak diubah ditolak saat simpan.
	"""
	rows = frappe.get_all(
		"Item Bin Qty",
		filters={"bin_location": bin_location, "qty": [">", 0]},
		fields=["item_code", "item_name", "qty", "stock_uom"],
		order_by="item_code asc",
	)
	return [
		{
			"bin_location": bin_location,
			"item_code": r.item_code,
			"item_name": r.item_name,
			"qty_before": flt(r.qty),
			"qty_after": flt(r.qty),
			"stock_uom": r.stock_uom,
		}
		for r in rows
	]


def post_stock(doc):
	"""Stock Reconciliation atas selisih yang dibuat adjustment ini. Nomornya dikembalikan.

	Selisihnya DIJUMLAHKAN per item dulu: Stock Reconciliation menetapkan qty
	AKHIR per (item, gudang), jadi dua baris bin yang menyentuh item yang sama
	harus jadi satu baris SR -- bukan dua yang saling menimpa.
	"""
	gudang = doc.gudang
	company = frappe.get_cached_value("Warehouse", gudang, "company")
	waktu = nowtime()

	delta = defaultdict(float)  # item -> perubahan qty di gudang ini
	bawa = defaultdict(float)  # item hasil switch -> nilai yang dibawa dari item lama

	saldo = {}

	def balance(item_code):
		if item_code not in saldo:
			saldo[item_code] = get_stock_balance(
				item_code, gudang, doc.posting_date, waktu, with_valuation_rate=True
			)
		return saldo[item_code]

	for row in doc.items:
		if row.new_item_code:
			delta[row.item_code] -= flt(row.qty_before)
			delta[row.new_item_code] += flt(row.qty_after)
			bawa[row.new_item_code] += flt(row.qty_before) * flt(balance(row.item_code)[1])
		else:
			delta[row.item_code] += flt(row.qty_after) - flt(row.qty_before)

	sr = frappe.new_doc("Stock Reconciliation")
	sr.company = company
	sr.purpose = "Stock Reconciliation"
	sr.set_posting_time = 1
	sr.posting_date = doc.posting_date
	sr.posting_time = waktu
	for item_code, selisih in delta.items():
		if abs(selisih) <= 0.0001:
			continue
		qty_lama, rate = balance(item_code)
		baris = sr.append(
			"items",
			{"item_code": item_code, "warehouse": gudang, "qty": flt(qty_lama) + selisih},
		)
		# Item yang belum pernah berstok di gudang ini tidak punya valuasi, dan Stock
		# Reconciliation menolak baris masuk tanpa nilai. Untuk item hasil SWITCH
		# nilainya dibawa dari item yang digantikan: barangnya sama, yang salah cuma
		# labelnya, jadi nilai persediaan totalnya tidak boleh ikut berubah.
		# Item yang SUDAH punya valuasi tidak diutak-atik -- menetapkan rate di SR
		# akan menilai ulang seluruh stok item itu, bukan cuma yang di bin ini.
		if not flt(rate) and bawa.get(item_code) and flt(baris.qty):
			baris.valuation_rate = flt(bawa[item_code]) / flt(baris.qty)

	if not sr.items:
		return None
	sr.flags.ignore_permissions = True
	sr.insert()
	sr.submit()
	return sr.name

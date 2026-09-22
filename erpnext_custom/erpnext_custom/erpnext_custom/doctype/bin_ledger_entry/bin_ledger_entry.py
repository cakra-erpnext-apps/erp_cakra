import frappe
from frappe.model.document import Document


class BinLedgerEntry(Document):
	"""Buku besar bin: satu baris = satu gerakan barang masuk/keluar sebuah bin.

	Hubungannya dengan Item Bin Qty persis seperti Stock Ledger Entry dengan Bin --
	yang ini gerakannya, yang itu saldonya. Baris masuk membawa `qty_left` sebagai
	kursor FIFO; baris keluar selalu `qty_left` nol dan menunjuk lapisan yang
	dimakannya lewat `source_ble`.

	Tidak ada yang boleh menulis ke sini lewat form. Satu-satunya penulis adalah
	erpnext_custom/bin_ledger.py.
	"""

	pass


def on_doctype_update():
	# FIFO selalu dicari per (item, gudang) dengan sisa > 0.
	frappe.db.add_index("Bin Ledger Entry", ["item_code", "gudang", "qty_left"])
	# Pembatalan dokumen mencari balik baris miliknya sendiri.
	frappe.db.add_index("Bin Ledger Entry", ["voucher_type", "voucher_no"])

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now

from erpnext_custom import bin_adjust, bin_ledger, replan
from erpnext_custom.bin_move import autoname_with_warehouse

_EPS = 0.0001


class BinAdjustment(Document):
	"""Koreksi isi bin: kurangi qty, kosongkan item, atau ganti itemnya.

	Satu bentuk baris untuk tiga pekerjaan, jadi tidak ada field "jenis adjustment"
	yang harus dijaga supaya tetap cocok dengan isinya:

	    qty_after < qty_before             qty-nya dikurangi
	    qty_after = 0                      item itu dikosongkan dari bin
	    new_item_code diisi                isinya ternyata item lain (salah label)

	Berlaku saat DIVALIDASI (submit) -- itu gerbangnya: role yang boleh submit
	di doctype ini adalah role yang boleh menyetujui koreksi (Stock User cuma bisa
	bikin draft). Sebelum itu tidak ada satu pun angka yang bergerak.

	Dampak stoknya nyata, tidak seperti Goods Receive/Replan yang cuma memindahkan:
	lihat erpnext_custom/bin_adjust.py.
	"""

	def autoname(self):
		self.name = autoname_with_warehouse(self)

	def validate(self):
		if frappe.get_cached_value("Warehouse", self.gudang, "is_group"):
			frappe.throw(
				_("{0} adalah group warehouse, pilih gudang yang menyimpan stok.").format(self.gudang)
			)
		terkunci = replan.locked_bins()
		sudah = set()
		for row in self.items:
			loc = frappe.get_cached_value(
				"Bin Location", row.bin_location, ["gudang", "rack"], as_dict=True
			)
			if loc.gudang != self.gudang:
				frappe.throw(
					_("Baris {0}: bin {1} ada di {2}, bukan di {3}.").format(
						row.idx, row.bin_location, loc.gudang, self.gudang
					)
				)
			row.rack = loc.rack
			if row.bin_location in terkunci:
				frappe.throw(
					_(
						"Baris {0}: bin {1} sedang dikunci Replan {2} yang belum disetujui. "
						"Isinya sedang dibongkar orang gudang -- selesaikan replan itu dulu."
					).format(row.idx, row.bin_location, terkunci[row.bin_location])
				)

			# Satu (item, bin) cuma boleh sekali. Baris kedua akan membaca Qty Sebelum
			# yang sudah basi begitu baris pertama dibukukan, dan koreksinya jadi dobel.
			kunci = (row.item_code, row.bin_location)
			if kunci in sudah:
				frappe.throw(
					_("Baris {0}: {1} di bin {2} sudah dikoreksi di baris lain, gabungkan jadi satu baris.").format(
						row.idx, row.item_code, row.bin_location
					)
				)
			sudah.add(kunci)

			# Tidak pernah percaya angka yang datang dari form: isi bin bisa berubah
			# antara draft disimpan dan divalidasi, dan yang dikoreksi harus keadaan
			# TERAKHIR -- bukan keadaan waktu barisnya ditarik.
			row.qty_before = bin_ledger.bin_qty(row.item_code, row.bin_location)
			if flt(row.qty_before) <= 0:
				frappe.throw(
					_("Baris {0}: bin {1} tidak berisi {2} menurut buku besar, tidak ada yang bisa dikoreksi.").format(
						row.idx, row.bin_location, row.item_code
					)
				)

			if row.new_item_code == row.item_code:
				row.new_item_code = None
			if flt(row.qty_after) < 0:
				frappe.throw(_("Baris {0}: Qty Sesudah tidak boleh minus.").format(row.idx))

			if row.new_item_code:
				if flt(row.qty_after) <= 0:
					frappe.throw(
						_("Baris {0}: Qty Sesudah 0 berarti bin dikosongkan -- kosongkan Ganti Item Ke.").format(
							row.idx
						)
					)
				if not bin_ledger.is_ledgered_item(row.new_item_code):
					frappe.throw(
						_("Baris {0}: {1} pakai batch/serial, letaknya diurus ERPNext sendiri dan tidak masuk buku besar bin.").format(
							row.idx, row.new_item_code
						)
					)
				if not frappe.get_cached_value("Item", row.new_item_code, "is_stock_item"):
					frappe.throw(
						_("Baris {0}: {1} bukan stock item, tidak bisa jadi isi bin.").format(
							row.idx, row.new_item_code
						)
					)
			else:
				if flt(row.qty_after) > flt(row.qty_before) + _EPS:
					frappe.throw(
						_(
							"Baris {0}: adjustment cuma mengurangi. Menambah barang di bin itu penerimaan "
							"(Goods Receive) atau opname, bukan koreksi."
						).format(row.idx)
					)
				if abs(flt(row.qty_after) - flt(row.qty_before)) <= _EPS:
					frappe.throw(
						_("Baris {0}: tidak ada yang dikoreksi. Ubah Qty Sesudah, atau hapus barisnya.").format(
							row.idx
						)
					)

			row.stock_uom = frappe.get_cached_value(
				"Item", row.new_item_code or row.item_code, "stock_uom"
			)

	def before_submit(self):
		self.approved_by = frappe.session.user
		self.approved_on = now()

	def on_submit(self):
		"""Buku besar bin DULU, Stock Reconciliation-nya belakangan.

		Alasannya di erpnext_custom/bin_adjust.py: `doc_hook` menutup selisih dengan
		MENGUKUR, jadi kalau buku besarnya sudah lebih dulu benar, pengukuran di ujung
		Stock Reconciliation hasilnya nol dan mesin penempatan tidak ikut menebak bin.
		"""
		for row in self.items:
			if row.new_item_code:
				# Umur barangnya IKUT: yang salah cuma labelnya, bukan kapan barangnya
				# datang. Dibaca sebelum lapisan lamanya dimakan.
				umur = _umur_tertua(row.item_code, row.bin_location)
				bin_ledger.adjust(row.item_code, row.bin_location, -flt(row.qty_before), self)
				bin_ledger.adjust(
					row.new_item_code, row.bin_location, flt(row.qty_after), self, received_on=umur
				)
			else:
				bin_ledger.adjust(
					row.item_code, row.bin_location, flt(row.qty_after) - flt(row.qty_before), self
				)

		frappe.flags.bin_adjustment = True
		try:
			sr = bin_adjust.post_stock(self)
		finally:
			frappe.flags.bin_adjustment = False
		if sr:
			self.db_set("stock_reconciliation", sr, update_modified=False)
			frappe.msgprint(
				_("Stock Reconciliation {0} dibuat untuk selisih stoknya.").format(
					frappe.utils.get_link_to_form("Stock Reconciliation", sr)
				),
				alert=True,
			)

	def on_cancel(self):
		"""Buku besar dipulihkan DULU, baru Stock Reconciliation-nya dibatalkan.

		Urutan yang sama dengan submit, alasan yang sama: kalau SR dibatalkan lebih
		dulu, `doc_hook` melihat tabBin sudah naik lagi sementara buku besar masih
		terkoreksi, lalu menaruh selisihnya ke staging -- barangnya "pindah" ke
		penampung padahal cuma pembatalan.
		"""
		bin_ledger.undo(self)
		if not self.stock_reconciliation:
			return
		sr = frappe.get_doc("Stock Reconciliation", self.stock_reconciliation)
		if sr.docstatus != 1:
			return
		frappe.flags.bin_adjustment = True
		try:
			sr.flags.ignore_permissions = True
			sr.cancel()
		finally:
			frappe.flags.bin_adjustment = False


def _umur_tertua(item_code, bin_location):
	gudang = frappe.get_cached_value("Bin Location", bin_location, "gudang")
	lapisan = bin_ledger.fifo_layers(item_code, gudang, bin_location)
	return lapisan[0].received_on if lapisan else None

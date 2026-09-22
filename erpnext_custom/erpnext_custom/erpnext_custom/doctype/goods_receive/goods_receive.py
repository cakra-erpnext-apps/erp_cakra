import frappe
from frappe import _
from frappe.utils import flt

from erpnext_custom.bin_move import BinMove


class GoodsReceive(BinMove):
	"""Put-away: memindahkan barang yang SUDAH ada stoknya ke bin tujuan.

	Tidak menyentuh stok maupun jurnal sama sekali -- stok sudah diakui di dokumen
	stoknya (PI/PR/Stock Entry) dan barangnya mendarat di bin penampung (staging).
	Dokumen inilah yang menaikkannya ke rak, atau memindahkannya dari rak ke rak.

	Aturan penempatannya (kapasitas, campur, tingkat, bin terkunci replan) ada di
	erpnext_custom/bin_move.py, dipakai bareng Bin Replan.

	Satu dokumen boleh memuat beberapa Purchase Invoice; nomor notanya ada di
	BARISNYA (`purchase_invoice`), bukan di kepala dokumen, supaya "sudah diterima
	berapa" tetap terhitung benar per nota.
	"""

	def validate(self):
		self._fill_invoice_rows()
		super().validate()

	def _fill_invoice_rows(self):
		"""Allocated diketik orang; Outstanding SELALU turunan, tidak pernah diketik.

		Dua angka yang sama-sama bisa diketik cepat atau lambat akan berbeda, dan
		tidak ada cara tahu mana yang benar.
		"""
		for row in self.invoice_items:
			# max_qty diisi saat barisnya ditarik; baris yang dibuat lewat API tanpa
			# angka itu jatuh ke qty notanya.
			batas = flt(row.max_qty) or flt(row.qty)
			row.max_qty = batas
			if flt(row.allocated) > batas + 0.0001:
				frappe.throw(
					_("Baris nota {0}: alokasi {1} lebih besar dari Outstanding-nya ({2}).").format(
						row.idx, flt(row.allocated), batas
					)
				)
			row.outstanding = batas - flt(row.allocated)

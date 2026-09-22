import frappe
from frappe import _
from frappe.utils import now

from erpnext_custom.bin_move import BinMove


class BinReplan(BinMove):
	"""Menata ulang letak barang yang SUDAH di rak: turun tingkat, dan barang tua maju.

	Perpindahannya baru berlaku saat DISETUJUI (submit) -- itulah gerbangnya: role
	yang boleh submit di doctype ini adalah role yang boleh menyetujui replan
	(Stock User cuma bisa bikin draft dan mencentang).

	Selama masih draft, semua bin yang disebut di dokumen ini -- asal MAUPUN tujuan
	-- terkunci dari barang masuk (erpnext_custom/replan.py: locked_bins). Barangnya
	sedang ada di tangan orang gudang, jadi kalau ada yang menitipkan barang lain ke
	situ, peta binnya bohong dan kapasitas bin tujuan bisa terpakai orang lain
	sebelum replannya selesai.

	Aturan penempatan (kapasitas, aturan campur, batas tingkat barang berat, daftar
	item) sama persis dengan Goods Receive; semuanya di erpnext_custom/bin_move.py.
	"""

	def before_submit(self):
		"""Checklist dulu, baru boleh disetujui.

		Gunanya kolom OK justru di sini: yang menyetujui tidak sedang menebak, dia
		menyetujui daftar yang sudah dicentang satu-satu oleh yang memindahkan.
		"""
		belum = [str(row.idx) for row in self.items if not row.done]
		if belum:
			frappe.throw(
				_(
					"Baris {0} belum dicentang OK. Centang baris yang barangnya sudah dipindah, "
					"dan hapus baris yang tidak dipindah."
				).format(", ".join(belum))
			)
		self.approved_by = frappe.session.user
		self.approved_on = now()

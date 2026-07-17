"""Pending Cash Type — master kode tipe pending cash (kasbon). Kodenya masuk ke nomor
Pending Cash (token .cmi_type_code. pada naming series; lihat erp.expedition.numbering)."""

import re

import frappe
from frappe.model.document import Document

# Kode ini ditempel MENTAH ke dalam nomor dokumen, jadi hanya huruf/angka/._- yang boleh:
# karakter lain (terutama "/" dan spasi) merusak bentuk nomor dan key counter tabSeries.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class PendingCashType(Document):
	def validate(self):
		self._validate_numbering_code()

	def _validate_numbering_code(self):
		"""Tolak kode yang tidak layak masuk nomor.

		Pernah terjadi: string naming series-nya sendiri ditempel ke Numbering Code, dan
		nomornya jadi `PC/PC/.cmi_type_code./.cmi_yy./.####/26/0001`. Divalidasi di sini
		supaya salah isinya ketahuan saat simpan master, bukan saat dokumen sudah bernomor.
		"""
		code = (self.numbering_code or "").strip()
		self.numbering_code = code
		target = code or (self.code or "").strip()
		if not target or CODE_PATTERN.match(target):
			return
		label = "Numbering Code" if code else "Code"
		frappe.throw(
			f"<b>{label}</b> dipakai langsung di dalam nomor Pending Cash, jadi hanya boleh "
			"huruf, angka, titik, garis bawah, atau strip — tanpa spasi maupun '/'. "
			f"Nilai sekarang: <b>{frappe.utils.escape_html(target)}</b>"
		)

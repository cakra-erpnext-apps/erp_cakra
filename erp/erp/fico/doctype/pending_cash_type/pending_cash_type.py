"""Pending Cash Type — master tipe pending cash (kasbon). Namanya ditempel MENTAH ke
nomor Pending Cash (token .cmi_type_code. pada naming series; lihat erp.expedition.numbering),
jadi satu field saja: `code` (label "Name")."""

import re

import frappe
from frappe.model.document import Document

# Hanya huruf/angka/._- : karakter lain (terutama "/" dan spasi) merusak bentuk nomor
# dan key counter tabSeries.
CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class PendingCashType(Document):
	def validate(self):
		"""Tolak nama yang tidak layak masuk nomor.

		Pernah terjadi: string naming series-nya sendiri ditempel ke sini, dan nomornya jadi
		`PC/PC/.cmi_type_code./.cmi_yy./.####/26/0001`. Dicek saat simpan master, bukan saat
		dokumen sudah bernomor.
		"""
		self.code = (self.code or "").strip()
		if CODE_PATTERN.match(self.code):
			return
		frappe.throw(
			"<b>Name</b> dipakai langsung di dalam nomor Pending Cash, jadi hanya boleh "
			"huruf, angka, titik, garis bawah, atau strip — tanpa spasi maupun '/'. "
			f"Nilai sekarang: <b>{frappe.utils.escape_html(self.code)}</b>"
		)

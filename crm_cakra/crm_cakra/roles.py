# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

"""Jabatan CRM, satu lapis di atas role akses bawaan.

Yang memegang izin sesungguhnya tetap Sales User / Sales Manager: permission
doctype, tingkat persetujuan margin, dan penyaringan branch (CMI Branch Access)
semuanya menempel di sana dan tidak disentuh. Jabatan di bawah ini menandai
orangnya masuk tim mana, dan tiap jabatan otomatis ikut membawa role akses
dasarnya (BASE_ROLE) -- sekali pilih di Settings > Users, dua role terpasang.

Satu-satunya yang langsung berakibat sekarang: rincian Fixed/Variable Cost di
halaman Procurement hanya untuk tim Procurement. Menu dan daftarnya sendiri
terbuka -- Marketing yang memasukkan inquiry dan menekan Submit to Procurement.
Beda kewenangan antar tingkat
Marketing (Manager / Supervisor / Sales) belum ada selain role dasarnya; kalau
nanti mau dibedakan per cabang, tempatnya di CMI Branch Access, bukan di sini.
"""

import functools

import frappe
from frappe import _

# "Marketing Manager" bukan role baru: ERPNext sudah punya (izin master UTM), dan
# dipakai ulang di sini supaya namanya seragam dengan tingkat lainnya. Fixture-nya
# sengaja menyalin definisi asli apa adanya -- jangan diubah, itu role bawaan.
MARKETING_ROLES = ("Marketing Manager", "Marketing Supervisor", "Marketing Sales")
PROCUREMENT_ROLES = ("Procurement Manager", "Procurement Operational")
JOB_ROLES = MARKETING_ROLES + PROCUREMENT_ROLES

# Role akses yang ikut dipasang bersama jabatannya. Manager dapat Sales Manager
# (lintas cabang + boleh mengatur user), sisanya Sales User.
BASE_ROLE = {
	"Marketing Manager": "Sales Manager",
	"Marketing Supervisor": "Sales User",
	"Marketing Sales": "Sales User",
	"Procurement Manager": "Sales Manager",
	"Procurement Operational": "Sales User",
}

# "Procurement Costing" sudah lebih dulu ada sebagai gerbang rincian costing dan
# tetap dihormati -- user yang memegangnya tidak kehilangan akses cuma karena
# jabatan baru ini ditambahkan. System Manager ikut lewat supaya admin tidak bisa
# mengunci dirinya sendiri dari data yang justru dia yang atur.
PROCUREMENT_ACCESS = set(PROCUREMENT_ROLES) | {"Procurement Costing", "System Manager"}


def has_procurement_access(user: str | None = None) -> bool:
	"""True kalau user termasuk tim Procurement (atau System Manager)."""
	return bool(set(frappe.get_roles(user or frappe.session.user)) & PROCUREMENT_ACCESS)


def procurement_only(fn: callable) -> callable:
	"""Gerbang server untuk data yang hanya milik tim Procurement.

	Tampilan sudah menyembunyikannya dari Marketing, tapi endpoint-nya tetap bisa
	dipanggil langsung lewat URL -- itu yang ditolak di sini.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if not has_procurement_access():
			frappe.throw(
				msg=_("Hanya tim Procurement yang bisa mengakses data ini."),
				title=_("Not Allowed"),
				exc=frappe.PermissionError,
			)

		return fn(*args, **kwargs)

	return wrapper

# Copyright (c) 2026, Cakra ERPNext Apps and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CMIItemGroupRef(Document):
	"""Baris Table MultiSelect berisi satu Item Group.

	Satu child doctype dipakai bersama oleh semua field pemilih Item Group di
	ERPNext Custom Setting (pembelian, Vehicle/Direct Use). Table MultiSelect
	TIDAK bisa dipakai di dalam grid, jadi pemilih per baris Invoice Type memakai
	Small Text berisi nama grup dipisah koma (pola yang sama dengan Roles).
	"""

	pass

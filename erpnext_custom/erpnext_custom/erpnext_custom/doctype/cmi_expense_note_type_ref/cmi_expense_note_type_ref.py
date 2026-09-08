# Copyright (c) 2026, Cakra ERPNext Apps and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CMIExpenseNoteTypeRef(Document):
	"""Baris Table MultiSelect berisi satu Expense Note Type.

	Dipakai field "Expense Note Type That Uses Cost Items" di ERPNext Custom Setting >
	Expense Note: tipe yang terdaftar di sana menampilkan tabel Cost Items, bukan panel
	Expense Items.
	"""

	pass

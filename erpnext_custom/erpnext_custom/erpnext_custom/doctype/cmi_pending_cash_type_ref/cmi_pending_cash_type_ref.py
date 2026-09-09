# Copyright (c) 2026, Cakra ERPNext Apps and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CMIPendingCashTypeRef(Document):
	"""Baris Table MultiSelect berisi satu Pending Cash Type.

	Dipakai field "Linked Other Module With Pending Cash Type" di ERPNext Custom Setting >
	Finance: tipe yang terdaftar di sana memunculkan section Connection di Pending Cash dan
	mewajibkan dokumennya ditaut.
	"""

	pass

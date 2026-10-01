# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CRMNoCostingReason(Document):
	"""Alasan sebuah quotation dibuat sebelum procurement menyetujui costing.

	Master, bukan pilihan di kode: daftarnya tumbuh mengikuti kebiasaan lapangan
	dan Sales Manager harus bisa menambahnya sendiri tanpa menunggu deploy.
	"""

	pass

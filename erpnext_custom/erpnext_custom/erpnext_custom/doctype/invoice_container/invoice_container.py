"""Invoice Container — baris container yang dihubungkan ke Sales Invoice via tab Connection.

Diisi otomatis dari Packing List / Shipping List (per BL), bisa di-add/remove manual.
Murni referensi/keterhubungan (tidak ditagih; penagihan tetap lewat tabel Items).
"""

from frappe.model.document import Document


class InvoiceContainer(Document):
	pass

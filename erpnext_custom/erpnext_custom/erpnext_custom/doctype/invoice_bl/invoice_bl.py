"""Invoice BL — daftar BL yang ditagih oleh sebuah Sales Invoice.

Satu invoice boleh mencakup BEBERAPA BL. Sebelumnya hanya ada field tunggal
`custom_bl_no`, padahal datanya sudah membantah itu (ada invoice dengan container
dari dua BL). Field lama tetap dipertahankan sebagai RINGKASAN (gabungan koma,
read-only) supaya print format dan invoice lama tidak tersentuh.

Kenapa tabel sendiri, bukan disimpulkan dari Invoice Container: 10 dari 95 BL di
Shipping List tidak punya container sama sekali, jadi menurunkannya dari container
akan menghilangkan BL-BL itu.
"""

from frappe.model.document import Document


class InvoiceBL(Document):
	pass

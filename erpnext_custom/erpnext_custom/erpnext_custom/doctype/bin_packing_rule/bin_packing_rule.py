from frappe.model.document import Document


class BinPackingRule(Document):
	"""Satu baris aturan kemasan: berapa kemasan item ini yang muat di satu bin.

	Isinya cuma data; yang menegakkan aturannya erpnext_custom/bin_layout.py.
	"""

	pass

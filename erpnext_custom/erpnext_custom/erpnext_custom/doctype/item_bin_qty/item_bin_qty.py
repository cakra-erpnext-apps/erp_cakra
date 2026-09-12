from frappe.model.document import Document


class ItemBinQty(Document):
	"""Saldo sub-ledger: berapa qty item X ada di bin Y.

	Bukan buku besar stok — total per (item, gudang) selalu <= stok ERPNext di
	gudang itu, dan dijaga begitu oleh erpnext_custom.bin_layout.
	"""

	pass

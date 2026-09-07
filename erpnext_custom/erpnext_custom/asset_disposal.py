"""Jejak pelepasan aset: aset ini TERJUAL di invoice mana, DI-SCRAP di jurnal mana.

ERPNext menyimpan jurnal scrap di `Asset.journal_entry_for_scrap`, tetapi penjualan
aset tidak meninggalkan jejak apa pun di record asetnya — nomor invoicenya hanya ada
di baris Sales Invoice Item. Handler di bawah menyalin nomor itu ke asetnya supaya
kelihatan langsung saat record aset dibuka. Laporan "Asset Disposal" (report/) tidak
bergantung pada field ini: ia tetap menelusuri Sales Invoice Item, jadi aset yang
dijual sebelum field ini ada pun tetap muncul.
"""

import frappe


def link_sales_invoice(doc, method=None):
	"""Isi (submit) atau kosongkan (cancel) Asset.custom_sales_invoice."""
	value = doc.name if doc.docstatus == 1 else None
	for row in doc.get("items") or []:
		if row.get("asset"):
			# update_modified=False: kolom turunan, jangan mengotori "Last Modified" aset.
			frappe.db.set_value("Asset", row.asset, "custom_sales_invoice", value, update_modified=False)

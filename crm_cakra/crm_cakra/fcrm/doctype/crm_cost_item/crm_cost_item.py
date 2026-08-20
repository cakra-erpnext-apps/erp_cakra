from frappe.model.document import Document
from frappe.utils import flt


class CRMCostItem(Document):
	"""Satu baris rincian biaya.

	Dipakai dua tempat:
	- CRM Cost Component.items -> rincian template, lengkap dengan harganya.
	- CRM Quotation.cost_items -> salinan rincian itu untuk satu baris produk
	  quotation (ditandai cost_key), yang boleh disesuaikan Procurement.
	"""

	pass


def compute_amount(rows):
	"""Isi amount = qty * rate, kembalikan totalnya."""
	total = 0.0
	for r in rows:
		# flt(): qty/rate dari grid bisa datang sebagai string. "2" * 3 di Python
		# menghasilkan "222", bukan 6 -- salah diam-diam, tanpa error.
		r.amount = flt(r.qty) * flt(r.rate)
		total += r.amount
	return total


def copy_row(row, **overrides):
	"""Salin baris rincian jadi dict siap append ke tabel lain."""
	out = {
		"item_name": row.item_name,
		"qty": row.qty,
		"uom": row.uom,
		"rate": row.rate,
		"remarks": row.remarks,
	}
	out.update(overrides)
	return out

"""Riwayat koreksi bin: satu baris per koreksi, sebelum dan sesudahnya berdampingan.

Yang dibaca BARIS dokumennya, bukan Bin Ledger Entry. Buku besar bin cuma tahu
pergerakannya (-3 di bin ini), sedangkan yang dicari orang di sini justru
konteksnya: isinya tadi apa, jadi apa, kenapa, dan siapa yang memvalidasi.

Cuma dokumen yang SUDAH divalidasi yang masuk -- draft belum mengubah apa pun.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Tanggal"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{
			"label": _("Adjustment"),
			"fieldname": "parent",
			"fieldtype": "Link",
			"options": "Bin Adjustment",
			"width": 210,
		},
		{
			"label": _("Bin"),
			"fieldname": "bin_location",
			"fieldtype": "Link",
			"options": "Bin Location",
			"width": 150,
		},
		{
			"label": _("Item Sebelum"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{"label": _("Qty Sebelum"), "fieldname": "qty_before", "fieldtype": "Float", "width": 100},
		{
			"label": _("Item Sesudah"),
			"fieldname": "item_after",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{"label": _("Qty Sesudah"), "fieldname": "qty_after", "fieldtype": "Float", "width": 100},
		{"label": _("Selisih"), "fieldname": "selisih", "fieldtype": "Float", "width": 90},
		{"label": _("UoM"), "fieldname": "stock_uom", "fieldtype": "Data", "width": 70},
		{"label": _("Alasan"), "fieldname": "reason", "fieldtype": "Data", "width": 110},
		{
			"label": _("Divalidasi Oleh"),
			"fieldname": "approved_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{
			"label": _("Stock Reconciliation"),
			"fieldname": "stock_reconciliation",
			"fieldtype": "Link",
			"options": "Stock Reconciliation",
			"width": 160,
		},
	]


def _data(filters):
	cond = {"docstatus": 1}
	if filters.gudang:
		cond["gudang"] = filters.gudang
	if filters.from_date and filters.to_date:
		cond["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.from_date:
		cond["posting_date"] = [">=", filters.from_date]
	elif filters.to_date:
		cond["posting_date"] = ["<=", filters.to_date]

	docs = {
		d.name: d
		for d in frappe.get_all(
			"Bin Adjustment",
			filters=cond,
			fields=["name", "posting_date", "gudang", "approved_by", "stock_reconciliation"],
		)
	}
	if not docs:
		return []

	baris = {"parent": ["in", list(docs)]}
	if filters.bin_location:
		baris["bin_location"] = filters.bin_location
	if filters.item_code:
		# Item yang dicari bisa duduk di sisi mana pun: yang dikoreksi, atau penggantinya.
		# Dua query lalu digabung -- lebih pendek daripada mengarang OR di get_all.
		nama = set()
		for field in ("item_code", "new_item_code"):
			nama |= set(
				frappe.get_all(
					"Bin Adjustment Item",
					filters={"parent": ["in", list(docs)], field: filters.item_code},
					pluck="name",
				)
			)
		baris["name"] = ["in", list(nama) or [""]]

	rows = frappe.get_all(
		"Bin Adjustment Item",
		filters=baris,
		fields=[
			"parent",
			"bin_location",
			"item_code",
			"new_item_code",
			"qty_before",
			"qty_after",
			"stock_uom",
			"reason",
		],
		order_by="parent desc, idx asc",
	)

	out = []
	for r in rows:
		doc = docs[r.parent]
		out.append(
			{
				"posting_date": doc.posting_date,
				"parent": r.parent,
				"bin_location": r.bin_location,
				"item_code": r.item_code,
				"qty_before": flt(r.qty_before),
				"item_after": r.new_item_code or r.item_code,
				"qty_after": flt(r.qty_after),
				# Selisih baris ganti-item tidak berarti (dua item berbeda), jadi dikosongkan
				# supaya tidak ada yang menjumlahkan apel dengan jeruk.
				"selisih": None if r.new_item_code else flt(r.qty_after) - flt(r.qty_before),
				"stock_uom": r.stock_uom,
				"reason": r.reason,
				"approved_by": doc.approved_by,
				"stock_reconciliation": doc.stock_reconciliation,
			}
		)
	return out

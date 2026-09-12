"""Stock per Rak: laporan bawaan "Warehouse wise Item Balance Age and Value"
ditambah kolom Rak dan Bin.

Isinya TIDAK dihitung ulang. Laporan intinya dipanggil apa adanya lalu dua kolom
disisipkan -- qty, nilai, dan umur tetap keluar dari kode ERPNext, jadi angkanya
tidak akan pernah berbeda dari laporan aslinya dan tidak perlu diikutkan kalau
ERPNext berubah.

Letak fisik diambil dari Item Bin Qty (lihat erpnext_custom/bin_layout.py). Satu
item bisa duduk di beberapa bin, jadi kolomnya berisi daftar, bukan satu nilai --
dan barisnya tidak dipecah supaya totalnya tetap sama dengan laporan aslinya.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.report.warehouse_wise_item_balance_age_and_value.warehouse_wise_item_balance_age_and_value import (
	execute as core_execute,
)

# Kolom Rak dan Bin disisipkan SESUDAH Item Group. Kolom gudang ditambahkan
# laporan inti di ujung baris, jadi menyisip di depan aman.
_SISIP = 3


def execute(filters=None):
	columns, data = core_execute(filters)[:2]

	item_codes = [row[0] for row in data if row]
	peta = _peta_rak(item_codes, (filters or {}).get("warehouse"))

	columns = (
		columns[:_SISIP]
		+ [_("Rak") + "::140", _("Bin") + "::200"]
		+ columns[_SISIP:]
	)
	for row in data:
		rak, binn = peta.get(row[0], ("", ""))
		row[_SISIP:_SISIP] = [rak, binn]

	return columns, data


def _peta_rak(item_codes, warehouse=None):
	"""{item: ("AA, AB", "AA0101A 12, AB0301C 3")} -- rak dan bin tempat item duduk.

	Qty per bin ikut ditulis supaya kelihatan sebarannya, bukan cuma daftar nama.
	"""
	if not item_codes:
		return {}

	filters = {"item_code": ["in", item_codes], "qty": [">", 0]}
	if warehouse:
		# ikut filter gudang laporan intinya, termasuk kalau yang dipilih node group
		anak = frappe.get_all("Warehouse", filters={"name": ["descendants of or self", warehouse]}, pluck="name")
		filters["gudang"] = ["in", anak or [warehouse]]

	rak_per_item = defaultdict(set)
	bin_per_item = defaultdict(list)
	for row in frappe.get_all(
		"Item Bin Qty",
		filters=filters,
		fields=["item_code", "bin_location", "rack", "qty"],
		order_by="rack, bin_location",
	):
		kode_rak = frappe.get_cached_value("Rack", row.rack, "rack_code") if row.rack else None
		kode_bin = frappe.get_cached_value("Bin Location", row.bin_location, "bin_code")
		if kode_rak:
			rak_per_item[row.item_code].add(kode_rak)
		bin_per_item[row.item_code].append("{0} {1}".format(kode_bin, flt(row.qty, 2)))

	return {
		item: (", ".join(sorted(rak_per_item.get(item, []))), ", ".join(bin_per_item.get(item, [])))
		for item in set(rak_per_item) | set(bin_per_item)
	}

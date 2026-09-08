"""Cek dashboard Expedition: tiap number card & chart benar-benar mengembalikan angka
(fieldname/filter salah ketahuan di sini, bukan sebagai kotak kosong di layar).

    bench --site erp.localhost console
    >>> from erp.expedition.test_dashboard import run; run()
"""

import json

import frappe
from frappe.desk.doctype.dashboard_chart.dashboard_chart import get as chart_get
from frappe.desk.doctype.number_card.number_card import get_result

from erp.expedition.dashboard import CARDS, CHARTS, PREFIX, WORKSPACE


def run(verbose=True):
	for spec in CARDS:
		doc = frappe.get_doc("Number Card", spec["name"])
		value = get_result(doc=doc.as_dict(), filters=doc.filters_json)
		assert value is not None, f"card {spec['name']} tidak mengembalikan nilai"
		if verbose:
			print("CARD ", spec["name"].ljust(30), "=", value)

	for spec in CHARTS:
		result = chart_get(chart_name=spec["name"])
		datasets = result.get("datasets") or []
		assert datasets, f"chart {spec['name']} tidak punya dataset"
		if verbose:
			print("CHART", spec["name"].ljust(30), len(result.get("labels") or []), "label")

	content = json.loads(frappe.db.get_value("Workspace", WORKSPACE, "content") or "[]")
	ours = [b for b in content if str(b.get("id") or "").startswith(PREFIX)]
	assert len(ours) == 1 + len(CARDS) + len(CHARTS), "blok dashboard di workspace tidak lengkap"
	# blok lain (card link ke doctype) tidak boleh ikut terhapus saat dashboard ditulis ulang
	assert len(content) > len(ours), "blok non-dashboard hilang dari workspace"
	print("\nOK")

"""Dashboard workspace Expedition: number card + chart dari dokumen Expedition sendiri.

Idempoten, dipanggil dari after_migrate. Semua blok milik dashboard ini diberi id
ber-awalan `exp-dash-` supaya bisa ditulis ulang tanpa menyentuh blok lain yang sudah
ada di workspace (header + card link ke doctype).

Chart/card sengaja `is_standard = 0` (hidup di DB, dibuat ulang tiap migrate) supaya
tidak perlu file json per chart -- definisinya cukup di sini.
"""

import json

import frappe

WORKSPACE = "Expedition"
PREFIX = "exp-dash-"

# function Count/Sum; filters memakai bentuk [doctype, field, operator, value] seperti
# filters_json bawaan (operator "Timespan" didukung, lihat Number Card bawaan ERPNext).
CARDS = [
	{
		"name": "Job Berjalan",
		"document_type": "Packing List",
		"function": "Count",
		"filters": [["Packing List", "closed", "=", 0], ["Packing List", "void", "=", 0]],
	},
	{
		"name": "Shipping List Bulan Ini",
		"document_type": "Shipping List",
		"function": "Count",
		"filters": [["Shipping List", "date", "Timespan", "this month"]],
	},
	{
		"name": "Expense Note Belum Validate",
		"document_type": "Expense Note",
		"function": "Count",
		"filters": [["Expense Note", "validated", "=", 0], ["Expense Note", "void", "=", 0]],
	},
	{
		"name": "Expense Note Belum Dibayar",
		"document_type": "Expense Note",
		"function": "Sum",
		"aggregate_function_based_on": "total_amount",
		"filters": [
			["Expense Note", "validated", "=", 1],
			["Expense Note", "paid", "=", 0],
			["Expense Note", "void", "=", 0],
		],
	},
]

# `col` = lebar blok di workspace (12 = selebar halaman).
CHARTS = [
	{
		"name": "Job per Bulan",
		"document_type": "Packing List",
		"chart_type": "Count",
		"based_on": "date",
		"type": "Bar",
		"col": 6,
		"filters": [["Packing List", "void", "=", 0]],
	},
	{
		"name": "Shipping List per Bulan",
		"document_type": "Shipping List",
		"chart_type": "Count",
		"based_on": "date",
		"type": "Bar",
		"col": 6,
	},
	{
		"name": "Container per Bulan",
		"document_type": "Shipping List",
		"chart_type": "Sum",
		"based_on": "date",
		"value_based_on": "container_count",
		"type": "Line",
		"col": 6,
	},
	{
		"name": "Biaya per Tipe Expense Note",
		"document_type": "Expense Note",
		"chart_type": "Group By",
		"group_by_type": "Sum",
		"group_by_based_on": "expense_note_type",
		"aggregate_function_based_on": "total_amount",
		"number_of_groups": 8,
		"type": "Donut",
		"col": 6,
		"filters": [["Expense Note", "void", "=", 0]],
	},
	{
		"name": "Biaya Expense Note per Bulan",
		"document_type": "Expense Note",
		"chart_type": "Sum",
		"based_on": "date",
		"value_based_on": "total_amount",
		"type": "Bar",
		"col": 12,
		"filters": [["Expense Note", "void", "=", 0]],
	},
]


def _ensure_card(spec):
	name = spec["name"]
	doc = (
		frappe.get_doc("Number Card", name)
		if frappe.db.exists("Number Card", name)
		else frappe.new_doc("Number Card")
	)
	doc.update(
		{
			"label": name,
			"type": "Document Type",
			"document_type": spec["document_type"],
			"function": spec["function"],
			"aggregate_function_based_on": spec.get("aggregate_function_based_on"),
			"filters_json": json.dumps(spec.get("filters") or []),
			"is_public": 1,
			# perbandingan bulan lalu butuh data historis; angka polos dulu.
			"show_percentage_stats": 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()


def _ensure_chart(spec):
	name = spec["name"]
	doc = (
		frappe.get_doc("Dashboard Chart", name)
		if frappe.db.exists("Dashboard Chart", name)
		else frappe.new_doc("Dashboard Chart")
	)
	group_by = spec["chart_type"] == "Group By"
	doc.update(
		{
			"chart_name": name,
			"chart_type": spec["chart_type"],
			"document_type": spec["document_type"],
			"based_on": spec.get("based_on"),
			"value_based_on": spec.get("value_based_on"),
			"group_by_type": spec.get("group_by_type"),
			"group_by_based_on": spec.get("group_by_based_on"),
			"aggregate_function_based_on": spec.get("aggregate_function_based_on"),
			"number_of_groups": spec.get("number_of_groups") or 0,
			# Group By tidak memakai sumbu waktu; sisanya per bulan, setahun ke belakang.
			"timeseries": 0 if group_by else 1,
			"timespan": None if group_by else "Last Year",
			"time_interval": None if group_by else "Monthly",
			"type": spec["type"],
			"filters_json": json.dumps(spec.get("filters") or []),
			"is_public": 1,
			"is_standard": 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()


def _block(kind, name, col):
	return {
		"id": PREFIX + frappe.scrub(name),
		"type": kind,
		"data": {f"{kind}_name": name, "col": col},
	}


def ensure_dashboard():
	for spec in CARDS:
		_ensure_card(spec)
	for spec in CHARTS:
		_ensure_chart(spec)

	w = frappe.get_doc("Workspace", WORKSPACE)
	# Blok content menunjuk chart/card lewat LABEL barisnya di tabel ini, bukan nama
	# dokumennya -- label sengaja disamakan dengan nama supaya keduanya cocok.
	w.set("number_cards", [{"number_card_name": c["name"], "label": c["name"]} for c in CARDS])
	w.set("charts", [{"chart_name": c["name"], "label": c["name"]} for c in CHARTS])

	blocks = [
		{
			"id": PREFIX + "header",
			"type": "header",
			"data": {"text": '<span class="h4"><b>Ringkasan Expedition</b></span>', "col": 12},
		}
	]
	blocks += [_block("number_card", c["name"], 3) for c in CARDS]
	blocks += [_block("chart", c["name"], c["col"]) for c in CHARTS]

	old = json.loads(w.content or "[]")
	keep = [b for b in old if not str(b.get("id") or "").startswith(PREFIX)]
	w.content = json.dumps(blocks + keep)
	w.flags.ignore_links = True
	w.save(ignore_permissions=True)
	return [c["name"] for c in CARDS], [c["name"] for c in CHARTS]

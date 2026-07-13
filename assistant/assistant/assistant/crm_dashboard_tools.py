"""Tool dashboard CRM untuk CRM Assistant (panel di halaman /crm/dashboard).

Prinsipnya sama dengan crm_tools.py: batasan ditegakkan DI KODE, bukan di prompt.

- Baca data dashboard lewat fungsi crm_cakra.api.dashboard yang SAMA dengan yang
  dipakai halaman dashboard — scope (mine/branch/all) ikut ditegakkan di sana,
  jadi assistant tidak bisa melihat angka yang tidak boleh dilihat user-nya.
- Mengubah layout hanya lewat operasi terstruktur (add/remove/move/resize),
  hanya oleh user yang memang punya izin write CRM Dashboard (admin), dan hanya
  setelah user menyetujui secara eksplisit (user_approved) — pola yang sama
  dengan crm_tools.update_status.
"""

import json

import frappe
from frappe import _

DASHBOARD_DOCTYPE = "CRM Dashboard"
DASHBOARD_NAME = "Manager Dashboard"
GRID_COLUMNS = 20

# Baris data maksimal per chart di ringkasan overview — chart panjang dipotong
# supaya satu panggilan overview tidak membengkakkan konteks model.
OVERVIEW_MAX_ROWS = 12

# Katalog widget yang dikenal frontend (DashboardItem.vue): name -> type.
# Sumber kebenaran: default layout di crm_dashboard.py + pilihan AddChartModal.vue.
# Kalau chart baru ditambahkan di crm_cakra.api.dashboard, daftarkan juga di sini.
WIDGET_TYPES = {
	# number_chart
	"total_leads": "number_chart",
	"ongoing_inquiries": "number_chart",
	"average_ongoing_inquiry_value": "number_chart",
	"won_inquiries": "number_chart",
	"average_won_inquiry_value": "number_chart",
	"average_inquiry_value": "number_chart",
	"average_time_to_close_a_lead": "number_chart",
	"average_time_to_close_a_inquiry": "number_chart",
	"open_quotations": "number_chart",
	"quotation_value_won": "number_chart",
	"quotation_win_rate": "number_chart",
	"expiring_quotations": "number_chart",
	# axis_chart
	"sales_trend": "axis_chart",
	"forecasted_revenue": "axis_chart",
	"funnel_conversion": "axis_chart",
	"inquiries_by_stage_axis": "axis_chart",
	"lost_inquiry_reasons": "axis_chart",
	"inquiries_by_territory": "axis_chart",
	"inquiries_by_salesperson": "axis_chart",
	"quotations_by_status": "axis_chart",
	"inquiry_trend_by_business_unit": "axis_chart",
	"inquiry_trend_by_job_service": "axis_chart",
	"inquiry_trend_by_transportation_mode": "axis_chart",
	"inquiry_trend_by_branch": "axis_chart",
	"inquiries_by_job_service": "axis_chart",
	"top_business_unit": "axis_chart",
	"top_type_of_inquiry": "axis_chart",
	"top_accounts": "axis_chart",
	"top_routes": "axis_chart",
	"win_rate_by_business_unit": "axis_chart",
	# donut_chart
	"inquiries_by_stage_donut": "donut_chart",
	"leads_by_source": "donut_chart",
	"inquiries_by_source": "donut_chart",
	"inquiries_by_business_unit": "donut_chart",
	"inquiries_by_transportation_mode": "donut_chart",
	# outstanding_table
	"my_outstanding_quotations": "outstanding_table",
	"my_outstanding_inquiries": "outstanding_table",
}

# Ukuran default (w, h) per tipe saat widget ditambahkan tanpa posisi eksplisit —
# mengikuti kebiasaan AddChartModal.vue / default layout.
DEFAULT_SIZE = {
	"number_chart": (7, 3),
	"axis_chart": (10, 9),
	"donut_chart": (10, 9),
	"outstanding_table": (10, 10),
	"spacer": (4, 2),
}


def _dashboard_api():
	from crm_cakra.api import dashboard

	return dashboard


def _load_layout() -> list[dict]:
	if not frappe.db.exists(DASHBOARD_DOCTYPE, DASHBOARD_NAME):
		from crm_cakra.fcrm.doctype.crm_dashboard.crm_dashboard import create_default_manager_dashboard

		return json.loads(create_default_manager_dashboard())
	return json.loads(frappe.db.get_value(DASHBOARD_DOCTYPE, DASHBOARD_NAME, "layout") or "[]")


def _compact_item(item: dict) -> dict:
	"""Ringkas satu widget dashboard untuk konsumsi model."""
	out = {
		"name": item.get("name"),
		"type": item.get("type"),
		"id": (item.get("layout") or {}).get("i"),
		"position": {k: (item.get("layout") or {}).get(k) for k in ("x", "y", "w", "h")},
	}
	data = item.get("data")
	if not isinstance(data, dict):
		return out

	if item.get("type") == "number_chart":
		for k in ("title", "value", "delta", "deltaSuffix", "prefix", "suffix", "tooltip"):
			if data.get(k) not in (None, ""):
				out[k] = data.get(k)
		return out

	out["title"] = data.get("title")
	if data.get("subtitle"):
		out["subtitle"] = data.get("subtitle")
	rows = data.get("data") or []
	out["rows"] = rows[:OVERVIEW_MAX_ROWS]
	if len(rows) > OVERVIEW_MAX_ROWS:
		out["rows_truncated"] = f"{OVERVIEW_MAX_ROWS} dari {len(rows)} baris (pakai crm_dashboard_get_chart untuk lengkap)"
	return out


def overview(from_date=None, to_date=None, scope=None, user=None, branch=None):
	"""Seluruh dashboard (layout + data ringkas) persis seperti yang dilihat user.

	Scope & permission ditegakkan oleh crm_cakra.api.dashboard.get_dashboard
	(sales user only; scope 'all' hanya manager).
	"""
	d = _dashboard_api()
	layout = d.get_dashboard(from_date=from_date, to_date=to_date, user=user, scope=scope, branch=branch)
	items = [_compact_item(it) for it in layout if it.get("type") != "spacer"]
	# Urutkan sesuai tampilan (atas ke bawah, kiri ke kanan) supaya "chart paling
	# atas" dalam jawaban model sama dengan yang dilihat user.
	items.sort(key=lambda i: ((i.get("position") or {}).get("y") or 0, (i.get("position") or {}).get("x") or 0))
	return {
		"dashboard": DASHBOARD_NAME,
		"period": {"from_date": str(from_date or ""), "to_date": str(to_date or "")},
		"scope": scope or "mine",
		"filter_user": user or None,
		"filter_branch": branch or None,
		"widgets": items,
	}


def get_chart(name: str, from_date=None, to_date=None, scope=None, user=None, branch=None):
	"""Data LENGKAP satu widget dashboard (tanpa pemotongan baris)."""
	wtype = WIDGET_TYPES.get(name)
	if not wtype:
		return {
			"_error": f"Widget '{name}' tidak dikenal. Pilihan: {', '.join(sorted(WIDGET_TYPES))}"
		}
	d = _dashboard_api()
	data = d.get_chart(
		name=name, type=wtype, from_date=from_date, to_date=to_date, user=user, scope=scope, branch=branch
	)
	return {"name": name, "type": wtype, "data": data}


def get_layout():
	"""Susunan dashboard saat ini + katalog widget yang tersedia (untuk edit)."""
	layout = _load_layout()
	catalog = {}
	for n, t in WIDGET_TYPES.items():
		catalog.setdefault(t, []).append(n)
	in_use = {it.get("name") for it in layout}
	return {
		"dashboard": DASHBOARD_NAME,
		"grid_columns": GRID_COLUMNS,
		"note": (
			"x,y = posisi (kolom, baris), w,h = lebar/tinggi. Lebar grid total "
			f"{GRID_COLUMNS} kolom. 'id' (i) unik per widget — pakai untuk edit."
		),
		"items": [
			{
				"name": it.get("name"),
				"type": it.get("type"),
				"id": (it.get("layout") or {}).get("i"),
				**{k: (it.get("layout") or {}).get(k) for k in ("x", "y", "w", "h")},
			}
			for it in layout
		],
		"available_widgets": catalog,
		"not_yet_used": sorted(n for n in WIDGET_TYPES if n not in in_use),
		"editable": bool(
			frappe.has_permission(DASHBOARD_DOCTYPE, ptype="write", doc=DASHBOARD_NAME)
		),
	}


def _find_item(layout: list[dict], key: str):
	"""Cari widget berdasarkan id (layout.i) atau name. Name yang muncul lebih dari
	sekali dianggap ambigu — model harus memakai id."""
	by_id = [it for it in layout if (it.get("layout") or {}).get("i") == key]
	if by_id:
		return by_id[0], None
	by_name = [it for it in layout if it.get("name") == key]
	if not by_name:
		return None, f"Widget '{key}' tidak ada di layout. Cek dulu dengan crm_dashboard_get_layout."
	if len(by_name) > 1:
		ids = ", ".join((it.get("layout") or {}).get("i") or "?" for it in by_name)
		return None, f"'{key}' ada {len(by_name)} buah. Pakai id yang spesifik: {ids}"
	return by_name[0], None


def _as_int(val, field, minimum=0):
	try:
		iv = int(val)
	except (TypeError, ValueError):
		raise ValueError(f"Nilai {field} harus angka, bukan {val!r}.")
	if iv < minimum:
		raise ValueError(f"Nilai {field} minimal {minimum}.")
	return iv


def edit_layout(actions, user_approved=False):
	"""Ubah layout dashboard dengan daftar operasi add/remove/move/resize.

	Penjagaan (semua di kode):
	  1. hanya user dengan izin write CRM Dashboard (admin) — dashboard ini satu
	     untuk semua user, jadi bukan wewenang sales user biasa;
	  2. hanya setelah user menyetujui secara eksplisit (user_approved);
	  3. widget baru harus ada di katalog WIDGET_TYPES (atau 'spacer');
	  4. posisi divalidasi terhadap lebar grid.
	"""
	if not user_approved:
		return {
			"_error": "Perubahan layout butuh persetujuan user. Jelaskan dulu perubahan yang akan "
			"dilakukan, lalu panggil ulang dengan user_approved=true setelah user setuju."
		}

	if not frappe.has_permission(DASHBOARD_DOCTYPE, ptype="write", doc=DASHBOARD_NAME):
		return {
			"_error": "User ini tidak punya izin mengubah layout dashboard (butuh akses admin). "
			"Layout dashboard berlaku untuk semua user, jadi hanya admin yang boleh mengubahnya."
		}

	if isinstance(actions, str):
		try:
			actions = json.loads(actions)
		except ValueError:
			return {"_error": "Parameter actions harus berupa array operasi, bukan teks bebas."}
	if not isinstance(actions, list) or not actions:
		return {"_error": "Parameter actions harus berupa array berisi minimal satu operasi."}

	layout = _load_layout()
	applied = []

	try:
		for act in actions:
			op = (act.get("op") or "").strip().lower()

			if op == "add":
				name = (act.get("name") or "").strip()
				if name != "spacer" and name not in WIDGET_TYPES:
					return {
						"_error": f"Widget '{name}' tidak dikenal. Pilihan: spacer, "
						+ ", ".join(sorted(WIDGET_TYPES))
					}
				wtype = "spacer" if name == "spacer" else WIDGET_TYPES[name]
				def_w, def_h = DEFAULT_SIZE.get(wtype, (10, 9))
				w = _as_int(act.get("w", def_w), "w", 1)
				h = _as_int(act.get("h", def_h), "h", 1)
				if w > GRID_COLUMNS:
					w = GRID_COLUMNS
				# Tanpa posisi -> taruh di baris paling bawah.
				bottom = max(
					(((it.get("layout") or {}).get("y") or 0) + ((it.get("layout") or {}).get("h") or 0))
					for it in layout
				) if layout else 0
				x = _as_int(act.get("x", 0), "x")
				y = _as_int(act.get("y", bottom), "y")
				if x + w > GRID_COLUMNS:
					return {"_error": f"x+w ({x}+{w}) melebihi lebar grid {GRID_COLUMNS}."}
				item_id = f"{name}_{frappe.generate_hash(length=4)}"
				layout.append({
					"name": name,
					"type": wtype,
					"layout": {"x": x, "y": y, "w": w, "h": h, "i": item_id},
				})
				applied.append(f"add {name} (id {item_id}) di x={x},y={y},w={w},h={h}")

			elif op == "remove":
				key = (act.get("id") or act.get("name") or "").strip()
				item, err = _find_item(layout, key)
				if err:
					return {"_error": err}
				layout.remove(item)
				applied.append(f"remove {item.get('name')} (id {(item.get('layout') or {}).get('i')})")

			elif op in ("move", "resize"):
				key = (act.get("id") or act.get("name") or "").strip()
				item, err = _find_item(layout, key)
				if err:
					return {"_error": err}
				lay = item.setdefault("layout", {})
				if op == "move":
					lay["x"] = _as_int(act.get("x", lay.get("x", 0)), "x")
					lay["y"] = _as_int(act.get("y", lay.get("y", 0)), "y")
				else:
					lay["w"] = _as_int(act.get("w", lay.get("w", 4)), "w", 1)
					lay["h"] = _as_int(act.get("h", lay.get("h", 2)), "h", 1)
				if (lay.get("x", 0) + lay.get("w", 1)) > GRID_COLUMNS:
					return {
						"_error": f"{op} {key}: x+w ({lay.get('x')}+{lay.get('w')}) melebihi "
						f"lebar grid {GRID_COLUMNS}."
					}
				applied.append(
					f"{op} {item.get('name')} -> x={lay.get('x')},y={lay.get('y')},w={lay.get('w')},h={lay.get('h')}"
				)

			else:
				return {"_error": f"Operasi '{op}' tidak dikenal. Pilihan: add, remove, move, resize."}
	except ValueError as e:
		return {"_error": str(e)}

	# Data widget tidak ikut disimpan ke layout (sama seperti tombol Save di UI).
	for it in layout:
		it.pop("data", None)

	doc = frappe.get_doc(DASHBOARD_DOCTYPE, DASHBOARD_NAME)
	doc.layout = json.dumps(layout, ensure_ascii=False)
	doc.save()
	frappe.db.commit()

	return {"ok": True, "applied": applied, "total_widgets": len(layout)}

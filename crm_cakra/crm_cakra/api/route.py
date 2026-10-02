"""Tombol Check di tabel Shipment Route: perkiraan Est KM & Est Days satu baris.

Urutannya sengaja dari yang pasti ke yang menebak:
1. Peta OSM -- titik lokasi (dicari lewat Nominatim kalau belum di-pin) lalu
   jarak jalan dari OSRM. Angkanya bisa dicek ulang di Google Maps.
2. AI (akun di Assistant Settings) -- hanya kalau peta tidak bisa menjawab,
   mis. rute antar pulau yang melewati laut, atau nama lokasi tak dikenal peta.
Hasilnya isian awal; user tetap boleh menimpanya.
"""

import json
import math
import re

import frappe
from frappe import _
from frappe.utils import flt

# ponytail: 8 jam nyetir per hari untuk truk, ganti jadi setting kalau ops minta angka lain
DRIVING_HOURS_PER_DAY = 8


def _days(hours):
	return max(1, math.ceil(flt(hours) / DRIVING_HOURS_PER_DAY)) if flt(hours) else 0


def _ensure_coords(location):
	"""Pin otomatis lokasi yang dibuat cepat tanpa koordinat, dari Nominatim."""
	row = frappe.db.get_value(
		"Fleet Location", location, ["latitude", "longitude", "alamat"], as_dict=True
	)
	if not row:
		frappe.throw(_("Lokasi {0} tidak ditemukan.").format(location))
	if row.latitude and row.longitude:
		return

	from erp.fleet.geocode import search_address

	hits = search_address(row.alamat or location, 1) or (search_address(location, 1) if row.alamat else [])
	if not hits:
		frappe.throw(_("Lokasi {0} tidak ditemukan di peta.").format(location))
	frappe.db.set_value(
		"Fleet Location",
		location,
		{"latitude": hits[0]["lat"], "longitude": hits[0]["lon"]},
		update_modified=False,
	)


def _from_map(origin, destination):
	from erp.fleet.doctype.fleet_route.fleet_route import get_distance

	_ensure_coords(origin)
	_ensure_coords(destination)
	r = get_distance(origin, destination)
	if not flt(r.get("distance_km")):
		frappe.throw(_("Rute tidak ditemukan di peta."))
	return flt(r["distance_km"], 1), _days(r.get("duration_hour"))


def _from_ai(origin, destination, detail):
	from assistant.assistant.llm import create_message

	prompt = (
		"Perkirakan jarak dan lama pengiriman kargo ekspedisi di Indonesia.\n"
		f"Origin: {origin}\nDestination: {destination}\n"
		+ (f"Detail alamat: {detail}\n" if detail else "")
		+ "Kalau rutenya menyeberang laut, hitung gabungan darat + kapal. "
		'Jawab HANYA JSON: {"km": <angka>, "days": <angka>}'
	)
	res = create_message(
		"Kamu analis logistik. Jawab singkat, hanya JSON.",
		[{"role": "user", "content": prompt}],
		# Model reasoning (Qwen) memakai token untuk berpikir dulu; 200 habis sebelum menjawab.
		max_tokens=4000,
	)
	text = " ".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
	m = re.search(r"\{.*?\}", text, re.S)
	data = json.loads(m.group(0)) if m else {}
	km, days = flt(data.get("km"), 1), math.ceil(flt(data.get("days")))
	if not km:
		frappe.throw(_("AI tidak bisa memperkirakan rute ini."))
	return km, max(days, 1)


@frappe.whitelist()
def estimate(origin: str, destination: str, detail_address: str | None = None):
	if not origin or not destination:
		frappe.throw(_("Isi Origin dan Destination dulu."))

	try:
		km, days = _from_map(origin, destination)
		return {"est_km": km, "est_days": days, "source": "map"}
	except Exception:
		frappe.clear_last_message()
		map_error = frappe.get_traceback()

	try:
		km, days = _from_ai(origin, destination, detail_address)
	except Exception:
		frappe.log_error(map_error + "\n\n" + frappe.get_traceback(), "Shipment Route: Check gagal")
		frappe.throw(_("Rute {0} -> {1} tidak bisa diperkirakan. Isi Est KM / Est Days manual.").format(origin, destination))
	return {"est_km": km, "est_days": days, "source": "ai"}


def sync_route_header(doc, origin_field="origin", destination_field="destination"):
	"""Field rute tunggal di header = baris pertama tabel routes.

	Header dipertahankan karena dibaca banyak tempat (dashboard, email procurement,
	estimasi, print). Dokumen lama tanpa tabel tidak disentuh.
	"""
	rows = [r for r in doc.get("routes") or [] if r.origin and r.destination]
	if rows:
		doc.set(origin_field, rows[0].origin)
		doc.set(destination_field, rows[0].destination)
	return rows


def joined(rows, fieldname):
	"""'A, B, C' tanpa duplikat, urutan sesuai tabel."""
	return ", ".join(dict.fromkeys(r.get(fieldname) for r in rows if r.get(fieldname)))


def copy_routes(source, target):
	target.set("routes", [])
	for r in source.get("routes") or []:
		target.append(
			"routes",
			{k: r.get(k) for k in ("origin", "destination", "detail_address", "est_km", "est_days")},
		)

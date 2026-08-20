"""Pencarian alamat untuk mengisi titik Fleet Location.

Nominatim = mesin pencari alamat resmi OpenStreetMap. Gratis, tanpa API key,
data yang sama dengan peta yang sudah dipakai di form ini.

Dilewatkan server, bukan dipanggil langsung dari browser, karena tiga hal:
User-Agent yang bisa diidentifikasi (Nominatim memblokir UA generik), cache
bersama antar user, dan jeda antar permintaan yang hanya bisa ditegakkan di
satu tempat.
"""

import time

import frappe
import requests
from frappe import _

NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Syarat pemakaian Nominatim: aplikasi harus menyebut identitasnya. UA generik
# (python-requests, browser polos) ditolak dengan 403.
UA = "ERPCakra Fleet Location (cakraindo.it@gmail.com)"

TIMEOUT = 15
CACHE_TTL = 24 * 60 * 60  # alamat nyaris tidak pernah pindah dalam sehari
MIN_CHARS = 3


def _throttle():
	"""Nominatim membatasi 1 permintaan per detik per sumber.

	Seluruh user lewat satu IP server, jadi jaraknya dijaga di sini. Tanpa ini
	pemakaian normal beberapa sales sekaligus bisa membuat IP kantor diblokir.
	"""
	cache = frappe.cache()
	last = float(cache.get_value("fleet_geocode_last") or 0)
	wait = 1.0 - (time.time() - last)
	if wait > 0:
		time.sleep(min(wait, 1.0))
	cache.set_value("fleet_geocode_last", time.time())


def _label(row: dict) -> tuple[str, str]:
	"""Pisahkan nama tempat dari sisa alamatnya.

	display_name Nominatim itu satu baris panjang ("Pelabuhan Belawan, Medan
	Belawan, Medan, Sumatera Utara, 20411, Indonesia"). Bagian pertama dipakai
	sebagai judul saran, sisanya jadi keterangan kecil di bawahnya.
	"""
	full = row.get("display_name") or ""
	head = row.get("name") or full.split(",")[0].strip()
	rest = full[len(head) :].lstrip(", ") if full.startswith(head) else full
	return head, rest


@frappe.whitelist()
def search_address(q: str, limit: int = 6):
	"""Saran alamat untuk kata kunci q.

	Mengembalikan list saran; list kosong berarti tidak ketemu ATAU layanannya
	sedang tidak bisa dihubungi. Sengaja tidak melempar error: ini jalan di
	tiap ketikan, dan dialog yang menyalak saat orang sedang mengetik lebih
	mengganggu daripada saran yang tidak muncul.
	"""
	q = (q or "").strip()
	if len(q) < MIN_CHARS:
		return []

	key = f"fleet_geocode::{q.lower()}"
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return cached

	_throttle()
	try:
		res = requests.get(
			NOMINATIM,
			params={
				"q": q,
				"format": "jsonv2",
				"limit": frappe.utils.cint(limit) or 6,
				# Dibatasi Indonesia: tanpa ini "Medan" juga memunculkan kota di
				# Spanyol dan Amerika, dan saran yang tidak relevan bikin salah pilih.
				"countrycodes": "id",
				"accept-language": "id",
			},
			headers={"User-Agent": UA},
			timeout=TIMEOUT,
		)
		res.raise_for_status()
		rows = res.json()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Fleet geocode: Nominatim gagal")
		return []

	out = []
	for row in rows:
		try:
			lat, lon = float(row["lat"]), float(row["lon"])
		except (KeyError, TypeError, ValueError):
			continue
		head, rest = _label(row)
		out.append(
			{
				"label": head,
				"detail": rest,
				"address": row.get("display_name") or head,
				"lat": round(lat, 6),
				"lon": round(lon, 6),
			}
		)

	frappe.cache().set_value(key, out, expires_in_sec=CACHE_TTL)
	return out

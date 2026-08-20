import frappe
import requests
from frappe import _
from frappe.model.document import Document

# OSRM publik: profil "driving" memilih rute tercepat, jadi otomatis lewat jalan
# besar -- bukan jalan tikus. Gratis, tanpa API key.
#
# Dipanggil paling banyak SEKALI per pasang lokasi seumur hidup: hasilnya disimpan
# sebagai Fleet Route dan dipakai terus. Dengan 12 lokasi, seluruh kemungkinan
# rutenya cuma 132 panggilan, itu pun tersebar seiring pemakaian.
OSRM = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
TIMEOUT = 25


class FleetRoute(Document):
	@staticmethod
	def default_list_data():
		columns = [
			{"label": "Origin", "type": "Link", "key": "origin", "width": "14rem"},
			{"label": "Destination", "type": "Link", "key": "destination", "width": "14rem"},
			{"label": "Distance (KM)", "type": "Float", "key": "distance_km", "width": "10rem"},
			{"label": "Duration (Hour)", "type": "Float", "key": "duration_hour", "width": "10rem"},
			{"label": "Fetched At", "type": "Datetime", "key": "fetched_at", "width": "10rem"},
		]
		rows = ["name", "origin", "destination", "distance_km", "duration_hour", "fetched_at"]
		return {"columns": columns, "rows": rows}


def _coords(location):
	"""Titik sebuah Fleet Location. Tanpa pin di peta, rutenya tidak bisa dihitung."""
	row = frappe.db.get_value("Fleet Location", location, ["latitude", "longitude"], as_dict=True)
	if not row:
		frappe.throw(_("Lokasi {0} tidak ditemukan.").format(location))
	if not row.latitude or not row.longitude:
		frappe.throw(
			_("Lokasi {0} belum punya titik koordinat. Buka lokasinya lalu pin di peta.").format(location)
		)
	return row.latitude, row.longitude


@frappe.whitelist()
def gmap_url(origin: str, destination: str) -> str:
	"""Link Google Maps Directions untuk sepasang lokasi, mode mobil.

	Dipakai user untuk membandingkan angka KM kita dengan Google Maps. Pakai
	koordinat, bukan nama lokasi: nama internal seperti "RT.01" tidak berarti
	apa-apa buat Google, sedangkan pin-nya sudah pasti titik yang kita maksud.
	"""
	if not origin or not destination:
		frappe.throw(_("Loading dan Unloading harus diisi dulu."))

	lat1, lon1 = _coords(origin)
	lat2, lon2 = _coords(destination)
	return (
		"https://www.google.com/maps/dir/?api=1"
		f"&origin={lat1},{lon1}&destination={lat2},{lon2}&travelmode=driving"
	)


@frappe.whitelist()
def get_distance(origin: str, destination: str, refresh: int | str = 0):
	"""Jarak jalan origin -> destination dalam KM.

	Arahnya disimpan terpisah (A->B tidak diasumsikan sama dengan B->A) karena
	jalan satu arah dan larangan belok membuat keduanya bisa beda.

	Kegagalan panggilan TIDAK disimpan: kalau OSRM sedang tidak bisa dihubungi,
	biarkan dicoba lagi nanti, jangan mengunci angka kosong selamanya.
	"""
	if not origin or not destination:
		frappe.throw(_("Origin dan Destination harus diisi."))

	if origin == destination:
		return {"distance_km": 0.0, "duration_hour": 0.0, "cached": True}

	existing = frappe.db.get_value(
		"Fleet Route",
		{"origin": origin, "destination": destination},
		["name", "distance_km", "duration_hour"],
		as_dict=True,
	)
	if existing and not frappe.utils.cint(refresh):
		return {
			"distance_km": existing.distance_km,
			"duration_hour": existing.duration_hour,
			"cached": True,
		}

	lat1, lon1 = _coords(origin)
	lat2, lon2 = _coords(destination)

	try:
		res = requests.get(
			OSRM.format(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2), timeout=TIMEOUT
		)
		res.raise_for_status()
		data = res.json()
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Fleet Route: OSRM gagal")
		frappe.throw(_("Gagal menghitung jarak rute: {0}").format(e))

	if data.get("code") != "Ok" or not data.get("routes"):
		frappe.throw(
			_("Rute {0} -> {1} tidak ditemukan mesin rute ({2}).").format(
				origin, destination, data.get("code") or "?"
			)
		)

	route = data["routes"][0]
	distance_km = round((route.get("distance") or 0) / 1000.0, 1)
	duration_hour = round((route.get("duration") or 0) / 3600.0, 1)

	values = {
		"distance_km": distance_km,
		"duration_hour": duration_hour,
		"fetched_at": frappe.utils.now(),
	}
	if existing:
		frappe.db.set_value("Fleet Route", existing.name, values)
	else:
		doc = frappe.get_doc(
			{"doctype": "Fleet Route", "origin": origin, "destination": destination, **values}
		)
		# Cache, bukan data yang diketik user: sales boleh memicunya tanpa hak tulis.
		doc.insert(ignore_permissions=True)

	return {"distance_km": distance_km, "duration_hour": duration_hour, "cached": False}

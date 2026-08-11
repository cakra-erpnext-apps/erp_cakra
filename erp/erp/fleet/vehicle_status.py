"""Status kendaraan di monitor GPS dan Monitoring Board.

SATU tempat, dipakai dua halaman: aturan status pernah tersebar di gps_monitor.py dan
monitoring_board.py dan langsung menyimpang satu sama lain. Halaman baru cukup memanggil
`status_map()`, jangan menyalin aturannya.

Urutan PRIORITAS (yang cocok pertama menang, jadi urutan daftar ini = aturannya):

    1 Suspect        diam >= 5 menit di dalam radius Fleet Location bercentang Danger
    2 Suspend        note terakhir unit dicentang Suspend oleh user
    3 Moving No Job  bergerak, tidak punya job, dan sudah keluar dari radius garasi
    4 Offline Active punya job + driver, tapi perangkatnya berhenti mengirim data
    5 Incident       ada Incident (NCR/LAKA) yang Tgl Selesai Perbaikan-nya masih kosong
    6 Maintenance    ada Maintenance yang Tgl Keluar-nya masih kosong
    7 Not Active     tidak pernah kirim data, atau diam/hilang lebih dari 30 hari
    8 On Job         punya job aktif dan tidak ada isu apa pun
      Idle           default: tidak ada job, tidak ada isu (mis. parkir di garasi)

Idle sengaja ditambahkan di luar delapan status permintaan user: tanpa itu, truk yang
parkir tenang di garasi akan dilabeli "On Job" padahal tidak sedang bekerja.
"""

import math

import frappe
from frappe.utils import get_datetime, now_datetime

# Ambang waktu. Diletakkan di sini supaya bisa disetel satu tempat kalau lapangan bicara lain.
STOP_MINUTES = 5  # diam di titik yang sama -> bahan status Suspect
OFFLINE_MINUTES = 15  # tidak ada kiriman data -> dianggap offline
NOT_ACTIVE_DAYS = 30  # tidak ada data / tidak bergerak sama sekali -> Not Active
MOVING_MINUTES = 5  # posisi berubah dalam rentang ini -> dianggap sedang bergerak

# Nama status + warna badge. Dikirim ke JS supaya kedua halaman memakai palet yang sama
# dan status baru tidak perlu ditambahkan dua kali di sisi klien.
STATUS_COLORS = {
	"Suspect": "background:#fee2e2;color:#991b1b;",
	"Suspend": "background:#fef3c7;color:#92400e;",
	"Moving No Job": "background:#ffedd5;color:#9a3412;",
	"Offline Active": "background:#e0e7ff;color:#3730a3;",
	"Incident": "background:#fecaca;color:#7f1d1d;",
	"Maintenance": "background:#ede9fe;color:#5b21b6;",
	"Not Active": "background:#e5e7eb;color:#374151;",
	"On Job": "background:#dbeafe;color:#1e40af;",
	"Idle": "background:var(--bg-light-gray,#f3f4f6);color:var(--text-muted);",
}


def _minutes_since(value, now):
	if not value:
		return None
	return (now - get_datetime(value)).total_seconds() / 60


def _km(lat1, lon1, lat2, lon2):
	"""Jarak haversine dalam km. Cukup untuk geofence radius kilometeran."""
	r = 6371.0
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp = math.radians(lat2 - lat1)
	dl = math.radians(lon2 - lon1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * r * math.asin(math.sqrt(a))


def _inside(lat, lon, spots):
	"""True kalau (lat, lon) berada di dalam radius salah satu lokasi."""
	if lat is None or lon is None:
		return False
	for s in spots:
		if s.latitude and s.longitude and _km(lat, lon, s.latitude, s.longitude) <= (s.radius_km or 5):
			return True
	return False


def _locations(flag):
	return frappe.get_all(
		"Fleet Location",
		filters={flag: 1, "disabled": 0},
		fields=["name", "latitude", "longitude", "radius_km"],
	)


def _suspended_vehicles():
	"""Unit yang note TERAKHIR-nya dicentang Suspend.

	Sengaja dibaca dari note terakhir, bukan dari kolom di Vehicle: melepas suspend
	cukup dengan membuat note baru tanpa centang, sehingga alasan pasang dan lepasnya
	sama-sama punya jejak.
	"""
	rows = frappe.db.sql(
		"""select vehicle, suspend from `tabMonitoring Notes`
		   where ifnull(vehicle, '') != '' order by ifnull(note_date, creation)""",
		as_dict=True,
	)
	last = {}
	for r in rows:
		last[r.vehicle] = r.suspend  # yang terakhir menang
	return {v for v, s in last.items() if s}


def gps_info():
	"""Posisi terakhir tiap kendaraan: {vehicle: {latitude, longitude, last_seen, moved_at}}.

	`last_seen`/`moved_at` diisi push_position(). Dokumen lama yang belum pernah lewat
	sana tidak punya keduanya, jadi `modified` dipakai sebagai perkiraan terbaik.
	"""
	info = {}
	for g in frappe.db.sql(
		"""select vehicle, latitude, longitude, last_seen, moved_at, modified
		   from `tabGPS Vehicle` where ifnull(vehicle, '') != '' order by modified""",
		as_dict=True,
	):
		g.last_seen = g.last_seen or g.modified
		g.moved_at = g.moved_at or g.modified
		info[g.vehicle] = g
	return info


def status_map(jobs, gps=None):
	"""{vehicle: status} untuk semua kendaraan yang punya data GPS atau job.

	`jobs` = {vehicle: <apa pun yang truthy>} hasil query job aktif milik pemanggil
	(item Dispatch Order assigned yang belum Lanjut Job / Menuju Garasi).
	"""
	now = now_datetime()
	gps = gps if gps is not None else gps_info()
	danger = _locations("is_danger")
	garasi = _locations("is_garasi")
	suspended = _suspended_vehicles()

	open_incident = set(
		frappe.get_all(
			"Incident",
			filters={"finish_date": ["is", "not set"], "vehicle": ["is", "set"]},
			pluck="vehicle",
		)
	)
	open_maintenance = set(
		frappe.get_all(
			"Maintenance",
			filters={"finish_date": ["is", "not set"], "void": 0},
			pluck="vehicle",
		)
	)

	result = {}
	for vehicle in set(gps) | set(jobs) | open_incident | open_maintenance:
		g = gps.get(vehicle)
		job = bool(jobs.get(vehicle))
		still = _minutes_since(g and g.moved_at, now)
		silent = _minutes_since(g and g.last_seen, now)
		online = silent is not None and silent <= OFFLINE_MINUTES
		moving = still is not None and still <= MOVING_MINUTES

		if online and still is not None and still >= STOP_MINUTES and _inside(g.latitude, g.longitude, danger):
			status = "Suspect"
		elif vehicle in suspended:
			status = "Suspend"
		elif moving and not job and not _inside(g.latitude, g.longitude, garasi):
			status = "Moving No Job"
		elif job and not online:
			status = "Offline Active"
		elif vehicle in open_incident:
			status = "Incident"
		elif vehicle in open_maintenance:
			status = "Maintenance"
		elif silent is None or silent > NOT_ACTIVE_DAYS * 24 * 60 or (still or 0) > NOT_ACTIVE_DAYS * 24 * 60:
			status = "Not Active"
		elif job:
			status = "On Job"
		else:
			status = "Idle"
		result[vehicle] = status
	return result


@frappe.whitelist()
def push_position(vehicle, latitude, longitude, device_id=None):
	"""Titik GPS masuk dari perangkat/vendor. Satu-satunya penulis last_seen & moved_at.

	`moved_at` hanya digeser kalau posisinya benar-benar berbeda (>= 20 meter) — GPS
	selalu bergoyang beberapa meter walau kendaraan diam, dan tanpa ambang ini tidak akan
	pernah ada kendaraan yang terhitung "diam 5 menit".
	"""
	frappe.has_permission("GPS Vehicle", "write", throw=True)
	latitude, longitude = float(latitude), float(longitude)
	now = now_datetime()

	name = frappe.db.get_value("GPS Vehicle", {"vehicle": vehicle}, "name")
	if not name:
		doc = frappe.get_doc({
			"doctype": "GPS Vehicle", "vehicle": vehicle, "device_id": device_id,
			"latitude": latitude, "longitude": longitude, "last_seen": now, "moved_at": now,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return {"vehicle": vehicle, "moved": True}

	old = frappe.db.get_value("GPS Vehicle", name, ["latitude", "longitude", "moved_at"], as_dict=True)
	moved = (
		old.latitude is None
		or old.longitude is None
		or _km(old.latitude, old.longitude, latitude, longitude) >= 0.02
	)
	values = {"latitude": latitude, "longitude": longitude, "last_seen": now}
	if moved:
		values["moved_at"] = now
	if device_id:
		values["device_id"] = device_id
	frappe.db.set_value("GPS Vehicle", name, values, update_modified=False)
	return {"vehicle": vehicle, "moved": moved}

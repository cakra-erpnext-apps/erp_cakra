"""Status kendaraan di monitor GPS dan Monitoring Board.

SATU tempat, dipakai dua halaman: aturan status pernah tersebar di gps_monitor.py dan
monitoring_board.py dan langsung menyimpang satu sama lain. Halaman baru cukup memanggil
`status_map()`, jangan menyalin aturannya.

Sejak 2026-08-11 aturannya TIDAK lagi dipatok di kode, melainkan dibaca dari doctype
**Fleet Settings**: ambang global (offline berapa menit, dst) + tabel Aturan Status.
Tiap baris aturan = satu kombinasi kondisi; yang berjenis "Status" dicek urut prioritas
dan yang cocok PERTAMA menentukan status unit, sedangkan yang berjenis "Peringatan"
dikumpulkan semua tanpa mengubah status.

Kalau tabel aturan kosong (site baru / belum di-seed), dipakai DEFAULT_RULES di bawah
supaya halaman monitor tidak pernah kosong gara-gara setting belum diisi.
"""

import math

import frappe
from frappe.utils import get_datetime, get_time, now_datetime, time_diff_in_seconds

# Dipakai kalau Fleet Settings belum diisi. Sekaligus jadi isi awal saat seed.
DEFAULTS = {
	"moving_minutes": 5,
	"offline_minutes": 15,
	"move_meters": 20,
	"not_active_days": 30,
	"route_distance_km": 3,
	"refresh_seconds": 60,
}

# Warna badge per pilihan di kolom Warna aturan.
COLOR_STYLE = {
	"Merah": "background:#fee2e2;color:#991b1b;",
	"Oranye": "background:#ffedd5;color:#9a3412;",
	"Kuning": "background:#fef3c7;color:#92400e;",
	"Biru": "background:#dbeafe;color:#1e40af;",
	"Ungu": "background:#ede9fe;color:#5b21b6;",
	"Hijau": "background:#dcfce7;color:#166534;",
	"Abu": "background:var(--bg-light-gray,#f3f4f6);color:var(--text-muted);",
}

# Ikon pin di peta, satu berkas per warna aturan. Dibuat dari truck.png dengan badan pin
# diwarnai (garis truk tetap putih) supaya semua status memakai artwork yang sama —
# lihat make_truck_icons.py kalau paletnya bertambah.
COLOR_ICON = {
	"Merah": "/assets/erp/images/truck-merah.png",
	"Oranye": "/assets/erp/images/truck-oranye.png",
	"Kuning": "/assets/erp/images/truck-kuning.png",
	"Biru": "/assets/erp/images/truck-biru.png",
	"Ungu": "/assets/erp/images/truck-ungu.png",
	"Hijau": "/assets/erp/images/truck-hijau.png",
	"Abu": "/assets/erp/images/truck-abu.png",
}

# (prioritas, nama, jenis, warna, kondisi...) — dipakai kalau tabel aturan masih kosong.
# Sembilan yang pertama = perilaku lama persis, lalu aturan baru hasil kesepakatan.
DEFAULT_RULES = [
	dict(priority=10, status_name="Suspect", color="Merah", motion="Diam", stop_minutes=5,
	     position_mode="Di dalam", loc_danger=1,
	     message="{nopol} berhenti {menit} di lokasi berbahaya {lokasi}"),
	dict(priority=20, status_name="Suspend", color="Kuning", special="Suspend",
	     message="{nopol} sedang di-suspend"),
	dict(priority=30, status_name="Offline Active", color="Ungu", has_job="Ya", online="Tidak",
	     message="{nopol} sedang job tapi GPS tidak mengirim data"),
	dict(priority=40, status_name="Lokasi Tidak Jelas", color="Merah", online="Ya", motion="Diam",
	     stop_minutes=20, position_mode="Di luar semua",
	     loc_garasi=1, loc_depo=1, loc_route=1, loc_rest=1, route_distance_km=3,
	     message="{nopol} berhenti {menit} di lokasi yang tidak dikenal"),
	dict(priority=50, status_name="Moving No Job", color="Oranye", has_job="Tidak", motion="Bergerak",
	     position_mode="Di luar semua", loc_garasi=1,
	     message="{nopol} berjalan tanpa job"),
	dict(priority=60, status_name="Incident", color="Merah", special="Incident Terbuka",
	     message="{nopol} punya incident yang belum selesai"),
	dict(priority=70, status_name="Maintenance", color="Ungu", special="Maintenance Terbuka",
	     message="{nopol} sedang perbaikan"),
	dict(priority=80, status_name="Not Active", color="Abu", special="Tidak Aktif Lama",
	     message="{nopol} sudah lama tidak mengirim data"),
	dict(priority=90, status_name="Antre Lama", color="Kuning", has_job="Ya", motion="Diam",
	     stop_minutes=360, position_mode="Di dalam", loc_route=1,
	     message="{nopol} antre {menit} di {lokasi}"),
	dict(priority=100, status_name="Istirahat", color="Hijau", has_job="Ya", motion="Diam",
	     stop_minutes=20, position_mode="Di dalam",
	     loc_garasi=1, loc_depo=1, loc_route=1, loc_rest=1,
	     message="{nopol} istirahat {menit} di {lokasi}"),
	dict(priority=110, status_name="On Job", color="Biru", has_job="Ya",
	     message="{nopol} sedang jalan"),
	dict(priority=120, status_name="Idle", color="Abu",
	     message="{nopol} standby"),
	# --- Peringatan: tidak mengubah status unit
	dict(priority=200, status_name="Over Speed", rule_type="Peringatan", color="Merah",
	     speed_over=80, message="{nopol} melaju {speed} km/jam"),
	dict(priority=210, status_name="Idling Boros", rule_type="Peringatan", color="Oranye",
	     engine="Hidup", motion="Diam", stop_minutes=15,
	     message="{nopol} mesin hidup tapi diam {menit}"),
	dict(priority=220, status_name="Luar Jam Operasional", rule_type="Peringatan", color="Kuning",
	     motion="Bergerak", time_from="22:00:00", time_to="05:00:00",
	     message="{nopol} berjalan di luar jam operasional"),
	dict(priority=230, status_name="Telat Di Titik", rule_type="Peringatan", color="Oranye",
	     has_job="Ya", late_hours=12,
	     message="{nopol} belum menyentuh titik berikutnya sejak {menit} lalu"),
]

LOC_FLAGS = (
	("loc_danger", "is_danger"),
	("loc_garasi", "is_garasi"),
	("loc_depo", "is_depo"),
	("loc_route", "is_route"),
	("loc_rest", "is_rest"),
)


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


# 1 derajat lintang ~ 111 km. Master lokasi bisa ratusan titik (734 titik rute di CMI),
# jadi sebelum menghitung haversine (4 fungsi trigonometri) titik yang jelas jauh dibuang
# lewat pengurangan biasa. Radius geofence tidak pernah sebesar ini.
_BOX_DEG = 1.0


def _nearest(lat, lon, spots):
	"""(lokasi terdekat yang MELINGKUPI titik, jarak km ke lokasi terdekat)."""
	if lat is None or lon is None:
		return None, None
	hit, best = None, None
	for s in spots:
		if not (s.latitude and s.longitude):
			continue
		if abs(lat - s.latitude) > _BOX_DEG or abs(lon - s.longitude) > _BOX_DEG:
			continue  # > ~111 km, mustahil masuk radius mana pun
		d = _km(lat, lon, s.latitude, s.longitude)
		if best is None or d < best:
			best = d
		if d <= (s.radius_km or 5) and hit is None:
			hit = s.name
	return hit, best


def get_settings():
	"""Ambang global dari Fleet Settings, jatuh balik ke DEFAULTS kalau belum diisi."""
	out = dict(DEFAULTS)
	try:
		doc = frappe.get_cached_doc("Fleet Settings")
	except Exception:
		return out
	for k in DEFAULTS:
		val = doc.get(k)
		if val:
			out[k] = val
	out["branch_order"] = doc.get("branch_order") or ""
	out["write_notification"] = doc.get("write_notification")
	out["repeat_minutes"] = doc.get("repeat_minutes") or 0
	return out


def get_rules():
	"""Aturan aktif urut prioritas; DEFAULT_RULES kalau tabelnya masih kosong."""
	rows = []
	try:
		doc = frappe.get_cached_doc("Fleet Settings")
		rows = [r.as_dict() for r in (doc.rules or []) if r.enabled]
	except Exception:
		rows = []
	if not rows:
		rows = [dict(r, enabled=1, rule_type=r.get("rule_type", "Status")) for r in DEFAULT_RULES]
	return sorted(rows, key=lambda r: (r.get("priority") or 0))


def status_colors():
	"""{nama status: style badge} untuk semua aturan — dikirim ke JS."""
	out = {r.get("status_name"): COLOR_STYLE.get(r.get("color") or "Abu", COLOR_STYLE["Abu"])
	       for r in get_rules()}
	out.setdefault("Idle", COLOR_STYLE["Abu"])
	return out


def status_icons():
	"""{nama status: url ikon pin} — warna truk di peta mengikuti warna badge status."""
	out = {r.get("status_name"): COLOR_ICON.get(r.get("color") or "Abu", COLOR_ICON["Abu"])
	       for r in get_rules()}
	out.setdefault("Idle", COLOR_ICON["Abu"])
	return out


# Kompatibilitas: halaman lama meng-import STATUS_COLORS sebagai konstanta.
STATUS_COLORS = {r["status_name"]: COLOR_STYLE.get(r.get("color", "Abu"), COLOR_STYLE["Abu"])
                 for r in DEFAULT_RULES}


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
	# Tabel note tumbuh terus; ambil HANYA baris terakhir tiap unit lewat SQL supaya
	# jumlah baris yang ditarik tetap sebanyak unit, bukan sebanyak riwayat note.
	rows = frappe.db.sql(
		"""select n.vehicle, n.suspend
		   from `tabMonitoring Notes` n
		   join (
		       select vehicle, max(ifnull(note_date, creation)) mx
		       from `tabMonitoring Notes` where ifnull(vehicle, '') != '' group by vehicle
		   ) last on last.vehicle = n.vehicle and ifnull(n.note_date, n.creation) = last.mx""",
		as_dict=True,
	)
	return {r.vehicle for r in rows if r.suspend}


def gps_info():
	"""Posisi terakhir tiap kendaraan: {vehicle: {latitude, longitude, last_seen, moved_at, ...}}.

	`last_seen`/`moved_at` diisi push_position(). Dokumen lama yang belum pernah lewat
	sana tidak punya keduanya, jadi `modified` dipakai sebagai perkiraan terbaik.
	"""
	info = {}
	for g in frappe.db.sql(
		"""select vehicle, latitude, longitude, last_seen, moved_at, speed, engine_on, modified
		   from `tabGPS Vehicle` where ifnull(vehicle, '') != '' order by modified""",
		as_dict=True,
	):
		g.last_seen = g.last_seen or g.modified
		g.moved_at = g.moved_at or g.modified
		info[g.vehicle] = g
	return info


def _late_hours_map(jobs, now):
	"""{vehicle: jam sejak ATD} untuk job yang titik berikutnya belum tersentuh."""
	items = [j.get("dpo_item") for j in jobs.values() if isinstance(j, dict) and j.get("dpo_item")]
	if not items:
		return {}
	rows = frappe.db.sql(
		"""select i.vehicle, i.atd, (
		       select count(*) from `tabDispatch Order Route` t
		       where t.dpo_item = i.name and t.step_type = 'Route' and t.start is null
		   ) belum
		   from `tabDispatch Order Item` i where i.name in %(items)s and i.atd is not null""",
		{"items": items},
		as_dict=True,
	)
	return {
		r.vehicle: (now - get_datetime(r.atd)).total_seconds() / 3600
		for r in rows
		if r.belum
	}


def _in_window(now, start, end):
	"""Jam sekarang di dalam rentang; rentang boleh melewati tengah malam (22:00-05:00)."""
	if not start or not end:
		return True
	t, a, b = now.time(), get_time(start), get_time(end)
	return (a <= t <= b) if a <= b else (t >= a or t <= b)


def _match(rule, f, cfg, now):
	"""True kalau satu baris aturan cocok dengan fakta unit."""
	ig = "Abaikan"

	if (rule.get("has_job") or ig) != ig and (rule["has_job"] == "Ya") != f["has_job"]:
		return False
	if (rule.get("online") or ig) != ig and (rule["online"] == "Ya") != f["online"]:
		return False
	if (rule.get("motion") or ig) != ig:
		if rule["motion"] == "Bergerak" and not f["moving"]:
			return False
		if rule["motion"] == "Diam" and f["moving"]:
			return False
	if (rule.get("engine") or ig) != ig and (rule["engine"] == "Hidup") != bool(f["engine_on"]):
		return False
	if rule.get("stop_minutes") and (f["stop_minutes"] or 0) < rule["stop_minutes"]:
		return False
	if rule.get("speed_over") and (f["speed"] or 0) <= rule["speed_over"]:
		return False
	if rule.get("late_hours") and (f["late_hours"] or 0) < rule["late_hours"]:
		return False

	mode = rule.get("position_mode") or ig
	if mode != ig:
		flags = [gf for col, gf in LOC_FLAGS if rule.get(col)]
		inside = any(f["inside"].get(gf) for gf in flags)
		if mode == "Di dalam" and not inside:
			return False
		if mode == "Di luar semua":
			if inside:
				return False
			# di luar radius saja belum cukup: masih dianggap wajar kalau dekat rute job-nya
			limit = rule.get("route_distance_km") or 0
			if limit and f["route_km"] is not None and f["route_km"] <= limit:
				return False

	special = rule.get("special") or ig
	if special != ig and not f["special"].get(special):
		return False
	if not _in_window(now, rule.get("time_from"), rule.get("time_to")):
		return False
	return True


def evaluate(jobs, gps=None):
	"""Hitung status + peringatan + alasan tiap unit.

	Kembali {vehicle: {"status", "reason", "minutes", "warnings": [...]}}.
	`jobs` = {vehicle: <row job aktif>} milik pemanggil (item Dispatch Order assigned
	yang belum Lanjut Job / Menuju Garasi).
	"""
	now = now_datetime()
	cfg = get_settings()
	rules = get_rules()
	gps = gps if gps is not None else gps_info()

	spots = {gf: _locations(gf) for _c, gf in LOC_FLAGS}
	route_spots = spots["is_route"]
	suspended = _suspended_vehicles()
	late = _late_hours_map(jobs, now)

	open_incident = set(frappe.get_all("Incident",
		filters={"finish_date": ["is", "not set"], "vehicle": ["is", "set"]}, pluck="vehicle"))
	open_maintenance = set(frappe.get_all("Maintenance",
		filters={"finish_date": ["is", "not set"], "void": 0}, pluck="vehicle"))

	targets = set(gps) | set(jobs) | open_incident | open_maintenance
	# satu query untuk semua nopol; sebelumnya _render menembak DB sekali PER unit
	titles = dict(
		frappe.db.sql("""select name, title from `tabVehicle`""")
	) if targets else {}

	result = {}
	for vehicle in targets:
		g = gps.get(vehicle)
		still = _minutes_since(g and g.moved_at, now)
		silent = _minutes_since(g and g.last_seen, now)
		lat = g and g.latitude
		lon = g and g.longitude

		inside, nearest_name, route_km = {}, None, None
		for _col, gf in LOC_FLAGS:
			hit, dist = _nearest(lat, lon, spots[gf])
			inside[gf] = bool(hit)
			nearest_name = nearest_name or hit
			if gf == "is_route":
				route_km = dist  # is_route daftar terbesar — jangan dipindai dua kali

		facts = {
			"has_job": bool(jobs.get(vehicle)),
			"online": silent is not None and silent <= cfg["offline_minutes"],
			"moving": still is not None and still <= cfg["moving_minutes"],
			"stop_minutes": still,
			"speed": g and g.speed,
			"engine_on": g and g.engine_on,
			"route_km": route_km,
			"late_hours": late.get(vehicle),
			"inside": inside,
			"special": {
				"Suspend": vehicle in suspended,
				"Incident Terbuka": vehicle in open_incident,
				"Maintenance Terbuka": vehicle in open_maintenance,
				"Tidak Aktif Lama": silent is None
				or silent > cfg["not_active_days"] * 24 * 60
				or (still or 0) > cfg["not_active_days"] * 24 * 60,
			},
		}

		status, reason, warnings = None, "", []
		for rule in rules:
			if not _match(rule, facts, cfg, now):
				continue
			if (rule.get("rule_type") or "Status") == "Peringatan":
				warnings.append({"status": rule["status_name"],
				                 "message": _render(rule, titles.get(vehicle, vehicle), facts, nearest_name)})
			elif status is None:
				status = rule["status_name"]
				reason = _render(rule, titles.get(vehicle, vehicle), facts, nearest_name)
		result[vehicle] = {
			"status": status or "Idle",
			"reason": reason,
			"minutes": int(still) if still is not None else None,
			"warnings": warnings,
		}
	return result


def _render(rule, nopol, facts, lokasi):
	tpl = rule.get("message") or rule.get("status_name") or ""
	mins = facts.get("stop_minutes")
	return (
		tpl.replace("{nopol}", nopol or "")
		.replace("{status}", rule.get("status_name") or "")
		.replace("{menit}", _age(int(mins)) if mins is not None else "-")
		.replace("{lokasi}", lokasi or "-")
		.replace("{speed}", str(int(facts.get("speed") or 0)))
	)


def _age(mins):
	if mins >= 1440:
		return f"{mins // 1440}h"
	if mins >= 60:
		return f"{mins // 60}j"
	return f"{mins}m"


def job_duration(assign, finish=None, now=None):
	"""Lama job driver: dari dia DI-ASSIGN job sampai selesai (Lanjut Job /
	Menuju Garasi). Belum selesai = dihitung sampai sekarang, jadi angkanya jalan
	terus di Monitoring Board. Belum ada job/assign = "" (bukan 0 menit).

	Dihitung dari Assign, bukan Accept Job: yang diukur adalah sejak job jatuh ke
	driver, termasuk waktu menunggu sebelum dia menekan Accept."""
	if not assign:
		return ""
	mins = int(time_diff_in_seconds(get_datetime(finish) if finish else (now or now_datetime()), get_datetime(assign)) // 60)
	if mins < 0:
		return ""
	if mins >= 1440:
		hari, sisa = divmod(mins, 1440)
		return f"{hari}h {sisa // 60}j" if sisa >= 60 else f"{hari}h"
	if mins >= 60:
		jam, sisa = divmod(mins, 60)
		return f"{jam}j {sisa}m" if sisa else f"{jam}j"
	return f"{mins}m"


def status_map(jobs, gps=None):
	"""{vehicle: status} — bentuk lama, dipakai halaman yang belum butuh alasan/peringatan."""
	return {v: d["status"] for v, d in evaluate(jobs, gps).items()}


@frappe.whitelist()
def push_position(vehicle, latitude, longitude, device_id=None):
	"""Titik GPS masuk dari perangkat/vendor. Satu-satunya penulis last_seen & moved_at.

	`moved_at` hanya digeser kalau posisinya benar-benar berbeda (ambang meter dari
	Fleet Settings) — GPS selalu bergoyang beberapa meter walau kendaraan diam, dan tanpa
	ambang ini tidak akan pernah ada kendaraan yang terhitung "diam 5 menit".
	"""
	frappe.has_permission("GPS Vehicle", "write", throw=True)
	latitude, longitude = float(latitude), float(longitude)
	now = now_datetime()
	limit_km = (get_settings()["move_meters"] or 20) / 1000.0

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
		or _km(old.latitude, old.longitude, latitude, longitude) >= limit_km
	)
	values = {"latitude": latitude, "longitude": longitude, "last_seen": now}
	if moved:
		values["moved_at"] = now
	if device_id:
		values["device_id"] = device_id
	frappe.db.set_value("GPS Vehicle", name, values, update_modified=False)
	return {"vehicle": vehicle, "moved": moved}

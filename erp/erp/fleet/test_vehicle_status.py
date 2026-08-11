"""Cek urutan prioritas status kendaraan. Semua perubahan di-rollback.

    bench --site erp.localhost console
    >>> from erp.fleet.test_vehicle_status import run; run()
"""

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from erp.fleet import vehicle_status as vs

DANGER = (-6.121000, 106.774000)  # dipakai untuk lokasi Danger uji
GARASI = (-6.200000, 106.816666)


def _gps(lat, lon, seen_min=0, moved_min=0):
	now = now_datetime()
	return frappe._dict({
		"latitude": lat, "longitude": lon,
		"last_seen": add_to_date(now, minutes=-seen_min),
		"moved_at": add_to_date(now, minutes=-moved_min),
	})


def run():
	vehicles = frappe.get_all("Vehicle", filters={"disabled": 0}, pluck="name", limit=3)
	if len(vehicles) < 3:
		frappe.throw("Butuh minimal 3 Vehicle aktif untuk pengujian.")
	v1, v2, v3 = vehicles[:3]

	try:
		# Bersihkan dulu kasus/servis yang MEMANG sedang terbuka di data nyata untuk ketiga
		# unit uji — kalau tidak, statusnya tertutup Incident/Maintenance dan tes menguji
		# data lapangan, bukan aturannya. Semua ini ikut ter-rollback.
		for dt in ("Incident", "Maintenance"):
			for name in frappe.get_all(
				dt, filters={"vehicle": ["in", vehicles[:3]], "finish_date": ["is", "not set"]}, pluck="name"
			):
				frappe.db.set_value(dt, name, "finish_date", nowdate(), update_modified=False)

		for code, lat, lon, flag in [
			("UJI-DANGER", DANGER[0], DANGER[1], "is_danger"),
			("UJI-GARASI", GARASI[0], GARASI[1], "is_garasi"),
		]:
			if not frappe.db.exists("Fleet Location", code):
				frappe.get_doc({
					"doctype": "Fleet Location", "code": code, "latitude": lat, "longitude": lon,
					"radius_km": 1, flag: 1,
				}).insert()

		def status(jobs, gps):
			return vs.status_map(jobs, gps)

		# 1 Suspect: diam 6 menit di dalam radius lokasi Danger, perangkat masih online
		got = status({}, {v1: _gps(*DANGER, seen_min=1, moved_min=6)})
		assert got[v1] == "Suspect", got[v1]

		# Suspect menang atas job aktif (prioritas 1 di atas On Job)
		got = status({v1: 1}, {v1: _gps(*DANGER, seen_min=1, moved_min=6)})
		assert got[v1] == "Suspect", got[v1]

		# 2 Suspend: note terakhir dicentang suspend
		note = frappe.get_doc({
			"doctype": "Monitoring Notes", "note": "uji suspend", "note_date": now_datetime(),
			"vehicle": v2, "suspend": 1,
		}).insert()
		got = status({v2: 1}, {v2: _gps(-6.3, 106.9, seen_min=1, moved_min=1)})
		assert got[v2] == "Suspend", got[v2]

		# note baru TANPA centang melepas suspend -> kembali On Job
		frappe.get_doc({
			"doctype": "Monitoring Notes", "note": "sudah beres", "note_date": add_to_date(note.note_date, minutes=1),
			"vehicle": v2, "suspend": 0,
		}).insert()
		got = status({v2: 1}, {v2: _gps(-6.3, 106.9, seen_min=1, moved_min=1)})
		assert got[v2] == "On Job", got[v2]

		# 3 Moving No Job: bergerak, tanpa job, di luar garasi
		got = status({}, {v3: _gps(-6.3, 106.9, seen_min=1, moved_min=1)})
		assert got[v3] == "Moving No Job", got[v3]

		# di DALAM garasi -> bukan Moving No Job, tapi Idle
		got = status({}, {v3: _gps(*GARASI, seen_min=1, moved_min=1)})
		assert got[v3] == "Idle", got[v3]

		# 4 Offline Active: punya job tapi perangkat diam lebih dari ambang offline
		got = status({v3: 1}, {v3: _gps(-6.3, 106.9, seen_min=vs.OFFLINE_MINUTES + 5, moved_min=60)})
		assert got[v3] == "Offline Active", got[v3]

		# 5 Incident: ada kasus yang Tgl Selesai Perbaikan-nya kosong
		inc = frappe.get_doc({
			"doctype": "Incident", "date": nowdate(), "vehicle": v3,
			"issue_title": "uji incident",
		}).insert()
		got = status({}, {v3: _gps(*GARASI, seen_min=1, moved_min=60)})
		assert got[v3] == "Incident", got[v3]

		# diisi tanggal selesainya -> tidak lagi Incident
		inc.finish_date = nowdate()
		inc.save()
		got = status({}, {v3: _gps(*GARASI, seen_min=1, moved_min=60)})
		assert got[v3] == "Idle", got[v3]

		# 6 Maintenance: kartu servis yang Tgl Keluar-nya kosong
		mtc = frappe.get_doc({
			"doctype": "Maintenance", "vehicle": v3, "maintenance_type": "Servis Rutin",
			"date": nowdate(), "company": frappe.defaults.get_global_default("company"),
		}).insert()
		got = status({}, {v3: _gps(*GARASI, seen_min=1, moved_min=60)})
		assert got[v3] == "Maintenance", got[v3]

		mtc.finish_date = nowdate()
		mtc.save()

		# 7 Not Active: tidak ada kiriman data lebih dari 30 hari
		old = frappe._dict({
			"latitude": -6.3, "longitude": 106.9,
			"last_seen": add_days(now_datetime(), -40), "moved_at": add_days(now_datetime(), -40),
		})
		got = status({}, {v3: old})
		assert got[v3] == "Not Active", got[v3]

		# unit tanpa data GPS sama sekali tapi punya job -> Offline Active (prioritas 4)
		got = status({v3: 1}, {})
		assert got[v3] == "Offline Active", got[v3]

		# 8 On Job: punya job, online, tidak ada isu
		got = status({v3: 1}, {v3: _gps(-6.3, 106.9, seen_min=1, moved_min=1)})
		assert got[v3] == "On Job", got[v3]

		# push_position menggeser moved_at hanya kalau posisinya benar-benar pindah
		vs.push_position(v1, -6.400000, 106.900000)
		first = frappe.db.get_value("GPS Vehicle", {"vehicle": v1}, "moved_at")
		vs.push_position(v1, -6.400010, 106.900010)  # goyang ~1.5 meter
		assert frappe.db.get_value("GPS Vehicle", {"vehicle": v1}, "moved_at") == first, "goyang GPS tidak boleh dianggap gerak"
		vs.push_position(v1, -6.410000, 106.900000)  # pindah ~1 km
		assert frappe.db.get_value("GPS Vehicle", {"vehicle": v1}, "moved_at") != first, "pindah 1 km harus tercatat gerak"

		print("SEMUA CEK LULUS")
	finally:
		frappe.db.rollback()

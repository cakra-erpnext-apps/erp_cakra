import frappe
from frappe.utils import now_datetime, nowdate, time_diff_in_seconds

from erp.fleet.vehicle_status import (
    get_rules,
    get_settings,
    evaluate,
    gps_info,
    status_colors,
    status_icons,
)


@frappe.whitelist()
def get_rows():
    """Data monitor GPS: daftar branch + 1 baris per kendaraan aktif.

    - driver = check-in TERAKHIR hari ini di absensi (Driver Attendance), bukan dari job.
    - job aktif = item Dispatch Order assigned yang belum ditekan Lanjut Job / Menuju Garasi.
    - note = notifikasi sementara (dihitung); nanti diganti feed notifikasi vehicle.
    """
    frappe.has_permission("GPS Vehicle", "read", throw=True)

    jobs = {}
    for r in frappe.db.sql(
        """select i.vehicle, i.name dpo_item, i.dpo_no, i.driver job_driver,
                  do.name dpo, do.packing_list, o.title origin, d.title destination, (
                 select t.point from `tabDispatch Order Route` t
                 where t.dpo_item = i.name and t.step_type = 'Route'
                   and (t.start is not null or t.end is not null)
                 order by t.step desc limit 1) checkpoint
           from `tabDispatch Order Item` i
           join `tabDispatch Order` do on i.parent = do.name
           left join `tabLocation` o on do.origin_location = o.name
           left join `tabLocation` d on do.destination_location = d.name
           where i.assigned = 1 and ifnull(i.vehicle, '') != ''
             and not exists (
               select 1 from `tabDispatch Order Route` t
               where t.dpo_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and t.start is not null)
           order by do.creation desc""",
        as_dict=True,
    ):
        jobs.setdefault(r.vehicle, r)  # job terbaru saja per unit

    # driver pemakai = check-in terakhir hari ini (absensi)
    drivers = {}
    for r in frappe.db.sql(
        """select a.vehicle, a.driver, d.title
           from `tabDriver Attendance` a left join `tabDriver` d on a.driver = d.name
           where a.type = 'Check In' and date(a.timestamp) = %s and ifnull(a.vehicle, '') != ''
           order by a.timestamp""",
        (nowdate(),),
        as_dict=True,
    ):
        drivers[r.vehicle] = r.title or r.driver  # yang terakhir menang

    # note terakhir per unit (untuk kolom Note di tabel)
    notes = {}
    for n in frappe.db.sql(
        """select vehicle, note from `tabMonitoring Notes`
           where ifnull(vehicle, '') != '' order by ifnull(note_date, creation)""",
        as_dict=True,
    ):
        notes[n.vehicle] = n.note  # yang terakhir menang

    now = now_datetime()
    gps = gps_info()
    verdict = evaluate(jobs, gps)
    rows = []
    for v in frappe.db.sql(
        """select v.name, v.code, v.title, v.branch, g.latitude, g.longitude, g.modified gps_time
           from `tabVehicle` v
           left join `tabGPS Vehicle` g on g.name = (
                select g2.name from `tabGPS Vehicle` g2 where g2.vehicle = v.name
                order by g2.modified desc limit 1)
           where ifnull(v.disabled, 0) = 0
           order by v.branch, v.title, v.code""",
        as_dict=True,
    ):
        job = jobs.get(v.name)
        if job:
            note = f"Di {job.checkpoint}" if job.checkpoint else "Belum lapor titik"
        elif not v.gps_time:
            note = "Belum ada GPS"
        else:
            mins = int(time_diff_in_seconds(now, v.gps_time) // 60)
            note = f"GPS diam {_age(mins)}" if mins > 30 else "Standby"
        rows.append(
            {
                "name": v.name,
                "branch": v.branch or "",
                "nopol": v.title or v.code,
                # absensi hari ini yang paling dipercaya; kalau supir belum check-in,
                # pakai driver yang tertulis di job supaya kolomnya tidak kosong melompong
                "driver": drivers.get(v.name) or (job and job.job_driver) or "",
                "status": (verdict.get(v.name) or {}).get("status", "Not Active"),
                "reason": (verdict.get(v.name) or {}).get("reason", ""),
                "job": (job and job.dpo_no) or "",
                "route": " - ".join(x for x in [job.origin, job.destination] if x) if job else "",
                "note": note,
                "last_note": notes.get(v.name) or "",
                "latitude": v.latitude,
                "longitude": v.longitude,
                "packing_list": (job and job.packing_list) or "",
                "dpo": (job and job.dpo) or "",
                "last_moving": v.gps_time or "",
                # customer/container/ATD/titik rute TIDAK ikut di sini — diambil get_detail()
                # saat popup dibuka supaya muat awal halaman tetap ringan.
            }
        )

    counts = {}
    for r in rows:
        counts[r["branch"]] = counts.get(r["branch"], 0) + 1
    # urutan branch mengikuti Fleet Setting (mis. Medan, Jakarta, Surabaya, Kalimantan);
    # yang tidak disebut di setting ikut di belakang sesuai abjad.
    wanted = [b.strip() for b in (get_settings().get("branch_order") or "").split(",") if b.strip()]
    order = {name: i for i, name in enumerate(wanted)}
    offices = frappe.get_all("CMI Office", fields=["name"], order_by="name")
    offices.sort(key=lambda b: (order.get(b.name, len(order)), b.name))
    branches = [{"name": "", "label": "All", "count": len(rows)}] + [
        {"name": b.name, "label": b.name, "count": counts.get(b.name, 0)} for b in offices
    ]
    # prioritas status = urutan aturan di Fleet Setting; dipakai tombol Auto untuk
    # memutar unit yang paling genting lebih dulu.
    priority = {
        r.get("status_name"): (r.get("priority") or 999)
        for r in get_rules()
        if (r.get("rule_type") or "Status") == "Status"
    }
    return {
        "branches": branches,
        "rows": rows,
        "status_colors": status_colors(),
        "status_icons": status_icons(),
        "status_priority": priority,
        "refresh_seconds": get_settings().get("refresh_seconds") or 180,
    }


@frappe.whitelist()
def get_detail(vehicle):
    """Detail 1 unit untuk popup peta — dipanggil hanya saat popup dibuka."""
    frappe.has_permission("GPS Vehicle", "read", throw=True)

    job = frappe.db.sql(
        """select i.name dpo_item, i.dpo_no, i.container_no, i.customer, i.atd, i.driver job_driver,
                  do.name dpo, do.packing_list, (
                 select max(t.start) from `tabDispatch Order Route` t
                 where t.dpo_item = i.name and t.step_type = 'Assign') assign_at
           from `tabDispatch Order Item` i
           join `tabDispatch Order` do on i.parent = do.name
           where i.assigned = 1 and i.vehicle = %s
             and not exists (
               select 1 from `tabDispatch Order Route` t
               where t.dpo_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and t.start is not null)
           order by do.creation desc limit 1""",
        (vehicle,),
        as_dict=True,
    )
    if not job:
        return {"route_points": [], "trip": 1}

    job = job[0]
    points, trip = [], 1
    for t in frappe.db.sql(
        """select ifnull(t.trip, 1) trip, t.step, t.point, t.start, t.end, f.latitude, f.longitude
           from `tabDispatch Order Route` t
           left join `tabFleet Location` f on t.point = f.name
           where t.dpo_item = %s and t.step_type = 'Route' and ifnull(t.point, '') != ''
           order by t.trip, t.step""",
        (job.dpo_item,),
        as_dict=True,
    ):
        if t.trip > trip:  # hanya titik trip terakhir yang ditampilkan
            trip, points = t.trip, []
        if t.trip == trip:
            points.append(t)

    job["job_driver"] = frappe.db.get_value("Driver", job.job_driver, "title") or job.job_driver
    job["trip"] = trip
    job["route_points"] = points
    return job


@frappe.whitelist()
def get_notes(dpo_no=None, vehicle=None, limit=20):
    """History Monitoring Notes.

    Kalau unit disebut, SEMUA note unit itu dikembalikan (dengan/ tanpa job) supaya user bisa
    langsung melihat mana yang dibuat saat ada job — pembedanya kolom dpo_no di tiap baris.
    """
    frappe.has_permission("Monitoring Notes", "read", throw=True)
    if vehicle:
        cond, val = "vehicle = %s", vehicle
    elif dpo_no:
        cond, val = "dpo_no = %s", dpo_no
    else:
        return []
    return frappe.db.sql(
        f"""select name, note, note_date, nopol, driver, status, dpo_no, owner
            from `tabMonitoring Notes` where {cond}
            order by ifnull(note_date, creation) desc limit %s""",
        (val, int(limit)),
        as_dict=True,
    )


@frappe.whitelist()
def add_note(
    note,
    latitude=None,
    longitude=None,
    vehicle=None,
    nopol=None,
    driver=None,
    dpo_no=None,
    status=None,
    note_date=None,
    suspend=0,
):
    """Simpan Monitoring Notes — dari popup unit, atau dari pin peta (boleh pilih unit sendiri).

    Kalau unit dipilih tapi kolom lain kosong, nopol/driver/job/status diisikan dari
    data monitor supaya kolomnya konsisten dengan yang tampil di layar.
    """
    if vehicle and not (nopol and dpo_no):
        row = next((r for r in get_rows()["rows"] if r["name"] == vehicle), None)
        if row:
            nopol = nopol or row.get("nopol")
            # driver monitor = check-in hari ini; kalau kosong pakai driver yang ter-assign di job
            driver = driver or row.get("driver") or get_detail(vehicle).get("job_driver")
            dpo_no = dpo_no or row.get("job")
            status = status or row.get("status")
            latitude = latitude if latitude is not None else row.get("latitude")
            longitude = longitude if longitude is not None else row.get("longitude")

    doc = frappe.get_doc(
        {
            "doctype": "Monitoring Notes",
            "note": note,
            "note_date": note_date or now_datetime(),
            "latitude": latitude,
            "longitude": longitude,
            "vehicle": vehicle,
            "nopol": nopol,
            "driver": driver,
            "dpo_no": dpo_no,
            "status": status,
            "suspend": int(suspend or 0),
        }
    ).insert()
    return doc.name


def _age(mins):
    return f"{mins // 60}j" if mins >= 60 else f"{mins}m"

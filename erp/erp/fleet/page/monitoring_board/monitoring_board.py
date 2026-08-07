import frappe
from frappe.utils import now_datetime, time_diff_in_seconds


@frappe.whitelist()
def get_rows():
    """1 baris per kendaraan aktif untuk tabel Monitoring.

    Job aktif memakai aturan yang sama dengan halaman GPS Vehicle: item Dispatch Order
    assigned yang belum ditekan Lanjut Job / Menuju Garasi.
    Note = Monitoring Notes TERAKHIR unit itu. Notifikasi masih dihitung di sini
    (checkpoint / GPS diam / Standby) sampai doctype notifikasi vehicle dibuat.
    """
    frappe.has_permission("Vehicle", "read", throw=True)

    jobs = {}
    for r in frappe.db.sql(
        """select i.vehicle, i.dpo_no, i.customer, i.atd, i.ata, do.name dpo, (
                 select t.point from `tabDispatch Order Route` t
                 where t.dpo_item = i.name and t.step_type = 'Route'
                   and (t.start is not null or t.end is not null)
                 order by t.step desc limit 1) checkpoint
           from `tabDispatch Order Item` i
           join `tabDispatch Order` do on i.parent = do.name
           where i.assigned = 1 and ifnull(i.vehicle, '') != ''
             and not exists (
               select 1 from `tabDispatch Order Route` t
               where t.dpo_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and t.start is not null)
           order by do.creation desc""",
        as_dict=True,
    ):
        jobs.setdefault(r.vehicle, r)

    # notifikasi terakhir per unit dari feed Vehicle Notification
    notifs = {}
    for n in frappe.db.sql(
        """select vehicle, message, notification_date from `tabVehicle Notification`
           where ifnull(vehicle, '') != '' order by notification_date""",
        as_dict=True,
    ):
        notifs[n.vehicle] = n  # yang terakhir menang

    notes = {}
    for n in frappe.db.sql(
        """select vehicle, note, ifnull(note_date, creation) note_date
           from `tabMonitoring Notes` where ifnull(vehicle, '') != ''
           order by ifnull(note_date, creation)""",
        as_dict=True,
    ):
        notes[n.vehicle] = n  # yang terakhir menang

    now = now_datetime()
    rows = []
    for v in frappe.db.sql(
        """select v.name, v.code, v.title, v.branch, g.modified gps_time, g.latitude, g.longitude
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
            notif = f"Di {job.checkpoint}" if job.checkpoint else "Belum lapor titik"
        elif not v.gps_time:
            notif = "Belum ada GPS"
        else:
            mins = int(time_diff_in_seconds(now, v.gps_time) // 60)
            notif = f"GPS diam {_age(mins)}" if mins > 30 else "Standby"
        n = notifs.get(v.name)  # feed notifikasi menang atas hitungan di atas
        c = notes.get(v.name)
        rows.append(
            {
                "vehicle": v.name,
                "branch": v.branch or "",
                "nopol": v.title or v.code,
                "status": "On Job" if job else "Idle",
                "job_no": (job and job.dpo_no) or "",
                "dpo": (job and job.dpo) or "",
                "customer": (job and job.customer) or "",
                "atd": (job and job.atd) or "",
                "ata": (job and job.ata) or "",
                "notifikasi": (n and n.message) or notif,
                "notification_date": (n and n.notification_date) or v.gps_time or "",
                "note": (c and c.note) or "",
                "note_date": (c and c.note_date) or "",
                "latitude": v.latitude,
                "longitude": v.longitude,
            }
        )
    return rows


@frappe.whitelist()
def get_notifications(vehicle, dpo_no=None, limit=30):
    """Daftar notifikasi unit (feed Vehicle Notification) — dipanggil saat modal dibuka."""
    frappe.has_permission("Vehicle Notification", "read", throw=True)
    return frappe.db.sql(
        """select name, message, notification_date, type, point, dpo_no
           from `tabVehicle Notification`
           where vehicle = %s or (%s != '' and dpo_no = %s)
           order by notification_date desc limit %s""",
        (vehicle, dpo_no or "", dpo_no or "", int(limit)),
        as_dict=True,
    )


def _age(mins):
    return f"{mins // 60}j" if mins >= 60 else f"{mins}m"

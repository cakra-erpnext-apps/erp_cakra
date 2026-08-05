import frappe
from frappe.utils import nowdate


@frappe.whitelist()
def get_rows():
    """Monitoring driver: 1 baris per driver aktif (tidak double).

    - absensi = absen PERTAMA hari ini, check in = check-in TERAKHIR hari ini (reset
      otomatis tiap ganti hari karena difilter per tanggal, bukan dihapus).
    - PL/DO/checkpoint = job aktif (assigned, belum tekan Lanjut Job / Menuju Garasi)
      — tidak ikut reset harian, mengikuti action driver.
    - status: On Job > Ready (sudah check in) > Absensi (baru absen) > Belum Absen.
    """
    today = nowdate()
    absen = {}   # driver -> {absen, checkin, vehicle}
    for r in frappe.db.sql(
        """select driver, type, timestamp, vehicle from `tabDriver Attendance`
           where date(timestamp) = %s order by timestamp""",
        (today,),
        as_dict=True,
    ):
        d = absen.setdefault(r.driver, {})
        if r.type == "Absensi" and "absen" not in d:
            d["absen"] = r.timestamp  # yang pertama hari ini
        if r.type == "Check In":
            d["checkin"] = r.timestamp  # yang terakhir hari ini
            if r.vehicle:
                d["vehicle"] = r.vehicle

    # job aktif per driver: assigned & belum ada start di Lanjut Job / Menuju Garasi
    jobs = {}
    for r in frappe.db.sql(
        """select i.driver, i.vehicle, i.do_no, do.name do_name, do.packing_list, pl.branch_office
           from `tabDelivery Order Item` i
           join `tabDelivery Order` do on i.parent = do.name
           left join `tabPacking List` pl on do.packing_list = pl.name
           where i.assigned = 1 and ifnull(i.driver, '') != ''
             and not exists (
               select 1 from `tabDelivery Order Route` t
               where t.do_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and t.start is not null)
           order by do.creation desc""",
        as_dict=True,
    ):
        jobs.setdefault(r.driver, r)  # ambil job terbaru saja per driver

    checkpoints = dict(
        frappe.db.sql(
            """select i.driver, (
                 select t.point from `tabDelivery Order Route` t
                 where t.do_item = i.name and t.step_type = 'Route'
                   and (t.start is not null or t.end is not null)
                 order by t.step desc limit 1)
               from `tabDelivery Order Item` i
               where i.assigned = 1 and ifnull(i.driver, '') != ''"""
        )
    )

    out = []
    for drv in frappe.get_all("Driver", filters={"disabled": 0}, fields=["name", "title"], order_by="name"):
        a = absen.get(drv.name, {})
        job = jobs.get(drv.name)
        if job:
            status = "On Job"
        elif a.get("checkin"):
            status = "Ready"
        elif a.get("absen"):
            status = "Absensi"
        else:
            status = "Belum Absen"
        out.append(
            {
                "branch": job and job.branch_office or "",
                "driver": drv.name,
                "driver_name": drv.title,
                "status": status,
                "nopol": (job and job.vehicle) or a.get("vehicle") or "",
                "absensi": a.get("absen"),
                "checkin": a.get("checkin"),
                "packing_list": job and job.packing_list or "",
                "do_no": job and job.do_no or "",
                "checkpoint": (job and checkpoints.get(drv.name)) or "",
            }
        )
    return out

import re

import frappe
from frappe.model.document import Document
from frappe.utils import cint, compare, get_filter, now_datetime, nowdate


class DriverMonitor(Document):
    """Virtual doctype (tanpa tabel): 1 baris per driver, dihitung saat list dibuka.

    Dipakai supaya monitoring absensi driver memakai list view bawaan desk
    (filter, sort, export) tanpa tabel HTML sendiri.
    """

    # read-only: tidak ada tulis balik ke mana pun
    def db_insert(self, *args, **kwargs):
        pass

    def db_update(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass

    def load_from_db(self):
        row = next((r for r in get_rows() if r.name == self.name), None)
        if not row:
            frappe.throw(frappe._("Driver {0} tidak ada").format(self.name), frappe.DoesNotExistError)
        super(Document, self).__init__(row)

    @staticmethod
    def get_list(**kwargs):
        rows = _filtered(kwargs)
        start = cint(kwargs.get("limit_start"))
        page_length = cint(kwargs.get("limit_page_length"))
        return rows[start : start + page_length] if page_length else rows[start:]

    @staticmethod
    def get_count(**kwargs):
        return len(_filtered(kwargs))

    @staticmethod
    def get_stats(**kwargs):
        return {}


def _lower(v):
    if isinstance(v, str):
        return v.lower()
    if isinstance(v, list | tuple):
        return [_lower(x) for x in v]
    return v


def _match(row, filters):
    """Seperti evaluate_filters, tapi case-insensitive supaya sama dengan LIKE/= MariaDB."""
    for f in filters:
        flt = get_filter("Driver Monitor", f)
        if not compare(_lower(row.get(flt.fieldname)), flt.operator, _lower(flt.value), flt.fieldtype):
            return False
    return True


def _filtered(kwargs):
    rows = get_rows()
    filters = kwargs.get("filters") or []
    if filters:
        rows = [r for r in rows if _match(r, filters)]
    m = re.search(r"`?(\w+)`?\s+(asc|desc)", (kwargs.get("order_by") or "").lower())
    if m and rows and m.group(1) in rows[0]:
        field = m.group(1)
        rows.sort(key=lambda r: str(r.get(field) or ""), reverse=m.group(2) == "desc")
    return rows


def get_rows():
    """1 baris per driver aktif (tidak double).

    - absensi = absen PERTAMA hari ini, check in = check-in TERAKHIR hari ini (reset
      otomatis tiap ganti hari karena difilter per tanggal, bukan dihapus).
    - PL/DPO/checkpoint = job aktif (assigned, belum tekan Lanjut Job / Menuju Garasi)
      — tidak ikut reset harian, mengikuti action driver.
    - status: On Job > Ready (sudah check in) > Absensi (baru absen) > Izin/Sakit
      (diinput user lewat Driver Attendance) > Belum Absen.
    """
    today = nowdate()
    absen = {}  # driver -> {absen, checkin, vehicle, izin, remark}
    for r in frappe.db.sql(
        """select driver, type, timestamp, vehicle, remark from `tabDriver Attendance`
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
        if r.type in ("Izin", "Sakit"):
            d["izin"] = r.type  # yang terakhir hari ini menang
        if r.remark:
            d["remark"] = r.remark

    # job aktif per driver: assigned & belum ada start di Lanjut Job / Menuju Garasi
    jobs = {}
    for r in frappe.db.sql(
        """select i.driver, i.vehicle, i.dpo_no, do.name dpo_name, do.packing_list, pl.branch_office
           from `tabDispatch Order Item` i
           join `tabDispatch Order` do on i.parent = do.name
           left join `tabPacking List` pl on do.packing_list = pl.name
           where i.assigned = 1 and ifnull(i.driver, '') != ''
             and not exists (
               select 1 from `tabDispatch Order Route` t
               where t.dpo_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and t.start is not null)
           order by do.creation desc""",
        as_dict=True,
    ):
        jobs.setdefault(r.driver, r)  # ambil job terbaru saja per driver

    checkpoints = dict(
        frappe.db.sql(
            """select i.driver, (
                 select t.point from `tabDispatch Order Route` t
                 where t.dpo_item = i.name and t.step_type = 'Route'
                   and (t.start is not null or t.end is not null)
                 order by t.step desc limit 1)
               from `tabDispatch Order Item` i
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
        elif a.get("izin"):
            status = a["izin"]
        else:
            status = "Belum Absen"
        stamp = a.get("checkin") or a.get("absen") or now_datetime()
        out.append(
            frappe._dict(
                {
                    "doctype": "Driver Monitor",
                    "name": drv.name,
                    "branch": job and job.branch_office or "",
                    "driver": drv.name,
                    "driver_name": drv.title,
                    "status": status,
                    "nopol": (job and job.vehicle) or a.get("vehicle") or "",
                    "absensi": a.get("absen"),
                    "checkin": a.get("checkin"),
                    "packing_list": job and job.packing_list or "",
                    "dpo_no": job and job.dpo_no or "",
                    "checkpoint": (job and checkpoints.get(drv.name)) or "",
                    "remark": a.get("remark") or "",
                    "docstatus": 0,
                    "idx": 0,
                    "owner": "Administrator",
                    "modified": stamp,
                    "creation": stamp,
                }
            )
        )
    return out


@frappe.whitelist()
def set_remark(drivers, type, remark=None):
    """Input user: tandai driver Izin/Sakit hari ini (1 record Driver Attendance per driver)."""
    frappe.only_for(("System Manager", "Fleet Manager"))
    for driver in frappe.parse_json(drivers):
    	frappe.get_doc(
    		{
    			"doctype": "Driver Attendance",
    			"driver": driver,
    			"type": type,
    			"timestamp": now_datetime(),
    			"remark": remark,
    		}
    	).insert()


@frappe.whitelist()
def get_today_attendance(driver):
    """Foto + titik peta absensi driver HARI INI (dipakai modal di list).

    Reset harian datang gratis dari filter tanggal: besok query ini kosong sendiri,
    tidak ada data yang dihapus. Foto selfie hanya ada di absensi (sekali sehari),
    check in tidak berfoto tapi boleh lebih dari sekali sehari.
    Posisi trado tidak ada di Driver Attendance -- diambil dari Driver Location Log
    yang ditulis barengan saat check in.
    """
    frappe.has_permission("Driver Monitor", throw=True)
    today = nowdate()
    rows = frappe.get_all(
        "Driver Attendance",
        filters={
            "driver": driver,
            "type": ("in", ["Absensi", "Check In"]),
            "timestamp": ("between", [today, today]),
        },
        fields=["type", "timestamp", "image", "vehicle", "latitude", "longitude", "distance_m", "gps_stale"],
        order_by="timestamp",
    )
    logs = frappe.get_all(
        "Driver Location Log",
        filters={"driver": driver, "source": "Check In", "timestamp": ("between", [today, today])},
        fields=["timestamp", "vehicle", "vehicle_latitude", "vehicle_longitude"],
        order_by="timestamp",
    )

    photo, points = None, []
    urutan = 0
    for r in rows:
        if r.type == "Check In":
            urutan += 1
        label = r.type if r.type == "Absensi" else f"Check In {urutan}"

        if r.type == "Absensi" and r.image and not photo:
            photo = {"label": label, "timestamp": r.timestamp, "image": r.image}
        if not (r.latitude and r.longitude):
            continue

        points.append(
            {
                "kind": "absensi" if r.type == "Absensi" else "checkin",
                "label": label,
                "timestamp": r.timestamp,
                "lat": r.latitude,
                "lon": r.longitude,
                "vehicle": r.vehicle,
                "distance_m": r.distance_m,
                "gps_stale": r.gps_stale,
            }
        )

        log = _nearest_log(logs, r.timestamp, r.vehicle) if r.type == "Check In" else None
        if log and log.vehicle_latitude:
            points.append(
                {
                    "kind": "trado",
                    "label": f"Trado {r.vehicle or ''} ({label})".strip(),
                    "timestamp": r.timestamp,
                    "lat": log.vehicle_latitude,
                    "lon": log.vehicle_longitude,
                    "vehicle": r.vehicle,
                    "distance_m": r.distance_m,
                    # dipakai menarik garis ke titik driver-nya
                    "driver_lat": r.latitude,
                    "driver_lon": r.longitude,
                }
            )

    return {"photo": photo, "points": points}


def _nearest_log(logs, timestamp, vehicle):
    """Log check-in yang paling dekat waktunya (ditulis di detik yang sama)."""
    kandidat = [l for l in logs if not vehicle or l.vehicle == vehicle] or logs
    if not kandidat:
        return None
    return min(kandidat, key=lambda l: abs((l.timestamp - timestamp).total_seconds()))

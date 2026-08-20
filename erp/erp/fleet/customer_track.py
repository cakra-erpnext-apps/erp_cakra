"""Halaman tracking untuk customer: dibuka tanpa login, hanya lewat link rahasia.

Aturan tampilan (mirip pelacakan pesanan makanan):
- Awal job hanya daftar titik rute yang muncul; peta dan armada disembunyikan.
- Armada + peta baru muncul untuk item yang kendaraannya sudah masuk radius titik
  bertanda Destination (default 5 km, ikut radius_km titik itu kalau diisi).
- Item lain di DPO yang sama tetap tersembunyi sampai kendaraannya ikut mendekat.
- Link mati sendiri begitu ATA item terisi (job selesai).

Pengaman: token 32 byte acak, rate limit per IP untuk token salah maupun benar,
dan tidak ada satu pun endpoint yang menerima id job selain lewat token.
"""

import math

import frappe
from frappe.utils import cint, flt, now_datetime

DEFAULT_RADIUS_KM = 5.0
MAX_BAD_PER_HOUR = 20     # token salah dari satu IP
MAX_HIT_PER_MINUTE = 30   # permintaan wajar dari satu IP


def _ip():
    return frappe.local.request_ip or "?"


def _guard(bad=False):
    """Rate limit sederhana berbasis cache: cegah tebak token dan banjir permintaan."""
    cache = frappe.cache()
    hit_key = f"track_hit::{_ip()}"
    hits = cint(cache.get_value(hit_key)) + 1
    cache.set_value(hit_key, hits, expires_in_sec=60)
    if hits > MAX_HIT_PER_MINUTE:
        frappe.throw("Terlalu banyak permintaan. Coba lagi sebentar lagi.", frappe.TooManyRequestsError)

    bad_key = f"track_bad::{_ip()}"
    bads = cint(cache.get_value(bad_key))
    if bads > MAX_BAD_PER_HOUR:
        frappe.throw("Akses diblokir sementara.", frappe.TooManyRequestsError)
    if bad:
        cache.set_value(bad_key, bads + 1, expires_in_sec=3600)


def _km(lat1, lon1, lat2, lon2):
    """Jarak haversine dalam km."""
    r = 6371.0
    p1, p2 = math.radians(flt(lat1)), math.radians(flt(lat2))
    dp = math.radians(flt(lat2) - flt(lat1))
    dl = math.radians(flt(lon2) - flt(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _job_by_token(token):
    name = frappe.db.get_value("Customer Job", {"token": token, "enabled": 1}, "name")
    if not name:
        _guard(bad=True)
        return None
    _guard()
    return frappe.get_doc("Customer Job", name)


@frappe.whitelist(allow_guest=True)
def get_track(token):
    """Data untuk halaman customer. Hanya mengembalikan yang perlu dilihat customer."""
    job = _job_by_token(token)
    if not job:
        return {"ok": False, "message": "Link tidak berlaku."}

    do = frappe.get_doc("Dispatch Order", job.dispatch_order)

    # titik rute + tanda origin/destination
    points, dest = [], None
    for n in range(1, 9):
        name = do.get(f"route_{n}")
        if not name:
            continue
        loc = frappe.db.get_value(
            "Fleet Location", name, ["code", "alamat", "latitude", "longitude", "radius_km"], as_dict=True
        ) or frappe._dict()
        p = {
            "no": len(points) + 1,
            "slot": n,
            "name": name,
            "label": loc.code or name,
            "address": loc.alamat,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "radius_km": flt(loc.radius_km) or DEFAULT_RADIUS_KM,
            "origin": bool(do.get(f"route_origin_{n}")),
            "dest": bool(do.get(f"route_dest_{n}")),
        }
        points.append(p)
        if p["dest"]:
            dest = p

    nopol_of = {}
    items, revealed = [], 0
    for it in do.items:
        if it.ata:
            continue  # sudah selesai bongkar, tidak ditampilkan lagi
        if it.vehicle and it.vehicle not in nopol_of:
            nopol_of[it.vehicle] = frappe.db.get_value("Vehicle", it.vehicle, "title") or it.vehicle
        row = {
            "container_no": it.container_no,
            "nopol": nopol_of.get(it.vehicle) or "",
            "dpo_no": it.dpo_no,
            "customer": it.customer,
            "status": "Menunggu" if not it.assigned else "Dalam perjalanan",
            "steps": _steps(it.name, points),
            "show_map": False,
        }
        pos = _position(it.vehicle) if it.assigned else None
        if pos and dest and dest.get("latitude") and dest.get("longitude"):
            jarak = _km(pos["latitude"], pos["longitude"], dest["latitude"], dest["longitude"])
            if jarak <= flt(dest["radius_km"] or DEFAULT_RADIUS_KM):
                row.update(
                    {
                        "show_map": True,
                        "distance_km": round(jarak, 2),
                        "latitude": pos["latitude"],
                        "longitude": pos["longitude"],
                        "last_seen": pos["last_seen"],
                        "status": "Hampir tiba",
                    }
                )
                revealed += 1
        items.append(row)

    if not items:  # semua ATA terisi -> tutup link
        job.db_set("enabled", 0, update_modified=False)
        return {"ok": False, "message": "Job sudah selesai."}

    job.db_set(
        {
            "opened_count": cint(job.opened_count) + 1,
            "last_opened": now_datetime(),
            "last_ip": _ip(),
        },
        update_modified=False,
    )
    frappe.db.commit()
    return {
        "ok": True,
        "packing_list": do.packing_list,
        "dest": (dest or {}).get("label"),
        "points": [{k: p[k] for k in ("no", "label", "address", "origin", "dest", "latitude", "longitude")} for p in points],
        "items": items,
        "revealed": revealed,
        "server_time": now_datetime(),
    }


def _steps(dpo_item, points):
    """Titik mana yang sudah dilewati unit ini (dari trip terakhir)."""
    rows = frappe.db.sql(
        """select t.point, t.start, t.end, ifnull(t.trip,1) trip from `tabDispatch Order Route` t
           where t.dpo_item = %s and t.step_type = 'Route' and ifnull(t.point,'') != ''
           order by t.trip, t.step""",
        (dpo_item,),
        as_dict=True,
    )
    if not rows:
        return [{"label": p["label"], "done": False, "at": None} for p in points]
    trip = max(r.trip for r in rows)
    by_point = {r.point: r for r in rows if r.trip == trip}
    out = []
    for p in points:
        r = by_point.get(p["name"])
        out.append({"label": p["label"], "done": bool(r and r.end), "at": (r and (r.end or r.start)) or None})
    return out


def _position(vehicle):
    """Posisi unit: vendor priority terkecil yang datanya masih segar."""
    if not vehicle:
        return None
    rows = frappe.db.sql(
        """select g.latitude, g.longitude, g.last_seen, ifnull(v.priority, 99) priority,
                  ifnull(v.stale_minutes, 0) stale_minutes
           from `tabGPS Vehicle` g left join `tabGPS Vendor` v on v.name = g.vendor
           where g.vehicle = %s order by ifnull(v.priority, 99)""",
        (vehicle,),
        as_dict=True,
    )
    now = now_datetime()
    for r in rows:
        if not (r.latitude and r.longitude):
            continue
        if r.stale_minutes and r.last_seen:
            if (now - r.last_seen).total_seconds() > r.stale_minutes * 60:
                continue
        return {"latitude": r.latitude, "longitude": r.longitude, "last_seen": r.last_seen}
    return None


@frappe.whitelist()
def share(dispatch_order):
    """Tombol Share di Dispatch Order: buat (atau ambil) link customer."""
    name = frappe.db.get_value("Customer Job", {"dispatch_order": dispatch_order}, "name")
    if name:
        doc = frappe.get_doc("Customer Job", name)
        if not doc.enabled:
            doc.db_set("enabled", 1)
    else:
        doc = frappe.get_doc({"doctype": "Customer Job", "dispatch_order": dispatch_order}).insert()
    frappe.db.commit()
    return {"name": doc.name, "url": doc.share_url}


@frappe.whitelist()
def clear_block(ip=None):
    """Buka blokir rate limit. Tanpa ip = bersihkan semua (dipakai tombol di Customer Job)."""
    cache = frappe.cache()
    if ip:
        cache.delete_value(f"track_bad::{ip}")
        cache.delete_value(f"track_hit::{ip}")
        return f"Blokir untuk {ip} dibuka."
    n = 0
    for pattern in ("track_bad::*", "track_hit::*"):
        keys = cache.get_keys(pattern)
        n += len(keys)
        for k in keys:
            cache.delete_value(frappe.safe_decode(k).split("|")[-1])
    return f"{n} catatan blokir dibersihkan."


@frappe.whitelist()
def stop_share(dispatch_order):
    """Matikan link customer. Token tetap tersimpan supaya bisa diaktifkan lagi tanpa ganti link."""
    name = frappe.db.get_value("Customer Job", {"dispatch_order": dispatch_order}, "name")
    if not name:
        return {"status": "none", "message": "Belum pernah dibagikan."}
    frappe.db.set_value("Customer Job", name, "enabled", 0)
    frappe.db.commit()
    return {"status": "stopped", "message": "Sharing dihentikan. Link lama tidak bisa dibuka lagi."}


@frappe.whitelist()
def share_status(dispatch_order):
    """Dipakai tombol di form: sudah pernah dibagikan atau belum, dan masih aktif atau tidak."""
    row = frappe.db.get_value(
        "Customer Job", {"dispatch_order": dispatch_order}, ["name", "enabled", "share_url"], as_dict=True
    )
    return row or {}

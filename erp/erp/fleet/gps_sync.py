"""Tarik posisi kendaraan dari API vendor GPS.

Satu adapter untuk semua vendor: bentuk respons dijelaskan lewat field "path" di
master GPS Vendor (notasi titik), jadi vendor baru cukup diisi lewat form.

Pairing unit ada di child table Vehicle GPS Source (vendor + device id) — satu
kendaraan boleh punya lebih dari satu sumber. Telemetri disimpan di GPS Vehicle
(1 baris per kendaraan per vendor), bukan di master Vehicle yang berubah jarang.
"""

import json

import requests

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime

TIMEOUT = 30


def _dig(obj, path):
    """Ambil nilai bersarang dengan notasi titik: 'position.latitude'."""
    if not path:
        return None
    for key in str(path).split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and key.isdigit():
            obj = obj[int(key)] if int(key) < len(obj) else None
        else:
            return None
        if obj is None:
            return None
    return obj


def _utc_to_local(value):
    """Vendor mengirim UTC (akhiran Z). Simpan dalam waktu site supaya jam tidak meleset."""
    if not value:
        return None
    try:
        from frappe.utils import convert_utc_to_system_timezone

        text = str(value).replace("Z", "+00:00")
        return convert_utc_to_system_timezone(get_datetime(text)).replace(tzinfo=None)
    except Exception:
        return get_datetime(value)


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _session(vendor, fresh_token=False):
    """Header/param auth sesuai tipe yang dipilih di master vendor."""
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": UA}
    params, auth = {}, None
    key = vendor.get_password("api_key", raise_exception=False) if vendor.api_key else None

    if vendor.auth_type == "API Key Header" and key:
        headers[vendor.auth_key_name or "X-API-Key"] = key
    elif vendor.auth_type == "Query Param" and key:
        params[vendor.auth_key_name or "token"] = key
    elif vendor.auth_type == "Bearer Token" and key:
        headers["Authorization"] = f"Bearer {key}"
    elif vendor.auth_type == "Basic" and key:
        auth = (vendor.auth_key_name or "", key)
    elif vendor.auth_type == "OAuth2 Client Credentials":
        headers["Authorization"] = f"Bearer {_oauth_token(vendor, fresh=fresh_token)}"
        # sebagian vendor (UD Trucks) tetap minta x-api-key di samping Bearer
        if vendor.send_api_key_header and key:
            headers[vendor.auth_key_name or "x-api-key"] = key
    return headers, params, auth


def _token_key(vendor):
    return f"gps_token::{vendor.name}"


def _oauth_token(vendor, fresh=False):
    """Token client_credentials, disimpan di cache sampai kedaluwarsa."""
    cached = None if fresh else frappe.cache().get_value(_token_key(vendor))
    if cached:
        return cached

    body = {
        "grant_type": "client_credentials",
        "client_id": vendor.client_id,
        "client_secret": vendor.get_password("client_secret", raise_exception=False),
    }
    if vendor.audience:
        body["audience"] = vendor.audience

    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": UA}
    key = vendor.get_password("api_key", raise_exception=False) if vendor.api_key else None
    if vendor.send_api_key_header and key:
        headers[vendor.auth_key_name or "x-api-key"] = key

    res = requests.post(vendor.token_url, json=body, headers=headers, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()
    token = data.get("access_token")
    if not token:
        frappe.throw("Login vendor tidak mengembalikan access_token.")
    ttl = cint(data.get("expires_in")) or cint(vendor.token_hours or 8) * 3600
    frappe.cache().set_value(_token_key(vendor), token, expires_in_sec=max(ttl - 60, 60))
    return token


def _fetch(vendor, path, retry=True):
    """Panggil endpoint vendor. Kalau 401 (token kedaluwarsa), ambil token baru lalu ulangi sekali."""
    url = f"{(vendor.base_url or '').rstrip('/')}/{(path or '').lstrip('/')}"
    headers, params, auth = _session(vendor)
    res = requests.request(
        vendor.http_method or "GET", url, headers=headers, params=params, auth=auth, timeout=TIMEOUT
    )
    if res.status_code == 401 and retry and vendor.auth_type == "OAuth2 Client Credentials":
        frappe.cache().delete_value(_token_key(vendor))
        headers, params, auth = _session(vendor, fresh_token=True)
        res = requests.request(
            vendor.http_method or "GET", url, headers=headers, params=params, auth=auth, timeout=TIMEOUT
        )
    res.raise_for_status()
    return res.json()


def _rows(vendor, payload):
    rows = _dig(payload, vendor.list_path) if vendor.list_path else payload
    return rows if isinstance(rows, list) else []


def _normalize(vendor, row):
    """Satu baris vendor -> bentuk seragam yang dipakai sistem."""
    engine = _dig(row, vendor.engine_path)
    if vendor.engine_on_value:
        # boleh lebih dari satu nilai, pisah koma: IGNITION_ON,MOVEMENT
        on_values = [v.strip().lower() for v in vendor.engine_on_value.split(",") if v.strip()]
        engine_on = str(engine).lower() in on_values
    else:
        engine_on = bool(engine)
    return {
        "device_id": _dig(row, vendor.device_id_path),
        "alt_id": _dig(row, vendor.alt_id_path),
        "latitude": flt(_dig(row, vendor.lat_path)),
        "longitude": flt(_dig(row, vendor.lon_path)),
        "last_seen": _utc_to_local(_dig(row, vendor.time_path)),
        "speed": flt(_dig(row, vendor.speed_path)),
        "direction": flt(_dig(row, vendor.heading_path)),
        "engine_on": 1 if engine_on else 0,
        "odometer": flt(_dig(row, vendor.odometer_path)) / (1000 if vendor.odometer_in_meters else 1),
    }


def _pairs(vendor_name):
    """device id vendor (huruf kecil) -> vehicle.

    Child table menyimpan nama record GPS Device, jadi di-join untuk dapat device_id aslinya.
    """
    out = {}
    # cukup isi field Vehicle di GPS Device; child table Vehicle GPS Source menang kalau dua-duanya ada
    for r in frappe.db.sql(
        """select d.device_id, coalesce(s.parent, d.vehicle) vehicle
           from `tabGPS Device` d
           left join `tabVehicle GPS Source` s on s.device_id = d.name and s.vendor = %s
           where d.vendor = %s and (s.parent is not null or ifnull(d.vehicle, '') != '')""",
        (vendor_name, vendor_name),
        as_dict=True,
    ):
        out[str(r.device_id).strip().lower()] = r.vehicle
    return out


@frappe.whitelist()
def sync_vendor(vendor):
    """Tarik posisi semua unit satu vendor (sekali panggil), lalu simpan."""
    doc = frappe.get_doc("GPS Vendor", vendor)
    try:
        rows = _rows(doc, _fetch(doc, doc.positions_path))
    except Exception as e:
        doc.db_set({"last_sync": now_datetime(), "last_status": "Error", "last_error": str(e)[:500]})
        frappe.log_error(frappe.get_traceback(), f"GPS sync {vendor}")
        return f"Gagal: {e}"

    pairs = _pairs(vendor)
    updated = 0
    for row in rows:
        pos = _normalize(doc, row)
        key = str(pos["device_id"] or "").strip().lower()
        vehicle = pairs.get(key) or pairs.get(str(pos["alt_id"] or "").strip().lower())
        if not vehicle or not (pos["latitude"] and pos["longitude"]):
            continue
        _save_position(vendor, vehicle, pos)
        updated += 1

    doc.db_set(
        {"last_sync": now_datetime(), "last_status": f"OK {updated}/{len(rows)}", "last_error": None}
    )
    frappe.db.commit()
    return f"{updated} unit diperbarui dari {len(rows)} baris."


def _save_position(vendor, vehicle, pos):
    """Update baris GPS Vehicle (buat kalau belum ada) + breadcrumb kalau unit sedang berjob."""
    name = frappe.db.get_value("GPS Vehicle", {"vehicle": vehicle, "vendor": vendor}, "name")
    values = {
        "latitude": pos["latitude"],
        "longitude": pos["longitude"],
        "last_seen": pos["last_seen"] or now_datetime(),
        "speed": pos["speed"],
        "direction": pos["direction"],
        "engine_on": pos["engine_on"],
        "odometer": pos["odometer"],
        "last_sync": now_datetime(),
    }
    if name:
        before = frappe.db.get_value("GPS Vehicle", name, ["latitude", "longitude"], as_dict=True)
        if flt(before.latitude) != pos["latitude"] or flt(before.longitude) != pos["longitude"]:
            values["moved_at"] = values["last_seen"]
        frappe.db.set_value("GPS Vehicle", name, values, update_modified=True)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "GPS Vehicle",
                "vehicle": vehicle,
                "vendor": vendor,
                "device_id": pos["device_id"],
                "moved_at": values["last_seen"],
                **values,
            }
        )
        doc.insert(ignore_permissions=True)

    _breadcrumb(vehicle, pos)


def _breadcrumb(vehicle, pos):
    """Jejak per menit hanya untuk unit yang punya job aktif (aturan route_history)."""
    job = frappe.db.sql(
        """select i.name dpo_item, i.parent dpo, i.driver, ifnull(t.trip, 1) trip
           from `tabDispatch Order Item` i
           left join `tabDispatch Order Route` t on t.dpo_item = i.name
           where i.assigned = 1 and i.vehicle = %s
             and not exists (
               select 1 from `tabDispatch Order Route` x
               where x.dpo_item = i.name and x.step_type in ('Lanjut Job', 'Menuju Garasi')
                 and x.start is not null)
           order by ifnull(t.trip, 1) desc limit 1""",
        (vehicle,),
        as_dict=True,
    )
    if not job:
        return
    j = job[0]
    frappe.db.sql(
        """insert into history.route_history
           (dispatch_order, dpo_item, trip, driver, vehicle, latitude, longitude, recorded_at)
           values (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (j.dpo, j.dpo_item, j.trip, j.driver, vehicle, pos["latitude"], pos["longitude"],
         pos["last_seen"] or now_datetime()),
    )


def sync_all():
    """Dipanggil scheduler tiap menit: satu panggilan bulk per vendor aktif."""
    for name in frappe.get_all("GPS Vendor", filters={"enabled": 1}, pluck="name"):
        try:
            sync_vendor(name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"GPS sync_all {name}")


@frappe.whitelist()
def test_connection(vendor):
    doc = frappe.get_doc("GPS Vendor", vendor)
    try:
        payload = _fetch(doc, doc.positions_path)
        rows = _rows(doc, payload)
        if not rows:
            doc.db_set({"last_status": "Kosong", "last_error": "Respons tidak berisi list."})
            return "Terhubung, tapi List Path tidak menghasilkan baris. Cek pemetaan."
        contoh = _normalize(doc, rows[0])
        doc.db_set({"last_status": "OK", "last_error": None})
        return f"OK, {len(rows)} baris. Contoh hasil pemetaan:<br><pre>{json.dumps(contoh, default=str, indent=1)}</pre>"
    except Exception as e:
        doc.db_set({"last_status": "Error", "last_error": str(e)[:500]})
        return f"Gagal: {e}"


@frappe.whitelist()
def pull_devices(vendor):
    """Tarik daftar unit vendor jadi record GPS Device, lalu cocokkan ke master Vehicle.

    Hasilnya jadi daftar pilihan saat memasang GPS Source di form Vehicle — user tidak
    perlu mengetik IMEI/VIN lagi. Pencocokan lewat IMEI, no rangka, nopol.
    """
    doc = frappe.get_doc("GPS Vendor", vendor)
    rows = _rows(doc, _fetch(doc, doc.devices_path or doc.positions_path))

    index = {}
    for v in frappe.db.sql(
        """select name, title, no_imei, no_rangka, no_lambung from `tabVehicle` where ifnull(disabled,0)=0""",
        as_dict=True,
    ):
        for key in (v.no_imei, v.no_rangka, v.no_lambung, v.title):
            if key:
                index.setdefault(str(key).strip().lower(), v.name)

    pairs = _pairs(vendor)
    baru = cocok = dipasang = 0
    belum = []
    for row in rows:
        pos = _normalize(doc, row)
        device_id = str(pos["device_id"] or "").strip()
        if not device_id:
            continue
        alt = str(pos["alt_id"] or "").strip()
        vehicle = next((index[i.lower()] for i in (device_id, alt) if i and i.lower() in index), None)

        name = frappe.db.get_value("GPS Device", {"vendor": vendor, "device_id": device_id}, "name")
        values = {"plate": alt, "last_seen": pos["last_seen"], "last_pull": now_datetime()}
        if name:
            if vehicle and not frappe.db.get_value("GPS Device", name, "vehicle"):
                values["vehicle"] = vehicle
            frappe.db.set_value("GPS Device", name, values)
        else:
            name = frappe.get_doc(
                {"doctype": "GPS Device", "vendor": vendor, "device_id": device_id, "vehicle": vehicle, **values}
            ).insert(ignore_permissions=True).name
            baru += 1

        if not vehicle:
            belum.append(device_id + (f" ({alt})" if alt else ""))
            continue
        cocok += 1
        if name in pairs.values() or device_id.lower() in pairs:
            continue
        v = frappe.get_doc("Vehicle", vehicle)
        v.append("gps_sources", {"vendor": vendor, "device_id": name})
        v.save(ignore_permissions=True)
        dipasang += 1

    frappe.db.commit()
    pesan = f"{len(rows)} unit dari vendor, {baru} baru dicatat, {cocok} cocok ke master, {dipasang} dipasangkan otomatis."
    if belum:
        pesan += "<br>Belum ketemu di master Vehicle (pasangkan manual): " + ", ".join(belum[:20])
        if len(belum) > 20:
            pesan += f" dan {len(belum) - 20} lainnya"
    return pesan


def position_of(vehicle_rows):
    """Pilih posisi per kendaraan: vendor priority terkecil yang datanya masih segar.

    vehicle_rows = list baris GPS Vehicle (sudah berisi kolom vendor, priority,
    stale_minutes, last_seen). Dipakai halaman monitor.
    """
    now = now_datetime()
    best = {}
    for r in sorted(vehicle_rows, key=lambda x: cint(x.get("priority") or 99)):
        veh = r.get("vehicle")
        if veh in best:
            continue
        stale = cint(r.get("stale_minutes") or 0)
        segar = True
        if stale and r.get("last_seen"):
            segar = (now - get_datetime(r["last_seen"])).total_seconds() <= stale * 60
        elif stale and not r.get("last_seen"):
            segar = False
        if r.get("latitude") and r.get("longitude") and segar:
            best[veh] = r
    # kendaraan yang semua sumbernya basi: pakai baris priority terkecil apa adanya
    for r in sorted(vehicle_rows, key=lambda x: cint(x.get("priority") or 99)):
        best.setdefault(r.get("vehicle"), r)
    return best

"""Pasangan 1:1 antara Asset (sisi keuangan) dan Vehicle (sisi operasional Fleet).

Aturan yang ditetapkan user (2026-09-10):
- Asset Category dicentang `custom_is_vehicle` = isinya kendaraan.
- Vehicle TIDAK dibuat otomatis. Di form aset ada tombol "Buat Vehicle" (Create) yang
  membuka form Vehicle baru sudah tertaut ke aset — nopol, branch, dan varian diisi user
  seperti membuat vehicle biasa. Lihat public/js/asset.js.
- SATU aset hanya boleh punya SATU vehicle (dijamin indeks unik di Vehicle.asset).
- Asset dihapus, vehicle-nya ikut terhapus.

Asset milik core ERPNext, jadi hooknya tinggal di app ini (erp sengaja steril terhadap
core). Vehicle sendiri doctype milik app `erp` — memanggilnya dari sini sudah lazim
(lihat custom_vehicle di Purchase Invoice/Receipt Item).
"""

import frappe
from frappe import _


def link_asset(vehicle, method=None):
    """Hook Vehicle after_insert/on_update: pasang penunjuk balik di aset.

    Kalau tautan asetnya dipindah, aset lama dilepas dulu supaya tidak ada dua aset yang
    mengaku punya vehicle yang sama.
    """
    before = vehicle.get_doc_before_save()
    lama = before.get("asset") if before else None
    if lama and lama != vehicle.get("asset"):
        _clear_back_link(lama, vehicle.name)

    if not vehicle.get("asset"):
        return
    if frappe.db.get_value("Asset", vehicle.asset, "custom_vehicle") != vehicle.name:
        frappe.db.set_value("Asset", vehicle.asset, "custom_vehicle", vehicle.name, update_modified=False)


def _clear_back_link(asset, vehicle_name):
    if frappe.db.get_value("Asset", asset, "custom_vehicle") == vehicle_name:
        frappe.db.set_value("Asset", asset, "custom_vehicle", None, update_modified=False)


def delete_vehicle(asset, method=None):
    """Hook Asset on_trash: vehicle pendampingnya ikut dihapus.

    Kalau vehicle-nya sudah dipakai (job, GPS, ban, absensi), penghapusan DITOLAK dengan
    pesan jelas — lebih baik daripada meninggalkan vehicle yatim yang menunjuk aset hilang.
    """
    name = frappe.db.get_value("Vehicle", {"asset": asset.name}, "name")
    if not name:
        return
    # Tautannya dua arah, jadi penunjuk dari sisi aset HARUS dilepas dulu — kalau tidak,
    # Frappe menolak menghapus vehicle karena "masih ditaut Asset" (kunci melingkar).
    asset.db_set("custom_vehicle", None, update_modified=False)
    try:
        frappe.delete_doc("Vehicle", name, ignore_permissions=True)
    except frappe.LinkExistsError:
        frappe.throw(
            _("Aset ini tidak bisa dihapus: Vehicle {0} sudah dipakai di dokumen lain. "
              "Hapus dulu pemakaiannya, atau lepas tautan asetnya di form Vehicle.").format(name)
        )


def unlink_asset(vehicle, method=None):
    """Hook Vehicle on_trash: lepas penunjuk di aset.

    on_trash berjalan SEBELUM Frappe memeriksa tautan, jadi ini juga yang membuat vehicle
    tetap bisa dihapus sendiri tanpa tersandung Asset.custom_vehicle.
    """
    if vehicle.get("asset"):
        _clear_back_link(vehicle.asset, vehicle.name)

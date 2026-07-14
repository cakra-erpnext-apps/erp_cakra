"""Daftarkan Module Def "FICO" (modul baru di modules.txt).

WAJIB lewat patch pre_model_sync, bukan after_migrate: `add_module_defs` hanya dipanggil
saat app di-INSTALL. Untuk app yang sudah terpasang, modul baru di modules.txt tidak pernah
dapat Module Def-nya — akibatnya doctype di dalam folder modul itu TIDAK ikut sync sama
sekali. pre_model_sync jalan SEBELUM sync doctype, jadi satu kali `bench migrate` cukup.

Modul ini sempat bernama "FiCo". Kolom name di MariaDB memakai collation case-insensitive,
jadi "FiCo" dan "FICO" adalah KUNCI YANG SAMA — insert biasa akan bentrok diam-diam.
Karena itu ejaannya dinormalkan lewat UPDATE dulu (LIKE juga case-insensitive), baru
add_module_defs mengisi kalau memang belum ada.
"""

import frappe
from frappe.installer import add_module_defs


def execute():
    frappe.db.sql("UPDATE `tabModule Def` SET name = 'FICO', module_name = 'FICO' WHERE module_name LIKE 'fico'")
    frappe.db.sql("UPDATE `tabDocType` SET module = 'FICO' WHERE module LIKE 'fico'")
    add_module_defs("erp", ignore_if_duplicate=True)
    frappe.db.commit()

"""Reset kolom grid Sales Invoice Item ke default meta (sekali jalan).

Kolom grid child table dikonfigurasi lewat ikon gerigi disimpan PER-USER di __UserSettings
(GridView) dan MENIMPA in_list_view meta — dan tidak ikut deploy. Akibatnya kolom baru
(Currency / Price / Rate per item) tidak muncul otomatis di server; user harus menambah
manual. Patch ini menghapus override "Sales Invoice Item" dari SEMUA user sekali, supaya
default meta (dikelola di install.py GRID) yang berlaku. Setelah ini user bebas kustom lagi.
"""

import json

import frappe


def execute():
    rows = frappe.db.sql("""SELECT user, data FROM `__UserSettings` WHERE doctype = 'Sales Invoice'""")
    for user, data in rows:
        if not data:
            continue
        try:
            j = json.loads(data)
        except Exception:
            continue
        gv = j.get("GridView")
        if isinstance(gv, dict) and "Sales Invoice Item" in gv:
            gv.pop("Sales Invoice Item", None)
            frappe.db.sql(
                """UPDATE `__UserSettings` SET data = %s WHERE user = %s AND doctype = 'Sales Invoice'""",
                (json.dumps(j), user),
            )
    frappe.db.commit()

"""Reset kolom grid Item Defaults ke default meta (sekali jalan).

Pola yang sama dengan reset_sales_invoice_item_grid_columns: kolom grid child table yang
pernah diatur lewat ikon gerigi tersimpan PER-USER di __UserSettings (GridView) dan
MENIMPA in_list_view meta, serta tidak ikut deploy. Akibatnya susunan kolom baru
(Warehouse | Expense | Income | Direct Use | Discount | Inventory, lihat install.py GRID)
tidak pernah muncul selama override lama masih ada. Setelah ini user bebas kustom lagi.
"""

import json

import frappe

PARENT = "Item"
CHILD = "Item Default"


def execute():
    rows = frappe.db.sql(
        """SELECT user, data FROM `__UserSettings` WHERE doctype = %s""", PARENT
    )
    for user, data in rows:
        if not data:
            continue
        try:
            j = json.loads(data)
        except Exception:
            continue
        gv = j.get("GridView")
        if isinstance(gv, dict) and CHILD in gv:
            gv.pop(CHILD, None)
            frappe.db.sql(
                """UPDATE `__UserSettings` SET data = %s WHERE user = %s AND doctype = %s""",
                (json.dumps(j), user, PARENT),
            )
    frappe.db.commit()

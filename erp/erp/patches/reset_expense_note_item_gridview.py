"""Reset SEMUA GridView tersimpan per user.

Kolom grid child table bisa di-override per user (__UserSettings > GridView) dan
override itu MENANG atas in_list_view di doctype. Setelan lama di Expense Note Item
menampilkan kolom `item` sekaligus menghilangkan `expense_account`, jadi grid entri
biaya tampil salah: Item | Description | Qty | Price | Amount.

Daripada menambal satu doctype, seluruh kunci GridView dibuang: tiap grid kembali ke
kolom default doctype-nya. Konsekuensinya penataan kolom yang pernah disimpan user
(doctype mana pun) ikut hilang — ini disengaja, diminta eksplisit. Setelan lain di
__UserSettings (filter list, sort, view terakhir) TIDAK disentuh.
"""

import json

import frappe


def execute():
    rows = frappe.db.sql(
        "select user, doctype, data from `__UserSettings` where data like %s",
        ("%GridView%",),
        as_dict=True,
    )
    reset = 0
    for r in rows:
        try:
            data = json.loads(r.data or "{}")
        except ValueError:
            continue
        if not data.pop("GridView", None):
            continue
        frappe.db.sql(
            "update `__UserSettings` set data = %s where user = %s and doctype = %s",
            (json.dumps(data), r.user, r.doctype),
        )
        reset += 1
    frappe.db.commit()
    print("GridView direset untuk {0} baris __UserSettings".format(reset))

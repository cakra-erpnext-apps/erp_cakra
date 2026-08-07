"""Pindahkan flag Connection dari doctype Expense Setting ke ERPNext Custom Setting > Flag.

Expense Setting cuma menampung dua checkbox dan berdiri sebagai doctype + menu sendiri.
Digabung ke ERPNext Custom Setting supaya seluruh setting custom satu tempat; doctype dan
menunya dibuang setelah nilainya disalin.

Nilai lama menang: kalau user sudah pernah menyimpan Expense Setting, itu yang dipakai.
Kalau belum pernah, biarkan default field-nya yang berlaku (SL=0, PL=1).
"""

import frappe

FIELDS = ("show_shipping_list", "show_packing_list")
NEW = "ERPNext Custom Setting"


def execute():
    if frappe.db.exists("DocType", "Expense Setting"):
        old = frappe.db.get_singles_dict("Expense Setting")
        for f in FIELDS:
            if old.get(f) is not None:
                frappe.db.set_single_value(NEW, f, frappe.utils.cint(old.get(f)))
        frappe.delete_doc("DocType", "Expense Setting", ignore_permissions=True, force=True)

    # Menu lamanya di sidebar ERPNext Settings ikut dibuang; kalau tidak, tersisa link mati.
    for name in frappe.get_all(
        "Workspace Sidebar Item",
        filters={"parenttype": "Workspace Sidebar", "link_to": "Expense Setting"},
        pluck="name",
    ):
        frappe.db.delete("Workspace Sidebar Item", {"name": name})

    frappe.db.delete("Singles", {"doctype": "Expense Setting"})
    frappe.db.commit()
    frappe.clear_cache()

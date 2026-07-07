"""Setup erp.

erp STERIL terhadap core ERPNext: tidak membuat custom field / property setter
di doctype core (Sales Invoice, Company, dll). Semua itu ada di app `erpnext_custom`.
Doctype milik erp sendiri otomatis ter-sync oleh `bench migrate` dari file JSON-nya.

CATATAN: seed Role divisi + flow Agent Fleet sudah DIPINDAH ke app `agents`
(`assistant.install`). erp tidak lagi mengurus Agent/Assistant.
"""

import frappe

# Role akses tab Summary Shipping List (data finansial: expense, revenue, margin).
SUMMARY_ROLE = "Shipping List Summary"


def after_install():
    after_migrate()


def after_migrate():
    _seed_roles()


def _seed_roles():
    if not frappe.db.exists("Role", SUMMARY_ROLE):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": SUMMARY_ROLE,
            "desk_access": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()

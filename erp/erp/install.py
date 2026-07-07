"""Setup erp.

erp STERIL terhadap core ERPNext: tidak membuat custom field / property setter
di doctype core (Sales Invoice, Company, dll). Semua itu ada di app `erpnext_custom`.
Doctype milik erp sendiri otomatis ter-sync oleh `bench migrate` dari file JSON-nya.

CATATAN: seed Role divisi + flow Agent Fleet sudah DIPINDAH ke app `agents`
(`assistant.install`). erp hanya menjaga akses Page Assistant Center karena page
itu ditampilkan di Workspace Expedition milik app ini.
"""

import frappe

# Role akses tab Summary Shipping List (data finansial: expense, revenue, margin).
SUMMARY_ROLE = "Shipping List Summary"
ASSISTANT_CENTER_PAGE = "assistant-center"
ASSISTANT_CENTER_ROLES = ("Assistant User", "Assistant Administrator")


def after_install():
    after_migrate()


def after_migrate():
    _seed_roles()
    _ensure_assistant_center_access()


def _seed_roles():
    if not frappe.db.exists("Role", SUMMARY_ROLE):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": SUMMARY_ROLE,
            "desk_access": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()


def _ensure_role(role_name):
    if frappe.db.exists("Role", role_name):
        frappe.db.set_value("Role", role_name, "desk_access", 1, update_modified=False)
        return
    frappe.get_doc({
        "doctype": "Role",
        "role_name": role_name,
        "desk_access": 1,
    }).insert(ignore_permissions=True)


def _ensure_assistant_center_access():
    """Keep Assistant Center visible for non-admin users after install/migrate.

    The page lives in app `erp`, while Assistant roles are seeded by app
    `assistant`. On a fresh server, app install order can leave the Page synced
    before those roles exist. Re-asserting access here keeps the Expedition menu
    link available for users with Assistant roles.
    """
    for role in ASSISTANT_CENTER_ROLES:
        _ensure_role(role)

    if not frappe.db.exists("Page", ASSISTANT_CENTER_PAGE):
        frappe.db.commit()
        return

    page = frappe.get_doc("Page", ASSISTANT_CENTER_PAGE)
    existing = {row.role for row in (page.roles or [])}
    changed = False
    for role in ("System Manager", *ASSISTANT_CENTER_ROLES):
        if role not in existing:
            page.append("roles", {"role": role})
            changed = True

    if changed:
        page.save(ignore_permissions=True)
    frappe.db.commit()

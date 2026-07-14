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
    _ensure_pending_cash_in_payments_sidebar()
    _drop_naming_series_overrides()


# Naming series HANYA boleh datang dari doctype JSON. Property Setter naming_series
# (dibuat lewat Customize Form, hidup di DB dan tidak ikut git) MENIMPA JSON, sehingga
# server bisa memakai seri lama sementara kode sudah seri baru — persis penyebab nomor
# `EXP-EN-2026-00001` muncul di server padahal kode memberi `EN/IMP/2026/0001`.
_NAMING_SERIES_OWNED = ("Expense Note", "Shipping List", "Packing List", "Pending Cash")


def _drop_naming_series_overrides():
    stale = frappe.get_all(
        "Property Setter",
        filters={
            "doc_type": ["in", _NAMING_SERIES_OWNED],
            "field_name": "naming_series",
            "property": ["in", ("options", "default")],
        },
        pluck="name",
    )
    for ps in stale:
        frappe.delete_doc("Property Setter", ps, ignore_permissions=True, force=True)
    if stale:
        frappe.clear_cache()
        frappe.db.commit()


# Sidebar "Payments" adalah ASET BAWAAN ERPNEXT (erpnext/workspace_sidebar/payments.json):
# tiap `bench migrate` dia di-import ulang dari file itu, sehingga item yang kita tambahkan
# lewat UI/DB akan HILANG. Karena itu Pending Cash disisipkan ulang di sini — after_migrate
# jalan SETELAH import, jadi hasilnya bertahan di setiap deploy. Idempoten.
def _ensure_pending_cash_in_payments_sidebar():
    # Doctype Pending Cash bisa belum ter-sync kalau Module Def FICO belum ada
    # (patch add_fico_module ter-skip); jangan bikin migrate mati karena sidebar.
    if not frappe.db.exists("DocType", "Pending Cash"):
        return
    if not frappe.db.exists("Workspace Sidebar", "Payments"):
        return
    sb = frappe.get_doc("Workspace Sidebar", "Payments")
    if any(i.link_to == "Pending Cash" for i in sb.items):
        return

    item = {
        "doctype": "Workspace Sidebar Item",
        "label": "Pending Cash",
        "link_type": "DocType",
        "link_to": "Pending Cash",
        # child=1: item di dalam grup (sama seperti Payment Entry), bukan judul grup.
        "child": 1,
        "indent": 0,
        "collapsible": 1,
        "show_arrow": 0,
        "keep_closed": 0,
    }
    # Tepat DI ATAS Payment Entry; kalau entah kenapa tak ketemu, taruh di akhir.
    pos = next((i.idx for i in sb.items if i.link_to == "Payment Entry"), None)
    rows = [d.as_dict() for d in sb.items]
    if pos is None:
        rows.append(item)
    else:
        rows.insert(pos - 1, item)

    sb.set("items", [])
    for r in rows:
        r.pop("name", None)
        r.pop("idx", None)
        sb.append("items", r)
    sb.flags.ignore_permissions = True
    sb.save()
    frappe.db.commit()


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

    # Sisipkan baris role LANGSUNG (child Has Role) — JANGAN page.save():
    # Page.on_update meng-export ulang file JSON page saat developer_mode aktif,
    # dan itu gagal PermissionError di server (file app milik user host, read-only
    # bagi container). Insert child row tidak menyentuh file sama sekali.
    existing = set(frappe.get_all(
        "Has Role",
        filters={"parenttype": "Page", "parent": ASSISTANT_CENTER_PAGE},
        pluck="role",
    ))
    for role in ("System Manager", *ASSISTANT_CENTER_ROLES):
        if role in existing:
            continue
        frappe.get_doc({
            "doctype": "Has Role",
            "parenttype": "Page",
            "parent": ASSISTANT_CENTER_PAGE,
            "parentfield": "roles",
            "role": role,
        }).insert(ignore_permissions=True)
    frappe.db.commit()

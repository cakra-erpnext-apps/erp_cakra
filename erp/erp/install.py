"""Setup erp.

erp STERIL terhadap core ERPNext: tidak membuat custom field / property setter
di doctype core (Sales Invoice, Company, dll). Semua itu ada di app `erpnext_custom`.
Doctype milik erp sendiri otomatis ter-sync oleh `bench migrate` dari file JSON-nya.

CATATAN: seed Role divisi + flow Agent Fleet sudah DIPINDAH ke app `agents`
(`assistant.install`). erp hanya menjaga akses Page Assistant Center karena page
itu ditampilkan di Workspace Expedition milik app ini.
"""

import frappe

ASSISTANT_CENTER_PAGE = "assistant-center"
ASSISTANT_CENTER_ROLES = ("Assistant User", "Assistant Administrator")


def after_install():
    after_migrate()


def after_migrate():
    _ensure_agent_customer_group()
    _ensure_assistant_center_access()
    _ensure_pending_cash_in_payments_sidebar()
    _ensure_expense_setting_in_settings_sidebar()
    _drop_naming_series_overrides()
    _backfill_expense_note_links()
    _ensure_expense_note_list_columns()
    _ensure_history_db()
    _ensure_fleet_in_desktop_layouts()


def _ensure_fleet_in_desktop_layouts():
    """Workspace baru TIDAK muncul untuk user yang punya snapshot Desktop Layout, dan
    reset-to-default kalah oleh re-sync localStorage — jadi entry Fleet disuntik
    langsung ke tiap snapshot (disisipkan setelah Master / Expedition)."""
    import json

    for name in frappe.get_all("Desktop Layout", pluck="name"):
        doc = frappe.get_doc("Desktop Layout", name)
        lay = json.loads(doc.layout or "[]")
        if not lay or any(e.get("name") == "Fleet" for e in lay):
            continue
        anchor = next(
            (i for i, e in enumerate(lay) if e.get("name") in ("Master", "Expedition")), None
        )
        base = lay[anchor] if anchor is not None else {}
        fleet = dict(
            base,
            name="Fleet",
            label="Fleet",
            link_to="Fleet",
            link_type="Workspace Sidebar",
            icon="truck",
            app="erp",
            standard=1,
        )
        lay.insert(anchor + 1 if anchor is not None else len(lay), fleet)
        doc.layout = json.dumps(lay)
        doc.save(ignore_permissions=True)


def _ensure_history_db():
    """Database terpisah `history` (breadcrumb GPS Fleet, tabel route_history).

    SEKALI per server (sebagai root MariaDB) user site harus diberi hak dulu:
        GRANT ALL PRIVILEGES ON `history`.* TO '<db_name site>'@'%'; FLUSH PRIVILEGES;
    Setelah itu migrate membuat & menjaga schema-nya sendiri. Tanpa grant, langkah ini
    dilewati dengan pesan di error log (tidak menggagalkan migrate).
    """
    try:
        frappe.db.sql_ddl(
            "create database if not exists history character set utf8mb4 collate utf8mb4_unicode_ci"
        )
        frappe.db.sql_ddl(
            """create table if not exists history.route_history (
                id bigint unsigned not null auto_increment,
                dispatch_order varchar(140) not null,
                dpo_item varchar(140) not null,
                trip int not null default 1,
                driver varchar(140) null,
                vehicle varchar(140) not null,
                latitude decimal(10,6) not null,
                longitude decimal(10,6) not null,
                recorded_at datetime not null,
                primary key (id),
                key idx_do_item_time (dpo_item, trip, recorded_at),
                key idx_do_time (dispatch_order, recorded_at),
                key idx_vehicle_time (vehicle, recorded_at)
            ) engine=InnoDB"""
        )
        # tabel lama (sebelum ada ritase): tambahkan kolom trip
        cols = [c[0] for c in frappe.db.sql("show columns from history.route_history")]
        if "trip" not in cols:
            frappe.db.sql_ddl("alter table history.route_history add column trip int not null default 1 after dpo_item")
        # arsip trip yang DIHAPUS user (bahan pemeriksaan kalau berkasus) — 1 baris per step
        frappe.db.sql_ddl(
            """create table if not exists history.dispatch_order_history (
                id bigint unsigned not null auto_increment,
                dispatch_order varchar(140) not null,
                dpo_no varchar(140) null,
                dpo_item varchar(140) not null,
                trip int not null default 1,
                driver varchar(140) null,
                vehicle varchar(140) null,
                chasis varchar(140) null,
                step int null,
                step_type varchar(40) null,
                point_type varchar(40) null,
                point varchar(140) null,
                start datetime null,
                end datetime null,
                deleted_by varchar(140) not null,
                deleted_at datetime not null,
                primary key (id),
                key idx_do (dispatch_order, deleted_at),
                key idx_item_trip (dpo_item, trip)
            ) engine=InnoDB"""
        )
        cols = [c[0] for c in frappe.db.sql("show columns from history.dispatch_order_history")]
        if "chasis" not in cols:
            frappe.db.sql_ddl("alter table history.dispatch_order_history add column chasis varchar(140) null after vehicle")
    except Exception:
        frappe.log_error(
            "Database `history` belum bisa dibuat — beri GRANT ALL ON history.* ke user site "
            "sebagai root MariaDB lalu migrate ulang (lihat erp/install.py _ensure_history_db).",
            "ensure_history_db",
        )


def _ensure_agent_customer_group():
    # "Agent Customer" di Packing List Item = Customer bergrup Agent (filter di packing_list.js).
    # Ini master data, bukan customization schema core — tetap sesuai aturan steril di atas.
    if not frappe.db.exists("Customer Group", "Agent"):
        frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": "Agent",
            "parent_customer_group": "All Customer Groups",
        }).insert(ignore_permissions=True)


# Kolom list Expense Note yang WAJIB ada, beserta patokan urutannya (disisipkan sesudah
# fieldname ini). List View Settings menyimpan daftar kolom secara utuh dan MENGGANTIKAN
# in_list_view dari doctype — jadi field baru tidak akan pernah muncul di site yang list
# view-nya pernah diatur user, sampai daftarnya ikut ditambah di sini.
_EN_LIST_COLUMNS = (
    ("invoice_no", "Invoice", "net_total"),
    ("payment_no", "Payment", "invoice_no"),
)


def _ensure_expense_note_list_columns():
    import json

    if not frappe.db.exists("List View Settings", "Expense Note"):
        return  # belum pernah diatur -> urutan in_list_view dari doctype sudah dipakai
    lvs = frappe.get_doc("List View Settings", "Expense Note")
    cols = json.loads(lvs.fields or "[]")
    changed = False
    for fieldname, label, after in _EN_LIST_COLUMNS:
        if any(c.get("fieldname") == fieldname for c in cols):
            continue
        at = next((i for i, c in enumerate(cols) if c.get("fieldname") == after), len(cols) - 1)
        cols.insert(at + 1, {"fieldname": fieldname, "label": label})
        changed = True
    if changed:
        lvs.fields = json.dumps(cols)
        lvs.save(ignore_permissions=True)


def _backfill_expense_note_links():
    """Kolom Invoice/Payment di list Expense Note diisi oleh hook Sales Invoice / Payment
    Entry — dokumen yang tautannya dibuat SEBELUM kolom ini ada tidak pernah kena hook itu,
    jadi diisi sekali di sini. Hanya EN yang benar-benar punya tautan yang disentuh."""
    from erp.expedition.doctype.expense_note.expense_note import sync_document_links

    names = set(
        frappe.get_all(
            "Sales Invoice Reimburse", filters={"parenttype": "Sales Invoice"}, pluck="expense_note"
        )
    ) | set(
        frappe.get_all(
            "Payment Entry Reference", filters={"parenttype": "Payment Entry"}, pluck="custom_expense_note"
        )
    )
    sync_document_links(names)


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


# Menu "Expense Setting" (single milik erp) di sidebar ERPNext Settings, tepat di bawah
# Selling Settings. Sidebar itu aset bawaan yang di-import ulang tiap migrate — alasan
# sama dengan _ensure_pending_cash_in_payments_sidebar. Tapi JANGAN sb.save(): sidebar
# ini punya baris bawaan yang link-nya sudah tidak valid (mis. Repost Accounting Ledger
# Settings), full save gagal LinkValidationError gara-gara baris yang bukan urusan kita.
# Jadi baris child di-insert LANGSUNG dengan idx digeser manual. Idempoten.
def _ensure_expense_setting_in_settings_sidebar():
    if not frappe.db.exists("DocType", "Expense Setting"):
        return
    if not frappe.db.exists("Workspace Sidebar", "ERPNext Settings"):
        return
    parent_filter = {"parenttype": "Workspace Sidebar", "parent": "ERPNext Settings"}
    if frappe.db.exists("Workspace Sidebar Item", {**parent_filter, "link_to": "Expense Setting"}):
        return

    pos = frappe.db.get_value(
        "Workspace Sidebar Item", {**parent_filter, "link_to": "Selling Settings"}, "idx"
    )
    if pos:
        frappe.db.sql(
            """update `tabWorkspace Sidebar Item` set idx = idx + 1
               where parenttype='Workspace Sidebar' and parent='ERPNext Settings' and idx > %s""",
            pos,
        )
    frappe.get_doc({
        "doctype": "Workspace Sidebar Item",
        "parenttype": "Workspace Sidebar",
        "parent": "ERPNext Settings",
        "parentfield": "items",
        "idx": (pos or 0) + 1,
        "label": "Expense Setting",
        "link_type": "DocType",
        "link_to": "Expense Setting",
        "child": 0,
        "indent": 0,
        "collapsible": 0,
        "show_arrow": 0,
        "keep_closed": 0,
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

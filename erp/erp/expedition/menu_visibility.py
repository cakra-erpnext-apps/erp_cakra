"""Flag Connection ikut menyembunyikan menu desk-nya, bukan cuma field di Expense Note.

Dulu `show_shipping_list` / `show_packing_list` hanya mengatur field Connection di Expense
Note (lihat expense_note.get_connection_settings). Site yang tidak memakai Shipping List
tetap melihat menunya di sidebar & workspace Expedition — membingungkan, karena menu ada
tapi alurnya tidak dipakai. Sekarang flag yang sama menggerbangi menunya juga.

Flagnya tinggal di ERPNext Custom Setting > Flag (dulu doctype sendiri, Expense Setting;
dipindah lewat patch move_expense_setting_flags supaya semua setting custom satu tempat).
Dipasang saat setting itu disimpan (doc_events) DAN saat migrate, supaya menu yang di-seed
ulang oleh migrate langsung ikut aturan yang berlaku.
"""

import frappe

SETTING_DT = "ERPNext Custom Setting"

# flag -> menu yang digerbanginya. Nilai: (workspace sidebar, [ (workspace, link_to) ])
GATED = {
    "show_shipping_list": {
        "sidebar": [("Expedition", "Shipping List")],
        "links": [("Expedition", "Shipping List")],
    },
    "show_packing_list": {
        "sidebar": [("Expedition", "Packing List")],
        # Packing List Type ikut disembunyikan: masternya tak ada gunanya tanpa Packing List.
        "links": [("Expedition", "Packing List"), ("Master", "Packing List Type")],
    },
}

# Default menyusul get_connection_settings: Packing List menyala, Shipping List tidak.
DEFAULTS = {"show_shipping_list": 0, "show_packing_list": 1}

# Urutan menu sidebar kalau sebuah item perlu dipasang kembali: item dimasukkan SESUDAH
# link ini. Sidebar Item tak punya field `hidden`, jadi menyalakan flag = menambah barisnya
# lagi, dan tanpa jangkar posisinya akan melompat ke paling bawah.
SIDEBAR_AFTER = {"Packing List": "CRM Estimation", "Shipping List": "Packing List"}


def _flags():
    es = frappe.db.get_singles_dict(SETTING_DT)
    out = {}
    for key, default in DEFAULTS.items():
        v = es.get(key)
        out[key] = frappe.utils.cint(v) if v is not None else default
    return out


def _apply_sidebar(sidebar, link_to, show):
    sb = frappe.get_doc("Workspace Sidebar", sidebar)
    items = sb.get("items")
    found = next((i for i in items if i.type == "Link" and i.link_to == link_to), None)
    if bool(found) == bool(show):
        return False
    if show:
        sb.append("items", {"label": link_to, "type": "Link",
                            "link_type": "DocType", "link_to": link_to})
        anchor = SIDEBAR_AFTER.get(link_to)
        pos = next((n for n, i in enumerate(items)
                    if i.type == "Link" and i.link_to == anchor), None)
        if pos is not None:
            items.insert(pos + 1, items.pop())
    else:
        items.remove(found)
    for n, i in enumerate(items, 1):
        i.idx = n
    # Sidebar bawaan bisa memuat baris rusak dari upstream; jangan sampai itu memblokir save.
    sb.flags.ignore_links = True
    sb.save(ignore_permissions=True)
    return True


def _apply_link(workspace, link_to, show):
    """Workspace Link punya field `hidden`, jadi cukup di-toggle — urutannya terjaga."""
    w = frappe.get_doc("Workspace", workspace)
    row = next((l for l in (w.get("links") or []) if l.link_to == link_to), None)
    if not row or frappe.utils.cint(row.hidden) == (0 if show else 1):
        return False
    row.hidden = 0 if show else 1
    w.flags.ignore_links = True
    w.save(ignore_permissions=True)
    return True


def apply_menu_visibility(doc=None, method=None):
    """Tegakkan tampil/sembunyi menu sesuai flag Expense Setting. Idempoten dua arah."""
    changed = False
    flags = _flags()
    for key, spec in GATED.items():
        show = flags[key]
        for sidebar, link_to in spec["sidebar"]:
            changed |= _apply_sidebar(sidebar, link_to, show)
        for workspace, link_to in spec["links"]:
            changed |= _apply_link(workspace, link_to, show)
    if changed:
        frappe.clear_cache()
    return changed

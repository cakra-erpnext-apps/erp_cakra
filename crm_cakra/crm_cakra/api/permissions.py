"""Akses berbasis branch — CUSTOM, ROLE-BASED, otomatis untuk SEMUA modul.

Config 'CMI Branch Access' (Single) mengatur level akses per Role:
  See All / Branch + Owner / Owner Only.  (level tertinggi menang kalau user banyak role)

Handler wildcard "*" (permission_query_conditions & has_permission di hooks) berlaku ke
SETIAP doctype yang punya field `branch_office` (Link CMI Office) — jadi menambah scope ke
modul lain = cukup tambah field `branch_office` ke doctype-nya, tanpa ubah kode/daftar.

`branch_office` dokumen baru diisi otomatis dari branch UTAMA pembuat (set_branch_from_user,
doc_events["*"] before_insert). System Manager & Administrator selalu See All.

MULTI-BRANCH: User.branch = branch utama (untuk stempel); field `custom_branches`
(Table MultiSelect -> CMI User Branch) = branch tambahan yang boleh DILIHAT. Visible =
branch utama + additional -> filter `branch_office IN (...)`.
"""

import frappe

SEE_ALL = 3
BRANCH_OWNER = 2
OWNER_ONLY = 1
_LEVEL = {"See All": SEE_ALL, "Branch + Owner": BRANCH_OWNER, "Owner Only": OWNER_ONLY}
_ALWAYS_ALL = {"System Manager"}


def _user_branch(user):
    """Branch UTAMA (untuk stempel dokumen baru)."""
    if not user or user == "Guest":
        return None
    return frappe.db.get_value("User", user, "branch")


def _user_branches(user):
    """SEMUA branch yang boleh DILIHAT user = branch utama + Additional Branches (multi)."""
    if not user or user == "Guest":
        return []
    branches = []
    primary = _user_branch(user)
    if primary:
        branches.append(primary)
    try:
        for r in frappe.get_all(
            "CMI User Branch", filters={"parent": user, "parenttype": "User"}, fields=["branch"]
        ):
            if r.branch and r.branch not in branches:
                branches.append(r.branch)
    except Exception:
        pass
    return branches


@frappe.whitelist()
def get_my_branch():
    """Branch utama user login — untuk mengisi branch_office di form BARU (server tetap
    mengisinya lagi di before_insert; ini hanya supaya field read-only tak terlihat kosong)."""
    return _user_branch(frappe.session.user)


def set_branch_from_user(doc, method=None):
    """doc_events["*"] before_insert: isi branch_office dari branch pembuat (kalau doctype
    punya field itu & masih kosong). WAJIB aman untuk semua doctype."""
    if not doc.meta.has_field("branch_office"):
        return
    if doc.get("branch_office"):
        return
    branch = _user_branch(doc.owner or frappe.session.user)
    if branch:
        doc.branch_office = branch


def _job_branch(shipping_list=None, packing_list=None):
    """branch_office job (Shipping/Packing List) yang tertaut."""
    if shipping_list:
        b = frappe.db.get_value("Shipping List", shipping_list, "branch_office")
        if b:
            return b
    if packing_list:
        b = frappe.db.get_value("Packing List", packing_list, "branch_office")
        if b:
            return b
    return None


def set_branch_from_job(doc, method=None):
    """branch_office DITURUNKAN dari job/type (OTORITATIF), bukan dari pembuat:
      - Shipping List  -> Shipment Type.branch
      - Packing List   -> Packing List Type.branch
      - Expense Note   -> Shipping/Packing List (shipping_list/packing_list).branch_office
      - Sales Invoice  -> custom_shipping_list/custom_packing_list.branch_office
    Kalau tak ketemu, biarkan nilai lama (fallback branch pembuat dari set_branch_from_user).
    Wire di doc_events before_validate doctype terkait."""
    dt = doc.doctype
    branch = None
    if dt == "Shipping List" and doc.get("type"):
        branch = frappe.db.get_value("Shipment Type", doc.get("type"), "branch")
    elif dt == "Packing List" and doc.get("type"):
        branch = frappe.db.get_value("Packing List Type", doc.get("type"), "branch")
    elif dt == "Expense Note":
        branch = _job_branch(doc.get("shipping_list"), doc.get("packing_list"))
    elif dt == "Sales Invoice":
        branch = _job_branch(doc.get("custom_shipping_list"), doc.get("custom_packing_list"))
    if branch:
        doc.branch_office = branch


def backfill_job_branch():
    """Re-derive branch_office dokumen LAMA: Shipping/Packing List dari branch Type-nya,
    lalu Expense Note & Sales Invoice dari job tertaut. Jalankan SETELAH mengisi field
    Branch di tiap Shipment Type / Packing List Type.
    Panggil: bench --site <site> execute crm_cakra.api.permissions.backfill_job_branch"""
    res = {}
    frappe.db.sql("""UPDATE `tabShipping List` sl JOIN `tabShipment Type` t ON sl.type = t.name
        SET sl.branch_office = t.branch WHERE t.branch IS NOT NULL AND t.branch != ''""")
    res["shipping_list"] = frappe.db._cursor.rowcount
    frappe.db.sql("""UPDATE `tabPacking List` pl JOIN `tabPacking List Type` t ON pl.type = t.name
        SET pl.branch_office = t.branch WHERE t.branch IS NOT NULL AND t.branch != ''""")
    res["packing_list"] = frappe.db._cursor.rowcount
    frappe.db.sql("""UPDATE `tabExpense Note` e JOIN `tabShipping List` sl ON e.shipping_list = sl.name
        SET e.branch_office = sl.branch_office WHERE sl.branch_office IS NOT NULL AND sl.branch_office != ''""")
    res["expense_from_sl"] = frappe.db._cursor.rowcount
    frappe.db.sql("""UPDATE `tabExpense Note` e JOIN `tabPacking List` pl ON e.packing_list = pl.name
        SET e.branch_office = pl.branch_office
        WHERE (e.branch_office IS NULL OR e.branch_office = '') AND pl.branch_office IS NOT NULL AND pl.branch_office != ''""")
    res["expense_from_pl"] = frappe.db._cursor.rowcount
    frappe.db.sql("""UPDATE `tabSales Invoice` i JOIN `tabShipping List` sl ON i.custom_shipping_list = sl.name
        SET i.branch_office = sl.branch_office WHERE sl.branch_office IS NOT NULL AND sl.branch_office != ''""")
    res["invoice_from_sl"] = frappe.db._cursor.rowcount
    frappe.db.sql("""UPDATE `tabSales Invoice` i JOIN `tabPacking List` pl ON i.custom_packing_list = pl.name
        SET i.branch_office = pl.branch_office
        WHERE (i.branch_office IS NULL OR i.branch_office = '') AND pl.branch_office IS NOT NULL AND pl.branch_office != ''""")
    res["invoice_from_pl"] = frappe.db._cursor.rowcount
    frappe.db.commit()
    return res


def _access_config():
    """(default_level, {role: level}, blank_visible) dari 'CMI Branch Access'. Cached.

    blank_visible: dokumen ber-branch_office KOSONG ikut terlihat oleh user level
    Branch + Owner (data lama yang belum di-tag). Tidak berlaku utk Owner Only.
    """
    cache = frappe.cache().get_value("cmi_branch_access")
    if cache is not None:
        return cache
    default_level = BRANCH_OWNER
    role_map = {}
    blank_visible = True
    try:
        s = frappe.get_cached_doc("CMI Branch Access")
        default_level = _LEVEL.get(s.get("default_access"), BRANCH_OWNER)
        for r in s.get("role_access") or []:
            if r.get("role"):
                role_map[r.role] = _LEVEL.get(r.get("access_level"), BRANCH_OWNER)
        blank_visible = (s.get("blank_branch") or "Terlihat semua") == "Terlihat semua"
    except Exception:
        pass
    out = (default_level, role_map, blank_visible)
    frappe.cache().set_value("cmi_branch_access", out)
    return out


def _access_level(user):
    if user == "Administrator":
        return SEE_ALL
    roles = set(frappe.get_roles(user))
    if roles & _ALWAYS_ALL:
        return SEE_ALL
    default_level, role_map, _blank = _access_config()
    level = 0
    for role in roles:
        level = max(level, role_map.get(role, default_level))
    return level or default_level


def _has_branch_field(doctype):
    """True kalau doctype punya kolom branch_office (target scope)."""
    try:
        return bool(frappe.get_meta(doctype).get_field("branch_office"))
    except Exception:
        return False


def _visible(user, table):
    level = _access_level(user)
    if level >= SEE_ALL:
        return ""
    esc_user = frappe.db.escape(user)
    like_user = frappe.db.escape('%"' + user + '"%')
    conds = [
        f"`{table}`.owner = {esc_user}",
        f"`{table}`._assign LIKE {like_user}",
    ]
    if level >= BRANCH_OWNER:
        branches = _user_branches(user)
        if branches:
            vals = ", ".join(frappe.db.escape(b) for b in branches)
            conds.append(f"`{table}`.branch_office IN ({vals})")
        # Dokumen tanpa branch (data lama belum di-tag) ikut terlihat kalau opsinya begitu.
        if _access_config()[2]:
            conds.append(f"(`{table}`.branch_office IS NULL OR `{table}`.branch_office = '')")
    return "(" + " OR ".join(conds) + ")"


def _doc_has_permission(doc, user):
    level = _access_level(user)
    if level >= SEE_ALL:
        return True
    if doc.get("owner") == user:
        return True
    assignees = frappe.parse_json(doc.get("_assign") or "[]") or []
    if user in assignees:
        return True
    if level >= BRANCH_OWNER:
        if not doc.get("branch_office") and _access_config()[2]:
            return True  # dokumen tanpa branch -> terlihat (sesuai opsi)
        branches = _user_branches(user)
        return bool(branches) and doc.get("branch_office") in branches
    return False


# --- Handler WILDCARD "*" (semua doctype ber-field branch_office) ---
def branch_query_conditions(user=None, doctype=None):
    if not doctype or not _has_branch_field(doctype):
        return ""
    return _visible(user or frappe.session.user, "tab" + doctype)


def branch_has_permission(doc, ptype=None, user=None, **kwargs):
    # WAJIB True untuk doctype tanpa branch_office (kalau falsy, Frappe MENOLAK).
    if not doc or not _has_branch_field(doc.doctype):
        return True
    return _doc_has_permission(doc, user or frappe.session.user)

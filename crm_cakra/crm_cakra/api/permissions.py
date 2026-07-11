"""Akses berbasis branch — CUSTOM, ROLE-BASED, otomatis untuk SEMUA modul.

Config 'CMI Branch Access' (Single) mengatur level akses per Role:
  See All / Branch + Owner / Owner Only.  (level tertinggi menang kalau user banyak role)

Handler wildcard "*" (permission_query_conditions & has_permission di hooks) berlaku ke
SETIAP doctype yang punya field `branch_office` (Link CMI Office) — jadi menambah scope ke
modul lain = cukup tambah field `branch_office` ke doctype-nya, tanpa ubah kode/daftar.

`branch_office` dokumen baru diisi otomatis dari branch pembuat (set_branch_from_user,
doc_events["*"] before_insert). System Manager & Administrator selalu See All.
"""

import frappe

SEE_ALL = 3
BRANCH_OWNER = 2
OWNER_ONLY = 1
_LEVEL = {"See All": SEE_ALL, "Branch + Owner": BRANCH_OWNER, "Owner Only": OWNER_ONLY}
_ALWAYS_ALL = {"System Manager"}


def _user_branch(user):
    if not user or user == "Guest":
        return None
    return frappe.db.get_value("User", user, "branch")


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


def _access_config():
    """(default_level, {role: level}) dari 'CMI Branch Access'. Cached."""
    cache = frappe.cache().get_value("cmi_branch_access")
    if cache is not None:
        return cache
    default_level = BRANCH_OWNER
    role_map = {}
    try:
        s = frappe.get_cached_doc("CMI Branch Access")
        default_level = _LEVEL.get(s.get("default_access"), BRANCH_OWNER)
        for r in s.get("role_access") or []:
            if r.get("role"):
                role_map[r.role] = _LEVEL.get(r.get("access_level"), BRANCH_OWNER)
    except Exception:
        pass
    out = (default_level, role_map)
    frappe.cache().set_value("cmi_branch_access", out)
    return out


def _access_level(user):
    if user == "Administrator":
        return SEE_ALL
    roles = set(frappe.get_roles(user))
    if roles & _ALWAYS_ALL:
        return SEE_ALL
    default_level, role_map = _access_config()
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
        branch = _user_branch(user)
        if branch:
            conds.append(f"`{table}`.branch_office = {frappe.db.escape(branch)}")
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
        branch = _user_branch(user)
        return bool(branch) and doc.get("branch_office") == branch
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

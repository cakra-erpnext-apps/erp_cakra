import frappe

# Role yang boleh melihat SEMUA data (bypass filter).
BYPASS_ROLES = {"System Manager", "Sales Manager", "Sales Master Manager"}


def _can_see_all(user):
    if user == "Administrator":
        return True
    return bool(BYPASS_ROLES & set(frappe.get_roles(user)))


def _user_branch(user):
    """Branch (CMI Office) yang di-set di record User."""
    if not user or user == "Guest":
        return None
    return frappe.db.get_value("User", user, "branch")


def set_branch_from_user(doc, method=None):
    """Auto-isi branch_office dari branch pembuat saat dokumen baru dibuat.

    Hanya diisi bila masih kosong, supaya pilihan office manual tetap dihormati.
    branch_office dipakai untuk penomoran & laporan, bukan lagi untuk hak akses.
    """
    if doc.get("branch_office"):
        return
    branch = _user_branch(doc.owner or frappe.session.user)
    if branch:
        doc.branch_office = branch


# ============================================================
# Siapa boleh MELIHAT dokumen CRM (Lead / Inquiry / Quotation / Estimation).
#
# Sales Manager / Sales Master Manager / System Manager / Administrator -> semua.
# Selain itu, dokumen terlihat bila salah satu terpenuhi:
#   - dia yang membuat (owner)
#   - dokumen di-assign ke dia (_assign)
#   - branch_office dokumen sama dengan branch user  -> rekan sesama branch
#
# Catatan penting soal user tanpa branch: klausa branch DILEWATI, bukan berarti
# lolos filter. Versi lama justru `return ""` (lihat semua) untuk kasus ini, dan
# itulah yang membocorkan seluruh data ke Sales User yang branch-nya kosong.
#
# Estimation tidak punya kolom branch_office, jadi tetap owner/assigned saja.
# ============================================================
def _visible(user, table, with_branch=True):
    if _can_see_all(user):
        return ""
    esc_user = frappe.db.escape(user)
    # _assign berisi JSON '["a@x.com"]'. Kutipnya ikut dicocokkan supaya email yang
    # merupakan akhiran email lain (iza@x.com vs riza@x.com) tidak ikut kena.
    like_user = frappe.db.escape('%"' + user + '"%')
    conds = [
        f"`{table}`.owner = {esc_user}",
        f"`{table}`._assign LIKE {like_user}",
    ]
    branch = _user_branch(user) if with_branch else None
    if branch:
        conds.append(f"`{table}`.branch_office = {frappe.db.escape(branch)}")
    return "(" + " OR ".join(conds) + ")"


def _doc_has_permission(doc, user, with_branch=True):
    if _can_see_all(user):
        return True
    if doc.get("owner") == user:
        return True
    assignees = frappe.parse_json(doc.get("_assign") or "[]") or []
    if user in assignees:
        return True
    branch = _user_branch(user) if with_branch else None
    return bool(branch) and doc.get("branch_office") == branch


# --- get_permission_query_conditions (filter LIST view) ---
def quotation_query_conditions(user=None):
    return _visible(user or frappe.session.user, "tabCRM Quotation")


def lead_query_conditions(user=None):
    return _visible(user or frappe.session.user, "tabCRM Lead")


def inquiry_query_conditions(user=None):
    return _visible(user or frappe.session.user, "tabCRM Inquiry")


def estimation_query_conditions(user=None):
    return _visible(user or frappe.session.user, "tabCRM Estimation", with_branch=False)


# --- has_permission (akses buka 1 dokumen langsung) ---
def quotation_has_permission(doc, ptype=None, user=None, **kwargs):
    return _doc_has_permission(doc, user or frappe.session.user)


def lead_has_permission(doc, ptype=None, user=None, **kwargs):
    return _doc_has_permission(doc, user or frappe.session.user)


def inquiry_has_permission(doc, ptype=None, user=None, **kwargs):
    return _doc_has_permission(doc, user or frappe.session.user)


def estimation_has_permission(doc, ptype=None, user=None, **kwargs):
    return _doc_has_permission(doc, user or frappe.session.user, with_branch=False)

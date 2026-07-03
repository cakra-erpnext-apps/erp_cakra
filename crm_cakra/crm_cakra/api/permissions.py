import frappe

# Role yang boleh melihat SEMUA data (bypass filter).
BYPASS_ROLES = {"System Manager", "Sales Manager"}


def _can_see_all(user):
    if user == "Administrator":
        return True
    return bool(BYPASS_ROLES & set(frappe.get_roles(user)))


def _user_branch(user):
    """Branch (CMI Office) yang di-set di record User. Kosong = tidak difilter."""
    if not user or user == "Guest":
        return None
    return frappe.db.get_value("User", user, "branch")


# ============================================================
# Branch-based access (Lead / Inquiry / Quotation)
# User hanya lihat dokumen yang branch_office-nya = branch user.
# User tanpa branch, atau role bypass, lihat semua.
# ============================================================
def _branch_scoped(user, table):
    if _can_see_all(user):
        return ""
    branch = _user_branch(user)
    if not branch:
        return ""  # user tanpa branch -> tidak difilter (lihat semua)
    return f"`{table}`.branch_office = {frappe.db.escape(branch)}"


def _branch_doc_has_permission(doc, user):
    if _can_see_all(user):
        return True
    branch = _user_branch(user)
    if not branch:
        return True
    return doc.get("branch_office") == branch


def set_branch_from_user(doc, method=None):
    """Auto-isi branch_office dari branch pembuat saat dokumen baru dibuat.

    Hanya diisi bila masih kosong, supaya pilihan office manual tetap dihormati.
    """
    if doc.get("branch_office"):
        return
    branch = _user_branch(doc.owner or frappe.session.user)
    if branch:
        doc.branch_office = branch


# --- get_permission_query_conditions (filter LIST view) ---
def quotation_query_conditions(user=None):
    return _branch_scoped(user or frappe.session.user, "tabCRM Quotation")


def lead_query_conditions(user=None):
    return _branch_scoped(user or frappe.session.user, "tabCRM Lead")


def inquiry_query_conditions(user=None):
    return _branch_scoped(user or frappe.session.user, "tabCRM Inquiry")


# --- has_permission (akses buka 1 dokumen langsung) ---
def quotation_has_permission(doc, ptype=None, user=None, **kwargs):
    return _branch_doc_has_permission(doc, user or frappe.session.user)


def lead_has_permission(doc, ptype=None, user=None, **kwargs):
    return _branch_doc_has_permission(doc, user or frappe.session.user)


def inquiry_has_permission(doc, ptype=None, user=None, **kwargs):
    return _branch_doc_has_permission(doc, user or frappe.session.user)


# ============================================================
# Estimation tetap berbasis owner/assigned (tidak punya branch_office).
# ============================================================
def _assigned_or_owned(user, table):
    if _can_see_all(user):
        return ""
    esc_user = frappe.db.escape(user)
    like_user = frappe.db.escape("%" + user + "%")
    return f"(`{table}`.owner = {esc_user} OR `{table}`._assign LIKE {like_user})"


def _doc_has_permission(doc, user):
    if _can_see_all(user):
        return True
    if doc.get("owner") == user:
        return True
    assignees = frappe.parse_json(doc.get("_assign") or "[]") or []
    return user in assignees


def estimation_query_conditions(user=None):
    return _assigned_or_owned(user or frappe.session.user, "tabCRM Estimation")


def estimation_has_permission(doc, ptype=None, user=None, **kwargs):
    return _doc_has_permission(doc, user or frappe.session.user)

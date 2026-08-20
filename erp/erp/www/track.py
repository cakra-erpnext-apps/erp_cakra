import frappe
from frappe.utils import now_datetime

no_cache = 1


def get_context(context):
    """Halaman publik: token dibaca di browser, server hanya menyajikan kerangka + identitas."""
    context.no_cache = 1
    context.show_sidebar = False
    context.token = frappe.form_dict.get("t") or ""
    context.company = (
        frappe.defaults.get_global_default("company")
        or frappe.db.get_value("Company", {}, "company_name")
        or "CMI"
    )
    context.year = now_datetime().year
    return context

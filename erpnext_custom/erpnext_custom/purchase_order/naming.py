"""Purchase Order numbering owned by the Purchase Order customization."""

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import getdate, today


def _uppercase_code(value, label):
    value = re.sub(r"[^A-Z0-9.-]+", "-", (value or "").strip().upper()).strip("-")
    if not value:
        frappe.throw(_("{0} wajib diisi untuk membuat nomor Purchase Order.").format(label))
    return value


def make_purchase_order_name(doc):
    """Return PO/{TYPE}/{COMPANY}/{YEAR}/{####}, uppercase.

    Because the counter is preceded by Type, company code, and year, Frappe
    maintains a separate four-digit series for every such combination.
    """
    po_type = _uppercase_code(doc.get("custom_type"), _("Type"))
    company = frappe.db.get_value(
        "Company",
        doc.get("company"),
        ["custom_company_code", "abbr"],
        as_dict=True,
    ) or {}
    company_code = _uppercase_code(
        company.get("custom_company_code") or company.get("abbr"),
        _("Company Code"),
    )
    year = getdate(doc.get("transaction_date") or today()).year
    pattern = f"PO/{po_type}/{company_code}/{year}/.####."
    return make_autoname(pattern, "Purchase Order", doc)

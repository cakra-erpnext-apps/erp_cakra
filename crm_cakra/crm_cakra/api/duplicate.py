import frappe
from frappe import _

ALLOWED = ("CRM Quotation", "CRM Inquiry")


@frappe.whitelist()
def duplicate_doc(doctype, name):
    """Duplikat 1 dokumen (semua field + child table) menjadi draft baru.

    Field workflow/unik yang tidak boleh diwariskan di-reset:
    - state -> Draft, void dibersihkan
    - CRM Quotation: inquiry & number (unik) dikosongkan
    """
    if doctype not in ALLOWED:
        frappe.throw(_("Duplicate is not allowed for {0}").format(doctype))

    if not frappe.has_permission(doctype, "read", doc=name):
        frappe.throw(_("Not permitted to read {0}").format(name), frappe.PermissionError)
    frappe.has_permission(doctype, "create", throw=True)

    src = frappe.get_doc(doctype, name)
    new = frappe.copy_doc(src)

    if new.meta.has_field("state"):
        new.state = "Draft"
    for field, value in (("is_void", 0), ("void_reason", None), ("void_at", None), ("void_by", None)):
        if new.meta.has_field(field):
            new.set(field, value)

    if doctype == "CRM Quotation":
        # 1 inquiry hanya boleh dipakai 1 quotation, dan number unik -> kosongkan.
        new.inquiry = None
        new.number = None
        new.printed_by = None

    new.insert()
    return new.name

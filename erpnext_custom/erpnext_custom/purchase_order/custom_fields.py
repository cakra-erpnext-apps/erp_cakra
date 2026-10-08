"""Custom Field definitions for Purchase Order.

Keep Purchase Order-specific fields in this package so they are not mixed with
customizations for other ERPNext doctypes.
"""

CUSTOM_FIELDS = [
    {
        "fieldname": "custom_type",
        "fieldtype": "Link",
        "label": "Type",
        "options": "Purchase Order Type",
        "reqd": 1,
        "insert_after": "supplier",
        "module": "ERPNext Custom",
        # Nomor PO memuat kode Type (PO/{TYPE}/{COMPANY}/{YEAR}/{####}) dan counternya
        # berjalan per tipe -> tidak bisa diganti setelah PO tersimpan (bernomor).
        # Server menegakkan hal yang sama lewat numbering.guard_type_change.
        "read_only_depends_on": "eval:!doc.__islocal",
    },
]


BRANCH_FIELD = {
    "fieldname": "branch",
    "fieldtype": "Link",
    "label": "Branch",
    "options": "CMI Office",
    "in_list_view": 1,
    "description": "Branch untuk dokumen yang memakai type ini. Kosong = tidak mengunci branch.",
}


DISABLED_FIELD = {"fieldname": "disabled", "fieldtype": "Check", "label": "Disabled", "in_list_view": 1}


def ensure_type_master(doctype="Purchase Order Type",
                       roles=("Purchase Manager", "Purchase User", "System Manager"),
                       no_delete_role="Purchase User",
                       seeds=("Non-Job", "PCP.IJ", "SH.IJ")):
    """Create an editable "<Document> Type" master (type_name + branch) and its initial values.

    Dipakai juga oleh Sales Order Type (sales_order/sales_order.py)."""
    import frappe

    if not frappe.db.exists("DocType", doctype):
        frappe.get_doc({
            "doctype": "DocType",
            "name": doctype,
            "module": "ERPNext Custom",
            "custom": 1,
            "autoname": "field:type_name",
            "naming_rule": "By fieldname",
            "title_field": "type_name",
            "allow_rename": 1,
            "track_changes": 1,
            "fields": [
                {
                    "fieldname": "type_name",
                    "fieldtype": "Data",
                    "label": "Type",
                    "reqd": 1,
                    "unique": 1,
                    "in_list_view": 1,
                    "in_global_search": 1,
                },
                dict(BRANCH_FIELD),
            ],
            "permissions": [
                {
                    "role": role,
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1 if role != no_delete_role else 0,
                    "print": 1,
                    "email": 1,
                    "report": 1,
                    "export": 1,
                    "share": 1,
                }
                for role in roles
            ],
        }).insert(ignore_permissions=True)
    else:
        # Recover cleanly if an older/failed migration created this master as a
        # standard DocType under a conflicting module name.
        frappe.db.set_value(
            "DocType",
            doctype,
            {"module": "ERPNext Custom", "custom": 1},
            update_modified=False,
        )
        frappe.clear_cache(doctype=doctype)

    doc = frappe.get_doc("DocType", doctype)
    have = {f.fieldname for f in doc.fields}
    if "branch" not in have:
        doc.append("fields", dict(BRANCH_FIELD))
    # Master yang di-disable tidak bisa dipilih di transaksi baru (pull_guard).
    if "disabled" not in have:
        doc.append("fields", dict(DISABLED_FIELD))
    if {"branch", "disabled"} - have:
        doc.save(ignore_permissions=True)

    for type_name in seeds:
        if not frappe.db.exists(doctype, type_name):
            frappe.get_doc({
                "doctype": doctype,
                "type_name": type_name,
            }).insert(ignore_permissions=True)


# Kolom grid Purchase Order Item, urut: Item | Qty | UOM | Price | Warehouse | Amount.
# `columns` = lebar relatif. Totalnya 16 (> 10): itu SAH — grid_row.js memasang kelas
# "column-limit-reached" dan grid-nya jadi bisa digeser horizontal, bukan ditolak.
ITEM_PROPERTIES = [
    ("item_code", "label", "Item", "Data"),
    ("item_code", "columns", "3", "Int"),
    ("qty", "columns", "2", "Int"),
    ("uom", "columns", "1", "Int"),
    ("rate", "label", "Price", "Data"),
    ("rate", "columns", "3", "Int"),
    ("warehouse", "label", "Warehouse", "Data"),
    ("warehouse", "columns", "3", "Int"),
    ("warehouse", "in_list_view", "1", "Check"),
    ("amount", "columns", "4", "Int"),
    # "Required By" dibuang dari form (diisi server = tanggal dokumen, lihat
    # overrides.purchasing.before_validate), jadi kolomnya tidak perlu memakan lebar grid
    # dan tidak boleh menuntut isian dari user.
    ("schedule_date", "in_list_view", "0", "Check"),
    ("schedule_date", "reqd", "0", "Check"),
]


def ensure_item_properties():
    """Apply Purchase Order Item presentation changes without editing ERPNext."""
    import frappe

    for field_name, prop, value, property_type in ITEM_PROPERTIES:
        filters = {
            "doc_type": "Purchase Order Item",
            "field_name": field_name,
            "property": prop,
        }
        name = frappe.db.exists("Property Setter", filters)
        setter = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
        setter.update({
            "doctype_or_field": "DocField",
            **filters,
            "value": value,
            "property_type": property_type,
            "module": "ERPNext Custom",
        })
        setter.save(ignore_permissions=True)


def ensure_list_view_status_labels():
    """Keep one PO list status column: Draft / Validate / Void."""
    import json

    import frappe

    # These temporary display fields are obsolete; the native status_field is
    # sufficient and avoids adding status columns to the core PO schema.
    for fieldname in ("custom_po_document", "custom_po_status"):
        custom_field = frappe.db.exists(
            "Custom Field",
            {"dt": "Purchase Order", "fieldname": fieldname},
        )
        if custom_field:
            frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)

    if not frappe.db.exists("List View Settings", "Purchase Order"):
        return

    settings = frappe.get_doc("List View Settings", "Purchase Order")
    fields = json.loads(settings.fields or "[]")
    updated = []
    display_fields = ("status_field", "status", "custom_po_document", "custom_po_status")
    for field in fields:
        if field.get("fieldname") in display_fields:
            continue
        updated.append(field)
        if field.get("fieldname") == "supplier_name":
            updated.append({"type": "Status", "fieldname": "status_field", "label": "Status"})

    if not any(field.get("fieldname") == "status_field" for field in updated):
        updated.insert(0, {"type": "Status", "fieldname": "status_field", "label": "Status"})

    if updated != fields:
        settings.fields = json.dumps(updated)
        settings.save(ignore_permissions=True)

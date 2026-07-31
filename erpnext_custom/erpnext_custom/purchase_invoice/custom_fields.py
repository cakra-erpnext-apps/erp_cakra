"""Purchase Invoice field properties.

The accounting field remains the native ``posting_date``. Only its presentation
and editability are customized, so every ERPNext posting continues to use it.
"""


def ensure_field_properties():
    import frappe

    properties = (
        ("posting_date", "label", "Date", "Data"),
        ("posting_date", "reqd", "1", "Check"),
        ("posting_date", "read_only", "0", "Check"),
        # ERPNext's stock controller locks posting_date while this flag is off.
        # Keep it enabled internally so Date stays editable without asking the
        # user to tick "Edit Posting Date and Time".
        ("set_posting_time", "default", "1", "Check"),
        ("set_posting_time", "hidden", "1", "Check"),
    )
    for field_name, prop, value, property_type in properties:
        filters = {
            "doc_type": "Purchase Invoice",
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

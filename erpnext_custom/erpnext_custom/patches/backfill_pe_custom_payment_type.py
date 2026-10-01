import frappe
from frappe.utils.fixtures import sync_fixtures


def execute():
    # Kolom custom_payment_type datang dari fixture, yang baru disinkron SESUDAH patch.
    sync_fixtures("erpnext_custom")
    frappe.db.sql("""
        update `tabPayment Entry`
        set custom_payment_type = if(payment_type = 'Receive' and party_type = 'Supplier',
                                     'Refund', payment_type)
        where ifnull(custom_payment_type, '') = ''""")
    # Pengganti checkbox "Refund dari Vendor".
    frappe.delete_doc_if_exists("Custom Field", "Payment Entry-custom_supplier_refund")

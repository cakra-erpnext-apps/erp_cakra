"""Pindahkan baris Invoice Type dari Selling Settings ke ERPNext Custom Setting.

Keduanya Single, jadi cukup mengalihkan parent baris child-nya — tidak ada data yang
disalin atau dibuat ulang. Dijalankan SEBELUM _drop_obsolete() menghapus Custom Field
lama di Selling Settings (after_migrate berjalan setelah patch).
"""

import frappe

OLD = ("Selling Settings", "custom_invoice_types")
NEW = ("ERPNext Custom Setting", "invoice_types")


def execute():
    if not frappe.db.table_exists("CMI Invoice Type"):
        return
    # Sudah pernah jalan (atau site baru yang langsung ter-seed di rumah baru) -> jangan
    # sentuh, supaya baris yang sudah diedit user di tempat baru tidak tertimpa.
    if frappe.db.exists("CMI Invoice Type", {"parenttype": NEW[0], "parentfield": NEW[1]}):
        return
    moved = frappe.db.sql(
        """UPDATE `tabCMI Invoice Type`
              SET parent = %s, parenttype = %s, parentfield = %s
            WHERE parenttype = %s AND parentfield = %s""",
        (NEW[0], NEW[0], NEW[1], OLD[0], OLD[1]),
    )
    frappe.db.commit()
    frappe.clear_cache(doctype=NEW[0])
    from erpnext_custom.invoice_types import clear_cache

    clear_cache()
    print(f"Invoice Type dipindah ke {NEW[0]} > {NEW[1]}: {moved} baris")

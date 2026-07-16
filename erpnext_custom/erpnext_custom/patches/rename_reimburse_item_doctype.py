"""Rename child doctype 'Reimburse Item' -> 'Sales Invoice Reimburse'.

Supaya nama tabel DB (tabSales Invoice Reimburse) langsung ketahuan milik Sales
Invoice, bukan 'Reimburse Item' yang ambigu.

WAJIB pre_model_sync: rename_doc memindahkan tabel + datanya SEBELUM model sync
mengimpor JSON nama baru. Kalau dijalankan setelah sync, sync sudah membuat
`tabSales Invoice Reimburse` kosong lebih dulu dan rename akan gagal karena target
sudah ada -- data lama pun tertinggal yatim di tabel lama.

Idempoten: sekali sudah di-rename, doctype lama tak ada lagi -> patch dilewati.
"""

import frappe


def execute():
    if frappe.db.exists("DocType", "Reimburse Item") and not frappe.db.exists(
        "DocType", "Sales Invoice Reimburse"
    ):
        frappe.rename_doc("DocType", "Reimburse Item", "Sales Invoice Reimburse", force=True)
        frappe.clear_cache()

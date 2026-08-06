"""Centang "Pakai Cost Items" di Expense Note Type menggantikan hardcode JOB/NO-JOB.

Dua tipe itu satu-satunya yang selama ini memakai tabel Cost manual, jadi flag-nya
di-set sekali di sini. Setelah itu Expense Note lama di-backfill: field tampilan
type_use_costs (fetch dari tipe) masih kosong di dokumen yang dibuat sebelum field
ini ada, padahal depends_on form membacanya.
"""

import frappe


def execute():
    for t in ("JOB", "NO-JOB"):
        if frappe.db.exists("Expense Note Type", t):
            frappe.db.set_value("Expense Note Type", t, "use_costs", 1, update_modified=False)
    frappe.db.sql(
        """
        UPDATE `tabExpense Note` en
        JOIN `tabExpense Note Type` t ON t.name = en.expense_note_type
        SET en.type_use_costs = t.use_costs
        WHERE en.type_use_costs != t.use_costs
        """
    )

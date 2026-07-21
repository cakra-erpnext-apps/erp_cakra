"""Perilaku ledger yang dipakai bersama override Sales Invoice / Purchase Invoice /
Payment Entry."""

import frappe


def fill_cost_center(doc, gl_dict, item=None):
    """Setiap baris ledger WAJIB punya Cost Center.

    ERPNext hanya mengisinya untuk baris yang punya sumbernya sendiri (baris item), jadi
    baris piutang/hutang, pajak, dan bank keluar tanpa cost center — dan laporan per cost
    center tidak pernah seimbang: pendapatannya terhitung, lawan jurnalnya tidak.

    Urutannya dari yang paling spesifik: baris item -> dokumen -> Default Cost Center
    Company.
    """
    if gl_dict.get("cost_center"):
        return gl_dict
    gl_dict["cost_center"] = (
        (item.get("cost_center") if item else None)
        or doc.get("cost_center")
        or frappe.get_cached_value("Company", doc.company, "cost_center")
    )
    return gl_dict

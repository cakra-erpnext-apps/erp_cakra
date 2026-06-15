"""Setup app `agents` — seed Role divisi + flow default Agent Fleet.

Diekstrak dari erp_cmi. Doctype agent (Agent Administrator/Settings/Event/Mail/
Provider/Flow Step) ada di module Assistant app ini; logika di agents/agent/.
"""

import frappe

# Role divisi untuk handoff antar fase Agent Fleet (expedition -> expense -> invoice -> ar).
FLEET_ROLES = ["Div Expedition", "Div Expense", "Div Invoice", "Div AR"]

# Flow default Agent Fleet (bisa diedit user di Agent Settings -> Flow Steps).
FLEET_FLOWS = [
    {
        "flow_name": "Penjualan",
        "title": "Alur Penjualan (Full)",
        "sequence": 1,
        "description": "Alur utama dari lead sampai terima pembayaran.",
        "steps": [
            "Lead",
            "Inquiry",
            "Quotation",
            "Estimation",
            "Packing List / Shipping List",
            "Expense Note → Payment Voucher",
            "Expense Note → Invoice (Reimburse)",
            "Invoice → Receive Voucher",
        ],
    },
    {
        "flow_name": "Lain-lain",
        "title": "Alur Lain-lain",
        "sequence": 2,
        "description": "Alur pembayaran/penerimaan di luar alur penjualan utama.",
        "steps": [
            "APN → Payment Voucher",
            "Jaminan → Payment Voucher",
            "Jaminan → Receipt Voucher",
        ],
    },
]


def after_install():
    after_migrate()


def after_migrate():
    _seed_fleet_roles()
    _seed_fleet_flows()


def _seed_fleet_roles():
    """Buat Role divisi (idempotent) — dipakai handoff Agent Fleet."""
    for role in FLEET_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({
                "doctype": "Role",
                "role_name": role,
                "desk_access": 1,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def _seed_fleet_flows():
    """Seed flow default ke child table Agent Settings.flows (idempotent).

    Insert baris child LANGSUNG (parent=Agent Settings) — JANGAN re-save Single
    Agent Settings, karena itu bisa menghapus api_key provider (field Password).
    """
    if not frappe.db.exists("DocType", "Agent Flow Step") or not frappe.db.exists("DocType", "Agent Settings"):
        return
    existing = frappe.db.count("Agent Flow Step", {"parenttype": "Agent Settings", "parentfield": "flows"})
    if existing:
        return  # sudah dikonfigurasi — jangan timpa
    idx = 0
    for f in FLEET_FLOWS:
        for step in f["steps"]:
            idx += 1
            frappe.get_doc({
                "doctype": "Agent Flow Step",
                "parent": "Agent Settings",
                "parenttype": "Agent Settings",
                "parentfield": "flows",
                "idx": idx,
                "flow": f["flow_name"],
                "step_name": step,
            }).insert(ignore_permissions=True)
    frappe.db.commit()

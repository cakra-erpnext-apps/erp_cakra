"""Setup app `assistant` — seed Role divisi + flow default Agent Fleet.

Diekstrak dari erp. Doctype agent (Agent Administrator/Settings/Event/Mail/
Provider/Flow Step) ada di module Assistant app ini; logika di assistant/assistant/.
"""

import frappe

# Role divisi untuk handoff antar fase Agent Fleet (expedition -> expense -> invoice -> ar).
# Plus role akses Assistant Center: "Assistant User" (pakai agent / review draft) dan
# "Assistant Administrator" (plus aksi administratif: broadcast, run routine, dsb).
FLEET_ROLES = [
    "Div Expedition", "Div Expense", "Div Invoice", "Div AR",
    "Assistant User", "Assistant Administrator",
]

# Flow default Agent Fleet (bisa diedit user di Assistant Settings -> Flow Steps).
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


# Menu assistant yang di-govern lewat Assistant Settings → tab Allowed Module.
# module_name = nama menu (jadi pilihan kolom Module di tab Skills);
# category = surface agent yang memakainya (Expedition = desk, CRM = /crm).
# Baris "CRM" adalah saklar master menu Assistant di /crm (sinkron FCRM Settings).
ALLOWED_MODULES = [
    # --- Expedition (desk) ---
    {"module_name": "Expedition", "category": "Expedition", "allowed": 1,
     "menu": "Desk: tab Agent + Assistant Center (umum)",
     "notes": "Playbook & skill umum agent expedisi."},
    {"module_name": "Shipping List", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Shipping List"},
    {"module_name": "Packing List", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Packing List"},
    {"module_name": "Expense Note", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Expense Note"},
    {"module_name": "Sales Invoice", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Sales Invoice (AR) / Receive Voucher"},
    {"module_name": "Purchase Order", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Purchase Order"},
    {"module_name": "Purchase Invoice", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Purchase Invoice"},
    {"module_name": "Payment", "category": "Expedition", "allowed": 1,
     "menu": "Desk: Payment Entry / Payment Voucher"},
    # --- CRM (/crm) ---
    {"module_name": "CRM", "category": "CRM", "allowed": 0,
     "menu": "/crm: menu Assistant paling atas sidebar (umum)",
     "notes": "Saklar master menu Assistant CRM."},
    {"module_name": "CRM Dashboard", "category": "CRM", "allowed": 1,
     "menu": "/crm: Dashboard"},
    {"module_name": "CRM Lead", "category": "CRM", "allowed": 1,
     "menu": "/crm: Leads"},
    {"module_name": "CRM Inquiry", "category": "CRM", "allowed": 1,
     "menu": "/crm: Inquiries"},
    {"module_name": "CRM Quotation", "category": "CRM", "allowed": 1,
     "menu": "/crm: Quotations"},
    {"module_name": "CRM Estimation", "category": "CRM", "allowed": 1,
     "menu": "/crm: Estimations"},
    {"module_name": "CRM Contact", "category": "CRM", "allowed": 1,
     "menu": "/crm: Contacts"},
    {"module_name": "CRM Account", "category": "CRM", "allowed": 1,
     "menu": "/crm: Accounts (Organizations)"},
    {"module_name": "CRM Note", "category": "CRM", "allowed": 1,
     "menu": "/crm: Notes"},
    {"module_name": "CRM Task", "category": "CRM", "allowed": 1,
     "menu": "/crm: Tasks"},
    {"module_name": "CRM Call Log", "category": "CRM", "allowed": 1,
     "menu": "/crm: Call Logs"},
]

# Skill bawaan (file di assistant/assistant/skill) + menu kategorinya.
DEFAULT_SKILLS = [
    {"skill_label": "Playbook Expedisi", "module": "Expedition", "file": "expedition.skill",
     "description": "Aturan kerja utama agent expedisi (email customer, lampiran, dsb)."},
    {"skill_label": "Baca Dokumen Shipping", "module": "Expedition", "file": "document_extraction.skill",
     "description": "Membaca PDF/scan (B/L, SWB, manifest) → field Packing List."},
    {"skill_label": "Baca Input Chat", "module": "Expedition", "file": "chat_extraction.skill",
     "description": "Ekstraksi data dari teks chat user."},
    {"skill_label": "B/L → Shipping List", "module": "Shipping List", "file": "bl_to_shipping_list.skill",
     "description": "Konversi Bill of Lading / SWB menjadi Shipping List 3 level."},
    {"skill_label": "Invoice Vendor → Expense Note", "module": "Expense Note", "file": "vendor_invoice_to_expense_note.skill",
     "description": "Membaca pra nota/invoice vendor (profil per vendor, gotcha PPN DPP Nilai Lain)."},
]


def after_install():
    after_migrate()


def after_migrate():
    _seed_fleet_roles()
    _seed_fleet_flows()
    _seed_allowed_modules()
    _seed_skills()


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
    """Seed flow default ke child table Assistant Settings.flows (idempotent).

    Insert baris child LANGSUNG (parent=Assistant Settings) — JANGAN re-save Single
    Assistant Settings, karena itu bisa menghapus api_key provider (field Password).
    """
    if not frappe.db.exists("DocType", "Agent Flow Step") or not frappe.db.exists("DocType", "Assistant Settings"):
        return
    existing = frappe.db.count("Agent Flow Step", {"parenttype": "Assistant Settings", "parentfield": "flows"})
    if existing:
        return  # sudah dikonfigurasi — jangan timpa
    idx = 0
    for f in FLEET_FLOWS:
        for step in f["steps"]:
            idx += 1
            frappe.get_doc({
                "doctype": "Agent Flow Step",
                "parent": "Assistant Settings",
                "parenttype": "Assistant Settings",
                "parentfield": "flows",
                "idx": idx,
                "flow": f["flow_name"],
                "step_name": step,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def _seed_child_rows(child_doctype, parentfield, rows):
    """Seed child table Assistant Settings.<parentfield> (idempotent, tanpa re-save
    parent Single — menjaga api_key Password provider tetap utuh)."""
    if not frappe.db.exists("DocType", child_doctype):
        return
    if frappe.db.count(child_doctype, {"parenttype": "Assistant Settings", "parentfield": parentfield}):
        return  # sudah dikonfigurasi — jangan timpa
    for i, row in enumerate(rows, start=1):
        frappe.get_doc({
            "doctype": child_doctype,
            "parent": "Assistant Settings",
            "parenttype": "Assistant Settings",
            "parentfield": parentfield,
            "idx": i,
            **row,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def _seed_allowed_modules():
    """Tab Allowed Module: modul assistant + saklar menunya. Baris CRM mengikuti
    nilai FCRM Settings yang sedang berlaku (kalau app crm terpasang)."""
    rows = [dict(r) for r in ALLOWED_MODULES]
    try:
        if frappe.db.exists("DocType", "FCRM Settings"):
            cur = frappe.db.get_single_value("FCRM Settings", "enable_crm_assistant")
            for r in rows:
                if r["module_name"] == "CRM":
                    r["allowed"] = 1 if cur else 0
    except Exception:
        pass
    _seed_child_rows("Assistant Allowed Module", "allowed_modules", rows)


def _seed_skills():
    """Tab Skills: daftar skill bawaan + kategori modulnya."""
    _seed_child_rows("Assistant Skill", "skills", DEFAULT_SKILLS)

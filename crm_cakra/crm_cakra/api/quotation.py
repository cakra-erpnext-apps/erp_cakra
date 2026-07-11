import frappe
from frappe import _

from crm_cakra.api.permissions import _can_see_all


INQUIRY_LIMIT = 50
# Slot yang disisakan untuk inquiry milik user lain, supaya mereka tetap terlihat
# walau user punya banyak inquiry sendiri.
INQUIRY_RESERVED_FOR_OTHERS = 10


@frappe.whitelist()
def get_available_inquiries(search=None):
    """Inquiry yang belum dipakai Quotation, milik user sendiri didahulukan.

    Picker ini SENGAJA lebih ketat daripada aturan lihat. Rekan sesama branch boleh
    saling melihat inquiry, tapi untuk memilihnya jadi quotation inquiry itu harus
    di-assign ke user. Jadi di sini branch tidak dipakai, hanya owner dan _assign.

    Dua query terpisah (milik saya, lalu milik orang lain) supaya inquiry milik user
    pasti muncul walau `modified`-nya kalah baru. Satu query + sort di Python tidak
    cukup: limit terlanjur memotong sebelum urutan diperbaiki.
    """
    used_inquiries = frappe.get_all(
        "CRM Quotation",
        fields=["inquiry"],
        filters={"inquiry": ["is", "set"]},
        pluck="inquiry",
    )
    base_filters = {"status": ["!=", "Lost"]}
    if used_inquiries:
        base_filters["name"] = ["not in", used_inquiries]
    if search:
        base_filters["organization"] = ["like", f"%{search}%"]

    def fetch(extra_filters, limit):
        if limit <= 0:
            return []
        # get_list, bukan get_all: get_all mengabaikan permission sehingga Sales User
        # tetap melihat inquiry milik user lain di picker walau list view sudah difilter.
        return frappe.get_list(
            "CRM Inquiry",
            fields=["name", "organization", "inquiry_owner"],
            filters={**base_filters, **extra_filters},
            order_by="modified desc",
            limit_page_length=limit,
        )

    me = frappe.session.user
    mine = fetch({"owner": me}, INQUIRY_LIMIT)

    others_filters = {"owner": ["!=", me]}
    if not _can_see_all(me):
        # milik rekan hanya boleh dipilih kalau di-assign ke saya.
        # Kutip ikut dicocokkan: _assign berisi JSON '["a@x.com"]'.
        others_filters["_assign"] = ["like", f'%"{me}"%']
    others = fetch(others_filters, INQUIRY_LIMIT)

    if not others:
        return mine[:INQUIRY_LIMIT]

    keep_mine = min(
        len(mine),
        INQUIRY_LIMIT - min(len(others), INQUIRY_RESERVED_FOR_OTHERS),
    )
    return mine[:keep_mine] + others[: INQUIRY_LIMIT - keep_mine]


@frappe.whitelist()
def mark_quotation_lost(quotation, lost_reason=None, lost_notes=None):
    """Tandai quotation sebagai Lose, sekalian isi Lost Reason di inquiry-nya.

    Digabung dalam satu panggilan supaya tidak ada keadaan setengah jadi: kalau
    alasan tersimpan tapi status gagal berubah (atau sebaliknya), CRM Inquiry akan
    menolak penyimpanan berikutnya lewat validate_lost_reason().
    """
    if not frappe.has_permission("CRM Quotation", "write", quotation):
        frappe.throw(_("Not allowed to update this Quotation"), frappe.PermissionError)

    quo = frappe.get_doc("CRM Quotation", quotation)

    if quo.inquiry:
        # Aturan ini milik CRM Inquiry.validate_lost_reason(); dicek di sini juga
        # supaya pesannya jelas sebelum apa pun tersentuh.
        if not lost_reason:
            frappe.throw(_("Lost Reason wajib diisi."))
        if lost_reason == "Other" and not (lost_notes or "").strip():
            frappe.throw(_("Lost Notes wajib diisi bila Lost Reason adalah 'Other'."))

        inquiry = frappe.get_doc("CRM Inquiry", quo.inquiry)
        inquiry.lost_reason = lost_reason
        inquiry.lost_notes = lost_notes
        # inquiry lama (hasil import) belum punya field wajib yang ditambahkan
        # belakangan; kita cuma menyentuh alasan kalah.
        inquiry.flags.ignore_mandatory = True
        inquiry.save(ignore_permissions=True)

    # sync_inquiry_status() di on_update yang mendorong inquiry -> Lost.
    quo.state = "Lose"
    quo.save()
    return quo.state


# Baris yang ditampilkan di sidebar Quotation. Urutan & label ditentukan di sini
# supaya form.js cukup me-render apa adanya.
INQUIRY_SIDEBAR_FIELDS = [
    ("inquiry_date", "Inquiry Date"),
    ("status", "Status"),
    ("type_inquiry", "Type of Inquiry"),
    ("shipper_consignee", "Shipper/Consignee"),
    ("transportation_mode", "Transportation Mode"),
    ("date_shipment", "Date of Shipment"),
    ("origin", "Origin"),
    ("destination", "Destination"),
    ("job_service", "Job Service"),
    ("business_unit", "Business Unit"),
]


@frappe.whitelist()
def get_inquiry_detail(name):
    """Detail CRM Inquiry untuk sidebar Quotation (read-only, dibaca langsung dari
    Inquiry sehingga selalu sinkron -- tidak disalin ke Quotation).

    Dikembalikan sebagai daftar {label, value} agar urutan baris dikendalikan server.
    """
    if not name or not frappe.db.exists("CRM Inquiry", name):
        return {}

    # Jangan bocorkan isi inquiry yang tidak boleh dilihat user ini. Quotation dan
    # inquiry-nya biasanya sebranch, jadi normalnya lolos.
    if not frappe.has_permission("CRM Inquiry", "read", doc=name):
        return {}

    inquiry = frappe.get_doc("CRM Inquiry", name)

    def value_of(fieldname):
        if fieldname == "type_inquiry":
            # Table MultiSelect -> gabungkan label baris anaknya.
            return ", ".join(r.type for r in (inquiry.type_inquiry or []) if r.type)
        value = inquiry.get(fieldname)
        if fieldname in ("inquiry_date", "date_shipment") and value:
            return frappe.utils.formatdate(value, "dd MMM yyyy")
        return value

    return {
        "name": inquiry.name,
        "rows": [
            {"label": label, "value": value_of(fieldname) or ""}
            for fieldname, label in INQUIRY_SIDEBAR_FIELDS
        ],
    }


@frappe.whitelist()
def get_quotation_contacts(name):
    """Get contacts linked to quotation's account (organization)"""
    quotation = frappe.get_doc("CRM Quotation", name)
    if not quotation.account:
        return []
    
    contacts = frappe.get_all(
        "Contact",
        filters={"company_name": quotation.account},
        fields=["name", "first_name", "last_name", "image"],
    )
    
    result = []
    for c in contacts:
        contact_doc = frappe.get_doc("Contact", c.name)
        primary_email = next(
            (e.email_id for e in contact_doc.email_ids if e.is_primary), None
        )
        primary_phone = next(
            (p.phone for p in contact_doc.phone_nos if p.is_primary_mobile_no),
            None,
        )
        full_name = f"{c.first_name or ''} {c.last_name or ''}".strip()
        result.append({
            "name": c.name,
            "full_name": full_name or c.name,
            "image": c.image,
            "email": primary_email,
            "mobile_no": primary_phone,
        })
    return result
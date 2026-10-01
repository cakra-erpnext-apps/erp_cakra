import frappe
from frappe import _

from crm_cakra.api.permissions import SEE_ALL, _access_level


def _can_see_all(user=None):
    """User boleh melihat data siapa pun (level See All di CMI Branch Access)."""
    return _access_level(user or frappe.session.user) >= SEE_ALL


INQUIRY_LIMIT = 50
# Slot yang disisakan untuk inquiry milik user lain, supaya mereka tetap terlihat
# walau user punya banyak inquiry sendiri.
INQUIRY_RESERVED_FOR_OTHERS = 10


@frappe.whitelist()
def get_available_inquiries(search=None):
    """Inquiry yang bisa dipilih untuk Quotation, milik user sendiri didahulukan.

    Satu inquiry boleh dipakai banyak quotation, jadi yang sudah pernah dipakai
    TIDAK disembunyikan dari picker.

    Picker ini SENGAJA lebih ketat daripada aturan lihat. Rekan sesama branch boleh
    saling melihat inquiry, tapi untuk memilihnya jadi quotation inquiry itu harus
    di-assign ke user. Jadi di sini branch tidak dipakai, hanya owner dan _assign.

    Dua query terpisah (milik saya, lalu milik orang lain) supaya inquiry milik user
    pasti muncul walau `modified`-nya kalah baru. Satu query + sort di Python tidak
    cukup: limit terlanjur memotong sebelum urutan diperbaiki.
    """
    base_filters = {"status": ["!=", "Lost"]}
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
def mark_quotation_lost(quotation, lost_notes=None):
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
        if not (lost_notes or "").strip():
            frappe.throw(_("Lost Notes wajib diisi."))

        inquiry = frappe.get_doc("CRM Inquiry", quo.inquiry)
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


PRINT_FORMAT = "Quotation Print Out"


@frappe.whitelist()
def check_printable(quotation: str):
	"""Jalankan penjaga cetak tanpa merender apa-apa, lalu naikkan statusnya.

	Yang mengikat tetap before_print di CRM Quotation (margin minus wajib
	beralasan). Dipanggil lebih dulu dari tombol Print supaya penolakannya tampil
	sebagai dialog di dalam app, bukan sebagai halaman printview yang error di tab
	baru -- sekalian menaikkan status ke Negotiation, karena tombol inilah yang
	berarti "penawaran dikirim ke customer".
	"""
	doc = frappe.get_doc("CRM Quotation", quotation)
	doc.check_permission("read")
	doc.before_print()
	doc.promote_to_negotiation()
	# Status barunya dikembalikan supaya app bisa langsung menampilkannya tanpa
	# memuat ulang dokumen -- dan tanpa menyalin aturan PRINT_PROMOTES_FROM ke sisi
	# layar, yang pasti melenceng begitu aturannya diubah di sini.
	return {"state": doc.state}


@frappe.whitelist()
def send_quotation_email(
	quotation: str,
	recipients: str,
	subject: str,
	content: str,
	cc: str | None = None,
	bcc: str | None = None,
	sender: str | None = None,
):
	"""Kirim quotation ke customer dengan PDF print-out-nya terlampir.

	PDF dibuat di server dari Print Format yang sama dengan tombol Print, jadi yang
	diterima customer persis dokumen yang dipratinjau di modal -- bukan hasil render
	kedua yang bisa berbeda diam-diam.

	Lampirannya disimpan sebagai File milik quotation ini (muncul di tab
	Attachments) supaya ada jejak dokumen mana yang dikirim, dan emailnya dibuat
	lewat Communication bawaan Frappe supaya ikut tampil di tab Activity dan masuk
	antrean kirim seperti email CRM lainnya.
	"""
	if not frappe.has_permission("CRM Quotation", "write", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not (recipients or "").strip():
		frappe.throw(_("Penerima email wajib diisi."))

	doc = frappe.get_doc("CRM Quotation", quotation)

	# attach_print menjalankan before_print, jadi penjaga margin minus berlaku di
	# sini juga -- tidak ada jalan pintas lewat email.
	printed = frappe.attach_print(
		"CRM Quotation", quotation, print_format=PRINT_FORMAT, doc=doc
	)
	pdf = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": printed["fname"],
			"content": printed["fcontent"],
			"attached_to_doctype": "CRM Quotation",
			"attached_to_name": quotation,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)

	from frappe.core.doctype.communication.email import make

	make(
		doctype="CRM Quotation",
		name=quotation,
		subject=subject,
		content=content,
		recipients=recipients,
		cc=cc,
		bcc=bcc,
		sender=sender or frappe.session.user,
		sender_full_name=frappe.utils.get_fullname(frappe.session.user),
		attachments=[pdf.name],
		send_email=True,
	)

	# Dikirim = penawaran sudah sampai ke customer, sama artinya dengan dicetak.
	doc.promote_to_negotiation()

	return {"attachment": pdf.file_name, "state": doc.state}


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
import os

import frappe
from frappe.model.document import Document
from frappe.utils import escape_html

# Jabatan untuk signature perusahaan: User bawaan tidak punya field-nya, dan Employee di sini
# tidak ditautkan ke User. Dipasang install.after_migrate.
SIGNATURE_FIELDS = {
	"User": [
		{
			"fieldname": "cmi_job_title",
			"label": "Job Title",
			"fieldtype": "Data",
			"insert_after": "last_name",
			"description": "Jabatan, tampil di signature email perusahaan (Mailbox).",
		}
	],
	# Telepon branch untuk baris "P:" signature; alamatnya sudah ada di Branch.address.
	"Branch": [
		{
			"fieldname": "cmi_phone",
			"label": "Phone",
			"fieldtype": "Data",
			"options": "Phone",
			"insert_after": "address",
			"description": "Tampil di signature email perusahaan (Mailbox).",
		}
	],
}

# Template bawaan signature perusahaan (Jinja). Disalin ke ERPNext Custom Setting > Mailbox
# sekali saat kosong; sesudah itu admin mengeditnya di sana.
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(__file__), "company_signature.html")


class MailboxSignature(Document):
	"""Signature email satu user (pemiliknya). Gambar di dalamnya diubah Frappe jadi berkas saat
	disimpan; halaman Mailbox mengirimnya sebagai gambar inline (cid:) lewat Microsoft."""

	def on_update(self):
		# Seperti Outlook: satu bawaan untuk email baru dan satu untuk balasan per user.
		for field in ("use_for_new", "use_for_reply"):
			if self.get(field):
				frappe.db.sql(
					f"update `tabMailbox Signature` set `{field}` = 0 where owner = %s and name != %s",
					(self.owner, self.name),
				)


@frappe.whitelist()
def company_signature() -> str:
	"""Signature perusahaan untuk user yang login: template di ERPNext Custom Setting > Mailbox
	diisi data User-nya (nama, jabatan, email, kantor cabang, telepon). Kosong = tidak dipakai."""
	settings = frappe.get_cached_doc("ERPNext Custom Setting")
	template = (settings.get("mailbox_signature_template") or "").strip()
	if not template:
		return ""
	return frappe.render_template(template, signature_context(frappe.session.user))


@frappe.whitelist()
def signature_preview() -> dict:
	"""Isi placeholder untuk user yang login: pratinjau di pembuat signature (ERPNext Custom
	Setting > Mailbox, public/js/signature_builder.js). Cuma data milik user itu sendiri."""
	return signature_context(frappe.session.user)


def signature_context(user: str) -> dict:
	"""Isi placeholder template. Semua nilai sudah di-escape: sebagian bisa diubah user sendiri
	(nama, nomor HP), sedangkan template dirender tanpa autoescape."""
	u = frappe.db.get_value(
		"User",
		user,
		["first_name", "last_name", "email", "mobile_no", "phone", "branch", "cmi_job_title"],
		as_dict=True,
	)
	office = (
		frappe.db.get_value("CMI Office", u.branch, ["office_name", "city", "address", "phone"], as_dict=True)
		if u.branch
		else None
	) or frappe._dict()
	# Alamat & telepon dari master Branch yang bernama sama dengan kantor user (nama CMI Office =
	# nama Branch: Jakarta/Medan/Surabaya); Branch tidak ada atau isiannya kosong -> CMI Office.
	branch = (
		frappe.db.get_value("Branch", u.branch, ["address", "cmi_phone"], as_dict=True) if u.branch else None
	) or frappe._dict()
	company = frappe.defaults.get_user_default("Company", user) or frappe.defaults.get_global_default("company")
	info = (
		frappe.db.get_value("Company", company, ["company_name", "website"], as_dict=True) if company else None
	) or frappe._dict()
	settings = frappe.get_cached_doc("ERPNext Custom Setting")
	website = (info.website or "").strip()

	e = lambda value: escape_html(value or "")  # noqa: E731
	return {
		"full_name": e(" ".join(filter(None, [u.first_name, u.last_name]))),
		"job_title": e(u.cmi_job_title),
		"email": e(u.email),
		"company": e(settings.get("mailbox_signature_company") or info.company_name),
		"branch_office": e(office.office_name),
		"office_city": e(office.city),
		# Alamat branch = beberapa baris (Small Text); tiap baris satu baris di signature.
		"office_address_lines": [e(line.strip().rstrip(",")) for line in (branch.address or office.address or "").splitlines() if line.strip()],
		"office_phone": e(branch.cmi_phone or office.phone),
		"mobile_no": e(u.mobile_no or u.phone),
		"website": e(website),
		"website_url": e(website if website.startswith("http") else f"http://{website}") if website else "",
	}


def ensure_signature_template():
	"""after_migrate: isi template bawaan kalau admin belum pernah mengisinya."""
	if (frappe.db.get_single_value("ERPNext Custom Setting", "mailbox_signature_template") or "").strip():
		return
	with open(DEFAULT_TEMPLATE, encoding="utf-8") as f:
		frappe.db.set_single_value("ERPNext Custom Setting", "mailbox_signature_template", f.read())

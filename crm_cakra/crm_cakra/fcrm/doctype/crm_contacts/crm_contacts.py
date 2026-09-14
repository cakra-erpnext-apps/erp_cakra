# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CRMContacts(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		contact: DF.Link | None
		email: DF.Data | None
		full_name: DF.Data | None
		gender: DF.Link | None
		is_primary: DF.Check
		mobile_no: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		phone: DF.Data | None
	# end: auto-generated types

	pass


# Kontak yang menempel di dokumen lain (§2 dan §4 Alur CRM). Lead dan Inquiry memakai
# child table yang sama, jadi aturannya ditulis sekali di sini dan dipanggil dua-duanya.
# Daftarnya dikunci: `doctype` datang dari browser, dan tanpa gerbang ini fungsi di bawah
# jadi alat menulis child row ke doctype mana pun yang kebetulan punya field `contacts`.
PARENT_DOCTYPES = ("CRM Lead", "CRM Inquiry")


def _parent(doctype: str, name: str, action: str):
	if doctype not in PARENT_DOCTYPES:
		frappe.throw(_("Contacts are not supported on {0}").format(doctype))
	if not frappe.has_permission(doctype, "write", name):
		frappe.throw(
			_("Not allowed to {0} contact on {1}").format(action, doctype), frappe.PermissionError
		)
	return frappe.get_doc(doctype, name)


@frappe.whitelist()
def get_linked_contacts(doctype: str, name: str) -> list[dict]:
	"""Kontak satu dokumen, lengkap dengan detail dari master Contact.

	Baris tanpa `contact` dilewati: ia sisa baris kosong, bukan kontak.
	"""
	if doctype not in PARENT_DOCTYPES:
		frappe.throw(_("Contacts are not supported on {0}").format(doctype))
	if not frappe.has_permission(doctype, "read", name):
		frappe.throw(_("Not allowed to read {0}").format(doctype), frappe.PermissionError)

	rows = frappe.get_all(
		"CRM Contacts",
		filters={"parenttype": doctype, "parent": name},
		fields=["contact", "is_primary", "role"],
		distinct=True,
	)

	contacts = []
	for row in rows:
		if not row.contact or not frappe.db.exists("Contact", row.contact):
			continue

		contact = frappe.get_doc("Contact", row.contact).as_dict()
		contacts.append(
			{
				"name": contact.name,
				"image": contact.image,
				"full_name": contact.full_name,
				"email": contact.email_id,
				"mobile_no": contact.mobile_no,
				"is_primary": row.is_primary,
				"role": row.role,
			}
		)
	return contacts


@frappe.whitelist()
def add_contact(doctype: str, name: str, contact: str) -> bool:
	doc = _parent(doctype, name, _("add"))
	if any(d.contact == contact for d in doc.contacts):
		return True

	doc.append("contacts", {"contact": contact, "is_primary": 0 if doc.contacts else 1})
	doc.save()
	return True


@frappe.whitelist()
def remove_contact(doctype: str, name: str, contact: str) -> bool:
	doc = _parent(doctype, name, _("remove"))
	doc.contacts = [d for d in doc.contacts if d.contact != contact]
	doc.save()
	return True


@frappe.whitelist()
def set_primary_contact(doctype: str, name: str, contact: str) -> bool:
	doc = _parent(doctype, name, _("set primary"))
	for d in doc.contacts:
		d.is_primary = 1 if d.contact == contact else 0
	doc.save()
	return True


@frappe.whitelist()
def set_contact_role(doctype: str, name: str, contact: str, role: str = "") -> bool:
	"""Peran kontak ditulis langsung ke barisnya, bukan lewat save() induk.

	Menyetel peran tidak boleh ikut menjalankan validate dokumen induk: banyak Lead dan
	Inquiry warisan impor yang field wajibnya kosong dan akan menolak simpan, padahal
	yang diubah cuma label peran.
	"""
	_parent(doctype, name, _("set role on"))

	# Nilainya datang dari browser -- cocokkan ke opsi Select di doctype, jangan percaya.
	allowed = (frappe.get_meta("CRM Contacts").get_field("role").options or "").splitlines()
	if role not in allowed:
		frappe.throw(_("Invalid contact role: {0}").format(role))

	row = frappe.db.exists(
		"CRM Contacts", {"parenttype": doctype, "parent": name, "contact": contact}
	)
	if not row:
		frappe.throw(_("Contact is not linked to this {0}").format(doctype))

	frappe.db.set_value("CRM Contacts", row, "role", role)
	return True

import frappe


@frappe.whitelist()
def get_inquiry_contacts(name: str):
	contacts = frappe.get_all(
		"CRM Contacts",
		filters={"parenttype": "CRM Inquiry", "parent": name},
		fields=["contact", "is_primary", "role"],
		distinct=True,
	)
	inquiry_contacts = []
	for contact in contacts:
		if not contact.contact:
			continue

		is_primary = contact.is_primary
		role = contact.role
		contact = frappe.get_doc("Contact", contact.contact).as_dict()

		_contact = {
			"name": contact.name,
			"image": contact.image,
			"full_name": contact.full_name,
			"email": contact.email_id,
			"mobile_no": contact.mobile_no,
			"is_primary": is_primary,
			"role": role,
		}
		inquiry_contacts.append(_contact)
	return inquiry_contacts

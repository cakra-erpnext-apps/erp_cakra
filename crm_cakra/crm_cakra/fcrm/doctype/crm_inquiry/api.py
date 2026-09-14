import frappe

from crm_cakra.fcrm.doctype.crm_contacts.crm_contacts import get_linked_contacts


@frappe.whitelist()
def get_inquiry_contacts(name: str):
	return get_linked_contacts("CRM Inquiry", name)

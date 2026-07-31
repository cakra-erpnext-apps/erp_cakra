import frappe


@frappe.whitelist()
def make_sales_invoice_from_delivery_note(source_name, target_doc=None, args=None):
	"""Map DN items while preserving the CMI invoice classification header."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	if isinstance(target_doc, str):
		target_doc = frappe.get_doc(frappe.parse_json(target_doc))

	preserved = {}
	if target_doc:
		for fieldname in (
			"custom_invoice_type",
			"custom_invoice_type_no",
			"custom_invoice_behavior",
		):
			preserved[fieldname] = target_doc.get(fieldname)

	mapped = make_sales_invoice(source_name, target_doc=target_doc, args=args)
	defaults = {
		"custom_invoice_type": "Trading",
		"custom_invoice_type_no": "C/T",
		"custom_invoice_behavior": "Normal",
	}
	for fieldname, default in defaults.items():
		mapped.set(fieldname, preserved.get(fieldname) or default)
	return mapped

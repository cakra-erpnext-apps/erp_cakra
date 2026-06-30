import frappe


def execute():
	inquiry_statuses = frappe.get_all("CRM Inquiry Status", fields=["name", "probability", "inquiry_status"])

	for status in inquiry_statuses:
		if status.probability is None or status.probability == 0:
			if status.inquiry_status == "Qualification":
				probability = 10
			elif status.inquiry_status == "Demo/Making":
				probability = 25
			elif status.inquiry_status == "Proposal/Quotation":
				probability = 50
			elif status.inquiry_status == "Negotiation":
				probability = 70
			elif status.inquiry_status == "Ready to Close":
				probability = 90
			elif status.inquiry_status == "Won":
				probability = 100
			else:
				probability = 0

			frappe.db.set_value("CRM Inquiry Status", status.name, "probability", probability)

import frappe


def execute():
	inquiry_statuses = frappe.get_all("CRM Inquiry Status", fields=["name", "type", "inquiry_status"])

	openStatuses = ["New", "Open", "Unassigned", "Qualification"]
	ongoingStatuses = [
		"Demo/Making",
		"Proposal/Quotation",
		"Negotiation",
		"Ready to Close",
		"Demo Scheduled",
		"Follow Up",
	]
	onHoldStatuses = ["On Hold", "Paused", "Stalled", "Awaiting Reply"]
	wonStatuses = ["Won", "Closed Won", "Successful", "Completed"]
	lostStatuses = [
		"Lost",
		"Closed",
		"Closed Lost",
		"Junk",
		"Unqualified",
		"Disqualified",
		"Cancelled",
		"No Response",
	]

	for status in inquiry_statuses:
		if not status.type or status.type is None or status.type == "Open":
			if status.inquiry_status in openStatuses:
				type = "Open"
			elif status.inquiry_status in ongoingStatuses:
				type = "Ongoing"
			elif status.inquiry_status in onHoldStatuses:
				type = "On Hold"
			elif status.inquiry_status in wonStatuses:
				type = "Won"
			elif status.inquiry_status in lostStatuses:
				type = "Lost"
			else:
				type = "Ongoing"

			frappe.db.set_value("CRM Inquiry Status", status.name, "type", type)

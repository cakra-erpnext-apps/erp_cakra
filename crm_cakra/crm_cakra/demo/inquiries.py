from datetime import datetime, timedelta

import frappe
from frappe.query_builder import DocType

from crm_cakra.demo.utils import (
	backdate,
	build_full_names,
	fix_auto_records,
	insert_comment,
	insert_communication,
	insert_version,
	resolve_owners,
)


def create_demo_inquiries(lead_names, demo_users):
	"""Convert seven leads into inquiries and add inquiry-specific activity."""
	from crm_cakra.fcrm.doctype.crm_lead.crm_lead import convert_to_inquiry

	session_user, owner_1, owner_2, _ = resolve_owners(demo_users)
	_full_names = build_full_names(session_user)

	# leads[0] Alice, [3] David, [7] Henry, [8] Iris, [9] Jack → 5 active/won inquiries
	# leads[10] Karen, [11] Leo → 2 lost inquiries
	d_alice = convert_to_inquiry(
		lead=lead_names[0],
		inquiry={"status": "Demo/Making", "inquiry_value": 120000, "probability": 50, "inquiry_owner": session_user},
	)
	d_david = convert_to_inquiry(
		lead=lead_names[3],
		inquiry={"status": "Proposal/Quotation", "inquiry_value": 45000, "probability": 70, "inquiry_owner": owner_1},
	)
	d_henry = convert_to_inquiry(
		lead=lead_names[7],
		inquiry={"status": "Negotiation", "inquiry_value": 85000, "probability": 60, "inquiry_owner": owner_2},
	)
	d_iris = convert_to_inquiry(
		lead=lead_names[8],
		inquiry={"status": "Qualification", "inquiry_value": 60000, "probability": 35, "inquiry_owner": session_user},
	)
	d_jack = convert_to_inquiry(
		lead=lead_names[9],
		inquiry={"status": "Won", "inquiry_value": 175000, "probability": 100, "inquiry_owner": owner_1},
	)
	d_karen = convert_to_inquiry(
		lead=lead_names[10],
		inquiry={
			"status": "Lost",
			"inquiry_value": 95000,
			"probability": 0,
			"inquiry_owner": owner_2,
			"lost_reason": "Competition",
			"lost_notes": "Prospect chose a competitor offering deeper BI integrations out of the box. Price was not the issue — feature parity was.",
		},
	)
	d_leo = convert_to_inquiry(
		lead=lead_names[11],
		inquiry={
			"status": "Lost",
			"inquiry_value": 55000,
			"probability": 0,
			"inquiry_owner": session_user,
			"lost_reason": "Budget constraints",
			"lost_notes": "Q2 budget was cut. Leo said they would revisit in Q4 once headcount hiring is complete. Added to nurture sequence.",
		},
	)

	inquiry_names_list = [d_alice, d_david, d_henry, d_iris, d_jack, d_karen, d_leo]
	# Converted lead indices — must match inquiry_names_list order
	_converted_lead_indices = [0, 3, 7, 8, 9, 10, 11]
	# Days ago each inquiry was created (always after its lead)
	_inquiry_days = [50, 37, 18, 11, 24, 9, 5]
	_inquiry_owners = [session_user, owner_1, owner_2, session_user, owner_1, owner_2, session_user]
	# Organization logos keyed by org name (index order: alice, david, henry, iris, jack, karen, leo)
	_org_logos = {
		"Acme Corp": "/assets/crm_cakra/images/demo/acme-corp.png",
		"TechStart Inc": "/assets/crm_cakra/images/demo/techstart-inc.png",
		"PivotTech Solutions": "/assets/crm_cakra/images/demo/pivottech-solutions.png",
		"ScaleUp Labs": "/assets/crm_cakra/images/demo/scaleup-labs.png",
		"Meridian Systems": "/assets/crm_cakra/images/demo/meridian-systems.png",
		"Vertex Analytics": "/assets/crm_cakra/images/demo/vertex-analytics.png",
		"Forge Digital": "/assets/crm_cakra/images/demo/forge-digital.png",
	}
	now = datetime.now()

	for d_name, days, d_owner, li in zip(
		inquiry_names_list, _inquiry_days, _inquiry_owners, _converted_lead_indices, strict=False
	):
		ts = now - timedelta(days=days)
		backdate("CRM Inquiry", d_name, d_owner, ts)
		org = frappe.db.get_value("CRM Inquiry", d_name, "organization")
		if org:
			logo = _org_logos.get(org)
			if logo:
				frappe.db.set_value("CRM Organization", org, "organization_logo", logo, update_modified=False)
			backdate("CRM Organization", org, d_owner, ts)
		contacts = frappe.get_all(
			"CRM Contacts", filters={"parent": d_name, "parenttype": "CRM Inquiry"}, pluck="contact"
		)
		for contact in contacts:
			if contact:
				backdate("Contact", contact, d_owner, ts)
		backdate("CRM Lead", lead_names[li], d_owner, ts, set_creation=False)
		fix_auto_records("CRM Inquiry", d_name, d_owner, ts)
		fix_auto_records("CRM Lead", lead_names[li], d_owner, ts)

	comment_names = _create_inquiry_comments(inquiry_names_list, session_user, owner_1, owner_2, _full_names, now)
	communication_names = _create_inquiry_communications(
		inquiry_names_list, session_user, owner_1, _full_names, now
	)
	_create_inquiry_versions(inquiry_names_list, session_user, owner_1, owner_2, now)

	# Re-backdate modified to last-activity date so active inquiries sort to the top of the list.
	# Index order: alice, david, henry, iris, jack, karen, leo
	_inquiry_last_touched_days = [2, 4, 7, 10, 6, 8, 12]
	for d_name, days, d_owner in zip(inquiry_names_list, _inquiry_last_touched_days, _inquiry_owners, strict=False):
		backdate("CRM Inquiry", d_name, d_owner, now - timedelta(days=days), set_creation=False)

	return {
		"inquiries": inquiry_names_list,
		"comments": comment_names,
		"communications": communication_names,
	}


def _create_inquiry_comments(inquiry_names, session_user, owner_1, owner_2, full_names, now):
	comments_data = [
		{
			"inquiry": inquiry_names[0],  # Alice / Acme Corp
			"owner": session_user,
			"content": (
				"<p>Live demo went well — Alice's product team joined and had great questions "
				"about workflow automation and bulk import. They want a custom sandbox environment "
				"to evaluate with their own data before signing. Following up to arrange access.</p>"
			),
			"days_ago": 3,
		},
		{
			"inquiry": inquiry_names[1],  # David / TechStart Inc
			"owner": owner_1,
			"content": (
				"<p>David reviewed the proposal with his co-founder. They're happy with the pricing "
				"but want a 3-month pilot before committing to annual. Checking with management on "
				"whether we can offer a pilot discount.</p>"
			),
			"days_ago": 5,
		},
		{
			"inquiry": inquiry_names[2],  # Henry / PivotTech Solutions
			"owner": owner_2,
			"content": (
				"<p>Negotiation call with Henry went long but productive. He’s pushing for a 15% "
				"discount on the annual plan citing budget constraints. Legal team is now reviewing "
				"the contract — decision expected by end of week.</p>"
			),
			"days_ago": 7,
		},
		{
			"inquiry": inquiry_names[3],  # Iris / ScaleUp Labs
			"owner": session_user,
			"content": (
				"<p>Qualification call completed with Iris and her co-founder. Small but fast-moving "
				"team of 8 engineers. Main concerns are API depth and self-serve onboarding. "
				"Sending over the developer docs and scheduling a technical deep-dive.</p>"
			),
			"days_ago": 10,
		},
		{
			"inquiry": inquiry_names[4],  # Jack / Meridian Systems
			"owner": owner_1,
			"content": (
				"<p>Inquiry closed — Jack signed the contract this morning. Final value $175k annual. "
				"Onboarding is scheduled for next Monday. Handoff notes sent to the customer "
				"success team. Great result for the quarter!</p>"
			),
			"days_ago": 2,
		},
		{
			"inquiry": inquiry_names[5],  # Karen / Vertex Analytics
			"owner": owner_2,
			"content": (
				"<p>Karen's team went with a competitor — they had deeper BI integrations that we "
				"currently don't support. Not a pricing issue. Flagged to product team for roadmap "
				"consideration. Karen asked us to follow up in 6 months.</p>"
			),
			"days_ago": 8,
		},
		{
			"inquiry": inquiry_names[6],  # Leo / Forge Digital
			"owner": session_user,
			"content": (
				"<p>Budget was cut for the rest of the year — Leo was very apologetic and said the "
				"product was exactly what they needed. Re-added to nurture sequence for Q4. "
				"Good candidate for a comeback inquiry.</p>"
			),
			"days_ago": 12,
		},
	]

	return [
		insert_comment(
			"CRM Inquiry",
			data["inquiry"],
			data["owner"],
			data["content"],
			full_names,
			now - timedelta(days=data["days_ago"]),
		)
		for data in comments_data
	]


def _create_inquiry_communications(inquiry_names, session_user, owner_1, full_names, now):
	# Use a placeholder email for recipients where we don't have a real one handy
	comms_data = [
		{
			"inquiry": inquiry_names[0],
			"owner": session_user,
			"sent_or_received": "Sent",
			"subject": "Sandbox access details — Acme Corp CRM Evaluation",
			"content": (
				"<p>Hi Alice,</p>"
				"<p>Thanks for joining yesterday's demo — really great session. I've created a "
				"dedicated sandbox environment pre-loaded with sample data. Login details and "
				"setup instructions are attached.</p>"
				"<p>Our onboarding specialist Sarah will also be available for a walkthrough "
				"session this week — just let us know a convenient time.</p>"
				"<p>Best regards</p>"
			),
			"sender": session_user,
			"recipients": "alice.johnson@example.com",
			"days_ago": 2,
		},
		{
			"inquiry": inquiry_names[1],
			"owner": owner_1,
			"sent_or_received": "Received",
			"subject": "Re: CRM Proposal — Pilot terms query",
			"content": (
				"<p>Hi,</p>"
				"<p>We've reviewed the proposal and the pricing looks good. Before we proceed, "
				"could you clarify what's included in the onboarding package? Specifically, we "
				"need help migrating ~4,000 contacts from our existing system.</p>"
				"<p>Also, is there flexibility on the contract start date?</p>"
				"<p>Thanks,<br>David Lee<br>CTO, TechStart Inc</p>"
			),
			"sender": "david.lee@example.com",
			"recipients": owner_1,
			"days_ago": 4,
		},
	]

	return [
		insert_communication(
			"CRM Inquiry", data["inquiry"], data, full_names, now - timedelta(days=data["days_ago"])
		)
		for data in comms_data
	]


def _create_inquiry_versions(inquiry_names, session_user, owner_1, owner_2, now):
	versions_data = [
		{
			"inquiry": inquiry_names[0],  # Alice
			"owner": session_user,
			"changed": [["probability", "30", "50"]],
			"days_ago": 4,
		},
		{
			"inquiry": inquiry_names[1],  # David
			"owner": owner_1,
			"changed": [["inquiry_value", "40000", "45000"]],
			"days_ago": 6,
		},
		{
			"inquiry": inquiry_names[2],  # Henry
			"owner": owner_2,
			"changed": [["probability", "50", "60"]],
			"days_ago": 8,
		},
		{
			"inquiry": inquiry_names[3],  # Iris
			"owner": session_user,
			"changed": [["probability", "25", "35"]],
			"days_ago": 11,
		},
		{
			"inquiry": inquiry_names[4],  # Jack
			"owner": owner_1,
			"changed": [["status", "Ready to Close", "Won"]],
			"days_ago": 3,
		},
		{
			"inquiry": inquiry_names[5],  # Karen
			"owner": owner_2,
			"changed": [["status", "Proposal/Quotation", "Lost"]],
			"days_ago": 9,
		},
		{
			"inquiry": inquiry_names[6],  # Leo
			"owner": session_user,
			"changed": [["status", "Demo/Making", "Lost"]],
			"days_ago": 13,
		},
	]

	for data in versions_data:
		insert_version(
			"CRM Inquiry", data["inquiry"], data["owner"], data["changed"], now - timedelta(days=data["days_ago"])
		)


def delete_demo_inquiries(inquiry_data, lead_names):
	"""
	Delete inquiries, their linked contacts, organizations, and inquiry-specific communications.
	Comments and Versions are cascade-deleted when the inquiry is deleted.
	"""
	communication_names = inquiry_data.get("communications", [])
	inquiry_names = set(inquiry_data.get("inquiries", []))

	# Find all inquiries converted from the provided demo leads
	if lead_names:
		demo_lead_inquiries = frappe.get_all("CRM Inquiry", filters={"lead": ["in", lead_names]}, pluck="name")
		inquiry_names.update(demo_lead_inquiries)

	for name in communication_names:
		if frappe.db.exists("Communication", name):
			frappe.delete_doc("Communication", name, ignore_permissions=True, force=True)

	for name in inquiry_names:
		if not frappe.db.exists("CRM Inquiry", name):
			continue
		# Collect linked contacts and organization before deleting inquiry
		contact_names = frappe.get_all(
			"CRM Contacts", filters={"parent": name, "parenttype": "CRM Inquiry"}, pluck="contact"
		)
		org = frappe.db.get_value("CRM Inquiry", name, "organization")
		frappe.delete_doc("CRM Inquiry", name, ignore_permissions=True, force=True)
		for contact in contact_names:
			if contact and frappe.db.exists("Contact", contact):
				for child_doctype in ("Contact Email", "Contact Phone", "Dynamic Link"):
					Child = DocType(child_doctype)
					frappe.qb.from_(Child).delete().where(Child.parent == contact).run()
				Contact = DocType("Contact")
				frappe.qb.from_(Contact).delete().where(Contact.name == contact).run()
		if org and frappe.db.exists("CRM Organization", org):
			frappe.delete_doc("CRM Organization", org, ignore_permissions=True, force=True)

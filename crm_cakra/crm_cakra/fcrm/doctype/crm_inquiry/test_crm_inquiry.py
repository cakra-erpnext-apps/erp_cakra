# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry import (
	add_contact,
	create_inquiry,
	remove_contact,
	set_primary_contact,
)


class TestCRMInquiry(FrappeTestCase):
	def tearDown(self) -> None:
		frappe.db.rollback()

	def test_inquiry_creation_with_organization(self):
		"""Test creating a inquiry with organization"""
		inquiry = create_test_inquiry(
			organization="Test Org Inc",
			annual_revenue=1000000,
			status="Qualification",
		)

		self.assertTrue(inquiry.name)
		self.assertTrue(inquiry.organization)
		self.assertEqual(inquiry.annual_revenue, 1000000)

	def test_set_primary_contact(self):
		"""Test setting primary contact from contacts table"""
		# Create contacts
		contact1 = create_test_contact(first_name="John", last_name="Doe", email="john@example.com")
		contact2 = create_test_contact(
			first_name="Jane", last_name="Smith", email="jane@example.com", mobile_no="+1234567890"
		)

		# Create inquiry with two contacts
		inquiry = create_test_inquiry(organization="Contact Test Org")
		inquiry.append("contacts", {"contact": contact1.name})
		inquiry.append("contacts", {"contact": contact2.name, "is_primary": 1})
		inquiry.save()

		# Verify primary contact is set
		inquiry.reload()
		primary_contacts = [c for c in inquiry.contacts if c.is_primary == 1]
		self.assertEqual(len(primary_contacts), 1)
		self.assertEqual(primary_contacts[0].contact, contact2.name)

	def test_set_primary_email_mobile_no(self):
		"""Test that email and mobile are set from primary contact"""
		# Create contact
		contact = create_test_contact(
			first_name="Test",
			last_name="User",
			email="testuser@example.com",
			mobile_no="+9876543210",
			phone="+1111111111",
		)

		# Create inquiry with contact
		inquiry = create_test_inquiry(organization="Email Test Org")
		inquiry.append("contacts", {"contact": contact.name, "is_primary": 1})
		inquiry.save()

		# Verify email and mobile are set from contact
		inquiry.reload()
		self.assertEqual(inquiry.email, "testuser@example.com")
		self.assertEqual(inquiry.mobile_no, "+9876543210")
		self.assertEqual(inquiry.phone, "+1111111111")

	def test_multiple_primary_contacts_error(self):
		"""Test that having multiple primary contacts throws error"""
		contact1 = create_test_contact(first_name="Primary1", email="p1@example.com")
		contact2 = create_test_contact(first_name="Primary2", email="p2@example.com")

		inquiry = create_test_inquiry(organization="Multiple Primary Test")
		inquiry.append("contacts", {"contact": contact1.name, "is_primary": 1})
		inquiry.append("contacts", {"contact": contact2.name, "is_primary": 1})

		with self.assertRaises(frappe.exceptions.ValidationError) as context:
			inquiry.save()
		self.assertIn("Only one", str(context.exception))

	def test_no_primary_contact_clears_email(self):
		"""Test that email/mobile on inquiry (not child table) are cleared when no primary contact"""
		contact1 = create_test_contact(
			first_name="Primary", email="primary@example.com", mobile_no="+1111111111"
		)
		contact2 = create_test_contact(first_name="NonPrimary", email="nonprimary@example.com")

		# Create inquiry with primary contact - email should be set
		inquiry = create_test_inquiry(
			organization="No Primary Org",
			expected_inquiry_value=1000,
			expected_closure_date="2026-12-31",
		)
		inquiry.append("contacts", {"contact": contact1.name, "is_primary": 1})
		inquiry.save()
		inquiry.reload()

		self.assertEqual(inquiry.email, "primary@example.com")
		self.assertEqual(inquiry.mobile_no, "+1111111111")

		# Change to non-primary contact - inquiry email should be cleared
		for c in inquiry.contacts:
			c.is_primary = 0
		inquiry.append("contacts", {"contact": contact2.name, "is_primary": 0})
		inquiry.save()
		inquiry.reload()

		# Inquiry-level fields should be cleared since no primary contact
		self.assertEqual(inquiry.email, "")
		self.assertEqual(inquiry.mobile_no, "")
		self.assertEqual(inquiry.phone, "")

	def test_inquiry_owner_assignment(self):
		"""Test that inquiry owner is assigned on creation"""
		inquiry = create_test_inquiry(organization="Owner Test Org", inquiry_owner="Administrator")

		# Verify inquiry owner is assigned
		assignees = inquiry.get_assigned_users()
		self.assertIn("Administrator", assignees)

	def test_update_inquiry_owner(self):
		"""Test updating inquiry owner assigns and shares with new owner"""
		# Create inquiry without owner
		inquiry = create_test_inquiry(organization="Update Owner Org")
		self.assertFalse(inquiry.inquiry_owner)

		# Update inquiry owner
		inquiry.inquiry_owner = "Administrator"
		inquiry.save()

		# Verify assignment and share
		inquiry.reload()
		self.assertEqual(inquiry.inquiry_owner, "Administrator")
		assignees = inquiry.get_assigned_users()
		self.assertIn("Administrator", assignees)

		docshare = frappe.db.exists(
			"DocShare",
			{"user": "Administrator", "share_name": inquiry.name, "share_doctype": "CRM Inquiry"},
		)
		self.assertTrue(docshare)

		# Try to assign same agent again - should not duplicate
		initial_count = len(assignees)
		inquiry.assign_agent("Administrator")
		assignees_after = inquiry.get_assigned_users()
		self.assertEqual(len(assignees_after), initial_count)

	def test_add_contact_api(self):
		"""Test add_contact API function"""
		inquiry = create_test_inquiry(organization="Add Contact Org")
		contact = create_test_contact(first_name="API", last_name="User", email="api@example.com")

		# Add contact using API
		result = add_contact(inquiry.name, contact.name)
		self.assertTrue(result)

		# Verify contact was added
		inquiry.reload()
		contact_names = [c.contact for c in inquiry.contacts]
		self.assertIn(contact.name, contact_names)

	def test_remove_contact_api(self):
		"""Test remove_contact API function"""
		contact = create_test_contact(first_name="Remove", email="remove@example.com")
		inquiry = create_test_inquiry(organization="Remove Contact Org")
		inquiry.append("contacts", {"contact": contact.name})
		inquiry.save()

		# Verify contact exists
		inquiry.reload()
		self.assertEqual(len(inquiry.contacts), 1)

		# Remove contact using API
		result = remove_contact(inquiry.name, contact.name)
		self.assertTrue(result)

		# Verify contact was removed
		inquiry.reload()
		self.assertEqual(len(inquiry.contacts), 0)

	def test_set_primary_contact_api(self):
		"""Test set_primary_contact API function"""
		contact1 = create_test_contact(first_name="First", email="first@example.com")
		contact2 = create_test_contact(first_name="Second", email="second@example.com")

		inquiry = create_test_inquiry(organization="Primary API Org")
		inquiry.append("contacts", {"contact": contact1.name, "is_primary": 1})
		inquiry.append("contacts", {"contact": contact2.name})
		inquiry.save()

		# Change primary contact using API
		result = set_primary_contact(inquiry.name, contact2.name)
		self.assertTrue(result)

		# Verify primary contact was changed
		inquiry.reload()
		for c in inquiry.contacts:
			if c.contact == contact2.name:
				self.assertEqual(c.is_primary, 1)
			else:
				self.assertEqual(c.is_primary, 0)

	def test_create_inquiry_api(self):
		"""Test create_inquiry API function"""
		inquiry_name = create_inquiry(
			{
				"organization_name": "API Inquiry Org",
				"annual_revenue": 500000,
				"first_name": "Inquiry",
				"last_name": "Creator",
				"email": "inquirycreator@example.com",
				"mobile_no": "+5555555555",
			}
		)

		self.assertTrue(inquiry_name)

		# Verify inquiry was created
		inquiry = frappe.get_doc("CRM Inquiry", inquiry_name)
		self.assertEqual(inquiry.annual_revenue, 500000)
		self.assertTrue(inquiry.organization)
		self.assertTrue(len(inquiry.contacts) > 0)

		# Verify organization was created
		org = frappe.get_doc("CRM Organization", inquiry.organization)
		self.assertEqual(org.organization_name, "API Inquiry Org")

		# Verify contact was created
		contact = frappe.get_doc("Contact", inquiry.contacts[0].contact)
		self.assertEqual(contact.first_name, "Inquiry")
		self.assertEqual(contact.email_id, "inquirycreator@example.com")

	def test_create_inquiry_with_existing_organization(self):
		"""Test create_inquiry with existing organization"""
		# Create organization first
		org = frappe.get_doc(
			{
				"doctype": "CRM Organization",
				"organization_name": "Existing Org",
				"annual_revenue": 2000000,
			}
		).insert()

		# Create inquiry with same organization name
		inquiry_name = create_inquiry(
			{
				"organization_name": "Existing Org",
				"first_name": "Existing",
				"email": "existing@example.com",
			}
		)

		inquiry = frappe.get_doc("CRM Inquiry", inquiry_name)
		self.assertEqual(inquiry.organization, org.name)

	def test_create_inquiry_with_existing_contact(self):
		"""Test create_inquiry with existing contact"""
		# Create contact first
		contact = create_test_contact(
			first_name="Existing", last_name="Contact", email="existingc@example.com"
		)

		# Create inquiry with same email
		inquiry_name = create_inquiry(
			{
				"organization_name": "Contact Existing Org",
				"first_name": "Existing",
				"email": "existingc@example.com",
			}
		)

		inquiry = frappe.get_doc("CRM Inquiry", inquiry_name)
		self.assertEqual(inquiry.contacts[0].contact, contact.name)

	def test_validate_lost_reason_required(self):
		"""Test that lost reason is required when status is Lost"""
		# Create Lost status if not exists
		if not frappe.db.exists("CRM Inquiry Status", "Lost"):
			frappe.get_doc({"doctype": "CRM Inquiry Status", "name": "Lost", "type": "Lost"}).insert()

		inquiry = create_test_inquiry(organization="Lost Inquiry Org")

		# Try to set status to Lost without lost_reason
		inquiry.status = "Lost"
		with self.assertRaises(frappe.exceptions.ValidationError) as context:
			inquiry.save()
		self.assertIn("reason for losing", str(context.exception))

	def test_validate_lost_reason_other(self):
		"""Test that lost_notes is required when lost_reason is Other"""
		if not frappe.db.exists("CRM Inquiry Status", "Lost"):
			frappe.get_doc({"doctype": "CRM Inquiry Status", "name": "Lost", "type": "Lost"}).insert()

		if not frappe.db.exists("CRM Lost Reason", "Other"):
			frappe.get_doc({"doctype": "CRM Lost Reason", "reason": "Other"}).insert()

		inquiry = create_test_inquiry(organization="Lost Notes Org")
		inquiry.status = "Lost"
		inquiry.lost_reason = "Other"

		with self.assertRaises(frappe.exceptions.ValidationError) as context:
			inquiry.save()
		self.assertIn("specify the reason", str(context.exception))

	def test_closed_date_set_on_won(self):
		"""Test that closed_date is set when status is Won"""
		if not frappe.db.exists("CRM Inquiry Status", "Won"):
			frappe.get_doc({"doctype": "CRM Inquiry Status", "name": "Won", "type": "Won"}).insert()

		inquiry = create_test_inquiry(
			organization="Won Inquiry Org", expected_inquiry_value=10000, expected_closure_date="2026-12-31"
		)
		self.assertFalse(inquiry.closed_date)

		inquiry.status = "Won"
		inquiry.save()

		inquiry.reload()
		self.assertTrue(inquiry.closed_date)

	def test_forecasting_fields_validation(self):
		"""Test forecasting fields validation when enabled"""
		# Enable forecasting
		settings = frappe.get_single("FCRM Settings")
		original_value = settings.enable_forecasting
		settings.enable_forecasting = 1
		settings.save()

		try:
			# Should fail without expected_inquiry_value
			with self.assertRaises(frappe.exceptions.MandatoryError):
				create_test_inquiry(organization="Forecast Org")

			# Should fail without expected_closure_date
			with self.assertRaises(frappe.exceptions.MandatoryError):
				create_test_inquiry(organization="Forecast Org 2", expected_inquiry_value=5000)

			# Should succeed with both fields
			inquiry = create_test_inquiry(
				organization="Forecast Org 3",
				expected_inquiry_value=5000,
				expected_closure_date="2026-12-31",
			)
			self.assertTrue(inquiry.name)

		finally:
			# Restore original setting
			settings.enable_forecasting = original_value
			settings.save()

	def test_single_contact_auto_primary(self):
		"""Test that single contact is automatically set as primary"""
		contact = create_test_contact(first_name="Auto", email="auto@example.com")
		inquiry = create_test_inquiry(organization="Auto Primary Org")
		inquiry.append("contacts", {"contact": contact.name})
		inquiry.save()

		inquiry.reload()
		self.assertEqual(inquiry.contacts[0].is_primary, 1)


def create_test_inquiry(**kwargs):
	"""Helper function to create a CRM Inquiry for testing"""
	# Create organization if provided as string
	if "organization" in kwargs and isinstance(kwargs["organization"], str):
		org_name = kwargs["organization"]
		if not frappe.db.exists("CRM Organization", {"organization_name": org_name}):
			org = frappe.get_doc({"doctype": "CRM Organization", "organization_name": org_name}).insert()
			kwargs["organization"] = org.name
		else:
			kwargs["organization"] = frappe.db.get_value(
				"CRM Organization", {"organization_name": org_name}, "name"
			)

	data = {"doctype": "CRM Inquiry"}
	data.update(kwargs)
	return frappe.get_doc(data).insert()


def create_test_contact(**kwargs):
	"""Helper function to create a Contact for testing"""
	contact = frappe.get_doc({"doctype": "Contact"})
	contact.update(kwargs)

	if kwargs.get("email"):
		contact.append("email_ids", {"email_id": kwargs["email"], "is_primary": 1})

	if kwargs.get("mobile_no"):
		contact.append("phone_nos", {"phone": kwargs["mobile_no"], "is_primary_mobile_no": 1})

	if kwargs.get("phone"):
		contact.append("phone_nos", {"phone": kwargs["phone"], "is_primary_phone": 1})

	contact.insert(ignore_permissions=True)
	return contact

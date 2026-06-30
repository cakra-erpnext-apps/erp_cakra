# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CRMDashboard(Document):
	pass


def default_manager_dashboard_layout():
	"""
	Returns the default layout for the CRM Manager Dashboard.
	"""
	return '[{"name":"total_leads","type":"number_chart","tooltip":"Total number of leads","layout":{"x":0,"y":0,"w":4,"h":3,"i":"total_leads"}},{"name":"ongoing_inquiries","type":"number_chart","tooltip":"Total number of ongoing inquiries","layout":{"x":8,"y":0,"w":4,"h":3,"i":"ongoing_inquiries"}},{"name":"won_inquiries","type":"number_chart","tooltip":"Total number of won inquiries","layout":{"x":12,"y":0,"w":4,"h":3,"i":"won_inquiries"}},{"name":"average_won_inquiry_value","type":"number_chart","tooltip":"Average value of won inquiries","layout":{"x":16,"y":0,"w":4,"h":3,"i":"average_won_inquiry_value"}},{"name":"average_inquiry_value","type":"number_chart","tooltip":"Average inquiry value of ongoing and won inquiries","layout":{"x":0,"y":2,"w":4,"h":3,"i":"average_inquiry_value"}},{"name":"average_time_to_close_a_lead","type":"number_chart","tooltip":"Average time taken to close a lead","layout":{"x":4,"y":0,"w":4,"h":3,"i":"average_time_to_close_a_lead"}},{"name":"average_time_to_close_a_inquiry","type":"number_chart","layout":{"x":4,"y":2,"w":4,"h":3,"i":"average_time_to_close_a_inquiry"}},{"name":"spacer","type":"spacer","layout":{"x":8,"y":2,"w":12,"h":3,"i":"spacer"}},{"name":"sales_trend","type":"axis_chart","layout":{"x":0,"y":4,"w":10,"h":9,"i":"sales_trend"}},{"name":"forecasted_revenue","type":"axis_chart","layout":{"x":10,"y":4,"w":10,"h":9,"i":"forecasted_revenue"}},{"name":"funnel_conversion","type":"axis_chart","layout":{"x":0,"y":11,"w":10,"h":9,"i":"funnel_conversion"}},{"name":"inquiries_by_stage_donut","type":"donut_chart","layout":{"x":10,"y":11,"w":10,"h":9,"i":"inquiries_by_stage_donut"}},{"name":"lost_inquiry_reasons","type":"axis_chart","layout":{"x":0,"y":32,"w":20,"h":9,"i":"lost_inquiry_reasons"}},{"name":"leads_by_source","type":"donut_chart","layout":{"x":0,"y":18,"w":10,"h":9,"i":"leads_by_source"}},{"name":"inquiries_by_source","type":"donut_chart","layout":{"x":10,"y":18,"w":10,"h":9,"i":"inquiries_by_source"}},{"name":"inquiries_by_territory","type":"axis_chart","layout":{"x":0,"y":25,"w":10,"h":9,"i":"inquiries_by_territory"}},{"name":"inquiries_by_salesperson","type":"axis_chart","layout":{"x":10,"y":25,"w":10,"h":9,"i":"inquiries_by_salesperson"}}]'


def create_default_manager_dashboard(force=False):
	"""
	Creates the default CRM Manager Dashboard if it does not exist.
	"""
	if not frappe.db.exists("CRM Dashboard", "Manager Dashboard"):
		doc = frappe.new_doc("CRM Dashboard")
		doc.title = "Manager Dashboard"
		doc.layout = default_manager_dashboard_layout()
		doc.insert(ignore_permissions=True)
	else:
		doc = frappe.get_doc("CRM Dashboard", "Manager Dashboard")
		if force:
			doc.layout = default_manager_dashboard_layout()
			doc.save(ignore_permissions=True)
	return doc.layout

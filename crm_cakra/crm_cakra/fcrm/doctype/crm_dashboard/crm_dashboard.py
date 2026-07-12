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
	return '[{"name":"my_outstanding_quotations","type":"quotation_table","layout":{"x":0,"y":0,"w":13,"h":10,"i":"my_outstanding_quotations"}},{"name":"open_quotations","type":"number_chart","layout":{"x":13,"y":0,"w":7,"h":3,"i":"open_quotations"}},{"name":"expiring_quotations","type":"number_chart","layout":{"x":13,"y":3,"w":7,"h":3,"i":"expiring_quotations"}},{"name":"quotation_win_rate","type":"number_chart","layout":{"x":13,"y":6,"w":7,"h":4,"i":"quotation_win_rate"}},{"name":"ongoing_inquiries","type":"number_chart","layout":{"x":0,"y":10,"w":5,"h":3,"i":"ongoing_inquiries"}},{"name":"won_inquiries","type":"number_chart","layout":{"x":5,"y":10,"w":5,"h":3,"i":"won_inquiries"}},{"name":"quotation_value_won","type":"number_chart","layout":{"x":10,"y":10,"w":5,"h":3,"i":"quotation_value_won"}},{"name":"total_leads","type":"number_chart","layout":{"x":15,"y":10,"w":5,"h":3,"i":"total_leads"}},{"name":"inquiry_trend_by_branch","type":"axis_chart","layout":{"x":0,"y":13,"w":20,"h":9,"i":"inquiry_trend_by_branch"}},{"name":"inquiry_trend_by_business_unit","type":"axis_chart","layout":{"x":0,"y":22,"w":10,"h":9,"i":"inquiry_trend_by_business_unit"}},{"name":"inquiry_trend_by_job_service","type":"axis_chart","layout":{"x":10,"y":22,"w":10,"h":9,"i":"inquiry_trend_by_job_service"}},{"name":"inquiry_trend_by_transportation_mode","type":"axis_chart","layout":{"x":0,"y":31,"w":20,"h":9,"i":"inquiry_trend_by_transportation_mode"}},{"name":"inquiries_by_business_unit","type":"donut_chart","layout":{"x":0,"y":40,"w":10,"h":9,"i":"inquiries_by_business_unit"}},{"name":"win_rate_by_business_unit","type":"axis_chart","layout":{"x":10,"y":40,"w":10,"h":9,"i":"win_rate_by_business_unit"}},{"name":"inquiries_by_job_service","type":"axis_chart","layout":{"x":0,"y":49,"w":10,"h":9,"i":"inquiries_by_job_service"}},{"name":"inquiries_by_transportation_mode","type":"donut_chart","layout":{"x":10,"y":49,"w":10,"h":9,"i":"inquiries_by_transportation_mode"}},{"name":"top_routes","type":"axis_chart","layout":{"x":0,"y":58,"w":20,"h":9,"i":"top_routes"}},{"name":"funnel_conversion","type":"axis_chart","layout":{"x":0,"y":67,"w":10,"h":9,"i":"funnel_conversion"}},{"name":"inquiries_by_stage_donut","type":"donut_chart","layout":{"x":10,"y":67,"w":10,"h":9,"i":"inquiries_by_stage_donut"}},{"name":"quotations_by_status","type":"axis_chart","layout":{"x":0,"y":76,"w":10,"h":9,"i":"quotations_by_status"}},{"name":"lost_inquiry_reasons","type":"axis_chart","layout":{"x":10,"y":76,"w":10,"h":9,"i":"lost_inquiry_reasons"}},{"name":"inquiries_by_salesperson","type":"axis_chart","layout":{"x":0,"y":85,"w":20,"h":9,"i":"inquiries_by_salesperson"}}]'


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

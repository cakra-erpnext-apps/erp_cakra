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
	return '[{"name":"my_outstanding_quotations","type":"outstanding_table","layout":{"x":0,"y":0,"w":10,"h":10,"i":"my_outstanding_quotations"}},{"name":"my_outstanding_inquiries","type":"outstanding_table","layout":{"x":10,"y":0,"w":10,"h":10,"i":"my_outstanding_inquiries"}},{"name":"open_quotations","type":"number_chart","layout":{"x":0,"y":10,"w":7,"h":3,"i":"open_quotations"}},{"name":"quotation_value_won","type":"number_chart","layout":{"x":7,"y":10,"w":6,"h":3,"i":"quotation_value_won"}},{"name":"quotation_win_rate","type":"number_chart","layout":{"x":13,"y":10,"w":7,"h":3,"i":"quotation_win_rate"}},{"name":"ongoing_inquiries","type":"number_chart","layout":{"x":0,"y":13,"w":10,"h":3,"i":"ongoing_inquiries"}},{"name":"expiring_quotations","type":"number_chart","layout":{"x":10,"y":13,"w":10,"h":3,"i":"expiring_quotations"}},{"name":"inquiry_trend_by_business_unit","type":"axis_chart","layout":{"x":0,"y":16,"w":7,"h":9,"i":"inquiry_trend_by_business_unit"}},{"name":"inquiry_trend_by_job_service","type":"axis_chart","layout":{"x":7,"y":16,"w":6,"h":9,"i":"inquiry_trend_by_job_service"}},{"name":"inquiry_trend_by_transportation_mode","type":"axis_chart","layout":{"x":13,"y":16,"w":7,"h":9,"i":"inquiry_trend_by_transportation_mode"}},{"name":"inquiry_trend_by_branch","type":"axis_chart","layout":{"x":0,"y":25,"w":20,"h":9,"i":"inquiry_trend_by_branch"}},{"name":"inquiries_by_job_service","type":"axis_chart","layout":{"x":0,"y":34,"w":7,"h":9,"i":"inquiries_by_job_service"}},{"name":"top_business_unit","type":"axis_chart","layout":{"x":7,"y":34,"w":6,"h":9,"i":"top_business_unit"}},{"name":"top_type_of_inquiry","type":"axis_chart","layout":{"x":13,"y":34,"w":7,"h":9,"i":"top_type_of_inquiry"}},{"name":"top_accounts","type":"axis_chart","layout":{"x":0,"y":43,"w":20,"h":9,"i":"top_accounts"}},{"name":"inquiries_by_business_unit","type":"donut_chart","layout":{"x":0,"y":52,"w":10,"h":9,"i":"inquiries_by_business_unit"}},{"name":"win_rate_by_business_unit","type":"axis_chart","layout":{"x":10,"y":52,"w":10,"h":9,"i":"win_rate_by_business_unit"}},{"name":"inquiries_by_transportation_mode","type":"donut_chart","layout":{"x":0,"y":61,"w":10,"h":9,"i":"inquiries_by_transportation_mode"}},{"name":"inquiries_by_stage_donut","type":"donut_chart","layout":{"x":10,"y":61,"w":10,"h":9,"i":"inquiries_by_stage_donut"}},{"name":"top_routes","type":"axis_chart","layout":{"x":0,"y":70,"w":20,"h":9,"i":"top_routes"}},{"name":"funnel_conversion","type":"axis_chart","layout":{"x":0,"y":79,"w":10,"h":9,"i":"funnel_conversion"}},{"name":"quotations_by_status","type":"axis_chart","layout":{"x":10,"y":79,"w":10,"h":9,"i":"quotations_by_status"}},{"name":"lost_inquiry_reasons","type":"axis_chart","layout":{"x":0,"y":88,"w":10,"h":9,"i":"lost_inquiry_reasons"}},{"name":"inquiries_by_salesperson","type":"axis_chart","layout":{"x":10,"y":88,"w":10,"h":9,"i":"inquiries_by_salesperson"}}]'


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

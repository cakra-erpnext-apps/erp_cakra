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
	# Sengaja ramping: 8 chart saja, semuanya berbasis CRM Quotation (permintaan
	# user: laporan berbentuk quotation; chart inquiry lama tetap ada sebagai
	# fungsi dan bisa ditambahkan lagi lewat Edit -> Chart bila dibutuhkan).
	return '[{"name":"my_outstanding_quotations","type":"outstanding_table","layout":{"x":0,"y":0,"w":10,"h":10,"i":"my_outstanding_quotations"}},{"name":"my_outstanding_inquiries","type":"outstanding_table","layout":{"x":10,"y":0,"w":10,"h":10,"i":"my_outstanding_inquiries"}},{"name":"open_quotations","type":"number_chart","layout":{"x":0,"y":10,"w":4,"h":3,"i":"open_quotations"}},{"name":"quotation_value_won","type":"number_chart","layout":{"x":4,"y":10,"w":4,"h":3,"i":"quotation_value_won"}},{"name":"quotation_win_rate","type":"number_chart","layout":{"x":8,"y":10,"w":4,"h":3,"i":"quotation_win_rate"}},{"name":"ongoing_inquiries","type":"number_chart","layout":{"x":12,"y":10,"w":4,"h":3,"i":"ongoing_inquiries"}},{"name":"expiring_quotations","type":"number_chart","layout":{"x":16,"y":10,"w":4,"h":3,"i":"expiring_quotations"}},{"name":"funnel_conversion","type":"axis_chart","layout":{"x":0,"y":13,"w":10,"h":9,"i":"funnel_conversion"}},{"name":"quotations_by_status","type":"axis_chart","layout":{"x":10,"y":13,"w":10,"h":9,"i":"quotations_by_status"}},{"name":"quotation_trend_by_branch","type":"axis_chart","layout":{"x":0,"y":22,"w":20,"h":9,"i":"quotation_trend_by_branch"}},{"name":"top_accounts","type":"axis_chart","layout":{"x":0,"y":31,"w":10,"h":9,"i":"top_accounts"}},{"name":"top_routes","type":"axis_chart","layout":{"x":10,"y":31,"w":10,"h":9,"i":"top_routes"}},{"name":"top_cargo","type":"axis_chart","layout":{"x":0,"y":40,"w":10,"h":9,"i":"top_cargo"}},{"name":"quotation_value_trend","type":"axis_chart","layout":{"x":10,"y":40,"w":10,"h":9,"i":"quotation_value_trend"}},{"name":"quotations_by_salesperson","type":"axis_chart","layout":{"x":0,"y":49,"w":20,"h":9,"i":"quotations_by_salesperson"}}]'


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

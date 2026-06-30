import json

import frappe
from frappe import _
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Avg, Coalesce, Count, Date, DateFormat, IfNull, Sum
from pypika.functions import Function

from crm_cakra.fcrm.doctype.crm_dashboard.crm_dashboard import create_default_manager_dashboard
from crm_cakra.utils import sales_user_only


# Custom function for TIMESTAMPDIFF (MySQL/MariaDB)
class TimestampDiff(Function):
	def __init__(self, unit, start, end, **kwargs):
		super().__init__("TIMESTAMPDIFF", unit, start, end, **kwargs)


@frappe.whitelist()
def reset_to_default():
	frappe.only_for("System Manager", True)
	create_default_manager_dashboard(force=True)


@frappe.whitelist()
@sales_user_only
def get_dashboard(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get the dashboard data for the CRM dashboard.
	"""

	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	roles = frappe.get_roles(frappe.session.user)
	is_sales_manager = "Sales Manager" in roles or "System Manager" in roles
	is_sales_user = "Sales User" in roles and not is_sales_manager

	if is_sales_user:
		user = frappe.session.user

	dashboard = frappe.db.exists("CRM Dashboard", "Manager Dashboard")

	layout = []

	if not dashboard:
		layout = json.loads(create_default_manager_dashboard())
		frappe.db.commit()
	else:
		layout = json.loads(frappe.db.get_value("CRM Dashboard", "Manager Dashboard", "layout") or "[]")

	for l in layout:
		method_name = f"get_{l['name']}"
		if hasattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name):
			method = getattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name)
			l["data"] = method(from_date, to_date, user)
		else:
			l["data"] = None

	return layout


@frappe.whitelist()
@sales_user_only
def get_chart(
	name: str, type: str, from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get number chart data for the dashboard.
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	roles = frappe.get_roles(frappe.session.user)
	is_sales_manager = "Sales Manager" in roles or "System Manager" in roles
	is_sales_user = "Sales User" in roles and not is_sales_manager

	if is_sales_user:
		user = frappe.session.user

	method_name = f"get_{name}"
	if hasattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name):
		method = getattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name)
		return method(from_date, to_date, user)
	else:
		return {"error": _("Invalid chart name")}


def get_total_leads(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get lead count for the dashboard.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Lead = DocType("CRM Lead")

	# Build conditions for current period
	current_cond = (Lead.creation >= from_date) & (Lead.creation < to_date_plus_one)
	if user:
		current_cond = current_cond & (Lead.lead_owner == user)

	# Build conditions for previous period
	prev_cond = (Lead.creation >= prev_from_date) & (Lead.creation < from_date)
	if user:
		prev_cond = prev_cond & (Lead.lead_owner == user)

	# Build query with CASE expressions
	query = frappe.qb.from_(Lead).select(
		Count(Case().when(current_cond, Lead.name).else_(None)).as_("current_month_leads"),
		Count(Case().when(prev_cond, Lead.name).else_(None)).as_("prev_month_leads"),
	)

	result = query.run(as_dict=True)

	current_month_leads = result[0].current_month_leads or 0
	prev_month_leads = result[0].prev_month_leads or 0

	delta_in_percentage = (
		(current_month_leads - prev_month_leads) / prev_month_leads * 100 if prev_month_leads else 0
	)

	return {
		"title": _("Total leads"),
		"tooltip": _("Total number of leads"),
		"value": current_month_leads,
		"delta": delta_in_percentage,
		"deltaSuffix": "%",
	}


def get_ongoing_inquiries(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get ongoing inquiry count for the dashboard, and also calculate average inquiry value for ongoing inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build conditions for current period
	current_cond = (
		(Inquiry.creation >= from_date)
		& (Inquiry.creation < to_date_plus_one)
		& (Status.type.notin(["Won", "Lost"]))
	)
	if user:
		current_cond = current_cond & (Inquiry.inquiry_owner == user)

	# Build conditions for previous period
	prev_cond = (
		(Inquiry.creation >= prev_from_date) & (Inquiry.creation < from_date) & (Status.type.notin(["Won", "Lost"]))
	)
	if user:
		prev_cond = prev_cond & (Inquiry.inquiry_owner == user)

	# Build query with CASE expressions
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Count(Case().when(current_cond, Inquiry.name).else_(None)).as_("current_month_inquiries"),
			Count(Case().when(prev_cond, Inquiry.name).else_(None)).as_("prev_month_inquiries"),
		)
	)

	result = query.run(as_dict=True)

	current_month_inquiries = result[0].current_month_inquiries or 0
	prev_month_inquiries = result[0].prev_month_inquiries or 0

	delta_in_percentage = (
		(current_month_inquiries - prev_month_inquiries) / prev_month_inquiries * 100 if prev_month_inquiries else 0
	)

	return {
		"title": _("Ongoing inquiries"),
		"tooltip": _("Total number of non won/lost inquiries"),
		"value": current_month_inquiries,
		"delta": delta_in_percentage,
		"deltaSuffix": "%",
	}


def get_average_ongoing_inquiry_value(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get ongoing inquiry count for the dashboard, and also calculate average inquiry value for ongoing inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build conditions for current period
	current_cond = (
		(Inquiry.creation >= from_date)
		& (Inquiry.creation < to_date_plus_one)
		& (Status.type.notin(["Won", "Lost"]))
	)
	if user:
		current_cond = current_cond & (Inquiry.inquiry_owner == user)

	# Build conditions for previous period
	prev_cond = (
		(Inquiry.creation >= prev_from_date) & (Inquiry.creation < from_date) & (Status.type.notin(["Won", "Lost"]))
	)
	if user:
		prev_cond = prev_cond & (Inquiry.inquiry_owner == user)

	# Calculate inquiry value with exchange rate
	inquiry_value_expr = Inquiry.inquiry_value * IfNull(Inquiry.exchange_rate, 1)

	# Build query with CASE expressions
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Avg(Case().when(current_cond, inquiry_value_expr).else_(None)).as_("current_month_avg_value"),
			Avg(Case().when(prev_cond, inquiry_value_expr).else_(None)).as_("prev_month_avg_value"),
		)
	)

	result = query.run(as_dict=True)

	current_month_avg_value = result[0].current_month_avg_value or 0
	prev_month_avg_value = result[0].prev_month_avg_value or 0

	avg_value_delta = current_month_avg_value - prev_month_avg_value if prev_month_avg_value else 0

	return {
		"title": _("Avg. ongoing inquiry value"),
		"tooltip": _("Average inquiry value of non won/lost inquiries"),
		"value": current_month_avg_value,
		"delta": avg_value_delta,
		"prefix": get_base_currency_symbol(),
	}


def get_won_inquiries(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get won inquiry count for the dashboard, and also calculate average inquiry value for won inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build conditions for current period
	current_cond = (
		(Inquiry.closed_date >= from_date) & (Inquiry.closed_date < to_date_plus_one) & (Status.type == "Won")
	)
	if user:
		current_cond = current_cond & (Inquiry.inquiry_owner == user)

	# Build conditions for previous period
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < from_date) & (Status.type == "Won")
	if user:
		prev_cond = prev_cond & (Inquiry.inquiry_owner == user)

	# Build query with CASE expressions
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Count(Case().when(current_cond, Inquiry.name).else_(None)).as_("current_month_inquiries"),
			Count(Case().when(prev_cond, Inquiry.name).else_(None)).as_("prev_month_inquiries"),
		)
	)

	result = query.run(as_dict=True)

	current_month_inquiries = result[0].current_month_inquiries or 0
	prev_month_inquiries = result[0].prev_month_inquiries or 0

	delta_in_percentage = (
		(current_month_inquiries - prev_month_inquiries) / prev_month_inquiries * 100 if prev_month_inquiries else 0
	)

	return {
		"title": _("Won inquiries"),
		"tooltip": _("Total number of won inquiries based on its closure date"),
		"value": current_month_inquiries,
		"delta": delta_in_percentage,
		"deltaSuffix": "%",
	}


def get_average_won_inquiry_value(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get won inquiry count for the dashboard, and also calculate average inquiry value for won inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build conditions for current period
	current_cond = (
		(Inquiry.closed_date >= from_date) & (Inquiry.closed_date < to_date_plus_one) & (Status.type == "Won")
	)
	if user:
		current_cond = current_cond & (Inquiry.inquiry_owner == user)

	# Build conditions for previous period
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < from_date) & (Status.type == "Won")
	if user:
		prev_cond = prev_cond & (Inquiry.inquiry_owner == user)

	# Calculate inquiry value with exchange rate
	inquiry_value_expr = Inquiry.inquiry_value * IfNull(Inquiry.exchange_rate, 1)

	# Build query with CASE expressions
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Avg(Case().when(current_cond, inquiry_value_expr).else_(None)).as_("current_month_avg_value"),
			Avg(Case().when(prev_cond, inquiry_value_expr).else_(None)).as_("prev_month_avg_value"),
		)
	)

	result = query.run(as_dict=True)

	current_month_avg_value = result[0].current_month_avg_value or 0
	prev_month_avg_value = result[0].prev_month_avg_value or 0

	avg_value_delta = current_month_avg_value - prev_month_avg_value if prev_month_avg_value else 0

	return {
		"title": _("Avg. won inquiry value"),
		"tooltip": _("Average inquiry value of won inquiries"),
		"value": current_month_avg_value,
		"delta": avg_value_delta,
		"prefix": get_base_currency_symbol(),
	}


def get_average_inquiry_value(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get average inquiry value for the dashboard.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build conditions for current period
	current_cond = (Inquiry.creation >= from_date) & (Inquiry.creation < to_date_plus_one) & (Status.type != "Lost")
	if user:
		current_cond = current_cond & (Inquiry.inquiry_owner == user)

	# Build conditions for previous period
	prev_cond = (Inquiry.creation >= prev_from_date) & (Inquiry.creation < from_date) & (Status.type != "Lost")
	if user:
		prev_cond = prev_cond & (Inquiry.inquiry_owner == user)

	# Calculate inquiry value with exchange rate
	inquiry_value_expr = Inquiry.inquiry_value * IfNull(Inquiry.exchange_rate, 1)

	# Build query with CASE expressions
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Avg(Case().when(current_cond, inquiry_value_expr).else_(None)).as_("current_month_avg"),
			Avg(Case().when(prev_cond, inquiry_value_expr).else_(None)).as_("prev_month_avg"),
		)
	)

	result = query.run(as_dict=True)

	current_month_avg = result[0].current_month_avg or 0
	prev_month_avg = result[0].prev_month_avg or 0

	delta = current_month_avg - prev_month_avg if prev_month_avg else 0

	return {
		"title": _("Avg. inquiry value"),
		"tooltip": _("Average inquiry value of ongoing & won inquiries"),
		"value": current_month_avg,
		"prefix": get_base_currency_symbol(),
		"delta": delta,
		"deltaSuffix": "%",
	}


def get_average_time_to_close_a_lead(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get average time to close inquiries for the dashboard.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)
	prev_to_date = from_date

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")
	Lead = DocType("CRM Lead")

	# Base condition: closed_date is not null and status type is Won
	base_cond = (Inquiry.closed_date.isnotnull()) & (Status.type == "Won")
	if user:
		base_cond = base_cond & (Inquiry.inquiry_owner == user)

	# Current period condition
	current_cond = (Inquiry.closed_date >= from_date) & (Inquiry.closed_date < to_date_plus_one)

	# Previous period condition
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < prev_to_date)

	# Calculate time difference from lead/inquiry creation to inquiry closure
	time_diff = TimestampDiff(
		frappe.qb.terms.LiteralValue("DAY"), Coalesce(Lead.creation, Inquiry.creation), Inquiry.closed_date
	)

	# Build query
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.left_join(Lead)
		.on(Inquiry.lead == Lead.name)
		.where(base_cond)
		.select(
			Avg(Case().when(current_cond, time_diff).else_(None)).as_("current_avg_lead"),
			Avg(Case().when(prev_cond, time_diff).else_(None)).as_("prev_avg_lead"),
		)
	)

	result = query.run(as_dict=True)

	current_avg_lead = result[0].current_avg_lead or 0
	prev_avg_lead = result[0].prev_avg_lead or 0
	delta_lead = current_avg_lead - prev_avg_lead if prev_avg_lead else 0

	return {
		"title": _("Avg. time to close a lead"),
		"tooltip": _("Average time taken from lead creation to inquiry closure"),
		"value": current_avg_lead,
		"suffix": " days",
		"delta": delta_lead,
		"deltaSuffix": " days",
		"negativeIsBetter": True,
	}


def get_average_time_to_close_a_inquiry(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get average time to close inquiries for the dashboard.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)
	to_date_plus_one = frappe.utils.add_days(to_date, 1)
	prev_to_date = from_date

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")
	Lead = DocType("CRM Lead")

	# Base condition: closed_date is not null and status type is Won
	base_cond = (Inquiry.closed_date.isnotnull()) & (Status.type == "Won")
	if user:
		base_cond = base_cond & (Inquiry.inquiry_owner == user)

	# Current period condition
	current_cond = (Inquiry.closed_date >= from_date) & (Inquiry.closed_date < to_date_plus_one)

	# Previous period condition
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < prev_to_date)

	# Calculate time difference from inquiry creation to inquiry closure
	time_diff = TimestampDiff(frappe.qb.terms.LiteralValue("DAY"), Inquiry.creation, Inquiry.closed_date)

	# Build query
	query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.left_join(Lead)
		.on(Inquiry.lead == Lead.name)
		.where(base_cond)
		.select(
			Avg(Case().when(current_cond, time_diff).else_(None)).as_("current_avg_inquiry"),
			Avg(Case().when(prev_cond, time_diff).else_(None)).as_("prev_avg_inquiry"),
		)
	)

	result = query.run(as_dict=True)

	current_avg_inquiry = result[0].current_avg_inquiry or 0
	prev_avg_inquiry = result[0].prev_avg_inquiry or 0
	delta_inquiry = current_avg_inquiry - prev_avg_inquiry if prev_avg_inquiry else 0

	return {
		"title": _("Avg. time to close a inquiry"),
		"tooltip": _("Average time taken from inquiry creation to inquiry closure"),
		"value": current_avg_inquiry,
		"suffix": " days",
		"delta": delta_inquiry,
		"deltaSuffix": " days",
		"negativeIsBetter": True,
	}


def get_sales_trend(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get sales trend data for the dashboard.
	[
		{ date: new Date('2024-05-01'), leads: 45, inquiries: 23, won_inquiries: 12 },
		{ date: new Date('2024-05-02'), leads: 50, inquiries: 30, won_inquiries: 15 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	Lead = DocType("CRM Lead")
	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")

	# Build leads query
	leads_query = (
		frappe.qb.from_(Lead)
		.select(
			Date(Lead.creation).as_("date"),
			Count("*").as_("leads"),
			frappe.qb.terms.ValueWrapper(0).as_("inquiries"),
			frappe.qb.terms.ValueWrapper(0).as_("won_inquiries"),
		)
		.where(Date(Lead.creation).between(from_date, to_date))
	)

	if user:
		leads_query = leads_query.where(Lead.lead_owner == user)

	leads_query = leads_query.groupby(Date(Lead.creation))

	# Build inquiries query
	inquiries_query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			Date(Inquiry.creation).as_("date"),
			frappe.qb.terms.ValueWrapper(0).as_("leads"),
			Count("*").as_("inquiries"),
			Sum(Case().when(Status.type == "Won", 1).else_(0)).as_("won_inquiries"),
		)
		.where(Date(Inquiry.creation).between(from_date, to_date))
	)

	if user:
		inquiries_query = inquiries_query.where(Inquiry.inquiry_owner == user)

	inquiries_query = inquiries_query.groupby(Date(Inquiry.creation))

	# Combine with UNION ALL and aggregate by date
	union_query = leads_query.union_all(inquiries_query)

	# Wrap in outer query to aggregate by date
	daily = (
		frappe.qb.from_(union_query)
		.select(
			DateFormat(union_query.date, "%Y-%m-%d").as_("date"),
			Sum(union_query.leads).as_("leads"),
			Sum(union_query.inquiries).as_("inquiries"),
			Sum(union_query.won_inquiries).as_("won_inquiries"),
		)
		.groupby(union_query.date)
		.orderby(union_query.date)
	)

	result = daily.run(as_dict=True)

	sales_trend = [
		{
			"date": frappe.utils.get_datetime(row.date).strftime("%Y-%m-%d"),
			"leads": row.leads or 0,
			"inquiries": row.inquiries or 0,
			"won_inquiries": row.won_inquiries or 0,
		}
		for row in result
	]

	return {
		"data": sales_trend,
		"title": _("Sales trend"),
		"subtitle": _("Daily performance of leads, inquiries, and wins"),
		"xAxis": {
			"title": _("Date"),
			"key": "date",
			"type": "time",
			"timeGrain": "day",
		},
		"yAxis": {
			"title": _("Count"),
		},
		"series": [
			{"name": "leads", "type": "line", "showDataPoints": True},
			{"name": "inquiries", "type": "line", "showDataPoints": True},
			{"name": "won_inquiries", "type": "line", "showDataPoints": True},
		],
	}


def get_forecasted_revenue(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get forecasted revenue for the dashboard.
	[
		{ date: new Date('2024-05-01'), forecasted: 1200000, actual: 980000 },
		{ date: new Date('2024-06-01'), forecasted: 1350000, actual: 1120000 },
		{ date: new Date('2024-07-01'), forecasted: 1600000, actual: "" },
		{ date: new Date('2024-08-01'), forecasted: 1500000, actual: "" },
		...
	]
	"""
	# Using Frappe Query Builder with CASE expressions
	CRMInquiry = DocType("CRM Inquiry")
	CRMInquiryStatus = DocType("CRM Inquiry Status")

	# Calculate the date 12 months ago
	twelve_months_ago = frappe.utils.add_months(frappe.utils.nowdate(), -12)

	forecasted_value = (
		Case()
		.when(CRMInquiryStatus.type == "Lost", CRMInquiry.expected_inquiry_value * IfNull(CRMInquiry.exchange_rate, 1))
		.else_(
			CRMInquiry.expected_inquiry_value
			* IfNull(CRMInquiry.probability, 0)
			/ 100
			* IfNull(CRMInquiry.exchange_rate, 1)
		)
	)

	actual_value = (
		Case()
		.when(CRMInquiryStatus.type == "Won", CRMInquiry.inquiry_value * IfNull(CRMInquiry.exchange_rate, 1))
		.else_(0)
	)

	query = (
		frappe.qb.from_(CRMInquiry)
		.join(CRMInquiryStatus)
		.on(CRMInquiry.status == CRMInquiryStatus.name)
		.select(
			DateFormat(CRMInquiry.expected_closure_date, "%Y-%m").as_("month"),
			Sum(forecasted_value).as_("forecasted"),
			Sum(actual_value).as_("actual"),
		)
		.where(CRMInquiry.expected_closure_date >= twelve_months_ago)
		.groupby(DateFormat(CRMInquiry.expected_closure_date, "%Y-%m"))
		.orderby(DateFormat(CRMInquiry.expected_closure_date, "%Y-%m"))
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	for row in result:
		row["month"] = frappe.utils.get_datetime(row["month"]).strftime("%Y-%m-01")
		row["forecasted"] = row["forecasted"] or ""
		row["actual"] = row["actual"] or ""

	return {
		"data": result or [],
		"title": _("Forecasted revenue"),
		"subtitle": _("Projected vs actual revenue based on inquiry probability"),
		"xAxis": {
			"title": _("Month"),
			"key": "month",
			"type": "time",
			"timeGrain": "month",
		},
		"yAxis": {
			"title": _("Revenue") + f" ({get_base_currency_symbol()})",
		},
		"series": [
			{"name": "forecasted", "type": "line", "showDataPoints": True},
			{"name": "actual", "type": "line", "showDataPoints": True},
		],
	}


def get_funnel_conversion(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get funnel conversion data for the dashboard.
	[
		{ stage: 'Leads', count: 120 },
		{ stage: 'Qualification', count: 100 },
		{ stage: 'Negotiation', count: 80 },
		{ stage: 'Ready to Close', count: 60 },
		{ stage: 'Won', count: 30 },
		...
	]
	"""
	lead_conds = ""
	inquiry_conds = ""

	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	lead_filters = {"from": from_date, "to": to_date}
	inquiry_filters = {"from": from_date, "to": to_date}

	if user:
		lead_conds += " AND lead_owner = %(user)s"
		inquiry_conds += " AND inquiry_owner = %(user)s"
		lead_filters["user"] = user
		inquiry_filters["user"] = user

	result = []

	# Get total leads using Query Builder
	CRMLead = DocType("CRM Lead")

	query = (
		frappe.qb.from_(CRMLead)
		.select(Count("*").as_("count"))
		.where(Date(CRMLead.creation).between(from_date, to_date))
	)

	if user:
		query = query.where(CRMLead.lead_owner == user)

	total_leads = query.run(as_dict=True)
	total_leads_count = total_leads[0].count if total_leads else 0

	result.append({"stage": "Leads", "count": total_leads_count})

	result += get_inquiry_status_change_counts(from_date, to_date, inquiry_conds, inquiry_filters)

	return {
		"data": result or [],
		"title": _("Funnel conversion"),
		"subtitle": _("Lead to inquiry conversion pipeline"),
		"xAxis": {
			"title": _("Stage"),
			"key": "stage",
			"type": "category",
		},
		"yAxis": {
			"title": _("Count"),
		},
		"swapXY": True,
		"series": [
			{
				"name": "count",
				"type": "bar",
				"echartOptions": {
					"colorBy": "data",
				},
			},
		],
	}


def get_inquiries_by_stage_axis(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get inquiry data by stage for the dashboard.
	[
		{ stage: 'Prospecting', count: 120 },
		{ stage: 'Negotiation', count: 45 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder with NOT IN clause
	CRMInquiry = DocType("CRM Inquiry")
	CRMInquiryStatus = DocType("CRM Inquiry Status")

	query = (
		frappe.qb.from_(CRMInquiry)
		.join(CRMInquiryStatus)
		.on(CRMInquiry.status == CRMInquiryStatus.name)
		.select(CRMInquiry.status.as_("stage"), Count("*").as_("count"), CRMInquiryStatus.type.as_("status_type"))
		.where((Date(CRMInquiry.creation).between(from_date, to_date)) & (CRMInquiryStatus.type.notin(["Lost"])))
		.groupby(CRMInquiry.status)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by ongoing & won stage"),
		"xAxis": {
			"title": _("Stage"),
			"key": "stage",
			"type": "category",
		},
		"yAxis": {"title": _("Count")},
		"series": [
			{"name": "count", "type": "bar"},
		],
	}


def get_inquiries_by_stage_donut(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get inquiry data by stage for the dashboard.
	[
		{ stage: 'Prospecting', count: 120 },
		{ stage: 'Negotiation', count: 45 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder with JOIN
	CRMInquiry = DocType("CRM Inquiry")
	CRMInquiryStatus = DocType("CRM Inquiry Status")

	query = (
		frappe.qb.from_(CRMInquiry)
		.join(CRMInquiryStatus)
		.on(CRMInquiry.status == CRMInquiryStatus.name)
		.select(CRMInquiry.status.as_("stage"), Count("*").as_("count"), CRMInquiryStatus.type.as_("status_type"))
		.where(Date(CRMInquiry.creation).between(from_date, to_date))
		.groupby(CRMInquiry.status)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by stage"),
		"subtitle": _("Current pipeline distribution"),
		"categoryColumn": "stage",
		"valueColumn": "count",
	}


def get_lost_inquiry_reasons(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get lost inquiry reasons for the dashboard.
	[
		{ reason: 'Price too high', count: 20 },
		{ reason: 'Competitor won', count: 15 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder with JOIN
	CRMInquiry = DocType("CRM Inquiry")
	CRMInquiryStatus = DocType("CRM Inquiry Status")

	query = (
		frappe.qb.from_(CRMInquiry)
		.join(CRMInquiryStatus)
		.on(CRMInquiry.status == CRMInquiryStatus.name)
		.select(CRMInquiry.lost_reason.as_("reason"), Count("*").as_("count"))
		.where((Date(CRMInquiry.creation).between(from_date, to_date)) & (CRMInquiryStatus.type == "Lost"))
		.groupby(CRMInquiry.lost_reason)
		.having((CRMInquiry.lost_reason.isnotnull()) & (CRMInquiry.lost_reason != ""))
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Lost inquiry reasons"),
		"subtitle": _("Common reasons for losing inquiries"),
		"xAxis": {
			"title": _("Reason"),
			"key": "reason",
			"type": "category",
		},
		"yAxis": {
			"title": _("Count"),
		},
		"series": [
			{"name": "count", "type": "bar"},
		],
	}


def get_leads_by_source(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get lead data by source for the dashboard.
	[
		{ source: 'Website', count: 120 },
		{ source: 'Referral', count: 45 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder (safer, more maintainable)
	CRMLead = DocType("CRM Lead")

	query = (
		frappe.qb.from_(CRMLead)
		.select(IfNull(CRMLead.source, "Empty").as_("source"), Count("*").as_("count"))
		.where(Date(CRMLead.creation).between(from_date, to_date))
		.groupby(CRMLead.source)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if user:
		query = query.where(CRMLead.lead_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Leads by source"),
		"subtitle": _("Lead generation channel analysis"),
		"categoryColumn": "source",
		"valueColumn": "count",
	}


def get_inquiries_by_source(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get inquiry data by source for the dashboard.
	[
		{ source: 'Website', count: 120 },
		{ source: 'Referral', count: 45 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder
	CRMInquiry = DocType("CRM Inquiry")

	query = (
		frappe.qb.from_(CRMInquiry)
		.select(IfNull(CRMInquiry.source, "Empty").as_("source"), Count("*").as_("count"))
		.where(Date(CRMInquiry.creation).between(from_date, to_date))
		.groupby(CRMInquiry.source)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by source"),
		"subtitle": _("Inquiry generation channel analysis"),
		"categoryColumn": "source",
		"valueColumn": "count",
	}


def get_inquiries_by_territory(from_date: str | None = None, to_date: str | None = None, user: str | None = None):
	"""
	Get inquiry data by territory for the dashboard.
	[
		{ territory: 'North America', inquiries: 45, value: 2300000 },
		{ territory: 'Europe', inquiries: 30, value: 1500000 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder with complex aggregations
	CRMInquiry = DocType("CRM Inquiry")

	query = (
		frappe.qb.from_(CRMInquiry)
		.select(
			IfNull(CRMInquiry.territory, "Empty").as_("territory"),
			Count("*").as_("inquiries"),
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)).as_("value"),
		)
		.where(Date(CRMInquiry.creation).between(from_date, to_date))
		.groupby(CRMInquiry.territory)
		.orderby(Count("*"), order=frappe.qb.desc)
		.orderby(
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)), order=frappe.qb.desc
		)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by territory"),
		"subtitle": _("Geographic distribution of inquiries and revenue"),
		"xAxis": {
			"title": _("Territory"),
			"key": "territory",
			"type": "category",
		},
		"yAxis": {
			"title": _("Number of inquiries"),
		},
		"y2Axis": {
			"title": _("Inquiry value") + f" ({get_base_currency_symbol()})",
		},
		"series": [
			{"name": "inquiries", "type": "bar"},
			{"name": "value", "type": "line", "showDataPoints": True, "axis": "y2"},
		],
	}


def get_inquiries_by_salesperson(
	from_date: str | None = None, to_date: str | None = None, user: str | None = None
):
	"""
	Get inquiry data by salesperson for the dashboard.
	[
		{ salesperson: 'John Smith', inquiries: 45, value: 2300000 },
		{ salesperson: 'Jane Doe', inquiries: 30, value: 1500000 },
		...
	]
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	# Using Frappe Query Builder with LEFT JOIN
	CRMInquiry = DocType("CRM Inquiry")
	User = DocType("User")

	query = (
		frappe.qb.from_(CRMInquiry)
		.left_join(User)
		.on(User.name == CRMInquiry.inquiry_owner)
		.select(
			IfNull(User.full_name, CRMInquiry.inquiry_owner).as_("salesperson"),
			Count("*").as_("inquiries"),
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)).as_("value"),
		)
		.where(Date(CRMInquiry.creation).between(from_date, to_date))
		.groupby(CRMInquiry.inquiry_owner)
		.orderby(Count("*"), order=frappe.qb.desc)
		.orderby(
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)), order=frappe.qb.desc
		)
	)

	if user:
		query = query.where(CRMInquiry.inquiry_owner == user)

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by salesperson"),
		"subtitle": _("Number of inquiries and total value per salesperson"),
		"xAxis": {
			"title": _("Salesperson"),
			"key": "salesperson",
			"type": "category",
		},
		"yAxis": {
			"title": _("Number of inquiries"),
		},
		"y2Axis": {
			"title": _("Inquiry value") + f" ({get_base_currency_symbol()})",
		},
		"series": [
			{"name": "inquiries", "type": "bar"},
			{"name": "value", "type": "line", "showDataPoints": True, "axis": "y2"},
		],
	}


def get_base_currency_symbol():
	"""
	Get the base currency symbol from the system settings.
	"""
	base_currency = frappe.db.get_single_value("FCRM Settings", "currency") or "USD"
	return frappe.db.get_value("Currency", base_currency, "symbol") or ""


def get_inquiry_status_change_counts(
	from_date: str | None = None,
	to_date: str | None = None,
	inquiry_conds: str = "",
	filters: dict | None = None,
):
	"""
	Get count of each status change (to) for each inquiry, excluding inquiries with current status type 'Lost'.
	Order results by status position.
	Returns:
	[
	  {"status": "Qualification", "count": 120},
	  {"status": "Negotiation", "count": 85},
	  ...
	]
	"""
	# Using Frappe Query Builder with multiple JOINs and table aliases
	CRMStatusChangeLog = DocType("CRM Status Change Log")
	CRMInquiry = DocType("CRM Inquiry")
	CurrentStatus = DocType("CRM Inquiry Status").as_("s")
	TargetStatus = DocType("CRM Inquiry Status").as_("st")

	query = (
		frappe.qb.from_(CRMStatusChangeLog)
		.join(CRMInquiry)
		.on(CRMStatusChangeLog.parent == CRMInquiry.name)
		.join(CurrentStatus)
		.on(CRMInquiry.status == CurrentStatus.name)
		.join(TargetStatus)
		.on(CRMStatusChangeLog.to == TargetStatus.name)
		.select(CRMStatusChangeLog.to.as_("stage"), Count("*").as_("count"))
		.where(
			(CRMStatusChangeLog.to.isnotnull())
			& (CRMStatusChangeLog.to != "")
			& (CurrentStatus.type != "Lost")
			& (Date(CRMInquiry.creation).between(from_date, to_date))
		)
		.groupby(CRMStatusChangeLog.to, TargetStatus.position)
		.orderby(TargetStatus.position)
	)

	# Handle optional user filter if inquiry_conds contains user condition
	if filters and filters.get("user"):
		query = query.where(CRMInquiry.inquiry_owner == filters["user"])

	result = query.run(as_dict=True)
	return result or []

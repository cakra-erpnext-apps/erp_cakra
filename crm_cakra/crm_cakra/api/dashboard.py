import json

import frappe
from frappe import _
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Avg, Coalesce, Count, Date, DateFormat, IfNull, Sum
from pypika.functions import NullIf
from pypika.functions import Function

from crm_cakra.fcrm.doctype.crm_dashboard.crm_dashboard import create_default_manager_dashboard
from crm_cakra.utils import sales_user_only


# Custom function for TIMESTAMPDIFF (MySQL/MariaDB)
class TimestampDiff(Function):
	def __init__(self, unit, start, end, **kwargs):
		super().__init__("TIMESTAMPDIFF", unit, start, end, **kwargs)


# ============================================================
# Scope dashboard: mine / branch / all
#
# Tiap chart memfilter lewat `owner` (pembuat dokumen). Supaya tidak perlu menyunting
# puluhan query, scope diterjemahkan jadi DAFTAR USER, lalu chart memakai .isin(users).
# Scope "all" menghasilkan None = tanpa filter.
#
# Dipakai `owner`, BUKAN lead_owner/inquiry_owner: field itu kosong di 5905 dari 5909
# inquiry, sehingga scope "mine" dulu selalu nol. `owner` terisi 100% dan juga yang
# dipakai sistem permission, jadi dashboard dan hak akses kini sejalan.
#
# Cabang dibaca dari User.branch milik owner, bukan dari kolom branch_office dokumen
# (kosong di hampir semua dokumen).
# ============================================================
SCOPE_MINE = "mine"
SCOPE_BRANCH = "branch"
SCOPE_ALL = "all"

# ============================================================
# Tanggal bisnis, bukan `creation`.
#
# Data hasil import/sync punya `creation` = waktu import — di server semua dokumen
# "lahir" di bulan yang sama, sehingga filter periode dan chart bulanan menumpuk di
# satu bulan. Periode dashboard karena itu difilter dengan tanggal BISNIS:
#   CRM Inquiry   -> inquiry_date  (terisi 5.908/5.909; fallback creation)
#   CRM Quotation -> date          (fallback creation)
# ============================================================


def _inq_bizdate(Inquiry):
	"""Ekspresi query-builder: tanggal bisnis CRM Inquiry."""
	return Coalesce(Inquiry.inquiry_date, Date(Inquiry.creation))


def _qt_bizdate(Quotation):
	"""Ekspresi query-builder: tanggal bisnis CRM Quotation."""
	return Coalesce(Quotation.date, Date(Quotation.creation))


# Versi raw-SQL (alias tabel `i` = tabCRM Inquiry).
INQ_BIZDATE_SQL = "COALESCE(i.inquiry_date, DATE(i.creation))"

MANAGER_ROLES = {"Sales Manager", "Sales Master Manager", "System Manager"}


def _is_manager(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def _branch_users(branch: str) -> list[str]:
	return frappe.get_all("User", filters={"enabled": 1, "branch": branch}, pluck="name")


@frappe.whitelist()
def get_allowed_scopes():
	"""Scope yang boleh dipakai user ini, untuk switch di dashboard.

	Sales User tidak diberi 'all' (lintas cabang), konsisten dengan pembatasan
	Lead/Inquiry/Quotation. Scope 'branch' disembunyikan bila user belum punya branch,
	daripada menampilkan switch yang hasilnya selalu kosong.
	"""
	me = frappe.session.user
	scopes = [SCOPE_MINE]
	if frappe.db.get_value("User", me, "branch"):
		scopes.append(SCOPE_BRANCH)
	if _is_manager(me):
		if SCOPE_BRANCH not in scopes:
			scopes.append(SCOPE_BRANCH)
		scopes.append(SCOPE_ALL)
	return {"scopes": scopes, "default": SCOPE_MINE}


def _scope_users(scope: str | None, user: str | None = None, branch: str | None = None) -> list[str] | None:
	"""Terjemahkan scope jadi daftar user. None = semua user (tanpa filter).

	`user` — pemilih satu orang. Manager boleh memilih siapa pun (dashboard-nya
	memang untuk memantau tim; sebelumnya pilihan di luar scope diam-diam kembali
	ke data sendiri, sehingga memilih user lain terlihat "kosong"). Non-manager
	tetap hanya boleh dirinya sendiri.

	`branch` — filter cabang (User.branch pemilik dokumen). Manager boleh cabang
	mana pun; non-manager hanya mempersempit daftar user yang memang sudah boleh
	dilihatnya.
	"""
	me = frappe.session.user
	scope = scope or SCOPE_MINE
	manager = _is_manager(me)

	if scope == SCOPE_ALL:
		if not manager:
			frappe.throw(_("You are not permitted to view all branches."), frappe.PermissionError)
		allowed = None
	elif scope == SCOPE_BRANCH:
		my_branch = frappe.db.get_value("User", me, "branch")
		if not my_branch:
			# Tanpa branch, "branch" tidak punya arti -> jangan diam-diam melebar
			# jadi semua data; perlakukan sebagai diri sendiri.
			allowed = [me]
		else:
			# Diri sendiri selalu ikut, walau branch di User baru saja diubah.
			allowed = list({*_branch_users(my_branch), me})
	else:
		allowed = [me]

	if user:
		if manager:
			allowed = [user]
		elif allowed is None or user in allowed:
			allowed = [user]
		else:
			# User di luar hak akses -> jangan bocorkan datanya.
			allowed = [me]

	if branch:
		b_users = _branch_users(branch)
		if allowed is None:
			allowed = b_users
		else:
			allowed = [u for u in allowed if u in b_users]
		# Kombinasi yang tidak cocok (mis. user terpilih bukan anggota cabang itu)
		# menghasilkan KOSONG, bukan diam-diam melebar; [""] menjaga isin() tetap sah.
		allowed = allowed or [""]

	return allowed


@frappe.whitelist()
def reset_to_default():
	frappe.only_for("System Manager", True)
	create_default_manager_dashboard(force=True)


@frappe.whitelist()
@sales_user_only
def get_dashboard(
	from_date: str | None = None,
	to_date: str | None = None,
	user: str | None = None,
	scope: str | None = None,
	branch: str | None = None,
):
	"""
	Get the dashboard data for the CRM dashboard.
	"""

	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	users = _scope_users(scope, user, branch)

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
			l["data"] = method(from_date, to_date, users)
		else:
			l["data"] = None

	return layout


@frappe.whitelist()
@sales_user_only
def get_chart(
	name: str,
	type: str,
	from_date: str | None = None,
	to_date: str | None = None,
	user: str | None = None,
	scope: str | None = None,
	branch: str | None = None,
):
	"""
	Get number chart data for the dashboard.
	"""
	if not from_date or not to_date:
		from_date = frappe.utils.get_first_day(from_date or frappe.utils.nowdate())
		to_date = frappe.utils.get_last_day(to_date or frappe.utils.nowdate())

	users = _scope_users(scope, user, branch)

	method_name = f"get_{name}"
	if hasattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name):
		method = getattr(frappe.get_attr("crm_cakra.api.dashboard"), method_name)
		return method(from_date, to_date, users)
	else:
		return {"error": _("Invalid chart name")}


def get_total_leads(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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
	if users is not None:
		current_cond = current_cond & (Lead.owner.isin(users))

	# Build conditions for previous period
	prev_cond = (Lead.creation >= prev_from_date) & (Lead.creation < from_date)
	if users is not None:
		prev_cond = prev_cond & (Lead.owner.isin(users))

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


def get_ongoing_inquiries(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
	"""
	Get ongoing inquiry count for the dashboard, and also calculate average inquiry value for ongoing inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")
	bizdate = _inq_bizdate(Inquiry)

	# Build conditions for current period
	current_cond = bizdate.between(from_date, to_date) & (Status.type.notin(["Won", "Lost"]))
	if users is not None:
		current_cond = current_cond & (Inquiry.owner.isin(users))

	# Build conditions for previous period
	prev_cond = bizdate.between(prev_from_date, frappe.utils.add_days(from_date, -1)) & (
		Status.type.notin(["Won", "Lost"])
	)
	if users is not None:
		prev_cond = prev_cond & (Inquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""
	Get ongoing inquiry count for the dashboard, and also calculate average inquiry value for ongoing inquiries.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")
	bizdate = _inq_bizdate(Inquiry)

	# Build conditions for current period
	current_cond = bizdate.between(from_date, to_date) & (Status.type.notin(["Won", "Lost"]))
	if users is not None:
		current_cond = current_cond & (Inquiry.owner.isin(users))

	# Build conditions for previous period
	prev_cond = bizdate.between(prev_from_date, frappe.utils.add_days(from_date, -1)) & (
		Status.type.notin(["Won", "Lost"])
	)
	if users is not None:
		prev_cond = prev_cond & (Inquiry.owner.isin(users))

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


def get_won_inquiries(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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
	if users is not None:
		current_cond = current_cond & (Inquiry.owner.isin(users))

	# Build conditions for previous period
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < from_date) & (Status.type == "Won")
	if users is not None:
		prev_cond = prev_cond & (Inquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
	if users is not None:
		current_cond = current_cond & (Inquiry.owner.isin(users))

	# Build conditions for previous period
	prev_cond = (Inquiry.closed_date >= prev_from_date) & (Inquiry.closed_date < from_date) & (Status.type == "Won")
	if users is not None:
		prev_cond = prev_cond & (Inquiry.owner.isin(users))

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


def get_average_inquiry_value(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
	"""
	Get average inquiry value for the dashboard.
	"""
	diff = frappe.utils.date_diff(to_date, from_date)
	if diff == 0:
		diff = 1

	prev_from_date = frappe.utils.add_days(from_date, -diff)

	Inquiry = DocType("CRM Inquiry")
	Status = DocType("CRM Inquiry Status")
	bizdate = _inq_bizdate(Inquiry)

	# Build conditions for current period
	current_cond = bizdate.between(from_date, to_date) & (Status.type != "Lost")
	if users is not None:
		current_cond = current_cond & (Inquiry.owner.isin(users))

	# Build conditions for previous period
	prev_cond = bizdate.between(prev_from_date, frappe.utils.add_days(from_date, -1)) & (Status.type != "Lost")
	if users is not None:
		prev_cond = prev_cond & (Inquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
	if users is not None:
		base_cond = base_cond & (Inquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
	if users is not None:
		base_cond = base_cond & (Inquiry.owner.isin(users))

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


def get_sales_trend(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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

	if users is not None:
		leads_query = leads_query.where(Lead.owner.isin(users))

	leads_query = leads_query.groupby(Date(Lead.creation))

	# Build inquiries query — tanggal bisnis, bukan creation (lihat _inq_bizdate).
	inq_bizdate = _inq_bizdate(Inquiry)
	inquiries_query = (
		frappe.qb.from_(Inquiry)
		.join(Status)
		.on(Inquiry.status == Status.name)
		.select(
			inq_bizdate.as_("date"),
			frappe.qb.terms.ValueWrapper(0).as_("leads"),
			Count("*").as_("inquiries"),
			Sum(Case().when(Status.type == "Won", 1).else_(0)).as_("won_inquiries"),
		)
		.where(inq_bizdate.between(from_date, to_date))
	)

	if users is not None:
		inquiries_query = inquiries_query.where(Inquiry.owner.isin(users))

	inquiries_query = inquiries_query.groupby(inq_bizdate)

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


def get_forecasted_revenue(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

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


def get_funnel_conversion(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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

	if users is not None:
		# IN (...) dengan daftar, bukan "= %(user)s": scope branch/all bisa berisi
		# banyak user. Daftar kosong tetap dilewatkan supaya hasilnya nol, bukan semua.
		lead_conds += " AND owner IN %(users)s"
		inquiry_conds += " AND owner IN %(users)s"
		lead_filters["users"] = users or [""]
		inquiry_filters["users"] = users or [""]

	result = []

	# Get total leads using Query Builder
	CRMLead = DocType("CRM Lead")

	query = (
		frappe.qb.from_(CRMLead)
		.select(Count("*").as_("count"))
		.where(Date(CRMLead.creation).between(from_date, to_date))
	)

	if users is not None:
		query = query.where(CRMLead.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
		.where((_inq_bizdate(CRMInquiry).between(from_date, to_date)) & (CRMInquiryStatus.type.notin(["Lost"])))
		.groupby(CRMInquiry.status)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
		.where(_inq_bizdate(CRMInquiry).between(from_date, to_date))
		.groupby(CRMInquiry.status)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by stage"),
		"subtitle": _("Current pipeline distribution"),
		"categoryColumn": "stage",
		"valueColumn": "count",
	}


def get_lost_inquiry_reasons(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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
		.where((_inq_bizdate(CRMInquiry).between(from_date, to_date)) & (CRMInquiryStatus.type == "Lost"))
		.groupby(CRMInquiry.lost_reason)
		.having((CRMInquiry.lost_reason.isnotnull()) & (CRMInquiry.lost_reason != ""))
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

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


def get_leads_by_source(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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

	if users is not None:
		query = query.where(CRMLead.owner.isin(users))

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Leads by source"),
		"subtitle": _("Lead generation channel analysis"),
		"categoryColumn": "source",
		"valueColumn": "count",
	}


def get_inquiries_by_source(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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
		.where(_inq_bizdate(CRMInquiry).between(from_date, to_date))
		.groupby(CRMInquiry.source)
		.orderby(Count("*"), order=frappe.qb.desc)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

	result = query.run(as_dict=True)

	return {
		"data": result or [],
		"title": _("Inquiries by source"),
		"subtitle": _("Inquiry generation channel analysis"),
		"categoryColumn": "source",
		"valueColumn": "count",
	}


def get_inquiries_by_territory(from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None):
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
		.where(_inq_bizdate(CRMInquiry).between(from_date, to_date))
		.groupby(CRMInquiry.territory)
		.orderby(Count("*"), order=frappe.qb.desc)
		.orderby(
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)), order=frappe.qb.desc
		)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

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
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
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
		.on(User.name == CRMInquiry.owner)
		.select(
			IfNull(User.full_name, CRMInquiry.owner).as_("salesperson"),
			Count("*").as_("inquiries"),
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)).as_("value"),
		)
		.where(_inq_bizdate(CRMInquiry).between(from_date, to_date))
		.groupby(CRMInquiry.owner)
		.orderby(Count("*"), order=frappe.qb.desc)
		.orderby(
			Sum(Coalesce(CRMInquiry.inquiry_value, 0) * IfNull(CRMInquiry.exchange_rate, 1)), order=frappe.qb.desc
		)
	)

	if users is not None:
		query = query.where(CRMInquiry.owner.isin(users))

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

	Default sistem didahulukan: FCRM Settings.currency masih berisi bawaan Frappe
	(INR) sementara seluruh dokumen memakai IDR, sehingga angka uang di dashboard
	tampil dengan simbol yang keliru (Rp jadi tanda Rupee India).
	"""
	base_currency = (
		frappe.db.get_default("currency")
		or frappe.db.get_single_value("FCRM Settings", "currency")
		or "USD"
	)
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
			& (_inq_bizdate(CRMInquiry).between(from_date, to_date))
		)
		.groupby(CRMStatusChangeLog.to, TargetStatus.position)
		.orderby(TargetStatus.position)
	)

	# Filter pemilik mengikuti scope (mine/branch/all) yang dikirim lewat filters.
	if filters and filters.get("users") is not None:
		query = query.where(CRMInquiry.owner.isin(filters["users"]))

	result = query.run(as_dict=True)
	return result or []


# ============================================================
# Chart ekspedisi: Quotation, Estimation, Job service.
#
# CRM Quotation tidak punya field *_owner seperti Lead/Inquiry, jadi scope-nya
# memakai `owner` (pembuat dokumen).
# ============================================================
QUOTATION_STATES = ["Draft", "Sent", "Waiting", "Win", "Lose"]


def get_quotations_by_status(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Sebaran quotation per status, untuk melihat di mana pipeline menumpuk."""
	Quotation = DocType("CRM Quotation")

	query = (
		frappe.qb.from_(Quotation)
		.select(IfNull(Quotation.state, "Draft").as_("status"), Count("*").as_("count"))
		.where(
			_qt_bizdate(Quotation).between(from_date, to_date)
			& (Coalesce(Quotation.is_void, 0) == 0)
		)
		.groupby(Quotation.state)
	)
	if users is not None:
		query = query.where(Quotation.owner.isin(users))

	rows = {r["status"]: r["count"] for r in query.run(as_dict=True)}
	# Status tanpa data tetap ditampilkan sebagai 0, supaya bentuk chart tidak
	# berubah-ubah tiap periode dan "tidak ada yang Lose" terbaca jelas.
	data = [{"status": s, "count": rows.get(s, 0)} for s in QUOTATION_STATES]

	return {
		"data": data,
		"title": _("Quotations by status"),
		"subtitle": _("Where quotations are piling up"),
		"xAxis": {
			"title": _("Status"),
			"key": "status",
			"type": "category",
		},
		"yAxis": {
			"title": _("Quotations"),
		},
		"series": [
			{"name": "count", "type": "bar"},
		],
	}


def get_quotation_win_rate(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Win rate = Win / (Win + Lose). Quotation yang belum diputuskan tidak dihitung,
	supaya angkanya tidak tertekan hanya karena banyak yang masih berjalan."""
	Quotation = DocType("CRM Quotation")

	def decided(start, end):
		q = (
			frappe.qb.from_(Quotation)
			.select(
				Count(Case().when(Quotation.state == "Win", Quotation.name).else_(None)).as_("win"),
				Count(Case().when(Quotation.state.isin(["Win", "Lose"]), Quotation.name).else_(None)).as_(
					"decided"
				),
			)
			.where(
				Date(Quotation.modified).between(start, end)
				& (Coalesce(Quotation.is_void, 0) == 0)
			)
		)
		if users is not None:
			q = q.where(Quotation.owner.isin(users))
		r = q.run(as_dict=True)
		return (r[0].win or 0, r[0].decided or 0) if r else (0, 0)

	diff = frappe.utils.date_diff(to_date, from_date) or 1
	win, total = decided(from_date, to_date)
	prev_win, prev_total = decided(frappe.utils.add_days(from_date, -diff), from_date)

	rate = (win / total * 100) if total else 0
	prev_rate = (prev_win / prev_total * 100) if prev_total else 0

	return {
		"title": _("Quotation win rate"),
		"tooltip": _("Win / (Win + Lose). Quotations still in progress are excluded."),
		"value": round(rate, 1),
		"suffix": "%",
		"delta": round(rate - prev_rate, 1),
		"deltaSuffix": "%",
	}


def get_quotation_value_won(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Total nilai quotation yang menang."""
	Quotation = DocType("CRM Quotation")

	def total(start, end):
		q = (
			frappe.qb.from_(Quotation)
			.select(Coalesce(Sum(Quotation.net_total), 0).as_("total"))
			.where(
				Date(Quotation.modified).between(start, end)
				& (Quotation.state == "Win")
				& (Coalesce(Quotation.is_void, 0) == 0)
			)
		)
		if users is not None:
			q = q.where(Quotation.owner.isin(users))
		r = q.run(as_dict=True)
		return r[0].total or 0 if r else 0

	diff = frappe.utils.date_diff(to_date, from_date) or 1
	current = total(from_date, to_date)
	prev = total(frappe.utils.add_days(from_date, -diff), from_date)
	delta = ((current - prev) / prev * 100) if prev else 0

	return {
		"title": _("Won quotation value"),
		"tooltip": _("Total net value of quotations marked Win"),
		"value": current,
		"prefix": get_base_currency_symbol(),
		"delta": round(delta, 1),
		"deltaSuffix": "%",
	}


def get_open_quotations(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Quotation yang masih menunggu keputusan (Sent/Waiting) -- ini yang perlu dikejar.

	Seperti tabel outstanding, angka ini TIDAK dibatasi periode dashboard. Kalau
	dibatasi, memilih periode lampau membuat angkanya nol sementara tabel di
	sebelahnya tetap menampilkan barisnya -- angka membantah daftarnya sendiri.
	Void dikecualikan: quotation yang dibatalkan bukan lagi tanggungan.
	"""
	Quotation = DocType("CRM Quotation")

	q = (
		frappe.qb.from_(Quotation)
		.select(Count("*").as_("count"), Coalesce(Sum(Quotation.net_total), 0).as_("total"))
		.where(Quotation.state.isin(OUTSTANDING_QUOTATION_STATES) & (Coalesce(Quotation.is_void, 0) == 0))
	)
	if users is not None:
		q = q.where(Quotation.owner.isin(users))

	r = q.run(as_dict=True)
	count = r[0].count or 0 if r else 0
	total = r[0].total or 0 if r else 0

	return {
		"title": _("Open quotations"),
		"tooltip": _("Draft, Sent or Waiting -- not yet decided (all periods)"),
		"value": count,
		"suffix": _(" ({0} {1})").format(get_base_currency_symbol(), frappe.utils.fmt_money(total)),
	}


def get_inquiries_by_job_service(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Job service yang paling sering diminta -- di mana bisnis benar-benar berjalan."""
	Inquiry = DocType("CRM Inquiry")

	query = (
		frappe.qb.from_(Inquiry)
		.select(IfNull(Inquiry.job_service, "Empty").as_("job_service"), Count("*").as_("count"))
		.where(_inq_bizdate(Inquiry).between(from_date, to_date))
		.groupby(Inquiry.job_service)
		.orderby(Count("*"), order=frappe.qb.desc)
		.limit(10)
	)
	if users is not None:
		query = query.where(Inquiry.owner.isin(users))

	return {
		"data": query.run(as_dict=True) or [],
		"title": _("Top job services"),
		"subtitle": _("Most requested services"),
		"xAxis": {
			"title": _("Job service"),
			"key": "job_service",
			"type": "category",
		},
		"yAxis": {
			"title": _("Inquiries"),
		},
		"series": [
			{"name": "count", "type": "bar"},
		],
	}


# Jumlah baris yang ditarik ke tiap panel outstanding. Dibatasi supaya dashboard
# tetap ringan -- panel ini menampilkan yang TERBARU, bukan seluruh tunggakan.
OUTSTANDING_LIMIT = 15

# Status quotation yang dianggap masih menggantung. Draft ikut: quotation yang sudah
# dibuat tapi belum dikirim juga pekerjaan yang belum selesai.
# Dipakai bersama oleh tabel outstanding, angka "Open quotations", dan "Expiring in 7
# days" -- supaya angka tidak pernah membantah tabel di sebelahnya.
OUTSTANDING_QUOTATION_STATES = ["Draft", "Sent", "Waiting"]


def _user_full_names(emails):
	"""Map email -> full name untuk daftar user (satu query, bukan per baris)."""
	emails = [e for e in set(emails) if e]
	if not emails:
		return {}
	return dict(
		frappe.get_all("User", filters={"name": ["in", emails]}, fields=["name", "full_name"], as_list=True)
	)


def _assigned_names(assign_json, names):
	"""Render field _assign (JSON list email) jadi daftar nama yang terbaca."""
	try:
		assignees = json.loads(assign_json or "[]")
	except ValueError:
		assignees = []
	return ", ".join(names.get(a, a) for a in assignees) or "-"


def get_my_outstanding_quotations(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Daftar quotation yang sudah dikirim tapi belum dijawab customer.

	Sengaja TIDAK dibatasi rentang tanggal dashboard: quotation yang menggantung dari
	bulan lalu justru yang paling perlu dikejar, dan akan hilang kalau ikut difilter
	periode. 
	Void dikecualikan -- quotation yang dibatalkan bukan lagi tanggungan.
	Ditampilkan 15 yang TERBARU (angka "Open quotations" di sampingnya tetap menghitung
	SELURUH tunggakan, jadi selisihnya wajar bila tunggakan lebih dari 15).
	"""
	Quotation = DocType("CRM Quotation")
	Inquiry = DocType("CRM Inquiry")
	Owner = DocType("User")

	query = (
		frappe.qb.from_(Quotation)
		# Rute quotation = loading/unloading MILIKNYA SENDIRI (sama maknanya dengan
		# origin/destination di inquiry); fallback ke inquiry bila kosong. Branch
		# dibaca dari User.branch pemilik dokumen -- konsisten dengan scope.
		.left_join(Inquiry)
		.on(Inquiry.name == Quotation.inquiry)
		.left_join(Owner)
		.on(Owner.name == Quotation.owner)
		.select(
			Quotation.name,
			Quotation.state,
			Quotation.account_name,
			Quotation.net_total,
			Quotation.currency,
			Quotation.date,
			Quotation.validity_date,
			Quotation.owner,
			Quotation.inquiry.as_("inquiry_name"),
			Quotation._assign.as_("assign_json"),
			Owner.branch.as_("branch"),
			Owner.full_name.as_("owner_name"),
			Coalesce(NullIf(Quotation.loading, ""), Inquiry.origin).as_("loading"),
			Coalesce(NullIf(Quotation.unloading, ""), Inquiry.destination).as_("unloading"),
			Inquiry.business_unit.as_("business_unit"),
		)
		.where(Quotation.state.isin(OUTSTANDING_QUOTATION_STATES) & (Coalesce(Quotation.is_void, 0) == 0))
		.orderby(Quotation.creation, order=frappe.qb.desc)
		.limit(OUTSTANDING_LIMIT)
	)
	if users is not None:
		query = query.where(Quotation.owner.isin(users))

	today = frappe.utils.nowdate()
	raw = query.run(as_dict=True)
	# Nama assignee di-resolve sekali untuk semua baris.
	assignee_emails = []
	for r in raw:
		try:
			assignee_emails.extend(json.loads(r.assign_json or "[]"))
		except ValueError:
			pass
	names = _user_full_names(assignee_emails)

	# Type Inquiry = child table di inquiry (multi-select) -- diambil sekali jalan.
	inq_names = list({r.inquiry_name for r in raw if r.inquiry_name})
	type_map = {}
	if inq_names:
		for t in frappe.get_all(
			"CRM Inquiry Type Inquiry",
			filters={"parent": ["in", inq_names], "parenttype": "CRM Inquiry"},
			fields=["parent", "type"],
			order_by="parent, idx",
		):
			if t.type:
				type_map.setdefault(t.parent, []).append(t.type)

	rows = []
	for r in raw:
		rows.append(
			{
				"name": r.name,
				"status": r.state,
				"account": r.account_name or "-",
				"branch": r.branch or "-",
				"loading": (r.loading or "-").strip() or "-",
				"unloading": (r.unloading or "-").strip() or "-",
				"type_inquiry": ", ".join(type_map.get(r.inquiry_name, [])) or "-",
				"business_unit": " ".join((r.business_unit or "-").split()),
				"owner": r.owner_name or r.owner or "-",
				"assigned": _assigned_names(r.assign_json, names),
				"value": r.net_total or 0,
				"currency": r.currency or get_base_currency_symbol(),
				# Umur = sudah berapa lama menggantung. Sisa = berapa hari lagi hangus.
				"age_days": frappe.utils.date_diff(today, r.date) if r.date else None,
				"days_left": frappe.utils.date_diff(r.validity_date, today) if r.validity_date else None,
				"validity_date": r.validity_date,
			}
		)

	# Yang paling mendesak di atas: sisa masa berlaku paling sedikit dulu
	# (termasuk yang sudah lewat); tanpa validity date di bawah.
	rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] if r["days_left"] is not None else 0))

	return {
		"data": rows,
		"title": _("Outstanding quotations"),
		"subtitle": _("Draft, sent, or waiting -- not yet decided"),
		"route": "Quotation",
		"routeParam": "quotationId",
		"columns": [
			{"key": "name", "label": _("Quotation"), "type": "id"},
			{"key": "account", "label": _("Account"), "type": "truncate"},
			{"key": "branch", "label": _("Branch"), "type": "truncate"},
			{"key": "loading", "label": _("Loading"), "type": "truncate"},
			{"key": "unloading", "label": _("Unloading"), "type": "truncate"},
			{"key": "type_inquiry", "label": _("Type Inquiry"), "type": "truncate"},
			{"key": "business_unit", "label": _("Business Unit"), "type": "truncate"},
			{"key": "owner", "label": _("Owner"), "type": "truncate"},
			{"key": "assigned", "label": _("Assigned To"), "type": "truncate"},
			{"key": "status", "label": _("Status"), "type": "badge"},
			{"key": "value", "label": _("Value"), "type": "money", "align": "right"},
			{"key": "age_days", "label": _("Age"), "type": "days", "align": "right"},
			{"key": "days_left", "label": _("Expires"), "type": "expiry", "align": "right"},
		],
	}


def get_expiring_quotations(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Berapa quotation outstanding yang kadaluarsa dalam 7 hari ke depan."""
	Quotation = DocType("CRM Quotation")
	today = frappe.utils.nowdate()
	deadline = frappe.utils.add_days(today, 7)

	q = (
		frappe.qb.from_(Quotation)
		.select(Count("*").as_("count"), Coalesce(Sum(Quotation.net_total), 0).as_("total"))
		.where(
			Quotation.state.isin(OUTSTANDING_QUOTATION_STATES)
			& (Coalesce(Quotation.is_void, 0) == 0)
			& Quotation.validity_date.between(today, deadline)
		)
	)
	if users is not None:
		q = q.where(Quotation.owner.isin(users))

	r = q.run(as_dict=True)
	count = (r[0].count or 0) if r else 0
	total = (r[0].total or 0) if r else 0

	return {
		"title": _("Expiring in 7 days"),
		"tooltip": _("Outstanding quotations whose validity date falls within the next 7 days"),
		"value": count,
		"suffix": _(" ({0} {1})").format(get_base_currency_symbol(), frappe.utils.fmt_money(total)),
	}


# ============================================================
# Kategori Inquiry.
#
# Dipilih dari field yang BENAR-BENAR terisi (dicek di data, bukan diasumsikan):
#   job_service         99%   56 nilai  -> top 10
#   business_unit       86%    7 nilai  -> donut
#   transportation_mode 61%    9 nilai  -> donut
#   origin/destination  99%   ribuan nilai, teks bebas -> dinormalkan lalu top 10
#
# Field source/industry/territory/inquiry_value/expected_* sengaja TIDAK dipakai:
# semuanya kosong (0-2%), chart-nya cuma jadi kotak kosong.
# ============================================================
def _fill_scope(query, users, owner_field):
	return query.where(owner_field.isin(users)) if users is not None else query


def get_inquiries_by_business_unit(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Sebaran inquiry per lini bisnis (EMKL / ISO / FF / PCP / ...)."""
	Inquiry = DocType("CRM Inquiry")
	query = (
		frappe.qb.from_(Inquiry)
		.select(
			Coalesce(NullIf(Inquiry.business_unit, ""), "Tidak diisi").as_("business_unit"),
			Count("*").as_("count"),
		)
		.where(_inq_bizdate(Inquiry).between(from_date, to_date))
		.groupby(Inquiry.business_unit)
		.orderby(Count("*"), order=frappe.qb.desc)
	)
	query = _fill_scope(query, users, Inquiry.owner)
	return {
		"data": query.run(as_dict=True) or [],
		"title": _("Inquiries by business unit"),
		"subtitle": _("Which service line the work comes from"),
		"categoryColumn": "business_unit",
		"valueColumn": "count",
	}


def get_inquiries_by_transportation_mode(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Sebaran inquiry per moda angkutan (Ocean / Inland Truck / Railway / Air)."""
	Inquiry = DocType("CRM Inquiry")
	query = (
		frappe.qb.from_(Inquiry)
		.select(
			Coalesce(NullIf(Inquiry.transportation_mode, ""), "Tidak diisi").as_("mode"),
			Count("*").as_("count"),
		)
		.where(_inq_bizdate(Inquiry).between(from_date, to_date))
		.groupby(Inquiry.transportation_mode)
		.orderby(Count("*"), order=frappe.qb.desc)
	)
	query = _fill_scope(query, users, Inquiry.owner)
	return {
		"data": query.run(as_dict=True) or [],
		"title": _("Inquiries by transportation mode"),
		"subtitle": _("Ocean, inland truck, railway, air"),
		"categoryColumn": "mode",
		"valueColumn": "count",
	}


def get_top_routes(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Rute (asal -> tujuan) yang paling sering diminta.

	origin/destination adalah teks bebas dan ditulis tidak seragam ("MEDAN", "Medan",
	"JAKARTA, INDONESIA"), sehingga dinormalkan (UPPER + TRIM) dulu; tanpa itu satu
	rute yang sama akan terpecah jadi beberapa baris.
	"""
	conds = [f"{INQ_BIZDATE_SQL} BETWEEN %(from_date)s AND %(to_date)s", "IFNULL(i.origin,'') != ''", "IFNULL(i.destination,'') != ''"]
	params = {"from_date": from_date, "to_date": to_date}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT CONCAT(UPPER(TRIM(i.origin)), ' -> ', UPPER(TRIM(i.destination))) AS route,
		       COUNT(*) AS count
		FROM `tabCRM Inquiry` i
		WHERE {" AND ".join(conds)}
		GROUP BY route
		ORDER BY count DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)
	return {
		"data": rows or [],
		"title": _("Top routes"),
		"subtitle": _("Most requested origin to destination"),
		"xAxis": {
			"title": _("Route"),
			"key": "route",
			"type": "category",
		},
		"yAxis": {
			"title": _("Inquiries"),
		},
		"series": [
			{"name": "count", "type": "bar"},
		],
	}


def get_win_rate_by_business_unit(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Win rate per lini bisnis: mana yang benar-benar menghasilkan, bukan sekadar ramai.

	Hanya inquiry yang sudah diputuskan (Won/Lost) yang dihitung; yang masih berjalan
	tidak menekan angkanya.
	"""
	conds = [f"{INQ_BIZDATE_SQL} BETWEEN %(from_date)s AND %(to_date)s", "s.type IN ('Won','Lost')"]
	params = {"from_date": from_date, "to_date": to_date}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(i.business_unit,''), 'Tidak diisi') AS business_unit,
		       ROUND(SUM(s.type = 'Won') / COUNT(*) * 100, 1) AS win_rate
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabCRM Inquiry Status` s ON s.name = i.status
		WHERE {" AND ".join(conds)}
		GROUP BY business_unit
		HAVING COUNT(*) >= 5
		ORDER BY win_rate DESC
		""",
		params,
		as_dict=True,
	)
	return {
		"data": rows or [],
		"title": _("Win rate by business unit"),
		"subtitle": _("Decided inquiries only (min. 5)"),
		"xAxis": {
			"title": _("Business unit"),
			"key": "business_unit",
			"type": "category",
		},
		"yAxis": {
			"title": _("Win rate (%)"),
		},
		"series": [
			{"name": "win_rate", "type": "bar"},
		],
	}


# ============================================================
# Tren per cabang.
#
# Cabang dibaca dari User.branch milik `owner` dokumen (bukan kolom branch_office,
# yang kosong di hampir semua dokumen). Ini juga konsisten dengan scope: scope
# menyaring daftar user, cabang mengelompokkan user yang sama.
#
# Hanya inquiry yang "hidup" yang dihitung -- sedang ditawar (Ongoing) atau menang
# (Won). Yang Lost/Open belum jadi pekerjaan nyata dan hanya menggemukkan grafik.
# ============================================================
TREND_STATUS_TYPES = ("Ongoing", "Won")

TREND_DIMENSIONS = {
	"branch": ("COALESCE(NULLIF(u.branch,''), 'Tanpa cabang')", _("Branch")),
	"business_unit": ("COALESCE(NULLIF(i.business_unit,''), 'Tidak diisi')", _("Business unit")),
	"transportation_mode": ("COALESCE(NULLIF(i.transportation_mode,''), 'Tidak diisi')", _("Transportation mode")),
	"job_service": ("COALESCE(NULLIF(i.job_service,''), 'Tidak diisi')", _("Job service")),
}


def _inquiry_trend(dimension: str, from_date, to_date, users, title, subtitle):
	"""Tren bulanan jumlah inquiry, dipecah per dimensi (cabang / kategori).

	Hasil dibentuk lebar (satu kolom per nilai dimensi) supaya AxisChart bisa
	menggambar satu garis per cabang/kategori dalam satu grafik.

	Bulan dihitung dari INQUIRY_DATE (tanggal bisnis), bukan `creation`: data hasil
	import/sync punya `creation` = tanggal import, sehingga kalau pakai creation
	seluruh riwayat menumpuk di satu bulan (di server semua jadi bulan import-nya).
	Inquiry tanpa inquiry_date (segelintir) jatuh ke tanggal creation-nya.
	"""
	expr, _label = TREND_DIMENSIONS[dimension]
	date_expr = INQ_BIZDATE_SQL

	conds = [
		f"{date_expr} BETWEEN %(from_date)s AND %(to_date)s",
		"s.type IN %(types)s",
	]
	params = {
		"from_date": from_date,
		"to_date": to_date,
		"types": TREND_STATUS_TYPES,
	}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT DATE_FORMAT({date_expr}, '%%b %%Y') AS period,
		       DATE_FORMAT({date_expr}, '%%Y-%%m') AS sort_key,
		       {expr} AS series,
		       COUNT(*) AS count
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabCRM Inquiry Status` s ON s.name = i.status
		LEFT JOIN `tabUser` u ON u.name = i.owner
		WHERE {" AND ".join(conds)}
		GROUP BY sort_key, period, series
		ORDER BY sort_key
		""",
		params,
		as_dict=True,
	)

	# Ambil 6 seri terbesar; sisanya digabung jadi "Lainnya" supaya grafik tetap terbaca.
	# Nama seri jadi KEY di tiap baris data dan label di legenda. business_unit
	# aslinya panjang & berspasi ganda ("EMKL  (TRUCKING DOMESTIK NON ISOTANK)"),
	# jadi dirapikan: ambil kode di depan kurung, rapatkan spasi, potong bila panjang.
	def clean(name: str) -> str:
		name = " ".join(str(name).split())
		if "(" in name:
			name = name.split("(", 1)[0].strip() or name
		return name[:28]

	for r in rows:
		r.series = clean(r.series)

	totals = {}
	for r in rows:
		totals[r.series] = totals.get(r.series, 0) + r.count
	top = [s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:6]]

	periods, buckets = [], {}
	for r in rows:
		if r.period not in buckets:
			buckets[r.period] = {"period": r.period}
			periods.append(r.period)
		key = r.series if r.series in top else _("Lainnya")
		buckets[r.period][key] = buckets[r.period].get(key, 0) + r.count

	series_names = top + ([_("Lainnya")] if len(totals) > len(top) else [])
	data = []
	for p in periods:
		row = buckets[p]
		# Titik kosong diisi 0, kalau tidak garisnya putus di bulan yang tidak ada datanya.
		for s in series_names:
			row.setdefault(s, 0)
		data.append(row)

	return {
		"data": data,
		"title": title,
		"subtitle": subtitle,
		"xAxis": {
			"title": _("Period"),
			"key": "period",
			"type": "category",
		},
		"yAxis": {"title": _("Inquiries")},
		"series": [{"name": s, "type": "line"} for s in series_names],
	}


def get_inquiry_trend_by_branch(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	return _inquiry_trend(
		"branch", from_date, to_date, users,
		_("Inquiry trend by branch"),
		_("Ongoing and won inquiries per month"),
	)


def get_inquiry_trend_by_business_unit(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	return _inquiry_trend(
		"business_unit", from_date, to_date, users,
		_("Inquiry trend by business unit"),
		_("Which service line is growing"),
	)


def get_inquiry_trend_by_transportation_mode(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	return _inquiry_trend(
		"transportation_mode", from_date, to_date, users,
		_("Inquiry trend by transportation mode"),
		_("Ocean, inland truck, railway, air"),
	)


def get_inquiry_trend_by_job_service(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	return _inquiry_trend(
		"job_service", from_date, to_date, users,
		_("Inquiry trend by job service"),
		_("Top services over time"),
	)


def get_my_outstanding_inquiries(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Inquiry yang belum dibuatkan quotation dan belum selesai -- dibuat tapi tidak digarap.

	Yang sudah Won/Lost dikecualikan: itu bukan pekerjaan menggantung, dan di data ini
	jumlahnya besar (1628 Won + 871 Lost tanpa quotation), sehingga kalau ikut dihitung
	panel ini jadi tumpukan riwayat, bukan daftar tugas.

	Seperti panel quotation, periode dashboard SENGAJA diabaikan: inquiry yang mangkrak
	sejak bulan lalu justru yang paling perlu ditengok, dan akan hilang kalau difilter
	periode. Ditampilkan 15 yang TERBARU.
	"""
	conds = [
		"i.name NOT IN (SELECT inquiry FROM `tabCRM Quotation` WHERE inquiry IS NOT NULL)",
		"COALESCE(s.type, '') NOT IN ('Won', 'Lost')",
	]
	params = {"row_limit": OUTSTANDING_LIMIT}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT i.name, i.status, i.organization, i.job_service, i.inquiry_date, i.creation,
		       i.owner, i._assign AS assign_json,
		       i.transportation_mode, i.business_unit,
		       u.branch, u.full_name AS owner_name,
		       (SELECT GROUP_CONCAT(t.type SEPARATOR ', ')
		          FROM `tabCRM Inquiry Type Inquiry` t
		         WHERE t.parent = i.name AND t.parenttype = 'CRM Inquiry') AS type_inquiry
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabCRM Inquiry Status` s ON s.name = i.status
		LEFT JOIN `tabUser` u ON u.name = i.owner
		WHERE {" AND ".join(conds)}
		ORDER BY i.creation DESC
		LIMIT %(row_limit)s
		""",
		params,
		as_dict=True,
	)

	# Nama assignee di-resolve sekali untuk semua baris.
	assignee_emails = []
	for r in rows:
		try:
			assignee_emails.extend(json.loads(r.assign_json or "[]"))
		except ValueError:
			pass
	names = _user_full_names(assignee_emails)

	today = frappe.utils.nowdate()
	data = []
	for r in rows:
		# Umur dihitung dari `creation`, bukan inquiry_date: yang terakhir diketik user
		# dan bisa salah tahun, menghasilkan umur negatif yang tak masuk akal di UI.
		started = r.creation.date() if r.creation else None
		data.append(
			{
				"name": r.name,
				"account": r.organization or "-",
				"branch": r.branch or "-",
				"type_inquiry": r.type_inquiry or "-",
				"transportation_mode": r.transportation_mode or "-",
				"business_unit": " ".join((r.business_unit or "-").split()),
				"owner": r.owner_name or r.owner or "-",
				"assigned": _assigned_names(r.assign_json, names),
				"status": r.status or "-",
				"job_service": r.job_service or "-",
				"age_days": frappe.utils.date_diff(today, started) if started else None,
			}
		)

	return {
		"data": data,
		"title": _("Outstanding inquiries"),
		"subtitle": _("No quotation yet -- created but not worked on"),
		"route": "Inquiry",
		"routeParam": "inquiryId",
		"columns": [
			{"key": "name", "label": _("Inquiry"), "type": "id"},
			{"key": "account", "label": _("Account"), "type": "truncate"},
			{"key": "branch", "label": _("Branch"), "type": "truncate"},
			{"key": "type_inquiry", "label": _("Type Inquiry"), "type": "truncate"},
			{"key": "transportation_mode", "label": _("Mode"), "type": "truncate"},
			{"key": "business_unit", "label": _("Business Unit"), "type": "truncate"},
			{"key": "owner", "label": _("Owner"), "type": "truncate"},
			{"key": "assigned", "label": _("Assigned To"), "type": "truncate"},
			{"key": "status", "label": _("Status"), "type": "badge"},
			{"key": "job_service", "label": _("Job Service"), "type": "truncate"},
			{"key": "age_days", "label": _("Age"), "type": "days", "align": "right"},
		],
	}


def _top_chart(field, title, subtitle, users, from_date, to_date, x_label, limit=10):
	"""Top-N nilai sebuah field Inquiry, sebagai bar chart."""
	Inquiry = DocType("CRM Inquiry")
	query = (
		frappe.qb.from_(Inquiry)
		.select(
			Coalesce(NullIf(Inquiry[field], ""), "Tidak diisi").as_("label"),
			Count("*").as_("count"),
		)
		.where(_inq_bizdate(Inquiry).between(from_date, to_date))
		.groupby(Inquiry[field])
		.orderby(Count("*"), order=frappe.qb.desc)
		.limit(limit)
	)
	if users is not None:
		query = query.where(Inquiry.owner.isin(users))

	return {
		"data": query.run(as_dict=True) or [],
		"title": title,
		"subtitle": subtitle,
		"xAxis": {"title": _(x_label), "key": "label", "type": "category"},
		"yAxis": {"title": _("Inquiries")},
		"series": [{"name": "count", "type": "bar"}],
	}


def get_top_business_unit(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	return _top_chart(
		"business_unit", _("Top business unit"), _("Most active service lines"),
		users, from_date, to_date, "Business unit",
	)


def get_top_type_of_inquiry(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Top Type of Inquiry.

	type_inquiry adalah Table MultiSelect (child: CRM Inquiry Type Inquiry), jadi satu
	inquiry bisa punya beberapa tipe -- dihitung per baris anak, bukan per inquiry.

	Catatan: saat ini hampir seluruh inquiry belum mengisi field ini (4 dari 5909), jadi
	chart akan tampak kosong sampai sales mulai mengisinya. Itu keadaan data, bukan bug.
	"""
	conds = ["1=1"]
	params = {"from_date": from_date, "to_date": to_date}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT t.type AS label, COUNT(*) AS count
		FROM `tabCRM Inquiry Type Inquiry` t
		JOIN `tabCRM Inquiry` i ON i.name = t.parent
		WHERE t.parenttype = 'CRM Inquiry'
		  AND t.type IS NOT NULL AND t.type != ''
		  AND {INQ_BIZDATE_SQL} BETWEEN %(from_date)s AND %(to_date)s
		  AND {" AND ".join(conds)}
		GROUP BY t.type
		ORDER BY count DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)
	return {
		"data": rows or [],
		"title": _("Top type of inquiry"),
		"subtitle": _("Most requested inquiry types"),
		"xAxis": {"title": _("Type of inquiry"), "key": "label", "type": "category"},
		"yAxis": {"title": _("Inquiries")},
		"series": [{"name": "count", "type": "bar"}],
	}


def get_top_accounts(
	from_date: str | None = None, to_date: str | None = None, users: list[str] | None = None
):
	"""Customer dengan inquiry terbanyak, beserta berapa yang sudah menang.

	Dua deret: jumlah inquiry dan jumlah yang Won -- jadi terlihat bukan cuma siapa yang
	paling ramai, tapi siapa yang benar-benar menghasilkan.
	"""
	conds = ["i.organization IS NOT NULL", "i.organization != ''"]
	params = {"from_date": from_date, "to_date": to_date}
	if users is not None:
		conds.append("i.owner IN %(users)s")
		params["users"] = users or [""]

	rows = frappe.db.sql(
		f"""
		SELECT i.organization AS account,
		       COUNT(*) AS inquiries,
		       SUM(s.type = 'Won') AS won
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabCRM Inquiry Status` s ON s.name = i.status
		WHERE {INQ_BIZDATE_SQL} BETWEEN %(from_date)s AND %(to_date)s
		  AND {" AND ".join(conds)}
		GROUP BY i.organization
		ORDER BY inquiries DESC
		LIMIT 10
		""",
		params,
		as_dict=True,
	)
	# Nama PT panjang -- dipotong supaya sumbu X tetap terbaca.
	for r in rows:
		r["account"] = (r["account"] or "")[:28]
		r["won"] = int(r["won"] or 0)

	return {
		"data": rows or [],
		"title": _("Top accounts"),
		"subtitle": _("Customers with the most inquiries, and how many were won"),
		"xAxis": {"title": _("Account"), "key": "account", "type": "category"},
		"yAxis": {"title": _("Inquiries")},
		"series": [
			{"name": "inquiries", "type": "bar"},
			{"name": "won", "type": "bar"},
		],
	}

# Copyright (c) 2026, Cakra Mandiri Indonesia
"""Report Expense Note — satu report, empat bentuk lewat filter `view`.

Detail      : satu baris per Expense Note Item (mata uang dokumen).
Summary     : agregat per dimensi pilihan (mata uang perusahaan).
Outstanding : EN validated yang belum lunas + aging (mata uang perusahaan).
Per Job     : rekap biaya per Shipping List / Packing List (mata uang perusahaan).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

GROUP_BY = {
	"Supplier": "en.vendor",
	"Expense Class": "i.expense_class",
	"Expense Note Type": "en.expense_note_type",
	"Month": "date_format(en.date, '%%Y-%%m')",
	"Branch Office": "en.branch_office",
	"Cost Center": "en.cost_center",
	"Expense Account": "i.expense_account",
}

STATUS_SQL = {
	"Draft": "en.validated = 0 and en.void = 0",
	"Validated": "en.validated = 1 and coalesce(pay.paid, 0) = 0 and en.closed = 0 and en.void = 0",
	"Half Paid": "en.validated = 1 and coalesce(pay.paid, 0) > 0 and en.void = 0 and en.paid = 0",
	"Paid": "en.paid = 1 and en.void = 0",
	"Closed": "en.closed = 1",
	"Void": "en.void = 1",
}

# Alokasi pembayaran per Expense Note: Payment Entry Reference yang menunjuk EN lewat
# custom_expense_note. Hanya PV SUBMITTED yang dihitung — draft belum uang keluar.
# Satu EN boleh ditarik banyak PV, karena itu SUM.
PAY_JOIN = """
	left join (
		select custom_expense_note as en, sum(allocated_amount) as paid
		from `tabPayment Entry Reference`
		where docstatus = 1 and ifnull(custom_expense_note, '') != ''
		group by custom_expense_note
	) pay on pay.en = en.name
"""

# Net per baris item (mata uang dokumen) dan porsi pembayaran yang jatuh ke baris itu.
# Pembayaran melekat di EN (header), jadi dibagi PRO RATA ke tiap baris menurut porsi
# net-nya — kalau tidak, angka Paid akan berlipat sebanyak jumlah baris di kolom Total.
ITEM_NET = "(i.amount - i.discount + i.tax - i.pph + i.materai)"
ITEM_PAID = "(coalesce(pay.paid, 0) * {net} / nullif(en.net_total, 0))".format(net=ITEM_NET)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.get("view") or "Detail"
	if view == "Summary":
		return _summary(filters)
	if view == "Outstanding":
		return _outstanding(filters)
	if view == "Per Job":
		return _per_job(filters)
	return _detail(filters)


# ---- shared -----------------------------------------------------------------


def _conditions(filters, item_level=True):
	c = []
	if filters.get("company"):
		c.append("en.company = %(company)s")
	if filters.get("from_date"):
		c.append("en.date >= %(from_date)s")
	if filters.get("to_date"):
		c.append("en.date <= %(to_date)s")
	if filters.get("vendor"):
		c.append("en.vendor = %(vendor)s")
	if filters.get("expense_note_type"):
		c.append("en.expense_note_type = %(expense_note_type)s")
	if filters.get("branch_office"):
		c.append("en.branch_office = %(branch_office)s")
	if filters.get("cost_center"):
		c.append("en.cost_center = %(cost_center)s")
	if filters.get("shipping_list"):
		c.append("en.shipping_list = %(shipping_list)s")
	if item_level:
		if filters.get("expense_class"):
			c.append("i.expense_class = %(expense_class)s")
		if filters.get("packing_list"):
			c.append("(en.packing_list = %(packing_list)s or i.packing_list = %(packing_list)s)")
	elif filters.get("packing_list"):
		c.append("en.packing_list = %(packing_list)s")
	if filters.get("status"):
		c.append(STATUS_SQL[filters.status])
	elif not filters.get("include_void"):
		c.append("en.void = 0")
	return (" and " + " and ".join(c)) if c else ""


def _net(row):
	return flt(row.amount) - flt(row.discount) + flt(row.tax) - flt(row.pph) + flt(row.materai)


def _status(row):
	"""Status EN, termasuk yang datang dari PV: lunas penuh -> Paid, sebagian -> Half Paid.

	`en_paid` = total alokasi PV submitted (mata uang perusahaan), `net_base` = net EN
	dalam mata uang perusahaan. Flag `paid` di dokumen tetap menang supaya pelunasan
	yang ditandai manual tidak turun jadi Half Paid.
	"""
	if row.void:
		return "Void"
	if row.closed:
		return "Closed"
	paid = flt(row.get("en_paid"))
	net_base = flt(row.get("net_base"))
	if row.paid or (paid and net_base and paid >= net_base - 0.005):
		return "Paid"
	if paid > 0:
		return "Half Paid"
	if row.validated:
		return "Validated"
	return "Draft"


def _bucket(age):
	"""Umur hutang -> kolom aging. Belum jatuh tempo (age negatif) ikut 0-30."""
	if age <= 30:
		return "b_0_30"
	if age <= 60:
		return "b_31_60"
	if age <= 90:
		return "b_61_90"
	return "b_90_plus"


def _money(fieldname, label, width=120, currency_field=None):
	col = {
		"fieldname": fieldname,
		"label": _(label),
		"fieldtype": "Currency",
		"width": width,
	}
	if currency_field:
		col["options"] = currency_field
	return col


# ---- Detail -----------------------------------------------------------------


def _detail(filters):
	rows = frappe.db.sql(
		"""
		select
			en.name, en.date, en.expense_note_type, en.vendor, sup.supplier_name,
			en.ref, en.currency, en.conversion_rate, en.shipping_list,
			coalesce(i.packing_list, en.packing_list) as packing_list,
			en.branch_office, en.cost_center, en.invoice_no, en.payment_no,
			en.validated, en.paid, en.closed, en.void, en.expected_date,
			i.expense_class, i.expense_account, i.container_no, i.description,
			i.qty, i.uom, i.price, i.amount, i.tax, i.pph, i.discount, i.materai,
			coalesce(pay.paid, 0) as en_paid,
			en.net_total * coalesce(en.conversion_rate, 1) as net_base,
			{paid} / coalesce(en.conversion_rate, 1) as paid_amount
		from `tabExpense Note` en
		inner join `tabExpense Note Item` i on i.parent = en.name
		left join `tabSupplier` sup on sup.name = en.vendor
		{pay_join}
		where 1 = 1 {cond}
		order by en.date desc, en.name, i.idx
		""".format(paid=ITEM_PAID, pay_join=PAY_JOIN, cond=_conditions(filters)),
		filters,
		as_dict=True,
	)
	for r in rows:
		r.net = _net(r)
		r.status = _status(r)
		r.unpaid = r.net - flt(r.paid_amount)

	columns = [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{
			"fieldname": "name",
			"label": _("Expense Note"),
			"fieldtype": "Link",
			"options": "Expense Note",
			"width": 170,
		},
		{
			"fieldname": "expense_note_type",
			"label": _("Type"),
			"fieldtype": "Link",
			"options": "Expense Note Type",
			"width": 120,
		},
		{
			"fieldname": "vendor",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 140,
		},
		{"fieldname": "supplier_name", "label": _("Supplier Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "ref", "label": _("External Ref"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "expense_class",
			"label": _("Expense Class"),
			"fieldtype": "Link",
			"options": "Expense Class",
			"width": 150,
		},
		{
			"fieldname": "expense_account",
			"label": _("Expense Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 200},
		{"fieldname": "container_no", "label": _("Container"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "shipping_list",
			"label": _("Shipping List"),
			"fieldtype": "Link",
			"options": "Shipping List",
			"width": 140,
		},
		{
			"fieldname": "packing_list",
			"label": _("Packing List"),
			"fieldtype": "Link",
			"options": "Packing List",
			"width": 140,
		},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 70},
		_money("price", "Price", 120, "currency"),
		_money("amount", "Amount", 130, "currency"),
		_money("discount", "Discount", 100, "currency"),
		_money("tax", "PPN", 100, "currency"),
		_money("pph", "PPh", 100, "currency"),
		_money("materai", "Materai", 100, "currency"),
		_money("net", "Net", 130, "currency"),
		_money("paid_amount", "Paid", 130, "currency"),
		_money("unpaid", "Unpaid", 130, "currency"),
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 80,
		},
		{"fieldname": "conversion_rate", "label": _("Exchange Rate"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "invoice_no", "label": _("Invoice"), "fieldtype": "Data", "width": 130},
		{"fieldname": "payment_no", "label": _("Payment"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 150,
		},
		{
			"fieldname": "branch_office",
			"label": _("Branch"),
			"fieldtype": "Link",
			"options": "CMI Office",
			"width": 110,
		},
	]
	return columns, rows


# ---- Summary ----------------------------------------------------------------


def _summary(filters):
	dimension = filters.get("group_by") or "Supplier"
	expr = GROUP_BY.get(dimension) or GROUP_BY["Supplier"]
	rows = frappe.db.sql(
		"""
		select
			{expr} as grp,
			count(distinct en.name) as notes,
			sum(i.amount * coalesce(en.conversion_rate, 1)) as amount,
			sum(i.discount * coalesce(en.conversion_rate, 1)) as discount,
			sum(i.tax * coalesce(en.conversion_rate, 1)) as tax,
			sum(i.pph * coalesce(en.conversion_rate, 1)) as pph,
			sum(i.materai * coalesce(en.conversion_rate, 1)) as materai,
			sum({paid}) as paid_amount
		from `tabExpense Note` en
		inner join `tabExpense Note Item` i on i.parent = en.name
		{pay_join}
		where 1 = 1 {cond}
		group by grp
		order by amount desc
		""".format(expr=expr, paid=ITEM_PAID, pay_join=PAY_JOIN, cond=_conditions(filters)),
		filters,
		as_dict=True,
	)
	for r in rows:
		r.net = _net(r)
		r.unpaid = r.net - flt(r.paid_amount)

	fieldtype, options = {
		"Supplier": ("Link", "Supplier"),
		"Expense Class": ("Link", "Expense Class"),
		"Expense Note Type": ("Link", "Expense Note Type"),
		"Branch Office": ("Link", "CMI Office"),
		"Cost Center": ("Link", "Cost Center"),
		"Expense Account": ("Link", "Account"),
	}.get(dimension, ("Data", None))

	columns = [
		{
			"fieldname": "grp",
			"label": _(dimension),
			"fieldtype": fieldtype,
			"options": options,
			"width": 220,
		},
		{"fieldname": "notes", "label": _("Notes"), "fieldtype": "Int", "width": 80},
		_money("amount", "Amount", 140),
		_money("discount", "Discount", 120),
		_money("tax", "PPN", 120),
		_money("pph", "PPh", 120),
		_money("materai", "Materai", 110),
		_money("net", "Net", 150),
		_money("paid_amount", "Paid", 140),
		_money("unpaid", "Unpaid", 140),
	]
	return columns, rows


# ---- Outstanding / aging ----------------------------------------------------


def _outstanding(filters):
	rows = frappe.db.sql(
		"""
		select
			en.name, en.date, en.expected_date, en.vendor, sup.supplier_name,
			en.expense_note_type, en.ref, en.terms, en.payment_status,
			en.branch_office, en.cost_center, en.expense_classes,
			en.net_total * coalesce(en.conversion_rate, 1) as net,
			coalesce(pay.paid, 0) as paid_amount
		from `tabExpense Note` en
		left join `tabSupplier` sup on sup.name = en.vendor
		{pay_join}
		where en.validated = 1 and en.void = 0 and en.closed = 0 {cond}
		order by en.vendor, en.date
		""".format(pay_join=PAY_JOIN, cond=_conditions(filters, item_level=False)),
		filters,
		as_dict=True,
	)
	if not rows:
		return _outstanding_columns(), []

	# ponytail: allocated_amount dipakai apa adanya (mata uang perusahaan), tanpa
	# konversi kurs PV. Tambahkan kalau nanti ada PV valas menarik EN valas.
	# Umur dihitung dari hari ini, bukan dari `to_date` — kolom Paid memang alokasi
	# pembayaran sampai sekarang, jadi aging "as of" tanggal lampau cuma setengah benar.
	today = getdate(nowdate())
	out = []
	for r in rows:
		r.outstanding = flt(r.net) - flt(r.paid_amount)
		if r.outstanding <= 0.005:
			continue
		r.status = "Half Paid" if flt(r.paid_amount) else "Validated"
		r.age = (today - getdate(r.expected_date or r.date)).days
		r[_bucket(r.age)] = r.outstanding
		out.append(r)
	return _outstanding_columns(), out


def _outstanding_columns():
	return [
		{
			"fieldname": "vendor",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 140,
		},
		{"fieldname": "supplier_name", "label": _("Supplier Name"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "name",
			"label": _("Expense Note"),
			"fieldtype": "Link",
			"options": "Expense Note",
			"width": 170,
		},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "expected_date", "label": _("Due Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "age", "label": _("Age (Days)"), "fieldtype": "Int", "width": 90},
		_money("net", "Net Total", 130),
		_money("paid_amount", "Paid", 120),
		_money("outstanding", "Outstanding", 140),
		_money("b_0_30", "0-30", 110),
		_money("b_31_60", "31-60", 110),
		_money("b_61_90", "61-90", 110),
		_money("b_90_plus", "90+", 110),
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "payment_status", "label": _("Payment Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "expense_classes", "label": _("Expense Class"), "fieldtype": "Data", "width": 220},
		{"fieldname": "ref", "label": _("External Ref"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "branch_office",
			"label": _("Branch"),
			"fieldtype": "Link",
			"options": "CMI Office",
			"width": 110,
		},
	]


# ---- Per Job ----------------------------------------------------------------


def _per_job(filters):
	rows = frappe.db.sql(
		"""
		select
			coalesce(en.shipping_list, '') as shipping_list,
			coalesce(en.packing_list, i.packing_list, '') as packing_list,
			count(distinct en.name) as notes,
			count(distinct nullif(i.container_no, '')) as containers,
			count(distinct en.vendor) as vendors,
			sum(i.amount * coalesce(en.conversion_rate, 1)) as amount,
			sum(i.discount * coalesce(en.conversion_rate, 1)) as discount,
			sum(i.tax * coalesce(en.conversion_rate, 1)) as tax,
			sum(i.pph * coalesce(en.conversion_rate, 1)) as pph,
			sum(i.materai * coalesce(en.conversion_rate, 1)) as materai,
			sum({paid}) as paid_amount
		from `tabExpense Note` en
		inner join `tabExpense Note Item` i on i.parent = en.name
		{pay_join}
		where 1 = 1 {cond}
		group by shipping_list, packing_list
		order by amount desc
		""".format(paid=ITEM_PAID, pay_join=PAY_JOIN, cond=_conditions(filters)),
		filters,
		as_dict=True,
	)
	for r in rows:
		r.net = _net(r)
		r.unpaid = r.net - flt(r.paid_amount)
		r.per_container = flt(r.net) / r.containers if r.containers else 0

	columns = [
		{
			"fieldname": "shipping_list",
			"label": _("Shipping List"),
			"fieldtype": "Link",
			"options": "Shipping List",
			"width": 170,
		},
		{
			"fieldname": "packing_list",
			"label": _("Packing List"),
			"fieldtype": "Link",
			"options": "Packing List",
			"width": 170,
		},
		{"fieldname": "notes", "label": _("Notes"), "fieldtype": "Int", "width": 80},
		{"fieldname": "vendors", "label": _("Suppliers"), "fieldtype": "Int", "width": 90},
		{"fieldname": "containers", "label": _("Containers"), "fieldtype": "Int", "width": 100},
		_money("amount", "Amount", 140),
		_money("discount", "Discount", 120),
		_money("tax", "PPN", 120),
		_money("pph", "PPh", 120),
		_money("materai", "Materai", 110),
		_money("net", "Net", 150),
		_money("paid_amount", "Paid", 140),
		_money("unpaid", "Unpaid", 140),
		_money("per_container", "Net / Container", 140),
	]
	return columns, rows

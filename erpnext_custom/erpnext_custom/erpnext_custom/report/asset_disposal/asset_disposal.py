"""Aset yang sudah lepas: dijual (Sold) atau dihapusbukukan (Scrapped).

Satu laporan untuk dua jalur, karena pertanyaannya sama: aset ini lepas lewat
transaksi apa, berapa nilai bukunya waktu itu, laba/rugi berapa, dan kenapa.

Angka-angkanya dibaca dari GL voucher yang bersangkutan, bukan dihitung ulang,
supaya persis sama dengan yang masuk buku besar:

    nilai perolehan  = kredit ke akun bertipe Fixed Asset
    akumulasi        = debit ke akun bertipe Accumulated Depreciation
    laba/rugi        = kredit - debit di akun disposal Company (laba positif)
    nilai buku       = perolehan - akumulasi
    nilai jual       = nilai buku + laba/rugi   (scrap: rugi = nilai buku -> 0)
"""

import frappe
from frappe import _
from frappe.utils import flt

TYPE_VOUCHER = {"Sold": "Sales Invoice", "Scrapped": "Journal Entry"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_data(filters):
	assets = _get_assets(filters)
	if not assets:
		return []

	names = [a.name for a in assets]
	# Aset terjual: nomor invoice ada di baris Sales Invoice Item, bukan di asetnya.
	si_map = {}
	for row in frappe.get_all(
		"Sales Invoice Item",
		filters={"asset": ("in", names), "docstatus": 1},
		fields=["asset", "parent"],
	):
		si_map[row.asset] = row.parent

	customer_map = {}
	if si_map:
		customer_map = dict(
			frappe.get_all(
				"Sales Invoice",
				filters={"name": ("in", list(set(si_map.values())))},
				fields=["name", "customer"],
				as_list=True,
			)
		)

	rows = []
	for asset in assets:
		voucher = si_map.get(asset.name) if asset.status == "Sold" else asset.journal_entry_for_scrap
		amounts = _voucher_amounts(voucher, asset.company)
		rows.append(
			{
				"asset": asset.name,
				"asset_name": asset.asset_name,
				"asset_category": asset.asset_category,
				"disposal_type": asset.status,
				"disposal_date": asset.disposal_date,
				"voucher_type": TYPE_VOUCHER.get(asset.status),
				"voucher_no": voucher,
				"customer": customer_map.get(voucher),
				"purchase_amount": amounts["purchase"] or flt(asset.purchase_amount),
				"accumulated_depreciation": amounts["accumulated"],
				"book_value": amounts["book"],
				"sale_amount": amounts["sale"],
				"gain_loss": amounts["gain"],
				"disposal_reason": asset.get("custom_disposal_reason"),
				"location": asset.location,
			}
		)
	return rows


def _get_assets(filters):
	cond = {"docstatus": 1, "status": ("in", list(TYPE_VOUCHER))}
	if filters.get("company"):
		cond["company"] = filters.company
	if filters.get("disposal_type"):
		cond["status"] = filters.disposal_type
	if filters.get("asset_category"):
		cond["asset_category"] = filters.asset_category
	if filters.get("from_date") and filters.get("to_date"):
		cond["disposal_date"] = ("between", [filters.from_date, filters.to_date])

	fields = [
		"name", "asset_name", "asset_category", "status", "disposal_date",
		"company", "location", "purchase_amount", "journal_entry_for_scrap",
	]
	if frappe.get_meta("Asset").has_field("custom_disposal_reason"):
		fields.append("custom_disposal_reason")

	return frappe.get_all("Asset", filters=cond, fields=fields, order_by="disposal_date desc, name desc")


def _voucher_amounts(voucher, company):
	"""Pecah GL satu voucher jadi perolehan / akumulasi / laba-rugi.

	ponytail: satu voucher yang melepas BEBERAPA aset sekaligus akan menampilkan
	angka gabungan di tiap barisnya. Jual/scrap di sini selalu satu aset per voucher;
	kalau nanti berubah, pecah per `against_voucher`.
	"""
	empty = {"purchase": 0.0, "accumulated": 0.0, "book": 0.0, "sale": 0.0, "gain": 0.0}
	if not voucher:
		return empty

	entries = frappe.get_all(
		"GL Entry",
		filters={"voucher_no": voucher, "is_cancelled": 0},
		fields=["account", "debit", "credit"],
	)
	if not entries:
		return empty

	types = dict(
		frappe.get_all(
			"Account",
			filters={"name": ("in", [e.account for e in entries])},
			fields=["name", "account_type"],
			as_list=True,
		)
	)
	disposal_account = frappe.get_cached_value("Company", company, "disposal_account")

	purchase = accumulated = gain = 0.0
	for e in entries:
		if e.account == disposal_account:
			gain += flt(e.credit) - flt(e.debit)
		elif types.get(e.account) == "Fixed Asset":
			purchase += flt(e.credit)
		elif types.get(e.account) == "Accumulated Depreciation":
			accumulated += flt(e.debit)

	book = purchase - accumulated
	return {
		"purchase": purchase,
		"accumulated": accumulated,
		"book": book,
		"sale": book + gain,
		"gain": gain,
	}


def get_columns():
	def c(fieldname, label, fieldtype="Data", width=120, options=None):
		col = {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width}
		if options:
			col["options"] = options
		return col

	return [
		c("asset", "Asset", "Link", 150, "Asset"),
		c("asset_name", "Asset Name", "Data", 200),
		c("asset_category", "Category", "Link", 120, "Asset Category"),
		c("disposal_type", "Type", "Data", 90),
		c("disposal_date", "Disposal Date", "Date", 110),
		c("voucher_type", "Voucher Type", "Data", 110),
		c("voucher_no", "Voucher", "Dynamic Link", 160, "voucher_type"),
		c("customer", "Customer", "Link", 150, "Customer"),
		c("purchase_amount", "Purchase Amount", "Currency", 140),
		c("accumulated_depreciation", "Accumulated Depreciation", "Currency", 170),
		c("book_value", "Book Value", "Currency", 140),
		c("sale_amount", "Sale Amount", "Currency", 140),
		c("gain_loss", "Gain / Loss", "Currency", 140),
		c("disposal_reason", "Reason", "Data", 220),
		c("location", "Location", "Link", 110, "Location"),
	]

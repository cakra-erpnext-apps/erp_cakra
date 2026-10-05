"""Account Mapping: akun yang BENAR-BENAR dipakai saat transaksi, per Customer / Supplier /
Item, plus asalnya. Hanya membaca, tidak mengubah apa pun.

Urutan cari akun meniru kode yang dipakai transaksi (grup TIDAK ditelusuri ke induknya):
- Customer / Supplier: Party Account master -> Party Account grup -> Company
  (erpnext.accounts.party.get_party_account / get_party_advance_account).
- Item: Item Default item -> Item Group -> Brand -> Company
  (erpnext get_item_details; HPP ditambah fallback delivery_note._set_item_expense_accounts,
  Penjualan jatuh ke Invoice Type lewat sales_invoice._apply_type_income_account).
"""

import frappe

from erpnext_custom.item_scope import item_groups

COLUMNS = [
	{"fieldname": "jenis", "label": "Jenis", "fieldtype": "Data", "width": 80},
	{"fieldname": "ref", "label": "Kode", "fieldtype": "Dynamic Link", "options": "ref_doctype", "width": 130},
	{"fieldname": "nama", "label": "Nama", "fieldtype": "Data", "width": 180},
	{"fieldname": "grup", "label": "Grup", "fieldtype": "Dynamic Link", "options": "group_doctype", "width": 170},
	{"fieldname": "akun_untuk", "label": "Akun Untuk", "fieldtype": "Data", "width": 100},
	{"fieldname": "account", "label": "Akun", "fieldtype": "Link", "options": "Account", "width": 280},
	{"fieldname": "sumber", "label": "Sumber", "fieldtype": "Data", "width": 110},
	{"fieldname": "status", "label": "Status", "fieldtype": "Data", "width": 130},
	{"fieldname": "ref_doctype", "label": "Ref DocType", "fieldtype": "Data", "hidden": 1},
	{"fieldname": "group_doctype", "label": "Group DocType", "fieldtype": "Data", "hidden": 1},
]

PARTY = {
	# jenis: (grup doctype, field grup, field nama, akun untuk, account_type, default Company, default uang muka)
	"Customer": ("Customer Group", "customer_group", "customer_name", "Piutang", "Receivable",
	             "default_receivable_account", "default_advance_received_account"),
	"Supplier": ("Supplier Group", "supplier_group", "supplier_name", "Hutang", "Payable",
	             "default_payable_account", "default_advance_paid_account"),
}

ITEM_FIELDS = ["default_inventory_account", "default_cogs_account", "expense_account",
               "income_account", "custom_reimburse_account"]


def execute(filters=None):
	f = frappe._dict(filters or {})
	ctx = _context(f.company)
	rows = []
	for jenis in ("Customer", "Supplier"):
		if f.jenis in (None, "", jenis):
			rows += _party_rows(jenis, ctx)
	if f.jenis in (None, "", "Item"):
		rows += _item_rows(ctx)
	return COLUMNS, [r for r in rows if _match(r, f)]


def _match(r, f):
	if f.akun_untuk and r["akun_untuk"] != f.akun_untuk:
		return False
	if f.grup and f.grup.lower() not in (r["grup"] or "").lower():
		return False
	if f.kode and f.kode.lower() not in f"{r['ref']} {r['nama']}".lower():
		return False
	return not (f.hanya_masalah and r["status"] == "OK")


def _context(company):
	party_acc = {}
	for r in frappe.get_all("Party Account", filters={"company": company},
	                        fields=["parenttype", "parent", "account", "advance_account"]):
		party_acc[(r.parenttype, r.parent)] = r
	item_def = {}
	for r in frappe.get_all("Item Default", filters={"company": company},
	                        fields=["parenttype", "parent", *ITEM_FIELDS]):
		item_def[(r.parenttype, r.parent)] = r
	return frappe._dict(
		company=company,
		comp=frappe.get_cached_doc("Company", company),
		party_acc=party_acc,
		item_def=item_def,
		accounts={a.name: a for a in frappe.get_all(
			"Account", fields=["name", "company", "account_type", "root_type", "disabled"])},
		en_groups=set(item_groups("expense_note")),
	)


def _pick(*chain):
	"""(akun, sumber) pertama yang terisi."""
	for account, source in chain:
		if account:
			return account, source
	return None, ""


def _status(ctx, account, source, group_value=None, check=None, empty="Kosong"):
	if not account:
		return empty
	acc = ctx.accounts.get(account)
	if not acc:
		return "Akun tidak ada"
	if acc.company != ctx.company:
		return "Company salah"
	if check and not check(acc):
		return "Tipe salah"
	if acc.disabled:
		return "Akun nonaktif"
	if source == "Company":
		return "Default Company"
	if source in ("Customer", "Supplier", "Item") and group_value and group_value != account:
		return "Beda dari grup"
	return "OK"


def _row(jenis, ref, nama, group_dt, grup, untuk, account, sumber, status):
	return {"jenis": jenis, "ref": ref, "nama": nama, "grup": grup, "akun_untuk": untuk,
	        "account": account, "sumber": sumber, "status": status,
	        "ref_doctype": jenis, "group_doctype": group_dt}


def _party_rows(jenis, ctx):
	group_dt, group_field, name_field, untuk, atype, comp_field, comp_adv = PARTY[jenis]
	empty = frappe._dict()
	# Uang muka hanya dipakai kalau Company membukukannya ke akun terpisah.
	with_advance = ctx.comp.get("book_advance_payments_in_separate_party_account")
	rows = []
	for p in frappe.get_all(jenis, filters={"disabled": 0}, order_by="name",
	                        fields=["name", f"{name_field} as nama", f"{group_field} as grup"]):
		own = ctx.party_acc.get((jenis, p.name), empty)
		grp = ctx.party_acc.get((group_dt, p.grup), empty)
		acc, src = _pick((own.account, jenis), (grp.account, "Grup"), (ctx.comp.get(comp_field), "Company"))
		rows.append(_row(jenis, p.name, p.nama, group_dt, p.grup, untuk, acc, src,
		                 _status(ctx, acc, src, grp.account, lambda a: a.account_type == atype)))
		if with_advance:
			acc, src = _pick((own.advance_account, jenis), (grp.advance_account, "Grup"),
			                 (ctx.comp.get(comp_adv), "Company"))
			rows.append(_row(jenis, p.name, p.nama, group_dt, p.grup, "Uang Muka", acc, src,
			                 _status(ctx, acc, src, grp.advance_account)))
	return rows


def _item_rows(ctx):
	empty = frappe._dict()
	comp = ctx.comp
	is_expense = lambda a: a.root_type == "Expense"  # noqa: E731
	rows = []
	for it in frappe.get_all("Item", filters={"disabled": 0}, order_by="name",
	                         fields=["name", "item_name", "item_group", "brand", "is_stock_item"]):
		own = ctx.item_def.get(("Item", it.name), empty)
		grp = ctx.item_def.get(("Item Group", it.item_group), empty)
		brand = ctx.item_def.get(("Brand", it.brand), empty) if it.brand else empty

		def chain(field, with_brand=True):
			c = [(own.get(field), "Item"), (grp.get(field), "Grup")]
			return c + [(brand.get(field), "Brand")] if with_brand else c

		def add(untuk, acc, src, field, check=None, empty_status="Kosong"):
			rows.append(_row("Item", it.name, it.item_name, "Item Group", it.item_group, untuk, acc, src,
			                 _status(ctx, acc, src, grp.get(field), check, empty_status)))

		if it.is_stock_item:
			if comp.get("enable_item_wise_inventory_account"):
				acc, src = _pick(*chain("default_inventory_account"))
				add("Persediaan", acc, src, "default_inventory_account", lambda a: a.account_type == "Stock")
			# HPP: Default COGS dulu; kosong -> akun Pemakaian item/grup (delivery_note
			# override) -> default Company.
			acc, src = _pick(*chain("default_cogs_account"),
			                 (own.get("expense_account"), "Item: Pemakaian"),
			                 (grp.get("expense_account"), "Grup: Pemakaian"),
			                 (comp.get("default_expense_account"), "Company"))
			add("HPP", acc, src, "default_cogs_account", is_expense)

		acc, src = _pick(*chain("expense_account"), (comp.get("default_expense_account"), "Company"))
		add("Pemakaian", acc, src, "expense_account", is_expense)

		# Item/grup sengaja kosong = ikut akun Invoice Type (keputusan akuntansi), bukan masalah.
		acc, src = _pick(*chain("income_account"))
		add("Penjualan", acc, src or "Invoice Type", "income_account",
		    lambda a: a.root_type == "Income", empty_status="OK")

		if it.item_group in ctx.en_groups:
			acc, src = _pick(*chain("custom_reimburse_account", with_brand=False))
			add("Reimburse", acc, src, "custom_reimburse_account")
	return rows

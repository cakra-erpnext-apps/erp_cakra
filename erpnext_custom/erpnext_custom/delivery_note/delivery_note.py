import frappe
from frappe import _

from erpnext_custom import bin_layout
from erpnext_custom.selling_amounts import compute_display, inject


def before_validate(doc, method=None):
	_sync_remark(doc)
	_set_item_expense_accounts(doc)
	inject(doc)


def validate(doc, method=None):
	compute_display(doc)
	validate_mixed_item_sources(doc)
	warn_unplaced(doc)


def _set_item_expense_accounts(doc):
	"""make_delivery_note dari SO tidak membawa default expense account (HPP) milik
	Item/Item Group — barisnya jatuh ke default expense account company. Tegakkan
	default Item di sini; isian manual user (selain default company) dibiarkan."""
	company_default = frappe.get_cached_value("Company", doc.company, "default_expense_account")
	for row in doc.get("items"):
		if not row.item_code:
			continue
		if row.get("expense_account") and row.expense_account != company_default:
			continue  # user sudah memilih akun sendiri
		account = frappe.db.get_value(
			"Item Default", {"parent": row.item_code, "company": doc.company}, "expense_account"
		) or frappe.db.get_value(
			"Item Default",
			{
				"parent": frappe.db.get_value("Item", row.item_code, "item_group"),
				"company": doc.company,
			},
			"expense_account",
		)
		if account:
			row.expense_account = account


def _sync_remark(doc):
	if doc.get("custom_remark"):
		doc.remarks = doc.custom_remark
	elif doc.get("remarks"):
		doc.custom_remark = doc.remarks


def warn_unplaced(doc):
	"""Peringatkan kalau barang yang mau dikirim masih menggantung di staging masuk.

	Itu tanda put-away-nya terlewat: fisiknya sudah naik rak, catatannya belum.
	Kalau DN tetap disubmit, consume() memakan lapisan dari staging -- bin yang
	fisiknya justru sudah kosong -- dan peta rak melenceng tanpa bisa dilihat
	audit(), karena total per gudang tetap cocok. Inilah satu-satunya momen
	kerusakan itu terjadi, jadi inilah satu-satunya tempat memperingatkannya.

	msgprint, bukan throw: mengirim langsung dari staging itu sah (barang datang
	pagi dan keluar sore, tidak pernah naik rak), dan memblokirnya akan
	menghentikan pengiriman yang benar.

	Baris yang lahir dari Pick List dilewati -- bin asalnya sudah pasti.
	"""
	if doc.get("is_return"):
		return
	kena = []
	for gudang in {r.warehouse for r in doc.get("items") or [] if r.get("warehouse")}:
		staging = bin_layout.staging_stock(gudang)
		if not staging:
			continue
		for row in doc.get("items"):
			if row.warehouse != gudang or row.get("pick_list_item"):
				continue
			if staging.get(row.item_code):
				kena.append(
					_("Baris {0}: {1} masih ada {2} di staging {3}").format(
						row.idx, frappe.bold(row.item_code), staging[row.item_code], gudang
					)
				)
	if kena:
		frappe.msgprint(
			"<br>".join(kena)
			+ "<br><br>"
			+ _(
				"Barang ini tercatat belum ditempatkan ke rak. Kalau fisiknya sudah di rak, "
				"buat <b>Goods Receive</b> dulu supaya rak asalnya benar."
			),
			title=_("Belum Ditempatkan ke Rak"),
			indicator="orange",
		)


def validate_mixed_item_sources(doc):
	"""Do not let the same item be added once from PL and again from SO/manual."""
	rows_by_item = {}
	for row in doc.get("items"):
		if not row.item_code:
			continue
		key = (row.item_code, row.warehouse or "")
		state = rows_by_item.setdefault(key, {"pick_list": [], "other": []})
		if row.get("pick_list_item"):
			state["pick_list"].append(row.idx)
		else:
			state["other"].append(row.idx)

	for (item_code, warehouse), rows in rows_by_item.items():
		if rows["pick_list"] and rows["other"]:
			frappe.throw(
				_(
					"Item {0} in warehouse {1} was added from both Picking List "
					"(row {2}) and Sales Order/manual (row {3}). Use the Picking List "
					"row only to prevent duplicate delivery."
				).format(
					frappe.bold(item_code),
					frappe.bold(warehouse or "-"),
					", ".join(map(str, rows["pick_list"])),
					", ".join(map(str, rows["other"])),
				),
				title=_("Duplicate Delivery Source"),
			)


@frappe.whitelist()
def get_pick_list_query(doctype, txt, searchfield, start, page_len, filters):
	"""Show both SO-linked and standalone Delivery Pick Lists in the DN picker."""
	frappe.has_permission("Pick List", throw=True)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

	if not filters.get("company"):
		frappe.throw(_("Please select a Company"))

	conditions = [
		"pl.docstatus = 1",
		"pl.status IN ('Open', 'Partly Delivered')",
		"pl.purpose = 'Delivery'",
		"pl.company = %(company)s",
	]
	values = {
		"company": filters.get("company"),
		"customer": filters.get("customer") or "",
		"sales_order": filters.get("sales_order") or "",
		"txt": f"%{txt or ''}%",
		"start": int(start or 0),
		"page_len": int(page_len or 20),
	}

	if values["customer"]:
		conditions.append("pl.customer = %(customer)s")
	if values["sales_order"]:
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabPick List Item` f "
			"WHERE f.parent = pl.name AND f.sales_order = %(sales_order)s)"
		)
	if txt:
		conditions.append("(pl.name LIKE %(txt)s OR pl.customer LIKE %(txt)s)")

	return frappe.db.sql(
		f"""
			SELECT
				pl.name,
				pl.customer,
				REPLACE(GROUP_CONCAT(DISTINCT pli.sales_order), ',', '<br>') AS sales_order
			FROM `tabPick List` pl
			INNER JOIN `tabPick List Item` pli ON pli.parent = pl.name
			WHERE {' AND '.join(conditions)}
			GROUP BY pl.name, pl.customer
			ORDER BY pl.modified DESC
			LIMIT %(start)s, %(page_len)s
		""",
		values,
		as_dict=True,
	)

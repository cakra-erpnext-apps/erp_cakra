"""Cek ketiga jalur sparepart dalam satu jalan. Semua perubahan di-rollback.

    bench --site erp.localhost console
    >>> from erp.fleet.doctype.maintenance.test_maintenance import run; run()
"""

import frappe
from frappe.utils import today


def run():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	wh = frappe.get_all("Warehouse", filters={"is_group": 0, "company": company}, pluck="name")[0]
	exp = frappe.get_all(
		"Account",
		filters={"company": company, "root_type": "Expense", "is_group": 0, "disabled": 0},
		pluck="name",
	)[0]
	vehicle = frappe.db.get_value("Vehicle", {"disabled": 0}, "name")
	supplier = frappe.get_all("Supplier", pluck="name")[0]

	def stock():
		return frappe.db.get_value("Bin", {"item_code": "TEST-SPR-01", "warehouse": wh}, "actual_qty")

	try:
		if not frappe.db.exists("Item", "TEST-SPR-01"):
			frappe.get_doc({
				"doctype": "Item", "item_code": "TEST-SPR-01", "item_name": "Filter Oli Uji",
				"item_group": "Products", "stock_uom": "Nos", "is_stock_item": 1,
				"item_defaults": [{"company": company, "default_warehouse": wh, "expense_account": exp}],
			}).insert()

		receipt = frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": company,
			"items": [{"item_code": "TEST-SPR-01", "qty": 10, "t_warehouse": wh, "basic_rate": 100000}],
		})
		receipt.insert()
		receipt.submit()
		qty0 = stock()

		# --- Jalur 3: Maintenance mengeluarkan stok saat Validate -------------
		mtc = frappe.get_doc({
			"doctype": "Maintenance", "vehicle": vehicle, "company": company,
			"maintenance_type": "Servis Rutin", "date": today(),
			"items": [
				{"item": "TEST-SPR-01", "warehouse": wh, "qty": 2, "rate": 1},  # rate ngawur
				{"description": "Jasa servis bengkel", "qty": 1, "rate": 250000},
			],
		}).insert()
		assert not mtc.stock_entry and stock() == qty0, "draft tidak boleh menyentuh stok"

		mtc.validated = 1
		mtc.save()
		mtc.reload()
		assert mtc.stock_entry, "Validate tidak menerbitkan Stock Entry"
		assert stock() == qty0 - 2, "stok tidak berkurang"
		# harga baris stock ditimpa valuation gudang, bukan ketikan user
		assert mtc.items[0].rate == 100000, mtc.items[0].rate
		assert mtc.total_amount == 450000, mtc.total_amount

		try:
			mtc.items[0].qty = 5
			mtc.save()
			raise AssertionError("dokumen tervalidasi masih bisa diubah")
		except frappe.ValidationError:
			pass
		mtc.reload()

		mtc.validated = 0
		mtc.save()
		mtc.reload()
		assert not mtc.stock_entry and stock() == qty0, "Invalidate tidak mengembalikan stok"

		# --- Jalur 1: PR ber-Vehicle = langsung pakai + kartu Maintenance ------
		pr = frappe.get_doc({
			"doctype": "Purchase Receipt", "company": company, "supplier": supplier, "posting_date": today(),
			"items": [{"item_code": "TEST-SPR-01", "qty": 3, "rate": 120000, "warehouse": wh,
			           "custom_vehicle": vehicle}],
		})
		pr.insert()
		pr.flags.cmi_action_ok = True
		pr.submit()
		pr.reload()
		assert stock() == qty0, "sparepart langsung pakai tidak boleh menambah stok"

		auto = frappe.get_all(
			"Maintenance", filters={"purchase_receipt": pr.name}, fields=["name", "validated", "stock_entry"]
		)
		assert len(auto) == 1 and auto[0].validated == 1, "kartu Maintenance otomatis tidak terbit"
		assert auto[0].stock_entry == pr.custom_sparepart_issue, "harus memakai Stock Entry milik PR"

		mirror = frappe.get_doc("Maintenance", auto[0].name)
		try:
			mirror.validated = 0
			mirror.save()
			raise AssertionError("turunan PR bisa di-invalidate sendiri")
		except frappe.ValidationError:
			pass

		pr.reload()
		pr.flags.cmi_action_ok = True
		pr.cancel()
		assert frappe.db.get_value("Maintenance", auto[0].name, "void") == 1, "PR batal tapi kartunya hidup"

		print("SEMUA CEK LULUS")
	finally:
		frappe.db.rollback()

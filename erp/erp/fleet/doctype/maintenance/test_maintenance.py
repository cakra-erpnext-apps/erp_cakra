"""Cek semua jalur sparepart dalam satu jalan (PR, PI ber-update_stock, Maintenance). Semua perubahan di-rollback.

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
	vehicle2 = frappe.db.get_value("Vehicle", {"disabled": 0, "name": ["!=", vehicle]}, "name")
	po_type = frappe.get_all("Purchase Order Type", pluck="name")[0]

	def stock():
		return frappe.db.get_value("Bin", {"item_code": "TEST-SPR-01", "warehouse": wh}, "actual_qty")

	try:
		if not frappe.db.exists("Item", "TEST-SPR-01"):
			frappe.get_doc({
				"doctype": "Item", "item_code": "TEST-SPR-01", "item_name": "Filter Oli Uji",
				"item_group": "Products", "stock_uom": "Nos", "is_stock_item": 1,
				"item_category": "Sparepart",
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
			"items": [{"item": "TEST-SPR-01", "warehouse": wh, "qty": 2, "rate": 1,
			           "description": "ganti filter oli"}],  # rate ngawur, harus ditimpa valuation
		}).insert()
		assert not mtc.stock_entry and stock() == qty0, "draft tidak boleh menyentuh stok"

		mtc.validated = 1
		mtc.save()
		mtc.reload()
		assert mtc.stock_entry, "Validate tidak menerbitkan Stock Entry"
		assert stock() == qty0 - 2, "stok tidak berkurang"
		# harga baris stock ditimpa valuation gudang, bukan ketikan user
		assert mtc.items[0].rate == 100000, mtc.items[0].rate
		assert mtc.total_amount == 200000, mtc.total_amount

		try:
			mtc.items[0].qty = 5
			mtc.save()
			raise AssertionError("dokumen tervalidasi masih bisa diubah")
		except frappe.ValidationError:
			pass
		mtc.reload()

		# 1:1 dengan Stock Entry-nya: SE tidak boleh dibatalkan dari layarnya sendiri,
		# revisi harus lewat Invalidate kartu ini.
		try:
			frappe.get_doc("Stock Entry", mtc.stock_entry).cancel()
			raise AssertionError("Stock Entry milik Maintenance masih bisa dibatalkan sendiri")
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

		# --- Jalur 1b: PI campuran (alur PO -> PI, tanpa PR) -------------------
		# Baris ber-Vehicle TANPA gudang = langsung biaya; baris ber-gudang = persediaan.
		pi = frappe.get_doc({
			"doctype": "Purchase Invoice", "company": company, "supplier": supplier,
			"posting_date": today(), "custom_type": po_type,
			# Item yang SAMA boleh muncul berkali-kali dengan kendaraan berbeda.
			"items": [
				{"item_code": "TEST-SPR-01", "qty": 4, "rate": 120000, "custom_vehicle": vehicle},
				{"item_code": "TEST-SPR-01", "qty": 3, "rate": 120000, "custom_vehicle": vehicle2},
				{"item_code": "TEST-SPR-01", "qty": 2, "rate": 120000, "warehouse": wh},
			],
		})
		pi.insert()
		assert pi.update_stock == 1, "ada baris bergudang tapi update_stock tidak menyala"
		assert not pi.items[0].warehouse, "baris ber-Vehicle tidak boleh diisi gudang"
		assert pi.items[0].expense_account == exp, pi.items[0].expense_account
		pi.flags.cmi_action_ok = True
		pi.submit()
		pi.reload()

		assert stock() == qty0 + 2, "hanya baris bergudang yang boleh menambah stok"
		gl = dict(frappe.db.sql(
			"""select account, sum(debit) from `tabGL Entry`
			   where voucher_no=%s and is_cancelled=0 group by account""", pi.name))
		assert gl.get(exp) == 840000, ("dua baris ber-Vehicle harus jadi biaya", gl)
		assert not frappe.db.exists(
			"Stock Ledger Entry", {"voucher_no": pi.name, "item_code": "TEST-SPR-01", "actual_qty": 4}
		), "baris ber-Vehicle tidak boleh menulis stok"

		# Satu kartu PER KENDARAAN (bukan per baris, bukan per faktur).
		auto_pi = frappe.get_all(
			"Maintenance", filters={"purchase_invoice": pi.name},
			fields=["name", "vehicle", "validated", "stock_entry"], order_by="vehicle",
		)
		assert len(auto_pi) == 2, ("harus 1 kartu per kendaraan", auto_pi)
		assert {a.vehicle for a in auto_pi} == {vehicle, vehicle2}, auto_pi
		assert all(a.validated == 1 for a in auto_pi), "kartu Maintenance dari PI tidak ter-validate"
		assert not any(a.stock_entry for a in auto_pi), "kartu dari PI tidak punya Stock Entry"
		kartu_awal = {a.name for a in auto_pi}
		auto_pi = [a for a in auto_pi if a.vehicle == vehicle]

		# Revisi lewat PI: Invalidate -> ubah -> Validate lagi. Kartu yang SAMA dipakai ulang
		# dan isinya ditulis ulang; kartu lain (manual/PR) tidak boleh ikut tersentuh.
		from erpnext_custom.workflow import invalidate_doc, validate_doc

		mtc.reload()
		manual_before = (mtc.modified, mtc.validated)
		invalidate_doc("Purchase Invoice", pi.name)
		assert not any(frappe.db.get_value("Maintenance", n, "validated") for n in kartu_awal), 			"Invalidate PI tidak mengembalikan kartunya ke belum-divalidasi"

		# Kartu turunan PI TIDAK bisa diedit dari sini, walau statusnya sedang belum
		# divalidasi -- perbaikannya lewat PI.
		lepas = frappe.get_doc("Maintenance", auto_pi[0].name)
		try:
			lepas.items[0].qty = 99
			lepas.save()
			raise AssertionError("kartu turunan PI bisa diedit langsung")
		except frappe.ValidationError:
			pass

		pi.reload()
		pi.items[0].qty = 6
		# received_qty diurus klien saat qty diubah di form; di sini diset manual.
		pi.items[0].received_qty = 6
		pi.save()
		validate_doc("Purchase Invoice", pi.name)

		kartu = set(frappe.get_all("Maintenance", filters={"purchase_invoice": pi.name}, pluck="name"))
		assert kartu == kartu_awal, ("harus kartu yang sama, bukan kartu baru", kartu, kartu_awal)
		revisi = frappe.get_doc("Maintenance", auto_pi[0].name)
		assert revisi.validated == 1 and revisi.items[0].qty == 6, "kartu tidak ikut terevisi"

		mtc.reload()
		assert (mtc.modified, mtc.validated) == manual_before, "kartu manual ikut tersentuh"
		pi.reload()

		# Catatan lapangan boleh dilengkapi walau kartunya sudah Validated (FIELD_NOTES) --
		# kartu turunan PI tidak punya layar lain untuk mengisinya. Isi kartunya tetap terkunci.
		mirror_pi = frappe.get_doc("Maintenance", auto_pi[0].name)
		mirror_pi.odometer = 125000
		mirror_pi.next_service_km = 130000
		mirror_pi.save()
		assert frappe.db.get_value("Maintenance", mirror_pi.name, "odometer") == 125000
		try:
			mirror_pi.items[0].qty = 9
			mirror_pi.save()
			raise AssertionError("isi kartu tervalidasi masih bisa diubah")
		except frappe.ValidationError:
			pass
		mirror_pi.reload()

		pi.reload()
		pi.flags.cmi_action_ok = True
		pi.cancel()
		assert frappe.db.get_value("Maintenance", auto_pi[0].name, "void") == 1, "PI batal tapi kartunya hidup"
		assert stock() == qty0, "pembatalan PI meninggalkan sisa stok"

		print("SEMUA CEK LULUS")
	finally:
		frappe.db.rollback()

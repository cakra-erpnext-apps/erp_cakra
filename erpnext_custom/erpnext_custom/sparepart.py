"""Sparepart langsung dipakai (aturan tipe pembelian #5).

Baris Purchase Receipt ber-Vehicle = sparepart itu dipakai langsung ke kendaraan
tersebut: barang tetap diterima ke gudang dulu (qty jujur, alur PR -> PI tetap
normal), lalu pada submit yang sama otomatis dibuat Stock Entry Material Issue
sehingga stoknya langsung nol dan nilainya jadi beban (default expense account
Item). Vehicle per BARIS — baris tanpa Vehicle jadi stok biasa.

Void/Invalidate PR membatalkan Material Issue-nya lebih dulu — kalau tidak,
pembatalan PR ditolak ERPNext karena stok akan minus.
"""

import frappe
from frappe import _


def issue_on_submit(doc, method=None):
	rows = [
		r for r in doc.items
		if r.item_code and r.get("custom_vehicle")
		and frappe.get_cached_value("Item", r.item_code, "is_stock_item")
	]
	if not rows:
		return

	vehicles = sorted({r.custom_vehicle for r in rows})
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.company = doc.company
	se.set_posting_time = 1
	se.posting_date = doc.posting_date
	se.posting_time = doc.posting_time
	se.remarks = _("Sparepart dipakai langsung dari {0}, kendaraan {1}").format(
		doc.name, ", ".join(vehicles)
	)
	for r in rows:
		se.append("items", {
			"item_code": r.item_code,
			"qty": r.stock_qty or r.qty,
			"s_warehouse": r.warehouse,
			"expense_account": expense_account(r.item_code, doc.company),
		})
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	doc.db_set("custom_sparepart_issue", se.name, update_modified=False)
	_make_maintenance(doc, rows, se.name)


def cancel_issue_before_cancel(doc, method=None):
	# Invalidate = dokumen akan diperbaiki lalu divalidasi lagi, jadi kartunya cukup
	# dikembalikan ke belum-divalidasi (outstanding) dan DIPAKAI ULANG nanti -- nomor
	# kartu ikut bertahan sebagaimana nomor PR-nya bertahan.
	# Void = dokumen memang batal, kartunya ditandai Void sebagai jejak.
	if doc.flags.get("cmi_invalidate"):
		_unvalidate_maintenance(doc)
	else:
		_void_maintenance(doc)
	se_name = doc.get("custom_sparepart_issue")
	if not se_name or not frappe.db.exists("Stock Entry", se_name):
		return
	se = frappe.get_doc("Stock Entry", se_name)
	if se.docstatus == 1:
		se.flags.ignore_permissions = True
		se.flags.pr_owned_ok = True  # satu-satunya jalur sah, lihat guard_issue_cancel
		se.cancel()
	doc.db_set("custom_sparepart_issue", None, update_modified=False)


def guard_issue_cancel(doc, method=None):
	"""Material Issue turunan PR tidak boleh dibatalkan dari dokumennya sendiri.

	Stok dan kartu Maintenance-nya milik PR. Membatalkan Stock Entry ini langsung
	mengembalikan stok, tetapi PR masih menunjuk dokumen yang sudah mati dan kartu
	Maintenance-nya tetap menyebut qty lama -- dan pembatalan PR-nya nanti akan
	ditolak karena penjaga di atas melihat pointer yang sudah docstatus 2 lalu diam.
	Jalan yang benar: Invalidate atau Void PR-nya, yang membatalkan Stock Entry ini
	lebih dulu lewat cancel_issue_before_cancel.
	"""
	if doc.flags.get("pr_owned_ok"):
		return
	pr = frappe.db.get_value(
		"Purchase Receipt", {"custom_sparepart_issue": doc.name, "docstatus": 1}, "name"
	)
	if pr:
		frappe.throw(
			_("Stock Entry {0} milik Purchase Receipt {1}. Batalkan lewat Invalidate "
			  "atau Void pada PR itu, bukan di sini.").format(doc.name, pr)
		)


# ---------------------------------------------------------------- kartu maintenance
# Sparepart yang dipakai langsung TETAP tercatat sebagai Maintenance kendaraan (satu
# dokumen per kendaraan, langsung Validated) supaya riwayat pemakaian sebuah nopol utuh
# di satu tempat -- tidak ada yang harus mengingat bahwa sebagian pemakaian "ada di PR".
# Dokumen itu cermin: jurnalnya milik Stock Entry di atas, lihat erp.fleet Maintenance.


def _make_maintenance(pr, rows, se_name):
	if not frappe.db.exists("DocType", "Maintenance"):
		return
	by_vehicle = {}
	for r in rows:
		by_vehicle.setdefault(r.custom_vehicle, []).append(r)

	for vehicle, items in by_vehicle.items():
		# Kartu yang tertinggal outstanding dari Invalidate sebelumnya DIPAKAI ULANG.
		# Tanpa ini, tiap koreksi menerbitkan kartu baru dan satu PR meninggalkan
		# tumpukan kartu untuk satu kejadian servis yang sama.
		existing = frappe.db.get_value(
			"Maintenance",
			{"purchase_receipt": pr.name, "vehicle": vehicle, "void": 0, "validated": 0},
			"name",
		)
		doc = frappe.get_doc("Maintenance", existing) if existing else frappe.new_doc("Maintenance")
		doc.set("items", [])
		doc.update({
			"vehicle": vehicle,
			"company": pr.company,
			"date": pr.posting_date,
			"maintenance_type": "Perbaikan",
			"supplier": pr.supplier,
			"purchase_receipt": pr.name,
			"stock_entry": se_name,
			"validated": 1,
			"description": _("Sparepart dipakai langsung dari {0}.").format(pr.name),
		})
		for r in items:
			doc.append("items", {
				"item": r.item_code,
				"description": r.item_name or r.item_code,
				"is_stock_item": 1,
				"warehouse": r.warehouse,
				"qty": r.stock_qty or r.qty,
				"uom": r.stock_uom or r.uom,
				# Harga beli, bukan valuation: barang ini tidak pernah mengendap di gudang.
				"rate": r.valuation_rate or r.base_rate or r.rate,
			})
		doc.flags.pr_sync = True
		doc.flags.ignore_permissions = True
		doc.save() if existing else doc.insert()


def _unvalidate_maintenance(pr):
	"""PR di-Invalidate -> kartu turunannya kembali OUTSTANDING (belum divalidasi).

	Bukan Void: PR-nya akan diperbaiki lalu divalidasi ulang, dan kartu yang sama
	dipakai lagi oleh _make_maintenance. Aman terhadap stok karena kartu turunan PR
	tidak pernah mengurus Stock Entry-nya sendiri (lihat Maintenance._sync_issue,
	yang langsung berhenti begitu purchase_receipt terisi).
	"""
	if not frappe.db.exists("DocType", "Maintenance"):
		return
	for name in frappe.get_all(
		"Maintenance", filters={"purchase_receipt": pr.name, "void": 0, "validated": 1}, pluck="name"
	):
		doc = frappe.get_doc("Maintenance", name)
		doc.validated = 0
		doc.flags.pr_sync = True
		doc.flags.ignore_permissions = True
		doc.save()


def _void_maintenance(pr):
	"""PR dibatalkan -> kartu Maintenance turunannya ikut Void (bukan dihapus: dokumen
	yang pernah terbit adalah jejak, dan nomornya sudah terlanjur dipakai)."""
	if not frappe.db.exists("DocType", "Maintenance"):
		return
	for name in frappe.get_all("Maintenance", filters={"purchase_receipt": pr.name, "void": 0}, pluck="name"):
		doc = frappe.get_doc("Maintenance", name)
		doc.void = 1
		doc.void_reason = _("Purchase Receipt {0} dibatalkan.").format(pr.name)
		doc.flags.pr_sync = True
		doc.flags.ignore_permissions = True
		doc.save()


# Field harga/akunting di edit-row Purchase Receipt Item yang tidak dipakai user
# (rate ikut PO / price list). Disembunyikan via Property Setter (idempotent,
# dipanggil dari install.after_migrate).
PR_ITEM_HIDE = (
	"rate", "amount", "base_rate", "base_amount", "is_free_item",
	"net_rate", "net_amount", "item_tax_template",
	"base_net_rate", "base_net_amount", "landed_cost_voucher_amount",
	"amount_difference_with_purchase_invoice", "billed_amt",
)


def ensure_view_properties():
	props = [("Purchase Receipt Item", f, "hidden", "1", "Check") for f in PR_ITEM_HIDE]
	props.append(("Purchase Receipt Item", "accounting_details_section", "collapsible", "1", "Check"))
	# WMS ringan: warehouse core = lokasi posting sebenarnya, dipakai sebagai RAK
	# (custom_gudang cuma filter gudangnya — lihat install.SPAREPART_FIELDS).
	props.append(("Purchase Receipt Item", "warehouse", "label", "Rack", "Data"))
	for doc_type, field_name, prop, value, property_type in props:
		filters = {"doc_type": doc_type, "field_name": field_name, "property": prop}
		name = frappe.db.exists("Property Setter", filters)
		setter = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
		setter.update({
			"doctype_or_field": "DocField",
			**filters,
			"value": value,
			"property_type": property_type,
			"module": "ERPNext Custom",
		})
		setter.save(ignore_permissions=True)


def expense_account(item_code, company):
	"""Akun beban sparepart: default Item, lalu default Item Group. Dipakai bersama
	oleh jalur PR ber-Vehicle (di atas) dan Maintenance (erp.fleet)."""
	account = frappe.db.get_value(
		"Item Default", {"parent": item_code, "company": company}, "expense_account"
	) or frappe.db.get_value(
		"Item Default",
		{"parent": frappe.db.get_value("Item", item_code, "item_group"), "company": company},
		"expense_account",
	)
	if not account:
		frappe.throw(
			_("Item {0} belum punya Default Expense Account (akun beban sparepart) untuk {1}.").format(
				item_code, company
			)
		)
	return account

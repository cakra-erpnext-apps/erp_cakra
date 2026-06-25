"""Import Customer dari CRM Organization (idempotent, cek by nama, dengan pilihan scope).

Customer (ERPNext, sisi akuntansi) dan CRM Organization (app `crm`, sisi pipeline)
adalah master berbeda yang sama-sama dibutuhkan app-nya — tidak bisa digabung jadi
satu doctype. Tool ini MENYALIN organisasi CRM menjadi Customer ERPNext, MELEWATI
yang sudah ada (cek nama) supaya ringan & bisa dijalankan berulang tanpa duplikat.

Scope:
- "operational" : nama yang dipakai di Shipping List / Packing List / Expense Note
                  (consignee/customer) — paling relevan untuk invoicing.
- "won_deals"   : organisasi dari CRM Deal berstatus Won.
- "all"         : semua CRM Organization (hati-hati: bisa ribuan).

Penamaan Customer = "Customer Name" (Customer.name == customer_name), jadi Customer
hasil impor langsung cocok dipakai di field consignee/customer (kini Link:Customer).
"""

import frappe
from frappe import _

SCOPES = ("operational", "won_deals", "all")


def _defaults():
	"""Customer Group & Territory default (Selling Settings -> fallback leaf yang ada)."""
	ss = frappe.get_single("Selling Settings")
	group = ss.get("customer_group")
	if not group:
		group = "Commercial" if frappe.db.exists("Customer Group", "Commercial") else None
	if not group:
		g = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit_page_length=1)
		group = g[0] if g else None
	territory = ss.get("territory")
	if not territory:
		territory = "Indonesia" if frappe.db.exists("Territory", "Indonesia") else None
	if not territory:
		t = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit_page_length=1)
		territory = t[0] if t else None
	return group, territory


def _scope_names(scope):
	"""Kumpulan nama (CRM Organization) untuk scope, SEBELUM filter 'sudah ada'."""
	if scope == "operational":
		names = set()
		names |= set(frappe.get_all("Shipping List BL", {"consignee": ["is", "set"]}, pluck="consignee"))
		names |= set(frappe.get_all("Shipping List Container", {"customer": ["is", "set"]}, pluck="customer"))
		names |= set(frappe.get_all("Packing List Item", {"customer": ["is", "set"]}, pluck="customer"))
		names |= set(frappe.get_all("Expense Note Container", {"customer": ["is", "set"]}, pluck="customer"))
		return {n for n in names if n}
	if scope == "won_deals":
		won = frappe.get_all("CRM Deal Status", {"type": "Won"}, pluck="name")
		if not won:
			return set()
		orgs = frappe.get_all("CRM Deal", {"status": ["in", won], "organization": ["is", "set"]}, pluck="organization")
		return {o for o in orgs if o}
	# default: all
	return {n for n in frappe.get_all("CRM Organization", pluck="name") if n}


def _existing():
	ex = set(frappe.get_all("Customer", pluck="name"))
	ex |= {n for n in frappe.get_all("Customer", pluck="customer_name") if n}
	return ex


def _pending_names(scope="operational"):
	ex = _existing()
	return [n for n in _scope_names(scope) if n not in ex]


@frappe.whitelist()
def preview_crm_import():
	"""Jumlah yang AKAN diimpor per scope (yang sudah ada di-skip)."""
	ex = _existing()
	counts = {s: len([n for n in _scope_names(s) if n not in ex]) for s in SCOPES}
	counts["total_org"] = frappe.db.count("CRM Organization")
	counts["already"] = len(ex)
	return counts


def _do_import(scope="operational", names=None):
	"""Buat Customer untuk nama yang belum ada. Dipakai langsung atau via background job."""
	group, territory = _defaults()
	if not group or not territory:
		frappe.throw(_("Default Customer Group / Territory tidak ditemukan — set dulu di Selling Settings."))
	pending = names if names is not None else _pending_names(scope)
	created, skipped, errors = 0, 0, []
	for nm in pending:
		# Cek ulang tepat sebelum insert (anti balapan / duplikat di tengah batch).
		if frappe.db.exists("Customer", nm) or frappe.db.exists("Customer", {"customer_name": nm}):
			skipped += 1
			continue
		try:
			c = frappe.new_doc("Customer")
			c.customer_name = nm
			c.customer_group = group
			c.territory = territory
			c.insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			errors.append(f"{nm}: {type(e).__name__}")
		if (created + skipped) % 200 == 0:
			frappe.db.commit()
	frappe.db.commit()
	return {"created": created, "skipped": skipped, "error_count": len(errors), "errors": errors[:15]}


@frappe.whitelist()
def import_from_crm_organization(scope="operational"):
	"""Impor sinkron (untuk set kecil). Mengembalikan ringkasan."""
	if scope not in SCOPES:
		frappe.throw(_("Scope tidak valid."))
	return _do_import(scope)


@frappe.whitelist()
def enqueue_crm_import(scope="operational"):
	"""Impor di background (aman untuk ribuan record)."""
	if scope not in SCOPES:
		frappe.throw(_("Scope tidak valid."))
	pending = len(_pending_names(scope))
	if pending:
		frappe.enqueue(
			"erpnext_custom.customer_import._do_import",
			queue="long",
			timeout=3600,
			job_name="import_crm_org_to_customer",
			scope=scope,
		)
	return {"queued": bool(pending), "pending": pending, "scope": scope}

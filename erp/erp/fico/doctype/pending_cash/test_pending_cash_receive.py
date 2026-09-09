"""Jaminan (Pending Cash arah Cash Inflow) dipakai di Payment Entry Receive. Jalankan:

	bench --site erp.localhost execute erp.fico.doctype.pending_cash.test_pending_cash_receive.run

Yang dijaga: uang muka arah Masuk ada di sisi KREDIT jurnalnya, jadi saat ditarik ke
Payment Entry Receive barisnya harus DIDEBIT (jaminan berkurang) menggantikan sebagian
sisi bank -- bukan dikredit seperti arah Keluar. Salah sisi di sini artinya saldo jaminan
customer tidak pernah tertutup dan bank tercatat menerima uang dua kali.

Payment Entry-nya sengaja TIDAK disimpan: yang diuji pembentukan baris GL-nya, dan itu
sudah cukup gagal kalau sisinya terbalik -- tanpa perlu Sales Invoice beneran.
"""

import frappe
from frappe.utils import flt, getdate

from erp.fico.doctype.pending_cash.test_pending_cash_direction import (
	_bank,
	_cleanup,
	_make_doc,
	_make_type,
	_pay,
	TOTAL,
)

BILL = 8_000_000  # tagihan lebih besar dari jaminan: sisanya masuk lewat bank


def _pe(company, bank_gl, party_type, party, payment_type, pending, amount):
	doc = frappe.new_doc("Payment Entry")
	doc.payment_type = payment_type
	doc.company = company
	doc.posting_date = getdate()
	doc.party_type, doc.party = party_type, party
	doc.cost_center = frappe.get_cached_value("Company", company, "cost_center")
	cur = frappe.get_cached_value("Company", company, "default_currency")
	side = "paid_to" if payment_type == "Receive" else "paid_from"
	setattr(doc, side, bank_gl)
	setattr(doc, side + "_account_currency", cur)
	doc.source_exchange_rate = doc.target_exchange_rate = 1
	doc.paid_amount = doc.received_amount = amount
	doc.base_paid_amount = doc.base_received_amount = amount
	doc.append("custom_pending_items", {
		"reference_doctype": "Pending Cash", "transaction": pending, "allocated": TOTAL,
	})
	return doc


def _by_account(gl):
	return {r["account"]: r for r in gl}


def run():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	bank = _bank(company)
	assert bank, f"Tidak ada Bank Account company untuk {company}"
	jaminan = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "root_type": "Liability", "name": ("like", "%Jaminan%")},
		pluck="name", limit=1,
	)
	assert jaminan, "Tidak ada akun Jaminan bertipe Liability untuk diuji"
	jaminan = jaminan[0]
	customer = frappe.get_all("Customer", pluck="name", limit=1)
	assert customer, "Butuh minimal satu Customer"
	customer = customer[0]

	docs, types = [], []
	try:
		t_in = _make_type("JMNPE", "Cash Inflow", jaminan)
		types.append(t_in)
		doc_in = _make_doc(t_in, company, bank["name"], receive_from=customer)
		docs.append(doc_in)
		frappe.db.set_value("Pending Cash", doc_in.name, "validated", 1)
		doc_in.reload()
		_pay(doc_in)

		# --- funding dibaca dari sisi KREDIT jurnalnya -------------------------
		pe = _pe(company, bank["account"], "Customer", customer, "Receive", doc_in.name, BILL)
		funding = pe._pending_cash_funding()
		assert len(funding) == 1, funding
		assert funding[0]["account"] == jaminan, funding[0]
		assert funding[0]["party"] == customer, funding[0]
		assert flt(funding[0]["base_amount"]) == TOTAL, funding[0]

		# --- baris GL: Dr Jaminan + sisanya Dr Bank ---------------------------
		gl = []
		pe.add_bank_gl_entries(gl)
		rows = _by_account(gl)
		assert flt(rows[jaminan].get("debit")) == TOTAL, rows[jaminan]
		assert not flt(rows[jaminan].get("credit")), rows[jaminan]
		assert flt(rows[bank["account"]].get("debit")) == BILL - TOTAL, rows[bank["account"]]
		print(f"Receive OK: Dr {jaminan} {TOTAL:,.0f} + Dr {bank['account']} {BILL - TOTAL:,.0f}")

		# --- jaminan MELEBIHI tagihan: kelebihannya keluar lewat bank (Cr) ----
		pe_kecil = _pe(company, bank["account"], "Customer", customer, "Receive", doc_in.name, 1_000_000)
		gl = []
		pe_kecil.add_bank_gl_entries(gl)
		rows = _by_account(gl)
		assert flt(rows[jaminan].get("debit")) == TOTAL, rows[jaminan]
		assert flt(rows[bank["account"]].get("credit")) == TOTAL - 1_000_000, rows[bank["account"]]
		print("Receive lebih-bayar OK: sisa jaminan dikembalikan lewat bank")

		# --- arah salah ditolak -----------------------------------------------
		from erpnext_custom.overrides.payment_entry import _apply_pending_cash

		pe_salah = _pe(company, bank["account"], "Supplier", customer, "Pay", doc_in.name, BILL)
		try:
			_apply_pending_cash(pe_salah)
			raise AssertionError("Pending Cash Cash Inflow seharusnya ditolak di Payment Entry Pay")
		except frappe.ValidationError:
			pass
		print("guard arah OK")
		print("PENDING CASH RECEIVE OK")
	finally:
		_cleanup(docs, types)

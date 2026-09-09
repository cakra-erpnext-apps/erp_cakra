"""Cek arah uang Pending Cash (Keluar / Masuk). Jalankan:

	bench --site erp.localhost execute erp.fico.doctype.pending_cash.test_pending_cash_direction.run

Membuat Type + dokumen uji, membayarnya supaya jurnalnya terbentuk, memeriksa sisi
debit/kredit dan party-nya, lalu menghapus semuanya lagi.
"""

import frappe
from frappe.utils import flt, getdate

from erp.fico.doctype.pending_cash import pending_cash as pc

TOTAL = 5_000_000


def _bank(company):
	row = frappe.get_all(
		"Bank Account",
		filters={"is_company_account": 1, "company": company, "disabled": 0},
		fields=["name", "account"],
		limit=1,
	)
	return row[0] if row else None


def _make_type(code, direction, account):
	# Kodenya diberi awalan UJI: nama master = code (autoname field:code), jadi kode polos
	# bisa bentrok dengan master sungguhan yang kebetulan bernama sama.
	doc = frappe.get_doc({
		"doctype": "Pending Cash Type", "code": f"UJI{code}",
		"direction": direction, "advance_account": account,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_doc(type_name, company, bank, **party):
	doc = frappe.get_doc({
		"doctype": "Pending Cash", "pending_cash_type": type_name, "date": getdate(),
		"company": company, "total": TOTAL, "bank_account": bank, **party,
	})
	doc.insert(ignore_permissions=True)
	return doc


def _je_rows(je_name):
	"""{akun: (debit, credit)} dari jurnal yang terbentuk."""
	rows = frappe.get_all(
		"Journal Entry Account",
		filters={"parent": je_name},
		fields=["account", "debit", "credit", "party_type", "party"],
	)
	return {r.account: r for r in rows}


def _pay(doc):
	res = pc.bulk_pay([doc.name])
	assert not res["failed"], res["failed"]
	doc.reload()
	assert doc.journal_entry, "Paid tapi jurnalnya tidak terbentuk"
	assert frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus") == 1, "jurnal belum submit"
	return _je_rows(doc.journal_entry)


def _cleanup(docs, types):
	for doc in docs:
		try:
			doc.reload()
			if doc.paid:
				doc.flags.delete_journal = True
				pc.bulk_unpaid([doc.name])
				doc.reload()
			if doc.journal_entry:
				frappe.db.set_value("Pending Cash", doc.name, "journal_entry", None)
			frappe.delete_doc("Pending Cash", doc.name, force=1, ignore_permissions=True)
		except Exception as e:
			print("bersih-bersih dokumen:", e)
	for t in types:
		try:
			frappe.delete_doc("Pending Cash Type", t, force=1, ignore_permissions=True)
		except Exception as e:
			print("bersih-bersih type:", e)
	frappe.db.commit()


def run():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	bank = _bank(company)
	assert bank, f"Tidak ada Bank Account company untuk {company}"

	# Jaminan yang DITERIMA adalah kewajiban (kita menahan uang orang), jadi akunnya
	# harus Liability. Ada juga "Piutang atas Jaminan" bertipe Asset untuk jaminan yang
	# kita setor keluar -- kalau tersaring ke situ, uji ini kehilangan maknanya.
	masuk_account = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "root_type": "Liability", "name": ("like", "%Jaminan%")},
		pluck="name", limit=1,
	)
	assert masuk_account, "Tidak ada akun Jaminan bertipe Liability untuk diuji"
	masuk_account = masuk_account[0]

	customer = frappe.get_all("Customer", pluck="name", limit=1)
	assert customer, "Butuh minimal satu Customer"
	customer = customer[0]
	supplier = frappe.get_all("Supplier", pluck="name", limit=1)

	docs, types = [], []
	try:
		# --- arah Masuk: Dr Bank / Cr Jaminan ---------------------------------
		t_in = _make_type("JMN", "Cash Inflow", masuk_account)
		types.append(t_in)
		doc_in = _make_doc(t_in, company, bank["name"], receive_from=customer)
		docs.append(doc_in)

		assert doc_in.direction == "Cash Inflow", doc_in.direction
		# Sisi yang tidak dipakai dikosongkan, supaya tidak terbawa ke jurnal.
		assert not doc_in.pay_to, doc_in.pay_to

		frappe.db.set_value("Pending Cash", doc_in.name, "validated", 1)
		doc_in.reload()
		rows = _pay(doc_in)

		assert flt(rows[bank["account"]].debit) == TOTAL, rows[bank["account"]]
		assert flt(rows[bank["account"]].credit) == 0
		assert flt(rows[masuk_account].credit) == TOTAL, rows[masuk_account]
		assert flt(rows[masuk_account].debit) == 0
		# Akun Jaminan account_type-nya kosong, jadi party boleh menempel.
		assert rows[masuk_account].party_type == "Customer", rows[masuk_account]
		assert rows[masuk_account].party == customer
		print(f"Masuk OK: Dr {bank['account']} / Cr {masuk_account} (party {customer})")

		# --- party wajib sesuai arah ------------------------------------------
		try:
			_make_doc(t_in, company, bank["name"])
			raise AssertionError("arah Masuk tanpa Receive From seharusnya ditolak")
		except frappe.ValidationError:
			pass
		print("guard party OK")

		# --- arah Keluar: perilaku lama tidak berubah -------------------------
		if not supplier:
			print("Lewat regresi arah Keluar: belum ada Supplier.")
			return
		keluar_account = frappe.get_all(
			"Account",
			filters={"company": company, "is_group": 0, "root_type": "Asset",
			         "name": ("like", "%Uang Muka Pembelian%")},
			pluck="name", limit=1,
		)
		assert keluar_account, "Tidak ada akun Uang Muka Pembelian untuk diuji"
		keluar_account = keluar_account[0]

		t_out = _make_type("KLR", "Cash Outflow", keluar_account)
		types.append(t_out)
		doc_out = _make_doc(t_out, company, bank["name"], pay_to=supplier[0])
		docs.append(doc_out)

		assert doc_out.direction == "Cash Outflow", doc_out.direction
		assert not doc_out.receive_from
		frappe.db.set_value("Pending Cash", doc_out.name, "validated", 1)
		doc_out.reload()
		rows = _pay(doc_out)

		assert flt(rows[keluar_account].debit) == TOTAL, rows[keluar_account]
		assert flt(rows[bank["account"]].credit) == TOTAL, rows[bank["account"]]
		assert rows[keluar_account].party_type == "Supplier", rows[keluar_account]
		assert rows[keluar_account].party == supplier[0]
		print(f"Keluar OK: Dr {keluar_account} / Cr {bank['account']} (party {supplier[0]})")
		print("PENDING CASH DIRECTION OK")
	finally:
		_cleanup(docs, types)

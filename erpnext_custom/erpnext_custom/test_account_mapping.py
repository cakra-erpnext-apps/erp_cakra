"""Cek report Account Mapping = akun yang dipakai transaksi.

bench --site erp.localhost execute erpnext_custom.test_account_mapping.run
"""

import frappe
from erpnext.accounts.party import get_party_account

from erpnext_custom.erpnext_custom.report.account_mapping.account_mapping import execute
from erpnext_custom.item_scope import item_account


def run(company="PT CMI"):
	_, rows = execute({"company": company})
	n = 0
	for r in rows:
		if r["akun_untuk"] in ("Piutang", "Hutang"):
			assert r["account"] == get_party_account(r["jenis"], r["ref"], company), r
		elif r["akun_untuk"] == "Pemakaian" and r["sumber"] in ("Item", "Grup"):
			assert r["account"] == item_account(r["ref"], company, "expense_account"), r
		elif r["akun_untuk"] == "Penjualan" and r["sumber"] in ("Item", "Grup"):
			assert r["account"] == item_account(r["ref"], company, "income_account"), r
		else:
			continue
		n += 1
	assert n, "tidak ada baris yang dicek"
	print(f"OK: {n} baris cocok dari {len(rows)}")

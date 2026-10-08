"""Cek halaman Compare Jurnal: tiap tabel seimbang, akun sisi ERPNext ada di CoA dengan nama sama.

bench --site erp.localhost execute erpnext_custom.test_compare_jurnal.run
"""

import frappe

from erpnext_custom.compare import BEDA, JOURNAL_CASES, SAMA, SETTING


def run(company="PT CMI"):
	names = {a.account_number: a.account_name for a in frappe.get_all(
		"Account", filters={"company": company}, fields=["account_number", "account_name"])}
	n = 0
	for modul, asc, erp in JOURNAL_CASES:
		for side, blocks in (("Ascend", asc), ("ERPNext", erp)):
			for trx, _review, status, lines in blocks:
				if lines:
					assert round(sum(l[2] for l in lines) - sum(l[3] for l in lines), 2) == 0, (modul, side, trx)
				if side == "ERPNext":
					assert status in (SAMA, BEDA, SETTING), (modul, trx, status)
					for code, name, _d, _k in lines:
						if not code:  # baris ringkasan (mis. akun-akun laba rugi yang dinolkan PCV)
							continue
						assert names.get(code) == name, (modul, trx, code, name, names.get(code))
						n += 1
	print(f"OK: {len(JOURNAL_CASES)} kasus seimbang, {n} baris akun ERPNext cocok dengan CoA")

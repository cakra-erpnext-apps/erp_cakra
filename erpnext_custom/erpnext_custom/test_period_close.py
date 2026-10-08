"""Cek tutup laba rugi ala Ascend (period_close.py): bulanan dan tahunan otomatis. Semua di-rollback.

bench --site erp.localhost execute erpnext_custom.test_period_close.run
"""

import frappe
from erpnext.accounts.utils import get_balance_on, get_fiscal_year
from frappe.utils import add_days, flt, getdate

COMPANY = "PT CMI"
MONTH = "3210.002 - Laba Rugi Bulan Berjalan - PC"
YEAR = "3210.001 - Laba Rugi Tahun Berjalan - PC"
LAST = "3210.003 - Laba Rugi Tahun Lalu - PC"


def _pl_profit(start, end):
	rows = frappe.db.sql("""
		select sum(g.credit - g.debit) from `tabGL Entry` g join tabAccount a on a.name = g.account
		where g.company = %s and g.is_cancelled = 0 and g.is_opening = 'No' and a.report_type = 'Profit and Loss'
		and g.posting_date between %s and %s and g.voucher_type != 'Period Closing Voucher'""",
		(COMPANY, start, end))
	return flt(rows[0][0], 2)


def _pcv(fy, start, end):
	pcv = frappe.get_doc({"doctype": "Period Closing Voucher", "company": COMPANY, "fiscal_year": fy,
	                      "transaction_date": end, "period_start_date": start, "period_end_date": end,
	                      "closing_account_head": MONTH, "remarks": "uji"})
	pcv.insert()
	pcv.submit()
	pcv.reload()
	return pcv


def _je_lines(name):
	return {a.account: flt(a.debit - a.credit, 2) for a in frappe.get_doc("Journal Entry", name).accounts}


def run(month_end="2026-09-30"):
	frappe.set_user("Administrator")
	cs = frappe.get_single("ERPNext Custom Setting")
	cs.set("period_close_accounts", [{"company": COMPANY, "month_account": MONTH, "year_account": YEAR,
	                                  "last_year_account": LAST, "monthly_roll": 1, "yearly_roll": 1}])
	cs.save(ignore_permissions=True)
	frappe.db.set_single_value("Accounts Settings", "use_legacy_controller_for_pcv", 1)  # GL sinkron di tes
	try:
		fy, fy_start, fy_end = get_fiscal_year(month_end, company=COMPANY)
		next_day = add_days(fy_end, 1)
		if not get_fiscal_year(next_day, company=COMPANY, boolean=True):
			y = getdate(next_day).year
			frappe.get_doc({"doctype": "Fiscal Year", "year": f"Uji {y}", "year_start_date": f"{y}-01-01",
			                "year_end_date": f"{y}-12-31"}).insert(ignore_permissions=True)

		# 1. PCV bulan biasa: hanya gulung bulanan, tanpa pindah tahunan.
		expected = _pl_profit(fy_start, month_end)
		assert expected, "tidak ada laba rugi di periode uji"
		pcv = _pcv(fy, fy_start, month_end)
		je = frappe.get_doc("Journal Entry", pcv.custom_roll_journal_entry)
		assert getdate(je.posting_date) == getdate(add_days(month_end, 1)) and je.is_system_generated == 1
		assert _je_lines(je.name) == {MONTH: expected, YEAR: -expected}, _je_lines(je.name)
		assert not pcv.custom_year_roll_journal_entry
		assert _pl_profit(fy_start, month_end) == expected  # laporan Laba Rugi utuh
		pcv.cancel()
		assert frappe.db.get_value("Journal Entry", je.name, "docstatus") == 2

		# 2. PCV akhir fiscal year: gulung bulanan + seluruh Tahun Berjalan pindah ke Tahun Lalu.
		last_before = get_balance_on(LAST, date=next_day, company=COMPANY)
		pcv = _pcv(fy, fy_start, fy_end)
		assert pcv.custom_roll_journal_entry and pcv.custom_year_roll_journal_entry, pcv.as_dict()
		ye = frappe.get_doc("Journal Entry", pcv.custom_year_roll_journal_entry)
		assert getdate(ye.posting_date) == getdate(next_day) and ye.is_system_generated == 1
		assert flt(get_balance_on(YEAR, date=next_day, company=COMPANY), 2) == 0  # Tahun Berjalan mulai nol
		moved = _je_lines(ye.name)[LAST]
		assert flt(get_balance_on(LAST, date=next_day, company=COMPANY) - last_before, 2) == moved
		pcv.cancel()
		assert frappe.db.get_value("Journal Entry", ye.name, "docstatus") == 2

		print(f"OK: bulanan {expected:,.2f} ke Tahun Berjalan; tahunan {-moved:,.2f} ke Tahun Lalu tanggal "
		      f"{next_day}, Tahun Berjalan nol; batal PCV membatalkan keduanya")
	finally:
		frappe.db.rollback()

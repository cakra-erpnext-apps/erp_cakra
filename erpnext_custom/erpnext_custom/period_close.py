"""Tutup laba rugi ala Ascend: tiap bulan dan tiap tahun otomatis.

Ascend (AS_CAKRA):
  akhir bulan  PL/          Dr Ikhtisar L/R / Cr 3210.002 Laba Rugi Bulan Berjalan (= laba bulan itu)
  tanggal 1    PL-ANNUAL/   Dr 3210.002 / Cr 3210.001 Laba Rugi Tahun Berjalan
  ganti tahun  ADJ/ manual  Dr 3210.001 / Cr 3210.003 Laba Rugi Tahun Lalu (mis. ADJ/0128/CMI/22
                            "LABA RUGI TAHUN 2022"); tidak konsisten, 2025 tertinggal sebagian.

Di sini: accounting membuat Period Closing Voucher tiap bulan dengan Closing Account = akun Bulan
Berjalan. PCV-nya sendiri menutup akun laba rugi (laporan Laba Rugi tetap utuh). Saat PCV di-submit:
  - Bulanan Otomatis : JE tanggal period_end+1, Dr Bulan Berjalan / Cr Tahun Berjalan (dibalik kalau rugi).
  - Tahunan Otomatis : kalau period_end = akhir fiscal year, JE kedua tanggal yang sama, SELURUH saldo
                       Tahun Berjalan ke Tahun Lalu, jadi Tahun Berjalan mulai nol. Tanggal 1 Januari,
                       bukan 31 Desember seperti Ascend, karena 31 Desember sudah dikunci PCV.
Setting per company: ERPNext Custom Setting > Journal Entry > Tutup Laba Rugi Bulanan
(tabel period_close_accounts, child "CMI Period Close").
"""

import frappe
from erpnext.accounts.utils import get_balance_on, get_fiscal_year
from frappe import _
from frappe.utils import add_days, flt, getdate


def _row(doc):
	# get_single, bukan get_cached_doc: cache Single bisa datang tanpa child table.
	for r in frappe.get_single("ERPNext Custom Setting").get("period_close_accounts") or []:
		if r.company == doc.company and r.month_account == doc.closing_account_head:
			return r
	return None


def _precision():
	return frappe.get_precision("GL Entry", "debit")


def period_profit(doc):
	"""Laba periode PCV (positif = laba), dihitung dengan rumus PCV sendiri: sisi akun penutup."""
	doc.get_pcv_gl_entries()
	return flt(sum(flt(g.credit) - flt(g.debit) for g in doc.closing_account_gle), _precision())


def _make_je(doc, posting_date, amount, from_acc, to_acc, remark):
	"""amount > 0: Dr from_acc / Cr to_acc (saldo kredit = laba dipindah); < 0 dibalik."""
	if not get_fiscal_year(posting_date, company=doc.company, boolean=True):
		frappe.throw(_("Fiscal Year untuk tanggal {0} belum ada. Buat dulu di Accounting > Fiscal Year, "
		               "baru submit Period Closing Voucher ini.").format(posting_date))
	dr, cr = (from_acc, to_acc) if amount > 0 else (to_acc, from_acc)
	je = frappe.get_doc({
		"doctype": "Journal Entry",
		"voucher_type": "Journal Entry",
		"company": doc.company,
		"posting_date": posting_date,
		"user_remark": remark,
		"accounts": [
			{"account": dr, "debit_in_account_currency": abs(amount)},
			{"account": cr, "credit_in_account_currency": abs(amount)},
		],
	})
	je.is_system_generated = 1  # ikut filter "Sembunyikan Jurnal Otomatis"
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def on_submit(doc, method=None):
	row = _row(doc)
	if not row:
		return
	next_day = add_days(doc.period_end_date, 1)

	if row.monthly_roll:
		amount = period_profit(doc)
		if amount:
			doc.db_set("custom_roll_journal_entry", _make_je(
				doc, next_day, amount, row.month_account, row.year_account,
				_("Gulung laba rugi bulan berjalan ke tahun berjalan, {0} ({1} s/d {2})").format(
					doc.name, doc.period_start_date, doc.period_end_date)))

	fy_end = frappe.db.get_value("Fiscal Year", doc.fiscal_year, "year_end_date")
	if row.yearly_roll and row.last_year_account and getdate(doc.period_end_date) == getdate(fy_end):
		# saldo kredit Tahun Berjalan per 1 Januari, sudah termasuk gulungan Desember di atas
		amount = flt(-get_balance_on(row.year_account, date=next_day, company=doc.company), _precision())
		if amount:
			doc.db_set("custom_year_roll_journal_entry", _make_je(
				doc, next_day, amount, row.year_account, row.last_year_account,
				_("Pindah laba rugi tahun {0} ke laba rugi tahun lalu, {1}").format(doc.fiscal_year, doc.name)))


def on_cancel(doc, method=None):
	# tahunan dulu: ia dihitung dari saldo sesudah gulungan bulanan
	for field in ("custom_year_roll_journal_entry", "custom_roll_journal_entry"):
		name = doc.get(field)
		if name and frappe.db.get_value("Journal Entry", name, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", name)
			je.flags.ignore_permissions = True
			je.cancel()

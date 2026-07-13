"""Bawa perubahan yang hidup di DB (bukan di file) ikut terbawa saat deploy.

Tiga hal ini tidak bisa dititipkan lewat kode saja:

1. Layout dashboard tersimpan sebagai record `CRM Dashboard`. Kode hanya menyediakan
   layout *default*, dan create_default_manager_dashboard() sengaja TIDAK menimpa
   record yang sudah ada. Tanpa patch ini, site lama tetap memakai layout usangnya --
   yang chart-nya masih bernama `ongoing_deals` dan sudah tidak punya fungsi, jadi
   sebagian besar dashboard kosong.

2. `CRM Settings.default_valid_till` menentukan berapa hari validity_date quotation
   baru. Kosong = tidak terisi otomatis = panel "Expiring in 7 days" selalu nol.

3. validity_date quotation LAMA. Print format membaca validity_date, sementara form
   dulu hanya mengisi `validity` (teks bebas), sehingga baris Validity di kertas
   quotation selalu kosong.

Aman dijalankan berulang: masing-masing langkah memeriksa keadaan lebih dulu.
"""

import frappe

DEFAULT_VALIDITY_DAYS = "30"


def execute():
	_reset_dashboard_layout()
	_set_default_validity_days()
	_backfill_quotation_validity_date()


def _reset_dashboard_layout():
	"""Paksa layout dashboard ke default terbaru.

	Layout lama menunjuk chart yang fungsinya sudah tidak ada (sisa rename
	Deal -> Inquiry), jadi menimpanya adalah perbaikan, bukan kehilangan.
	"""
	from crm_cakra.fcrm.doctype.crm_dashboard.crm_dashboard import (
		create_default_manager_dashboard,
	)

	create_default_manager_dashboard(force=True)


def _set_default_validity_days():
	"""Isi default masa berlaku quotation bila belum di-set. Nilai yang sudah ada
	dihormati -- jangan menimpa keputusan admin."""
	current = frappe.db.get_single_value("CRM Settings", "default_valid_till")
	if not (current or "").strip():
		frappe.db.set_single_value("CRM Settings", "default_valid_till", DEFAULT_VALIDITY_DAYS)


def _backfill_quotation_validity_date():
	"""validity_date = date + default hari, hanya untuk yang masih kosong."""
	days = frappe.utils.cint(
		frappe.db.get_single_value("CRM Settings", "default_valid_till")
	) or frappe.utils.cint(DEFAULT_VALIDITY_DAYS)

	rows = frappe.get_all(
		"CRM Quotation",
		filters={"validity_date": ["is", "not set"], "date": ["is", "set"]},
		fields=["name", "date"],
	)
	for r in rows:
		frappe.db.set_value(
			"CRM Quotation",
			r.name,
			"validity_date",
			frappe.utils.add_days(r.date, days),
			update_modified=False,
		)

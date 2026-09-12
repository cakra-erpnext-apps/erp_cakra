"""Proforma Invoice — penagihan sementara, TABEL SENDIRI (`tabProforma Invoice`).

Kenapa doctype sendiri: penomorannya berdiri sendiri (`PR-INV/0001/CMI/26`) dan tidak
ikut terseret apa pun yang menghitung dari tabel Sales Invoice.

Field-nya CERMIN Sales Invoice, dibangun ulang dari meta Sales Invoice tiap migrate
(erpnext_custom/proforma.py). Jadi field baru di invoice otomatis ikut ke sini, tidak
dirawat dua kali. Tabel ANAK sengaja dipakai bersama (Sales Invoice Item, Invoice
Container, Invoice BL, dst): yang dipisah dokumennya, bukan skema barisnya — dan itu yang
membuat tombol Import ke Sales Invoice cuma menyalin baris apa adanya.

Yang TIDAK ada di sini, beda dengan Sales Invoice: jurnal/GL, piutang, dan pembaruan
status billing Sales Order / Delivery Note. Controllernya sengaja `Document` polos, bukan
turunan SalesInvoice — mesin hitung ERPNext dipanggil langsung, jadi tidak ada satu pun
efek samping akuntansi yang bisa menyelinap masuk.
"""

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import money_in_words

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals

PREFIX = "PR-INV"
# Doctype ini sendiri; dipakai untuk mengembalikan penyamaran di _calculate_as_invoice.
MIRRORS = "Proforma Invoice"


class ProformaInvoice(Document):
	def autoname(self):
		# PR-INV/0001/CMI/26 — counter per (prefix, abbr company), tahun dari tanggal dokumen.
		abbr = frappe.db.get_value("Company", self.company, "abbr") if self.company else None
		self.name = make_autoname("%s/.####./%s/.YY." % (PREFIX, abbr or "CMI"), self.doctype, self)

	def validate(self):
		# Mesin hitung ERPNext (item amount, pajak, diskon, grand total) dipakai LANGSUNG.
		# Baris pajak & diskonnya sendiri sudah disiapkan hook before_validate yang sama
		# dengan Sales Invoice (erpnext_custom.overrides.sales_invoice.before_validate).
		if self.get("items"):
			self._calculate_as_invoice()
		self.set_total_in_words()
		# Field `status` ikut dicermin dan dipakai list view sebagai indikator. Proforma
		# tidak punya siklus piutang, jadi statusnya cukup mengikuti docstatus.
		self.status = "Draft"

	def _calculate_as_invoice(self):
		"""Hitung total dengan MENYAMAR sebagai Sales Invoice.

		Mesin hitung ERPNext bercabang lewat `doc.doctype` yang di-hardcode: daftar doctype
		penjualan di `calculate_totals`, dan penurunan nama doctype anak `"<doctype> Item"`
		di rincian pajak. Tanpa penyamaran ini proforma jatuh ke cabang PEMBELIAN lalu pecah
		(`tax.category` tidak ada di Sales Taxes and Charges).

		Menyamar juga lebih BENAR di sini: baris itemnya memang `Sales Invoice Item`.
		`meta` disentuh dulu supaya ter-cache (ia cached_property), jadi yang berubah HANYA
		string doctype-nya — struktur field tetap milik Proforma Invoice.
		"""
		self.meta  # noqa: B018 — kunci meta Proforma Invoice sebelum doctype disamarkan
		self.doctype = "Sales Invoice"
		try:
			calculate_taxes_and_totals(self)
		finally:
			self.doctype = MIRRORS

	def is_rounded_total_disabled(self):
		# Dipakai mesin hitung ERPNext (set_rounded_total); aslinya method AccountsController,
		# yang sengaja TIDAK diwarisi controller ini (lihat docstring modul).
		if self.meta.get_field("disable_rounded_total"):
			return self.disable_rounded_total
		return frappe.db.get_single_value("Global Defaults", "disable_rounded_total")

	def is_internal_transfer(self):
		# Idem: dipanggil mesin hitung saat menghitung outstanding. Proforma tidak pernah
		# transaksi antar-perusahaan — tidak ada customer internal di sini.
		return False

	def set_total_in_words(self):
		import erpnext

		self.in_words = money_in_words(
			self.get("rounded_total") or self.get("grand_total") or 0, self.currency
		)
		self.base_in_words = money_in_words(
			self.get("base_rounded_total") or self.get("base_grand_total") or 0,
			erpnext.get_company_currency(self.company) if self.company else None,
		)

	def get_print_settings(self):
		# Sama dengan Sales Invoice: setelan yang tampil di sidebar print view dan tersimpan
		# per dokumen (lihat public/js/print_view.js).
		fields = super().get_print_settings() or []
		fields += ["invoice_title", "print_as_currency", "print_rate", "print_decimal",
		           "printed_by", "branch_office"]
		return fields

	def on_submit(self):
		self.db_set("status", "Submitted")
		self.db_set("custom_validated_by", frappe.session.user)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		self.db_set("custom_voided_by", frappe.session.user)

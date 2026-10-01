"""Proforma Invoice — penagihan sementara, TABEL SENDIRI (`tabProforma Invoice`).

Kenapa doctype sendiri: penomorannya berdiri sendiri (`PR-INV/0001/CMI/26`) dan tidak
ikut terseret apa pun yang menghitung dari tabel Sales Invoice.

Field-nya CERMIN Sales Invoice, dibangun ulang dari meta Sales Invoice tiap migrate
(erpnext_custom/proforma.py). Jadi field baru di invoice otomatis ikut ke sini, tidak
dirawat dua kali. Tabel ANAK sengaja dipakai bersama (Sales Invoice Item, Invoice
Container, Invoice BL, dst): yang dipisah dokumennya, bukan skema barisnya — dan itu yang
membuat tombol Import ke Sales Invoice cuma menyalin baris apa adanya.

Yang TIDAK ada di sini, beda dengan Sales Invoice: jurnal/GL, piutang, dan pembaruan
status billing Sales Order / Delivery Note. Controllernya turunan `TransactionBase`, BUKAN
SalesInvoice/AccountsController — mesin hitung ERPNext dipanggil langsung, jadi tidak ada
satu pun efek samping akuntansi yang bisa menyelinap masuk. TransactionBase dipakai cuma
untuk `process_item_selection` (dipanggil form saat Item dipilih: UOM, conversion factor,
harga); ia tidak menjurnal apa pun.
"""

import re

import frappe
from frappe import _
from frappe.model.naming import getseries, parse_naming_series
from frappe.utils import money_in_words

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from erpnext.utilities.transaction_base import TransactionBase

# Doctype ini sendiri; dipakai untuk mengembalikan penyamaran di _calculate_as_invoice.
MIRRORS = "Proforma Invoice"


class ProformaInvoice(TransactionBase):
	def autoname(self):
		"""Nomor dari naming series (pola diatur di Document Naming Settings).

		Bedanya dengan Frappe: counter Frappe dikunci oleh teks SEBELUM `####`, jadi
		`PR-INV/.####./.cmi_company_abbr./.cmi_yy.` tidak pernah reset. Di sini kuncinya
		= SEMUA bagian pola selain nomor (`PR-INV/CMI/26`), jadi counter reset per company
		dan per tahun, di posisi mana pun `####` ditaruh."""
		series = self.naming_series
		# Seri yang bukan pilihan proforma (mis. ikut tersalin dari Sales Invoice) -> default.
		if series not in self.meta.get_naming_series_options():
			series = self.meta.get_field("naming_series").default
			self.naming_series = series
		digits = []
		full = parse_naming_series(series, doc=self, number_generator=lambda _p, d: digits.append(d) or "\0")
		if not digits:
			frappe.throw(_("Naming series {0} harus memuat .####.").format(series))
		key = re.sub("/{2,}", "/", full.replace("\0", ""))
		# Lompati nomor yang sudah terpakai (mis. dari penomoran lama yang counternya beda).
		while True:
			name = full.replace("\0", getseries(key, digits[0]))
			if not frappe.db.exists(self.doctype, name):
				break
		self.name = name

	def validate(self):
		# Company hidden & tidak `reqd` di cermin (lihat proforma._mirror_fields).
		if not self.company:
			frappe.throw(_("Company wajib diisi."))
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

	def fetch_item_details(self, item):
		# Menyamar lagi (lihat _calculate_as_invoice): get_item_details menurunkan doctype anak
		# dari `ctx.doctype + " Item"` ("Proforma Invoice Item" tidak ada) dan memilih UOM
		# jual hanya untuk doctype penjualan bawaan. Barisnya memang Sales Invoice Item.
		self.meta  # noqa: B018
		self.doctype = "Sales Invoice"
		try:
			return super().fetch_item_details(item)
		finally:
			self.doctype = MIRRORS

	@frappe.whitelist()
	def apply_shipping_rule(self):
		# Dipanggil form saat Shipping Rule terisi (salinan AccountsController.apply_shipping_rule).
		if self.get("shipping_rule"):
			frappe.get_doc("Shipping Rule", self.shipping_rule).apply(self)
			self.calculate_taxes_and_totals()

	def calculate_taxes_and_totals(self):
		# Dipanggil TransactionBase.process_item_selection sesudah item diisi.
		self._calculate_as_invoice()

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
		# per dokumen (lihat public/js/print_view.js). TIDAK memanggil super(): versi dasarnya
		# milik AccountsController, yang sengaja tidak diwarisi (tanpa itu print view error
		# dan sidebarnya kosong). Watermark PAID tidak ada: proforma tidak pernah dibayar.
		return ["compact_item_print", "print_uom_after_quantity", "print_taxes_with_zero_amount",
		        "invoice_title", "print_as_currency", "print_rate", "print_decimal",
		        "printed_by", "branch_office"]

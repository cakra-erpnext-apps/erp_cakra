# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from crm_cakra.fcrm.doctype.crm_cost_item.crm_cost_item import compute_amount


class CRMProcurement(Document):
	"""Permintaan harga ke tim Procurement, satu per Inquiry.

	Dokumen ini sengaja TIDAK menyalin field inquiry. Halamannya merender layout
	CRM Inquiry apa adanya, jadi apa pun yang berubah di inquiry langsung terlihat
	di sini tanpa sinkronisasi -- yang dimiliki dokumen ini cuma dua tabel biaya
	di bawahnya, yang memang tidak ada di inquiry.
	"""

	@staticmethod
	def default_list_data():
		"""Kolom daftar Procurement.

		Account dan Inquiry Date memang milik Inquiry, tapi disalin ke dokumen ini
		lewat fetch_from: mesin list view CRM menyaring, mencari, dan mengurutkan
		satu doctype saja, jadi kolom pinjaman harus ada sebagai field sungguhan.
		"""
		columns = [
			{"label": "No Procurement", "type": "Data", "key": "name", "width": "12rem"},
			{"label": "Status", "type": "Select", "key": "status", "width": "8rem"},
			{"label": "Account", "type": "Link", "key": "account", "width": "14rem"},
			{"label": "No Inquiry", "type": "Link", "key": "inquiry", "width": "12rem"},
			{"label": "Inquiry Date", "type": "Date", "key": "inquiry_date", "width": "9rem"},
			{"label": "Fixed Cost", "type": "Currency", "key": "total_fixed_cost", "width": "10rem", "align": "right"},
			{"label": "Variable Cost", "type": "Currency", "key": "total_variable_cost", "width": "10rem", "align": "right"},
			{"label": "Request Date", "type": "Datetime", "key": "submitted_on", "width": "10rem"},
			{"label": "Request By", "type": "Link", "key": "submitted_by", "width": "10rem"},
			{"label": "Approve Date", "type": "Datetime", "key": "approved_on", "width": "10rem"},
			{"label": "Approve By", "type": "Link", "key": "approved_by", "width": "10rem"},
			{"label": "Modified Date", "type": "Datetime", "key": "modified", "width": "10rem"},
			{"label": "Modified By", "type": "Link", "key": "modified_by", "width": "10rem"},
		]
		rows = [
			"name",
			"status",
			"account",
			"inquiry",
			"inquiry_date",
			"total_fixed_cost",
			"total_variable_cost",
			"submitted_on",
			"submitted_by",
			"requested_to",
			"approved_on",
			"approved_by",
			"remark",
			"marketing_cost",
			"margin",
			"owner",
			"creation",
			"modified",
			"modified_by",
			"_assign",
		]
		return {"columns": columns, "rows": rows}

	def validate(self):
		self.protect_approved_costing()
		self.total_fixed_cost = compute_amount(self.fixed_cost_items)
		self.total_variable_cost = compute_amount(self.variable_cost_items)
		self.advance_to_reviewing()
		# Marketing Cost = harga jual yang diisi Marketing di tabel Products inquiry.
		# Dibaca dari inquiry tiap simpan, bukan disalin sekali saat dibuat.
		self.marketing_cost = flt(frappe.db.get_value("CRM Inquiry", self.inquiry, "net_total"))
		self.margin = self.marketing_cost - (flt(self.total_fixed_cost) + flt(self.total_variable_cost))

	def protect_approved_costing(self):
		"""Costing yang sudah Approve beku, kecuali Remarks.

		Sel yang terkunci di halaman cuma kenyamanan; yang menahan perubahan
		lewat jalan lain (API, tab yang sudah lama terbuka) adalah pemeriksaan ini.
		Mengubah statusnya keluar dari Approve di simpanan yang sama = sengaja
		membuka kuncinya, jadi dibiarkan.
		"""
		before = self.get_doc_before_save()
		if not before or before.status != "Approve" or self.status != "Approve":
			return

		def angka(doc):
			return [
				(r.item_name, flt(r.qty), r.uom, flt(r.rate))
				for table in ("fixed_cost_items", "variable_cost_items")
				for r in doc.get(table) or []
			]

		if angka(self) != angka(before):
			frappe.throw(_("Costing sudah Approve -- hanya Remarks yang masih boleh diubah."))

	def advance_to_reviewing(self):
		"""Request -> Reviewing begitu baris biaya pertama diisi.

		Tanpa ini Reviewing butuh tombol sendiri yang cuma berarti "saya sudah
		mulai" -- padahal mengisi biaya sudah membuktikannya. Status yang lebih
		maju (Approve) tidak ditarik mundur.
		"""
		if self.status == "Request" and (self.fixed_cost_items or self.variable_cost_items):
			self.status = "Reviewing"

	def on_update(self):
		self.mirror_totals_to_inquiry()

	def mirror_totals_to_inquiry(self):
		"""Cerminkan total biaya ke field Fixed Cost / Variable Cost / Estimation Cost
		di Inquiry.

		Ditulis pakai set_value, bukan inquiry.save(): dua field itu read_only dan
		inquiry hasil impor lama sering gagal validasi field wajib -- menyimpan
		costing jadi gagal karena urusan yang sama sekali bukan costing.

		`modified` sengaja ikut terbarui walau akibatnya orang Procurement tercatat
		sebagai penyunting terakhir Inquiry: tanpa itu tab Inquiry yang sudah lama
		terbuka menyimpan seluruh dokumen berisi angka lama tanpa kena
		TimestampMismatchError, dan cerminan ini hilang diam-diam.

		Dokumen yang belum pernah punya satu baris biaya pun TIDAK mencerminkan
		apa-apa. Nolnya bukan pendapat, cuma dokumen kosong -- sementara ribuan
		inquiry lama mengisi kedua field itu manual. Tanpa penjagaan ini, menekan
		Submit to Procurement (yang membuat dokumennya) menghapus angka yang sudah
		ada di Inquiry. Begitu pernah ada barisnya, pencerminan berlaku penuh,
		termasuk kembali ke nol saat tabelnya sengaja dikosongkan.

		Statusnya lain soal: itu memang milik dokumen ini sejak baris pertama ada
		atau belum, jadi selalu dicerminkan.
		"""
		# Draft = belum diminta apa-apa; di inquiry itu kosong, bukan kata "Draft"
		# yang menyiratkan ada pekerjaan berjalan.
		values = {"procurement_status": "" if self.status == "Draft" else self.status}

		before = self.get_doc_before_save()
		pernah_ada_baris = bool(
			before and (before.get("fixed_cost_items") or before.get("variable_cost_items"))
		)
		if self.fixed_cost_items or self.variable_cost_items or pernah_ada_baris:
			values["estimasi_tarif"] = flt(self.total_fixed_cost)
			values["costing_procurement"] = flt(self.total_variable_cost)
			# Estimation Cost (annual_revenue) = jumlah kedua tabel. Dihitung di
			# sini, bukan diketik orang: angka yang dilihat Marketing harus sama
			# dengan yang disetujui procurement, tanpa perlu membuka dokumennya.
			values["annual_revenue"] = flt(self.total_fixed_cost) + flt(self.total_variable_cost)

		frappe.db.set_value("CRM Inquiry", self.inquiry, values)


def for_inquiry(inquiry: str) -> str | None:
	"""Nama dokumen procurement milik sebuah inquiry, kalau ada."""
	return frappe.db.get_value("CRM Procurement", {"inquiry": inquiry})

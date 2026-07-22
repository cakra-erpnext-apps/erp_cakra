import frappe
from frappe.model.document import Document

from erp.expedition import numbering


def _bl_payment_status(doc):
	"""Isi `payment_status` tiap baris BL: Unpaid / Partial / Paid (kosong kalau belum ada dokumen).

	Sebuah BL dianggap Paid kalau SEMUA dokumen uangnya sudah lunas — Invoice (uang masuk)
	maupun Expense Note (uang keluar). Cakupan dokumen: draft ikut, cancelled/void dibuang:
	  Invoice      -> docstatus != 2. Lunas HANYA kalau sudah submitted DAN outstanding habis
	                  (turun sendiri saat Payment Entry submit). Draft outstanding-nya 0 karena
	                  belum dihitung — tanpa cek docstatus, draft malah terbaca lunas.
	  Expense Note -> tidak void. Lunas = flag `paid` (di-set update_expense_note_paid_status
	                  saat Payment Entry submit). `validated` SENGAJA tidak disyaratkan: sama
	                  seperti label status EN di tabel BL, `paid` menang sendiri — dan di
	                  data legacy banyak EN paid yang tidak pernah ditandai validated.

	DITURUNKAN, tidak disimpan sebagai sumber kebenaran: dihitung ulang di onload (jadi selalu
	segar tiap form dibuka, tanpa perlu hook di Payment Entry) dan di validate (jadi nilai yang
	tersimpan ikut benar). Baris BL dicocokkan lewat STRING `bl_no` — sama seperti no_containers;
	invoice/EN tanpa bl_no tidak masuk BL mana pun.
	"""
	bls = doc.get("bls") or []
	if not bls:
		return
	# {bl_no: [lunas?, lunas?, ...]}
	per_bl = {b.bl_no: [] for b in bls if b.bl_no}
	if per_bl:
		si = frappe.get_meta("Sales Invoice")
		if si.has_field("custom_shipping_list") and si.has_field("custom_bl_no"):
			for iv in frappe.get_all(
				"Sales Invoice",
				filters={"custom_shipping_list": doc.name, "docstatus": ["!=", 2],
				         "custom_bl_no": ["in", list(per_bl)]},
				fields=["custom_bl_no", "docstatus", "outstanding_amount"],
			):
				lunas = iv.docstatus == 1 and (iv.outstanding_amount or 0) <= 0.005
				per_bl[iv.custom_bl_no].append(lunas)

		for e in frappe.get_all(
			"Expense Note",
			filters={"shipping_list": doc.name, "void": ["!=", 1],
			         "bl_no": ["in", list(per_bl)]},
			fields=["bl_no", "paid"],
		):
			per_bl[e.bl_no].append(bool(e.paid))

	for b in bls:
		flags = per_bl.get(b.bl_no) or []
		if not flags:
			b.payment_status = ""
		elif all(flags):
			b.payment_status = "Paid"
		elif any(flags):
			b.payment_status = "Partial"
		else:
			b.payment_status = "Unpaid"


class ShippingList(Document):
	def onload(self):
		# Status payment BL selalu dihitung ulang saat form dibuka -> tidak pernah basi
		# walau invoice/EN-nya dibayar tanpa Shipping List ikut disave.
		_bl_payment_status(self)

	def autoname(self):
		# Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
		# numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
		if self.flags.get("agent_draft"):
			self.name = numbering.draft_name()
			return
		# Dokumen normal: JANGAN set name di sini — biarkan Frappe memakai naming series
		# `SH/.type./.ABBR./.YY./.#####` (dikelola di Document Naming Settings; counter
		# reset per tipe+company+tahun). Format kini counter-DI-AKHIR: SH/SA.IMP/CMI/26/00001.

	def make_real_number(self):
		# Draft agent di-Confirm (assign_number): pakai naming series yang sama persis.
		return numbering.make_from_series(self)

	def validate(self):
		# Denormalised counts.
		self.bl_count = len(self.bls or [])
		self.container_count = len(self.containers or [])

		# Per-BL container counts (group containers by their BL no).
		counts = {}
		for c in self.containers or []:
			if c.bl:
				counts[c.bl] = counts.get(c.bl, 0) + 1
		for b in self.bls or []:
			b.no_containers = counts.get(b.bl_no, 0)

		_bl_payment_status(self)

		# Warn about containers pointing at a BL that isn't in the BLs table.
		bl_nos = {b.bl_no for b in self.bls or [] if b.bl_no}
		orphans = sorted({c.bl for c in self.containers or [] if c.bl and c.bl not in bl_nos})
		if orphans:
			frappe.msgprint(
				frappe._("Containers reference BL(s) not in the BLs table: {0}").format(", ".join(orphans)),
				indicator="orange",
				alert=True,
			)

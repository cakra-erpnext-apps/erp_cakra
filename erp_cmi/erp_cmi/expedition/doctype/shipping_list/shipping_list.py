import frappe
from frappe.model.document import Document

from erp_cmi.expedition import numbering


class ShippingList(Document):
	def autoname(self):
		# Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
		# numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
		if self.flags.get("agent_draft"):
			self.name = numbering.draft_name()
			return
		# SH/{type}/{number}/{company}/{year}
		self.shipping_list_no = self.make_real_number()
		self.name = self.shipping_list_no

	def make_real_number(self):
		return numbering.make_number("SH", self.type, "Packing List Type", date=self.date)

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

		# Warn about containers pointing at a BL that isn't in the BLs table.
		bl_nos = {b.bl_no for b in self.bls or [] if b.bl_no}
		orphans = sorted({c.bl for c in self.containers or [] if c.bl and c.bl not in bl_nos})
		if orphans:
			frappe.msgprint(
				frappe._("Containers reference BL(s) not in the BLs table: {0}").format(", ".join(orphans)),
				indicator="orange",
				alert=True,
			)

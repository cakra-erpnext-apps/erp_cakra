import frappe
from frappe.model.document import Document

from erp.expedition import numbering


class PackingList(Document):
	def autoname(self):
		# Draft buatan agent: nama sementara, nomor seri belum dipakai (lihat
		# numbering.assign_number — nomor asli diberikan saat user Save/Confirm).
		if self.flags.get("agent_draft"):
			self.name = numbering.draft_name()
			return
		# PL-SO/{type}/{number}/{company}/{year}
		self.packing_list_no = self.make_real_number()
		self.name = self.packing_list_no

	def make_real_number(self):
		return numbering.make_number("PL-SO", self.type, "Packing List Type", date=self.date)

	def validate(self):
		# Keep the denormalised item count in sync with the child rows.
		self.item_count = len(self.items or [])

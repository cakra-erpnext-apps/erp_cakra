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
		# Dokumen normal: biarkan Frappe pakai naming series `PL-SO/.type./.ABBR./.cmi_yy./.#####`
		# (dikelola di Document Naming Settings; counter reset per tipe+company+tahun).

	def make_real_number(self):
		# Draft agent di-Confirm (assign_number): pakai naming series yang sama persis.
		return numbering.make_from_series(self)

	def validate(self):
		# Keep the denormalised item count in sync with the child rows.
		self.item_count = len(self.items or [])
		# packing_list_no = nomor dokumen (name), disinkronkan untuk yang sudah bernomor.
		if self.name and not numbering.is_draft_name(self.name):
			self.packing_list_no = self.name

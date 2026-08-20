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
		# Dokumen normal: biarkan Frappe pakai naming series `PL/.type./.ABBR./.cmi_yyyy./.#####`
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


ROUTE_FIELDS = [f"route{n}" for n in range(1, 9)]


@frappe.whitelist()
def estimation_route(estimation: str):
	"""Delapan slot route sebuah CRM Estimation, apa adanya, beserta koordinatnya.

	Slot yang kosong TETAP dikembalikan (name None) supaya grid Route di Packing List
	selalu punya 8 baris pada posisi yang sama seperti di estimation-nya. Yang menyaring
	baris kosong adalah peta dan rantai route, bukan fungsi ini.

	Loading/Unloading estimation sengaja tidak dibawa: Packing List hanya memakai
	urutan route-nya.
	"""
	est = frappe.db.get_value("CRM Estimation", estimation, ROUTE_FIELDS, as_dict=True) or {}
	names = [est.get(f) for f in ROUTE_FIELDS]
	filled = [n for n in names if n]
	coords = {
		d.name: d
		for d in frappe.get_all(
			"Fleet Location",
			filters={"name": ["in", list(set(filled))]},
			fields=["name", "code", "latitude", "longitude"],
		)
	} if filled else {}

	points = []
	for name in names:
		c = coords.get(name) or {}
		points.append(
			{
				"name": name,
				"label": c.get("code") or name,
				"lat": c.get("latitude"),
				"lon": c.get("longitude"),
			}
		)
	return {"points": points}

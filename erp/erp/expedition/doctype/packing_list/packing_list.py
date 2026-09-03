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
		self.spread_party()
		# packing_list_no = nomor dokumen (name), disinkronkan untuk yang sudah bernomor.
		if self.name and not numbering.is_draft_name(self.name):
			self.packing_list_no = self.name

	def spread_party(self):
		"""Pihak di header (section Estimation and Customer) menurun ke tiap baris Items.

		Dijamin di server, bukan cuma di packing_list.js: baris bisa lahir dari mana saja
		(grid, draft agent, import) dan yang dipakai report adalah kolom di barisnya.
		Flag Packing List Party Read Only ON = baris TIDAK bisa diketik sendiri, jadi
		header selalu menang; OFF = header hanya mengisi yang masih kosong.
		"""
		locked = frappe.db.get_single_value("ERPNext Custom Setting", "packing_list_party_readonly")
		for row in self.items or []:
			for f in PARTY_FIELDS:
				if locked:
					row.set(f, self.get(f))
				elif self.get(f) and not row.get(f):
					row.set(f, self.get(f))


PARTY_FIELDS = ("customer", "estimation", "agent", "agent_estimation")
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


@frappe.whitelist()
def container_trips(packing_list: str):
	"""Trip Fleet per container PL ini, dari Dispatch Order-nya (1 PL = 1 DPO).

	Return: {packing_list_item(name baris PL): {"container_no", "trips"(jumlah trip),
	"rows"(baris Dispatch Order Route milik container itu, urut idx)}}. Dipakai kolom
	Trip di grid Items ("{n} trip", klik = modal rincian) — lihat packing_list.js.
	"""
	frappe.has_permission("Packing List", "read", packing_list, throw=True)
	dpo = frappe.db.get_value("Dispatch Order", {"packing_list": packing_list}, "name")
	if not dpo:
		return {}
	items = {
		r.name: r
		for r in frappe.get_all(
			"Dispatch Order Item",
			filters={"parent": dpo, "parenttype": "Dispatch Order"},
			fields=["name", "packing_list_item", "container_no"],
		)
	}
	out = {}
	for r in frappe.get_all(
		"Dispatch Order Route",
		filters={"parent": dpo, "parenttype": "Dispatch Order"},
		fields=["dpo_item", "trip", "driver", "vehicle", "chasis", "atd", "ata",
			"step", "step_type", "point_type", "point", "start", "end"],
		order_by="idx",
	):
		it = items.get(r.dpo_item)
		if not it or not it.packing_list_item:
			continue
		d = out.setdefault(it.packing_list_item, {"container_no": it.container_no, "trip_nos": set(), "rows": []})
		d["trip_nos"].add(r.trip or 1)
		d["rows"].append(r)
	for d in out.values():
		d["trips"] = len(d.pop("trip_nos"))
	return out

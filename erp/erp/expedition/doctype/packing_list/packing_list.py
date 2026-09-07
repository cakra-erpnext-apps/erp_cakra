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

	Loading/Unloading estimation ikut dikembalikan: dipakai mengisi Origin/Destination
	Location di Packing List saat estimation-nya dipilih.
	"""
	est = frappe.db.get_value(
		"CRM Estimation", estimation, ROUTE_FIELDS + ["loading", "unloading"], as_dict=True
	) or {}
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
	return {"points": points, "loading": est.get("loading"), "unloading": est.get("unloading")}


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


# ---- Tab Summary -------------------------------------------------------------------
# Empat section: Expense (baris Expense Note), Reimburse (baris EN reimburse + invoice
# IR-nya), Invoice (per Sales Invoice + itemnya), Margin (rekap).
# Angka per baris memakai mata uang dokumennya; rekap Margin memakai mata uang
# perusahaan (nominal x kurs) dan rumusnya SAMA dengan kolom Margin di list view
# (lihat erp.expedition.financials.list_financials) supaya tidak beda angka.


def _est_expense_map(names):
	"""{estimation: {item: amount}} dari baris Expense sebuah CRM Estimation."""
	names = [n for n in names if n]
	if not names:
		return {}
	out = {}
	for r in frappe.get_all(
		"CRM Estimation Detail",
		filters={"parent": ["in", list(set(names))], "parentfield": "expense_items"},
		fields=["parent", "type_id", "amount"],
	):
		out.setdefault(r.parent, {}).setdefault(r.type_id, r.amount)
	return out


@frappe.whitelist()
def summary(packing_list: str):
	frappe.has_permission("Packing List", "read", packing_list, throw=True)

	# Container -> pihak & estimation-nya (dipakai kolom "Sesuai Estimation" & Invoice).
	by_container = {}
	for r in frappe.get_all(
		"Packing List Item",
		filters={"parent": packing_list, "parenttype": "Packing List"},
		fields=["container_no", "customer", "agent", "estimation", "agent_estimation"],
	):
		if r.container_no:
			by_container[r.container_no] = r
	header = frappe.db.get_value(
		"Packing List", packing_list,
		["customer", "agent", "estimation", "agent_estimation"], as_dict=True
	) or frappe._dict()

	# ---- Expense ----
	ens = frappe.get_all(
		"Expense Note",
		filters={"packing_list": packing_list, "void": ["!=", 1]},
		fields=["name", "date", "currency", "conversion_rate", "is_reimburse", "reimburse_to_customer",
			"validated", "paid_amount", "tax_amount", "total_amount", "net_total"],
		order_by="date asc, name asc",
	)
	en_map = {e.name: e for e in ens}
	en_items = frappe.get_all(
		"Expense Note Item",
		filters={"parent": ["in", list(en_map)], "parenttype": "Expense Note"},
		fields=["name", "parent", "container_no", "expense_class", "item", "amount", "discount", "tax"],
		order_by="parent asc, idx asc",
	) if en_map else []

	# Paid Amount tersimpan per Expense Note, bukan per baris -> diprorata menurut porsi
	# net barisnya. Kalau tidak, satu EN dgn 5 baris terbaca dibayar 5 kali di total.
	net_of, en_net = {}, {}
	for it in en_items:
		net_of[it.name] = (it.amount or 0) - (it.discount or 0) + (it.tax or 0)
		en_net[it.parent] = en_net.get(it.parent, 0) + net_of[it.name]

	est_map = _est_expense_map(
		[r.get("estimation") for r in by_container.values()]
		+ [r.get("agent_estimation") for r in by_container.values()]
		+ [header.get("estimation"), header.get("agent_estimation")]
	)

	def sesuai_estimation(it):
		"""Item baris ini ada di baris Expense estimation-nya, dan nominalnya sama?"""
		party = by_container.get(it.container_no) or header
		for f in ("estimation", "agent_estimation"):
			prices = est_map.get(party.get(f)) or {}
			if it.item in prices:
				return "Ya" if abs((prices[it.item] or 0) - (it.amount or 0)) < 1 else "Tidak"
		return ""

	expense_rows = []
	for it in en_items:
		e = en_map[it.parent]
		net = net_of[it.name]
		share = net / en_net[it.parent] if en_net.get(it.parent) else 0
		expense_rows.append({
			"container": it.container_no or "",
			"en": it.parent,
			"date": str(e.date or ""),
			"expense_class": it.item or it.expense_class or "",
			"currency": e.currency or "",
			"rate": e.conversion_rate or 1,
			"amount": it.amount or 0,
			"discount": it.discount or 0,
			"tax": it.tax or 0,
			"net": net,
			"sesuai": sesuai_estimation(it),
			"validated": bool(e.validated),
			"paid": (e.paid_amount or 0) * share,
			"reimburse": bool(e.is_reimburse),
		})

	# ---- Invoice ----
	# EN reimburse -> invoice yang menariknya (child Sales Invoice Reimburse).
	inv_of_en = {}
	if en_map:
		for r in frappe.get_all(
			"Sales Invoice Reimburse",
			filters={"expense_note": ["in", list(en_map)], "parenttype": "Sales Invoice"},
			fields=["parent", "expense_note"],
		):
			inv_of_en.setdefault(r.expense_note, r.parent)

	# Invoice terhubung: sama jalurnya dgn financials.list_financials (custom field +
	# child Invoice Container), ditambah invoice reimburse yang menarik EN job ini.
	inv_names = set(frappe.get_all(
		"Sales Invoice", filters={"custom_packing_list": packing_list, "docstatus": ["!=", 2]}, pluck="name"
	))
	for r in frappe.get_all(
		"Invoice Container",
		filters={"source_doctype": "Packing List", "source_name": packing_list, "parenttype": "Sales Invoice"},
		fields=["parent"],
	):
		if r.parent:
			inv_names.add(r.parent)
	inv_names |= set(inv_of_en.values())

	invs = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", list(inv_names)], "docstatus": ["!=", 2]},
		fields=["name", "posting_date", "invoice_date", "customer", "currency", "conversion_rate",
			"docstatus", "base_total", "base_grand_total", "outstanding_amount", "custom_markup",
			"custom_tax_amount"],
		order_by="posting_date asc, name asc",
	) if inv_names else []
	inv_map = {iv.name: iv for iv in invs}

	inv_containers = {}
	for r in (frappe.get_all(
		"Invoice Container",
		filters={"parent": ["in", list(inv_map)], "parenttype": "Sales Invoice", "source_name": packing_list},
		fields=["parent", "container_no"],
	) if inv_map else []):
		if r.container_no:
			inv_containers.setdefault(r.parent, []).append(r.container_no)

	inv_items = {}
	for r in (frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ["in", list(inv_map)], "parenttype": "Sales Invoice"},
		fields=["parent", "item_name", "description", "net_amount", "amount"],
		order_by="parent asc, idx asc",
	) if inv_map else []):
		inv_items.setdefault(r.parent, []).append({
			"item_name": r.item_name or r.description or "",
			"net": r.net_amount or r.amount or 0,
		})

	def invoice_paid(iv):
		# Terbayar = grand total - sisa tagihan; keduanya dibawa ke mata uang perusahaan.
		if iv.docstatus != 1:
			return 0
		return (iv.base_grand_total or 0) - (iv.outstanding_amount or 0) * (iv.conversion_rate or 1)

	def invoice_estimation(iv):
		"""Estimation yang dipakai invoice ini: Agent bila pelanggannya si Agent."""
		for c in inv_containers.get(iv.name, []):
			row = by_container.get(c)
			if not row:
				continue
			if row.get("agent") and iv.customer == row.get("agent"):
				return row.get("agent_estimation") or ""
			if row.get("estimation"):
				return row.get("estimation")
		if header.get("agent") and iv.customer == header.get("agent"):
			return header.get("agent_estimation") or ""
		return header.get("estimation") or ""

	invoice_groups = [{
		"estimation": invoice_estimation(iv),
		"containers": inv_containers.get(iv.name, []),
		"invoice": iv.name,
		"date": str(iv.invoice_date or iv.posting_date or ""),
		"customer": iv.customer or "",
		"currency": iv.currency or "",
		"rate": iv.conversion_rate or 1,
		"tax": iv.custom_tax_amount or 0,
		"net": iv.base_grand_total or 0,
		"draft": iv.docstatus == 0,
		"items": inv_items.get(iv.name, []),
	} for iv in invs]

	# ---- Reimburse ----
	# Baris EN yang dicentang Reimburse + invoice IR yang menagihkannya. Invoice tipe
	# Reimburse yang belum menarik EN apa pun belum punya baris di sini.
	reimburse_rows = []
	for row in expense_rows:
		if not row["reimburse"]:
			continue
		e = en_map[row["en"]]
		iv = inv_map.get(inv_of_en.get(row["en"]))
		reimburse_rows.append(dict(row, **{
			"customer": e.reimburse_to_customer or "",
			"invoice": iv.name if iv else "",
			"invoice_date": str((iv.invoice_date or iv.posting_date) or "") if iv else "",
			"markup": bool(iv and iv.custom_markup),
			"invoice_paid": invoice_paid(iv) if iv else 0,
		}))

	# ---- Margin (mata uang perusahaan) ----
	company = frappe.defaults.get_global_default("company")
	rate_of = lambda d: d.get("conversion_rate") or 1  # noqa: E731
	# Expense = DPP (pajaknya berdiri sendiri di kolom sebelahnya); Invoice & Reimburse
	# = Net Total dokumennya (di sistem ini Net Total invoice = grand total).
	totals = {
		"currency": (company and frappe.get_cached_value("Company", company, "default_currency")) or "IDR",
		"expense": sum((e.total_amount or 0) * rate_of(e) for e in ens),
		"tax_expense": sum((e.tax_amount or 0) * rate_of(e) for e in ens),
		"invoice": sum(iv.base_grand_total or 0 for iv in invs),
		"tax_invoice": sum((iv.custom_tax_amount or 0) * rate_of(iv) for iv in invs),
		"reimburse": sum((e.net_total or 0) * rate_of(e) for e in ens if e.is_reimburse),
	}
	totals["margin"] = totals["invoice"] - totals["expense"]
	totals["margin_pct"] = round(totals["margin"] / totals["invoice"] * 100, 1) if totals["invoice"] else None

	return {
		"expenses": expense_rows,
		"reimburse": reimburse_rows,
		"invoices": invoice_groups,
		"totals": totals,
	}
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def unused_estimation_query(doctype, txt, searchfield, start, page_len, filters):
	"""Pilihan Est Customer / Est Agent: estimation yang BELUM dipakai Packing List mana pun.

	Syarat lainnya (purpose, disabled, validated, belum expired, customer_id) tetap dikirim
	dari set_query di packing_list.js sebagai `filters` biasa -- di sini hanya ditambah
	syarat "belum terpakai", yang tidak bisa diungkapkan lewat filter link biasa.

	`exclude_packing_list` = dokumen yang sedang dibuka: estimation yang dipakainya sendiri
	tetap boleh dipilih ulang (kalau tidak, mengosongkan lalu memilih lagi jadi mustahil).

	Baris Items ikut dihitung, bukan cuma header: kalau Packing List Party Read Only OFF,
	tiap baris boleh memakai estimation sendiri.

	Packing List VOID tidak dihitung -- dokumennya dibatalkan, jadi estimationnya bebas
	dipakai lagi. Yang CLOSED tetap dihitung: pekerjaannya benar-benar jalan, cuma selesai.
	"""
	filters = dict(filters or {})
	exclude = filters.pop("exclude_packing_list", None) or ""
	used = frappe.db.sql_list(
		"""
		select p.estimation from `tabPacking List` p
			where p.void = 0 and p.name != %(pl)s and p.estimation is not null
		union select p.agent_estimation from `tabPacking List` p
			where p.void = 0 and p.name != %(pl)s and p.agent_estimation is not null
		union select i.estimation from `tabPacking List Item` i
			join `tabPacking List` p on p.name = i.parent
			where p.void = 0 and i.parent != %(pl)s and i.estimation is not null
		union select i.agent_estimation from `tabPacking List Item` i
			join `tabPacking List` p on p.name = i.parent
			where p.void = 0 and i.parent != %(pl)s and i.agent_estimation is not null
		""",
		{"pl": exclude},
	)

	conds = [
		[k] + (list(v) if isinstance(v, list | tuple) else ["=", v]) for k, v in filters.items()
	]
	if used:
		conds.append(["name", "not in", used])
	if txt:
		conds.append(["name", "like", f"%{txt}%"])

	return frappe.get_all(
		doctype,
		filters=conds,
		fields=["name"],
		as_list=True,
		limit_start=start,
		limit_page_length=page_len,
		order_by="expired_date asc",
	)

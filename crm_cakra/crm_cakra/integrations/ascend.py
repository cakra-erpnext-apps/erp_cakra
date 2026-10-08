"""Estimation Ascend (SQL Server: EXP_Estimation + EXP_EstimationDetail) dibaca LANGSUNG.

Tidak ada salinan dan tidak ada sync: list Estimation CRM menggabungkan dokumen CRM dengan baris
EXP_Estimation yang di-query tiap kali list dibuka (TOP n, ikut filter/search/urutan list), lalu
dibuang. Kolom Ascend dipetakan ke field CRM Estimation yang sudah ada (LIST_COLS); field CRM
tanpa padanan kosong untuk baris Ascend.

Koneksi diatur di ERPNext Custom Setting, tab Ascend (host, port, database, user, password).
Login harus SQL Server Authentication: ERPNext jalan di Docker (Linux), Windows auth tidak bisa.
Host kosong = list hanya berisi estimasi CRM.
"""

import datetime
import re
from xml.sax.saxutils import quoteattr

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, get_datetime, getdate

SETTINGS = "ERPNext Custom Setting"


def _conf():
	"""Koneksi dari ERPNext Custom Setting (tab Ascend). None = Host belum diisi."""
	s = frappe.get_cached_doc(SETTINGS)
	if not s.get("ascend_host"):
		return None
	return frappe._dict(
		host=s.ascend_host,
		port=cint(s.ascend_port) or 1433,
		database=s.ascend_database,
		user=s.ascend_user,
		password=s.get_password("ascend_password", raise_exception=False),
		list_from=s.get("ascend_list_from"),
	)


def _connect(conf=None):
	import pymssql

	c = conf or _conf()
	return pymssql.connect(
		server=c.host,
		port=c.port,
		user=c.user,
		password=c.password,
		database=c.database,
		login_timeout=15,
		timeout=120,
		as_dict=True,
		autocommit=False,
	)


@frappe.whitelist()
def test_connection() -> str:
	"""Tombol Test Connection di ERPNext Custom Setting: login + hitung estimasi Ascend."""
	frappe.only_for("System Manager")
	conf = _conf()
	if not conf:
		frappe.throw(_("Host Ascend belum diisi."))
	try:
		conn = _connect(conf)
		try:
			cur = conn.cursor()
			cur.execute("SELECT COUNT(*) AS n FROM EXP_Estimation")
			total = cur.fetchone()["n"]
		finally:
			conn.close()
	except Exception as e:
		frappe.throw(_("Gagal terhubung ke Ascend: {0}").format(cstr(e)), title=_("Test Connection"))
	return _("Terhubung ke {0}/{1}. Ada {2} estimasi di Ascend.").format(conf.host, conf.database, total)


# ---------------------------------------------------------------- list langsung dari Ascend
# Field CRM -> ekspresi SQL Ascend. Route -1/-2 = Depo / Depo Krt (tidak ada di EXP_FleetRoute).

LIST_FROM = "EXP_Estimation e LEFT JOIN AR_Customers c ON c.CustomerID = e.CustomerID"
LIST_COLS = {
	"name": "'ASC-' + CAST(e.EstimationID AS varchar(20))",
	"estimation_no": "e.EstimationNo",
	"ascend_estimation_no": "e.EstimationNo",
	"ascend_estimation_id": "e.EstimationID",
	"customer_id": "c.CustomerName",
	"erp_customer": "c.CustomerName",
	"effective_date": "e.EffectiveDate",
	"expired_date": "e.EffectiveDate",  # Ascend cuma punya satu tanggal berlaku
	"quo_no": "e.QuoNo",
	"purpose": "e.Purpose",
	"estimation_type": "'Expedition'",  # modul EXP Ascend = ekspedisi
	"disabled": "e.Disabled",
	"remarks": "e.Remarks",
	"rev_inc_tax": "e.RevIncTax",
	"est_profit": "e.EstProfit",
	"est_km": "TRY_CAST(e.EstKM AS float)",
	"validated": "CASE WHEN e.ApprovedDateTime IS NULL THEN 0 ELSE 1 END",
	"validated_date": "e.ApprovedDateTime",
	"ascend_approved_by": "e.ApprovedBy",
	"owner": "e.CreatedBy",
	"modified_by": "e.LastModBy",
	"creation": "e.CreateDate",
	"modified": "e.LastMod",
	**{
		f"route{i}": f"CASE e.Route{i} WHEN -1 THEN 'Depo' WHEN -2 THEN 'Depo Krt' "
		f"ELSE (SELECT FleetRouteName FROM EXP_FleetRoute WHERE FleetRouteID = e.Route{i}) END"
		for i in range(1, 9)
	},
}
SEARCH_COLS = ("e.EstimationNo", "e.QuoNo", "c.CustomerName", "e.Remarks")
LIST_OPS = {"=", "!=", ">", "<", ">=", "<=", "like", "not like"}


def _list_where(filters, search):
	"""Filter list CRM -> WHERE T-SQL. None = ada filter yang tidak punya padanan di Ascend
	(mis. branch_office), artinya tidak ada estimasi Ascend yang lolos."""
	parts, args = [], []
	for field, value in (filters or {}).items():
		expr = LIST_COLS.get(field)
		if not expr:
			return None
		op, val = (cstr(value[0]).lower(), value[1]) if isinstance(value, (list, tuple)) else ("=", value)
		if op in LIST_OPS:
			parts.append(f"{expr} {op} %s")
			args.append(val)
		elif op in ("in", "not in"):
			vals = val if isinstance(val, (list, tuple)) else [v.strip() for v in cstr(val).split(",") if v.strip()]
			if not vals:
				return None if op == "in" else (parts, args)
			parts.append(f"{expr} {op} ({', '.join(['%s'] * len(vals))})")
			args += list(vals)
		elif op == "between":
			parts.append(f"{expr} BETWEEN %s AND %s")
			args += list(val)[:2]
		elif op == "is":
			parts.append(f"ISNULL(CAST({expr} AS varchar(100)), '') {'<>' if val == 'set' else '='} ''")
		else:
			return None
	if search:
		parts.append("(" + " OR ".join(f"{c} LIKE %s" for c in SEARCH_COLS) + ")")
		args += [f"%{search}%"] * len(SEARCH_COLS)
	return parts, args


def _list_order(order_by):
	"""'modified desc' / '`tabCRM Estimation`.creation asc' -> (field CRM, desc?)."""
	first = cstr(order_by).split(",")[0].strip()
	words = first.rsplit(None, 1)
	desc = not (len(words) == 2 and words[1].lower() == "asc")
	if len(words) == 2 and words[1].lower() in ("asc", "desc"):
		first = words[0]
	field = first.replace("`", "").split(".")[-1].strip() or "modified"
	return (field if field in LIST_COLS else "modified"), desc


def list_estimations(rows, filters=None, search=None, order_by=None, limit=20):
	"""(baris Ascend berkunci field CRM, total) -- dibaca langsung, TOP `limit`."""
	where = _list_where(filters, search)
	if where is None:
		return [], 0
	parts, args = where
	list_from = _conf().list_from
	if list_from:
		parts.append("e.CreateDate >= %s")
		args.append(str(getdate(list_from)))
	where_sql = ("WHERE " + " AND ".join(parts)) if parts else ""
	field, desc = _list_order(order_by)
	cols = [r for r in dict.fromkeys(["name", *rows]) if r in LIST_COLS]
	select = ", ".join(f"{LIST_COLS[r]} AS [{r}]" for r in cols)
	conn = _connect(_conf())
	try:
		cur = conn.cursor()
		cur.execute(
			f"SELECT TOP {cint(limit)} {select} FROM {LIST_FROM} {where_sql} "
			f"ORDER BY {LIST_COLS[field]} {'DESC' if desc else 'ASC'}, e.EstimationID DESC",
			tuple(args) or None,
		)
		data = cur.fetchall()
		cur.execute(f"SELECT COUNT(*) AS n FROM {LIST_FROM} {where_sql}", tuple(args) or None)
		total = cint(cur.fetchone()["n"])
	finally:
		conn.close()
	for d in data:
		for r in rows:
			d.setdefault(r, None)
			if isinstance(d[r], bool):
				d[r] = int(d[r])  # bit SQL Server -> 0/1 seperti Check CRM
		d["ascend_source"] = 1
	return data, total


def merge_list(data, rows, filters, search, order_by, page_length):
	"""Gabung halaman list CRM dengan Ascend: ambil `page_length` teratas dari tiap sumber,
	urutkan bersama, potong lagi. List CRM memakai "load more" (page_length bertambah), jadi
	tidak perlu offset. Ascend tak bisa dihubungi -> list CRM tetap tampil, kesalahannya dicatat."""
	if not _conf():
		return data, 0
	field, desc = _list_order(order_by)
	try:
		extra, total = list_estimations([*rows, field], filters, search, order_by, page_length)
	except Exception:
		frappe.log_error("Ascend: list Estimation")
		return data, 0
	# Kolom urutan belum tentu ikut ditampilkan: ambil nilainya untuk baris CRM supaya urutan gabungan benar.
	if data and field not in data[0]:
		vals = dict(frappe.get_all("CRM Estimation", filters={"name": ["in", [d["name"] for d in data]]}, fields=["name", field], as_list=True))
		for d in data:
			d[field] = vals.get(d["name"])

	def key(d):
		v = d.get(field)
		if isinstance(v, datetime.date) and not isinstance(v, datetime.datetime):
			v = datetime.datetime.combine(v, datetime.time())
		return v

	merged = data + extra
	filled = sorted([d for d in merged if key(d) is not None], key=key, reverse=desc)
	return (filled + [d for d in merged if key(d) is None])[: cint(page_length)], total


# ---------------------------------------------------------------- form: buka & simpan langsung
# Dokumen CRM Estimation bernama ASC-<EstimationID> tidak ada di tabel ERPNext: CRMEstimation
# memuatnya lewat load_doc() dan menyimpannya lewat save_doc(), langsung ke SQL Server. Form,
# grid Revenue/Expense, dan tab Route CRM dipakai apa adanya.

MASTERS = {
	# kind: (tabel, kolom id, kolom nama, punya kolom Disabled)
	"customer": ("AR_Customers", "CustomerID", "CustomerName", True),
	"revenue": ("EXP_RevenueTypes", "RevenueTypeID", "RevenueTypeDescription", True),
	"expense": ("EXP_ExpenseClass", "ExpenseClassID", "ExpenseClassDescription", True),
	"supplier": ("AP_Suppliers", "SupplierID", "SupplierName", True),
	"area": ("TRS_Areas", "AreaID", "AreaName", True),
	"location": ("TRS_Locations", "LocationID", "LocationName", False),
	"port": ("EXP_Ports", "PortID", "PortName", False),
	"sandaran": ("TRS_Sandaran", "SandaranID", "SandaranName", False),
	"voyage": ("TRS_Voyages", "VoyageID", "VoyageName", False),
	"currency": ("CO_Currency", "CurrencyID", "Currency", False),
	"route": ("EXP_FleetRoute", "FleetRouteID", "FleetRouteName", False),
}
# (kolom ID detail Ascend, kind master, field CRM Estimation Detail -- field Data berisi nama)
DETAIL_NAMED = (
	("AreaID", "area", "area_id"),
	("DestID", "location", "dest_id"),
	("PortID", "port", "port_id"),
	("SupplierID", "supplier", "supplier_id"),
	("ShippingLineID", "voyage", "shipping_line_id"),
	("SandaranID", "sandaran", "sandaran_id"),
)
DEPO = {-1: "Depo", -2: "Depo Krt"}  # Route -1/-2 Ascend, tidak ada di EXP_FleetRoute
PASSTHROUGH = (
	# Kolom Ascend tanpa padanan di form CRM: diteruskan apa adanya (proc menimpa semua kolom).
	"DisabledReason", "Size", "EstimationNo", "RevIncTax", "AccManager", "QuoDate", "EstimationType",
	"EstProfit", "EstProfitDate", "EstProfitBy", "EDepartment", "KAMType", "CS", "CS2", "KAMRemarks",
	"JobType", "EstDays", "DisabledFleet", "RouteType",
)


def is_ascend_name(name):
	return cstr(name).startswith("ASC-")


def _est_id(name):
	return cint(cstr(name)[4:])


class Masters:
	"""ID <-> nama master Ascend, dimuat sekali per buka/simpan.
	ponytail: baca ulang semua master (~9 rb baris) tiap kali; cache kalau mulai terasa lambat."""

	def __init__(self, cur):
		self.name_of, self.ids_of, self.errors = {}, {}, []
		for kind, (table, id_col, name_col, has_disabled) in MASTERS.items():
			active = "ISNULL(Disabled, 0) = 0" if has_disabled else "1 = 1"
			cur.execute(f"SELECT {id_col} AS id, {name_col} AS name, CASE WHEN {active} THEN 1 ELSE 0 END AS active FROM {table}")
			self.name_of[kind], self.ids_of[kind] = {}, {}
			for r in cur.fetchall():
				name = cstr(r["name"]).strip()
				self.name_of[kind][r["id"]] = name
				if r["active"] and name:
					self.ids_of[kind].setdefault(name.lower(), []).append(r["id"])

	def name(self, kind, id_):
		if kind == "route" and cint(id_) < 0:
			return DEPO.get(cint(id_), "")
		return self.name_of[kind].get(id_, "") if cint(id_) > 0 else ""

	def label(self, kind, id_):
		"""Nama untuk form/dropdown; nama yang kembar di Ascend diberi " [ID]" supaya bisa dibedakan."""
		name = self.name(kind, id_)
		return f"{name} [{id_}]" if len(self.ids_of[kind].get(name.lower(), [])) > 1 else name

	def id(self, kind, name, label, keep=0):
		"""Nama (atau "Nama [ID]") -> ID Ascend. keep = ID sekarang: dipakai lagi selama namanya sama.
		Tidak ketemu / kembar tanpa [ID] -> dicatat, hasil 0."""
		name = cstr(name).strip()
		if not name:
			return 0
		tagged = re.match(r"^(.*) \[(-?\d+)\]$", name)
		if tagged and self.name(kind, cint(tagged[2])).lower() == tagged[1].strip().lower():
			return cint(tagged[2])
		if cint(keep) and name.lower() in (self.name(kind, keep).lower(), self.label(kind, keep).lower()):
			return keep
		if kind == "route":
			for id_, depo in DEPO.items():
				if depo.lower() == name.lower():
					return id_
		ids = self.ids_of[kind].get(name.lower(), [])
		if len(ids) == 1:
			return ids[0]
		self.errors.append(
			_("{0} '{1}' tidak ada di Ascend").format(label, name)
			if not ids
			else _("{0} '{1}' ada {2} kali di Ascend").format(label, name, len(ids))
		)
		return 0


def _read(cur, est_id):
	cur.execute("SELECT * FROM EXP_Estimation WHERE EstimationID = %d", (est_id,))
	header = cur.fetchone()
	cur.execute("SELECT * FROM EXP_EstimationDetail WHERE EstimationID = %d ORDER BY DetailID", (est_id,))
	return header, cur.fetchall()


def load_doc(name):
	"""(field header CRM Estimation, {revenue_items/expense_items: [baris]}) dibaca dari Ascend."""
	est_id = _est_id(name)
	conn = _connect(_conf())
	try:
		cur = conn.cursor()
		m = Masters(cur)
		h, details = _read(cur, est_id)
	finally:
		conn.close()
	if not h:
		frappe.throw(
			_("Estimation {0} tidak ada di Ascend").format(name),
			frappe.DoesNotExistError(doctype="CRM Estimation"),
		)

	customer = m.label("customer", h["CustomerID"])
	doc = {
		"doctype": "CRM Estimation",
		"name": name,
		"docstatus": 0,
		"owner": cstr(h["CreatedBy"]).strip(),
		"creation": h["CreateDate"],
		"modified": h["LastMod"],
		"modified_by": cstr(h["LastModBy"]).strip(),
		"estimation_no": cstr(h["EstimationNo"]).strip(),
		"ascend_estimation_id": est_id,
		"ascend_estimation_no": cstr(h["EstimationNo"]).strip(),
		"customer_id": customer,
		"erp_customer": customer,
		"effective_date": h["EffectiveDate"],
		"expired_date": h["EffectiveDate"],
		"quo_no": cstr(h["QuoNo"]).strip(),
		"purpose": cstr(h["Purpose"]).strip(),
		"estimation_type": "Expedition",
		"disabled": cint(h["Disabled"]),
		"remarks": cstr(h["Remarks"]).strip(),
		"rev_inc_tax": h["RevIncTax"],
		"est_profit": h["EstProfit"],
		"est_km": flt(h["EstKM"]),
		"validated": int(bool(h["ApprovedDateTime"])),
		"validated_date": h["ApprovedDateTime"],
		"ascend_approved_by": cstr(h["ApprovedBy"]).strip(),
		**{f"route{i}": m.label("route", h[f"Route{i}"]) or None for i in range(1, 9)},
	}
	base = frappe.defaults.get_global_default("currency")
	children = {"revenue_items": [], "expense_items": []}
	for d in details:
		exp = cint(d["IsExpense"])
		row = {
			"name": f"{name}-{d['DetailID']}",  # DetailID dipakai save_doc untuk memasangkan baris lama
			"type_id": m.label("expense" if exp else "revenue", d["TypeID"]),
			"amount": d["Amount"],
			"currency": m.name("currency", d["CurrID"]) or base,
			"rate": 1,
			"csize": cstr(d["CSize"]).strip(),
			"status": "Per Doc" if d["PerDoc"] else "By Qty" if d["ByQty"] else "",
			"remarks": cstr(d["Remarks"]).strip(),
			"jalur": cstr(d["Jalur"]).strip(),
			"jenis_karantina": cstr(d["JenisKarantina"]).strip(),
			"uom": cstr(d["UOM"]).strip(),
			"is_expense": exp,
			**{field: m.label(kind, d[col]) for col, kind, field in DETAIL_NAMED},
		}
		children["expense_items" if exp else "revenue_items"].append(row)
	return doc, children


def _xml(details):
	items = "".join("<Item " + " ".join(f"{k}={quoteattr(cstr(v))}" for k, v in d.items()) + "/>" for d in details)
	return f"<Items>{items}</Items>"


def _exec(cur, proc, params):
	"""EXEC proc dengan parameter bernama; kembalikan nilai RETURN-nya."""
	names = list(params)
	args = ", ".join(f"@{n} = %s" for n in names)
	cur.execute(f"SET NOCOUNT ON; DECLARE @r INT; EXEC @r = dbo.{proc} {args}; SELECT @r AS r", tuple(params[n] for n in names))
	return cint(cur.fetchone()["r"])


def _type_id(m, kind, row, old):
	"""Baris grid -> TypeID: nama Ascend / kode atau nama Item ERPNext; ID lama dipakai lagi kalau sama."""
	names = [cstr(n).strip().lower() for n in (row.type_id, row.type_id and frappe.db.get_value("Item", row.type_id, "item_name")) if n]
	if old and {m.name(kind, old["TypeID"]).lower(), m.label(kind, old["TypeID"]).lower()} & set(names):
		return old["TypeID"]
	for n in names:
		ids = m.ids_of[kind].get(n, [])
		if len(ids) == 1:
			return ids[0]
	return m.id(kind, row.type_id, _("Baris {0} {1}").format(row.idx, kind.title()))


def _detail_rows(doc, m, olds):
	old_by_id = {d["DetailID"]: d for d in olds}
	base = frappe.defaults.get_global_default("currency")
	prefix = doc.name + "-"
	details = []
	for field, kind, exp in (("revenue_items", "revenue", 0), ("expense_items", "expense", 1)):
		for r in doc.get(field):
			old = old_by_id.get(cint(cstr(r.name)[len(prefix):]) if cstr(r.name).startswith(prefix) else 0) or {}
			d = {
				"IsExpense": exp,
				"TypeID": _type_id(m, kind, r, old),
				"Amount": flt(r.amount, 4),
				"Remarks": cstr(r.remarks).strip()[:100],
				"PerDoc": int(r.status == "Per Doc"),
				# PerDoc+ByQty sekaligus (ada di data lama) tidak bisa diwakili status CRM -> pertahankan.
				"ByQty": int(r.status == "By Qty" or (r.status == "Per Doc" and bool(old.get("PerDoc") and old.get("ByQty")))),
				"Jalur": cstr(r.jalur).strip()[:30],
				"CSize": cstr(r.csize).strip()[:30],
				# CurrID 0 = mata uang dasar tanpa pilihan (data lama); jangan diganti ID IDR.
				"CurrID": 0
				if old and not cint(old.get("CurrID")) and r.currency == base
				else m.id("currency", r.currency, _("Currency"), old.get("CurrID")),
				"JenisKarantina": cstr(r.jenis_karantina).strip()[:10],
				"UOM": cstr(r.uom).strip()[:10],
			}
			for col, mkind, f in DETAIL_NAMED:
				d[col] = m.id(mkind, r.get(f), frappe.unscrub(f.removesuffix("_id")), old.get(col))
			details.append(d)
	return details


def save_doc(doc):
	"""Tulis dokumen ASC- ke Ascend lewat USP_EXP_Estimation_Update (proc aplikasi Ascend sendiri)."""
	est_id = _est_id(doc.name)
	conn = _connect(_conf())
	try:
		cur = conn.cursor()
		m = Masters(cur)
		h, olds = _read(cur, est_id)
		if not h:
			frappe.throw(_("Estimation {0} sudah tidak ada di Ascend").format(doc.name))
		if doc.modified and get_datetime(doc.modified) != get_datetime(h["LastMod"]):
			frappe.throw(_("Estimation ini sudah diubah di Ascend sejak dibuka. Muat ulang halaman lalu ulangi perubahannya."))

		details = _detail_rows(doc, m, olds)
		params = {
			"EstimationID": est_id,
			"CustomerID": m.id("customer", doc.customer_id, _("Customer"), h["CustomerID"]),
			"EffectiveDate": getdate(doc.expired_date or doc.effective_date),
			"Disabled": cint(doc.disabled),
			"DisabledDate": h["DisabledDate"] if h["Disabled"] or not doc.disabled else getdate(),
			"Remarks": cstr(doc.remarks).strip()[:1000],
			"Purpose": doc.purpose or h["Purpose"],
			"QuoNo": cstr(doc.quo_no).strip()[:50],
			# EstKM varchar ("15.00"): teks lama dipakai lagi selama angkanya sama.
			"EstKM": cstr(h["EstKM"]) if flt(h["EstKM"]) == flt(doc.est_km) else ("%g" % flt(doc.est_km) if flt(doc.est_km) else ""),
			**{f"Route{i}": m.id("route", doc.get(f"route{i}"), _("Route {0}").format(i), h[f"Route{i}"]) for i in range(1, 9)},
			**{col: h[col] for col in PASSTHROUGH},
		}
		if m.errors:
			frappe.throw("<br>".join(dict.fromkeys(m.errors)), title=_("Tidak tersimpan ke Ascend"))
		params["XML"] = _xml(details)
		params["By"] = cstr(frappe.db.get_value("User", frappe.session.user, "username") or frappe.session.user)[:30]
		try:
			# Proc tidak transaksional (cek CSize jalan sesudah detail ditulis): bungkus sendiri.
			if _exec(cur, "USP_EXP_Estimation_Update", params) <= 0:
				frappe.throw(_("Ascend tidak menyimpan estimation ini"))
			conn.commit()
		except Exception as e:
			conn.rollback()
			if isinstance(e, frappe.ValidationError):
				raise
			frappe.throw(_("Ascend menolak: {0}").format(cstr(e)), title=_("Tidak tersimpan ke Ascend"))
	finally:
		conn.close()


# ---------------------------------------------------------------- dropdown dari master Ascend
# Form ASC- memberi field Link-nya filter {"__ascend": "<kind>"}; search_link (override
# frappe.desk.search.search_link di hooks) lalu mencari ke master Ascend, bukan master ERPNext.
SEARCH_KINDS = {"customer", "revenue", "expense", "route", "currency", "csize"}
CSIZE = ("CO_ContainerSizes", "ContainerSize", "ContainerSize", False)


@frappe.whitelist()
def search_link(
	doctype, txt, query=None, filters=None, page_length=10, searchfield=None, reference_doctype=None,
	ignore_user_permissions=False, *, link_fieldname=None,
):
	f = frappe.parse_json(filters) if isinstance(filters, str) and filters.strip().startswith("{") else filters
	kind = f.get("__ascend") if isinstance(f, dict) else None
	if kind not in SEARCH_KINDS:
		from frappe.desk.search import search_link as standard

		return standard(
			doctype, txt, query, filters, page_length, searchfield, reference_doctype,
			ignore_user_permissions, link_fieldname=link_fieldname,
		)
	frappe.has_permission("CRM Estimation", "read", throw=True)
	return [{"value": v, "description": ""} for v in search_master(kind, txt, cint(page_length) or 10)]


def search_master(kind, txt, limit=10):
	"""Nama master Ascend yang mengandung txt (aktif saja); nama kembar diberi " [ID]"."""
	table, id_col, name_col, has_disabled = CSIZE if kind == "csize" else MASTERS[kind]
	where = "ISNULL(Disabled, 0) = 0 AND " if has_disabled else ""
	conn = _connect(_conf())
	try:
		cur = conn.cursor()
		cur.execute(
			f"SELECT TOP {cint(limit)} {id_col} AS id, LTRIM(RTRIM({name_col})) AS name, "
			f"COUNT(*) OVER (PARTITION BY LTRIM(RTRIM({name_col}))) AS dup FROM {table} "
			f"WHERE {where}{name_col} LIKE %s ORDER BY {name_col}" + (f", {id_col}" if id_col != name_col else ""),
			(f"%{cstr(txt).strip()}%",),
		)
		rows = cur.fetchall()
	finally:
		conn.close()
	out = [f"{r['name']} [{r['id']}]" if r["dup"] > 1 else r["name"] for r in rows if r["name"]]
	if kind == "route":
		out = [d for d in DEPO.values() if cstr(txt).strip().lower() in d.lower()] + out
	return out[: cint(limit)]

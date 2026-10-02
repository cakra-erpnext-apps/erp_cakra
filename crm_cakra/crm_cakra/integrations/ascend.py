"""Sinkron dua arah CRM Estimation <-> Ascend (SQL Server: EXP_Estimation + EXP_EstimationDetail).

Koneksi diatur di ERPNext Custom Setting, tab Ascend (host, port, database, user, password,
department, tanggal mulai tarik, centang Aktif). Department = EDepartment/Cost Center untuk
estimasi BARU dari CRM -- proc Ascend menolak kalau kosong. Kalau host di sana kosong, kunci lama
di site_config (ascend_mssql_host, _port, _db, _user, _password, ascend_estimation_department)
masih dibaca. Selama tidak aktif seluruh sinkron diam (tidak ada job, tidak ada error).

CRM -> Ascend (push): setiap save meng-antre push(); isi dikirim lewat USP_EXP_Estimation_Update
(+ USP_EXP_Estimation_DoApprove untuk approval) -- proc yang sama dengan aplikasi Ascend, jadi
aturannya ikut jalan. Proc itu TIDAK memakai transaksi (validasi CSize jalan sesudah detail
ditulis), jadi di sini dibungkus transaksi sendiri dan di-rollback kalau gagal. Kolom Ascend
yang tidak ada di CRM (AccManager, KAM, JobType, EDepartment, ...) diteruskan apa adanya dari
baris yang sekarang, karena proc menimpa semua parameter.

Ascend -> CRM (pull_all, cron tiap 2 menit): kedua tabel dibaca utuh lalu dibandingkan per
EstimationID dengan ascend_hash (sidik jari baris Ascend saat sync terakhir). Tanpa trigger /
Change Tracking karena tabelnya tanpa primary key, Approve tidak mengubah LastMod, dan Delete
menghapus fisik -- membaca ulang semuanya satu-satunya cara yang menangkap ketiganya.
ponytail: baca tabel utuh (~300 header); kalau sudah ratusan ribu baris, pasang PK + Change Tracking.

Konflik: kalau kedua sisi berubah sejak sync terakhir, tidak ada yang ditimpa -> status Conflict,
diputuskan orang lewat use_ascend() / use_crm().

Pemetaan master lewat NAMA (Ascend memakai ID int, CRM memakai nama). Nama yang tidak ketemu
atau kembar menggagalkan sync dokumen itu dengan pesan jelas -- tidak pernah mengirim ID 0 diam-diam.
"""

import hashlib
import json
from xml.sax.saxutils import quoteattr

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, now_datetime, nowdate

LOCK = "ascend_estimation_sync"
# ponytail: satu lock global untuk semua push+pull; lock per dokumen kalau antreannya mulai terasa.

HEADER_COLS = (
	"EstimationNo", "CustomerID", "EffectiveDate", "Disabled", "Remarks", "Purpose", "EstimationType",
	"QuoNo", "RevIncTax", "EstProfit", "EstKM", "Route1", "Route2", "Route3", "Route4", "Route5", "Route6",
)
APPROVAL_COLS = ("ApprovedDateTime", "ApprovedBy")
DETAIL_COLS = (
	"IsExpense", "TypeID", "Amount", "Remarks", "PerDoc", "ByQty", "Jalur", "AreaID", "PortID", "CSize",
	"DestID", "SupplierID", "CurrID", "ShippingLineID", "JenisKarantina", "SandaranID", "UOM",
)
# (kolom id di detail, kind master, field CRM) -- field CRM-nya Data, isinya nama master.
DETAIL_NAMED = (
	("AreaID", "area", "area_id"),
	("DestID", "location", "dest_id"),
	("PortID", "port", "port_id"),
	("SupplierID", "supplier", "supplier_id"),
	("ShippingLineID", "voyage", "shipping_line_id"),
	("SandaranID", "sandaran", "sandaran_id"),
)
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


class SyncError(Exception):
	pass


SETTINGS = "ERPNext Custom Setting"


def _conf(require_enabled=True):
	"""Koneksi dari ERPNext Custom Setting (tab Ascend), site_config sebagai cadangan.

	require_enabled=False dipakai tombol Test Connection: boleh dites sebelum dicentang Aktif.
	"""
	s = frappe.get_cached_doc(SETTINGS) if frappe.db.exists("DocType", SETTINGS) else None
	if s and s.get("ascend_host"):
		if require_enabled and not s.get("ascend_enabled"):
			return None
		return frappe._dict(
			host=s.ascend_host,
			port=cint(s.ascend_port) or 1433,
			database=s.ascend_database,
			user=s.ascend_user,
			password=s.get_password("ascend_password", raise_exception=False),
			department=s.ascend_department,
			pull_from=s.ascend_pull_from,
		)
	c = frappe.conf
	if not c.get("ascend_mssql_host"):
		return None
	return frappe._dict(
		host=c.ascend_mssql_host,
		port=cint(c.get("ascend_mssql_port")) or 1433,
		database=c.ascend_mssql_db,
		user=c.ascend_mssql_user,
		password=c.ascend_mssql_password,
		department=c.get("ascend_estimation_department"),
		pull_from=None,
	)


def enabled():
	return bool(_conf())


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


class Masters:
	"""ID <-> nama untuk semua master yang dirujuk estimasi. Dimuat sekali per job."""

	def __init__(self, cur):
		self.name_of, self.ids_of = {}, {}
		for kind, (table, id_col, name_col, has_disabled) in MASTERS.items():
			active = "ISNULL(Disabled, 0) = 0" if has_disabled else "1 = 1"
			cur.execute(f"SELECT {id_col} AS id, {name_col} AS name, CASE WHEN {active} THEN 1 ELSE 0 END AS active FROM {table}")
			self.name_of[kind], self.ids_of[kind] = {}, {}
			for r in cur.fetchall():
				name = cstr(r["name"]).strip()
				self.name_of[kind][r["id"]] = name
				if r["active"] and name:
					self.ids_of[kind].setdefault(name.lower(), []).append(r["id"])
		self.errors = []

	def id(self, kind, name, label):
		"""Nama CRM -> ID Ascend. Kosong -> 0. Tidak ketemu / kembar -> dicatat, hasil 0."""
		name = cstr(name).strip()
		if not name:
			return 0
		ids = self.ids_of[kind].get(name.lower(), [])
		if len(ids) == 1:
			return ids[0]
		self.errors.append(
			_("{0} '{1}' tidak ada di Ascend").format(label, name)
			if not ids
			else _("{0} '{1}' ada {2} kali di Ascend (ID {3})").format(label, name, len(ids), ", ".join(map(str, ids)))
		)
		return 0

	def name(self, kind, id_):
		return self.name_of[kind].get(id_, "") if cint(id_) > 0 else ""

	def raise_errors(self):
		if self.errors:
			errors, self.errors = self.errors, []
			raise SyncError("\n".join(dict.fromkeys(errors)))


# ---------------------------------------------------------------- baca Ascend


def _read(cur, estimation_id=None):
	"""{EstimationID: (header, [detail...])}. Tanpa estimation_id = seluruh tabel."""
	where = "WHERE EstimationID = %d" if estimation_id else ""
	args = (estimation_id,) if estimation_id else None
	cur.execute(f"SELECT * FROM EXP_Estimation {where}", args)
	out = {r["EstimationID"]: (r, []) for r in cur.fetchall()}
	cur.execute(f"SELECT * FROM EXP_EstimationDetail {where} ORDER BY EstimationID, DetailID", args)
	for d in cur.fetchall():
		if d["EstimationID"] in out:
			out[d["EstimationID"]][1].append(d)
	return out


def _norm(v):
	if v is None:
		return ""
	if isinstance(v, bool):
		return int(v)
	if hasattr(v, "isoformat"):
		return v.isoformat()
	if isinstance(v, (int, str)):
		return v.strip() if isinstance(v, str) else v
	return f"{flt(v):.4f}"  # money / Decimal / float


def _snapshot(header, details, with_approval=True):
	cols = HEADER_COLS + (APPROVAL_COLS if with_approval else ())
	h = {c: _norm(header.get(c)) for c in cols}
	h["EffectiveDate"] = cstr(h["EffectiveDate"])[:10]
	return {"h": h, "d": [{c: _norm(d.get(c)) for c in DETAIL_COLS} for d in details]}


def _hash(header, details):
	return hashlib.sha1(json.dumps(_snapshot(header, details), sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- CRM -> Ascend


def queue_push(doc):
	"""Dipanggil dari CRMEstimation.on_update."""
	if not enabled() or doc.flags.from_ascend:
		return
	if doc.ascend_sync_status in ("Conflict", "Removed in Ascend"):
		return  # tunggu keputusan orang (use_crm / use_ascend)
	doc.db_set("ascend_sync_status", "Pending", update_modified=False)
	frappe.enqueue(
		"crm_cakra.integrations.ascend.push",
		queue="short",
		name=doc.name,
		by=frappe.session.user,
		job_id=f"ascend_push::{doc.name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)


def _item_candidates(row):
	"""Nama yang dicoba untuk TypeID: kode & nama Item, lalu nama CRM Product (revenue)."""
	names = []
	if row.type_id:
		names += [row.type_id, frappe.db.get_value("Item", row.type_id, "item_name")]
	if row.product_id:
		names.append(frappe.db.get_value("CRM Product", row.product_id, "product_name"))
	return [n for n in names if n]


def _type_id(m, row, kind):
	label = _("Revenue Type") if kind == "revenue" else _("Expense Class")
	cands = _item_candidates(row)
	if not cands:
		m.errors.append(_("Baris {0} {1}: Item kosong").format(row.idx, label))
		return 0
	for n in cands:
		ids = m.ids_of[kind].get(cstr(n).strip().lower(), [])
		if len(ids) == 1:
			return ids[0]
	return m.id(kind, cands[0], label)  # tidak ada yang cocok -> catat pesan untuk nama pertama


def _want(doc, m, cur_header):
	"""Isi Ascend yang diinginkan dari dokumen CRM: (params proc, detail rows)."""
	cur_header = cur_header or {}
	details = []
	for kind, rows, is_exp in (("revenue", doc.revenue_items, 0), ("expense", doc.expense_items, 1)):
		for r in rows:
			d = {
				"IsExpense": is_exp,
				"TypeID": _type_id(m, r, kind),
				"Amount": flt(r.amount, 4),
				"Remarks": cstr(r.remarks).strip()[:100],
				"PerDoc": int(r.status == "Per Doc"),
				"ByQty": int(r.status == "By Qty"),
				"Jalur": cstr(r.jalur).strip()[:30],
				"CSize": cstr(r.csize).strip()[:30],
				"CurrID": m.id("currency", r.currency, _("Currency")),
				"JenisKarantina": cstr(r.jenis_karantina).strip()[:10],
				"UOM": cstr(r.uom).strip()[:10],
			}
			for col, mkind, field in DETAIL_NAMED:
				d[col] = m.id(mkind, r.get(field), frappe.unscrub(field.removesuffix("_id")))
			details.append(d)

	routes = {}
	for i in range(1, 7):
		v = doc.get(f"route{i}")
		old = cint(cur_header.get(f"Route{i}"))
		# -1/-2 (Depo / Depo Krt) tidak punya padanan di CRM: biarkan selama slotnya kosong di CRM.
		routes[f"Route{i}"] = m.id("route", v, _("Route {0}").format(i)) if v else (old if old < 0 else 0)

	customer = frappe.db.get_value("Customer", doc.customer_id, "customer_name") or doc.customer_id
	dept = cur_header.get("EDepartment") or (_conf() or {}).get("department")
	if not dept:
		m.errors.append(_("Department belum diisi di ERPNext Custom Setting, tab Ascend (Cost Center Ascend untuk estimasi baru)"))
	was_disabled = cint(cur_header.get("Disabled"))
	params = {
		"EstimationID": cint(doc.ascend_estimation_id),
		"CustomerID": m.id("customer", customer, _("Customer")),
		"EffectiveDate": getdate(doc.effective_date or nowdate()),
		"Disabled": cint(doc.disabled),
		"DisabledDate": cur_header.get("DisabledDate") if was_disabled or not doc.disabled else getdate(nowdate()),
		"DisabledReason": cur_header.get("DisabledReason") or "",
		"Size": cur_header.get("Size") or "",
		"Remarks": cstr(doc.remarks).strip()[:1000],
		"Purpose": doc.purpose or cur_header.get("Purpose") or "Customer",
		"EstimationNo": cur_header.get("EstimationNo") or "",  # kosong = Ascend memberi nomornya sendiri
		"RevIncTax": flt(doc.rev_inc_tax, 4),
		"QuoNo": (doc.quo_no or cur_header.get("QuoNo") or "")[:50],
		"AccManager": cur_header.get("AccManager") or "",
		"QuoDate": cur_header.get("QuoDate"),
		"EstimationType": doc.estimation_type or cur_header.get("EstimationType") or "",
		"EstProfit": flt(doc.est_profit, 4),
		"EstProfitDate": cur_header.get("EstProfitDate"),
		"EstProfitBy": cur_header.get("EstProfitBy") or "",
		"EDepartment": dept or "",
		"KAMType": cur_header.get("KAMType") or "",
		"CS": cur_header.get("CS") or "",
		"CS2": cur_header.get("CS2") or "",
		"KAMRemarks": cur_header.get("KAMRemarks") or "",
		"JobType": cur_header.get("JobType") or "",
		"EstKM": ("%g" % flt(doc.est_km)) if flt(doc.est_km) else "",
		"EstDays": cur_header.get("EstDays") or "",
		"DisabledFleet": cint(cur_header.get("DisabledFleet")),
		"RouteType": cur_header.get("RouteType") or "",
		**routes,
	}
	m.raise_errors()
	return params, details


def _xml(details):
	items = "".join(
		"<Item " + " ".join(f"{k}={quoteattr(cstr(v))}" for k, v in d.items()) + "/>" for d in details
	)
	return f"<Items>{items}</Items>"


def _exec(cur, proc, params):
	"""EXEC proc dengan parameter bernama; kembalikan nilai RETURN-nya."""
	names = list(params)
	sql = (
		"SET NOCOUNT ON; DECLARE @r INT; EXEC @r = dbo.{0} {1}; SELECT @r AS r".format(
			proc, ", ".join(f"@{n} = %s" for n in names)
		)
	)
	cur.execute(sql, tuple(params[n] for n in names))
	return cint(cur.fetchone()["r"])


def _mark(name, status, message="", **extra):
	frappe.db.set_value(
		"CRM Estimation",
		name,
		{"ascend_sync_status": status, "ascend_sync_error": message[:2000], "ascend_synced_at": now_datetime(), **extra},
		update_modified=False,
	)


def push(name, by=None, force=False):
	if not enabled():
		return
	try:
		with _lock():
			_push(name, by, force)
	except Exception as e:
		frappe.db.rollback()
		msg = cstr(e) if isinstance(e, SyncError) else f"{type(e).__name__}: {e}"
		_mark(name, "Push Failed", msg)
		if not isinstance(e, SyncError):
			frappe.log_error(f"Ascend push {name}")
	frappe.db.commit()


def _push(name, by, force):
	doc = frappe.get_doc("CRM Estimation", name)
	if doc.ascend_sync_status in ("Conflict", "Removed in Ascend") and not force:
		return
	conn = _connect()
	try:
		cur = conn.cursor()
		m = Masters(cur)
		est_id = cint(doc.ascend_estimation_id)
		cur_row = _read(cur, est_id).get(est_id) if est_id else None
		if est_id and not cur_row:
			_mark(name, "Removed in Ascend", _("EstimationID {0} sudah tidak ada di Ascend").format(est_id))
			return
		if cur_row and not force and _hash(*cur_row) != doc.ascend_hash:
			_mark(name, "Conflict", _("Estimasi ini juga diubah di Ascend sejak sync terakhir. Pilih data mana yang dipakai."))
			return

		header = cur_row[0] if cur_row else {}
		params, details = _want(doc, m, header)
		wrote = False
		if not cur_row or _snapshot({**header, **params}, details, False) != _snapshot(header, cur_row[1], False):
			params["XML"] = _xml(details)
			params["By"] = cstr(by or frappe.session.user)[:30]
			est_id = _exec(cur, "USP_EXP_Estimation_Update", params)
			if est_id <= 0:
				raise SyncError(_("USP_EXP_Estimation_Update tidak menyimpan (kembali {0})").format(est_id))
			wrote = True

		warning = ""
		approved = bool(header.get("ApprovedDateTime"))
		req = header.get("ReqApproval") if cur_row else None
		if bool(doc.validated) != approved and (req is None or req):
			cur.execute("SAVE TRANSACTION approve")
			try:
				_exec(cur, "USP_EXP_Estimation_DoApprove", {
					"EstimationID": est_id,
					"DoApprove": cint(doc.validated),
					"ApprovedDateTime": doc.validated_date or now_datetime(),
					"ApprovedBy": cstr(doc.validated_by or by)[:30],
				})
			except Exception as e:
				# Approval ditolak Ascend (mis. belum ada baris revenue/expense) -> data tetap tersimpan.
				cur.execute("ROLLBACK TRANSACTION approve")
				warning = _("Data tersimpan, approval ditolak Ascend: {0}").format(e)
		conn.commit()
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()

	conn = _connect()  # baca ulang hasil akhirnya (nomor dari Ascend, Size, approval) untuk hash
	try:
		row = _read(conn.cursor(), est_id)[est_id]
	finally:
		conn.close()
	_mark(
		name,
		"Synced",
		warning or ("" if wrote else _("Tidak ada perubahan untuk Ascend")),
		ascend_estimation_id=est_id,
		ascend_estimation_no=cstr(row[0].get("EstimationNo")).strip(),
		ascend_hash=_hash(*row),
	)


# ---------------------------------------------------------------- Ascend -> CRM


def pull_all():
	conf = _conf()
	if not conf:
		return
	pull_from = getdate(conf.pull_from) if conf.pull_from else None
	counts = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
	with _lock():
		conn = _connect()
		try:
			cur = conn.cursor()
			m = Masters(cur)
			rows = _read(cur)
		finally:
			conn.close()

		linked = {
			cint(r.ascend_estimation_id): r
			for r in frappe.get_all(
				"CRM Estimation",
				filters={"ascend_estimation_id": [">", 0]},
				fields=["name", "ascend_estimation_id", "ascend_hash", "ascend_sync_status"],
			)
		}
		for est_id, row in rows.items():
			h = _hash(*row)
			local = linked.get(est_id)
			if local and (local.ascend_hash == h or local.ascend_sync_status in ("Pending", "Conflict")):
				continue
			if not local and pull_from and row[0].get("EffectiveDate") and getdate(row[0]["EffectiveDate"]) < pull_from:
				counts["skipped"] += 1  # estimasi lama di luar batas tanggal: tidak dibawa masuk ke CRM
				continue
			try:
				if not local:
					_link_or_create(est_id, row, h, m)
					counts["created"] += 1
				elif local.ascend_sync_status == "Push Failed":
					_mark(local.name, "Conflict", _("Perubahan CRM belum terkirim dan Ascend juga berubah. Pilih data mana yang dipakai."))
				else:
					_apply(frappe.get_doc("CRM Estimation", local.name), row, h, m)
					counts["updated"] += 1
				frappe.db.commit()
			except Exception as e:
				frappe.db.rollback()
				_pull_failed(est_id, local, e)
				counts["failed"] += 1

		for est_id, local in linked.items():
			if est_id not in rows and local.ascend_sync_status != "Removed in Ascend":
				frappe.db.set_value("CRM Estimation", local.name, "disabled", 1, update_modified=False)
				_mark(local.name, "Removed in Ascend", _("EstimationID {0} dihapus di Ascend").format(est_id))
				frappe.db.commit()

	_record_pull(
		_("{0} estimasi di Ascend. Baru masuk {1}, diperbarui {2}, gagal {3}, dilewati karena tanggal {4}.").format(
			len(rows), counts["created"], counts["updated"], counts["failed"], counts["skipped"]
		)
	)


def _record_pull(result):
	"""Jejak tarikan terakhir di tab Ascend, supaya admin tahu cron-nya hidup tanpa membuka log."""
	if frappe.db.exists("DocType", SETTINGS):
		# update_modified=False: cron ini jalan tiap 2 menit; tanpa itu admin yang sedang membuka
		# form setting selalu kena "dokumen sudah diubah" waktu menyimpan.
		frappe.db.set_single_value(
			SETTINGS, {"ascend_last_pull": now_datetime(), "ascend_last_result": result}, update_modified=False
		)
		frappe.db.commit()


@frappe.whitelist()
def test_connection() -> str:
	"""Tombol Test Connection di ERPNext Custom Setting: login + hitung estimasi Ascend."""
	frappe.only_for("System Manager")
	conf = _conf(require_enabled=False)
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


@frappe.whitelist()
def sync_now() -> str:
	"""Tombol Sync Now: tarik dari Ascend sekarang tanpa menunggu cron 2 menit."""
	frappe.only_for("System Manager")
	if not enabled():
		frappe.throw(_("Sinkron Ascend belum aktif. Centang Aktif dan isi koneksinya dulu."))
	frappe.enqueue("crm_cakra.integrations.ascend.pull_all", queue="long", job_id="ascend_pull_now", deduplicate=True)
	return _("Tarikan dari Ascend dijalankan di belakang. Hasilnya muncul di Hasil Tarik Terakhir.")


def _pull_failed(est_id, local, e):
	msg = cstr(e) if isinstance(e, SyncError) else f"{type(e).__name__}: {e}"
	if local:
		_mark(local.name, "Pull Failed", msg)
	# Estimasi Ascend yang belum punya pasangan di CRM tidak punya tempat untuk status -> Error Log,
	# sekali per isi pesan (job ini jalan tiap 2 menit).
	key = f"ascend_pull_err::{est_id}"
	if frappe.cache().get_value(key) != msg:
		frappe.cache().set_value(key, msg, expires_in_sec=86400)
		frappe.log_error(f"Ascend pull EstimationID {est_id}", msg)
	frappe.db.commit()


def _link_or_create(est_id, row, h, m):
	quo = cstr(row[0].get("QuoNo")).strip()
	match = quo and frappe.db.get_value(
		"CRM Estimation", {"quo_no": quo, "ascend_estimation_id": 0}, "name"
	)
	if match:
		# Estimasi yang sudah ada di kedua sisi sebelum sync dinyalakan: jangan tebak mana yang benar.
		_mark(
			match,
			"Conflict",
			_("Dicocokkan otomatis dengan Ascend lewat Quotation {0}. Pilih data mana yang dipakai.").format(quo),
			ascend_estimation_id=est_id,
			ascend_estimation_no=cstr(row[0].get("EstimationNo")).strip(),
			ascend_hash=h,
		)
		return
	_apply(frappe.new_doc("CRM Estimation"), row, h, m, est_id)


def _crm_link(doctype, value, label, m, by_field=None):
	value = cstr(value).strip()
	if not value:
		return None
	if frappe.db.exists(doctype, value):
		return value
	if by_field:
		found = frappe.db.get_value(doctype, {by_field: value}, "name")
		if found:
			return found
	m.errors.append(_("{0} '{1}' tidak ada di CRM").format(label, value))
	return None


def _apply(doc, row, h, m, new_id=None):
	header, details = row
	meta = frappe.get_meta("CRM Estimation")

	def opt(field, value):
		value = cstr(value).strip()
		return value if value in (meta.get_field(field).options or "").split("\n") else doc.get(field)

	doc.customer_id = _crm_link("Customer", m.name("customer", header.get("CustomerID")), _("Customer"), m, "customer_name")
	doc.effective_date = header.get("EffectiveDate")
	doc.disabled = cint(header.get("Disabled"))
	doc.remarks = cstr(header.get("Remarks")).strip()
	doc.purpose = opt("purpose", header.get("Purpose"))
	doc.estimation_type = opt("estimation_type", header.get("EstimationType"))
	quo = cstr(header.get("QuoNo")).strip()
	if quo and frappe.db.exists("CRM Quotation", quo):
		doc.quo_no = quo
	doc.est_km = flt(header.get("EstKM"))
	for i in range(1, 7):
		doc.set(f"route{i}", _crm_link("Fleet Location", m.name("route", header.get(f"Route{i}")), _("Route {0}").format(i), m))
	if cint(header.get("ReqApproval")) or header.get("ApprovedDateTime"):
		doc.validated = int(bool(header.get("ApprovedDateTime")))
		doc.validated_date = header.get("ApprovedDateTime")
		doc.validated_by = frappe.db.get_value("User", {"username": cstr(header.get("ApprovedBy")).strip()}) if doc.validated else None
		doc.ascend_approved_by = cstr(header.get("ApprovedBy")).strip()

	for field, is_exp, kind in (("revenue_items", 0, "revenue"), ("expense_items", 1, "expense")):
		src = [d for d in details if cint(d.get("IsExpense")) == is_exp]
		rows = doc.get(field)[: len(src)]  # baris ke-i dipasangkan dgn baris ke-i: qty/rate/CRM Product tetap
		doc.set(field, rows)
		for i, d in enumerate(src):
			r = rows[i] if i < len(rows) else doc.append(field, {})
			type_name = m.name(kind, d.get("TypeID"))
			r.type_id = _crm_link("Item", type_name, _("Item"), m, "item_name")
			r.amount = flt(d.get("Amount"))
			r.remarks = cstr(d.get("Remarks")).strip()
			r.status = "Per Doc" if d.get("PerDoc") else "By Qty" if d.get("ByQty") else None
			r.jalur = cstr(d.get("Jalur")).strip()
			r.csize = _crm_link("Container Size", d.get("CSize"), _("Container Size"), m)
			r.currency = _crm_link("Currency", m.name("currency", d.get("CurrID")), _("Currency"), m) or r.currency
			r.jenis_karantina = cstr(d.get("JenisKarantina")).strip()
			r.uom = cstr(d.get("UOM")).strip()
			for col, mkind, f in DETAIL_NAMED:
				r.set(f, m.name(mkind, d.get(col)))
	m.raise_errors()

	doc.ascend_estimation_no = cstr(header.get("EstimationNo")).strip()
	doc.flags.from_ascend = True
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	if new_id:
		doc.ascend_estimation_id = new_id
		doc.insert()
	else:
		doc.save()
	_mark(doc.name, "Synced", "", ascend_hash=h)


# ---------------------------------------------------------------- keputusan orang


@frappe.whitelist()
def resolve(name, which):
	"""Tombol di halaman Estimation CRM: which = use_crm | use_ascend."""
	return {"use_crm": use_crm, "use_ascend": use_ascend}[which](name)


def use_crm(name):
	"""Kirim isi CRM ke Ascend, menimpa perubahan di sana (Conflict / Push Failed / kirim ulang)."""
	frappe.get_doc("CRM Estimation", name).check_permission("write")
	push(name, frappe.session.user, force=True)
	return frappe.db.get_value("CRM Estimation", name, ["ascend_sync_status", "ascend_sync_error"], as_dict=True)


def use_ascend(name):
	"""Timpa isi CRM dengan data Ascend."""
	doc = frappe.get_doc("CRM Estimation", name)
	doc.check_permission("write")
	est_id = cint(doc.ascend_estimation_id)
	if not est_id:
		frappe.throw(_("Estimasi ini belum terhubung ke Ascend"))
	with _lock():
		conn = _connect()
		try:
			cur = conn.cursor()
			m = Masters(cur)
			row = _read(cur, est_id).get(est_id)
		finally:
			conn.close()
		if not row:
			frappe.throw(_("EstimationID {0} sudah tidak ada di Ascend").format(est_id))
		try:
			_apply(doc, row, _hash(*row), m)
		except SyncError as e:
			frappe.throw(cstr(e), title=_("Tidak bisa ditarik dari Ascend"))
	return frappe.db.get_value("CRM Estimation", name, ["ascend_sync_status", "ascend_sync_error"], as_dict=True)


class _lock:
	"""MariaDB GET_LOCK: push & pull tidak pernah jalan bersamaan (lihat LOCK)."""

	def __enter__(self):
		if not frappe.db.sql("SELECT GET_LOCK(%s, 120)", LOCK)[0][0]:
			raise SyncError(_("Sinkron Ascend lain masih berjalan, coba lagi sebentar"))

	def __exit__(self, *exc):
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", LOCK)

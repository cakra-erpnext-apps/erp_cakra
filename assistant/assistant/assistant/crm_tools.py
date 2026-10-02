"""Tool untuk CRM Assistant.

Batasannya ditegakkan DI SINI, bukan hanya di teks skill. Prompt bisa diabaikan
model; kode tidak. Karena itu:

- Tidak ada satu pun tool yang membuat transaksi. Tool create_* milik Expedition
  sama sekali tidak didaftarkan untuk surface CRM (lihat CRM_TOOL_NAMES di api.py).
- Baca dibatasi ke doctype CRM saja (READ_DOCTYPES). Modul lain -- Shipping List,
  Expense Note, Sales Invoice, dsb. -- tidak bisa disentuh, bahkan bila model
  memintanya.
- Ubah status hanya untuk CRM Inquiry & CRM Quotation, HANYA pada dokumen milik
  user sendiri (owner = session user), dan hanya field status/state.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt

# Doctype yang boleh DIBACA. Sengaja daftar putih, bukan daftar hitam: doctype baru
# di modul lain tidak otomatis ikut terbuka.
READ_DOCTYPES = {
	"CRM Lead",
	"CRM Inquiry",
	"CRM Quotation",
	"CRM Estimation",
	"CRM Organization",
	"CRM Product",
	"CRM Products",
	"CRM Inquiry Status",
	"CRM Lead Status",
	"CRM Lost Reason",
	"Contact",
	# Transaksi CRM lain + master rute, supaya rekomendasi bisa melihat semuanya.
	# CRM Cost Item SENGAJA tidak: baris cost_items quotation dikunci role costing.
	"CRM Procurement",
	"CRM Tender",
	"CRM Meeting",
	"CRM Task",
	"FCRM Note",
	"CRM Type Inquiry",
	"CRM Inquiry Type Inquiry",
	"Fleet Location",
	"Fleet Route",
}

# Doctype yang statusnya boleh diubah, beserta nama field statusnya.
STATUS_FIELD = {
	"CRM Inquiry": "status",
	"CRM Quotation": "state",
}

MAX_ROWS = 50

WON_STATES = ("Win", "Converted")

# Route frontend CRM per doctype — untuk link yang bisa diklik user di chat.
_CRM_ROUTES = {
	"CRM Lead": "leads",
	"CRM Inquiry": "inquiries",
	"CRM Quotation": "quotations",
	"CRM Estimation": "estimations",
	"CRM Procurement": "procurement",
	"CRM Tender": "tenders",
}


def _doc_url(doctype: str, name: str):
	slug = _CRM_ROUTES.get(doctype)
	return f"/crm/{slug}/{name}" if slug and name else None


def _check_readable(doctype: str):
	if doctype not in READ_DOCTYPES:
		frappe.throw(
			_("Assistant CRM hanya boleh membaca data CRM. Doctype '{0}' di luar jangkauan.").format(
				doctype
			)
		)


# Rincian biaya per baris produk quotation (lihat procurement()) dikunci role
# "Procurement Costing". Baca umum di bawah ini tidak boleh jadi jalan memutarnya:
# tanpa gerbang ini, crm_get_record("CRM Quotation", ...) menyerahkan seluruh
# cost_items ke user yang di layarnya memang tidak pernah melihatnya.
_COSTING_ONLY = ("fixed_cost", "variable_cost", "cost_items")


def _hide_costing(data):
	"""Buang field costing dari hasil baca, sampai ke child table-nya.

	Bersarang, bukan cuma tingkat atas: yang dikirim get_record adalah dokumen
	utuh, dan angka yang dikunci justru duduk di baris products[]-nya.
	"""
	if _costing_access():
		return data
	_strip_costing(data)
	return data


def _strip_costing(value):
	if isinstance(value, list):
		for v in value:
			_strip_costing(v)
	elif isinstance(value, dict):
		for f in _COSTING_ONLY:
			value.pop(f, None)
		for v in value.values():
			_strip_costing(v)


_OP_IN_VALUE = re.compile(r"^\s*(not like|like|!=|>=|<=|>|<)\s+(.+)$", re.I)


def _norm_filters(filters):
	"""Model sering menulis operator di dalam nilai: {"name": "like %Tunggul%"}.
	Frappe membacanya sebagai sama-dengan teks itu -> hasil kosong, lalu model
	menyimpulkan datanya tidak ada. Ubah jadi [operator, nilai]."""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		return filters or {}
	out = {}
	for k, v in filters.items():
		if isinstance(v, str):
			m = _OP_IN_VALUE.match(v)
			if m:
				v = [m.group(1).lower(), m.group(2).strip()]
			elif "%" in v:
				v = ["like", v]
		out[k] = v
	return out


def list_records(doctype: str, filters=None, fields=None, order_by=None, limit=20):
	"""Baca daftar dokumen CRM.

	Memakai get_all, bukan get_list: user boleh melihat data cabang lain (sesuai
	permintaan -- assistant untuk memahami sistem, lintas cabang). Pembatasannya ada
	pada daftar putih doctype di atas, bukan pada permission per-baris.
	"""
	_check_readable(doctype)
	limit = min(int(limit or 20), MAX_ROWS)
	return _hide_costing(
		frappe.get_all(
			doctype,
			filters=_norm_filters(filters),
			fields=fields or ["name"],
			order_by=order_by or "modified desc",
			limit_page_length=limit,
		)
	)


def get_record(doctype: str, name: str):
	"""Baca satu dokumen CRM utuh."""
	_check_readable(doctype)
	if not frappe.db.exists(doctype, name):
		return {"_error": f"{doctype} '{name}' tidak ditemukan."}
	doc = frappe.get_doc(doctype, name)
	return _hide_costing(doc.as_dict(no_default_fields=False))


def get_status_options(doctype: str):
	"""Status apa saja yang tersedia untuk doctype ini."""
	if doctype not in STATUS_FIELD:
		return {"_error": f"Status {doctype} tidak bisa diubah lewat assistant."}
	if doctype == "CRM Inquiry":
		return {"options": frappe.get_all("CRM Inquiry Status", pluck="name")}
	field = frappe.get_meta(doctype).get_field(STATUS_FIELD[doctype])
	return {"options": (field.options or "").split("\n") if field else []}


def lookup(number: str):
	"""Cari Inquiry & Quotation dari potongan nomor (user sering hanya mengetik "2005").

	Mengembalikan kandidat dari KEDUA doctype beserta data terbarunya, supaya agent
	bisa menampilkan dokumen mana yang dimaksud dan meminta konfirmasi sebelum
	mengubah apa pun.
	"""
	q = (number or "").strip()
	if not q:
		return {"_error": "Nomor/kata kunci kosong."}
	me = frappe.session.user
	out = []
	for doctype, fields in (
		("CRM Inquiry", ["name", "status", "organization", "inquiry_date", "job_service", "owner", "modified"]),
		("CRM Quotation", ["name", "state", "account_name", "date", "net_total", "currency", "owner", "modified"]),
	):
		rows = frappe.get_all(
			doctype,
			filters={"name": ["like", f"%{q}%"]},
			fields=fields,
			order_by="modified desc",
			limit_page_length=5,
		)
		for r in rows:
			r["doctype"] = doctype
			r["milik_user_ini"] = r.get("owner") == me
			r["url"] = _doc_url(doctype, r["name"])
			# Siap tempel: model tinggal menyalin ini setiap menyebut nomornya.
			r["link_markdown"] = f"[{r['name']}]({r['url']})"
		out.extend(rows)
	if not out:
		return {"matches": [], "note": f"Tidak ada Inquiry/Quotation yang nomornya memuat '{q}'."}
	return {"matches": out}


def field_catalog(doctype: str):
	"""Daftar SEMUA field sebuah doctype CRM (nama, label, tipe, options).

	Supaya model tahu persis field apa saja yang bisa diminta lewat
	list_records/get_record — tidak menebak nama field."""
	_check_readable(doctype)
	meta = frappe.get_meta(doctype)
	skip = {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
	return {
		"doctype": doctype,
		"fields": [
			{
				"fieldname": f.fieldname,
				"label": f.label or "",
				"type": f.fieldtype,
				"options": (f.options or "") if f.fieldtype in ("Link", "Select", "Table", "Table MultiSelect") else "",
			}
			for f in meta.fields
			if f.fieldtype not in skip
		],
	}


def find_rates(origin: str = None, destination: str = None, keyword: str = None, limit: int = 10):
	"""Cari referensi rate berdasarkan rute — LINTAS user dan cabang (memang tujuannya).

	Mencari CRM Inquiry yang origin/destination-nya cocok (teks bebas, LIKE),
	opsional disaring keyword jenis job (job_service / transportation_mode /
	business_unit / type inquiry). Harga diambil dari quotation yang terhubung
	(rate yang benar-benar ditawarkan); inquiry ber-quotation didahulukan.
	"""
	if not (origin or destination):
		return {"_error": "Sebutkan origin dan/atau destination rutenya."}
	limit = min(int(limit or 10), 20)

	conds = []
	params = {"limit": limit}
	if origin:
		conds.append("i.origin LIKE %(origin)s")
		params["origin"] = f"%{origin.strip()}%"
	if destination:
		conds.append("i.destination LIKE %(dest)s")
		params["dest"] = f"%{destination.strip()}%"
	if keyword:
		conds.append(
			"(i.job_service LIKE %(kw)s OR i.transportation_mode LIKE %(kw)s "
			"OR i.business_unit LIKE %(kw)s OR EXISTS (SELECT 1 FROM `tabCRM Inquiry Type Inquiry` t "
			"WHERE t.parent = i.name AND t.type LIKE %(kw)s))"
		)
		params["kw"] = f"%{keyword.strip()}%"

	rows = frappe.db.sql(
		f"""
		SELECT i.name, i.origin, i.destination, i.status, i.job_service,
		       i.transportation_mode, i.business_unit, i.inquiry_value,
		       i.inquiry_date, i.owner, u.full_name AS owner_name, u.branch,
		       q.name AS quotation, q.state AS quotation_state,
		       q.net_total, q.currency AS quotation_currency, q.date AS quotation_date
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabUser` u ON u.name = i.owner
		LEFT JOIN `tabCRM Quotation` q ON q.inquiry = i.name AND IFNULL(q.is_void, 0) = 0
		WHERE {" AND ".join(conds)}
		ORDER BY (q.net_total IS NULL), COALESCE(q.modified, i.modified) DESC
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)
	# Quotation yang rutenya sendiri cocok (loading/unloading) — termasuk ribuan
	# quotation legacy tanpa link inquiry.
	seen_qt = {r.get("quotation") for r in rows if r.get("quotation")}
	for q in _route_quotations(origin, destination, keyword, limit=limit):
		if q["quotation"] in seen_qt:
			continue
		rows.append({
			"name": q["quotation"],
			"doctype": "CRM Quotation",
			"origin": q.get("loading"),
			"destination": q.get("unloading"),
			"status": q.get("state"),
			"job_service": q.get("subject"),
			"owner": q.get("owner"),
			"owner_name": q.get("owner_name"),
			"branch": q.get("branch"),
			"quotation": q["quotation"],
			"quotation_state": q.get("state"),
			"net_total": q.get("net_total"),
			"quotation_currency": q.get("currency"),
			"quotation_date": q.get("date"),
			"account_name": q.get("account_name"),
		})
	# Kandidat ber-quotation (punya harga nyata) didahulukan sebelum dipotong limit.
	rows.sort(key=lambda r: 0 if r.get("quotation") else 1)
	rows = rows[: max(limit, 10)]

	items_by_qt = _quotation_items([r["quotation"] for r in rows if r.get("quotation")])
	for r in rows:
		base_dt = r.get("doctype") or "CRM Inquiry"
		r["url"] = _doc_url(base_dt, r["name"])
		r["link_markdown"] = f"[{r['name']}]({r['url']})"
		if r.get("quotation"):
			r["quotation_url"] = _doc_url("CRM Quotation", r["quotation"])
			r["quotation_link_markdown"] = f"[{r['quotation']}]({r['quotation_url']})"
			# Rate per layanan ada di baris product quotation (price = harga satuan),
			# bukan cuma net_total (total seluruh item).
			r["items"] = items_by_qt.get(r["quotation"], [])
	if not rows:
		return {
			"matches": [],
			"note": "Tidak ada rute yang cocok. Coba longgarkan pencarian: satu sisi rute saja, "
			"atau tanpa keyword.",
		}
	return {"matches": rows}


def _route_quotations(origin=None, destination=None, keyword=None, limit=50):
	"""Quotation yang RUTENYA SENDIRI cocok (field loading/unloading).

	Quotation hasil import legacy tidak terhubung ke inquiry, tapi menyimpan rute
	di loading/unloading — tanpa ini ribuan rate lama tak terlihat tools."""
	conds = ["IFNULL(q.is_void, 0) = 0"]
	params = {"limit": limit}
	if origin:
		conds.append("q.loading LIKE %(origin)s")
		params["origin"] = f"%{origin.strip()}%"
	if destination:
		conds.append("q.unloading LIKE %(dest)s")
		params["dest"] = f"%{destination.strip()}%"
	if keyword:
		conds.append(
			"(q.subject LIKE %(kw)s OR q.cargo LIKE %(kw)s OR q.packaging LIKE %(kw)s "
			"OR EXISTS (SELECT 1 FROM `tabCRM Products` cp WHERE cp.parent = q.name "
			"AND cp.parenttype = 'CRM Quotation' AND cp.product_name LIKE %(kw)s))"
		)
		params["kw"] = f"%{keyword.strip()}%"
	return frappe.db.sql(
		f"""
		SELECT q.name AS quotation, q.state, q.net_total, q.currency, q.date,
		       q.subject, q.loading, q.unloading, q.account_name, q.owner,
		       u.full_name AS owner_name, u.branch
		FROM `tabCRM Quotation` q
		LEFT JOIN `tabUser` u ON u.name = q.owner
		WHERE {" AND ".join(conds)}
		ORDER BY (q.net_total IS NULL OR q.net_total = 0), q.date DESC, q.modified DESC
		LIMIT %(limit)s
		""",
		params,
		as_dict=True,
	)


def _product_names(codes):
	"""Nama produk dari master (field child `notes` = catatan bebas, bukan nama).

	product_code menaut ke CRM Product. Item dipakai sebagai cadangan: baris
	quotation hasil impor lama masih menyimpan kode item ERPNext."""
	codes = [c for c in set(codes or []) if c]
	if not codes:
		return {}
	names = dict(
		frappe.get_all(
			"CRM Product", filters={"name": ["in", codes]}, fields=["name", "product_name"], as_list=True
		)
	)
	sisa = [c for c in codes if not names.get(c)]
	if sisa:
		names.update(
			dict(
				frappe.get_all(
					"Item", filters={"name": ["in", sisa]}, fields=["name", "item_name"], as_list=True
				)
			)
		)
	return names


def _quotation_items(quotation_names):
	"""Baris product semua quotation sekaligus (satu query).

	Grid products CRM Quotation memakai child doctype "CRM Products"
	(BUKAN "CRM Quotation Product" — doctype itu ada tapi kosong/tak terpakai).
	price = harga satuan (rate), amount = price x qty."""
	if not quotation_names:
		return {}
	rows = frappe.get_all(
		"CRM Products",
		filters={"parent": ["in", list(set(quotation_names))], "parenttype": "CRM Quotation"},
		fields=["parent", "product_code", "notes", "qty", "price", "amount"],
		order_by="parent, idx",
	)
	codes = list({r.product_code for r in rows if r.product_code})
	names = _product_names(codes)
	out = {}
	for r in rows:
		code = r.get("product_code") or ""
		r["product"] = code
		r["product_name"] = names.get(code) or ""
		out.setdefault(r.pop("parent"), []).append(r)
	return out


def _stats(values):
	"""Statistik dasar sebuah daftar angka (deterministik — bukan hitungan model)."""
	vals = sorted(float(v) for v in values if v)
	if not vals:
		return None
	n = len(vals)
	mid = n // 2
	median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
	return {
		"jumlah_sampel": n,
		"min": vals[0],
		"median": round(median, 2),
		"rata2": round(sum(vals) / n, 2),
		"max": vals[-1],
	}


def price_stats(origin: str = None, destination: str = None, keyword: str = None):
	"""Statistik harga historis untuk sebuah rute — bahan rekomendasi harga.

	Harga dihitung dari quotation (net_total > 0) atas inquiry yang rutenya cocok,
	dipisah per keadaan: Win (harga yang terbukti laku), open (Draft/Sent/Waiting),
	dan Lose (harga yang ditolak — batas atas yang perlu diwaspadai). Inquiry
	tanpa quotation ikut dihitung lewat inquiry_value sebagai indikasi kasar.
	Semua agregat dihitung DI SINI, bukan oleh model."""
	if not (origin or destination):
		return {"_error": "Sebutkan origin dan/atau destination rutenya."}

	conds = []
	params = {}
	if origin:
		conds.append("i.origin LIKE %(origin)s")
		params["origin"] = f"%{origin.strip()}%"
	if destination:
		conds.append("i.destination LIKE %(dest)s")
		params["dest"] = f"%{destination.strip()}%"
	if keyword:
		conds.append(
			"(i.job_service LIKE %(kw)s OR i.transportation_mode LIKE %(kw)s "
			"OR i.business_unit LIKE %(kw)s OR EXISTS (SELECT 1 FROM `tabCRM Inquiry Type Inquiry` t "
			"WHERE t.parent = i.name AND t.type LIKE %(kw)s))"
		)
		params["kw"] = f"%{keyword.strip()}%"

	rows = frappe.db.sql(
		f"""
		SELECT i.name AS inquiry, i.origin, i.destination, i.job_service,
		       i.inquiry_value, i.exchange_rate,
		       q.name AS quotation, q.state, q.net_total, q.currency, q.date
		FROM `tabCRM Inquiry` i
		LEFT JOIN `tabCRM Quotation` q ON q.inquiry = i.name AND IFNULL(q.is_void, 0) = 0
		WHERE {" AND ".join(conds)}
		ORDER BY COALESCE(q.date, i.inquiry_date) DESC
		""",
		params,
		as_dict=True,
	)

	# Quotation yang rutenya sendiri cocok (loading/unloading) — quotation legacy
	# tidak terhubung inquiry tapi menyimpan rute & harga nyata.
	seen_qt = {r.quotation for r in rows if r.quotation}
	for q in _route_quotations(origin, destination, keyword, limit=200):
		if q["quotation"] in seen_qt:
			continue
		rows.append(frappe._dict({
			"inquiry": None,
			"origin": q.get("loading"),
			"destination": q.get("unloading"),
			"job_service": q.get("subject"),
			"inquiry_value": 0,
			"exchange_rate": 1,
			"quotation": q["quotation"],
			"state": q.get("state"),
			"net_total": q.get("net_total"),
			"currency": q.get("currency"),
			"date": q.get("date"),
		}))

	if not rows:
		return {"note": "Tidak ada inquiry/quotation yang cocok dengan rute ini. Coba longgarkan pencarian."}

	# Converted = Win yang sudah jadi estimasi, jadi ikut terbukti laku.
	win = [r for r in rows if r.quotation and r.state in WON_STATES and (r.net_total or 0) > 0]
	open_ = [
		r for r in rows
		if r.quotation and r.state not in WON_STATES + ("Lose",) and (r.net_total or 0) > 0
	]
	lose = [r for r in rows if r.quotation and r.state == "Lose" and (r.net_total or 0) > 0]
	inq_vals = [
		(r.inquiry_value or 0) * (r.exchange_rate or 1)
		for r in rows
		if not r.quotation and (r.inquiry_value or 0) > 0
	]

	# Rate sesungguhnya ada di baris product quotation (price = harga satuan) —
	# net_total hanyalah totalnya. Ambil item semua quotation yang cocok, lalu
	# hitung statistik PER PRODUCT per keadaan (Win/open/Lose). Mata uang TIDAK
	# dicampur: produk quotation USD diberi label [USD] terpisah dari IDR.
	items_by_qt = _quotation_items([r.quotation for r in rows if r.quotation])
	state_of = {r.quotation: r.state for r in rows if r.quotation}
	ccy_of = {r.quotation: (r.currency or "IDR") for r in rows if r.quotation}
	per_product = {}
	for qt, items in items_by_qt.items():
		st = state_of.get(qt)
		bucket = "win" if st in WON_STATES else ("lose" if st == "Lose" else "open")
		ccy = ccy_of.get(qt, "IDR")
		for it in items:
			if (it.get("price") or 0) <= 0:
				continue
			label = it["product"] + (f" - {it['product_name']}" if it.get("product_name") else "")
			if ccy != "IDR":
				label += f" [{ccy}]"
			per_product.setdefault(label, {"win": [], "open": [], "lose": []})[bucket].append(it["price"])
	per_product_stats = {
		p: {k: _stats(v) for k, v in b.items() if v} for p, b in per_product.items()
	}

	def stats_per_ccy(bucket):
		"""Statistik total per mata uang — IDR dan USD tidak boleh dirata-rata bersama."""
		by = {}
		for r in bucket:
			by.setdefault((r.currency or "IDR"), []).append(r.net_total)
		return {c: _stats(v) for c, v in by.items()} or None

	def refs(bucket, n=5):
		out = []
		for r in bucket[:n]:
			out.append({
				"quotation": r.quotation,
				"quotation_link": f"[{r.quotation}]({_doc_url('CRM Quotation', r.quotation)})",
				"inquiry_link": f"[{r.inquiry}]({_doc_url('CRM Inquiry', r.inquiry)})" if r.inquiry else None,
				"rute": f"{(r.origin or '-').strip()} -> {(r.destination or '-').strip()}",
				"job": (r.job_service or "-")[:60],
				"total": r.net_total,
				"currency": r.currency,
				"tanggal": str(r.date or ""),
				"items": items_by_qt.get(r.quotation, []),
			})
		return out

	return {
		"total_inquiry_cocok": len({r.inquiry for r in rows if r.inquiry}),
		"total_quotation_cocok": len({r.quotation for r in rows if r.quotation}),
		"rate_per_product": per_product_stats,
		"win": {"stats_total": stats_per_ccy(win), "harga_win_terbaru": refs(win, 1), "referensi": refs(win)},
		"open": {"stats_total": stats_per_ccy(open_), "referensi": refs(open_)},
		"lose": {"stats_total": stats_per_ccy(lose), "referensi": refs(lose)},
		"inquiry_value_tanpa_quotation": _stats(inq_vals),
		"catatan": (
			"rate_per_product = statistik HARGA SATUAN per item/layanan (ini rate yang "
			"sebenarnya); stats_total = total per quotation. Prioritas dasar rekomendasi: "
			"harga Win terbaru (terbukti laku) > median Win > quotation open terbaru > "
			"inquiry_value. Harga Lose = batas atas yang ditolak pasar."
		),
	}


# --- Tab Procurement (costing quotation) ---------------------------------

# Baris tabel yang ikut dikirim ke model. Tab Procurement bisa memuat puluhan baris
# biaya; yang dibutuhkan untuk menjawab pertanyaan adalah totalnya plus contoh
# barisnya, bukan seluruh tabel (lihat larangan dump di skill).
PROC_MAX_ROWS = 15


def _costing_access() -> bool:
	"""Gerbang yang sama dengan blok costing di UI: rincian Fixed/Variable hanya
	untuk tim Procurement (roles.PROCUREMENT_ACCESS, System Manager ikut).

	Assistant tidak boleh jadi pintu belakang atas angka yang sengaja tidak
	dikirim server ke browser user.
	"""
	from crm_cakra.roles import has_procurement_access

	return has_procurement_access()


def _cost_table(quotation: str, parentfield: str):
	rows = frappe.get_all(
		"CRM Cost Item",
		filters={"parent": quotation, "parenttype": "CRM Quotation", "parentfield": parentfield},
		fields=["item_name", "qty", "uom", "rate", "amount"],
		order_by="idx",
	)
	out = {"jumlah_baris": len(rows), "baris": rows[:PROC_MAX_ROWS]}
	if len(rows) > PROC_MAX_ROWS:
		out["baris_tidak_ditampilkan"] = len(rows) - PROC_MAX_ROWS
	return out


def procurement(quotation: str):
	"""Costing sebuah quotation: status, biaya, margin, dan persetujuannya.

	Angkanya milik quotation, disalin dari dokumen CRM Procurement inquiry-nya saat
	quotation pertama disimpan (lihat pull_cost_from_procurement).

	Semua angka DIBACA dari dokumen (hasil hitungan server saat disimpan), tidak
	dihitung ulang di sini — yang muncul di chat sama persis dengan yang dilihat
	user di layar. Yang dihitung di sini hanya turunan sederhana (persen margin,
	selisih harga terhadap Base Price), tetap di kode, bukan di kepala model.

	Rincian Fixed/Variable per BARIS PRODUK dikunci role "Procurement Costing";
	tanpa role, yang keluar hanya Base Price & margin baris — persis seperti kartu
	costing di layar user tanpa role.
	"""
	name = (quotation or "").strip()
	if not name:
		return {"_error": "Sebutkan nomor quotation-nya."}
	if not frappe.db.exists("CRM Quotation", name):
		out = lookup(name)
		out["note"] = (
			f"Quotation '{name}' tidak ada. Ini kandidat yang nomornya mirip — pastikan dulu "
			"ke user quotation mana yang dimaksud, lalu panggil lagi dengan nomor lengkapnya."
		)
		return out

	q = frappe.get_doc("CRM Quotation", name)
	detail = _costing_access()
	names = _product_names([p.product_code for p in q.products])

	items = []
	for p in q.products[:PROC_MAX_ROWS]:
		base = flt(p.procurement_price)
		row = {
			"produk": p.product_code,
			"nama": names.get(p.product_code) or "",
			"catatan": p.notes,
			"qty": p.qty,
			"uom": p.uom,
			"duration_hari": p.duration,
			"harga_jual": p.price,
			"amount": p.amount,
			"base_price": base,
			"margin_percent": p.margin_percent,
			"margin_amount": p.margin_amount,
		}
		if base > 0:
			# Lantai harga: dicek server saat CETAK (bukan saat simpan).
			row["selisih_vs_base_price"] = flt(p.price) - base
			row["di_bawah_base_price"] = flt(p.price) < base
		if detail:
			row["fixed_cost"] = p.fixed_cost
			row["variable_cost"] = p.variable_cost
		items.append(row)

	proc = frappe.db.get_value(
		"CRM Procurement", {"inquiry": q.inquiry}, ["name", "status"], as_dict=True
	) if q.inquiry else None

	net = flt(q.net_total)
	fixed = flt(q.total_fixed_cost)
	variable = flt(q.total_variable_cost)
	margin = flt(q.summary_margin)

	url = _doc_url("CRM Quotation", name)
	return {
		"quotation": name,
		"url": url,
		"link_markdown": f"[{name}]({url})",
		"subject": q.subject,
		"customer": q.account_name,
		"inquiry": q.inquiry,
		"inquiry_link_markdown": f"[{q.inquiry}]({_doc_url('CRM Inquiry', q.inquiry)})" if q.inquiry else None,
		"state": q.state,
		"currency": q.currency,
		"revenue": {
			"net_total": net,
			"jumlah_baris": len(q.products),
			"items": items,
			"baris_tidak_ditampilkan": max(len(q.products) - PROC_MAX_ROWS, 0),
		},
		"expense_fixed_cost": {"total": fixed, **_cost_table(name, "fixed_cost_items")},
		"expense_variable_cost": {"total": variable, **_cost_table(name, "variable_cost_items")},
		"summary": {
			"total_marketing_cost": net,
			"total_fixed_cost": fixed,
			"total_variable_cost": variable,
			"margin": margin,
			"margin_percent": round(margin / net * 100, 2) if net else None,
		},
		"margin_vs_estimation_cost": {
			"estimation_costing": flt(q.estimation_costing),
			"margin": flt(q.margin),
		},
		"procurement": {
			"dokumen": proc.name if proc else None,
			"status": proc.status if proc else None,
			"keterangan": "Approve = costing sudah disetujui tim Procurement; Draft/Request/Reviewing = angka belum final.",
		},
		"margin_minus": {
			"negative_margin_reason": q.negative_margin_reason or None,
			"aturan": "Margin minus boleh disimpan, tapi wajib alasan tertulis sebelum quotation dicetak/dikirim.",
		},
		"rincian_costing_per_baris": detail or (
			"Disembunyikan — rincian Fixed/Variable per baris produk hanya untuk role "
			"Procurement Costing. Base Price & margin baris tetap ditampilkan."
		),
		"rumus": (
			"Margin Summary = Total Marketing Cost (net_total) - (Total Fixed Cost + Total "
			"Variable Cost). Base Price baris = (Fixed Cost/hari x Duration) + Variable Cost "
			"+ Margin, dengan Margin = (Fixed + Variable) x Margin %. margin = net_total - "
			"estimation_costing (Estimation Cost inquiry = Fixed + Variable Procurement)."
		),
	}


# --- Kalkulator aman: model TIDAK dipercaya berhitung sendiri --------------
import ast as _ast
import operator as _op

_CALC_OPS = {
	_ast.Add: _op.add,
	_ast.Sub: _op.sub,
	_ast.Mult: _op.mul,
	_ast.Div: _op.truediv,
	_ast.FloorDiv: _op.floordiv,
	_ast.Mod: _op.mod,
	_ast.Pow: _op.pow,
	_ast.USub: _op.neg,
	_ast.UAdd: _op.pos,
}
_CALC_FUNCS = {"round": round, "abs": abs, "min": min, "max": max}


def _calc_eval(node):
	if isinstance(node, _ast.Expression):
		return _calc_eval(node.body)
	if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)):
		return node.value
	if isinstance(node, _ast.BinOp) and type(node.op) in _CALC_OPS:
		return _CALC_OPS[type(node.op)](_calc_eval(node.left), _calc_eval(node.right))
	if isinstance(node, _ast.UnaryOp) and type(node.op) in _CALC_OPS:
		return _CALC_OPS[type(node.op)](_calc_eval(node.operand))
	if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) and node.func.id in _CALC_FUNCS:
		return _CALC_FUNCS[node.func.id](*[_calc_eval(a) for a in node.args])
	raise ValueError(f"Ekspresi tidak diizinkan: {_ast.dump(node)[:60]}")


def calculate(expression: str):
	"""Hitung ekspresi aritmetika secara pasti (mis. '12500000 * 1.1' untuk markup 10%).

	Hanya angka, + - * / // % **, kurung, dan round/abs/min/max. Bukan eval bebas."""
	expr = (expression or "").strip()
	if not expr or len(expr) > 300:
		return {"_error": "Ekspresi kosong atau terlalu panjang."}
	try:
		value = _calc_eval(_ast.parse(expr, mode="eval"))
	except Exception as e:
		return {"_error": f"Ekspresi tidak sah: {e}"}
	return {
		"expression": expr,
		"result": value,
		"formatted": f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", "."),
	}


BULK_LIMIT = 5


def bulk_update_status(items, user_approved=False):
	"""Ubah status beberapa dokumen sekaligus — maksimal BULK_LIMIT per panggilan.

	`items` = daftar {doctype, name, status}; boleh campuran Inquiry & Quotation.
	Penjagaan per dokumen sama persis dengan update_status (doctype terdaftar,
	milik user sendiri, status sah, wajib user_approved). Batas 5 ditegakkan di
	kode: permintaan lebih dari itu ditolak utuh, bukan diproses sebagian diam-diam.
	"""
	if isinstance(items, str):
		import json

		try:
			items = json.loads(items)
		except ValueError:
			return {"_error": "Parameter items harus berupa array {doctype, name, status}."}
	if not isinstance(items, list) or not items:
		return {"_error": "Parameter items harus berupa array berisi minimal satu dokumen."}
	if len(items) > BULK_LIMIT:
		return {
			"_error": f"Maksimal {BULK_LIMIT} dokumen per perubahan bulk. Kamu mengirim {len(items)}. "
			"Minta user memecah permintaannya."
		}
	if not user_approved:
		return {
			"_error": "Perubahan status butuh persetujuan user. Tampilkan daftar dokumen + status "
			"lama -> baru, tunggu user setuju, lalu panggil ulang dengan user_approved=true."
		}

	results = []
	for it in items:
		r = update_status(
			(it or {}).get("doctype"),
			(it or {}).get("name"),
			(it or {}).get("status"),
			user_approved=True,
			reason=(it or {}).get("reason"),
			notes=(it or {}).get("notes"),
		)
		r["name"] = r.get("name") or (it or {}).get("name")
		results.append(r)
	ok = [r for r in results if r.get("ok")]
	failed = [r for r in results if r.get("_error")]
	return {"ok": len(failed) == 0, "changed": len(ok), "failed": len(failed), "results": results}


def _is_lost_status(doctype: str, status: str) -> bool:
	if doctype == "CRM Quotation":
		return status == "Lose"
	if doctype == "CRM Inquiry":
		return (frappe.db.get_value("CRM Inquiry Status", status, "type") or "") == "Lost"
	return False


def _resolve_lost_reason(reason: str, notes: str | None):
	"""Cocokkan alasan ke master CRM Lost Reason. Alasan bebas jatuh ke 'Other'
	dengan teks aslinya tersimpan sebagai catatan — tidak ada informasi yang dibuang."""
	options = frappe.get_all("CRM Lost Reason", pluck="name")
	match = next((o for o in options if o.lower() == (reason or "").strip().lower()), None)
	if match:
		return match, (notes or "").strip() or None
	fallback = next((o for o in options if o.lower() == "other"), None)
	joined = " -- ".join(x for x in [(reason or "").strip(), (notes or "").strip()] if x) or None
	return fallback, joined


def update_status(doctype: str, name: str, status: str, user_approved=False, reason=None, notes=None):
	"""Ubah status CRM Inquiry / CRM Quotation.

	Penjagaan, semuanya di kode:
	  1. hanya doctype di STATUS_FIELD -- tidak bisa menyentuh yang lain;
	  2. hanya dokumen MILIK USER SENDIRI (owner = session user);
	  3. hanya setelah user menyetujui secara eksplisit (user_approved);
	  4. status kalah (Inquiry->Lost / Quotation->Lose) WAJIB disertai alasan --
	     tersimpan di lost_reason/lost_notes inquiry (Quotation menyimpannya di
	     inquiry yang terhubung, karena Lose memang mendorong inquiry jadi Lost).
	Status dicocokkan case-insensitive; status tak dikenal membalas daftar pilihan
	supaya agent bisa langsung menawarkannya ke user.
	"""
	if doctype not in STATUS_FIELD:
		return {"_error": f"Assistant hanya boleh mengubah status CRM Inquiry & CRM Quotation, bukan {doctype}."}

	if not user_approved:
		return {
			"_error": "Perubahan status butuh persetujuan user. Tanyakan dulu, lalu panggil ulang "
			"dengan user_approved=true setelah user setuju."
		}

	if not frappe.db.exists(doctype, name):
		return {"_error": f"{doctype} '{name}' tidak ditemukan."}

	me = frappe.session.user
	owner = frappe.db.get_value(doctype, name, "owner")
	if owner != me:
		return {
			"_error": f"{name} bukan milik Anda (pemilik: {owner}). Assistant hanya boleh mengubah "
			"status dokumen milik user sendiri."
		}

	field = STATUS_FIELD[doctype]
	valid = get_status_options(doctype).get("options") or []
	# Case-insensitive: user menulis "win", sistem menyimpannya sebagai "Win".
	canonical = next((v for v in valid if v.lower() == (status or "").strip().lower()), None)
	if valid and not canonical:
		return {
			"_error": f"Status '{status}' tidak dikenal untuk {doctype}. "
			f"Pilihan statusnya: {', '.join(valid)}. Tampilkan pilihan ini ke user "
			"supaya dia bisa langsung memilih."
		}
	status = canonical or status

	# Status kalah wajib beralasan -- tanpa alasan, minta agent bertanya dulu.
	lost = _is_lost_status(doctype, status)
	lost_reason = lost_notes = None
	if lost:
		if not (reason or "").strip():
			options = frappe.get_all("CRM Lost Reason", pluck="name")
			return {
				"_error": "Status kalah butuh alasan. Tanyakan dulu kenapa kalah, lalu panggil ulang "
				f"dengan parameter reason. Pilihan alasan: {', '.join(options)}. "
				"Alasan bebas juga boleh -- akan dicatat sebagai Other + catatan."
			}
		lost_reason, lost_notes = _resolve_lost_reason(reason, notes)

	old = frappe.db.get_value(doctype, name, field)
	if old == status and not lost:
		return {"ok": True, "unchanged": True, "name": name, "status": status, "url": _doc_url(doctype, name)}

	doc = frappe.get_doc(doctype, name)
	doc.set(field, status)
	if lost and doctype == "CRM Inquiry":
		doc.lost_reason = lost_reason
		if lost_notes:
			doc.lost_notes = lost_notes
	# ignore_mandatory: dokumen lama (hasil import) belum punya field wajib yang
	# ditambahkan belakangan; kita hanya menyentuh status.
	doc.flags.ignore_mandatory = True
	doc.save()

	# Quotation tidak punya field alasan -- alasannya milik inquiry yang terhubung,
	# yang oleh cascade Lose memang ikut jadi Lost.
	reason_saved_to = "CRM Inquiry" if (lost and doctype == "CRM Inquiry") else None
	if lost and doctype == "CRM Quotation":
		linked_inquiry = frappe.db.get_value("CRM Quotation", name, "inquiry")
		if linked_inquiry:
			updates = {"lost_reason": lost_reason}
			if lost_notes:
				updates["lost_notes"] = lost_notes
			frappe.db.set_value("CRM Inquiry", linked_inquiry, updates)
			reason_saved_to = linked_inquiry
	frappe.db.commit()

	url = _doc_url(doctype, name)
	out = {
		"ok": True,
		"doctype": doctype,
		"name": name,
		"from": old,
		"to": status,
		"url": url,
		"link_markdown": f"[{name}]({url})",
		"_note": "Sebutkan dokumen ini ke user memakai link_markdown supaya bisa diklik.",
	}
	if lost:
		out["lost_reason"] = lost_reason
		if lost_notes:
			out["lost_notes"] = lost_notes
		out["reason_saved_to"] = reason_saved_to or "(tidak ada inquiry terhubung -- alasan tidak tersimpan)"
	return out


# --- Draft Inquiry / Quotation: assistant MENYIAPKAN, user yang menyimpan ---------
#
# Tidak ada insert di sini. Isian disimpan sementara di cache, assistant memberi link
# ke form New CRM (?draft=<token>), form mengisi dirinya dari situ, dan user sendiri
# yang memeriksa lalu menekan Create. Nomor dokumen baru lahir saat itu.

DRAFT_ROUTES = {"CRM Inquiry": "inquiries", "CRM Quotation": "quotations"}
# ponytail: draft hidup di redis cache (hilang kalau redis-cache di-restart);
# pindah ke tabel kalau link yang mati setelah restart jadi keluhan.
DRAFT_TTL = 3 * 24 * 3600

# Diurus sistem/workflow atau hitungan server, bukan isian draft.
_DRAFT_SKIP = {
	"name", "owner", "naming_series", "status", "state", "is_void", "void_reason",
	"void_at", "void_by", "status_change_log", "account", "account_name",
	"cost_items", "fixed_cost_items", "variable_cost_items", "net_total", "total",
	"margin", "summary_margin", "estimation_costing", "total_fixed_cost",
	"total_variable_cost", "approved_by", "approved_on", "approval_required",
	"approval_signature", "negative_margin_reason", "estimasi_tarif",
	"costing_procurement", "annual_revenue", "procurement_status",
}
_ROW_SKIP = {
	"procurement_price", "fixed_cost", "variable_cost", "cost_key", "cost_seeded",
	"margin_amount", "amount", "net_amount",
}
_ROW_META = {"name", "owner", "parent", "parenttype", "creation", "modified", "modified_by", "docstatus"}


def draft_key(token: str) -> str:
	return f"crm_assistant_draft|{token}"


def _draft_rows(df, rows):
	"""Baris child dari isian model. String polos = nilai Link pertama (Table MultiSelect)."""
	child = frappe.get_meta(df.options)
	link = next((f.fieldname for f in child.fields if f.fieldtype == "Link"), None)
	out = []
	for r in rows if isinstance(rows, list) else [rows]:
		if not isinstance(r, dict):
			r = {link: r} if link else {}
		row = {k: v for k, v in r.items() if child.has_field(k) and k not in _ROW_SKIP}
		if row:
			out.append(row)
	return out


def _usable_inquiry(name: str):
	"""Inquiry yang boleh jadi dasar quotation -- aturan yang sama dengan picker
	form New Quotation (crm_cakra.api.quotation.get_available_inquiries)."""
	from crm_cakra.api.quotation import _can_see_all

	inq = frappe.db.get_value(
		"CRM Inquiry",
		name,
		["name", "status", "is_void", "owner", "_assign", "organization", "subject",
		 "origin", "destination", "cargo_commodity", "cargo_packaging"],
		as_dict=True,
	)
	if not inq:
		return None, f"Inquiry '{name}' tidak ada. Cari dulu nomornya dengan crm_lookup."
	if inq.is_void:
		return None, f"Inquiry {name} sudah di-void."
	if inq.status == "Lost":
		return None, f"Inquiry {name} berstatus Lost, tidak bisa dibuatkan quotation."
	me = frappe.session.user
	if inq.owner != me and f'"{me}"' not in (inq._assign or "") and not _can_see_all(me):
		return None, (
			f"Inquiry {name} bukan milik user ini dan tidak di-assign ke dia, jadi tidak bisa "
			"dipilih untuk quotation-nya. Minta pemiliknya meng-assign dulu."
		)
	return inq, None


def create_draft(doctype: str, values=None):
	"""Siapkan draft CRM Inquiry / CRM Quotation TANPA menyimpan. Lihat blok di atas."""
	if doctype not in DRAFT_ROUTES:
		return {"_error": "Draft hanya untuk CRM Inquiry atau CRM Quotation."}
	values = frappe.parse_json(values) if isinstance(values, str) else (values or {})
	if not isinstance(values, dict):
		return {"_error": "values harus objek {fieldname: nilai}."}

	meta = frappe.get_meta(doctype)
	doc = frappe.new_doc(doctype)
	me = frappe.session.user
	ignored = []
	for k, v in values.items():
		df = meta.get_field(k)
		if not df or df.read_only or k in _DRAFT_SKIP or v in (None, ""):
			ignored.append(k)
			continue
		if df.fieldtype in ("Table", "Table MultiSelect"):
			doc.set(k, _draft_rows(df, v))
		else:
			doc.set(k, v if isinstance(v, (int, float)) else str(v).strip())

	if doctype == "CRM Inquiry":
		doc.status = frappe.get_all(
			"CRM Inquiry Status", order_by="position asc", pluck="name", limit=1
		)[0]
		doc.inquiry_owner = doc.inquiry_owner or me
		doc.currency = doc.currency or "IDR"
		route = ("origin", "destination")
	else:
		# Aturan keras: quotation selalu lahir dari inquiry.
		inq_name = (doc.inquiry or "").strip()
		if not inq_name:
			return {
				"_error": (
					"Quotation WAJIB berdasarkan Inquiry. Tanyakan inquiry mana ke user "
					"(crm_lookup), atau buatkan draft Inquiry-nya dulu. Jangan pernah membuat "
					"quotation tanpa inquiry."
				)
			}
		inq, err = _usable_inquiry(inq_name)
		if err:
			return {"_error": err}
		# Sama dengan watcher inquiry di QuotationNew.vue.
		doc.account = inq.organization
		doc.subject = doc.subject or inq.subject
		doc.loading = doc.loading or inq.origin
		doc.unloading = doc.unloading or inq.destination
		doc.cargo = doc.cargo or inq.cargo_commodity
		doc.packaging = doc.packaging or inq.cargo_packaging
		if not doc.products:
			for p in frappe.get_all(
				"CRM Products",
				filters={"parent": inq_name, "parenttype": "CRM Inquiry"},
				fields=["product_code", "notes", "qty", "uom", "duration", "price", "currency", "rate"],
				order_by="idx",
			):
				doc.append("products", p)
		doc.printed_by = doc.printed_by or me
		route = ("loading", "unloading")

	for p in doc.get("products") or []:
		p.amount = flt(p.qty) * flt(p.price) * (flt(p.rate) or 1)

	# Link yang tidak ada di master; sekalian mengisi field fetch_from
	# (organization_name dari organization, dsb.).
	invalid = []
	for d in [doc, *doc.get_all_children()]:
		try:
			bad, _cancelled = d.get_invalid_links()
			invalid += [msg for _f, _v, msg in bad]
		except AssertionError:
			invalid.append(f"Nilai tidak sah di {d.doctype}")
	for df in meta.fields:
		val = doc.get(df.fieldname)
		if df.fieldtype == "Select" and val:
			opts = [o for o in (df.options or "").split("\n") if o]
			if val not in opts:
				invalid.append(f"{df.label}: '{val}' bukan pilihan. Pilihan: {', '.join(opts)}")

	missing = [df.label for df in meta.fields if df.reqd and not doc.get(df.fieldname)]
	missing += [meta.get_label(f) for f in route if not doc.get(f) and meta.get_label(f) not in missing]

	if missing or invalid:
		return {
			"draft_dibuat": False,
			"field_wajib_kosong": missing,
			"isian_tidak_valid": invalid,
			"diabaikan": ignored,
			"note": (
				"Draft BELUM dibuat. Tanyakan field yang kosong/tidak valid ke user (pakai "
				"crm_field_catalog / crm_list_records untuk pilihan master), lalu panggil lagi."
			),
		}

	data = {}
	for df in meta.fields:
		val = doc.get(df.fieldname)
		if df.fieldtype in ("Table", "Table MultiSelect"):
			if val:
				cols = frappe.get_meta(df.options).get_valid_columns()
				data[df.fieldname] = [
					{
						**{k: r.get(k) for k in cols if k not in _ROW_META and r.get(k) not in (None, "")},
						"doctype": df.options,
						"parentfield": df.fieldname,
						"idx": n,
					}
					for n, r in enumerate(val, 1)
				]
		elif val not in (None, "") and df.fieldtype not in ("Button", "HTML") and df.fieldname != "naming_series":
			data[df.fieldname] = val
	data = frappe.parse_json(frappe.as_json(data))  # tanggal/Decimal -> JSON polos

	token = frappe.generate_hash(length=12)
	frappe.cache().set_value(
		draft_key(token), {"user": me, "doctype": doctype, "values": data}, expires_in_sec=DRAFT_TTL
	)
	url = f"/crm/{DRAFT_ROUTES[doctype]}/new?draft={token}"
	label = "Inquiry" if doctype == "CRM Inquiry" else "Quotation"
	return {
		"draft_dibuat": True,
		"tersimpan": False,
		"url": url,
		"link_markdown": f"[Buka draft {label}]({url})",
		"isi": {k: v for k, v in data.items() if not isinstance(v, list)},
		"jumlah_baris": {k: len(v) for k, v in data.items() if isinstance(v, list)},
		"diabaikan": ignored,
		"berlaku": "3 hari",
		"note": (
			"Dokumen BELUM tersimpan dan belum bernomor. User membuka link, memeriksa isinya, "
			"lalu menekan Create sendiri."
		),
	}


# --- Kisaran harga sebuah inquiry: biaya + jarak + pasar ----------------------------

def _route_km(origin, destination):
	"""KM rute dari cache Fleet Route; kalau belum ada, minta OSRM (sekali, lalu tercache)."""
	if not (origin and destination):
		return None
	try:
		from erp.fleet.doctype.fleet_route.fleet_route import get_distance

		return flt(get_distance(origin, destination).get("distance_km")) or None
	except Exception:
		# Lokasi tanpa koordinat / OSRM mati: jarak tidak diketahui, bukan error tool.
		frappe.clear_last_message()
		return None


def _price_per_km(transportation_mode=None, exclude_inquiry=None):
	"""Harga per KM dari quotation yang KM-nya terisi, per moda inquiry-nya."""
	conds = [
		"q.distance_km > 0", "q.net_total > 0", "IFNULL(q.is_void, 0) = 0",
		"q.state != 'Lose'", "IFNULL(q.currency, 'IDR') = 'IDR'",
	]
	params = {}
	if transportation_mode:
		conds.append("i.transportation_mode = %(mode)s")
		params["mode"] = transportation_mode
	if exclude_inquiry:
		conds.append("IFNULL(q.inquiry, '') != %(ex)s")
		params["ex"] = exclude_inquiry
	rows = frappe.db.sql(
		f"""SELECT q.net_total / q.distance_km AS per_km
		FROM `tabCRM Quotation` q LEFT JOIN `tabCRM Inquiry` i ON i.name = q.inquiry
		WHERE {" AND ".join(conds)} ORDER BY q.date DESC LIMIT 200""",
		params,
		as_dict=True,
	)
	return _stats([r.per_km for r in rows])


def _product_cost(product_code, duration, qty):
	"""Biaya standar satu baris produk = (Fixed/hari x durasi + Variable komponen) x qty.
	Rumus yang sama dengan Base Price (calculate_costing), margin 0."""
	from crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component import (
		VARIABLE,
		resolve_for_product,
	)

	per_day = flt(frappe.db.get_value("CRM Product", product_code, "fixed_cost_per_day"))
	variable = sum(
		flt(i.qty) * flt(i.rate) for comp in resolve_for_product(product_code, VARIABLE) for i in comp.items
	)
	fixed = per_day * (cint(duration) or 1)
	return (fixed + variable) * (flt(qty) or 1), fixed, variable


def estimate_price(inquiry: str):
	"""Bahan menentukan kisaran harga sebuah inquiry. Semua angka dihitung DI SINI."""
	name = (inquiry or "").strip()
	if not name or not frappe.db.exists("CRM Inquiry", name):
		out = lookup(name) if name else {}
		out["note"] = f"Inquiry '{name}' tidak ada. Pastikan nomornya ke user, lalu panggil lagi."
		return out
	i = frappe.get_doc("CRM Inquiry", name)

	# 1. Biaya: dokumen Procurement > angka di inquiry > biaya standar produk.
	proc = frappe.db.get_value(
		"CRM Procurement", {"inquiry": name},
		["name", "status", "total_fixed_cost", "total_variable_cost"], as_dict=True,
	)
	fixed = flt(proc.total_fixed_cost) if proc else flt(i.estimasi_tarif)
	variable = flt(proc.total_variable_cost) if proc else flt(i.costing_procurement)
	sumber = None
	if fixed or variable:
		sumber = f"CRM Procurement {proc.name} (status {proc.status})" if proc else "isian Fixed/Variable di inquiry"

	detail = _costing_access()
	names = _product_names([p.product_code for p in i.products])
	produk, std_total = [], 0.0
	for p in i.products:
		if not p.product_code or not frappe.db.exists("CRM Product", p.product_code):
			continue
		total, f, v = _product_cost(p.product_code, p.duration, p.qty)
		std_total += total
		row = {
			"produk": p.product_code, "nama": names.get(p.product_code) or "",
			"qty": p.qty, "duration_hari": p.duration, "biaya_standar": total,
		}
		if detail:
			row.update({"fixed": f, "variable": v})
		produk.append(row)

	biaya = fixed + variable
	if not biaya and std_total:
		biaya, sumber = std_total, "biaya standar master produk (belum ada costing Procurement)"

	# 2. Jarak & pasar.
	km = _route_km(i.origin, i.destination)
	rute = price_stats(i.origin, i.destination) if (i.origin or i.destination) else {}
	win_idr = ((rute.get("win") or {}).get("stats_total") or {}).get("IDR")
	open_idr = ((rute.get("open") or {}).get("stats_total") or {}).get("IDR")
	per_km = _price_per_km(i.transportation_mode, name)

	acuan = {}
	if win_idr:
		acuan["median_win_rute_sama"] = win_idr["median"]
	if open_idr:
		acuan["median_penawaran_berjalan_rute_sama"] = open_idr["median"]
	if per_km and km:
		acuan["median_harga_per_km_x_jarak"] = round(per_km["median"] * km, 2)

	def margin_at(price):
		if not biaya or not price:
			return {}
		return {"margin": round(price - biaya, 2), "margin_persen": round((price - biaya) / price * 100, 2)}

	pasar = [v for v in acuan.values() if v]
	low = biaya or (min(pasar) if pasar else None)
	high = max(pasar) if pasar and max(pasar) > (low or 0) else None

	return {
		"inquiry": name,
		"link_markdown": f"[{name}]({_doc_url('CRM Inquiry', name)})",
		"input_inquiry": {
			"rute": f"{i.origin or '-'} -> {i.destination or '-'}",
			"jarak_km": km,
			"transportation_mode": i.transportation_mode,
			"business_unit": i.business_unit,
			"job_service": i.job_service,
			"type_inquiry": [t.get("type") for t in (i.get("type_inquiry") or [])],
			"qty": i.qty,
			"qty_volume": i.qty_volume,
			"cargo_commodity": i.cargo_commodity,
			"cargo_weight": i.cargo_weight,
			"cargo_packaging": i.cargo_packaging,
			"incoterms": i.incoterms,
			"date_shipment": str(i.date_shipment or ""),
			"inquiry_value_dari_customer": flt(i.inquiry_value) or None,
		},
		"biaya": {
			"fixed_cost": fixed,
			"variable_cost": variable,
			"total": biaya or None,
			"sumber": sumber or "BELUM ADA -- costing belum diisi Procurement dan produk tanpa biaya standar",
			"final": bool(proc and proc.status == "Approve"),
			"biaya_standar_produk": produk,
			"per_km": round(biaya / km, 2) if biaya and km else None,
		},
		"pasar": {
			"acuan": {k: {"harga": v, **margin_at(v)} for k, v in acuan.items()},
			"harga_per_km_historis": per_km,
			"referensi_win_terbaru": (rute.get("win") or {}).get("harga_win_terbaru"),
		},
		"kisaran": {
			"bawah": low,
			"atas": high,
			"dasar": (
				"bawah = total biaya (margin 0; di bawahnya margin minus dan wajib alasan); "
				"atas = acuan pasar tertinggi. Tanpa biaya, bawah = acuan pasar terendah."
			),
		},
		"catatan": (
			"Angka total per job (bukan per unit). Simulasi margin/markup tambahan WAJIB lewat "
			"calculate. Biaya yang belum final (status Procurement bukan Approve) harus disebut."
		),
	}

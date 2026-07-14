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

import frappe
from frappe import _

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
}

# Doctype yang statusnya boleh diubah, beserta nama field statusnya.
STATUS_FIELD = {
	"CRM Inquiry": "status",
	"CRM Quotation": "state",
}

MAX_ROWS = 50

# Route frontend CRM per doctype — untuk link yang bisa diklik user di chat.
_CRM_ROUTES = {
	"CRM Lead": "leads",
	"CRM Inquiry": "inquiries",
	"CRM Quotation": "quotations",
	"CRM Estimation": "estimations",
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


def list_records(doctype: str, filters=None, fields=None, order_by=None, limit=20):
	"""Baca daftar dokumen CRM.

	Memakai get_all, bukan get_list: user boleh melihat data cabang lain (sesuai
	permintaan -- assistant untuk memahami sistem, lintas cabang). Pembatasannya ada
	pada daftar putih doctype di atas, bukan pada permission per-baris.
	"""
	_check_readable(doctype)
	limit = min(int(limit or 20), MAX_ROWS)
	return frappe.get_all(
		doctype,
		filters=filters or {},
		fields=fields or ["name"],
		order_by=order_by or "modified desc",
		limit_page_length=limit,
	)


def get_record(doctype: str, name: str):
	"""Baca satu dokumen CRM utuh."""
	_check_readable(doctype)
	if not frappe.db.exists(doctype, name):
		return {"_error": f"{doctype} '{name}' tidak ditemukan."}
	doc = frappe.get_doc(doctype, name)
	return doc.as_dict(no_default_fields=False)


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
	items_by_qt = _quotation_items([r["quotation"] for r in rows if r.get("quotation")])
	for r in rows:
		r["url"] = _doc_url("CRM Inquiry", r["name"])
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
		fields=["parent", "product_code", "product_name", "qty", "price", "amount"],
		order_by="parent, idx",
	)
	# product_name di baris sering kosong — resolve nama dari master Item sekali jalan.
	codes = list({r.product_code for r in rows if r.product_code})
	names = dict(
		frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name"], as_list=True)
	) if codes else {}
	out = {}
	for r in rows:
		code = r.get("product_code") or ""
		r["product"] = code
		if not r.get("product_name"):
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
	if not rows:
		return {"note": "Tidak ada inquiry yang cocok dengan rute ini. Coba longgarkan pencarian."}

	win = [r for r in rows if r.quotation and r.state == "Win" and (r.net_total or 0) > 0]
	open_ = [r for r in rows if r.quotation and r.state in ("Draft", "Sent", "Waiting") and (r.net_total or 0) > 0]
	lose = [r for r in rows if r.quotation and r.state == "Lose" and (r.net_total or 0) > 0]
	inq_vals = [
		(r.inquiry_value or 0) * (r.exchange_rate or 1)
		for r in rows
		if not r.quotation and (r.inquiry_value or 0) > 0
	]

	# Rate sesungguhnya ada di baris product quotation (price = harga satuan) —
	# net_total hanyalah totalnya. Ambil item semua quotation yang cocok, lalu
	# hitung statistik PER PRODUCT per keadaan (Win/open/Lose).
	items_by_qt = _quotation_items([r.quotation for r in rows if r.quotation])
	state_of = {r.quotation: r.state for r in rows if r.quotation}
	per_product = {}
	for qt, items in items_by_qt.items():
		st = state_of.get(qt)
		bucket = "win" if st == "Win" else ("lose" if st == "Lose" else "open")
		for it in items:
			if (it.get("price") or 0) <= 0:
				continue
			label = it["product"] + (f" - {it['product_name']}" if it.get("product_name") else "")
			per_product.setdefault(label, {"win": [], "open": [], "lose": []})[bucket].append(it["price"])
	per_product_stats = {
		p: {k: _stats(v) for k, v in b.items() if v} for p, b in per_product.items()
	}

	def refs(bucket, n=5):
		out = []
		for r in bucket[:n]:
			out.append({
				"quotation": r.quotation,
				"quotation_link": f"[{r.quotation}]({_doc_url('CRM Quotation', r.quotation)})",
				"inquiry_link": f"[{r.inquiry}]({_doc_url('CRM Inquiry', r.inquiry)})",
				"rute": f"{(r.origin or '-').strip()} -> {(r.destination or '-').strip()}",
				"job": r.job_service or "-",
				"total": r.net_total,
				"currency": r.currency,
				"tanggal": str(r.date or ""),
				"items": items_by_qt.get(r.quotation, []),
			})
		return out

	return {
		"total_inquiry_cocok": len({r.inquiry for r in rows}),
		"rate_per_product": per_product_stats,
		"win": {"stats_total": _stats([r.net_total for r in win]), "harga_win_terbaru": refs(win, 1), "referensi": refs(win)},
		"open": {"stats_total": _stats([r.net_total for r in open_]), "referensi": refs(open_)},
		"lose": {"stats_total": _stats([r.net_total for r in lose]), "referensi": refs(lose)},
		"inquiry_value_tanpa_quotation": _stats(inq_vals),
		"catatan": (
			"rate_per_product = statistik HARGA SATUAN per item/layanan (ini rate yang "
			"sebenarnya); stats_total = total per quotation. Prioritas dasar rekomendasi: "
			"harga Win terbaru (terbukti laku) > median Win > quotation open terbaru > "
			"inquiry_value. Harga Lose = batas atas yang ditolak pasar."
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

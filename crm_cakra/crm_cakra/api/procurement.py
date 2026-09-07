import frappe
from frappe import _
from frappe.utils import cint, flt, get_fullname, strip_html

from crm_cakra.api.comment import extract_mentions
from crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component import (
	FIXED,
	VARIABLE,
	resolve_for_product,
)
from crm_cakra.fcrm.doctype.crm_notification.crm_notification import notify_user
from crm_cakra.utils import sales_user_only


def _comment_row(d):
	return {
		"name": d.name,
		"quotation": d.quotation,
		"content": d.content,
		"reply_to": d.reply_to,
		"owner": d.owner,
		"owner_name": frappe.get_cached_value("User", d.owner, "full_name") or d.owner,
		"owner_image": frappe.get_cached_value("User", d.owner, "user_image"),
		"creation": d.creation,
	}


@frappe.whitelist()
@sales_user_only
def get_comments(quotation: str):
	"""Thread komentar procurement untuk satu quotation, urut lama -> baru."""
	rows = frappe.get_all(
		"CRM Procurement Comment",
		filters={"quotation": quotation},
		fields=["name", "quotation", "content", "reply_to", "owner", "creation"],
		order_by="creation asc",
		limit_page_length=0,
	)
	return [_comment_row(r) for r in rows]


@frappe.whitelist()
@sales_user_only
def add_comment(quotation: str, content: str, reply_to: str | None = None):
	# Konten HTML dari rich editor; kosong = tanpa teks nyata.
	if not strip_html(content or "").strip():
		frappe.throw(_("Komentar tidak boleh kosong."))
	# reply_to harus komentar di thread quotation yang sama.
	if reply_to and frappe.db.get_value("CRM Procurement Comment", reply_to, "quotation") != quotation:
		reply_to = None
	doc = frappe.get_doc(
		{
			"doctype": "CRM Procurement Comment",
			"quotation": quotation,
			"content": content,
			"reply_to": reply_to,
		}
	).insert()
	_notify(doc)
	return _comment_row(doc)


def _notify(doc):
	"""Notifikasi komentar procurement.

	Dua lapis: user yang di-@mention, lalu semua PESERTA thread (pernah komentar
	di quotation ini) -- bukan seluruh user. Yang sudah kena mention tidak
	dinotifikasi dua kali; penulisnya sendiri juga tidak.
	"""
	owner_name = get_fullname(doc.owner)

	def text(verb):
		return (
			f'<div class="mb-2 leading-5 text-ink-gray-5">'
			f'<span class="font-medium text-ink-gray-9">{owner_name}</span>'
			f"<span> {verb} </span>"
			f'<span class="font-medium text-ink-gray-9">{doc.quotation}</span>'
			f"</div>"
		)

	def send(user, verb):
		notify_user(
			{
				"owner": doc.owner,
				"assigned_to": user,
				"notification_type": "Mention",
				"message": doc.content,
				"notification_text": text(verb),
				"reference_doctype": "CRM Procurement Comment",
				"reference_docname": doc.name,
				"redirect_to_doctype": "CRM Quotation",
				"redirect_to_docname": doc.quotation,
			}
		)

	mentioned = {m.email for m in extract_mentions(doc.content)}
	for user in mentioned:
		send(user, _("mentioned you in procurement discussion"))

	participants = set(
		frappe.get_all(
			"CRM Procurement Comment",
			filters={"quotation": doc.quotation, "name": ["!=", doc.name]},
			pluck="owner",
			distinct=True,
		)
	)
	for user in participants - mentioned - {doc.owner}:
		send(user, _("added a comment in procurement discussion"))


# Status quotation yang masih boleh meminta procurement. Sekali diminta, statusnya
# jadi Waiting dan tombolnya hilang -- itu yang mencegah permintaan dobel, jadi
# gerbangnya ditaruh di server, bukan cuma di tampilan tombol.
REQUESTABLE_STATES = ("Draft", "Sent")


@frappe.whitelist()
@sales_user_only
def request_procurement(quotation: str, assignees: str | list, note: str | None = None):
	"""Minta tim procurement menghargai satu quotation.

	Satu aksi, tiga akibat yang memang harus jalan bersama:
	- quotation di-assign ke orang yang dituju (muncul di daftar tugas mereka),
	- catatannya masuk sebagai komentar di tab Procurement, supaya jejak permintaan
	  ada di tempat diskusinya berlangsung dan bukan hilang di notifikasi,
	- statusnya jadi Waiting, yang sekaligus menyembunyikan tombolnya.
	"""
	if not frappe.has_permission("CRM Quotation", "write", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	assignees = frappe.parse_json(assignees) if isinstance(assignees, str) else assignees
	assignees = [u for u in dict.fromkeys(assignees or []) if u]
	if not assignees:
		frappe.throw(_("Pilih minimal satu orang untuk dikirimi permintaan."))

	state = frappe.db.get_value("CRM Quotation", quotation, "state")
	if state not in REQUESTABLE_STATES:
		frappe.throw(_("Quotation {0} berstatus {1}, permintaan procurement sudah tidak berlaku.").format(quotation, _(state)))

	# Catatan diketik di textarea polos, sedangkan komentar disimpan sebagai HTML.
	# Di-escape supaya tanda < atau & pada catatan tidak merusak tampilannya, lalu
	# baris barunya dipertahankan.
	body = frappe.utils.escape_html((note or "").strip()).replace(chr(10), "<br>")
	content = f"<p><b>{_('Request Procurement')}</b></p>"
	if body:
		content += f"<p>{body}</p>"

	comment = frappe.get_doc(
		{"doctype": "CRM Procurement Comment", "quotation": quotation, "content": content}
	).insert()

	from frappe.desk.form.assign_to import add as assign_to_add

	assign_to_add(
		{
			"assign_to": assignees,
			"doctype": "CRM Quotation",
			"name": quotation,
			"description": strip_html(content).strip() or _("Request Procurement"),
		},
		ignore_permissions=True,
	)

	owner_name = get_fullname(frappe.session.user)
	text = (
		f'<div class="mb-2 leading-5 text-ink-gray-5">'
		f'<span class="font-medium text-ink-gray-9">{owner_name}</span>'
		f"<span> {_('requested procurement on')} </span>"
		f'<span class="font-medium text-ink-gray-9">{quotation}</span>'
		f"</div>"
	)
	for user in assignees:
		if user == frappe.session.user:
			continue
		notify_user(
			{
				"owner": frappe.session.user,
				"assigned_to": user,
				"notification_type": "Mention",
				"message": content,
				"notification_text": text,
				"reference_doctype": "CRM Procurement Comment",
				"reference_docname": comment.name,
				"redirect_to_doctype": "CRM Quotation",
				"redirect_to_docname": quotation,
			}
		)

	frappe.db.set_value("CRM Quotation", quotation, "state", "Waiting")
	return {"state": "Waiting", "comment": _comment_row(comment)}


@frappe.whitelist()
@sales_user_only
def delete_comment(name: str):
	# Permission doctype yang menentukan (owner boleh hapus miliknya, manager semua).
	# force=1: lewati link check -- notifikasi dan reply_to komentar lain menaut ke
	# sini dan tanpa ini penghapusan selalu gagal LinkExistsError. Reply yang
	# kehilangan induk ditampilkan frontend sebagai "Komentar dihapus" (ala WA).
	frappe.delete_doc("CRM Procurement Comment", name, force=1)
	frappe.db.delete(
		"CRM Notification",
		{"notification_type_doctype": "CRM Procurement Comment", "notification_type_doc": name},
	)


# Status yang boleh diset dari tab Procurement. Finish -> Approved (costing
# selesai), Edit -> Waiting (dibuka lagi untuk direvisi). Selain dua ini bukan
# urusan tab ini, jadi tidak diterima.
COSTING_STATES = ("Approved", "Waiting")


@frappe.whitelist()
@sales_user_only
def set_costing_state(quotation: str, state: str):
	"""Pindahkan status quotation dari tab Procurement.

	Harganya sendiri tidak disentuh -- Base Price cuma lantai, angka jual tetap
	ketikan orang. Gerbangnya di server supaya dokumen yang sudah final tidak bisa
	diputar balik lewat tab yang kebetulan masih terbuka.
	"""
	if not frappe.has_permission("CRM Quotation", "write", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if state not in COSTING_STATES:
		frappe.throw(_("Status {0} tidak bisa diset dari tab Procurement.").format(state))

	current, is_void = frappe.db.get_value("CRM Quotation", quotation, ["state", "is_void"])
	if current == "Converted":
		frappe.throw(_("Quotation {0} sudah dikonversi dan tidak bisa diubah.").format(quotation))
	if is_void:
		frappe.throw(_("Quotation {0} sudah di-void.").format(quotation))
	# Finish hanya menutup costing yang memang sedang diminta. Tombolnya sudah
	# disembunyikan di status lain, tapi tab yang terlanjur terbuka masih bisa
	# mengirimnya -- itu yang ditolak di sini.
	if state == "Approved" and current != "Waiting":
		frappe.throw(
			_("Quotation {0} berstatus {1}, bukan Waiting -- costing tidak bisa di-Finish.").format(
				quotation, _(current)
			)
		)

	frappe.db.set_value("CRM Quotation", quotation, "state", state)
	return {"state": state}


COSTING_ROLE = "Procurement Costing"


def has_costing_access() -> bool:
	"""Rincian Fixed/Variable cost cuma untuk pemegang role Procurement Costing.

	System Manager ikut dilewatkan supaya admin tidak bisa mengunci dirinya sendiri
	dari data yang justru dia yang atur.
	"""
	return bool(set(frappe.get_roles()) & {COSTING_ROLE, "System Manager"})


@frappe.whitelist()
@sales_user_only
def get_cost_defaults(quotation: str, codes: str | list | None = None):
	"""Komponen biaya default tiap produk yang dipakai quotation ini.

	Fixed dipakai panel costing untuk ditampilkan read-only (angkanya milik master
	CRM Product). Variable dipakai panel untuk memuat komponen produk ke baris
	costing, otomatis saat produk dipilih maupun lewat tombol "Load Defaults".

	codes dikirim frontend berisi produk yang sedang ada di layar -- produk yang
	baru dipilih dan belum disimpan tidak akan ketemu kalau daftarnya dibaca dari
	tabel. Tanpa codes, jatuh ke isi tabel quotation-nya.
	"""
	# Tanpa role, panel costing hanya menampilkan ringkasan yang sudah tersimpan.
	# Dikembalikan kosong, bukan throw: panelnya tetap hidup, cuma rinciannya tidak
	# pernah sampai ke browser.
	if not has_costing_access():
		return {}

	codes = frappe.parse_json(codes) if isinstance(codes, str) else codes
	codes = {c for c in (codes or []) if c}
	if not codes:
		codes = {
			c
			for c in frappe.get_all(
				"CRM Products",
				filters={"parent": quotation, "parenttype": "CRM Quotation"},
				pluck="product_code",
			)
			if c
		}
	def lines(code, cost_type):
		return [
			{
				"source_component": comp.name,
				"item_name": i.item_name,
				"qty": i.qty,
				"uom": i.uom,
				"rate": i.rate,
				"amount": i.amount,
			}
			for comp in resolve_for_product(code, cost_type)
			for i in comp.items
		]

	out = {}
	for code in codes:
		master = (
			frappe.db.get_value(
				"CRM Product", code, ["product_name", "fixed_cost_per_day"], as_dict=True
			)
			or {}
		)
		out[code] = {
			# Dipakai judul kartu costing: "C-00001 - Nama Item".
			"product_name": master.get("product_name") or code,
			"per_day": master.get("fixed_cost_per_day") or 0,
			"fixed": lines(code, FIXED),
			"variable": lines(code, VARIABLE),
		}
	return out


@frappe.whitelist()
@sales_user_only
def preview_base_prices(rows: str | list):
	"""Base Price tiap baris untuk quotation yang belum tersimpan.

	Halaman New tidak punya panel costing, jadi kolom Base Price-nya diam di 0
	sampai simpan pertama -- padahal angka itulah lantai harganya. Di sini
	dihitung lebih awal, dengan rumus yang sama persis dengan calculate_costing().

	Yang dikembalikan hanya totalnya, bukan rincian komponennya: lantai harga
	perlu dilihat siapa pun yang membuat quotation, sedangkan pecahan fixed dan
	variable tetap milik pemegang role Procurement Costing.

	Ini pratinjau. Yang mengikat tetap hitungan server saat dokumennya disimpan.
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	out = []
	for row in rows or []:
		code = (row or {}).get("product_code")
		if not code or not frappe.db.exists("CRM Product", code):
			out.append(0.0)
			continue

		per_day = flt(frappe.db.get_value("CRM Product", code, "fixed_cost_per_day"))
		# Produk tanpa komponen variable tetap punya Base Price dari fixed cost-nya.
		variable_per_day = sum(
			flt(i.qty) * flt(i.rate)
			for comp in resolve_for_product(code, VARIABLE)
			for i in comp.items
		)

		dur = cint(row.get("duration")) or 1
		base_per_day = per_day + variable_per_day
		margin = base_per_day * flt(row.get("margin_percent")) / 100
		out.append((base_per_day + margin) * dur)
	return out


@frappe.whitelist()
@sales_user_only
def get_discussions():
	"""Semua quotation untuk menu Procurement -- bukan hanya yang sudah ada diskusinya.

	Quotation baru harus langsung kelihatan di sini supaya Procurement tahu ada
	yang perlu dihargai. Kolom `priced` vs `items` yang menandai sudah/belum
	diproses; komentar cuma pelengkap.
	"""
	rows = frappe.db.sql(
		"""
		SELECT q.name,
		       q.subject,
		       q.account_name,
		       q.state,
		       COUNT(DISTINCT c.name) AS comments,
		       COUNT(DISTINCT p.name) AS items,
		       COUNT(DISTINCT CASE WHEN p.procurement_price > 0 THEN p.name END) AS priced,
		       COALESCE(MAX(c.creation), q.creation) AS last_at
		FROM `tabCRM Quotation` q
		LEFT JOIN `tabCRM Procurement Comment` c ON c.quotation = q.name
		LEFT JOIN `tabCRM Products` p
		       ON p.parent = q.name AND p.parenttype = 'CRM Quotation'
		GROUP BY q.name, q.subject, q.account_name, q.state, q.creation
		ORDER BY last_at DESC
		LIMIT 100
		""",
		as_dict=True,
	)
	# Komentar terakhir per quotation, untuk cuplikan di daftar.
	for r in rows:
		if not r.comments:
			continue
		last = frappe.get_all(
			"CRM Procurement Comment",
			filters={"quotation": r.name},
			fields=["content", "owner", "creation"],
			order_by="creation desc",
			limit_page_length=1,
		)
		if last:
			r["last_comment"] = last[0].content
			r["last_owner"] = frappe.get_cached_value("User", last[0].owner, "full_name") or last[0].owner
			r["last_owner_email"] = last[0].owner
	return rows

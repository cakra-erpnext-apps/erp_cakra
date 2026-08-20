import frappe
from frappe import _
from frappe.utils import get_fullname, strip_html

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
def get_discussions():
	"""Daftar quotation yang punya diskusi procurement, terbaru dulu (untuk menu Procurement)."""
	rows = frappe.db.sql(
		"""
		SELECT c.quotation AS name,
		       q.subject,
		       q.account_name,
		       q.state,
		       COUNT(*) AS comments,
		       MAX(c.creation) AS last_at
		FROM `tabCRM Procurement Comment` c
		LEFT JOIN `tabCRM Quotation` q ON q.name = c.quotation
		GROUP BY c.quotation, q.subject, q.account_name, q.state
		ORDER BY last_at DESC
		LIMIT 100
		""",
		as_dict=True,
	)
	# Komentar terakhir per quotation, untuk cuplikan di daftar.
	for r in rows:
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

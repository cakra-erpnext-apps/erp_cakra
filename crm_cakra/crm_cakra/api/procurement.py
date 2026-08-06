import frappe
from frappe import _
from frappe.utils import get_fullname, strip_html

from crm_cakra.api.comment import extract_mentions
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

from collections.abc import Iterable

import frappe
from bs4 import BeautifulSoup
from frappe import _
from frappe.desk.form.utils import add_comment as frappe_add_comment
from frappe.utils import get_fullname

from crm_cakra.api.activities import get_attachments
from crm_cakra.fcrm.doctype.crm_notification.crm_notification import notify_user


def on_update(self, method):
	notify_mentions(self)


def notify_mentions(doc):
	"""
	Extract mentions from `content`, and notify.
	`content` must have `HTML` content.
	"""
	content = getattr(doc, "content", None)
	if not content:
		return
	mentions = extract_mentions(content)
	reference_doc = frappe.get_doc(doc.reference_doctype, doc.reference_name)
	for mention in mentions:
		owner = frappe.get_cached_value("User", doc.owner, "full_name")
		doctype = doc.reference_doctype
		if doctype.startswith("CRM "):
			doctype = doctype[4:].lower()
		# .get(): doctype lain (mis. Procurement) tidak punya field ini sama sekali
		name = reference_doc.get("lead_name") or reference_doc.get("organization") or reference_doc.name
		notification_text = f"""
            <div class="mb-2 leading-5 text-ink-gray-5">
                <span class="font-medium text-ink-gray-9">{ owner }</span>
                <span>{ _('mentioned you in {0}').format(doctype) }</span>
                <span class="font-medium text-ink-gray-9">{ name }</span>
            </div>
        """
		notify_user(
			{
				"owner": doc.owner,
				"assigned_to": mention.email,
				"notification_type": "Mention",
				"message": doc.content,
				"notification_text": notification_text,
				"reference_doctype": "Comment",
				"reference_docname": doc.name,
				"redirect_to_doctype": doc.reference_doctype,
				"redirect_to_docname": doc.reference_name,
			}
		)


def extract_mentions(html):
	if not html:
		return []
	soup = BeautifulSoup(html, "html.parser")
	mentions = []
	for d in soup.find_all("span", attrs={"data-type": "mention"}):
		mentions.append(frappe._dict(full_name=d.get("data-label"), email=d.get("data-id")))
	return mentions


@frappe.whitelist()
def get_comments(reference_doctype: str, reference_name: str):
	"""Komentar satu dokumen: daftar datar, urut waktu.

	Balasan tidak disarangkan — yang ditumpangkan cuma kutipan induknya (ala
	WhatsApp), jadi urutan percakapan tetap terbaca di panel sempit.
	"""
	if not frappe.has_permission(reference_doctype, "read", reference_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"comment_type": "Comment",
		},
		fields=[
			"name",
			"content",
			"owner",
			"comment_by",
			"creation",
			"modified",
			"parent_comment",
		],
		order_by="creation asc",
	)

	by_name = {row.name: row for row in rows}
	for row in rows:
		row.attachments = get_attachments("Comment", row.name)
		row.edited = row.modified and row.creation and (row.modified - row.creation).total_seconds() > 1

		parent = by_name.get(row.parent_comment)
		row.quote = (
			{"name": parent.name, "owner": parent.owner, "text": strip_html(parent.content)} if parent else None
		)

	return rows


def strip_html(html: str, limit: int = 140) -> str:
	"""Teks polos untuk kutipan balasan."""
	text = " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())
	return text[: limit - 1] + "…" if len(text) > limit else text


@frappe.whitelist()
def edit_comment(name: str, content: str):
	"""Ubah isi komentar sendiri."""
	doc = frappe.get_doc("Comment", name)
	if frappe.session.user not in ("Administrator", doc.owner):
		frappe.throw(_("Comment can only be edited by the owner"), frappe.PermissionError)

	doc.content = content
	doc.save(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def delete_comment(name: str):
	"""Hapus komentar sendiri. Balasannya tetap ada, kutipannya saja yang dilepas."""
	doc = frappe.get_doc("Comment", name)
	if frappe.session.user != doc.owner and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Comment can only be deleted by the owner"), frappe.PermissionError)

	for reply in frappe.get_all("Comment", filters={"parent_comment": name}, pluck="name"):
		frappe.db.set_value("Comment", reply, "parent_comment", "", update_modified=False)

	# notifikasi mention/balasan menunjuk komentar ini; tanpa dibersihkan dulu
	# Frappe menolak hapus (LinkExistsError)
	for notification in frappe.get_all(
		"CRM Notification",
		or_filters={"comment": name, "notification_type_doc": name},
		pluck="name",
	):
		frappe.delete_doc("CRM Notification", notification, ignore_permissions=True, delete_permanently=True)

	frappe.delete_doc("Comment", name, ignore_permissions=True, delete_permanently=True)


@frappe.whitelist()
def add_comment(
	reference_doctype: str,
	reference_name: str,
	content: str,
	attachments: list | None = None,
	parent_comment: str | None = None,
):
	"""Add a comment to the given document

	:param reference_doctype: Reference Doctype
	:param reference_name: Reference Document Name
	:param content: Comment Content (HTML)
	:param attachments: List of File names or dicts with keys "fname" and "fcontent"
	:return: Comment Document
	"""
	comment = frappe_add_comment(
		reference_doctype,
		reference_name,
		content,
		comment_email=frappe.session.user,
		comment_by=get_fullname(frappe.session.user),
	)

	if parent_comment and comment.name:
		frappe.db.set_value("Comment", comment.name, "parent_comment", parent_comment, update_modified=False)
		notify_reply(comment, parent_comment)

	notify_participants(comment, parent_comment)

	if attachments and comment.name:
		add_attachments(comment.name, attachments)

	return comment


# Dokumen yang obrolannya dipakai bolak-balik antar tim, jadi pesan baru harus
# sampai ke semua yang terlibat -- bukan cuma yang kebetulan disebut @.
CHAT_DOCTYPES = ("CRM Procurement", "CRM Inquiry")


def notify_participants(comment, parent_comment: str | None = None) -> None:
	"""Colek semua yang terlibat di percakapan dokumen ini.

	Terlibat = pernah ikut berkomentar, pemilik dokumennya, pemilik inquiry-nya,
	dan siapa pun yang di-assign. Tanpa ini pesan di dokumen yang jarang dibuka
	cuma terbaca kalau orangnya kebetulan mampir -- padahal ini dipakai sebagai
	ruang obrolan antara Marketing dan Procurement.

	Yang sudah kena notifikasi lain (disebut @, atau komentarnya dibalas) sengaja
	dilewati supaya satu pesan tidak berbunyi dua kali.
	"""
	if comment.reference_doctype not in CHAT_DOCTYPES:
		return

	sudah = {m.email for m in extract_mentions(comment.content)}
	sudah.add(comment.owner)
	if parent_comment:
		sudah.add(frappe.db.get_value("Comment", parent_comment, "owner"))

	penerima = set(
		frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": comment.reference_doctype,
				"reference_name": comment.reference_name,
				"comment_type": "Comment",
			},
			pluck="owner",
		)
	)

	doc = frappe.get_doc(comment.reference_doctype, comment.reference_name)
	penerima.add(doc.owner)
	penerima.update(frappe.parse_json(doc.get("_assign") or "[]"))

	inquiry = doc.name if doc.doctype == "CRM Inquiry" else doc.get("inquiry")
	if inquiry:
		inq = frappe.db.get_value("CRM Inquiry", inquiry, ["owner", "inquiry_owner"], as_dict=True) or {}
		penerima.update(u for u in (inq.get("owner"), inq.get("inquiry_owner")) if u)

	judul = inquiry or comment.reference_name
	tempat = _("procurement") if comment.reference_doctype == "CRM Procurement" else _("inquiry")
	owner_name = frappe.get_cached_value("User", comment.owner, "full_name")
	notification_text = (
		'<div class="mb-2 leading-5 text-ink-gray-5">'
		f'<span class="font-medium text-ink-gray-9">{owner_name}</span>'
		f"<span> {_('mengirim pesan di')} {tempat} </span>"
		f'<span class="font-medium text-ink-gray-9">{judul}</span>'
		"</div>"
	)

	for user in penerima - sudah:
		# user nonaktif/terhapus tidak perlu dikirimi apa-apa
		if not user or not frappe.db.get_value("User", user, "enabled"):
			continue
		notify_user(
			{
				"owner": comment.owner,
				"assigned_to": user,
				"notification_type": "Mention",
				"message": comment.content,
				"notification_text": notification_text,
				"reference_doctype": "Comment",
				"reference_docname": comment.name,
				"redirect_to_doctype": comment.reference_doctype,
				"redirect_to_docname": comment.reference_name,
			}
		)


def notify_reply(comment, parent_comment: str) -> None:
	"""Yang dibalas ikut dicolek, persis seperti disebut @ -- tanpa itu balasan
	di dokumen yang jarang dibuka tidak akan pernah terbaca orangnya."""
	parent_owner = frappe.db.get_value("Comment", parent_comment, "owner")
	# user bisa saja sudah dihapus/dinonaktifkan -- notifikasi gagal jangan sampai
	# menggagalkan komentarnya
	if not parent_owner or not frappe.db.get_value("User", parent_owner, "enabled"):
		return

	# sudah disebut @ di isi balasannya: cukup satu notifikasi
	if parent_owner in [m.email for m in extract_mentions(comment.content)]:
		return

	owner_name = frappe.get_cached_value("User", comment.owner, "full_name")
	notification_text = f"""
		<div class="mb-2 leading-5 text-ink-gray-5">
			<span class="font-medium text-ink-gray-9">{ owner_name }</span>
			<span>{ _('membalas komentar Anda') }</span>
		</div>
	"""
	notify_user(
		{
			"owner": comment.owner,
			"assigned_to": parent_owner,
			"notification_type": "Mention",
			"message": comment.content,
			"notification_text": notification_text,
			"reference_doctype": "Comment",
			"reference_docname": comment.name,
			"redirect_to_doctype": comment.reference_doctype,
			"redirect_to_docname": comment.reference_name,
		}
	)


def add_attachments(name: str, attachments: Iterable[str | dict]) -> None:
	"""Add attachments to the given Comment

	:param name: Comment name
	:param attachments: File names or dicts with keys "fname" and "fcontent"
	"""
	# loop through attachments
	for a in attachments:
		if isinstance(a, str):
			attach = frappe.db.get_value("File", {"name": a}, ["file_url", "is_private"], as_dict=1)
			file_args = {
				"file_url": attach.file_url,
				"is_private": attach.is_private,
			}
		elif isinstance(a, dict) and "fcontent" in a and "fname" in a:
			# dict returned by frappe.attach_print()
			file_args = {
				"file_name": a["fname"],
				"content": a["fcontent"],
				"is_private": 1,
			}
		else:
			continue

		file_args.update(
			{
				"attached_to_doctype": "Comment",
				"attached_to_name": name,
				"folder": "Home/Attachments",
			}
		)

		_file = frappe.new_doc("File")
		_file.update(file_args)
		_file.save(ignore_permissions=True)

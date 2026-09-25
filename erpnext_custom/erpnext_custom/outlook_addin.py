"""Add-in ERPNext untuk Outlook: tautkan email yang sedang dibaca di Outlook ke transaksi.

Panel add-in (public/outlook/taskpane.html) berjalan DI DALAM Outlook, bukan di desk. Email
tetap tinggal di Microsoft; ERPNext hanya menyimpan email yang ditautkan -- pada saat
ditautkan, isi lengkapnya (.eml dari Outlook) dijadikan Communication lalu dikaitkan ke
transaksi yang dipilih, sehingga muncul di timeline dokumen-dokumen itu.

Autentikasi: token API ERPNext (`Authorization: token key:secret`), BUKAN cookie sesi.
Panel dibuka Outlook di dalam iframe domain lain, dan browser tidak mengirim cookie ERPNext
di konteks pihak ketiga seperti itu. ponytail: kunci API per user ditempel sekali di panel;
untuk 50+ user ganti dengan single sign-on Microsoft (token Entra dicocokkan ke User).

Satu email = satu Communication, dicari lewat Message-ID ke SELURUH sistem: dua user yang
menerima email yang sama dan sama-sama menautkannya menambah tautan ke catatan yang sama,
bukan membuat salinan kedua. Email yang sudah ditarik lewat IMAP (Mailbox) juga dikenali.

Halaman Mailbox mode laptop (public/js/mailbox_local.js) memakai lookup/save_links yang sama:
emailnya diambil browser langsung dari Microsoft 365 dan disimpan di laptop user, server hanya
menerima yang ditautkan.
"""

import base64
import os
from urllib.parse import urlencode
from email import message_from_bytes, policy
from email.utils import parseaddr

import frappe
from frappe import _
from frappe.utils import cint, cstr, escape_html
from frappe.utils.password import encrypt, get_decrypted_password

from erpnext_custom.mail_inbox import CMIInboundMail, get_links, link_transaction, unlink_transaction


# Interval sinkron otomatis Mailbox Local Mode paling rapat. Batas Microsoft jauh di atasnya
# (10.000 panggilan per 10 menit per mailbox; satu putaran tanpa email baru = 1 panggilan per
# folder); ini cuma supaya laptop tidak sibuk tanpa guna.
SYNC_SECONDS_MIN = 15


@frappe.whitelist()
def mailbox_config() -> dict:
	"""Setelan Mailbox Local Mode untuk browser. client_id kosong = Local Mode mati
	(centang Local Mode di ERPNext Custom Setting > Mailbox).

	Tidak ada rahasia di sini: aplikasi Entra tipe SPA memang tanpa client secret, dan
	Microsoft hanya mengembalikan token ke redirect URI yang terdaftar di domain ERP.
	"""
	settings = frappe.get_cached_doc("ERPNext Custom Setting")
	keep_days = settings.get("mailbox_keep_days")
	return {
		"client_id": (settings.get("mailbox_client_id") or "").strip() if settings.get("mailbox_local_mode") else "",
		"tenant_id": (settings.get("mailbox_tenant_id") or "").strip(),
		"email": (frappe.db.get_value("User", frappe.session.user, "email") or "").lower(),
		# Satu setelan untuk semua user. Belum pernah diisi = 30; 0 = simpan semua.
		"keep_days": 30 if keep_days is None else max(cint(keep_days), 0),
		# Sinkron otomatis selama ERP terbuka di browser user. Kosong = 60 detik.
		"sync_seconds": max(cint(settings.get("mailbox_sync_seconds")) or 60, SYNC_SECONDS_MIN),
	}


# Kunci enkripsi salinan email Local Mode di laptop: satu kunci AES-256 acak per user, disimpan
# di tabel __Auth (dienkripsi encryption_key situs, seperti field Password). Bukan kolom User:
# tidak ikut tampil/terekspor bersama dokumen User. Backup database + site_config.json = backup
# kunci; hilang keduanya = salinan di laptop tak terbaca (email aslinya tetap di Microsoft).
MAILBOX_KEY_FIELD = "cmi_mailbox_key"


@frappe.whitelist(methods=["POST"])
def mailbox_key() -> str:
	"""Kunci milik user yang sedang login (base64). Browser memegangnya di memori saja, jadi
	berkas email di laptop hanya terbaca selama user bisa login ERP -- akun dinonaktifkan =
	salinannya ikut terkunci."""
	return _mailbox_key(frappe.session.user, create=True)


@frappe.whitelist(methods=["POST"])
def export_mailbox_key(user: str) -> str:
	"""Kunci Mailbox user lain untuk membuka salinannya tanpa ERP (alat mailbox_decrypt.html).
	Hanya System Manager, dan setiap ekspor tercatat di timeline User itu."""
	frappe.only_for("System Manager")
	key = _export_key(user)
	if not key:
		frappe.throw(_("{0} has no Mailbox key yet (Local Mode never used).").format(user))
	return key


@frappe.whitelist(methods=["POST"])
def export_mailbox_keys(users=None) -> dict:
	"""Banyak kunci sekaligus (daftar User > Menu > Export Mailbox Keys): user yang dicentang,
	atau semua user yang punya kunci. Tiap user tetap tercatat di timeline-nya sendiri."""
	frappe.only_for("System Manager")
	users = frappe.parse_json(users) if users else frappe.db.sql_list(
		"select name from `__Auth` where doctype = 'User' and fieldname = %s order by name", MAILBOX_KEY_FIELD
	)
	keys, missing = [], []
	for user in users:
		key = _export_key(user)
		if key:
			keys.append({"user": user, "email": frappe.db.get_value("User", user, "email"), "key": key})
		else:
			missing.append(user)
	return {"keys": keys, "missing": missing}


def _export_key(user: str) -> str | None:
	key = _mailbox_key(user, create=False)
	if key:
		frappe.get_doc("User", user).add_comment(
			"Info", _("Mailbox key exported by {0}").format(frappe.session.user)
		)
	return key


def _mailbox_key(user: str, create: bool) -> str | None:
	key = get_decrypted_password("User", user, MAILBOX_KEY_FIELD, raise_exception=False)
	if key or not create:
		return key
	# INSERT IGNORE, bukan set_encrypted_password (yang menimpa): dua tab yang meminta kunci
	# pertama kali bersamaan tetap berakhir dengan SATU kunci; yang kalah membaca milik pemenang.
	frappe.db.sql(
		"insert ignore into `__Auth` (doctype, name, fieldname, `password`, encrypted) values (%s, %s, %s, %s, 1)",
		("User", user, MAILBOX_KEY_FIELD, encrypt(base64.b64encode(os.urandom(32)).decode())),
	)
	frappe.db.commit()
	return get_decrypted_password("User", user, MAILBOX_KEY_FIELD)


@frappe.whitelist(methods=["POST"])
def notify_local_mail(mails) -> int:
	"""Local Mode: email masuk ditarik browser, bukan server, jadi notify_new_mail tidak pernah
	jalan. Browser melaporkan email baru di Kotak Masuk; di sini dibuat Notification Log untuk
	user yang login SAJA (tidak bisa mengirim notifikasi ke orang lain), maksimal 20 per panggilan.
	Link-nya membuka email itu lewat Message-ID (LocalMailbox.on_show -> open_route)."""
	mails = frappe.parse_json(mails) or []
	for mail in mails[:20]:
		mid = _normalize(mail.get("message_id"))
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": frappe.session.user,
				"type": "Alert",
				# Subjek & pengirim dari email luar: di-escape, dropdown lonceng merender HTML.
				"subject": _("New email from {0}: {1}").format(
					escape_html(cstr(mail.get("sender"))[:140]),
					escape_html(cstr(mail.get("subject"))[:200]) or _("(no subject)"),
				),
				"document_type": "Communication",
				"link": "/desk/mailbox?" + urlencode({"message_id": mid}) if mid else "/desk/mailbox",
			}
		).insert(ignore_permissions=True)
	return min(len(mails), 20)


@frappe.whitelist()
def lookup(mailbox: str, message_id: str) -> dict:
	"""Email ini sudah tersimpan di ERP? Kalau ya, tertaut ke transaksi apa saja."""
	_check_mailbox(mailbox)
	name = _find(message_id)
	return {"communication": name, "links": get_links(name) if name else []}


@frappe.whitelist()
def save_links(mailbox: str, message_id: str, links, eml_b64: str | None = None) -> dict:
	"""Jadikan tautan email ini PERSIS `links`: yang baru ditautkan, yang hilang dilepas.

	`eml_b64` (isi lengkap email dari Outlook) hanya dibutuhkan kalau email belum ada di ERP.
	"""
	_check_mailbox(mailbox)
	links = frappe.parse_json(links) or []

	name = _find(message_id)
	if not name:
		if not links:
			return {"communication": None, "links": []}
		if not eml_b64:
			frappe.throw(_("The email content is required to save it to ERPNext."))
		name = _import(mailbox, eml_b64)

	key = lambda l: (l["doctype"], l["name"])  # noqa: E731
	current = {key(l) for l in get_links(name)}
	wanted = {key(l) for l in links}

	for doctype, docname in wanted - current:
		link_transaction(name, doctype, docname)
	for doctype, docname in current - wanted:
		unlink_transaction(name, doctype, docname)

	return {"communication": name, "links": get_links(name)}


def _check_mailbox(mailbox: str):
	"""Hanya boleh atas nama mailbox milik user ERP yang sedang login (atau System Manager).

	Isi email datang dari klien, jadi yang dijaga di sini: user tidak bisa mengaku-aku
	mailbox orang lain untuk menentukan akun dan arah (masuk/terkirim) email yang disimpan.
	"""
	if not mailbox:
		frappe.throw(_("Mailbox address is empty."))

	own = (frappe.db.get_value("User", frappe.session.user, "email") or "").lower()
	if mailbox.lower() != own and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Mailbox {0} does not belong to user {1}.").format(mailbox, frappe.session.user),
			frappe.PermissionError,
		)


def _normalize(message_id: str) -> str:
	# Outlook memberi "<abc@host>", Frappe menyimpan tanpa kurung sudut.
	return (message_id or "").strip().strip("<>").strip()


def _find(message_id: str) -> str | None:
	mid = _normalize(message_id)
	if not mid:
		return None
	return frappe.db.get_value(
		"Communication",
		{"message_id": mid, "communication_medium": "Email"},
		"name",
		order_by="creation asc",
	)


def _account_for(mailbox: str):
	name = frappe.db.get_value("Email Account", {"email_id": mailbox}, "name")
	if name:
		return frappe.get_doc("Email Account", name)

	# Mailbox tanpa Email Account (mode laptop: tiap user, tidak ditarik server). InboundMail
	# cuma membaca atribut di bawah ini dari akunnya; Communication-nya tercatat tanpa
	# email_account. Balasan dikirim browser lewat Microsoft, bukan lewat akun ERP.
	return frappe._dict(
		name=None,
		email_id=mailbox,
		use_imap=0,
		append_to=None,
		attachment_limit=0,
		flags=frappe._dict(),
	)


def _import(mailbox: str, eml_b64: str) -> str:
	"""Simpan email dari Outlook jadi Communication lewat jalur yang sama dengan tarikan IMAP.

	CMIInboundMail mengurus semuanya seperti email yang ditarik: pengkodean, lampiran,
	gambar inline (cid:) jadi URL berkas, dan penanda utas. Email yang DIKIRIM mailbox ini
	dicatat sebagai Terkirim -- bawaan Frappe menolaknya (SentEmailInInboxError).
	"""
	raw = base64.b64decode(eml_b64)
	sender = parseaddr(message_from_bytes(raw, policy=policy.default).get("From", ""))[1]
	account = _account_for(mailbox)

	# Ditautkan manual, bukan email yang baru datang: jangan picu balasan otomatis assistant
	# (on_communication_insert membaca flag yang sama dengan tarik ulang).
	frappe.flags.cmi_mail_backfill = True
	try:
		mail = CMIInboundMail(
			raw,
			account,
			None,
			"SEEN",
			"Communication",
			imap_folder=None,
			is_sent=sender.lower() == mailbox.lower(),
		)
		communication = mail.process()
	finally:
		frappe.flags.cmi_mail_backfill = False

	frappe.db.commit()
	return communication.name

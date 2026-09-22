"""Kirim email keluar lewat Microsoft Graph, bukan SMTP.

Kenapa ada: tenant Microsoft bisa mematikan SMTP AUTH untuk seluruh organisasi
(`535 5.7.139 SmtpClientAuthentication is disabled for the Tenant`), dan larangan itu
kena OAuth juga, bukan cuma basic auth. IMAP tetap jalan -- jadi terima email normal --
tapi kirim harus lewat jalan lain. Graph sendMail tidak menyentuh SMTP sama sekali,
jadi kebijakan itu tidak lagi relevan.

Dua kait di hooks.py:
    override_email_send                  -> send()
    override_doctype_class Email Account -> CMIEmailAccount

Sebuah Email Account memakai Graph kalau field `cmi_graph_connected_app` terisi, dan
isinya boleh Connected App yang SAMA dengan yang dipakai IMAP.

Satu access token Azure memang cuma berlaku untuk satu resource, jadi token IMAP
(`outlook.office.com`) tidak bisa dipakai memanggil Graph. Tapi REFRESH token tidak
terikat resource: token itu bisa ditukar jadi access token Graph lewat client_id +
client_secret yang sama, tanpa alur browser. Jadi tidak perlu Connected App kedua,
Connect kedua, maupun redirect URI kedua -- satu-satunya syarat tambahan di Azure
adalah izin `Mail.Send` yang sudah di-Grant admin consent.
"""

import base64
from email import message_from_bytes, policy
from email.utils import getaddresses
from urllib.parse import quote

import requests

import frappe
from frappe import _
from frappe.utils import cint
from frappe.email.doctype.email_account.email_account import EmailAccount

GRAPH_SENDMAIL = "https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail"
GRAPH_SCOPE = "offline_access https://graph.microsoft.com/Mail.Send"

# ponytail: sendMail berbentuk MIME dibatasi ~4 MB oleh Graph. Lampiran lebih besar
# butuh createUploadSession (unggah bertahap ke folder Drafts lalu kirim) -- baru
# dikerjakan kalau memang ada email sebesar itu.
MAX_MIME_SIZE = 4 * 1024 * 1024

GRAPH_FIELDS = {
	"Email Account": [
		{
			"fieldname": "cmi_graph_connected_app",
			"label": "Kirim lewat Microsoft Graph",
			"fieldtype": "Link",
			"options": "Connected App",
			"insert_after": "connected_user",
			"depends_on": "eval:doc.enable_outgoing",
			"description": (
				"Kalau diisi, email keluar dikirim lewat Microsoft Graph dan setelan SMTP di "
				"atas tidak dipakai. Boleh Connected App yang sama dengan IMAP: token Graph "
				"diambil dengan menukar refresh token-nya, jadi tidak ada Connect kedua. "
				"Syaratnya app itu punya izin Mail.Send yang sudah di-Grant admin consent."
			),
		}
	]
}


class CMIEmailAccount(EmailAccount):
	def validate_smtp_conn(self):
		# Akun Graph tidak punya sesi SMTP untuk diuji, dan tenant-nya justru memblokir
		# SMTP -- tes bawaan pasti gagal dan akunnya jadi tidak bisa disimpan sama sekali.
		if self.get("cmi_graph_connected_app"):
			return None

		return super().validate_smtp_conn()


def send(email_queue, sender, recipient, message):
	"""Hook `override_email_send`: dipanggil Frappe sekali per penerima."""
	account = email_queue.get_email_account(raise_error=True)

	if not account.get("cmi_graph_connected_app"):
		_send_over_smtp(account, sender, recipient, message)
		return

	# Graph mengantar berdasarkan header To/Cc/Bcc, bukan amplop SMTP seperti smtplib.
	# Jadi satu dokumen antrean = SATU penyerahan: kalau tiap penerima diserahkan
	# sendiri-sendiri, orang yang ada di header Cc menerima salinan berkali-kali.
	# Harganya: penanda baca dan tautan unsubscribe memakai personalisasi penerima
	# pertama untuk semua orang.
	if getattr(email_queue, "_cmi_graph_submitted", False):
		return

	mime = message if isinstance(message, bytes) else message.encode("utf-8")
	mime = _append_bcc(mime, email_queue)

	if len(mime) > MAX_MIME_SIZE:
		frappe.throw(
			_("Email {0} berukuran {1:.1f} MB, di atas batas 4 MB untuk kirim lewat Graph.").format(
				email_queue.name, len(mime) / (1024 * 1024)
			)
		)

	response = requests.post(
		GRAPH_SENDMAIL.format(mailbox=quote(account.email_id)),
		headers={
			"Authorization": f"Bearer {_graph_token(account)}",
			"Content-Type": "text/plain",
		},
		data=base64.b64encode(mime),
		timeout=60,
	)

	if response.status_code not in (200, 202):
		frappe.throw(
			_("Microsoft Graph menolak kiriman ({0}): {1}").format(
				response.status_code, response.text[:500]
			),
			title=_("Gagal Kirim lewat Graph"),
		)

	email_queue._cmi_graph_submitted = True


def _graph_token(account):
	"""Tukar refresh token Connected App jadi access token ber-scope Graph.

	Token Cache milik Frappe menyimpan access token untuk resource IMAP; yang dipakai
	di sini refresh token-nya, yang tidak terikat resource. Hasil penukaran disimpan di
	cache (bukan di Token Cache) supaya access token IMAP di sana tidak tertimpa.
	"""
	app = frappe.get_doc("Connected App", account.cmi_graph_connected_app)
	user = account.connected_user or frappe.session.user
	cache_key = f"cmi-graph-token:{app.name}:{user}"

	if cached := frappe.cache.get_value(cache_key):
		return cached

	token_cache = app.get_token_cache(user)
	if not token_cache or not token_cache.refresh_token:
		frappe.throw(
			_("Belum ada token untuk {0}. Buka Connected App {1} lalu klik Connect.").format(user, app.name),
			title=_("Token Tidak Ada"),
		)

	refresh_token = token_cache.get_password("refresh_token")
	response = requests.post(
		app.token_uri,
		data={
			"client_id": app.client_id,
			"client_secret": app.get_password("client_secret"),
			"grant_type": "refresh_token",
			"refresh_token": refresh_token,
			"scope": GRAPH_SCOPE,
		},
		timeout=30,
	)

	if response.status_code != 200:
		frappe.throw(
			_("Azure menolak penukaran token untuk Graph ({0}): {1}").format(
				response.status_code, response.text[:500]
			),
			title=_("Gagal Ambil Token Graph"),
		)

	data = response.json()

	# JANGAN menyimpan apa pun ke Token Cache, termasuk refresh token baru yang dikirim
	# Azure di sini. `TokenCache.get_expires_in()` menghitung kedaluwarsa dari
	# `modified` + `expires_in`, jadi sekali dokumen itu disimpan, Frappe mengira access
	# token IMAP di dalamnya baru diterbitkan dan tidak menyegarkannya lagi sampai jauh
	# setelah Microsoft mematikannya -- IMAP lalu balas `AUTHENTICATE failed` berjam-jam.
	# Refresh token lama tetap sah dipakai berulang, dan Frappe sendiri yang memutarnya
	# lewat penyegaran IMAP biasa.

	frappe.cache.set_value(
		cache_key, data["access_token"], expires_in_sec=max(60, cint(data.get("expires_in")) - 120)
	)

	return data["access_token"]


def _append_bcc(mime: bytes, email_queue) -> bytes:
	"""Tambahkan penerima yang tidak ada di header To/Cc sebagai Bcc.

	Frappe menaruh alamat bcc di daftar penerima antrean saja, tidak pernah di header --
	untuk SMTP itu cukup karena amplopnya yang menentukan. Graph tidak punya amplop, jadi
	tanpa header Bcc orang-orang itu tidak menerima apa pun.
	"""
	parsed = message_from_bytes(mime, policy=policy.default)
	addressed = {
		address.lower()
		for _name, address in getaddresses(parsed.get_all("To", []) + parsed.get_all("Cc", []))
		if address
	}

	missing = [
		row.recipient
		for row in email_queue.recipients
		if row.recipient and row.recipient.lower() not in addressed
	]
	if not missing:
		return mime

	# Sisipkan secara tekstual, bukan lewat as_bytes(): mem-bangun ulang pesan bisa
	# mengubah boundary dan pengkodean lampiran yang sudah jadi.
	for eol in (b"\r\n", b"\n"):
		head, sep, body = mime.partition(eol + eol)
		if sep:
			return head + eol + b"Bcc: " + ", ".join(missing).encode("utf-8") + sep + body

	return mime


def _send_over_smtp(account, sender, recipient, message):
	"""Akun non-Graph tetap lewat SMTP.

	`override_email_send` menggantikan SELURUH jalur kirim bawaan, jadi begitu hook ini
	terpasang, akun SMTP biasa juga harus dilayani di sini.
	"""
	msg = message if isinstance(message, bytes) else message.encode("utf-8")
	account.get_smtp_server().session.sendmail(from_addr=sender, to_addrs=recipient, msg=msg)

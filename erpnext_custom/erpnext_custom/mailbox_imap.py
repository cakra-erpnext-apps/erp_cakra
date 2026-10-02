"""Mailbox Local Mode lewat IMAP: mailbox di luar Microsoft 365 (cPanel, GoDaddy, dll).

Browser tidak bisa bicara IMAP/SMTP, jadi server ERP meneruskan: tiap panggilan membuka koneksi
atas nama user yang login, mengambil yang diminta, lalu menutupnya. Isi email TIDAK disimpan di
server; browser menyimpannya terenkripsi di laptop (public/js/mailbox_local.js, ImapMail), sama
persis dengan jalur Microsoft 365. Yang disimpan server cuma password email user (tabel __Auth,
terenkripsi encryption_key situs, seperti field Password).

Server, port, dan keamanan satu untuk semua user (ERPNext Custom Setting > Mailbox > IMAP);
login = alamat email User yang sedang login, jadi user tidak bisa membuka mailbox orang lain.

Galat yang wajar (password salah, server mati, folder hilang) DIKEMBALIKAN sebagai
{"error": ..., "need"/"missing": 1}, bukan dilempar: sinkron otomatis jalan tiap menit di semua
halaman desk, dan galat yang dilempar memunculkan pop-up di layar user tiap kali.

ponytail: satu koneksi IMAP per panggilan (login ulang tiap sinkron per folder); pakai pool per
user kalau server mail mulai membatasi jumlah login.
"""

import base64
import functools
import imaplib
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid

import frappe
from frappe import _
from frappe.core.utils import html2text
from frappe.utils import cint, cstr
from frappe.utils.password import get_decrypted_password, remove_encrypted_password, set_encrypted_password

PASSWORD_FIELD = "cmi_mailbox_imap_password"
TIMEOUT = 30
HEADER_FIELDS = "SUBJECT FROM TO CC MESSAGE-ID CONTENT-TYPE"
# Satu panggilan headers/older paling banyak sekian email (sama dengan halaman Graph).
PAGE = 100
OLDER_PAGE = 50

# Penanda SPECIAL-USE (RFC 6154) -> jenis folder yang dipakai halaman Mailbox (nama Graph).
SPECIAL_USE = {
	"\\sent": "sentitems",
	"\\drafts": "drafts",
	"\\junk": "junkemail",
	"\\trash": "deleteditems",
	"\\archive": "archive",
}
# Server tanpa SPECIAL-USE (Courier/cPanel lama): dikenali dari nama foldernya.
FOLDER_NAMES = {
	"sent": "sentitems",
	"sent items": "sentitems",
	"sent messages": "sentitems",
	"sent mail": "sentitems",
	"drafts": "drafts",
	"junk": "junkemail",
	"spam": "junkemail",
	"trash": "deleteditems",
	"deleted items": "deleteditems",
	"deleted messages": "deleteditems",
	"archive": "archive",
}

LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?P<delim>"(?:[^"\\]|\\.)*"|NIL) ?(?P<name>.*)$')


class LoginFailed(Exception):
	pass


class FolderMissing(Exception):
	pass


def relay(fn):
	"""Galat koneksi/login jadi jawaban biasa (lihat keterangan modul)."""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		try:
			return fn(*args, **kwargs)
		except (LoginFailed, smtplib.SMTPAuthenticationError) as e:
			return {"error": cstr(e) or _("IMAP login failed."), "need": "login"}
		except FolderMissing as e:
			return {"error": cstr(e), "missing": 1}
		except (imaplib.IMAP4.error, smtplib.SMTPException, OSError, frappe.ValidationError) as e:
			return {"error": cstr(e) or type(e).__name__}

	return wrapper


def is_enabled() -> bool:
	s = frappe.get_cached_doc("ERPNext Custom Setting")
	return bool(s.get("mailbox_local_mode") and s.get("mailbox_imap_enabled") and (s.get("mailbox_imap_host") or "").strip())


def is_connected(user: str) -> bool:
	return bool(
		frappe.db.sql(
			"select 1 from `__Auth` where doctype = 'User' and name = %s and fieldname = %s", (user, PASSWORD_FIELD)
		)
	)


def _settings():
	if not is_enabled():
		frappe.throw(_("IMAP is not enabled in ERPNext Custom Setting > Mailbox."))
	return frappe.get_cached_doc("ERPNext Custom Setting")


def _email() -> str:
	return (frappe.db.get_value("User", frappe.session.user, "email") or "").lower()


def _password() -> str:
	password = get_decrypted_password("User", frappe.session.user, PASSWORD_FIELD, raise_exception=False)
	if not password:
		raise LoginFailed(_("IMAP is not connected yet."))
	return password


class Imap:
	"""with Imap() as c: koneksi IMAP yang sudah login sebagai user yang sedang login."""

	def __init__(self, password: str | None = None):
		self.password = password

	def __enter__(self):
		s = _settings()
		host = s.mailbox_imap_host.strip()
		context = ssl.create_default_context()
		if s.mailbox_imap_ssl:
			self.c = imaplib.IMAP4_SSL(host, cint(s.mailbox_imap_port) or 993, ssl_context=context, timeout=TIMEOUT)
		else:
			self.c = imaplib.IMAP4(host, cint(s.mailbox_imap_port) or 143, timeout=TIMEOUT)
			if "STARTTLS" in self.c.capabilities:
				self.c.starttls(context)
		try:
			self.c.login(_email(), self.password or _password())
		except imaplib.IMAP4.error as e:
			self.c.shutdown()
			raise LoginFailed(_("IMAP login failed for {0}: {1}").format(_email(), _text(e))) from e
		return self.c

	def __exit__(self, *exc):
		try:
			self.c.logout()
		except Exception:
			pass


def _text(e) -> str:
	return cstr(e.args[0] if e.args else e).strip("b'\"")


def _quote(folder: str) -> str:
	return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _select(c, folder: str, readonly: bool = True) -> int:
	typ, _data = c.select(_quote(folder), readonly=readonly)
	if typ != "OK":
		raise FolderMissing(_("Folder {0} was not found on the mail server.").format(folder))
	return cint((c.response("UIDVALIDITY")[1] or [b"0"])[0])


def _check_validity(c, folder: str, uidvalidity, readonly: bool = True):
	# UIDVALIDITY berubah = semua UID folder itu berganti arti; id lama di laptop tak berlaku.
	if _select(c, folder, readonly) != cint(uidvalidity):
		raise FolderMissing(_("Folder {0} was renumbered on the mail server.").format(folder))


def _imap_date(iso: str, days: int = 0) -> str:
	# SINCE/BEFORE IMAP cuma tanggal (tanpa jam): hasilnya bisa lebih lebar sehari, browser
	# menyaring ulang dengan jam yang tepat.
	d = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(days=days)
	return d.strftime("%d-%b-%Y")


def _utf7(name: str) -> str:
	"""Nama folder IMAP (modified UTF-7, RFC 3501) -> teks biasa."""

	def decode(m):
		if not m[1]:
			return "&"
		b64 = m[1].replace(",", "/")
		return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")

	return re.sub(r"&([^-]*)-", decode, name)


def _uids(data) -> list[int]:
	return [int(x) for x in (data[0] or b"").split()] if data else []


# ---------------------------------------------------------------- endpoint


@frappe.whitelist(methods=["POST"])
@relay
def connect(password: str) -> dict:
	"""Uji login lalu simpan password email user (dipanggil dari dialog Connect IMAP)."""
	with Imap(password):
		pass
	set_encrypted_password("User", frappe.session.user, password, PASSWORD_FIELD)
	return {"ok": 1}


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	remove_encrypted_password("User", frappe.session.user, PASSWORD_FIELD)
	return {"ok": 1}


@frappe.whitelist(methods=["POST"])
@relay
def folders() -> dict:
	"""Semua folder: [{id (nama IMAP asli), name, path, kind}]."""
	with Imap() as c:
		typ, data = c.list()
	out = []
	for item in data or []:
		if isinstance(item, tuple):  # nama dikirim sebagai literal {n}
			m, name = LIST_RE.match(item[0].rsplit(b" ", 1)[0] + b" "), item[1]
		else:
			m = LIST_RE.match(item or b"")
			name = m and m["name"]
		if not m:
			continue
		flags = m["flags"].decode(errors="replace").lower()
		if "\\noselect" in flags or "\\nonexistent" in flags:
			continue
		name = name.strip()
		if name.startswith(b'"'):
			name = name[1:-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\")
		raw = name.decode(errors="replace")
		delim = m["delim"][1:-1].replace(b"\\", b"").decode() if m["delim"] != b"NIL" else ""
		path = [_utf7(p) for p in (raw.split(delim) if delim else [raw])]
		kind = next((k for flag, k in SPECIAL_USE.items() if flag in flags), None)
		if raw.upper() == "INBOX":
			kind = "inbox"
		out.append({"id": raw, "name": path[-1], "path": path, "kind": kind})

	# Tanpa SPECIAL-USE: kenali dari nama, satu folder per jenis.
	taken = {f["kind"] for f in out if f["kind"]}
	for f in out:
		kind = FOLDER_NAMES.get(f["name"].lower())
		if not f["kind"] and kind and kind not in taken:
			f["kind"] = kind
			taken.add(kind)
	return {"folders": out}


@frappe.whitelist(methods=["POST"])
@relay
def state(folder: str, since: str | None = None) -> dict:
	"""UIDVALIDITY + [uid, seen, flagged] semua email folder itu dalam rentang simpan. Browser
	membandingkannya dengan indeks laptop: yang baru diminta lewat headers(), yang hilang
	(dihapus/dipindah) dibuang, status dibaca diselaraskan.

	ponytail: seluruh rentang dibaca ulang tiap sinkron (ringan: angka saja); pakai CONDSTORE
	(MODSEQ) kalau mailbox dengan rentang "semua email" terasa lambat."""
	with Imap() as c:
		uidvalidity = _select(c, folder)
		typ, data = c.uid("SEARCH", None, f"SINCE {_imap_date(since)}" if since else "ALL")
		wanted = set(_uids(data))
		rows = []
		if wanted:
			typ, data = c.uid("FETCH", f"{min(wanted)}:{max(wanted)}", "(FLAGS)")
			for line in data or []:
				line = line[0] if isinstance(line, tuple) else line
				uid = re.search(rb"UID (\d+)", line or b"")
				flags = re.search(rb"FLAGS \(([^)]*)\)", line or b"")
				if uid and int(uid[1]) in wanted:
					flags = flags[1] if flags else b""
					rows.append([int(uid[1]), int(b"\\Seen" in flags), int(b"\\Flagged" in flags)])
	return {"uidvalidity": uidvalidity, "uids": rows}


@frappe.whitelist(methods=["POST"])
@relay
def headers(folder: str, uidvalidity: int, uids: str) -> dict:
	"""Data indeks (subjek, pengirim, tanggal, ...) untuk UID yang diminta (dipisah koma)."""
	uids = ",".join(str(cint(u)) for u in cstr(uids).split(",")[:PAGE] if cint(u))
	if not uids:
		return {"messages": []}
	with Imap() as c:
		_check_validity(c, folder, uidvalidity)
		return {"messages": _fetch_headers(c, uids)}


def _fetch_headers(c, uids: str) -> list[dict]:
	typ, data = c.uid("FETCH", uids, f"(UID FLAGS INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])")
	out = []
	for item in data or []:
		if not isinstance(item, tuple):
			continue
		meta, head = item
		uid = re.search(rb"UID (\d+)", meta)
		if not uid:
			continue
		flags = re.search(rb"FLAGS \(([^)]*)\)", meta)
		date = re.search(rb'INTERNALDATE "([^"]+)"', meta)
		msg = message_from_bytes(head or b"", policy=policy.default)
		sender = getaddresses([_header(msg, "From")])
		name, addr = sender[0] if sender else ("", "")
		out.append(
			{
				"uid": int(uid[1]),
				"subject": _header(msg, "Subject"),
				"from_name": name,
				"from_addr": addr.lower(),
				"to": _addresses(_header(msg, "To")),
				"cc": _addresses(_header(msg, "Cc")),
				"date": _iso(date[1].decode()) if date else "",
				"seen": 1 if flags and b"\\Seen" in flags[1] else 0,
				# bintang Important di Mailbox = \Flagged, sama dengan klien email lain
				"flagged": 1 if flags and b"\\Flagged" in flags[1] else 0,
				# ponytail: multipart/mixed dianggap berlampiran; BODYSTRUCTURE kalau perlu tepat
				"has_att": 1 if _header(msg, "Content-Type").lower().startswith("multipart/mixed") else 0,
				"imid": _header(msg, "Message-ID").strip().strip("<>"),
			}
		)
	return out


def _header(msg, name: str) -> str:
	try:
		return cstr(msg.get(name) or "").replace("\r", "").replace("\n", " ").strip()
	except Exception:  # header rusak dari pengirim: lewati, jangan gagalkan satu halaman
		return ""


def _addresses(value: str) -> str:
	return ", ".join(a for _n, a in getaddresses([value]) if a)


def _iso(internaldate: str) -> str:
	# INTERNALDATE: " 2-Oct-2026 09:15:00 +0700" -> "2026-10-02T02:15:00Z" (format Graph)
	d = datetime.strptime(internaldate.strip(), "%d-%b-%Y %H:%M:%S %z")
	return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@frappe.whitelist(methods=["POST"])
@relay
def raw(folder: str, uidvalidity: int, uid: int) -> dict:
	"""Isi lengkap satu email (.eml, base64). Tidak menandai dibaca."""
	with Imap() as c:
		_check_validity(c, folder, uidvalidity)
		typ, data = c.uid("FETCH", str(cint(uid)), "(BODY.PEEK[])")
	body = next((item[1] for item in data or [] if isinstance(item, tuple)), None)
	if body is None:
		raise FolderMissing(_("This email is no longer on the mail server."))
	return {"eml": base64.b64encode(body).decode()}


@frappe.whitelist(methods=["POST"])
@relay
def mark_read(folder: str, uidvalidity: int, uid: int) -> dict:
	with Imap() as c:
		_check_validity(c, folder, uidvalidity, readonly=False)
		c.uid("STORE", str(cint(uid)), "+FLAGS", "(\\Seen)")
	return {"ok": 1}


@frappe.whitelist(methods=["POST"])
@relay
def set_flag(folder: str, uidvalidity: int, uid: int, flagged: int) -> dict:
	with Imap() as c:
		_check_validity(c, folder, uidvalidity, readonly=False)
		c.uid("STORE", str(cint(uid)), "+FLAGS" if cint(flagged) else "-FLAGS", "(\\Flagged)")
	return {"ok": 1}


@frappe.whitelist(methods=["POST"])
@relay
def older(
	folder: str,
	before: str,
	search: str | None = None,
	lo: str | None = None,
	hi: str | None = None,
	offset: int = 0,
) -> dict:
	"""Email di luar rentang simpan, dibaca langsung dari server (tidak disimpan ke laptop)."""
	offset = cint(offset)
	criteria = [f"BEFORE {_imap_date(before)}"]
	if lo:
		criteria.append(f"SINCE {_imap_date(lo)}")
	if hi:
		criteria.append(f"BEFORE {_imap_date(hi, 1)}")
	with Imap() as c:
		uidvalidity = _select(c, folder)
		if search:
			# Kata kunci dikirim sebagai literal: aman untuk tanda kutip dan huruf non-ASCII.
			c.literal = search.encode()
			typ, data = c.uid("SEARCH", "CHARSET", "UTF-8", *criteria, "TEXT")
		else:
			typ, data = c.uid("SEARCH", None, *criteria)
		found = sorted(_uids(data), reverse=True)
		page = found[offset : offset + OLDER_PAGE]
		messages = _fetch_headers(c, ",".join(map(str, page))) if page else []
	messages.sort(key=lambda m: m["date"], reverse=True)
	more = offset + OLDER_PAGE < len(found)
	return {"uidvalidity": uidvalidity, "messages": messages, "next": offset + OLDER_PAGE if more else None}


@frappe.whitelist(methods=["POST"])
@relay
def find(message_id: str, folders) -> dict:
	"""Cari email lewat Message-ID di folder-folder yang diberikan (yang pertama ketemu)."""
	mid = cstr(message_id).strip().strip("<>")
	if not mid:
		return {}
	with Imap() as c:
		for folder in frappe.parse_json(folders) or []:
			try:
				uidvalidity = _select(c, folder)
			except FolderMissing:
				continue
			c.literal = f"<{mid}>".encode()
			typ, data = c.uid("SEARCH", "CHARSET", "UTF-8", "HEADER", "Message-ID")
			found = _uids(data)
			if found:
				return {"folder": folder, "uidvalidity": uidvalidity, "uid": found[-1]}
	return {}


@frappe.whitelist(methods=["POST"])
@relay
def send(
	to: str,
	subject: str,
	html: str,
	cc: str | None = None,
	attachments=None,
	in_reply_to: str | None = None,
	references: str | None = None,
	sent_folder: str | None = None,
	want_eml: int = 0,
) -> dict:
	"""Kirim lewat SMTP sebagai user yang login, lalu simpan salinannya ke folder Sent (server
	cPanel dan sejenisnya tidak melakukannya sendiri).

	attachments: [{name, type, b64, cid?}]; cid terisi = gambar inline yang dirujuk badan email.
	ponytail: server yang SUDAH menyimpan kiriman SMTP ke Sent sendiri (Gmail) jadi dobel;
	tambahkan setelan "jangan simpan ke Sent" kalau ada yang memakai server seperti itu."""
	email = _email()
	msg = EmailMessage()
	msg["From"] = formataddr((frappe.utils.get_fullname(frappe.session.user), email))
	msg["To"] = to
	if cc:
		msg["Cc"] = cc
	msg["Subject"] = subject or ""
	msg["Date"] = formatdate(localtime=True)
	msg["Message-ID"] = make_msgid(domain=email.rsplit("@", 1)[-1])
	if in_reply_to:
		msg["In-Reply-To"] = f"<{in_reply_to.strip('<>')}>"
		msg["References"] = cstr(references).strip() or msg["In-Reply-To"]

	msg.set_content(html2text(html or "") or " ")
	msg.add_alternative(html or "", subtype="html")
	body = msg.get_payload()[1]
	files = frappe.parse_json(attachments) or []
	for f in files:
		data = base64.b64decode(f.get("b64") or "")
		maintype, _s, subtype = (f.get("type") or "application/octet-stream").partition("/")
		if f.get("cid"):
			body.add_related(data, maintype, subtype or "octet-stream", cid=f"<{f['cid']}>", filename=f.get("name"))
	for f in files:
		if not f.get("cid"):
			data = base64.b64decode(f.get("b64") or "")
			maintype, _s, subtype = (f.get("type") or "application/octet-stream").partition("/")
			msg.add_attachment(data, maintype, subtype or "octet-stream", filename=f.get("name"))

	_smtp_send(msg)
	if sent_folder:
		with Imap() as c:
			c.append(_quote(sent_folder), "(\\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())

	return {
		"message_id": msg["Message-ID"].strip("<>"),
		"eml": base64.b64encode(msg.as_bytes()).decode() if cint(want_eml) else None,
	}


def _smtp_send(msg: EmailMessage):
	s = _settings()
	host = (s.mailbox_smtp_host or s.mailbox_imap_host).strip()
	security = s.mailbox_smtp_security or "SSL"
	context = ssl.create_default_context()
	if security == "SSL":
		smtp = smtplib.SMTP_SSL(host, cint(s.mailbox_smtp_port) or 465, context=context, timeout=TIMEOUT)
	else:
		smtp = smtplib.SMTP(host, cint(s.mailbox_smtp_port) or 587, timeout=TIMEOUT)
		if security == "STARTTLS":
			smtp.starttls(context=context)
	with smtp:
		smtp.login(_email(), _password())
		smtp.send_message(msg)

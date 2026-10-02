"""Arsip email ke database terpisah `mail_db` supaya database utama (erp_db) tetap kecil.

Keputusan pemilik sistem (2026-10-01):
- Email tertaut ke transaksi: header (subjek, pengirim, penerima, tanggal, tautan) tetap di
  Communication erp_db supaya tetap muncul di transaksinya; ISI lengkap (content, text_content)
  pindah ke mail_db.communication_content saat ditautkan. Di erp_db tersisa cuplikan
  SNIPPET huruf untuk daftar tab Email. Dibaca balik saat email dibuka (content_of).
  Pengecualian: email yang tertaut ke doctype CRM -- aplikasi CRM membaca isi email langsung
  dari Communication, jadi isinya tetap (atau dikembalikan) di erp_db.
- Email Queue: tiap hari dipindah utuh ke mail_db lalu dihapus dari erp_db. Sent/Error sesudah
  `mail_queue_done_days`, Not Sent/Sending sesudah `mail_queue_pending_days` (ERPNext Custom
  Setting > Mailbox). Yang tertahan dinotifikasi ke System Manager (alert_stuck).

Nama database: `mail_db`, atau `mail_db` di site_config kalau satu server MariaDB dipakai
beberapa site. Dibuat migrate lewat extra_db.ensure. bench backup TIDAK mencakupnya: backup().
"""

import gzip
import os
import shutil
import subprocess
from email.header import decode_header, make_header
from email.parser import HeaderParser

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, cstr, escape_html, get_backups_path, now_datetime

SNIPPET = 200
QUEUE_DONE = ("Sent", "Error")
# Partially Sent masih dicoba ulang Frappe, jadi diperlakukan seperti yang belum terkirim.
QUEUE_PENDING = ("Not Sent", "Sending", "Partially Sent")
QUEUE_TABLES = (("tabEmail Queue", "email_queue"), ("tabEmail Queue Recipient", "email_queue_recipient"))
BATCH = 500


def db() -> str:
	return frappe.conf.get("mail_db") or "mail_db"


def ensure():
	"""after_migrate: database + tabelnya. Tabel Email Queue mengikuti struktur aslinya; kolom
	baru dari update Frappe ditambahkan ke salinannya."""
	from erpnext_custom.extra_db import ensure as ensure_db

	if not ensure_db(db()):
		return
	d = db()
	first_time = not frappe.db.sql(f"show tables from `{d}` like 'communication_content'")
	frappe.db.sql_ddl(
		f"""create table if not exists `{d}`.communication_content (
			name varchar(140) not null primary key,
			content longtext,
			text_content longtext,
			moved_on datetime(6) not null
		) engine=InnoDB"""
	)
	frappe.db.sql_ddl(
		f"""create table if not exists `{d}`.email_queue_alert (
			name varchar(140) not null primary key,
			alerted_on datetime(6) not null
		) engine=InnoDB"""
	)
	for src, dst in QUEUE_TABLES:
		frappe.db.sql_ddl(f"create table if not exists `{d}`.{dst} like `{src}`")
		have = {c[0] for c in frappe.db.sql(f"show columns from `{d}`.{dst}")}
		for col, coltype, *_rest in frappe.db.sql(f"show columns from `{src}`"):
			if col not in have:
				frappe.db.sql_ddl(f"alter table `{d}`.{dst} add column `{col}` {coltype} null")
	if first_time:
		_move_existing()


def _move_existing():
	"""Sekali, saat mail_db baru dibuat: email yang sudah tertaut sebelumnya ikut diarsip."""
	from erpnext_custom.mail_inbox import _transaction_doctypes

	doctypes = tuple(dt for dt in _transaction_doctypes() if not dt.startswith("CRM"))
	names = frappe.db.sql_list(
		"""select distinct c.name from `tabCommunication` c
		left join `tabCommunication Link` l on l.parent = c.name and l.parenttype = 'Communication'
		where c.communication_medium = 'Email' and ifnull(c.content, '') != ''
			and (c.reference_doctype in %(dt)s or l.link_doctype in %(dt)s)""",
		{"dt": doctypes},
	)
	for start in range(0, len(names), BATCH):
		move_content(names[start : start + BATCH])


# ---------------------------------------------------------------- isi email tertaut


def move_content(names):
	"""Isi email tertaut -> mail_db, di erp_db tinggal cuplikan. Dipanggil dalam transaksi yang
	sama dengan penautannya (link/unlink_transaction), jadi gagal di sini = tautan ikut batal."""
	from erpnext_custom.mail_inbox import _links_of

	names = [n for n in set(names or []) if n]
	if not names:
		return
	crm = _crm_linked(names)
	if crm:
		_restore(crm)
	names = [n for n in names if n not in crm and _links_of(n)]
	if not names:
		return

	where = "name in %(names)s and ifnull(content, '') != ''"
	args = {"names": tuple(names), "n": SNIPPET}
	frappe.db.sql(
		f"""insert into `{db()}`.communication_content (name, content, text_content, moved_on)
		select name, content, text_content, now(6) from `tabCommunication` where {where}
		on duplicate key update content = values(content), text_content = values(text_content),
			moved_on = values(moved_on)""",
		args,
	)
	frappe.db.sql(
		f"update `tabCommunication` set content = '', text_content = left(text_content, %(n)s) where {where}",
		args,
	)


def _crm_linked(names) -> set:
	by_ref = frappe.get_all(
		"Communication", filters={"name": ["in", names], "reference_doctype": ["like", "CRM %"]}, pluck="name"
	)
	by_link = frappe.get_all(
		"Communication Link",
		filters={"parent": ["in", names], "parenttype": "Communication", "link_doctype": ["like", "CRM %"]},
		pluck="parent",
	)
	return set(by_ref) | set(by_link)


def _restore(names):
	"""Isi yang sudah di mail_db dikembalikan ke erp_db (email kini tertaut ke CRM)."""
	args = {"names": tuple(names)}
	frappe.db.sql(
		f"""update `tabCommunication` c join `{db()}`.communication_content m on m.name = c.name
		set c.content = m.content, c.text_content = m.text_content
		where c.name in %(names)s and ifnull(c.content, '') = ''""",
		args,
	)
	frappe.db.sql(f"delete from `{db()}`.communication_content where name in %(names)s", args)


def content_of(name: str) -> dict | None:
	rows = frappe.db.sql(
		f"select content, text_content from `{db()}`.communication_content where name = %s",
		name,
		as_dict=True,
	)
	return rows[0] if rows else None


def fill_content(doc, method=None):
	"""Hook Communication.onload: form Communication menampilkan isi dari mail_db."""
	if not doc.content:
		found = content_of(doc.name)
		if found:
			doc.content, doc.text_content = found.content, found.text_content


# ---------------------------------------------------------------- Email Queue


SETTINGS = {"mail_queue_done_days": 1, "mail_queue_pending_days": 3, "mail_queue_alert_minutes": 30}


def _settings():
	# Langsung dari tabSingles: field Single yang belum pernah disimpan (server yang baru
	# migrate) tidak punya baris, dan get_single_value membacanya 0 = mati, bukan bawaannya.
	saved = dict(
		frappe.db.sql(
			"select field, value from tabSingles where doctype = 'ERPNext Custom Setting' and field in %s",
			(tuple(SETTINGS),),
		)
	)
	return tuple(cint(saved[f]) if saved.get(f) not in (None, "") else d for f, d in SETTINGS.items())


def archive_queue():
	"""Scheduler harian. 0 hari = kelompok itu tidak dipindah."""
	done_days, pending_days, _minutes = _settings()
	now = now_datetime()
	for statuses, days in ((QUEUE_DONE, done_days), (QUEUE_PENDING, pending_days)):
		if days <= 0:
			continue
		cutoff = add_to_date(now, days=-days)
		while names := frappe.get_all(
			"Email Queue",
			filters={"status": ["in", statuses], "creation": ["<", cutoff]},
			pluck="name",
			limit=BATCH,
		):
			_move_queue(names)
			frappe.db.commit()


def _move_queue(names):
	d = db()
	args = {"names": tuple(names)}
	for src, dst in QUEUE_TABLES:
		key = "parent" if dst == "email_queue_recipient" else "name"
		mine = {c[0] for c in frappe.db.sql(f"show columns from `{d}`.{dst}")}
		cols = ", ".join(f"`{c[0]}`" for c in frappe.db.sql(f"show columns from `{src}`") if c[0] in mine)
		frappe.db.sql(
			f"insert ignore into `{d}`.{dst} ({cols}) select {cols} from `{src}` where `{key}` in %(names)s", args
		)
	frappe.db.sql("delete from `tabEmail Queue Recipient` where parent in %(names)s", args)
	frappe.db.sql("delete from `tabEmail Queue` where name in %(names)s", args)
	frappe.db.sql(f"delete from `{d}`.email_queue_alert where name in %(names)s", args)


def alert_stuck():
	"""Scheduler tiap 5 menit: email yang belum terkirim lebih dari `mail_queue_alert_minutes`
	-> Notification Log ke System Manager (lonceng + popup aplikasi desktop), sekali per email.

	Antrean yang berasal dari Email Queue / Notification Log dilewati sebagai pengaman: notifikasi
	tipe Alert sendiri tidak pernah mengirim email (is_email_notifications_enabled_for_type), tapi
	kalau suatu saat diganti tipe lain, alert tidak boleh memicu alert berikutnya.
	"""
	_done, _pending, minutes = _settings()
	if minutes <= 0:
		return
	now = now_datetime()
	rows = frappe.db.sql(
		f"""select q.name, q.status, q.error, q.message,
			(select group_concat(r.recipient separator ', ') from `tabEmail Queue Recipient` r
				where r.parent = q.name) recipients
		from `tabEmail Queue` q
		left join `{db()}`.email_queue_alert a on a.name = q.name
		where q.status in %(statuses)s and a.name is null
			and ifnull(q.reference_doctype, '') not in ('Email Queue', 'Notification Log')
			and coalesce(q.send_after, q.creation) < %(cutoff)s
		order by q.creation limit 50""",
		{"statuses": QUEUE_PENDING, "cutoff": add_to_date(now, minutes=-minutes)},
		as_dict=True,
	)
	if not rows:
		return

	admins = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"name": ["in", frappe.get_all("Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent")],
		},
		pluck="name",
	)
	for row in rows:
		subject = _("Email not sent after {0} minutes ({1}): {2} to {3}").format(
			minutes,
			_(row.status),
			escape_html(_subject(row.message)[:150]) or _("(no subject)"),
			escape_html(cstr(row.recipients)[:150]),
		)
		for user in admins:
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": subject,
					"email_content": escape_html(cstr(row.error)[:500]),
					"document_type": "Email Queue",
					"document_name": row.name,
				}
			).insert(ignore_permissions=True)
		frappe.db.sql(
			f"insert ignore into `{db()}`.email_queue_alert (name, alerted_on) values (%s, %s)", (row.name, now)
		)


def _subject(message) -> str:
	try:
		raw = HeaderParser().parsestr(cstr(message), headersonly=True).get("Subject") or ""
		return str(make_header(decode_header(raw)))
	except Exception:
		return ""


# ---------------------------------------------------------------- backup


def backup() -> str:
	"""Backup mail_db ke folder backup site (sites/<site>/private/backups), terpisah dari bench
	backup. Jalankan: bench --site <site> execute erpnext_custom.mail_archive.backup"""
	conf = frappe.conf
	path = os.path.join(get_backups_path(), f"{now_datetime():%Y%m%d_%H%M%S}-{db()}.sql.gz")
	dump = subprocess.Popen(
		[
			"mariadb-dump" if shutil.which("mariadb-dump") else "mysqldump",
			f"--host={conf.db_host or 'localhost'}",
			f"--port={conf.db_port or 3306}",
			f"--user={conf.db_user or conf.db_name}",
			"--single-transaction",
			"--quick",
			db(),
		],
		# password lewat environment, bukan argumen (argumen terlihat di daftar proses)
		env={**os.environ, "MYSQL_PWD": conf.db_password},
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
	)
	# dialirkan per potong: mail_db bisa jauh lebih besar dari memori
	with gzip.open(path, "wb") as f:
		shutil.copyfileobj(dump.stdout, f)
	if dump.wait():
		os.remove(path)
		frappe.throw(_("Backup {0} failed: {1}").format(db(), cstr(dump.stderr.read())[:500]))
	return path

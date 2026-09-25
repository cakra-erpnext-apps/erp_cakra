"""Email masuk: penjaga penarikan, sinkron banyak folder IMAP, notifikasi, dan tautan
email ke transaksi. Dipakai halaman Mailbox (page/mailbox).

Nama lampiran kepanjangan
    Satu email cacat tidak boleh menjatuhkan seluruh penarikan: `EmailAccount.receive`
    memproses satu batch dalam satu transaksi, jadi kalau satu lampiran ditolak, email
    lain di batch yang sama ikut tidak masuk dan penarikan berikutnya mengulangi
    kegagalan yang sama terus-menerus. Pemicu nyata: nama lampiran lebih panjang dari
    kolom `File.file_name` (140 karakter).

Banyak folder
    Frappe mendukung banyak folder per akun, tapi di mode sinkron ALL loop-nya rusak:
    - titik awal (`build_email_sync_rule`) dihitung SEKALI per akun dari UID tertinggi
      semua email, padahal UID IMAP berlaku per folder. Folder kecil (UID 1..48) di
      belakang INBOX (UID ribuan) cuma terus mendapat satu surat terakhirnya;
    - folder yang baru pertama disinkron menimpa aturan itu di objek bersama (bocor ke
      folder berikutnya) dan mereset `uid = -1` pada SELURUH email akun;
    - kolom `Communication.imap_folder` ada, tapi tidak pernah diisi.
    `get_inbound_mails` di sini menggantikan loop itu: aturan per folder, disetel ulang
    tiap folder, UIDVALIDITY folder baru diisi dulu supaya reset tadi tidak terpicu,
    dan asal folder dicatat.

Folder Terkirim (Sent Items)
    Frappe menolak setiap surat yang pengirimnya alamat akun itu sendiri
    (`SentEmailInInboxError`), jadi isi Sent Items tidak pernah bisa masuk. Folder yang
    ditandai `cmi_is_sent` (terdeteksi otomatis dari penanda IMAP \\Sent) dicatat sebagai
    Communication Terkirim, tanpa diteruskan ke siapa pun -- surat itu sudah sampai ke
    penerimanya dari Outlook.

Kecepatan
    - Tarikan terjadwal bawaan Frappe cuma tiap 10 menit; `pull_often` menjalankannya
      tiap menit.
    - `UID N:*` saat belum ada surat baru dijawab server dengan surat TERAKHIR folder itu
      (RFC 3501: `*` = UID tertinggi). Bawaan Frappe lalu mengunduhnya utuh, lampiran
      ikut, di setiap tarikan dan di setiap folder. `_fetch` membuangnya sebelum diunduh.
    - Tombol Tarik Email memakai nama job yang sama dengan tarikan terjadwal, jadi
      keduanya tidak pernah berjalan bersamaan (sebelumnya saling menunggu kunci baris
      Email Account sampai `Lock wait timeout`).

Isi awal / tarik ulang
    Email LAMA tidak ditarik lewat penarik rutin, karena `receive()` memperlakukan tiap
    Communication baru sebagai email yang baru datang: meneruskannya ke peserta dokumen
    yang terhubung, dan hook assistant bisa membalas otomatis. `backfill` membuat
    Communication-nya saja, senyap.
"""

import os
import re
import socket
from email.utils import getaddresses

import frappe
from frappe import _
from frappe.email.doctype.email_account.email_account import EmailAccount, pull_from_email_account
from frappe.email.receive import InboundMail, LoginLimitExceeded, SentEmailInInboxError
from frappe.utils import add_days, cint
from frappe.utils.background_jobs import enqueue, get_jobs

FILE_NAME_LIMIT = 140

# get_messages Frappe mengambil paling banyak 100 surat per panggilan.
BATCH = 100

MAIL_FIELDS = {
	"IMAP Folder": [
		{
			"fieldname": "cmi_is_sent",
			"label": "Folder Terkirim",
			"fieldtype": "Check",
			"insert_after": "append_to",
			"in_list_view": 1,
			"description": (
				"Isinya surat yang DIKIRIM dari akun ini (Sent Items). Dicatat sebagai email "
				"Terkirim, bukan email masuk. Terisi otomatis dari penanda \\Sent server IMAP."
			),
		}
	]
}

# Siapa yang boleh membuka halaman Mailbox (menu Inbox/Sent), selain System Manager: role ini
# tercantum di page/mailbox/mailbox.json dan diberikan admin per user.
MAILBOX_ROLE = "Mailbox User"


def ensure_mailbox_role():
	"""after_migrate. Page diimpor dengan ignore_links, jadi role yang belum ada tidak menggagalkan
	impor mailbox.json; di sini role-nya dibuat supaya bisa diberikan ke user."""
	if not frappe.db.exists("Role", MAILBOX_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": MAILBOX_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def trim_file_name(doc, method=None):
	"""Potong nama berkas yang kepanjangan, ekstensinya dipertahankan."""
	name = doc.file_name or ""
	if len(name) <= FILE_NAME_LIMIT:
		return

	root, ext = os.path.splitext(name)
	# Ekstensi dipertahankan karena itu yang menentukan berkas ini dibuka pakai apa;
	# yang dibuang bagian tengah-akhir nama yang cuma keterangan.
	doc.file_name = root[: FILE_NAME_LIMIT - len(ext)] + ext


# ---------------------------------------------------------------- tarik email


def _pull_job_name(email_account: str) -> str:
	# SAMA PERSIS dengan nama job di frappe...email_account.pull(); itulah yang membuat
	# tombol dan tarikan terjadwal saling mengenali dan tidak jalan bersamaan.
	return f"pull_from_email_account|{email_account}"


def _is_pulling(email_account: str) -> bool:
	site = frappe.local.site
	return _pull_job_name(email_account) in get_jobs(site=site, key="job_name")[site]


def pull_often():
	"""Scheduler tiap menit: tarikan bawaan Frappe (tiap 10 menit) terlalu jarang."""
	from frappe.email.doctype.email_account.email_account import pull

	pull()


@frappe.whitelist()
def pull_now(email_account: str) -> dict:
	"""Tombol Tarik Email. Hasilnya dipantau halaman lewat `mailbox_state`, bukan realtime:
	`frappe.realtime.on` di desk ini membuang listener diam-diam kalau socket belum
	terbentuk saat halaman dimuat (lihat public/js/notification_badge.js), dan tombolnya
	jadi macet sampai halaman di-refresh.
	"""
	# Nama kosong lolos has_permission (dianggap cek tingkat doctype), jadi ditolak di sini
	# dengan pesan yang bisa dimengerti, bukan " tidak menerima email masuk."
	if not email_account:
		frappe.throw(_("Select an email account first."))

	frappe.has_permission("Email Account", "read", doc=email_account, throw=True)

	if not frappe.db.get_value("Email Account", email_account, "enable_incoming"):
		frappe.throw(_("{0} does not receive incoming email.").format(email_account))

	if not _is_pulling(email_account):
		enqueue(
			pull_from_email_account,
			"short",
			event="all",
			job_name=_pull_job_name(email_account),
			email_account=email_account,
		)

	return mailbox_state(email_account)


@frappe.whitelist()
def mailbox_state(email_account: str) -> dict:
	"""Dipoll halaman Mailbox: ada surat baru? penarikan masih jalan?"""
	frappe.has_permission("Email Account", "read", doc=email_account, throw=True)

	latest, total = frappe.db.sql(
		"""select max(creation), count(*) from `tabCommunication`
		where email_account = %s and communication_medium = 'Email'""",
		email_account,
	)[0]
	return {"latest": str(latest or ""), "total": cint(total), "pulling": _is_pulling(email_account)}


# ---------------------------------------------------------------- banyak folder


class CMIInboundMail(InboundMail):
	"""InboundMail yang mencatat folder asalnya dan bisa berupa surat Terkirim."""

	def __init__(self, *args, imap_folder=None, is_sent=False, **kwargs):
		super().__init__(*args, **kwargs)
		self.imap_folder = imap_folder
		self.is_sent = is_sent

	def as_dict(self):
		data = super().as_dict()
		data["imap_folder"] = self.imap_folder
		if self.is_sent:
			data["sent_or_received"] = "Sent"
			data["seen"] = 1
		return data

	def process(self):
		if self.is_sent:
			return self._process_sent()

		communication = super().process()
		# Sudah ada di sistem tapi kini ditemukan di folder lain = dipindahkan di Outlook.
		# Frappe sendiri cuma memperbarui uid-nya; foldernya ikut dicatat supaya uid dan
		# folder tetap sepasang (titik awal per folder dihitung dari pasangan itu).
		if (
			communication
			and not self.flags.is_new_communication
			and communication.get("imap_folder") != self.imap_folder
		):
			communication.db_set("imap_folder", self.imap_folder, update_modified=False)

		if communication and self.flags.is_new_communication:
			# dikumpulkan di akun, diberitahukan sekali di akhir receive() (notify_new_mail)
			self.email_account.flags.setdefault("cmi_new_mail", []).append(communication.name)

		return communication

	def _process_sent(self):
		# Kiriman dari ERPNext juga tersimpan di Sent Items oleh server (Graph menyimpannya),
		# jadi dicocokkan lewat Message-ID ke SEMUA Communication akun, bukan cuma yang
		# Received seperti is_exist_in_system bawaan -- kalau tidak, tiap kiriman dobel.
		existing = self.message_id and frappe.db.get_value(
			"Communication",
			{"message_id": self.message_id, "email_account": self.email_account.name},
			"name",
		)
		if existing:
			frappe.db.set_value(
				"Communication",
				existing,
				{"uid": self.uid, "imap_folder": self.imap_folder},
				update_modified=False,
			)
			return frappe.get_doc("Communication", existing)

		# Sengaja TIDAK menandai is_new_communication: receive() lalu tidak memanggil
		# send_email(), yang akan meneruskan surat ini ke peserta dokumen terkait.
		return self._build_communication_doc()


def sync_start(max_uid, uidnext) -> int:
	"""UID pertama yang diambil dari satu folder di mode ALL.

	Lanjut dari surat terakhir yang sudah ada di folder itu; folder yang belum pernah diisi
	mulai dari ujungnya (`uidnext`) -- surat lamanya urusan `backfill`, bukan penarik rutin.
	"""
	return cint(max_uid) + 1 if cint(max_uid) > 0 else cint(uidnext) or 1


def sync_rule(option: str, max_uid, uidnext) -> str:
	"""Aturan UID SEARCH untuk SATU folder. Mode UNSEEN memang per folder dari sananya."""
	if option != "ALL":
		return option or "UNSEEN"

	return f"UID {sync_start(max_uid, uidnext)}:*"


def get_inbound_mails(account) -> list:
	"""Pengganti `EmailAccount.get_inbound_mails` untuk akun IMAP (lihat docstring modul)."""
	if not account.enable_incoming or not account.use_imap or account.service == "Frappe Mail":
		return EmailAccount.get_inbound_mails(account)

	mails = []
	try:
		server = account.get_incoming_server(in_receive=True, email_sync_rule="UNSEEN")
		for folder in account.imap_folder:
			if not server.select_imap_folder(folder.folder_name):
				continue

			_seed_uidvalidity(server, folder)
			max_uid = _max_uid(account.name, folder.folder_name)
			server.settings["uid_validity"] = folder.uidvalidity
			server.settings["email_sync_rule"] = sync_rule(account.email_sync_option, max_uid, folder.uidnext)

			start = sync_start(max_uid, folder.uidnext) if account.email_sync_option == "ALL" else None
			messages = _fetch(server, folder.folder_name, start)
			mails.extend(_to_inbound(account, messages, folder))

			# check_imap_uidvalidity menulis uidnext ke baris Email Account di tiap folder.
			# Dilepas sekarang, bukan menunggu surat pertama selesai diproses, supaya baris
			# itu tidak terkunci selama seluruh unduhan berlangsung.
			frappe.db.commit()

		server.logout()
	except Exception:
		account.log_error(title=_("Error while connecting to email account {0}").format(account.name))
		return []

	return mails


def _fetch(server, folder_name: str, start=None) -> dict:
	"""`EmailServer.get_messages` bawaan, tapi UID di bawah `start` dibuang SEBELUM diunduh."""
	server.latest_messages = []
	server.seen_status = {}
	server.uid_reindexed = False

	quoted = f'"{folder_name}"'
	uids = server.get_new_mails(quoted)
	# uid_reindexed = Frappe menimpa aturannya sendiri (UIDVALIDITY berubah); hasilnya dipakai apa adanya.
	if start and not server.uid_reindexed:
		uids = [uid for uid in uids if cint(uid) >= start]

	for index, uid in enumerate(uids[:BATCH]):
		try:
			server.retrieve_message(uid, index + 1, quoted)
		except (socket.timeout, LoginLimitExceeded):
			break

	return {
		"latest_messages": server.latest_messages,
		"uid_list": uids,
		"seen_status": server.seen_status,
		"uid_reindexed": server.uid_reindexed,
	}


def _to_inbound(account, messages, folder, keep_seen=False) -> list:
	out = []
	for index, message in enumerate(messages.get("latest_messages", [])):
		uid = messages["uid_list"][index] if messages.get("uid_list") else None
		seen_status = messages.get("seen_status", {}).get(uid)
		if account.email_sync_option == "UNSEEN" and seen_status == "SEEN" and not keep_seen:
			continue

		out.append(
			CMIInboundMail(
				message,
				account,
				frappe.safe_decode(uid),
				seen_status,
				folder.append_to,
				imap_folder=folder.folder_name,
				is_sent=cint(folder.get("cmi_is_sent")),
			)
		)
	return out


def _max_uid(email_account: str, folder_name: str):
	return frappe.db.sql(
		"""select max(uid) from `tabCommunication`
		where email_account = %s and imap_folder = %s and communication_medium = 'Email'""",
		(email_account, folder_name),
	)[0][0]


def _seed_uidvalidity(server, folder):
	"""Isi UIDVALIDITY folder yang belum pernah disinkron dengan nilai server saat ini.

	Tanpa ini `check_imap_uidvalidity` Frappe menganggapnya berubah: aturan folder ditimpa
	jadi "N surat terakhir" dan `uid` SELURUH email akun direset ke -1. Sekalian dicatat
	apakah ini folder surat terkirim (penanda IMAP \\Sent).
	"""
	if folder.uidvalidity:
		return

	quoted = f'"{folder.folder_name}"'
	_typ, data = server.imap.status(quoted, "(UIDVALIDITY UIDNEXT)")
	folder.uidvalidity = server.parse_imap_response("UIDVALIDITY", data[0])
	folder.uidnext = server.parse_imap_response("UIDNEXT", data[0])

	_typ, listing = server.imap.list('""', quoted)
	flags = re.match(rb"\(([^)]*)\)", (listing or [b""])[0] or b"")
	if flags and b"\\Sent" in flags.group(1):
		folder.cmi_is_sent = 1

	folder.db_update()
	frappe.db.commit()


# ---------------------------------------------------------------- notifikasi


def notify_new_mail(account, names: list):
	"""Satu Notification Log per email baru, untuk setiap user yang memegang mailbox ini.

	Tipe "Alert" sengaja: Frappe tidak pernah mengirim email notifikasi untuk tipe itu
	(is_email_notifications_enabled_for_type), jadi tidak ada email yang memicu email.
	Lonceng dan toast-nya digambar public/js/notification_badge.js.
	"""
	if not names:
		return

	users = frappe.get_all("User Email", filters={"email_account": account.name}, pluck="parent")
	if not users:
		return

	for name in names:
		mail = frappe.db.get_value(
			"Communication", name, ["subject", "sender", "sender_full_name"], as_dict=True
		)
		if not mail:
			continue

		who = mail.sender_full_name or mail.sender or ""
		for user in set(users):
			frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"type": "Alert",
					"subject": _("New email from {0}: {1}").format(who, mail.subject or _("(no subject)")),
					"document_type": "Communication",
					"document_name": name,
					"link": f"/desk/mailbox?open={name}",
				}
			).insert(ignore_permissions=True)

	frappe.db.commit()


# ---------------------------------------------------------------- tautan ke transaksi


def _transaction_doctypes() -> set:
	# Sama persis dengan yang bisa dicari di modal Tautkan ke: ledger/log/pengaturan tidak
	# boleh ditautkan walau endpoint-nya dipanggil langsung.
	from erpnext_custom.quick_search import transaction_doctypes

	return set(transaction_doctypes())


@frappe.whitelist()
def get_links(communication: str) -> list[dict]:
	"""Transaksi yang tertaut ke email ini: reference utamanya + timeline links.

	Timeline links juga berisi Contact pengirim yang ditambahkan Frappe otomatis -- itu
	bukan transaksi, jadi hanya doctype bernomor (quick_search) yang ditampilkan.

	Izinnya dari transaksinya, bukan dari Communication (aturan tautan, lihat
	link_transaction): yang dikembalikan hanya transaksi yang boleh dibaca user ini.
	"""
	return [link for link in _links_of(communication) if _can_read(link["doctype"], link["name"])]


def _can_read(doctype: str, name: str) -> bool:
	return bool(frappe.db.exists(doctype, name) and frappe.has_permission(doctype, "read", doc=name))


def _links_of(communication: str) -> list[dict]:
	"""Seperti get_links, tanpa cek izin: dipakai hook saat email baru disimpan."""
	doc = frappe.get_doc("Communication", communication)
	allowed = _transaction_doctypes()
	links = []
	if doc.reference_doctype and doc.reference_name and doc.reference_doctype in allowed:
		links.append({"doctype": doc.reference_doctype, "name": doc.reference_name})

	for row in doc.timeline_links:
		pair = {"doctype": row.link_doctype, "name": row.link_name}
		if row.link_doctype in allowed and pair not in links:
			links.append(pair)

	return links


@frappe.whitelist()
def link_transaction(communication: str, doctype: str, name: str) -> list[dict]:
	"""Tautkan email ke satu transaksi -- berikut SELURUH percakapannya (lihat conversation).

	Orang menautkan "urusan", bukan satu surat: balasan sebelum dan sesudahnya ikut tampil di
	timeline dokumen itu. Email yang datang belakangan ikut sendiri lewat
	inherit_conversation_links.

	Aturan (keputusan pemilik sistem): siapa pun yang boleh MEMBACA transaksinya boleh
	menautkan. Izin tulis Communication sengaja tidak dipakai -- bawaan Frappe hampir tidak
	memberikannya ke siapa pun (di prod cuma Agent Manager), jadi System Manager biasa pun
	tertolak. Penyimpanannya memakai ignore_permissions di _link_one.
	"""
	if doctype not in _transaction_doctypes():
		frappe.throw(_("{0} is not a transaction document.").format(doctype))
	frappe.get_doc(doctype, name).check_permission("read")

	for member in conversation(communication):
		_link_one(member, doctype, name)

	return _links_of(communication)


def _link_one(communication: str, doctype: str, name: str):
	doc = frappe.get_doc("Communication", communication)
	if {"doctype": doctype, "name": name} in _links_of(communication):
		return

	# Reference utama dipakai kalau masih kosong; kalau sudah terisi (mis. "Communication
	# <induk>" hasil membalas dari desk), transaksinya masuk timeline links.
	if not doc.reference_doctype or not doc.reference_name:
		doc.reference_doctype, doc.reference_name = doctype, name
	else:
		doc.add_link(doctype, name)
	doc.save(ignore_permissions=True)


# ---------------------------------------------------------------- percakapan

# Email satu percakapan yang dicari lewat subjek harus berjarak paling jauh sekian hari.
CONVERSATION_DAYS = 30
CONVERSATION_LIMIT = 300
_REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw|wg|tr)\s*(\[\d+\])?\s*:\s*)+", re.I)


def normalize_subject(subject) -> str:
	"""Subjek tanpa awalan balas/teruskan: "RE: Fwd: Re: Invoice PL-01" -> "invoice pl-01"."""
	return _REPLY_PREFIX.sub("", subject or "").strip().lower()


def conversation(communication: str) -> set:
	"""Semua email satu percakapan dengan `communication`, termasuk dirinya.

	1. Rantai balasan lewat `in_reply_to`, ke atas dan ke bawah -- ini yang pasti.
	2. Ditambah email bersubjek sama (tanpa Re:/Fwd:) yang melibatkan pihak LUAR yang sama,
	   dalam CONVERSATION_DAYS hari. Perlu karena rantai bisa putus: `in_reply_to` hanya
	   terisi kalau email yang dibalas sudah ada di ERP saat balasannya masuk, dan kiriman
	   dari Outlook baru tertarik dari Sent Items belakangan.

	ponytail: pencocokan subjek bisa menyatukan dua urusan yang kebetulan bersubjek sama
	dengan pihak yang sama dalam 30 hari (mis. "Invoice" bulanan dari vendor yang sama).
	Kalau itu terjadi, simpan header References saat impor dan jadikan itu satu-satunya kunci.
	"""
	members = {communication}

	# 1. rantai balasan
	frontier = {communication}
	while frontier and len(members) < CONVERSATION_LIMIT:
		parents = set(
			frappe.get_all("Communication", filters={"name": ["in", list(frontier)]}, pluck="in_reply_to")
		)
		children = set(
			frappe.get_all("Communication", filters={"in_reply_to": ["in", list(frontier)]}, pluck="name")
		)
		frontier = {n for n in parents | children if n} - members
		members |= frontier

	# 2. subjek + pihak luar yang sama
	anchor = frappe.db.get_value(
		"Communication",
		communication,
		["subject", "sender", "recipients", "cc", "communication_date"],
		as_dict=True,
	)
	subject = normalize_subject(anchor and anchor.subject)
	if not subject or not anchor.communication_date:
		return members

	own = {e.lower() for e in frappe.get_all("Email Account", pluck="email_id") if e}
	people = _outside_parties(anchor, own)
	if not people:
		return members

	like = "%" + subject.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
	candidates = frappe.db.sql(
		"""select name, subject, sender, recipients, cc from `tabCommunication`
		where communication_medium = 'Email' and subject like %s
			and communication_date between %s and %s
		limit %s""",
		(
			like,
			add_days(anchor.communication_date, -CONVERSATION_DAYS),
			add_days(anchor.communication_date, CONVERSATION_DAYS),
			CONVERSATION_LIMIT,
		),
		as_dict=True,
	)
	for row in candidates:
		if normalize_subject(row.subject) == subject and _outside_parties(row, own) & people:
			members.add(row.name)

	return members


def _outside_parties(row, own: set) -> set:
	# Alamat mailbox sendiri tidak dihitung: kalau dihitung, semua email akun ini "sepihak".
	addresses = getaddresses([row.sender or "", row.recipients or "", row.cc or ""])
	return {address.lower() for _name, address in addresses if address and address.lower() not in own}


def inherit_conversation_links(doc, method=None):
	"""Hook Communication.after_insert: email baru di percakapan yang sudah tertaut ke
	transaksi ikut tertaut ke transaksi yang sama.

	Pewarisan bawaan Frappe cuma menyalin reference UTAMA email yang dibalas, dan sering
	isinya "Communication <induk>", bukan transaksinya -- jadi balasan tidak pernah sampai ke
	timeline Expense Note/Packing List-nya.

	Ditulis langsung ke baris timeline link (db_insert) dan lewat db_set, bukan doc.save():
	dokumen ini sedang di tengah proses simpan, dan pemanggilnya (InboundMail, make) masih
	akan menyimpannya lagi -- save di sini membuat `modified` berubah di bawah kakinya.
	"""
	if doc.communication_medium != "Email" or doc.communication_type != "Communication":
		return

	wanted = []
	for member in conversation(doc.name) - {doc.name}:
		for link in _links_of(member):
			if link not in wanted:
				wanted.append(link)
	if not wanted:
		return

	have = {(r.link_doctype, r.link_name) for r in doc.timeline_links}
	for link in wanted:
		pair = (link["doctype"], link["name"])
		if pair == (doc.reference_doctype, doc.reference_name) or pair in have:
			continue
		if not doc.reference_doctype or not doc.reference_name:
			doc.db_set({"reference_doctype": pair[0], "reference_name": pair[1]}, update_modified=False)
			continue
		row = doc.append("timeline_links", {"link_doctype": pair[0], "link_name": pair[1]})
		row.db_insert()
		have.add(pair)


def _linked_names(doctype: str, name: str) -> set:
	"""Communication yang tertaut ke satu dokumen: lewat reference utama ATAU timeline link."""
	by_reference = frappe.get_all(
		"Communication",
		filters={"reference_doctype": doctype, "reference_name": name, "communication_medium": "Email"},
		pluck="name",
	)
	by_link = frappe.get_all(
		"Communication Link",
		filters={"link_doctype": doctype, "link_name": name, "parenttype": "Communication"},
		pluck="parent",
	)
	return set(by_reference) | set(by_link)


@frappe.whitelist()
def linked_emails(doctype: str, name: str) -> list[dict]:
	"""Daftar email tab Email di form transaksi, terbaru di atas.

	Izinnya dari DOKUMEN-nya, bukan dari Communication: yang boleh membuka Expense Note
	boleh membaca email yang tertaut ke Expense Note itu -- dan hanya email itu.

	Dipanggil setiap form desk dimuat ulang (section Email, public/js/linked_mail.js), jadi
	doctype yang bukan transaksi langsung dijawab kosong tanpa memuat dokumennya.
	"""
	if doctype not in _transaction_doctypes():
		return []

	# Cek tautan dulu (dua query ringan), baru izin: memuat dokumen utuh untuk cek izin
	# (Sales Invoice beserta item & pajaknya) makan ratusan ms, padahal kebanyakan dokumen
	# tidak punya email. Jawaban kosong tidak membocorkan apa pun.
	names = _linked_names(doctype, name)
	if not names:
		return []

	frappe.get_doc(doctype, name).check_permission("read")

	return frappe.get_all(
		"Communication",
		filters={"name": ["in", list(names)], "communication_medium": "Email"},
		fields=[
			"name",
			"subject",
			"sender",
			"sender_full_name",
			"recipients",
			"communication_date",
			"sent_or_received",
			"has_attachment",
			"text_content",
		],
		order_by="communication_date desc",
		limit_page_length=200,
	)


@frappe.whitelist()
def linked_email(doctype: str, name: str, communication: str) -> dict:
	"""Isi satu email untuk panel baca tab Email -- hanya kalau email itu tertaut ke dokumen ini."""
	frappe.get_doc(doctype, name).check_permission("read")
	if communication not in _linked_names(doctype, name):
		frappe.throw(_("This email is not linked to {0} {1}.").format(_(doctype), name), frappe.PermissionError)

	mail = frappe.db.get_value(
		"Communication",
		communication,
		[
			"name",
			"subject",
			"sender",
			"sender_full_name",
			"recipients",
			"cc",
			"communication_date",
			"sent_or_received",
			"content",
			"text_content",
			# Balas dari tab Email di Mailbox mode laptop: suratnya dicari di mailbox lewat ini.
			"message_id",
		],
		as_dict=True,
	)
	mail.attachments = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Communication", "attached_to_name": communication},
		fields=["file_name", "file_url"],
		limit_page_length=50,
	)
	return mail


@frappe.whitelist()
def unlink_transaction(communication: str, doctype: str, name: str) -> list[dict]:
	"""Lepas transaksi dari email ini berikut seluruh percakapannya -- kebalikan link_transaction,
	dengan aturan izin yang sama (boleh membaca transaksinya)."""
	# Transaksi yang sudah dihapus tetap boleh dilepas dari emailnya.
	if frappe.db.exists(doctype, name):
		frappe.get_doc(doctype, name).check_permission("read")

	for member in conversation(communication):
		doc = frappe.get_doc("Communication", member)
		if doc.reference_doctype == doctype and doc.reference_name == name:
			doc.reference_doctype = doc.reference_name = None
		doc.remove_link(doctype, name)
		doc.save(ignore_permissions=True)

	return _links_of(communication)


# ---------------------------------------------------------------- tarik ulang


@frappe.whitelist()
def backfill(email_account: str) -> str:
	"""Tarik surat lama yang belum ada di ERPNext, dari semua folder akun, secara senyap."""
	frappe.only_for("System Manager")
	if not email_account:
		frappe.throw(_("Select an email account first."))

	frappe.enqueue(
		_backfill,
		queue="long",
		timeout=4 * 60 * 60,
		job_id=f"mailbox-backfill:{email_account}",
		deduplicate=True,
		email_account=email_account,
	)
	return email_account


def _backfill(email_account: str):
	account = frappe.get_doc("Email Account", email_account)
	server = account.get_incoming_server(in_receive=True, email_sync_rule="UNSEEN")
	# Dibaca hook assistant (on_communication_insert): surat lama bukan email baru masuk.
	frappe.flags.cmi_mail_backfill = True
	counts = {}

	try:
		for folder in account.imap_folder:
			if not server.select_imap_folder(folder.folder_name):
				continue

			_seed_uidvalidity(server, folder)
			server.settings["uid_validity"] = folder.uidvalidity

			_typ, data = server.imap.uid("search", None, "ALL")
			on_server = [uid.decode() for uid in (data[0] or b"").split()]
			already = {
				str(uid)
				for uid in frappe.get_all(
					"Communication",
					filters={
						"email_account": account.name,
						"imap_folder": folder.folder_name,
						"uid": [">", 0],
					},
					pluck="uid",
				)
			}
			todo = [uid for uid in on_server if uid not in already]
			counts[folder.folder_name] = 0

			for start in range(0, len(todo), BATCH):
				server.settings["email_sync_rule"] = "UID " + ",".join(todo[start : start + BATCH])
				messages = server.get_messages(folder=f'"{folder.folder_name}"') or {}

				for mail in _to_inbound(account, messages, folder, keep_seen=True):
					try:
						# Sengaja TANPA send_email / auto reply seperti di receive():
						# ini surat lama, bukan email yang baru datang.
						mail.process()
						frappe.db.commit()
						counts[folder.folder_name] += 1
					except SentEmailInInboxError:
						frappe.db.rollback()
					except Exception:
						frappe.db.rollback()
						account.log_error(title=f"Mailbox backfill {folder.folder_name} uid {mail.uid}")
	finally:
		frappe.flags.cmi_mail_backfill = False
		server.logout()

	frappe.logger("mailbox").info(f"backfill {email_account}: {counts}")
	return counts

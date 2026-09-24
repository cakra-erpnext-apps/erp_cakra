"""Cek sinkron banyak folder IMAP. Tidak menyentuh server mail, tidak menulis data.

    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console
    >>> from erpnext_custom.test_mail_folders import run; run()

Yang dijaga (lihat docstring mail_inbox.py):
- titik awal dihitung PER FOLDER, bukan dari UID tertinggi seluruh akun;
- folder yang belum pernah diisi mulai dari ujungnya, bukan dari UID 1 -- surat lamanya
  masuk lewat backfill yang senyap, bukan lewat penarik rutin yang memicu notifikasi;
- asal folder ikut tercatat ke Communication.imap_folder.
"""

import frappe

from erpnext_custom.mail_inbox import CMIInboundMail, _fetch, normalize_subject, sync_rule, sync_start


class FakeServer:
	"""Cukup untuk _fetch: server menjawab `UID N:*` dengan surat terakhirnya (RFC 3501)."""

	def __init__(self, uids, reindexed=False):
		self.uids = uids
		self.reindexed = reindexed
		self.downloaded = []

	def get_new_mails(self, folder):
		self.uid_reindexed = self.reindexed
		return list(self.uids)

	def retrieve_message(self, uid, msg_num, folder):
		self.downloaded.append(uid)
		self.latest_messages.append(b"raw " + uid)

RAW = (
	b"From: Andi <andi@contoh.com>\r\n"
	b"To: admin@cakraindo.com\r\n"
	b"Subject: uji folder\r\n"
	b"Message-ID: <uji-folder@contoh.com>\r\n"
	b"Date: Wed, 23 Sep 2026 10:00:00 +0700\r\n"
	b"\r\n"
	b"isi\r\n"
)


def run():
	# folder yang sudah berisi: lanjut dari surat terakhirnya sendiri
	assert sync_rule("ALL", 48, 60) == "UID 49:*", sync_rule("ALL", 48, 60)

	# folder belum pernah diisi: mulai dari ujung, bukan dari surat pertama
	assert sync_rule("ALL", None, 60) == "UID 60:*", sync_rule("ALL", None, 60)
	assert sync_rule("ALL", 0, 60) == "UID 60:*", "uid -1/0 hasil reset Frappe dianggap belum berisi"

	# tanpa informasi apa pun jangan sampai aturan kosong
	assert sync_rule("ALL", None, None) == "UID 1:*"

	# mode UNSEEN tetap apa adanya -- pencarian UNSEEN sudah per folder
	assert sync_rule("UNSEEN", 48, 60) == "UNSEEN"
	assert sync_rule("", 48, 60) == "UNSEEN"

	assert sync_start(48, 60) == 49 and sync_start(None, 60) == 60

	# Belum ada surat baru: server tetap menjawab surat terakhirnya (UID 48). Surat itu
	# TIDAK boleh diunduh -- dulu diunduh utuh di setiap tarikan, di setiap folder.
	idle = FakeServer([b"48"])
	out = _fetch(idle, "Notification", start=49)
	assert idle.downloaded == [], idle.downloaded
	assert out["latest_messages"] == [] and out["uid_list"] == []

	# Ada surat baru: yang baru diunduh, uid_list sejajar dengan latest_messages.
	fresh = FakeServer([b"49", b"50"])
	out = _fetch(fresh, "Notification", start=49)
	assert fresh.downloaded == [b"49", b"50"], fresh.downloaded
	assert out["uid_list"] == [b"49", b"50"] and len(out["latest_messages"]) == 2

	# Frappe menimpa aturannya sendiri (UIDVALIDITY berubah): hasilnya dipakai apa adanya.
	reset = FakeServer([b"3", b"4"], reindexed=True)
	_fetch(reset, "Notification", start=49)
	assert reset.downloaded == [b"3", b"4"], reset.downloaded

	account = frappe.get_doc("Email Account", {"enable_incoming": 1})
	mail = CMIInboundMail(RAW, account, "7", None, "Communication", imap_folder="Notification")
	data = mail.as_dict()
	assert data["imap_folder"] == "Notification", data.get("imap_folder")
	assert data["uid"] == "7" and data["subject"] == "uji folder", data
	assert data["sent_or_received"] == "Received"

	# Surat dari folder Terkirim dicatat sebagai kiriman, bukan email masuk.
	sent = CMIInboundMail(RAW, account, "8", None, "Communication", imap_folder="Sent Items", is_sent=True)
	data = sent.as_dict()
	assert data["sent_or_received"] == "Sent" and data["imap_folder"] == "Sent Items", data

	# Satu percakapan = subjek tanpa awalan balas/teruskan (dipakai conversation()).
	assert normalize_subject("RE: Fwd: Re: Invoice PL-01") == "invoice pl-01"
	assert normalize_subject("Re[2]: Hallo") == "hallo"
	assert normalize_subject("AW: WG: Test") == "test"
	assert normalize_subject("Rencana: kirim besok") == "rencana: kirim besok", "kata biasa ber-titik-dua jangan terpotong"
	assert normalize_subject(None) == ""

	print("OK mail_folders: titik awal per folder, unduhan idle, penandaan folder & Terkirim, subjek percakapan benar")

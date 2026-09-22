"""Cek penyisipan Bcc untuk kirim lewat Microsoft Graph. Tidak menyentuh jaringan.

    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console
    >>> from erpnext_custom.test_graph_mail import run; run()

Yang diuji `_append_bcc`: Graph tidak punya amplop SMTP, jadi penerima yang tidak
tercantum di header To/Cc HARUS dijadikan header Bcc atau dia tidak menerima apa pun.
Penyisipannya tekstual supaya lampiran yang sudah terbentuk tidak ikut dibangun ulang --
itu juga yang bisa diam-diam rusak, makanya badan pesan ikut dibandingkan di sini.
"""

from types import SimpleNamespace

from erpnext_custom.graph_mail import _append_bcc


def _queue(*recipients):
	return SimpleNamespace(recipients=[SimpleNamespace(recipient=r) for r in recipients])


def _mime(eol=b"\r\n", body=b"--batas\r\nisi lampiran\r\n--batas--"):
	head = eol.join(
		[
			b"From: admin@cakraindo.com",
			b"To: andi@contoh.com",
			b"Cc: budi@contoh.com",
			b"Subject: uji",
			b'Content-Type: multipart/mixed; boundary="batas"',
		]
	)
	return head + eol + eol + body


def run():
	body = b"--batas\r\nisi lampiran\r\n--batas--"

	# penerima tersembunyi -> jadi header Bcc, badan pesan tidak berubah
	out = _append_bcc(_mime(), _queue("andi@contoh.com", "budi@contoh.com", "rahasia@contoh.com"))
	assert b"Bcc: rahasia@contoh.com" in out, "penerima bcc tidak disisipkan"
	assert out.endswith(body), "badan pesan ikut berubah"
	assert out.count(b"\r\n\r\n") == 1, "batas header/badan rusak"

	# semua penerima sudah ada di header -> byte-nya harus sama persis
	same = _mime()
	assert _append_bcc(same, _queue("andi@contoh.com", "budi@contoh.com")) == same, "pesan diubah tanpa perlu"

	# perbandingan alamat tidak boleh peka huruf besar-kecil
	assert _append_bcc(_mime(), _queue("ANDI@contoh.com")) == _mime(), "huruf besar dianggap penerima lain"

	# pesan berakhiran LF saja tetap tertangani
	lf = _append_bcc(_mime(eol=b"\n"), _queue("rahasia@contoh.com"))
	assert b"Bcc: rahasia@contoh.com" in lf, "pemisah baris LF tidak tertangani"
	assert lf.endswith(body), "badan pesan versi LF ikut berubah"

	# beberapa penerima tersembunyi digabung dalam satu header
	dua = _append_bcc(_mime(), _queue("a@contoh.com", "b@contoh.com"))
	assert b"Bcc: a@contoh.com, b@contoh.com" in dua, "bcc jamak tidak digabung"

	# Menyimpan Token Cache dari sini pernah melumpuhkan IMAP berjam-jam: Frappe
	# menghitung kedaluwarsa token dari `modified` + `expires_in`, jadi menyentuh
	# dokumen itu membuatnya mengira token mati masih segar dan berhenti menyegarkan.
	import frappe

	source = frappe.read_file(frappe.get_app_path("erpnext_custom", "graph_mail.py"))
	assert "token_cache.save(" not in source, "graph_mail menulis ke Token Cache lagi"
	assert ".db_set(" not in source, "graph_mail menulis ke Token Cache lagi"

	print("OK graph_mail: penyisipan Bcc benar, Token Cache tidak disentuh")

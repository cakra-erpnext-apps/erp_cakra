"""Penjaga email masuk.

Satu email cacat tidak boleh menjatuhkan seluruh penarikan: `EmailAccount.receive`
memproses satu batch dalam satu transaksi, jadi kalau satu lampiran ditolak, email
lain di batch yang sama ikut tidak masuk dan penarikan berikutnya mengulangi kegagalan
yang sama terus-menerus.

Pemicu nyata: nama lampiran lebih panjang dari kolom `File.file_name` (140 karakter),
mis. kiriman nego yang nama berkasnya memuat rute lengkap. Frappe melempar
`CharacterLengthExceededError` saat menyimpan File-nya.
"""

import os

import frappe
from frappe import _

FILE_NAME_LIMIT = 140


def trim_file_name(doc, method=None):
	"""Potong nama berkas yang kepanjangan, ekstensinya dipertahankan."""
	name = doc.file_name or ""
	if len(name) <= FILE_NAME_LIMIT:
		return

	root, ext = os.path.splitext(name)
	# Ekstensi dipertahankan karena itu yang menentukan berkas ini dibuka pakai apa;
	# yang dibuang bagian tengah-akhir nama yang cuma keterangan.
	doc.file_name = root[: FILE_NAME_LIMIT - len(ext)] + ext


@frappe.whitelist()
def pull_now(email_account: str) -> str:
	"""Tarik email sekarang juga. Dipanggil tombol Tarik Email di halaman Mailbox.

	Penarikan dilempar ke latar: satu batch bisa memakan menit, jauh melewati umur
	permintaan HTTP. Hasilnya diberitahukan lewat realtime, bukan lewat balasan ini.
	"""
	frappe.has_permission("Email Account", "read", doc=email_account, throw=True)

	if not frappe.db.get_value("Email Account", email_account, "enable_incoming"):
		frappe.throw(_("{0} tidak menerima email masuk.").format(email_account))

	# deduplicate: menekan tombolnya berkali-kali tidak menumpuk penarikan yang sama --
	# dua sesi IMAP serentak ke mailbox yang sama bikin salah satunya ditolak server.
	frappe.enqueue(
		_pull_and_notify,
		queue="short",
		timeout=900,
		job_id=f"mailbox-pull:{email_account}",
		deduplicate=True,
		email_account=email_account,
		user=frappe.session.user,
	)

	return email_account


def _pull_and_notify(email_account: str, user: str):
	sebelum = frappe.db.count("Communication", {"email_account": email_account})

	try:
		frappe.get_doc("Email Account", email_account).receive()
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		frappe.publish_realtime(
			"cmi_mailbox_synced", {"email_account": email_account, "error": str(e)[:200]}, user=user
		)
		raise

	sesudah = frappe.db.count("Communication", {"email_account": email_account})
	frappe.publish_realtime(
		"cmi_mailbox_synced", {"email_account": email_account, "baru": sesudah - sebelum}, user=user
	)

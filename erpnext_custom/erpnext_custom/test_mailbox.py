"""Cek halaman Mailbox masih punya pijakan datanya. Tidak mengubah data.

    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console
    >>> from erpnext_custom.test_mailbox import run; run()

Halaman Mailbox (page/mailbox/mailbox.js) tidak punya tabel sendiri: folder-nya cuma
kombinasi filter Communication. Jadi yang bisa diam-diam rusak adalah nama fieldnya --
sekali Frappe mengganti/menghapus salah satunya, panel tengah jadi kosong tanpa error
yang kelihatan. Tes ini menjalankan query yang sama persis dengan halaman itu.
"""

import frappe

# sama dengan fields[] di mailbox.js load_list()
LIST_FIELDS = [
	"name",
	"subject",
	"sender",
	"sender_full_name",
	"recipients",
	"communication_date",
	"seen",
	"has_attachment",
	"text_content",
]


def _filters(folder, account):
	"""Cerminan get_filters() di mailbox.js -- ubah di sana, ubah juga di sini."""
	filters = [
		["communication_type", "=", "Communication"],
		["communication_medium", "=", "Email"],
		["email_account", "=", account],
	]
	if folder in ("Spam", "Trash"):
		filters.append(["email_status", "=", folder])
	else:
		filters.append(["sent_or_received", "=", "Received" if folder == "Inbox" else "Sent"])
		filters.append(["email_status", "not in", ["Spam", "Trash"]])
	return filters


def run():
	meta = frappe.get_meta("Communication")
	for field in LIST_FIELDS:
		assert field == "name" or meta.has_field(field), f"Communication kehilangan field {field}"

	account = frappe.db.get_value("Email Account", {"enable_incoming": 1}, "name")
	assert account, "tidak ada Email Account incoming di site ini"

	for folder in ("Inbox", "Sent", "Spam", "Trash"):
		rows = frappe.get_all(
			"Communication",
			filters=_filters(folder, account),
			fields=LIST_FIELDS,
			order_by="communication_date desc",
			limit_page_length=5,
		)
		assert isinstance(rows, list), f"query folder {folder} gagal"

	# Pencarian memakai or_filters. Mengirim or_filters kosong BUKAN hal netral: Frappe
	# membaca string di posisi itu sebagai nama dokumen, jadi query-nya jadi `name = ''`
	# dan daftarnya kosong tanpa error. mailbox.js karena itu cuma mengirim kuncinya
	# kalau ada kata kunci -- dijaga di sini supaya tidak balik lagi.
	assert (
		frappe.get_list(
			"Communication", fields=["name"], filters=[["email_account", "=", account]], or_filters="", limit_page_length=5
		)
		== []
	), "jebakan or_filters kosong sudah berubah, periksa lagi mailbox.js"

	source = frappe.read_file(
		frappe.get_app_path("erpnext_custom", "erpnext_custom", "page", "mailbox", "mailbox.js")
	)
	assert "if (or_filters) args.or_filters = or_filters;" in source, "mailbox.js kirim or_filters tanpa syarat"

	assert frappe.db.exists("Page", "mailbox"), "Page mailbox belum ter-import (bench migrate)"

	# mailbox cuma muncul di pemilih akun kalau usernya punya baris User Email
	inbox_users = frappe.get_all("User Email", filters={"email_account": account}, pluck="parent")
	assert inbox_users, f"{account} belum terpasang di tab Email User mana pun"

	print(f"OK mailbox: akun {account}, terpasang untuk {', '.join(inbox_users)}")

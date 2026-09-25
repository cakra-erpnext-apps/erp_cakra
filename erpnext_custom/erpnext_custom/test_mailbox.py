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
	elif folder == "Sent":
		filters.append(["sent_or_received", "=", "Sent"])
		filters.append(["email_status", "not in", ["Spam", "Trash"]])
	else:
		# folder IMAP (INBOX atau folder buatan pemilik mailbox)
		filters.append(["sent_or_received", "=", "Received"])
		filters.append(["imap_folder", "=", folder])
		filters.append(["email_status", "not in", ["Spam", "Trash"]])
	return filters


def run():
	meta = frappe.get_meta("Communication")
	for field in LIST_FIELDS:
		assert field == "name" or meta.has_field(field), f"Communication kehilangan field {field}"

	account = frappe.db.get_value("Email Account", {"enable_incoming": 1}, "name")
	assert account, "tidak ada Email Account incoming di site ini"

	imap_folders = [r.folder_name for r in frappe.get_doc("Email Account", account).imap_folder]
	for folder in [*imap_folders, "Sent", "Spam", "Trash"]:
		rows = frappe.get_all(
			"Communication",
			filters=_filters(folder, account),
			fields=LIST_FIELDS,
			order_by="communication_date desc",
			limit_page_length=5,
		)
		assert isinstance(rows, list), f"query folder {folder} gagal"

	# Kotak Masuk hanya menampilkan surat yang tercatat asal foldernya. Surat hasil TARIKAN
	# IMAP (uid > 0) tanpa imap_folder berarti ada jalur tarik yang melewati mail_inbox --
	# tak terlihat di folder mana pun. Email yang disimpan lewat add-in Outlook memang tidak
	# punya folder IMAP (uid -1) dan cukup tampil di timeline transaksinya.
	lost = frappe.db.count(
		"Communication",
		{
			"email_account": account,
			"sent_or_received": "Received",
			"uid": [">", 0],
			"imap_folder": ["is", "not set"],
		},
	)
	assert not lost, f"{lost} surat masuk tanpa imap_folder, tidak tampil di folder mana pun"

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

	# Halaman Mailbox terbuka untuk role Mailbox User, bukan cuma System Manager.
	from erpnext_custom.mail_inbox import MAILBOX_ROLE

	assert frappe.db.exists("Role", MAILBOX_ROLE), f"role {MAILBOX_ROLE} belum dibuat (after_migrate)"
	page_roles = [r.role for r in frappe.get_doc("Page", "mailbox").roles]
	assert MAILBOX_ROLE in page_roles, f"Page mailbox belum mengizinkan {MAILBOX_ROLE}: {page_roles}"

	_check_link_rule()

	print(f"OK mailbox: akun {account}, terpasang untuk {', '.join(inbox_users)}; role dan aturan tautan benar")


def _check_link_rule():
	"""Aturan tautan: siapa pun yang boleh MEMBACA transaksinya boleh menautkan/melepas, tanpa
	izin tulis Communication (yang hampir tidak dimiliki siapa pun). Menulis, lalu rollback."""
	from erpnext_custom.mail_inbox import get_links, link_transaction, unlink_transaction
	from erpnext_custom.quick_search import transaction_doctypes

	users = [
		u
		for u in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name")
		if u not in ("Administrator", "Guest") and "System Manager" not in frappe.get_roles(u)
	]
	assert users, "butuh satu user desk bukan System Manager untuk tes aturan tautan"
	user = users[0]
	email = frappe.db.get_value("Communication", {"communication_medium": "Email"}, "name", order_by="creation desc")

	frappe.set_user(user)
	try:
		readable = blocked = None
		for doctype in transaction_doctypes():
			name = frappe.db.get_value(doctype, {}, "name")
			if not name:
				continue
			if frappe.has_permission(doctype, "read", doc=name):
				readable = readable or (doctype, name)
			else:
				blocked = blocked or (doctype, name)
			if readable and blocked:
				break
		assert readable and blocked, f"{user}: tidak ketemu pasangan transaksi boleh/tidak boleh dibaca"
		assert not frappe.has_permission("Communication", "write"), f"{user} ternyata punya izin tulis Communication"

		links = link_transaction(email, *readable)
		assert {"doctype": readable[0], "name": readable[1]} in links, f"{user} gagal menautkan {readable}"
		assert all(frappe.has_permission(l["doctype"], "read", doc=l["name"]) for l in get_links(email))

		try:
			link_transaction(email, *blocked)
			raise AssertionError(f"{user} bisa menautkan {blocked} yang tidak boleh dibacanya")
		except frappe.PermissionError:
			pass

		unlink_transaction(email, *readable)
		assert {"doctype": readable[0], "name": readable[1]} not in get_links(email)
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()

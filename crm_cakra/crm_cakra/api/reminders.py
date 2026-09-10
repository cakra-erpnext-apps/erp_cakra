"""Pengingat harian CRM (§29 Alur CRM).

Dua aturan saja, dan keduanya menunjuk dokumen yang bisa dibuka orang:

1. Penawaran yang belum diputuskan dan diam lebih dari N hari.
2. Inquiry yang lewat Expected Closure Date tapi belum Won/Lost.

"Kapan terakhir diingatkan" TIDAK disimpan sebagai field di dokumen, melainkan
dibaca balik dari `CRM Notification` yang sudah tercatat. Alasannya bukan hemat
field: menulis stempel ke dokumen ikut menaikkan `modified`, dan `modified` itulah
yang dipakai aturan 1 untuk mengukur "diam" -- jadi pengingat akan menghapus
sebab dirinya sendiri dan tidak ada dokumen yang pernah diam lagi.

Sengaja belum ada: pengingat akun dormant. Bukan karena querinya berat, tapi
karena notifikasi CRM hanya bisa menaut ke Lead/Inquiry/Quotation
(lihat `route_name` di api/notifications.py) -- pengingat akun akan lahir dengan
tautan yang salah arah.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

# Quotation yang sudah selesai urusannya. Sengaja daftar YANG FINAL, bukan daftar
# yang terbuka: state baru yang belum terpikir akan ikut diingatkan, bukan diam-diam
# dilewati.
QUOTATION_FINAL_STATES = ("Win", "Lose", "Converted")

REMINDER_TYPE = "Reminder"


def send_reminders():
	"""Dipanggil scheduler `daily`. Idempoten: aman dijalankan berkali-kali."""
	settings = frappe.get_single("FCRM Settings")
	if not settings.get("enable_reminders"):
		return

	repeat_days = frappe.utils.cint(settings.get("reminder_repeat_days"))
	idle_days = frappe.utils.cint(settings.get("quotation_idle_days")) or 3

	sent = 0
	sent += _remind_idle_quotations(idle_days, repeat_days)
	sent += _remind_overdue_inquiries(repeat_days)
	if sent:
		frappe.db.commit()
	return sent


def _remind_idle_quotations(idle_days: int, repeat_days: int) -> int:
	cutoff = add_days(now_datetime(), -idle_days)
	rows = frappe.get_all(
		"CRM Quotation",
		filters={
			"state": ["not in", QUOTATION_FINAL_STATES],
			"is_void": 0,
			"modified": ["<", cutoff],
		},
		fields=["name", "owner", "_assign", "state", "account", "modified"],
	)
	if not rows:
		return 0

	last = _last_reminded("CRM Quotation")
	sent = 0
	for row in rows:
		if not _due(last.get(row.name), repeat_days):
			continue
		days = (now_datetime() - row.modified).days
		text = _("Penawaran <b>{0}</b> ({1}) belum tersentuh {2} hari.").format(
			row.name, row.state, days
		)
		sent += _notify(_recipients(row), "CRM Quotation", row.name, text)
	return sent


def _remind_overdue_inquiries(repeat_days: int) -> int:
	final_statuses = [
		s.name
		for s in frappe.get_all(
			"CRM Inquiry Status", filters={"type": ["in", ("Won", "Lost")]}, fields=["name"]
		)
	]
	rows = frappe.get_all(
		"CRM Inquiry",
		filters={
			"is_void": 0,
			"expected_closure_date": ["<", frappe.utils.today()],
			"status": ["not in", final_statuses] if final_statuses else ["is", "set"],
		},
		fields=["name", "owner", "inquiry_owner", "_assign", "status", "expected_closure_date"],
	)
	if not rows:
		return 0

	last = _last_reminded("CRM Inquiry")
	sent = 0
	for row in rows:
		if not _due(last.get(row.name), repeat_days):
			continue
		text = _("Inquiry <b>{0}</b> lewat target tutup {1} dan masih {2}.").format(
			row.name, frappe.utils.formatdate(row.expected_closure_date), row.status
		)
		sent += _notify(_recipients(row, "inquiry_owner"), "CRM Inquiry", row.name, text)
	return sent


def _last_reminded(doctype: str) -> dict:
	"""Kapan tiap dokumen terakhir diingatkan, dari notifikasi yang sudah tercatat."""
	Notification = frappe.qb.DocType("CRM Notification")
	rows = (
		frappe.qb.from_(Notification)
		.select(
			Notification.notification_type_doc,
			frappe.qb.functions("MAX", Notification.creation).as_("last"),
		)
		.where(
			(Notification.notification_type_doctype == doctype)
			& (Notification.type == REMINDER_TYPE)
		)
		.groupby(Notification.notification_type_doc)
	).run(as_dict=True)
	return {r.notification_type_doc: r.last for r in rows}


def _due(last, repeat_days: int) -> bool:
	if not last:
		return True
	return last < add_days(now_datetime(), -repeat_days)


def _recipients(row, owner_field: str | None = None) -> list[str]:
	"""Yang di-assign duluan; kalau tidak ada, pemilik dokumen."""
	users = []
	if row.get("_assign"):
		try:
			users = [u for u in json.loads(row["_assign"]) if u]
		except (ValueError, TypeError):
			users = []
	if not users and owner_field:
		users = [row.get(owner_field)] if row.get(owner_field) else []
	if not users:
		users = [row.get("owner")] if row.get("owner") else []
	# Administrator bukan orang yang menindaklanjuti apa pun.
	return [u for u in dict.fromkeys(users) if u and u != "Administrator"]


def _notify(users: list[str], doctype: str, name: str, text: str) -> int:
	sent = 0
	for user in users:
		if not frappe.db.exists("User", {"name": user, "enabled": 1}):
			continue
		frappe.get_doc(
			{
				"doctype": "CRM Notification",
				"from_user": "Administrator",
				"to_user": user,
				"type": REMINDER_TYPE,
				"notification_text": text,
				"notification_type_doctype": doctype,
				"notification_type_doc": name,
				"reference_doctype": doctype,
				"reference_name": name,
			}
		).insert(ignore_permissions=True)
		sent += 1
	return sent

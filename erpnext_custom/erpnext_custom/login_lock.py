# Login gagal beruntun dikunci Frappe di redis lewat dua hash, "login_failed_count" dan
# "login_failed_time" (frappe/auth.py LoginAttemptTracker). Tiap percobaan gagal dicatat
# DUA kali: sekali atas nama user, sekali atas IP asal. Karyawan satu kantor umumnya
# keluar lewat satu IP publik, jadi salah ketik beramai-ramai bisa mengunci IP-nya
# walaupun tiap usernya sendiri masih jauh dari batas.
#
# Frappe tidak punya cara membuka kunci sebelum "Allow Login After Fail" habis, padahal
# add_success_attempt() cuma menghapus dua entri itu. Di sini dihapus manual, untuk
# user-nya sekaligus IP yang dipakainya gagal login belakangan.

import frappe
from frappe import _

HASHES = ("login_failed_count", "login_failed_time")


def _clear(key: str) -> bool:
	"""Hapus catatan gagal satu key. True kalau key-nya memang sedang tercatat."""
	locked = any(frappe.cache.hget(h, key) for h in HASHES)
	for h in HASHES:
		frappe.cache.hdel(h, key)
	return locked


@frappe.whitelist()
def unlock(user: str) -> list[str]:
	"""Buka kunci login user + IP bekas percobaan gagalnya. Balikan: key yang tadi terkunci."""
	frappe.only_for("System Manager")
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} tidak ada").format(user))

	cleared = [user] if _clear(user) else []

	ips = frappe.get_all(
		"Activity Log",
		filters={"user": user, "status": "Failed", "operation": "Login"},
		pluck="ip_address",
		order_by="creation desc",
		limit=20,
	)
	# dict.fromkeys = unik tapi urutannya tetap (IP terbaru duluan).
	for ip in dict.fromkeys(ip for ip in ips if ip):
		if _clear(ip):
			cleared.append(ip)

	return cleared

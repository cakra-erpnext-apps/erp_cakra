"""Cek tombol Reset Kunci Login: user yang terkunci gagal login jadi bebas lagi,
berikut IP bekas percobaannya. Data uji dibersihkan sendiri.

    bench --site erp.localhost console
    >>> from erpnext_custom.test_login_lock import run; run()
"""

import frappe
from frappe.auth import get_login_attempt_tracker as tracker

from erpnext_custom.login_lock import unlock

IP = "203.0.113.99"  # blok TEST-NET-3, tidak akan bentrok dengan IP sungguhan


def locked(key):
	return not tracker(key, raise_locked_exception=False).is_user_allowed()


def run(user="Administrator"):
	# Activity Log menimpa ip_address dengan IP request (set_ip_address), jadi
	# jejak uji ini IP-nya dipaksa lewat db.
	log = frappe.get_doc(
		dict(doctype="Activity Log", subject="tes kunci login", user=user, operation="Login", status="Failed")
	).insert(ignore_permissions=True)
	frappe.db.set_value("Activity Log", log.name, "ip_address", IP)

	try:
		# Frappe mencatat tiap kegagalan dua kali: atas nama user, dan atas IP asal.
		for key in (user, IP):
			t = tracker(key, raise_locked_exception=False)
			for _ in range(tracker(key, raise_locked_exception=False).max_failed_logins + 1):
				t.add_failure_attempt()
		assert locked(user) and locked(IP), "gagal mengunci, tes tidak sahih"

		cleared = unlock(user)
		assert not locked(user), "user masih terkunci"
		assert not locked(IP), f"IP {IP} masih terkunci"
		assert set(cleared) == {user, IP}, f"yang dilaporkan terbuka tidak cocok: {cleared}"

		assert unlock(user) == [], "dijalankan ulang harusnya kosong, bukan mengaku membuka kunci"
		print("OK: kunci login user + IP-nya terbuka, aman diulang")
	finally:
		frappe.delete_doc("Activity Log", log.name, ignore_permissions=True, force=True)
		frappe.db.commit()

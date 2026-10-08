"""Cek Tugas Saya: task yang dioper muncul di penerima (dengan siapa yang mengoper) dan di
"menunggu orang lain" milik yang mengoper; temuan pemeriksaan punya kalimat langkah berikutnya.

bench --site <situs> execute assistant.assistant.test_my_tasks.run   (rollback)
"""

import frappe

from assistant.assistant import orchestrator as orc


def run():
	frappe.set_user("Administrator")
	try:
		a, b = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User",
		                                       "name": ["not in", ["Administrator", "Guest"]]}, pluck="name", limit=2)
		# task manual untuk A, lalu Administrator mengopernya ke B
		name = orc.create_manual("uji tugas saya", assign_to=a)
		orc.reassign(name, b)

		frappe.set_user(b)
		mine = orc.my_tasks()
		row = next(r for r in mine["todo"] if r["name"] == name)
		assert row["handed_by"] and row["action"] == "finish" and "Selesai" in row["step"], row
		assert orc.my_task_count() == len(mine["todo"])

		frappe.set_user(a)
		assert not any(r["name"] == name for r in orc.my_tasks()["todo"]), "A tidak lagi memegang task itu"

		frappe.set_user("Administrator")
		waiting = orc.my_tasks()["waiting"]
		assert any(r["name"] == name and "oper" in r["step"] for r in waiting), waiting

		# temuan pemeriksaan milik B: langkahnya "Putuskan"
		t = frappe.get_doc({"doctype": "Agent Task", "subject": "uji temuan", "source": "Audit", "status": "Open",
		                    "assigned_to": b, "dedupe_key": "test:my_tasks:audit", "shadow": 0}).insert(ignore_permissions=True)
		frappe.set_user(b)
		r = next(r for r in orc.my_tasks()["todo"] if r["name"] == t.name)
		assert r["action"] == "decide" and "Putuskan" in r["step"], r
		# Selesai: catatan opsional untuk Ditangani, wajib untuk Normal / Tidak Valid
		frappe.set_user("Administrator")
		other = orc.create_manual("uji selesai", assign_to=b)
		try:
			orc.resolve(other, "Normal", "")
			raise AssertionError("Normal tanpa alasan harus ditolak")
		except frappe.ValidationError:
			pass
		orc.resolve(other, "Ditangani", "")
		assert frappe.db.get_value("Agent Task", other, "status") == "Resolved"
		print("test_my_tasks OK")
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()

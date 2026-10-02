"""Cek mesin Orchestrator: dedupe kejadian, rantai eskalasi, akses, pengetahuan.

bench --site <site> execute assistant.assistant.test_orchestrator.run
Semua data di-rollback (commit di dalam mesin dimatikan selama tes).
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from assistant.assistant import orchestrator as orc


def _user(email, role=None):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0],
		                "send_welcome_email": 0, "roles": [{"role": role}] if role else []}).insert(ignore_permissions=True)
	return email


def run():
	commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		_run()
		print("test_orchestrator OK")
	finally:
		frappe.db.rollback()
		frappe.db.commit = commit


def _run():
	for role in ("Orchestrator Controller", "Orchestrator Admin"):
		assert frappe.db.exists("Role", role), role
	pic = _user("orc.pic@test.local")
	ctl = _user("orc.ctl@test.local", "Orchestrator Controller")
	adm = _user("orc.adm@test.local", "Orchestrator Admin")
	other = _user("orc.other@test.local")
	frappe.db.delete("Orchestrator Rule", {"parenttype": "Assistant Settings", "source": "Job"})
	frappe.get_doc({
		"doctype": "Orchestrator Rule", "parent": "Assistant Settings", "parenttype": "Assistant Settings",
		"parentfield": "orchestrator_rules", "source": "Job", "enabled": 1, "severity": "Medium",
		"response_minutes": 10, "escalate_minutes": 20,
		"controller_role": "Orchestrator Controller", "admin_role": "Orchestrator Admin",
	}).insert(ignore_permissions=True)

	# kejadian baru -> task untuk pemegang, batas action 10 menit
	name = orc.raise_task("Job", "job:TEST-1", "Job TEST belum selesai", "jalan 13 jam", assign_to=pic)
	t = frappe.get_doc("Agent Task", name)
	assert t.status == "Open" and t.assigned_to == pic and pic in orc._watchers(t)
	assert 9 <= (t.due_at - now_datetime()).total_seconds() / 60 <= 10

	# kejadian sama -> task sama; isi sama tidak menambah riwayat, isi baru menambah
	n_log = len(t.log)
	assert orc.raise_task("Job", "job:TEST-1", "x", "jalan 13 jam") == name
	assert len(frappe.get_doc("Agent Task", name).log) == n_log
	orc.raise_task("Job", "job:TEST-1", "x", "jalan 14 jam")
	assert len(frappe.get_doc("Agent Task", name).log) == n_log + 1

	# diam lewat batas -> Controller, lalu Admin, lalu berhenti
	frappe.db.set_value("Agent Task", name, "due_at", add_to_date(now_datetime(), minutes=-1))
	orc.escalate_due()
	t = frappe.get_doc("Agent Task", name)
	assert t.escalation_level == 1 and ctl in orc._watchers(t) and t.due_at
	frappe.db.set_value("Agent Task", name, "due_at", add_to_date(now_datetime(), minutes=-1))
	orc.escalate_due()
	t = frappe.get_doc("Agent Task", name)
	assert t.escalation_level == 2 and adm in orc._watchers(t) and not t.due_at

	# akses: penerima notifikasi boleh, orang lain tidak
	assert orc.has_permission(t, user=ctl) and orc.has_permission(t, user=pic)
	assert not orc.has_permission(t, user=other)

	# action menghentikan eskalasi; selesai = pengetahuan untuk kejadian serupa
	frappe.set_user(pic)
	try:
		orc.ack(name)
		assert frappe.db.get_value("Agent Task", name, "status") == "In Progress"
		orc.resolve(name, "Normal", "Driver menunggu muat, customer minta tunggu.")
	finally:
		frappe.set_user("Administrator")
	t = frappe.get_doc("Agent Task", name)
	assert t.status == "Resolved" and t.outcome == "Normal" and not t.due_at

	# kunci sama setelah selesai -> task baru, dan agent menemukan penyelesaian lama
	again = orc.raise_task("Job", "job:TEST-1", "Job TEST belum selesai", "jalan 20 jam", assign_to=pic)
	assert again != name
	past = orc._knowledge(frappe.get_doc("Agent Task", again))
	assert any("menunggu muat" in (p.resolution or "") for p in past), past

	# aturan nonaktif -> tidak ada task
	frappe.db.set_value("Orchestrator Rule", {"parenttype": "Assistant Settings", "source": "Job"}, "enabled", 0)
	assert orc.raise_task("Job", "job:TEST-2", "x", "y") is None

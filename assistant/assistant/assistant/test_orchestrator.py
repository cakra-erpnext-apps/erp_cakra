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

	_run_progress_and_manual(pic, ctl)
	_run_document_workflow(pic, ctl)


def _run_progress_and_manual(pic, ctl):
	# ditangani tapi didiamkan -> tetap dieskalasi, severity naik
	frappe.db.set_value("Orchestrator Rule", {"parenttype": "Assistant Settings", "source": "Job"}, "enabled", 1)
	name = orc.raise_task("Job", "job:TEST-3", "Job TEST-3", "macet", assign_to=pic)
	frappe.set_user(pic)
	try:
		orc.ack(name)
	finally:
		frappe.set_user("Administrator")
	t = frappe.get_doc("Agent Task", name)
	assert t.status == "In Progress" and t.due_at, "ack harus memasang batas selesai"
	frappe.db.set_value("Agent Task", name, "due_at", add_to_date(now_datetime(), minutes=-1))
	orc.escalate_due()
	t = frappe.get_doc("Agent Task", name)
	assert t.escalation_level == 1 and t.severity == "High" and ctl in orc._watchers(t), (t.escalation_level, t.severity)

	# task manual tidak bergantung rule Job: Job dimatikan, eskalasi tetap jalan
	frappe.db.set_value("Orchestrator Rule", {"parenttype": "Assistant Settings", "source": "Job"}, "enabled", 0)
	manual = orc.create_manual("Cek manual", assign_to=pic)
	frappe.db.set_value("Agent Task", manual, "due_at", add_to_date(now_datetime(), minutes=-1))
	orc.escalate_due()
	t = frappe.get_doc("Agent Task", manual)
	assert t.escalation_level == 1 and ctl in orc._watchers(t), t.escalation_level


def _run_document_workflow(pic, ctl):
	rule = frappe.get_doc({
		"doctype": "Orchestrator Rule", "parent": "Assistant Settings", "parenttype": "Assistant Settings",
		"parentfield": "orchestrator_rules", "source": "Document", "enabled": 1, "workflow_name": "Tes ToDo",
		"document_type": "ToDo", "doc_filters": '[["description", "like", "ORC-TEST%"]]',
		"doc_condition": "doc.priority == 'High'", "date_field": "creation", "threshold_hours": 0,
		"subject_template": "ToDo {{ doc.name }} prioritas {{ doc.priority }}", "assign_field": "allocated_to",
		"response_minutes": 30, "controller_role": "Orchestrator Controller", "admin_role": "Orchestrator Admin",
	}).insert(ignore_permissions=True)
	hit = frappe.get_doc({"doctype": "ToDo", "description": "ORC-TEST satu", "priority": "High", "allocated_to": pic}).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "ToDo", "description": "ORC-TEST dua", "priority": "Low"}).insert(ignore_permissions=True)

	# uji tanpa simpan: hanya yang lolos filter + kondisi
	prev = orc.preview_workflow(rule.as_dict())
	assert prev["count"] == 1 and prev["sample"][0]["name"] == hit.name and prev["sample"][0]["holder"] == pic, prev

	# jalan: task untuk PIC dari field dokumen, judul dari template, workflow tercatat
	orc._safe(lambda: orc.scan_document_rule(orc._rule_of(frappe._dict(source="Document", rule=rule.name))), rule.name)
	run = frappe.cache().hget("orchestrator:runs", rule.name)
	assert run and run.get("new") == 1 and not run.get("error"), run
	name = frappe.db.get_value("Agent Task", {"dedupe_key": f"doc:{rule.name}:{hit.name}"})
	t = frappe.get_doc("Agent Task", name)
	assert t.assigned_to == pic and t.workflow == "Tes ToDo" and t.subject == f"ToDo {hit.name} prioritas High", t.subject
	assert t.reference_doctype == "ToDo" and t.reference_name == hit.name

	# putaran kedua: tidak ada task ganda
	orc.scan_document_rule(orc._rule_of(t))
	assert frappe.db.count("Agent Task", {"rule": rule.name}) == 1

	# dokumen tidak memenuhi kondisi lagi -> task ditutup otomatis
	frappe.db.set_value("ToDo", hit.name, "priority", "Medium")
	orc.scan_document_rule(orc._rule_of(t))
	assert frappe.db.get_value("Agent Task", name, "status") == "Resolved"

	# monitoring: workflow tampil dengan hitungannya, aktivitas memuat riwayat task
	w = next(r for r in orc.workflows()["rows"] if r["name"] == rule.name)
	assert w["label"] == "Tes ToDo" and w["resolved"] == 1 and w["run"].get("new") == 1, w
	assert any(a.get("task") == name for a in orc.activity()["rows"])

	# kondisi rusak -> tercatat sebagai error workflow itu, bukan menghentikan scheduler
	frappe.db.set_value("Orchestrator Rule", rule.name, "doc_condition", "doc.tidak_ada(")
	orc.scan_documents()
	assert frappe.cache().hget("orchestrator:runs", rule.name).get("error")
	frappe.cache().hdel("orchestrator:runs", rule.name)

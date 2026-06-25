"""Agent Center — monitor many agents at once.

Concept: 1 PDF = 1 job = 1 agent (an Agent Administrator record) that runs to completion.
Each agent has a name, a creator (the Frappe `owner`), a status and a live
`current_activity`. PDF jobs run in a BACKGROUND worker so the user can watch
several agents work in parallel from the Agent Center page.
"""

import re

import frappe
from frappe import _

# Western first names; agents are shown as "Agent <Name>" (e.g. "Agent Andrew").
AGENT_NAMES = [
	"Andrew", "Oliver", "Ethan", "Mason", "Henry", "Oscar", "Felix", "Leo",
	"Max", "Victor", "Hugo", "Julian", "Adrian", "Aaron", "Nathan", "Sebastian",
	"Theodore", "Vincent", "Gabriel", "Emma", "Sophia", "Olivia", "Grace", "Chloe",
]

# Prepended to every generated name.
AGENT_PREFIX = "Agent"

ACTIVE_STATUSES = ("New", "In Progress", "Awaiting Review")
HISTORY_STATUSES = ("Completed", "Error")
STATUS_ICON = {"New": "🟡", "In Progress": "🔵", "Awaiting Review": "🟠", "Completed": "🟢", "Error": "🔴"}


def generate_agent_name():
	used = set(frappe.get_all("Agent Administrator", filters={"agent_name": ["is", "set"]}, pluck="agent_name") or [])
	for nm in AGENT_NAMES:
		cand = f"{AGENT_PREFIX} {nm}"
		if cand not in used:
			return cand
	i = 2
	while True:
		for nm in AGENT_NAMES:
			cand = f"{AGENT_PREFIX} {nm} {i}"
			if cand not in used:
				return cand
		i += 1


def _owner_name(owner):
	return frappe.db.get_value("User", owner, "full_name") or owner


def _pick_doc(r):
	return r.get("packing_list") or r.get("shipping_list") or r.get("expense_note") or r.get("sales_invoice")


@frappe.whitelist()
def list_agents(scope="active"):
	statuses = ACTIVE_STATUSES if scope == "active" else HISTORY_STATUSES
	rows = frappe.get_all(
		"Agent Administrator",
		filters={"status": ["in", statuses]},
		fields=[
			"name", "agent_name", "status", "current_activity", "summary", "job_label",
			"source", "owner", "creation", "modified", "packing_list", "shipping_list",
			"expense_note", "sales_invoice", "total_tokens_in", "total_tokens_out",
		],
		order_by="modified desc",
		limit_page_length=200,
	)
	for r in rows:
		r["owner_name"] = _owner_name(r["owner"])
		r["doc"] = _pick_doc(r)
		r["icon"] = STATUS_ICON.get(r["status"], "•")
	return rows


def _render_messages(transcript):
	out = []
	try:
		msgs = frappe.parse_json(transcript or "[]")
	except Exception:
		return out
	for m in msgs:
		role, content = m.get("role"), m.get("content")
		if isinstance(content, str):
			text = content
		elif isinstance(content, list):
			text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
		else:
			text = ""
		if role in ("user", "assistant") and (text or "").strip():
			out.append({"role": role, "text": text})
	return out


@frappe.whitelist()
def get_agent(intake):
	d = frappe.get_doc("Agent Administrator", intake)
	return {
		"intake": d.name, "agent_name": d.agent_name, "status": d.status,
		"current_activity": d.current_activity, "summary": d.summary, "job_label": d.job_label,
		"source": d.source, "owner": d.owner, "owner_name": _owner_name(d.owner),
		"creation": str(d.creation), "icon": STATUS_ICON.get(d.status, "•"),
		"messages": _render_messages(d.transcript),
		"packing_list": d.packing_list, "shipping_list": d.shipping_list,
		"expense_note": d.expense_note, "sales_invoice": d.sales_invoice,
		"tokens_in": d.total_tokens_in, "tokens_out": d.total_tokens_out,
	}


@frappe.whitelist()
def mark_done(intake):
	frappe.db.set_value("Agent Administrator", intake, {"status": "Completed", "current_activity": "Selesai (ditandai user)."})
	frappe.db.commit()
	return {"ok": True}


AUTO_PROMPT = (
	"Kerjakan job ini sampai selesai TANPA bertanya ke user. Baca dokumen terlampir, "
	"tentukan Packing List atau Shipping List, resolve master semampumu, lalu LANGSUNG "
	"buat draftnya (panggil create_*_draft). Kalau ada data kurang/ambigu, isi yang bisa, "
	"pilih kandidat terbaik, dan catat kekurangannya di ringkasan — JANGAN menunggu jawaban. "
	"Akhiri dengan ringkasan singkat: dokumen yang dibuat + apa yang perlu direview."
)


@frappe.whitelist()
def create_job(filename, content_b64):
	"""Create one agent for one PDF job and run it in the background."""
	from assistant.assistant import api

	sess = api.new_session(source="PDF")
	intake = sess["intake"]
	doc = frappe.get_doc("Agent Administrator", intake)
	doc.job_label = filename
	doc.status = "In Progress"
	doc.current_activity = "Antri — menyiapkan dokumen…"
	doc.summary = f"Job: {filename}"
	doc.save(ignore_permissions=True)

	up = api.upload_attachment(intake, filename, content_b64)
	if not up.get("ok"):
		frappe.db.set_value("Agent Administrator", intake, {"status": "Error", "current_activity": up.get("error") or "Lampiran ditolak."})
		frappe.db.commit()
		return {"intake": intake, "agent_name": doc.agent_name, "error": up.get("error")}

	frappe.db.commit()
	frappe.enqueue("assistant.assistant.center.run_agent_job", queue="short", timeout=900, intake=intake)
	return {"intake": intake, "agent_name": doc.agent_name, "ok": True}


def run_agent_job(intake):
	"""Background worker: process the PDF job into a draft, autonomously."""
	from assistant.assistant import api

	try:
		frappe.db.set_value("Agent Administrator", intake, {"status": "In Progress", "current_activity": "Membaca dokumen & menyiapkan draft…"})
		frappe.db.commit()
		res = api.chat(intake, AUTO_PROMPT)
		created = res.get("packing_list") or res.get("shipping_list") or res.get("expense_note") or res.get("sales_invoice")
		act = f"Selesai — draft {created} dibuat. Perlu review." if created else "Selesai membaca — perlu input lanjut (buka chat agent)."
		frappe.db.set_value("Agent Administrator", intake, {"current_activity": act})
		frappe.db.commit()
	except Exception as e:
		frappe.db.set_value("Agent Administrator", intake, {"status": "Error", "current_activity": f"Gagal: {str(e)[:180]}"})
		frappe.db.commit()
		frappe.log_error(frappe.get_traceback(), "run_agent_job")


def _status_line(a):
	act = a.get("current_activity") or a.get("summary") or "-"
	return f"{a.get('icon', '•')} **{a.get('agent_name')}** ({a['status']}) — {act}"


@frappe.whitelist()
def monitor(text):
	"""Monitoring chat: '@AgentName' shows that agent's status; otherwise lists all active."""
	mentions = re.findall(r"@([A-Za-z][\w]*)", text or "")
	active = list_agents("active")
	by_name = {(a.get("agent_name") or "").lower(): a for a in active}
	lines = []
	if mentions:
		for m in mentions:
			a = by_name.get(m.lower()) or next((x for x in active if (x.get("agent_name") or "").lower().startswith(m.lower())), None)
			lines.append(_status_line(a) if a else f"❓ Agent '{m}' tidak ditemukan / sudah selesai.")
	elif not active:
		return {"reply": "Tidak ada agent yang aktif sekarang."}
	else:
		lines.append(f"**{len(active)} agent aktif:**")
		lines += [_status_line(a) for a in active]
	return {"reply": "\n".join(lines)}

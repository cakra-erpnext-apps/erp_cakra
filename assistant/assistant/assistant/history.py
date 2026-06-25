"""Agent History — arsip PERMANEN tiap pesan chat & email.

Record di doctype 'Agent History' sengaja TERPISAH dari Agent Administrator
(pakai Data, bukan Link) supaya tetap ada walau agent di-reset/dihapus. Dipakai
untuk review/audit di kemudian hari.
"""

import json

import frappe
from frappe.utils import now_datetime

_DOC_FIELDS = (
	("sales_invoice", "Sales Invoice"),
	("expense_note", "Expense Note"),
	("shipping_list", "Shipping List"),
	("packing_list", "Packing List"),
)


def _agent_doc(agent):
	if hasattr(agent, "get"):
		return agent
	return frappe.get_doc("Agent Administrator", agent)


def log_history(agent, channel, role, message, subject=None, email_to=None,
				email_tag=None, status=None, occurred_at=None):
	"""Tambah 1 baris Agent History. Tidak pernah melempar error (best-effort)."""
	try:
		d = _agent_doc(agent)
		document = ""
		for fn, dt in _DOC_FIELDS:
			if d.get(fn):
				document = f"{dt} {d.get(fn)}"
				break
		frappe.get_doc({
			"doctype": "Agent History",
			"occurred_at": occurred_at or now_datetime(),
			"agent_name": d.get("agent_name") or d.name,
			"agent_id": d.name,
			"user": d.get("assigned_user") or d.get("owner") or "",
			"channel": channel,
			"role": role,
			"customer": d.get("customer") or "",
			"job_ref": d.get("job_ref") or "",
			"document": document,
			"email_to": email_to or "",
			"email_tag": d.get("email_tag") or email_tag or "",
			"status": status or "",
			"subject": (subject or "")[:240],
			"message": message or "",
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "history.log_history")


def _text_of(content):
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		return "\n".join(
			b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
		)
	return ""


def history_query_conditions(user=None):
	"""Permission filter (hooks.permission_query_conditions): di list 'Agent History',
	user NON-System-Manager HANYA melihat baris yang `user`-nya dia (yang pernah
	berhubungan dengan agent itu). System Manager lihat semua."""
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	return "`tabAgent History`.`user` = {0}".format(frappe.db.escape(user))


@frappe.whitelist()
def get_agent_history(agent_id=None, agent_name=None):
	"""History (chat + email) SATU agent untuk tab History (gaya bubble/thread).

	Akses dibatasi: hanya System Manager ATAU user yang terlibat (field `user`).
	"""
	out = {"chat": [], "emails": [], "agent_name": agent_name or ""}
	if not (agent_id or agent_name):
		return out
	filt = {"agent_id": agent_id} if agent_id else {"agent_name": agent_name}
	if "System Manager" not in frappe.get_roles():
		filt["user"] = frappe.session.user
	rows = frappe.get_all(
		"Agent History", filters=filt,
		fields=["channel", "role", "subject", "message", "email_to", "status", "occurred_at", "agent_name"],
		order_by="occurred_at asc", limit_page_length=0,
	)
	for r in rows:
		if r.channel == "Chat":
			out["chat"].append({"role": r.role, "text": r.message or "", "at": str(r.occurred_at)})
		else:
			out["emails"].append({
				"role": r.role, "subject": r.subject or "", "body": r.message or "",
				"mail_to": r.email_to or "", "status": r.status or "", "at": str(r.occurred_at),
			})
	if rows:
		out["agent_name"] = rows[0].agent_name or out["agent_name"]
	return out


@frappe.whitelist()
def backfill_all():
	"""Arsipkan SEMUA chat (transcript) + email (Agent Mail) yang ada sekarang ke
	Agent History. Aman dipanggil sekali sebelum reset agent. Mengembalikan jumlah baris."""
	n = 0
	for name in frappe.get_all("Agent Administrator", pluck="name"):
		d = frappe.get_doc("Agent Administrator", name)
		try:
			msgs = json.loads(d.transcript or "[]")
		except Exception:
			msgs = []
		for m in msgs:
			role, text = m.get("role"), _text_of(m.get("content"))
			if role in ("user", "assistant") and (text or "").strip():
				log_history(d, "Chat", role, text)
				n += 1
		for mail in frappe.get_all(
			"Agent Mail", filters={"agent_intake": name},
			fields=["role", "mail_to", "subject", "body", "status", "creation"],
			order_by="creation asc",
		):
			log_history(
				d, "Email", mail.role or "agent", mail.body or "",
				subject=mail.subject, email_to=mail.mail_to, status=mail.status,
				occurred_at=mail.creation,
			)
			n += 1
	frappe.db.commit()
	return n

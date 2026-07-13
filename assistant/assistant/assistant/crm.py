"""Assistant untuk Frappe CRM — 1 user = 1 agent pribadi (chat).

Dipakai frontend CRM (/crm): menu "Assistant" membuka chat; tiap user punya SATU
Agent Administrator sendiri (get-or-create, ditandai job_label "CRM Assistant"),
jadi session-nya persisten dan tetap terpantau di Assistant Center / list Agent
Administrator seperti agent lain.

Permission: user CRM (Sales dsb.) TIDAK punya role atas Agent Administrator —
akses dibatasi per-user: endpoint di sini hanya menyentuh agent miliknya sendiri
(assigned_user = session user); penyimpanan lewat jalur ignore_permissions yang
gerbangnya _assert_agent_access (lihat api.py).
"""

import frappe
from frappe import _

CRM_JOB_LABEL = "CRM Assistant"

# Sapaan khusus CRM. Sebelumnya memakai api.GREETING, milik agen input Expedition,
# sehingga user CRM disambut kalimat soal vessel, kontainer, dan draft Packing List.
CRM_GREETING = (
	"Halo! Saya asisten CRM Anda. Tanyakan apa saja soal lead, inquiry, quotation, "
	"atau estimasi — misalnya quotation mana yang belum dijawab customer, inquiry apa "
	"yang perlu ditindaklanjuti, atau ringkasan pipeline Anda."
)


def _assert_crm_allowed():
	"""Gerbang modul: baris "CRM" di Assistant Settings → Allowed Module.
	Tanpa baris CRM → dianggap boleh (kompatibel mundur)."""
	try:
		s = frappe.get_cached_doc("Assistant Settings")
		row = next(
			(r for r in (s.get("allowed_modules") or [])
			 if (r.module_name or "").strip().lower() == "crm"),
			None,
		)
	except Exception:
		return
	if row is not None and not row.allowed:
		frappe.throw(
			_("Assistant CRM sedang dinonaktifkan (Assistant Settings, tab Allowed Module)."),
			frappe.PermissionError,
		)


def _my_agent(create=False):
	"""Agent Administrator milik user login (1 user = 1 agent CRM)."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Silakan login dulu."), frappe.PermissionError)
	name = frappe.db.get_value(
		"Agent Administrator",
		{"assigned_user": user, "job_label": CRM_JOB_LABEL},
		"name",
		order_by="creation desc",
	)
	if name:
		return frappe.get_doc("Agent Administrator", name)
	if not create:
		return None

	from assistant.assistant import center

	full_name = frappe.db.get_value("User", user, "full_name") or user
	doc = frappe.new_doc("Agent Administrator")
	doc.source = "Chat"
	doc.status = "New"
	doc.job_label = CRM_JOB_LABEL
	doc.summary = _("Assistant CRM milik {0}").format(full_name)
	doc.agent_name = center.generate_agent_name()
	doc.current_activity = "Idle — siap menerima input."
	doc.assigned_user = user
	doc.phase = "expedition"
	doc.step = 0
	doc.contact_email = frappe.db.get_value("User", user, "email")
	try:
		s = frappe.get_cached_doc("Assistant Settings")
		doc.token_limit = int(s.get("tokens_per_agent") or 200000)
	except Exception:
		doc.token_limit = 200000
	doc.insert(ignore_permissions=True)
	try:
		from assistant.assistant import fleet

		fleet.log_event(doc.name, "created", f"{doc.agent_name} dibuat (CRM Assistant untuk {user}).", actor=user)
	except Exception:
		pass
	return doc


@frappe.whitelist()
def session():
	"""Get-or-create assistant CRM milik user + transcript untuk ditampilkan."""
	from assistant.assistant import fleet, llm

	_assert_crm_allowed()
	doc = _my_agent(create=True)
	return {
		"intake": doc.name,
		"agent_name": doc.agent_name,
		"messages": fleet._render_messages(doc.transcript),
		"greeting": CRM_GREETING,
		"configured": llm.is_configured(),
	}


@frappe.whitelist()
def chat(message):
	"""Kirim pesan ke assistant CRM milik user; balasan dari loop chat standar."""
	from assistant.assistant import api as aapi

	_assert_crm_allowed()
	doc = _my_agent(create=True)
	return aapi.chat(doc.name, message)

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

import json

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


def _new_agent(user):
	"""Buat satu sesi CRM Assistant baru (satu sesi = satu Agent Administrator)."""
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


def _my_agent(create=False):
	"""Agent Administrator milik user login — sesi AKTIF = row terbaru.

	Sesi lama (ditutup lewat /clear, status Completed) tetap ada sebagai riwayat;
	karena pencarian memakai creation desc, row terbarulah yang jadi sesi aktif."""
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
	return _new_agent(user)


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
def chat(message, context=None):
	"""Kirim pesan ke assistant CRM milik user; balasan dari loop chat standar.

	``context`` (opsional) — deskripsi singkat layar yang sedang dilihat user
	(mis. periode & scope dashboard), diteruskan ke loop chat sebagai konteks
	turn ini saja.

	Balasan membawa ``dashboard_updated`` bila agent mengubah layout CRM Dashboard
	di turn ini, supaya frontend bisa langsung me-reload dashboard-nya.
	"""
	from assistant.assistant import api as aapi

	_assert_crm_allowed()
	doc = _my_agent(create=True)

	def _dashboard_stamp():
		try:
			return frappe.db.get_value("CRM Dashboard", "Manager Dashboard", "modified")
		except Exception:
			return None

	before = _dashboard_stamp()
	out = aapi.chat(doc.name, message, context=context)
	if isinstance(out, dict):
		out["dashboard_updated"] = bool(before != _dashboard_stamp())
	return out


@frappe.whitelist()
def clear_session():
	"""/clear — tutup sesi aktif (jadi arsip riwayat) dan mulai sesi baru.

	Sesi lama TIDAK dihapus: row Agent Administrator-nya ditandai Completed dan
	tetap bisa dibuka lewat sessions()/session_messages(). Sesi aktif yang masih
	kosong dipakai ulang saja — tidak ada gunanya menumpuk sesi kosong."""
	from assistant.assistant import fleet, llm

	_assert_crm_allowed()
	user = frappe.session.user
	doc = _my_agent(create=True)

	if json.loads(doc.transcript or "[]"):
		from assistant.assistant.api import _save_agent

		doc.status = "Completed"
		doc.current_activity = "Sesi ditutup user (/clear)."
		# Judul riwayat = pesan pertama user (summary bawaan "Assistant CRM milik X"
		# tidak membedakan sesi satu dengan lainnya di daftar riwayat).
		if (doc.summary or "").startswith("Assistant CRM milik"):
			for m in json.loads(doc.transcript or "[]"):
				content = m.get("content")
				if m.get("role") != "user":
					continue
				text = content if isinstance(content, str) else next(
					(b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"),
					"",
				)
				if text:
					doc.summary = text[:130]
					break
		_save_agent(doc)
		try:
			fleet.log_event(doc.name, "closed", f"Sesi ditutup {user} lewat /clear.", actor=user)
		except Exception:
			pass
		doc = _new_agent(user)

	return {
		"intake": doc.name,
		"agent_name": doc.agent_name,
		"messages": [],
		"greeting": CRM_GREETING,
		"configured": llm.is_configured(),
	}


@frappe.whitelist()
def sessions(limit=20):
	"""Riwayat sesi chat CRM milik user login (yang sudah ditutup /clear)."""
	_assert_crm_allowed()
	rows = frappe.get_all(
		"Agent Administrator",
		filters={
			"assigned_user": frappe.session.user,
			"job_label": CRM_JOB_LABEL,
			"status": "Completed",
		},
		fields=["name", "agent_name", "summary", "creation", "modified"],
		order_by="creation desc",
		limit_page_length=min(int(limit or 20), 50),
	)
	for r in rows:
		r["creation"] = str(r["creation"])
		r["modified"] = str(r["modified"])
	return rows


@frappe.whitelist()
def session_messages(name):
	"""Isi chat satu sesi riwayat — hanya sesi CRM milik user sendiri."""
	from assistant.assistant import fleet

	_assert_crm_allowed()
	doc = frappe.get_doc("Agent Administrator", name)
	if doc.get("assigned_user") != frappe.session.user or doc.get("job_label") != CRM_JOB_LABEL:
		frappe.throw(_("Ini bukan sesi chat milik Anda."), frappe.PermissionError)
	return {
		"name": doc.name,
		"agent_name": doc.agent_name,
		"creation": str(doc.creation),
		"messages": fleet._render_messages(doc.transcript),
	}

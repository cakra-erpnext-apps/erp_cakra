"""Orchestrator: kejadian (email, GPS, job) -> Agent Task -> notifikasi -> eskalasi -> pengetahuan.

Satu mesin untuk semua sumber. Tiap sumber cukup memanggil `raise_task()` dengan kunci
kejadian; sisanya (siapa yang dikabari, batas waktu, naik ke Controller lalu Admin,
riwayat) diurus di sini menurut baris Orchestrator Rule di Assistant Settings.

- Kunci kejadian (`dedupe_key`) = satu masalah. Selama task-nya belum Resolved, kejadian
  berulang hanya menambah riwayat, bukan task baru. Email per transaksi, GPS per unit +
  peringatan, Job per item Dispatch Order. Task lain di dokumen yang sama = satu "case".
- Action user (Tangani / catat langkah / selesai) menghentikan eskalasi; cara penyelesaian
  disimpan dan dibaca agent saat menganalisa kejadian serupa berikutnya.
- AI hanya menganalisa dan merekomendasi; keputusan tetap di user.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, get_url, now_datetime, strip_html

SEVERITIES = ("Low", "Medium", "High", "Critical")
LEVELS = ("Penanggung jawab", "Controller", "Admin")
ADMIN_ROLES = {"System Manager", "Orchestrator Admin", "Orchestrator Controller"}
EMAIL_LOOKBACK_DAYS = 3


# --- aturan & penerima ----------------------------------------------------------------


def _rule(source):
	row = frappe.db.get_value(
		"Orchestrator Rule",
		{"parenttype": "Assistant Settings", "source": source, "enabled": 1},
		["source", "severity", "send_email", "ai_note", "handler_role", "response_minutes",
		 "controller_role", "escalate_minutes", "admin_role", "threshold_hours", "fleet_statuses"],
		as_dict=True,
	)
	return row


def _role_users(role):
	if not role:
		return []
	from assistant.assistant.fleet import _users_with_role
	return [u["name"] for u in _users_with_role(role) if u["name"] != "Administrator"]


def _watchers(doc):
	return [w for w in (doc.watchers or "").split("\n") if w]


def _add_watchers(doc, users):
	have = _watchers(doc)
	doc.watchers = "\n".join(have + [u for u in dict.fromkeys(users) if u and u not in have])


def _log(doc, kind, message, actor=None):
	doc.append("log", {
		"at": now_datetime(), "kind": kind,
		"actor": actor or frappe.session.user, "message": (message or "")[:2000],
	})


def _notify(doc, users, headline, rule=None):
	"""Lonceng desk ke tiap user + email bila aturannya minta. Satu baris riwayat."""
	users = [u for u in dict.fromkeys(users) if u]
	if not users:
		return
	subject = f"[{doc.severity}] {headline}"[:140]
	for u in users:
		try:
			frappe.get_doc({
				"doctype": "Notification Log", "subject": subject, "for_user": u, "type": "Alert",
				"document_type": "Agent Task", "document_name": doc.name,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "orchestrator._notify")
	if rule and rule.get("send_email"):
		emails = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
		if emails:
			link = f"{get_url()}/app/orchestrator?task={doc.name}"
			frappe.sendmail(
				recipients=emails, subject=subject,
				message=(
					f"<p>{frappe.utils.escape_html(headline)}</p>"
					f"<p style='white-space:pre-line'>{frappe.utils.escape_html(doc.description or '')}</p>"
					f"<p><a href='{link}'>Buka di Orchestrator ({doc.name})</a></p>"
				),
				reference_doctype="Agent Task", reference_name=doc.name,
			)
	names = ", ".join(frappe.db.get_value("User", u, "full_name") or u for u in users)
	_log(doc, "notify", f"{headline} -> {names}", actor="agent")


def _changed():
	frappe.publish_realtime("orchestrator_update", {}, after_commit=True)


# --- inti: buat / tambah kejadian -----------------------------------------------------


def raise_task(source, key, subject, description, reference=(None, None), assign_to=None,
               severity=None, rule=None):
	"""Satu kejadian. Task terbuka dengan kunci sama -> tambah riwayat saja. Kembali nama task."""
	rule = rule or _rule(source)
	if not rule:
		return None
	name = frappe.db.get_value("Agent Task", {"dedupe_key": key, "status": ["!=", "Resolved"]})
	if name:
		doc = frappe.get_doc("Agent Task", name)
		last = next((r.message for r in reversed(doc.log) if r.kind == "event"), None)
		if last != description:
			doc.event_at = now_datetime()
			doc.description = description
			_log(doc, "event", description, actor="agent")
			doc.save(ignore_permissions=True)
			_changed()
		return name

	handlers = [assign_to] if assign_to else _role_users(rule.handler_role)
	doc = frappe.get_doc({
		"doctype": "Agent Task", "subject": subject[:140], "source": source, "status": "Open",
		"severity": severity or rule.severity or "Medium", "dedupe_key": key,
		"reference_doctype": reference[0], "reference_name": reference[1],
		"assigned_to": assign_to if assign_to and frappe.db.exists("User", assign_to) else None,
		"description": description, "event_at": now_datetime(),
		"due_at": add_to_date(now_datetime(), minutes=cint(rule.response_minutes) or 10),
	})
	_add_watchers(doc, handlers)
	_log(doc, "event", description, actor="agent")
	doc.insert(ignore_permissions=True)
	_notify(doc, handlers, subject, rule)
	doc.save(ignore_permissions=True)
	if rule.ai_note:
		frappe.enqueue("assistant.assistant.orchestrator.write_agent_note", queue="short",
		               timeout=300, task=doc.name, enqueue_after_commit=True)
	_changed()
	return doc.name


def _resolve(doc, outcome, resolution, actor):
	doc.status = "Resolved"
	doc.outcome = outcome
	doc.resolution = resolution
	doc.resolved_by = actor if frappe.db.exists("User", actor) else None
	doc.resolved_at = now_datetime()
	doc.due_at = None
	_log(doc, "resolve", f"{outcome}: {resolution}", actor=actor)
	doc.save(ignore_permissions=True)
	_changed()


# --- eskalasi -----------------------------------------------------------------------


def escalate_due():
	"""Task Open lewat batas action: naik satu level (Controller, lalu Admin)."""
	now = now_datetime()
	for name in frappe.get_all("Agent Task", filters={"status": "Open", "due_at": ["<", now]}, pluck="name"):
		doc = frappe.get_doc("Agent Task", name)
		rule = _rule("Job" if doc.source == "Manual" else doc.source) or frappe._dict()
		level, targets = cint(doc.escalation_level), []
		while level < 2 and not targets:
			level += 1
			targets = _role_users(rule.controller_role if level == 1 else rule.admin_role)
		doc.escalation_level = level
		# Admin = ujung rantai: berhenti, jangan diulang tiap menit.
		doc.due_at = add_to_date(now, minutes=cint(rule.escalate_minutes) or 30) if level < 2 and targets else None
		if not targets:
			_log(doc, "escalate", _("Tidak ada action, tapi Controller/Admin belum diatur di Orchestrator Rule."), actor="agent")
			doc.save(ignore_permissions=True)
			continue
		_add_watchers(doc, targets)
		_log(doc, "escalate", _("Tidak ada action, dinaikkan ke {0}.").format(LEVELS[level]), actor="agent")
		_notify(doc, targets, _("Eskalasi ke {0}: {1}").format(LEVELS[level], doc.subject), rule)
		doc.save(ignore_permissions=True)
		_changed()
		frappe.db.commit()


# --- sumber: Email ------------------------------------------------------------------


def _email_links(comm):
	try:
		from erpnext_custom.mail_inbox import _links_of
		links = _links_of(comm)
	except ImportError:
		ref = frappe.db.get_value("Communication", comm, ["reference_doctype", "reference_name"], as_dict=True)
		links = [{"doctype": ref.reference_doctype, "name": ref.reference_name}] if ref and ref.reference_name else []
	return [l for l in links if l["doctype"] not in ("Agent Administrator", "Communication")]


def _doc_holder(doctype, name):
	"""Pemegang transaksi: orang pertama di Assign To, kalau tidak ada pembuatnya."""
	row = frappe.db.get_value(doctype, name, ["owner", "_assign"], as_dict=True) or {}
	assigned = frappe.parse_json(row.get("_assign") or "[]") or []
	return (assigned[0] if assigned else None) or row.get("owner")


def _replied_after(doctype, name, since):
	return frappe.db.sql(
		"""select 1 from `tabCommunication` c
		where c.communication_medium = 'Email' and c.sent_or_received = 'Sent' and c.creation > %(since)s
		  and ((c.reference_doctype = %(dt)s and c.reference_name = %(dn)s)
		    or exists (select 1 from `tabCommunication Link` l where l.parent = c.name
		               and l.link_doctype = %(dt)s and l.link_name = %(dn)s))
		limit 1""",
		{"dt": doctype, "dn": name, "since": since},
	)


def scan_email():
	"""Email customer yang tertaut ke transaksi -> task 'balas' untuk pemegang transaksinya."""
	rule = _rule("Email")
	if not rule:
		return
	cache = frappe.cache()
	since = cache.get_value("orchestrator:email_since") or add_to_date(now_datetime(), minutes=-15)
	now = now_datetime()
	rows = frappe.db.sql(
		"""select name, sender, subject, content, creation from `tabCommunication`
		where communication_medium = 'Email' and communication_type = 'Communication'
		  and sent_or_received = 'Received' and communication_date > %(oldest)s
		  and (creation > %(since)s or modified > %(since)s)
		order by creation""",
		{"since": since, "oldest": add_to_date(now, days=-EMAIL_LOOKBACK_DAYS)},
		as_dict=True,
	)
	for c in rows:
		for link in _email_links(c.name)[:1]:
			dt, dn = link["doctype"], link["name"]
			key = f"email:{dt}:{dn}"
			# sudah dibalas, atau task-nya sudah diselesaikan user setelah email ini datang
			if _replied_after(dt, dn, c.creation) or frappe.db.exists(
				"Agent Task", {"dedupe_key": key, "status": "Resolved", "resolved_at": [">", c.creation]}
			):
				continue
			snippet = strip_html(c.content or "").strip()[:600]
			raise_task(
				"Email", key, _("Balas email: {0}").format(c.subject or dn),
				_("Email dari {0} untuk {1} {2}.\nSubjek: {3}\n\n{4}").format(c.sender, dt, dn, c.subject or "-", snippet),
				reference=(dt, dn), assign_to=_doc_holder(dt, dn), rule=rule,
			)
	cache.set_value("orchestrator:email_since", now)

	# Sudah dibalas (email keluar tertaut ke transaksi yang sama) -> selesai sendiri.
	for t in frappe.get_all("Agent Task", filters={"source": "Email", "status": ["!=", "Resolved"]},
	                        fields=["name", "reference_doctype", "reference_name", "event_at"]):
		if t.reference_name and _replied_after(t.reference_doctype, t.reference_name, t.event_at):
			_resolve(frappe.get_doc("Agent Task", t.name), "Ditangani", _("Sudah dibalas lewat email."), "agent")


# --- sumber: Fleet (GPS) ------------------------------------------------------------


def _active_jobs():
	"""{vehicle: job aktif} -- sama dengan definisi GPS monitor: item Dispatch Order assigned
	yang belum Lanjut Job / Menuju Garasi."""
	jobs = {}
	for r in frappe.db.sql(
		"""select i.vehicle, i.name dpo_item, i.dpo_no, i.driver, i.customer, do.name dpo,
		          do.created_by_user, do.owner, (
		            select min(t.start) from `tabDispatch Order Route` t
		            where t.dpo_item = i.name and t.step_type = 'Assign') assign
		   from `tabDispatch Order Item` i join `tabDispatch Order` do on i.parent = do.name
		   where i.assigned = 1 and ifnull(i.vehicle, '') != ''
		     and not exists (select 1 from `tabDispatch Order Route` t where t.dpo_item = i.name
		                     and t.step_type in ('Lanjut Job', 'Menuju Garasi') and t.start is not null)
		   order by do.creation desc""",
		as_dict=True,
	):
		jobs.setdefault(r.vehicle, r)
	return jobs


def scan_fleet():
	"""Peringatan GPS (Fleet Status Rule) -> task untuk operator GPS; diam -> eskalasi."""
	rule = _rule("Fleet")
	if not rule:
		return
	try:
		from erp.fleet.vehicle_status import evaluate
	except ImportError:
		return
	wanted = {s.strip() for s in (rule.fleet_statuses or "").splitlines() if s.strip()}
	jobs = _active_jobs()
	titles = dict(frappe.db.sql("select name, title from `tabVehicle`"))
	seen = set()
	for vehicle, v in evaluate(jobs).items():
		hits = [(w["status"], w["message"]) for w in v["warnings"] if not wanted or w["status"] in wanted]
		if wanted and v["status"] in wanted:
			hits.append((v["status"], v["reason"]))
		for status, message in hits:
			key = f"fleet:{vehicle}:{status}"
			seen.add(key)
			job = jobs.get(vehicle)
			extra = _("\nJob: {0}, driver {1}, customer {2}").format(job.dpo_no, job.driver or "-", job.customer or "-") if job else ""
			raise_task(
				"Fleet", key, f"{status}: {titles.get(vehicle) or vehicle}", f"{message}{extra}",
				reference=("Vehicle", vehicle), rule=rule,
			)
	# Kondisi sudah hilang sebelum ada yang menangani -> tutup, dicatat sebagai pola.
	for t in frappe.get_all("Agent Task", filters={"source": "Fleet", "status": "Open"}, fields=["name", "dedupe_key"]):
		if t.dedupe_key not in seen:
			_resolve(frappe.get_doc("Agent Task", t.name), "Hilang Sendiri", _("Kondisi GPS kembali normal sebelum ditangani."), "agent")


# --- sumber: Job --------------------------------------------------------------------


def scan_job():
	"""Job sudah di-assign lebih dari N jam tapi belum selesai -> pengingat ke pembuatnya."""
	rule = _rule("Job")
	if not rule:
		return
	now = now_datetime()
	hours = cint(rule.threshold_hours) or 12
	active = {}
	for j in _active_jobs().values():
		active[f"job:{j.dpo_item}"] = j
		if not j.assign or (now - get_datetime(j.assign)).total_seconds() < hours * 3600:
			continue
		ran = int((now - get_datetime(j.assign)).total_seconds() // 3600)
		raise_task(
			"Job", f"job:{j.dpo_item}", _("Job {0} belum selesai").format(j.dpo_no or j.dpo),
			_("Job {0} ({1}, driver {2}, customer {3}) sudah {4} jam sejak assign, belum Lanjut Job / Menuju Garasi.").format(
				j.dpo_no or j.dpo_item, j.vehicle, j.driver or "-", j.customer or "-", ran),
			reference=("Dispatch Order", j.dpo), assign_to=j.created_by_user or j.owner, rule=rule,
		)
	for t in frappe.get_all("Agent Task", filters={"source": "Job", "status": ["!=", "Resolved"]}, fields=["name", "dedupe_key"]):
		if t.dedupe_key not in active:
			_resolve(frappe.get_doc("Agent Task", t.name), "Ditangani", _("Job sudah selesai."), "agent")


# --- scheduler ----------------------------------------------------------------------


def _safe(fn):
	try:
		fn()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"orchestrator.{fn.__name__}")


def tick():
	"""Tiap menit: email masuk + eskalasi (batas 10 menit butuh resolusi menit)."""
	_safe(scan_email)
	_safe(escalate_due)


def tick_slow():
	"""Tiap 15 menit: cek GPS + job macet."""
	_safe(scan_fleet)
	_safe(scan_job)


# --- analisa agent (AI) -------------------------------------------------------------

_NOTE_SYSTEM = (
	"Kamu Orchestrator operasional ERP CMI. Tugasmu membantu user menyelesaikan satu kejadian. "
	"Tulis singkat dalam Bahasa Indonesia, teks polos: 1) apa yang terjadi, 2) data terkait yang "
	"penting dari dokumen, 3) rekomendasi langkah. Kalau ada riwayat penyelesaian serupa, pakai "
	"sebagai acuan dan sebutkan polanya. Jangan mengarang data yang tidak ada di konteks."
)


def _knowledge(doc, limit=5):
	"""Penyelesaian terdahulu: dokumen yang sama, atau jenis kejadian yang sama (ujung kunci,
	mis. peringatan GPS yang sama di unit lain)."""
	kind = (doc.dedupe_key or "").rsplit(":", 1)[-1]
	return frappe.get_all(
		"Agent Task",
		filters={"source": doc.source, "status": "Resolved", "resolution": ["is", "set"], "name": ["!=", doc.name]},
		or_filters={"reference_name": doc.reference_name or "-", "dedupe_key": ["like", f"%:{kind}"]},
		fields=["subject", "outcome", "resolution"], order_by="resolved_at desc", limit=limit,
	)


def write_agent_note(task):
	from assistant.assistant import api, fleet
	doc = frappe.get_doc("Agent Task", task)
	parts = [f"Kejadian: {doc.subject}\n{doc.description or ''}"]
	if doc.reference_doctype and doc.reference_name:
		try:
			parts.append(f"Dokumen {doc.reference_doctype} {doc.reference_name}:\n{api._target_doc_snapshot(doc.reference_doctype, doc.reference_name, 3000)}")
		except Exception:
			pass
	past = _knowledge(doc)
	if past:
		parts.append("Riwayat penyelesaian serupa:\n" + "\n".join(f"- {p.subject}: {p.outcome}, {p.resolution}" for p in past))
	note = fleet._complete(_NOTE_SYSTEM, "\n\n".join(parts))
	doc.reload()
	doc.agent_note = note
	_log(doc, "agent", note, actor="agent")
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_changed()
	return note


# --- akses ---------------------------------------------------------------------------


def _is_manager(user=None):
	return bool(set(frappe.get_roles(user or frappe.session.user)) & ADMIN_ROLES)


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	return _is_manager(user) or doc.assigned_to == user or user in _watchers(doc)


def query_conditions(user=None):
	user = user or frappe.session.user
	if _is_manager(user):
		return ""
	u = frappe.db.escape(user)
	return f"(`tabAgent Task`.assigned_to = {u} or `tabAgent Task`.watchers like {frappe.db.escape('%' + user + '%')})"


def _get(task):
	doc = frappe.get_doc("Agent Task", task)
	if not has_permission(doc):
		frappe.throw(_("Task ini bukan untuk Anda."), frappe.PermissionError)
	return doc


# --- API halaman Orchestrator ------------------------------------------------------

_LIST_FIELDS = ["name", "subject", "status", "severity", "source", "escalation_level", "assigned_to",
                "reference_doctype", "reference_name", "due_at", "event_at", "creation", "outcome",
                "resolution", "resolved_by", "resolved_at", "watchers"]


def _due_in(due_at):
	"""Menit tersisa ke batas action, dihitung di server: browser bisa beda zona waktu."""
	return int((get_datetime(due_at) - now_datetime()).total_seconds() // 60) if due_at else None


@frappe.whitelist()
def inbox(scope="mine"):
	user = frappe.session.user
	manager = _is_manager()
	if scope == "knowledge":
		filters = {"status": "Resolved"}
		order = "resolved_at desc"
	else:
		filters = {"status": ["!=", "Resolved"]}
		order = "event_at desc"
	or_filters = None
	if scope == "mine" or not manager:
		or_filters = {"assigned_to": user, "watchers": ["like", f"%{user}%"]}
	rows = frappe.get_all("Agent Task", filters=filters, or_filters=or_filters, fields=_LIST_FIELDS,
	                      order_by=order, limit=300)
	if scope != "knowledge":
		rows.sort(key=lambda r: -SEVERITIES.index(r.severity or "Medium"))  # stabil: event_at tetap urut
	for r in rows:
		r.assigned_name = frappe.db.get_value("User", r.assigned_to, "full_name") if r.assigned_to else ""
		r.level_label = LEVELS[min(cint(r.escalation_level), 2)]
		r.due_in = _due_in(r.due_at)
	counts = frappe._dict(
		open=frappe.db.count("Agent Task", {"status": "Open"}),
		escalated=frappe.db.count("Agent Task", {"status": "Open", "escalation_level": [">", 0]}),
		in_progress=frappe.db.count("Agent Task", {"status": "In Progress"}),
		resolved_today=frappe.db.count("Agent Task", {"status": "Resolved", "resolved_at": [">=", frappe.utils.today()]}),
	)
	# nama tampilan semua user yang muncul (pemegang + penerima notifikasi), untuk Peta Kerja
	ids = {u for r in rows for u in [r.assigned_to, *(r.watchers or "").splitlines()] if u}
	users = dict(frappe.get_all("User", filters={"name": ["in", list(ids)]}, fields=["name", "full_name"], as_list=True)) if ids else {}
	return {"rows": rows, "counts": counts, "is_manager": manager, "users": users}


@frappe.whitelist()
def get_task(task):
	doc = _get(task)
	out = doc.as_dict()
	out.level_label = LEVELS[min(cint(doc.escalation_level), 2)]
	out.due_in = _due_in(doc.due_at)
	out.assigned_name = frappe.db.get_value("User", doc.assigned_to, "full_name") if doc.assigned_to else ""
	return out


@frappe.whitelist()
def ack(task):
	"""Tangani: pemegang = saya, eskalasi berhenti."""
	doc = _get(task)
	if doc.status == "Resolved":
		frappe.throw(_("Task sudah selesai."))
	doc.status = "In Progress"
	doc.assigned_to = frappe.session.user
	doc.due_at = None
	_log(doc, "action", _("Ditangani oleh {0}.").format(frappe.utils.get_fullname()))
	doc.save(ignore_permissions=True)
	_changed()
	return get_task(task)


@frappe.whitelist()
def add_note(task, note):
	"""Catat langkah yang dikerjakan -- bahan pengetahuan, juga menghentikan eskalasi."""
	doc = _get(task)
	if not (note or "").strip():
		frappe.throw(_("Catatan kosong."))
	if doc.status == "Open":
		doc.status = "In Progress"
		doc.assigned_to = doc.assigned_to or frappe.session.user
		doc.due_at = None
	_log(doc, "note", note.strip())
	doc.save(ignore_permissions=True)
	_changed()
	return get_task(task)


@frappe.whitelist()
def resolve(task, outcome, resolution):
	doc = _get(task)
	if outcome not in ("Ditangani", "Normal", "Tidak Valid"):
		frappe.throw(_("Hasil tidak dikenal."))
	if not (resolution or "").strip():
		frappe.throw(_("Isi cara penyelesaiannya: dipakai agent untuk kejadian serupa."))
	_resolve(doc, outcome, resolution.strip(), frappe.session.user)
	return get_task(task)


@frappe.whitelist()
def reassign(task, user):
	doc = _get(task)
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} tidak ditemukan.").format(user))
	doc.assigned_to = user
	doc.status = "Open"
	doc.escalation_level = 0
	rule = _rule(doc.source) or frappe._dict()
	doc.due_at = add_to_date(now_datetime(), minutes=cint(rule.response_minutes) or 10)
	_add_watchers(doc, [user])
	_log(doc, "action", _("Dioper ke {0}.").format(frappe.utils.get_fullname(user)))
	_notify(doc, [user], _("Dioper ke Anda: {0}").format(doc.subject), rule)
	doc.save(ignore_permissions=True)
	_changed()
	return get_task(task)


@frappe.whitelist()
def ask_agent(task):
	_get(task)
	write_agent_note(task)
	return get_task(task)


@frappe.whitelist()
def create_manual(subject, description=None, assign_to=None, severity="Medium",
                  reference_doctype=None, reference_name=None, response_minutes=60):
	"""Task manual dari admin/controller: tetap ikut mesin eskalasi (rule sumber Job sebagai acuan)."""
	if not _is_manager():
		frappe.throw(_("Hanya Controller/Admin yang boleh membuat task manual."), frappe.PermissionError)
	if severity not in SEVERITIES:
		severity = "Medium"
	doc = frappe.get_doc({
		"doctype": "Agent Task", "subject": subject[:140], "source": "Manual", "status": "Open",
		"severity": severity, "assigned_to": assign_to or None, "description": description or subject,
		"reference_doctype": reference_doctype or None, "reference_name": reference_name or None,
		"event_at": now_datetime(), "due_at": add_to_date(now_datetime(), minutes=cint(response_minutes) or 60),
		"dedupe_key": f"manual:{frappe.generate_hash(length=10)}",
	})
	_add_watchers(doc, [assign_to, frappe.session.user])
	_log(doc, "event", doc.description)
	doc.insert(ignore_permissions=True)
	_notify(doc, [assign_to], subject, _rule("Job"))
	doc.save(ignore_permissions=True)
	_changed()
	return doc.name

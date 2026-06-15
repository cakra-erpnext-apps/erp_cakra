"""File-based activity log for the agent, under `agent/logs/`.

For every chat turn we write:
- sessions/<intake>.json — structured turns (machine-processable)
- sessions/<intake>.md   — full human-readable record (user input + AI actions)
- log.md                 — append-only one-block summary per interaction

The folder lives inside the app (bind-mounted to the host), so the data is easy
to process outside ERP. Logging never breaks the chat flow — failures are
swallowed and reported to the error log.
"""

import json
import os

import frappe


def _enabled():
	try:
		s = frappe.get_cached_doc("Agent Settings")
		val = s.get("enable_file_log")
		return True if val in (None, "") else bool(val)
	except Exception:
		return True


def _logs_dir():
	d = frappe.get_app_path("agents", "agent", "logs")
	os.makedirs(os.path.join(d, "sessions"), exist_ok=True)
	return d


def log_turn(intake, source, user_text, attachments, actions, reply, created_pl, status):
	"""Record one chat turn to the JSON, per-session MD, and summary log."""
	if not _enabled():
		return
	try:
		_write(intake, source, user_text, attachments or [], actions or [], reply, created_pl, status)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "agent file log")


def _write(intake, source, user_text, attachments, actions, reply, created_pl, status):
	ts = frappe.utils.now()
	d = _logs_dir()

	# 1) structured JSON (read-modify-write)
	jpath = os.path.join(d, "sessions", f"{intake}.json")
	turns = []
	if os.path.exists(jpath):
		try:
			with open(jpath, encoding="utf-8") as f:
				turns = json.load(f)
		except Exception:
			turns = []
	turns.append(
		{
			"ts": ts,
			"source": source,
			"user": user_text,
			"attachments": attachments,
			"ai_actions": actions,
			"ai_reply": reply,
			"created_packing_list": created_pl,
			"status": status,
		}
	)
	with open(jpath, "w", encoding="utf-8") as f:
		json.dump(turns, f, ensure_ascii=False, indent=2)

	turn_no = len(turns)

	# 2) per-session human-readable MD
	mpath = os.path.join(d, "sessions", f"{intake}.md")
	is_new = not os.path.exists(mpath)
	with open(mpath, "a", encoding="utf-8") as f:
		if is_new:
			f.write(f"# Session {intake} ({source})\n\nStarted: {ts}\n")
		f.write(f"\n### Turn {turn_no} — [{ts}]\n")
		f.write(f"**User input:** {user_text or '(tidak ada teks)'}\n")
		if attachments:
			f.write(f"**Attachments:** {', '.join(attachments)}\n")
		if actions:
			f.write("**AI solved:**\n")
			for a in actions:
				f.write(f"- {a}\n")
		if created_pl:
			f.write(f"**Created draft:** {created_pl}\n")
		f.write(f"**AI reply:** {reply or ''}\n")

	# 3) append-only summary log
	lpath = os.path.join(d, "log.md")
	is_new = not os.path.exists(lpath)
	with open(lpath, "a", encoding="utf-8") as f:
		if is_new:
			f.write("# Expedition Agent — Activity Log\n\n> Append-only. One block per interaction.\n")
		att = f" | lampiran: {len(attachments)}" if attachments else ""
		ai = "; ".join(actions) if actions else "—"
		outcome = f"→ draft {created_pl}" if created_pl else f"→ {(reply or '').strip()[:60]}"
		f.write(f"\n## [{ts}] {intake} ({source}) — {status}\n")
		f.write(f"- user: {(user_text or '(lampiran saja)').strip()[:120]}{att}\n")
		f.write(f"- ai: {ai[:240]}\n")
		f.write(f"- {outcome}\n")

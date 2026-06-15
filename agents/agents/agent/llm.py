"""Multi-provider LLM layer with automatic failover.

Accounts live in Agent Settings -> Accounts (child table "Agent Provider"), run
in priority order. When one hits a rate limit / quota (or is over its daily token
limit / in cooldown), the next enabled account is used automatically. Token usage
is recorded per account. If no accounts are configured, the legacy single
Anthropic key on Agent Settings (or site_config) is used as a fallback.

Every provider response is normalised to the Anthropic Messages shape
({"stop_reason", "content":[blocks]}) so the rest of the agent is provider-agnostic.
"""

import json

import requests

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

DEFAULT_MODEL = "claude-opus-4-8"
ANTHROPIC_BASE = "https://api.anthropic.com"
OPENAI_BASE = "https://api.openai.com/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_COOLDOWN_SEC = 60

# HTTP statuses that should trigger failover to the next account.
ROTATE_STATUSES = {401, 402, 403, 429, 500, 502, 503, 529}


class RotatableError(Exception):
	def __init__(self, message, status=None, retry_after=None):
		super().__init__(message)
		self.status = status
		self.retry_after = retry_after


# --- Settings / accounts ---------------------------------------------------


def _settings():
	try:
		return frappe.get_cached_doc("Agent Settings")
	except Exception:
		return None


def _today():
	return frappe.utils.today()


def auto_failover():
	s = _settings()
	if s is None:
		return True
	val = s.get("auto_failover")
	return True if val in (None, "") else bool(val)


def _is_anthropic(provider):
	p = (provider or "").lower()
	return "anthropic" in p or "claude" in p


def _default_base(provider):
	"""Default API base URL per provider (when the row leaves Base URL blank)."""
	p = (provider or "").lower()
	if _is_anthropic(provider):
		return ANTHROPIC_BASE
	if "gemini" in p or "google" in p:
		return GEMINI_BASE
	if "compatible" in p:
		return ""  # custom — the user must supply it
	return OPENAI_BASE  # OpenAI (ChatGPT) and anything else OpenAI-shaped


def _infer_provider(base, model):
	"""Guess the provider from a base URL / model name (for the legacy single key)."""
	b = (base or "").lower()
	m = (model or "").lower()
	if "anthropic" in b:
		return "Anthropic (Claude)"
	if "generativelanguage" in b or "googleapis" in b:
		return "Google (Gemini)"
	if "openai.com" in b:
		return "OpenAI (ChatGPT)"
	if m.startswith("claude"):
		return "Anthropic (Claude)"
	if m.startswith("gemini"):
		return "Google (Gemini)"
	if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
		return "OpenAI (ChatGPT)"
	if b:
		return "OpenAI Compatible"  # custom base, OpenAI-shaped
	return "Anthropic (Claude)"


def _legacy_account():
	s = _settings()
	key = model = base = None
	if s is not None:
		en = s.get("enabled")
		enabled = True if en in (None, "") else bool(en)
		if enabled:
			key = s.get_password("api_key", raise_exception=False)
			model = (s.get("model") or "").strip() or None
			base = (s.get("base_url") or "").strip() or None
	if not key:
		key = frappe.conf.get("anthropic_api_key")
		model = model or frappe.conf.get("anthropic_model")
	if not key:
		return None
	provider = _infer_provider(base, model)
	return {
		"row": None,
		"label": f"Default ({provider})",
		"provider": provider,
		"api_key": key,
		"model": model or DEFAULT_MODEL,
		"base_url": base or _default_base(provider),
	}


def _account_from_row(row):
	key = row.get_password("api_key", raise_exception=False)
	if not key:
		return None
	provider = row.provider or "Anthropic"
	return {
		"row": row.name,
		"label": row.label or provider,
		"provider": provider,
		"api_key": key,
		"model": (row.model or "").strip() or DEFAULT_MODEL,
		"base_url": (row.base_url or "").strip() or _default_base(provider),
	}


def _provider_rows():
	s = _settings()
	if s is None:
		return []
	return list(s.get("providers") or [])


def _selectable_accounts():
	"""Enabled accounts with a key, not in cooldown, under their daily limit,
	sorted by priority. Falls back to the legacy single key if none usable."""
	now = now_datetime()
	today = _today()
	accts = []
	for row in _provider_rows():
		if not row.enabled:
			continue
		if row.cooldown_until and get_datetime(row.cooldown_until) > now:
			continue
		if row.daily_token_limit and row.usage_date == today and (row.tokens_today or 0) >= row.daily_token_limit:
			continue
		acct = _account_from_row(row)
		if acct:
			acct["_priority"] = row.priority or 10
			accts.append(acct)
	accts.sort(key=lambda a: a.get("_priority", 10))
	if not accts:
		leg = _legacy_account()
		if leg:
			accts = [leg]
	return accts


def _account_by_label(label):
	"""Build an account dict for a specific enabled provider by label, ignoring
	cooldown/limit (used when the user forces an account)."""
	for row in _provider_rows():
		if row.label == label and row.enabled:
			acct = _account_from_row(row)
			if acct:
				acct["_priority"] = row.priority or 10
				return acct
	return None


def account_status():
	"""Every provider account with a live health status, for the chat UI picker.

	status: alive | cooldown | over_limit | disabled | no_key
	"""
	now = now_datetime()
	today = _today()
	out = []
	for row in _provider_rows():
		has_key = bool(row.get_password("api_key", raise_exception=False))
		cd = get_datetime(row.cooldown_until) if row.cooldown_until else None
		in_cooldown = bool(cd and cd > now)
		over_limit = bool(
			row.daily_token_limit and row.usage_date == today and (row.tokens_today or 0) >= row.daily_token_limit
		)
		if not row.enabled:
			status = "disabled"
		elif not has_key:
			status = "no_key"
		elif in_cooldown:
			status = "cooldown"
		elif over_limit:
			status = "over_limit"
		else:
			status = "alive"
		out.append(
			{
				"label": row.label,
				"provider": row.provider,
				"model": row.model,
				"priority": row.priority or 10,
				"status": status,
				"alive": status == "alive",
				"vision": _supports_vision({"model": row.model}),
				"cooldown_until": str(cd) if in_cooldown else None,
				"tokens_today": row.tokens_today or 0,
				"daily_token_limit": row.daily_token_limit or 0,
				"last_error": (row.last_error or "")[:160] if status not in ("alive", "disabled") else None,
			}
		)
	out.sort(key=lambda a: a["priority"])
	return out


def _any_key():
	for row in _provider_rows():
		if row.enabled and row.get_password("api_key", raise_exception=False):
			return True
	return bool(_legacy_account())


def is_configured():
	return _any_key()


def get_model():
	accts = _selectable_accounts()
	if accts:
		return accts[0]["model"]
	leg = _legacy_account()
	return leg["model"] if leg else DEFAULT_MODEL


# --- Public entry point ----------------------------------------------------


# Model-name hints for text-only models (no image/vision input). Vision variants
# (…-vision, …-vl…) override this. Used to route image requests away from accounts
# that would 404 on an attached document.
_TEXT_ONLY_HINTS = ("gpt-oss", "llama", "mixtral", "mistral", "gemma", "qwen", "deepseek", "kimi", "moonshot")


def _supports_vision(acct):
	m = (acct.get("model") or "").lower()
	if "vision" in m or "-vl" in m or "vl-" in m:
		return True
	return not any(h in m for h in _TEXT_ONLY_HINTS)


def _messages_have_images(messages):
	for msg in messages or []:
		c = msg.get("content")
		if isinstance(c, list):
			for b in c:
				if isinstance(b, dict) and b.get("type") == "image":
					return True
	return False


def create_message(system, messages, tools=None, max_tokens=None, account_label=None):
	"""Call the LLM with failover across accounts. Returns the normalised
	Anthropic-shaped response, with extra keys `_account` and `_usage`.

	If ``account_label`` is given, that one account is used (failover overridden) —
	honoured even if it is in cooldown, so the user can force a specific AI.
	"""
	max_tokens = max_tokens or DEFAULT_MAX_TOKENS
	has_images = _messages_have_images(messages)

	if account_label:
		forced = _account_by_label(account_label)
		if not forced:
			frappe.throw(_("Akun AI '{0}' tidak ditemukan / tanpa API key.").format(account_label))
		if has_images and not _supports_vision(forced):
			frappe.throw(
				_("Akun '{0}' ({1}) tidak bisa membaca gambar — pilih akun lain atau Auto.").format(
					account_label, forced.get("model")
				)
			)
		candidates = [forced]
	else:
		accounts = _selectable_accounts()
		if not accounts:
			frappe.throw(
				_("Belum ada akun AI yang aktif/berkey. Atur di Agent Settings."),
				title=_("Agent not configured"),
			)
		candidates = accounts if auto_failover() else accounts[:1]
		# Image/document requests must only go to vision-capable accounts; otherwise a
		# text-only model (e.g. gpt-oss, llama) 404s on the attachment.
		if has_images:
			vision = [a for a in candidates if _supports_vision(a)]
			if vision:
				candidates = vision
			else:
				frappe.throw(
					_("Tidak ada akun AI 'vision' yang aktif untuk membaca gambar/PDF. "
					  "Nyalakan akun yang mendukung gambar (mis. CX gpt-5.5, Gemini, atau GPT-4o).")
				)
	last_err = None
	for acct in candidates:
		try:
			norm, usage, headers = _dispatch(acct, system, messages, tools, max_tokens)
		except RotatableError as e:
			_mark_cooldown(acct, e)
			last_err = e
			continue
		_record_usage(acct, usage, headers)
		norm["_account"] = acct["label"]
		norm["_usage"] = usage
		return norm

	frappe.throw(
		_("Semua akun AI gagal atau kena limit. Error terakhir: {0}").format(str(last_err) if last_err else "-")
	)


def _dispatch(acct, system, messages, tools, max_tokens):
	# Anthropic uses its native Messages API; OpenAI, Gemini and any
	# OpenAI-compatible endpoint all go through the OpenAI adapter.
	if _is_anthropic(acct.get("provider")):
		return _anthropic_call(acct, system, messages, tools, max_tokens)
	return _openai_call(acct, system, messages, tools, max_tokens)


# --- Anthropic adapter -----------------------------------------------------


def _anthropic_call(acct, system, messages, tools, max_tokens):
	base = (acct.get("base_url") or ANTHROPIC_BASE).rstrip("/")
	payload = {
		"model": acct["model"],
		"max_tokens": max_tokens,
		"thinking": {"type": "disabled"},
		"system": system,
		"messages": messages,
	}
	if tools:
		payload["tools"] = tools

	try:
		resp = requests.post(
			f"{base}/v1/messages",
			headers={
				"x-api-key": acct["api_key"],
				"anthropic-version": ANTHROPIC_VERSION,
				"content-type": "application/json",
			},
			json=payload,
			timeout=120,
		)
	except requests.RequestException as e:
		raise RotatableError(f"network: {e}")

	if resp.status_code >= 400:
		_raise_for_status(resp)

	data = resp.json()
	usage = {
		"input": (data.get("usage") or {}).get("input_tokens", 0),
		"output": (data.get("usage") or {}).get("output_tokens", 0),
	}
	headers = {
		"tokens_remaining": resp.headers.get("anthropic-ratelimit-tokens-remaining"),
		"requests_remaining": resp.headers.get("anthropic-ratelimit-requests-remaining"),
	}
	return data, usage, headers


# --- OpenAI-compatible adapter ---------------------------------------------


def _system_text(system):
	if isinstance(system, str):
		return system
	return "\n\n".join(b.get("text", "") for b in (system or []) if isinstance(b, dict))


def _to_openai_messages(system, messages):
	out = [{"role": "system", "content": _system_text(system)}]
	for m in messages:
		role = m.get("role")
		content = m.get("content")
		if role == "user":
			if isinstance(content, str):
				out.append({"role": "user", "content": content})
				continue
			parts, tool_msgs = [], []
			for b in content or []:
				t = b.get("type")
				if t == "text":
					parts.append({"type": "text", "text": b.get("text", "")})
				elif t == "image":
					src = b.get("source") or {}
					url = f"data:{src.get('media_type','image/png')};base64,{src.get('data','')}"
					parts.append({"type": "image_url", "image_url": {"url": url}})
				elif t == "tool_result":
					c = b.get("content")
					if isinstance(c, list):
						c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
					tool_msgs.append({"role": "tool", "tool_call_id": b.get("tool_use_id"), "content": str(c)})
			out.extend(tool_msgs)
			if parts:
				if len(parts) == 1 and parts[0]["type"] == "text":
					out.append({"role": "user", "content": parts[0]["text"]})
				else:
					out.append({"role": "user", "content": parts})
		elif role == "assistant":
			texts, calls = [], []
			for b in content or []:
				if b.get("type") == "text":
					texts.append(b.get("text", ""))
				elif b.get("type") == "tool_use":
					calls.append(
						{
							"id": b.get("id"),
							"type": "function",
							"function": {"name": b.get("name"), "arguments": json.dumps(b.get("input") or {})},
						}
					)
			# Groq (and some OpenAI-compatible servers) reject null content — always
			# send a string (empty when the turn was tool calls only).
			msg = {"role": "assistant", "content": "\n".join(texts)}
			if calls:
				msg["tool_calls"] = calls
			out.append(msg)
	return out


def _to_openai_tools(tools):
	if not tools:
		return None
	return [
		{
			"type": "function",
			"function": {
				"name": t["name"],
				"description": t.get("description", ""),
				"parameters": t.get("input_schema", {"type": "object", "properties": {}}),
			},
		}
		for t in tools
	]


def _from_openai(choice):
	msg = choice.get("message") or {}
	blocks = []
	if msg.get("content"):
		blocks.append({"type": "text", "text": msg["content"]})
	for tc in msg.get("tool_calls") or []:
		fn = tc.get("function") or {}
		try:
			inp = json.loads(fn.get("arguments") or "{}")
		except Exception:
			inp = {}
		blocks.append({"type": "tool_use", "id": tc.get("id"), "name": fn.get("name"), "input": inp})
	finish = choice.get("finish_reason")
	stop = "tool_use" if msg.get("tool_calls") else ("max_tokens" if finish == "length" else "end_turn")
	return {"stop_reason": stop, "content": blocks}


def _openai_call(acct, system, messages, tools, max_tokens):
	base = (acct.get("base_url") or "").rstrip("/")
	if not base:
		frappe.throw(_("Base URL wajib diisi untuk provider 'OpenAI Compatible'."))
	payload = {
		"model": acct["model"],
		"max_tokens": max_tokens,
		"messages": _to_openai_messages(system, messages),
	}
	oai_tools = _to_openai_tools(tools)
	if oai_tools:
		payload["tools"] = oai_tools
		payload["tool_choice"] = "auto"

	try:
		resp = requests.post(
			f"{base}/chat/completions",
			headers={"Authorization": f"Bearer {acct['api_key']}", "content-type": "application/json"},
			json=payload,
			timeout=120,
		)
	except requests.RequestException as e:
		raise RotatableError(f"network: {e}")

	if resp.status_code >= 400:
		_raise_for_status(resp)

	data = resp.json()
	choice = (data.get("choices") or [{}])[0]
	norm = _from_openai(choice)
	u = data.get("usage") or {}
	usage = {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)}
	headers = {"tokens_remaining": resp.headers.get("x-ratelimit-remaining-tokens")}
	return norm, usage, headers


# --- Errors / usage --------------------------------------------------------


def _raise_for_status(resp):
	try:
		err = resp.json().get("error", {})
		msg = err.get("message") or resp.text
	except Exception:
		msg = resp.text
	retry_after = resp.headers.get("retry-after")
	# "No endpoints found that support image input" etc. — the model can't do vision.
	# Treat as rotatable so failover moves to a vision-capable account instead of dying.
	low = (msg or "").lower()
	vision_unsupported = "image input" in low or "support image" in low or ("vision" in low and "support" in low)
	if resp.status_code in ROTATE_STATUSES or vision_unsupported:
		raise RotatableError(f"HTTP {resp.status_code}: {msg}", status=resp.status_code, retry_after=retry_after)
	# Non-rotatable (e.g. 400 bad request) — surface to the user, don't burn accounts.
	frappe.throw(_("AI error ({0}): {1}").format(resp.status_code, msg))


def _update_row(row_name, values):
	"""Update Agent Provider child-row columns directly.

	IMPORTANT: never re-save the parent Agent Settings doc to update usage —
	Frappe masks child-table Password fields on load, so a parent .save() wipes
	every provider's api_key. Writing columns directly leaves api_key untouched.
	"""
	frappe.db.set_value("Agent Provider", row_name, values, update_modified=False)
	frappe.db.commit()
	frappe.clear_cache(doctype="Agent Settings")


def _record_usage(acct, usage, headers):
	row_name = acct.get("row")
	if not row_name:
		return
	try:
		cur = frappe.db.get_value(
			"Agent Provider", row_name,
			["requests", "tokens_in", "tokens_out", "tokens_today", "usage_date"],
			as_dict=True,
		) or {}
		today = _today()
		tin = usage.get("input") or 0
		tout = usage.get("output") or 0
		tt = 0 if cur.get("usage_date") != today else (cur.get("tokens_today") or 0)
		vals = {
			"requests": (cur.get("requests") or 0) + 1,
			"tokens_in": (cur.get("tokens_in") or 0) + tin,
			"tokens_out": (cur.get("tokens_out") or 0) + tout,
			"tokens_today": tt + tin + tout,
			"usage_date": today,
			"last_used": now_datetime(),
			"cooldown_until": None,
			"last_error": None,
		}
		if headers.get("tokens_remaining") is not None:
			vals["tokens_remaining"] = str(headers.get("tokens_remaining"))
		_update_row(row_name, vals)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "agent usage record")


def _mark_cooldown(acct, err):
	row_name = acct.get("row")
	if not row_name:
		return
	try:
		secs = DEFAULT_COOLDOWN_SEC
		try:
			if err.retry_after:
				secs = max(secs, int(float(err.retry_after)))
		except Exception:
			pass
		_update_row(
			row_name,
			{"cooldown_until": add_to_date(now_datetime(), seconds=secs), "last_error": str(err)[:140]},
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "agent cooldown")


def _all_accounts_for_test():
	accts = []
	for row in _provider_rows():
		if row.enabled:
			a = _account_from_row(row)
			if a:
				accts.append(a)
	if not accts:
		leg = _legacy_account()
		if leg:
			accts = [leg]
	return accts


def test_accounts():
	"""Ping each enabled account with a tiny request; report ok/fail per account."""
	out = []
	sys = [{"type": "text", "text": "Connectivity test."}]
	msgs = [{"role": "user", "content": "Reply with the single word: OK"}]
	for acct in _all_accounts_for_test():
		entry = {"label": acct["label"], "provider": acct["provider"], "model": acct["model"]}
		try:
			norm, usage, headers = _dispatch(acct, sys, msgs, None, 256)
			txt = "".join(b.get("text", "") for b in norm.get("content", []) if b.get("type") == "text")
			entry.update({"ok": True, "reply": txt.strip()[:40]})
		except Exception as e:
			entry.update({"ok": False, "error": str(e)[:140]})
		out.append(entry)
	return out


def get_usage():
	"""Current usage/limit snapshot per account — for the get_usage tool & UI."""
	now = now_datetime()
	rows = []
	for row in _provider_rows():
		cooling = bool(row.cooldown_until and get_datetime(row.cooldown_until) > now)
		rows.append(
			{
				"label": row.label,
				"provider": row.provider,
				"model": row.model,
				"enabled": bool(row.enabled),
				"requests": row.requests or 0,
				"tokens_in": row.tokens_in or 0,
				"tokens_out": row.tokens_out or 0,
				"tokens_today": row.tokens_today or 0,
				"daily_token_limit": row.daily_token_limit or 0,
				"limit_remaining": row.tokens_remaining,
				"cooling_down": cooling,
				"cooldown_until": str(row.cooldown_until) if row.cooldown_until else None,
				"last_error": row.last_error,
			}
		)
	return {"auto_failover": auto_failover(), "accounts": rows}

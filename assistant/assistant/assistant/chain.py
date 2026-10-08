"""Rantai antar agent (Fase C Tangga Otonomi Agent): serah terima lewat Orchestrator.

- Agent tidak memanggil agent lain. Kejadian dokumen (doc_events) -> Agent Task sumber "Chain"
  untuk agent berikutnya -> dikerjakan antrean (run_task). Tiap langkah = satu task, jadi
  terlihat di Inbox, Peta Kerja, Aktivitas, dan tab Rantai.
- Satu dokumen satu pemilik: agent tidak mengubah dokumen yang sedang dipegang langkah lain.
- Rantai berhenti di langkah manusia (validasi). Begitu user memvalidasi, kejadian berikutnya
  memicu agent sesudahnya.
- Agent hanya membuat draft dan memeriksa. Validasi, posting, pembayaran tetap oleh user.
- Gagal = berhenti dan diserahkan ke Controller, bukan dicoba ulang diam-diam.

Rantai:
  Reimburse: Expense Note reimburse divalidasi -> Billing: SI Reimburse draft -> User: validasi SI
             -> Accounting: periksa jurnal SI
  Trading:   Delivery Note divalidasi -> Billing: SI draft dari DN -> User -> Accounting
  Pembelian: Purchase Invoice divalidasi -> Accounting: periksa jurnal PI
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, today

from assistant.assistant import orchestrator as orc

BILLING, ACCOUNTING, USER = "Agent Billing", "Agent Accounting", "User"
SWITCH = {"Reimburse": "chain_reimburse_enabled", "Trading": "chain_trading_enabled", "Pembelian": "chain_purchase_enabled"}
CONTROLLER = "Orchestrator Controller"


def _on(chain):
	"""Rantai jalan hanya kalau Orchestrator dan saklar rantainya nyala. Saklar rantai bawaan
	mati (belum pernah disimpan = mati), beda dengan saklar Orchestrator."""
	if not orc.switch_on():
		return False
	v = frappe.db.sql("select value from `tabSingles` where doctype = 'ERPNext Custom Setting' and field = %s", SWITCH[chain])
	return bool(v and cint(v[0][0]))


def _pic(doctype, name):
	"""Pemilik dokumen yang aktif dan bukan Administrator; selain itu None (-> Controller)."""
	user = orc._doc_holder(doctype, name)
	if user in (None, "Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
		return None
	return user


def _task(chain_id, step, agent, subject, description, ref, assign_to=None):
	"""Satu langkah rantai. Kunci = rantai + langkah + dokumen: kejadian berulang tidak membuat
	langkah dobel."""
	key = f"chain:{chain_id}:{step}:{ref[1]}"
	name = frappe.db.get_value("Agent Task", {"dedupe_key": key})
	if name:
		return frappe.get_doc("Agent Task", name)
	doc = frappe.get_doc({
		"doctype": "Agent Task", "subject": subject[:140], "source": "Chain", "status": "Open", "severity": "Medium",
		"dedupe_key": key, "reference_doctype": ref[0], "reference_name": ref[1], "description": description,
		"event_at": now_datetime(), "chain_id": chain_id, "chain_step": step, "agent_role": agent,
		"assigned_to": assign_to, "workflow": _("Rantai {0}").format(chain_id.split(":", 1)[0]),
	})
	watchers = [assign_to] if assign_to else orc._role_users(CONTROLLER) if agent == USER else []
	orc._add_watchers(doc, watchers)
	orc._log(doc, "event", description, actor="agent")
	doc.insert(ignore_permissions=True)
	if agent == USER:
		orc._notify(doc, watchers, subject)
		doc.save(ignore_permissions=True)
	else:
		frappe.enqueue("assistant.assistant.chain.run_task", queue="short", timeout=300, task=doc.name,
		               enqueue_after_commit=True)
	orc._changed()
	return doc


def _history(chain_id):
	"""Konteks yang ikut diserahkan: langkah-langkah sebelumnya beserta hasilnya."""
	rows = frappe.get_all("Agent Task", filters={"source": "Chain", "chain_id": chain_id},
	                      fields=["chain_step", "agent_role", "status", "resolution", "reference_name"], order_by="creation")
	return "\n".join(f"- {r.chain_step} ({r.agent_role}): {r.resolution or r.status}" for r in rows)


def _owned_by_other(ref, agent):
	"""Langkah lain yang masih memegang dokumen ini (satu dokumen satu pemilik)."""
	return frappe.db.get_value("Agent Task", {
		"source": "Chain", "reference_doctype": ref[0], "reference_name": ref[1],
		"status": ["!=", "Resolved"], "agent_role": ["!=", agent]}, "name")


# --- kejadian (doc_events) ------------------------------------------------------------------


def on_expense_note(doc, method=None):
	"""EN reimburse baru saja tervalidasi -> Billing."""
	if not (doc.get("is_reimburse") and doc.get("validated") and not doc.get("void")):
		return
	if not (doc.is_new() or doc.has_value_changed("validated")) or not _on("Reimburse"):
		return
	cid = f"Reimburse:{doc.name}"
	_task(cid, "Buat invoice", BILLING, _("Billing: tagih reimburse {0}").format(doc.name),
	      _("Expense Note reimburse {0} divalidasi ({1}). Agent Billing menyiapkan Sales Invoice Reimburse draft.").format(
	          doc.name, doc.reimburse_to_customer or "-"), ("Expense Note", doc.name))


def on_delivery_note(doc, method=None):
	"""DN divalidasi (submit) -> Billing."""
	if not _on("Trading"):
		return
	cid = f"Trading:{doc.name}"
	_task(cid, "Buat invoice", BILLING, _("Billing: tagih {0}").format(doc.name),
	      _("Delivery Note {0} divalidasi ({1}). Agent Billing menyiapkan Sales Invoice draft.").format(doc.name, doc.customer),
	      ("Delivery Note", doc.name))


def on_sales_invoice(doc, method=None):
	"""SI divalidasi: langkah manusia selesai -> Accounting. Hanya SI yang lahir dari rantai."""
	waiting = frappe.get_all("Agent Task", filters={"source": "Chain", "agent_role": USER, "status": ["!=", "Resolved"],
	                                                "reference_doctype": "Sales Invoice", "reference_name": doc.name},
	                         fields=["name", "chain_id"])
	for w in waiting:
		orc._resolve(frappe.get_doc("Agent Task", w.name), "Ditangani",
		             _("Divalidasi oleh {0}.").format(frappe.session.user), frappe.session.user)
		_task(w.chain_id, "Periksa jurnal", ACCOUNTING, _("Accounting: periksa jurnal {0}").format(doc.name),
		      _("Sales Invoice {0} divalidasi. Agent Accounting memeriksa jurnalnya.\n\nRiwayat rantai:\n{1}").format(
		          doc.name, _history(w.chain_id)), ("Sales Invoice", doc.name))


def on_purchase_invoice(doc, method=None):
	"""PI divalidasi (dibuat user) -> Accounting memeriksa jurnalnya."""
	if not _on("Pembelian"):
		return
	_task(f"Pembelian:{doc.name}", "Periksa jurnal", ACCOUNTING, _("Accounting: periksa jurnal {0}").format(doc.name),
	      _("Purchase Invoice {0} divalidasi ({1}). Agent Accounting memeriksa jurnalnya.").format(doc.name, doc.supplier),
	      ("Purchase Invoice", doc.name))


# --- agent ----------------------------------------------------------------------------------


def _fill_address(si):
	"""Alamat customer wajib di Sales Invoice Cakra; di desk terisi saat customer dipilih."""
	if not si.get("custom_customer_address"):
		from frappe.contacts.doctype.address.address import get_default_address
		si.custom_customer_address = get_default_address("Customer", si.customer)


def _billing_reimburse(task):
	from erpnext_custom.overrides.sales_invoice import get_reimburse_expense_notes
	en = frappe.get_doc("Expense Note", task.reference_name)
	rows = [r for r in get_reimburse_expense_notes(en.reimburse_to_customer, en.currency) if r.get("status") == "ready"]
	mine = [r for r in rows if r["expense_note"] == en.name]
	if not mine:
		return None, _("Semua baris {0} sudah ada di Sales Invoice lain (termasuk draft). Tidak ada yang perlu ditagih.").format(en.name)
	si = frappe.new_doc("Sales Invoice")
	si.update({"company": en.company, "customer": en.reimburse_to_customer, "custom_invoice_type": "Reimburse",
	           "custom_invoice_type_no": "IR", "invoice_date": today(), "posting_date": today(),
	           "currency": en.currency, "conversion_rate": flt(en.get("conversion_rate")) or 1})
	# satu invoice untuk semua reimburse customer ini yang siap ditagih (cara kerja picker di desk)
	for r in rows:
		si.append("custom_reimburse_items", {k: r.get(k) for k in (
			"expense_note", "item", "expense_class", "amount", "tax", "net_total", "document_date", "document_no_fp", "note")}
			| {"currency": r.get("currency") or en.currency, "rate": si.conversion_rate})
	_fill_address(si)
	si.insert()
	ens = sorted({r["expense_note"] for r in rows})
	return si, _("Sales Invoice Reimburse {0} draft dibuat untuk {1}: {2} baris dari {3}.").format(
		si.name, en.reimburse_to_customer, len(rows), ", ".join(ens))


def _billing_trading(task):
	from assistant.assistant.audit import _existing_draft
	existing = _existing_draft("Sales Invoice", "delivery_note", task.reference_name)
	if existing:
		return frappe.get_doc("Sales Invoice", existing), _("Sudah ada Sales Invoice draft {0} dari DN ini.").format(existing)
	from erpnext_custom.sales_invoice.mapping import make_sales_invoice_from_delivery_note
	si = make_sales_invoice_from_delivery_note(task.reference_name)
	_fill_address(si)
	si.insert()
	return si, _("Sales Invoice {0} draft dibuat dari {1}.").format(si.name, task.reference_name)


def check_journal(si_name, doctype="Sales Invoice"):
	"""Pemeriksaan pasti atas jurnal satu Sales/Purchase Invoice. Kembali daftar masalah (kosong = beres)."""
	si = frappe.get_doc(doctype, si_name)
	gl = frappe.get_all("GL Entry", filters={"voucher_type": doctype, "voucher_no": si_name, "is_cancelled": 0},
	                    fields=["account", "debit", "credit", "party"])
	problems = []
	if not gl:
		return [_("Tidak ada jurnal (GL Entry) untuk {0}.").format(si_name)] if not si.get("dont_post_to_gl") else []
	dr, cr = sum(flt(g.debit) for g in gl), sum(flt(g.credit) for g in gl)
	if abs(dr - cr) > 0.5:
		problems.append(_("Jurnal tidak seimbang: debit {0}, kredit {1}.").format(dr, cr))
	# piutang (SI, sisi debit) atau hutang (PI, sisi kredit) = total invoice
	party_acc, label, sign = (si.debit_to, _("Piutang"), 1) if doctype == "Sales Invoice" else (si.credit_to, _("Hutang"), -1)
	total = flt(si.base_rounded_total or si.base_grand_total)
	party = sign * sum(flt(g.debit) - flt(g.credit) for g in gl if g.account == party_acc)
	# lunas di tempat / POS / retur: saldo pihak memang tidak sama dengan total
	if total and not (si.get("is_paid") or si.get("is_pos") or si.get("is_return")) and abs(party - total) > 0.5:
		problems.append(_("{0} {1} = {2}, padahal total invoice {3}.").format(label, party_acc, party, total))
	for acc in {g.account for g in gl}:
		a = frappe.db.get_value("Account", acc, ["is_group", "disabled", "company"], as_dict=True) or {}
		if a.get("is_group") or a.get("disabled"):
			problems.append(_("Akun {0} adalah grup atau nonaktif.").format(acc))
		elif a.get("company") != si.company:
			problems.append(_("Akun {0} milik company lain.").format(acc))
	if si.get("custom_invoice_behavior") == "Reimburse":
		tax = sum(flt(r.tax) for r in si.get("custom_reimburse_items") or [])
		ppn = frappe.db.get_single_value("ERPNext Custom Setting", "tax_account")
		posted = sum(flt(g.credit) - flt(g.debit) for g in gl if g.account == ppn)
		if tax and abs(posted - tax * flt(si.conversion_rate or 1)) > 0.5:
			problems.append(_("PPN reimburse di jurnal {0} = {1}, padahal baris EN {2}.").format(ppn, posted, tax))
	return problems


def _accounting(task):
	problems = check_journal(task.reference_name, task.reference_doctype)
	if problems:
		return None, problems
	return None, _("Jurnal {0} beres: seimbang, {1} sesuai total, akun valid.").format(
		task.reference_name, _("piutang") if task.reference_doctype == "Sales Invoice" else _("hutang"))


def _as(user, fn, *args):
	"""Kerjakan atas nama user itu: izin dan pemilik dokumen = dia."""
	original = frappe.session.user
	frappe.set_user(user or "Administrator")
	try:
		return fn(*args)
	finally:
		frappe.set_user(original)


def run_task(task):
	"""Kerjakan satu langkah agent (antrean). Gagal atau ada temuan -> berhenti, ke Controller."""
	doc = frappe.get_doc("Agent Task", task)
	if doc.status == "Resolved" or doc.agent_role == USER:
		return
	ref = (doc.reference_doctype, doc.reference_name)
	other = _owned_by_other(ref, doc.agent_role)
	if other:
		orc._log(doc, "agent", _("Menunggu: dokumen masih dipegang langkah {0}.").format(other), actor="agent")
		doc.save(ignore_permissions=True)
		return
	pic = _pic(*ref) if doc.agent_role == BILLING else None
	frappe.db.savepoint("chain_step")
	try:
		if doc.agent_role == BILLING:
			fn = _billing_reimburse if doc.chain_id.startswith("Reimburse:") else _billing_trading
			si, note = _as(pic, fn, doc)
		else:
			si, note = _accounting(doc)
	except Exception as e:
		frappe.db.rollback(save_point="chain_step")
		doc.reload()
		why = frappe.utils.strip_html(str(e))[:400]
		_hand_to_controller(doc, _("{0} gagal: {1}").format(doc.agent_role, why))
		return
	if isinstance(note, list):  # temuan Accounting
		_hand_to_controller(doc, _("Temuan pemeriksaan jurnal:\n{0}").format("\n".join(f"- {p}" for p in note)), severity="High")
		return
	orc._resolve(doc, "Ditangani", note, "agent")
	if si and si.docstatus == 0:
		who = pic or None
		_task(doc.chain_id, "Validasi invoice", USER, _("Validasi Sales Invoice {0}").format(si.name),
		      _("{0}\n\nPeriksa lalu Validate. Sesudah divalidasi, Agent Accounting memeriksa jurnalnya.\n\nRiwayat rantai:\n{1}").format(
		          note, _history(doc.chain_id)), ("Sales Invoice", si.name), assign_to=who)
	elif si and si.docstatus == 1:  # tervalidasi otomatis (setting auto validate)
		_task(doc.chain_id, "Periksa jurnal", ACCOUNTING, _("Accounting: periksa jurnal {0}").format(si.name),
		      _("Sales Invoice {0} tervalidasi otomatis. Agent Accounting memeriksa jurnalnya.").format(si.name), ("Sales Invoice", si.name))
	frappe.db.commit()


def _hand_to_controller(doc, message, severity=None):
	controllers = orc._role_users(CONTROLLER)
	doc.status = "Open"
	doc.severity = severity or doc.severity
	doc.description = f"{doc.description}\n\n{message}"
	orc._add_watchers(doc, controllers)
	orc._log(doc, "escalate", _("Rantai berhenti, diserahkan ke Controller. {0}").format(message), actor="agent")
	doc.save(ignore_permissions=True)
	orc._notify(doc, controllers, _("Rantai berhenti: {0}").format(doc.subject))
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	orc._changed()


def run_pending():
	"""Tiap 15 menit: langkah agent yang belum tersentuh (antrean sempat mati)."""
	for name in frappe.get_all("Agent Task", filters={"source": "Chain", "status": "Open", "agent_role": ["!=", USER],
	                                                  "watchers": ["in", ["", None]]}, pluck="name"):
		run_task(name)


# --- API tab Rantai -------------------------------------------------------------------------


@frappe.whitelist()
def chains(limit=50, mine=0):
	"""Rantai terbaru beserta langkahnya, untuk tab Rantai. mine=1 (Laporan Saya): hanya rantai
	yang melibatkan user ini, walau dia manager."""
	user = frappe.session.user
	manager = orc._is_manager() and not cint(mine)
	rows = frappe.get_all("Agent Task", filters={"source": "Chain"},
	                      fields=["name", "chain_id", "chain_step", "agent_role", "status", "reference_doctype", "reference_name",
	                              "resolution", "assigned_to", "watchers", "creation", "severity"],
	                      order_by="creation desc", limit=1000)
	out = {}
	for r in rows:
		out.setdefault(r.chain_id, []).append(r)
	result = []
	for cid, steps in out.items():
		steps.sort(key=lambda s: s.creation)
		if not manager and not any(s.assigned_to == user or user in (s.watchers or "") for s in steps):
			continue
		kind, source = cid.split(":", 1)
		result.append({"chain": kind, "source": source, "steps": steps, "at": steps[-1].creation,
		               "stopped": any(s.status != "Resolved" and s.agent_role != USER and s.watchers for s in steps)})
	result.sort(key=lambda c: c["at"], reverse=True)
	return {"rows": result[: cint(limit) or 50],
	        "enabled": {k: _on(k) for k in SWITCH}}

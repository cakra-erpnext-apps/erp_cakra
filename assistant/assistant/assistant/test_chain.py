"""Cek rantai Reimburse: EN tervalidasi -> Billing (SI draft atas nama PIC) -> langkah user
-> validasi SI -> Accounting memeriksa jurnal. Juga: satu dokumen satu pemilik.

bench --site <situs> execute assistant.assistant.test_chain.run
Butuh satu Expense Note reimburse tervalidasi yang barisnya belum ditagih. Semua di-rollback
(commit dan antrean dimatikan selama tes).
"""

import frappe

from assistant.assistant import chain


def run():
	_reimburse()
	run_trading()
	run_purchase()


def _reimburse():
	frappe.set_user("Administrator")
	commit, enqueue = frappe.db.commit, frappe.enqueue
	frappe.db.commit = lambda *a, **k: None
	frappe.enqueue = lambda *a, **k: None
	try:
		frappe.db.set_single_value("ERPNext Custom Setting", "chain_reimburse_enabled", 1)
		# jalur dengan langkah user (validasi otomatis invoice Reimburse dimatikan selama tes)
		frappe.db.set_single_value("ERPNext Custom Setting", "invoice_type_reimburse_auto_validate", 0)
		from erpnext_custom.connection import used_reimburse_keys
		used = used_reimburse_keys()
		en_name = next(e.name for e in frappe.get_all("Expense Note", filters={"is_reimburse": 1, "validated": 1, "void": 0},
		                                               fields=["name"])
		               if any((e.name, i.item, i.expense_class) not in used for i in frappe.get_all(
		                   "Expense Note Item", filters={"parent": e.name}, fields=["item", "expense_class"])))

		# 1. kejadian: EN baru saja tervalidasi
		en = frappe.get_doc("Expense Note", en_name)
		before = frappe.copy_doc(en)
		before.validated = 0
		en._doc_before_save = before
		chain.on_expense_note(en)
		cid = f"Reimburse:{en_name}"
		billing = frappe.get_doc("Agent Task", {"chain_id": cid, "agent_role": chain.BILLING})

		# 2. Billing membuat SI Reimburse draft, lalu rantai berhenti di langkah user
		chain.run_task(billing.name)
		billing.reload()
		assert billing.status == "Resolved", billing.description
		step = frappe.get_doc("Agent Task", {"chain_id": cid, "agent_role": chain.USER})
		si = frappe.get_doc("Sales Invoice", step.reference_name)
		assert si.docstatus == 0 and si.custom_invoice_type == "Reimburse"
		assert any(r.expense_note == en_name for r in si.custom_reimburse_items)
		pic = chain._pic("Expense Note", en_name)
		assert si.owner == (pic or "Administrator") and step.assigned_to == pic, (si.owner, step.assigned_to)

		# 3. satu dokumen satu pemilik: agent lain menunggu selama langkah user masih memegang SI
		early = chain._task(cid, "Periksa jurnal", chain.ACCOUNTING, "uji", "uji", ("Sales Invoice", si.name))
		chain.run_task(early.name)
		assert frappe.db.get_value("Agent Task", early.name, "status") == "Open"
		frappe.delete_doc("Agent Task", early.name, ignore_permissions=True, force=True)

		# 4. user memvalidasi -> langkah user selesai -> Accounting memeriksa jurnal
		from erpnext_custom.workflow import validate_doc
		validate_doc("Sales Invoice", si.name)
		assert frappe.db.get_value("Agent Task", step.name, "status") == "Resolved"
		acc = frappe.get_doc("Agent Task", {"chain_id": cid, "agent_role": chain.ACCOUNTING})
		chain.run_task(acc.name)
		acc.reload()
		print("Accounting:", acc.status, acc.resolution or acc.description.splitlines()[-1])
		assert acc.status == "Resolved", acc.description
		assert not chain.check_journal(si.name)
		print("test_chain OK", en_name, "->", si.name)
	finally:
		frappe.db.commit, frappe.enqueue = commit, enqueue
		frappe.set_user("Administrator")
		frappe.db.rollback()


def run_trading():
	"""Rantai Trading: DN tervalidasi -> Billing membuat SI draft dari DN -> langkah user."""
	frappe.set_user("Administrator")
	commit, enqueue = frappe.db.commit, frappe.enqueue
	frappe.db.commit = lambda *a, **k: None
	frappe.enqueue = lambda *a, **k: None
	try:
		frappe.db.set_single_value("ERPNext Custom Setting", "chain_trading_enabled", 1)
		dn = frappe.get_doc("Delivery Note", frappe.get_all("Delivery Note", filters={"docstatus": 1, "per_billed": ["<", 100]},
		                                                     pluck="name", limit=1)[0])
		chain.on_delivery_note(dn)
		cid = f"Trading:{dn.name}"
		chain.run_task(frappe.db.get_value("Agent Task", {"chain_id": cid, "agent_role": chain.BILLING}))
		step = frappe.get_doc("Agent Task", {"chain_id": cid, "agent_role": chain.USER})
		si = frappe.get_doc("Sales Invoice", step.reference_name)
		assert si.docstatus == 0 and any(i.delivery_note == dn.name for i in si.items)
		print("test_chain trading OK", dn.name, "->", si.name)
	finally:
		frappe.db.commit, frappe.enqueue = commit, enqueue
		frappe.db.rollback()


def run_purchase():
	"""Rantai Pembelian: PI tervalidasi -> Accounting memeriksa jurnal PI."""
	frappe.set_user("Administrator")
	commit, enqueue = frappe.db.commit, frappe.enqueue
	frappe.db.commit = lambda *a, **k: None
	frappe.enqueue = lambda *a, **k: None
	try:
		frappe.db.set_single_value("ERPNext Custom Setting", "chain_purchase_enabled", 1)
		pi = frappe.get_doc("Purchase Invoice", frappe.get_all("Purchase Invoice", filters={"docstatus": 1}, pluck="name", limit=1)[0])
		chain.on_purchase_invoice(pi)
		t = frappe.db.get_value("Agent Task", {"chain_id": f"Pembelian:{pi.name}", "agent_role": chain.ACCOUNTING})
		chain.run_task(t)
		d = frappe.get_doc("Agent Task", t)
		print("Pembelian:", d.status, d.resolution or d.description.splitlines()[-1])
		assert d.status == "Resolved" or "Temuan" in d.description
		print("test_chain pembelian OK", pi.name)
	finally:
		frappe.db.commit, frappe.enqueue = commit, enqueue
		frappe.db.rollback()

"""Cek aturan email Packing List (auto-reply / review / info). Semua data di-rollback.

bench --site erp.localhost execute assistant.assistant.test_email_rules.run
bench --site erp.localhost execute assistant.assistant.test_email_rules.run --kwargs "{'live': 1}"
  (live = keputusan dari LLM sungguhan, hanya dicetak, tidak di-assert)
"""

import frappe

from assistant.assistant import fleet

BL, CTR, CUST_MAIL = "ZZTESTBL260901", "ZZTU1234567", "ops@customer-test.co.id"


def _canned(decision, topic):
	return f"KEPUTUSAN: {decision}\nTOPIK: {topic}\nALASAN: tes\nSUBJECT: Re: tes\nBODY:\nYth. Bapak/Ibu, ...\nTim CMI"


def _inbound(sender, subject, content):
	return frappe._dict(
		communication_type="Communication", sent_or_received="Received", sender=sender,
		subject=subject, content=content, reference_doctype=None, reference_name=None,
	)


def run(live=0):
	pl = frappe.get_all("Packing List", filters={"void": 0}, fields=["name", "customer", "owner"], limit=1)[0]
	sent, orig = [], {}
	try:
		# Data uji: BL di header, container di baris, kontak customer ber-email.
		frappe.db.set_value("Packing List", pl.name, "bl_no", BL, update_modified=False)
		frappe.get_doc({
			"doctype": "Packing List Item", "parent": pl.name, "parenttype": "Packing List",
			"parentfield": "items", "idx": 99, "container_no": CTR,
		}).db_insert()
		frappe.get_doc({
			"doctype": "Contact", "first_name": "ZZ Test Ops",
			"email_ids": [{"email_id": CUST_MAIL, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": pl.customer}],
		}).insert(ignore_permissions=True)

		s = frappe.get_single("Assistant Settings")
		s.auto_reply_enabled = 1
		rule = next(r for r in s.email_rules if r.menu == "Packing List")
		rule.enabled = 1
		out = {"text": ""}
		orig = {
			"_settings": fleet._settings, "send_mail": fleet.send_mail, "_complete": fleet._complete,
			"enqueue": frappe.enqueue, "commit": frappe.db.commit,
		}
		fleet._settings = lambda: s
		fleet.send_mail = lambda intake, **kw: sent.append(kw)
		if not live:
			fleet._complete = lambda sys_text, user_text: out["text"]
		frappe.enqueue = lambda method, **kw: frappe.get_attr(method)(**{k: v for k, v in kw.items() if k not in ("queue", "timeout")})
		frappe.db.commit = lambda: None

		# 1. Token: container berspasi tetap ketemu, BL ketemu.
		toks = fleet._email_tokens(f"Mohon info bl {BL} cont zztu 123456 7")
		assert BL in toks and CTR in toks, toks
		assert pl.name in fleet._match_packing_lists(f"cont {CTR}")
		assert CUST_MAIL in fleet._party_emails("Packing List", pl.name)

		def case(label, sender, subject, body, canned):
			out["text"] = canned
			before = (len(sent), frappe.db.count("Agent Mail", {"status": "draft"}),
				frappe.db.count("Notification Log", {"subject": ["like", "%tidak dibalas otomatis%"]}))
			fleet.on_communication_insert(_inbound(sender, subject, body))
			after = (len(sent), frappe.db.count("Agent Mail", {"status": "draft"}),
				frappe.db.count("Notification Log", {"subject": ["like", "%tidak dibalas otomatis%"]}))
			res = {"sent": after[0] - before[0], "draft": after[1] - before[1], "notif_owner": after[2] - before[2]}
			print(label, res)
			return res

		r = case("status, pengirim kontak", f"Ops <{CUST_MAIL}>", f"Status BL {BL}", "Kapal sudah berangkat?", _canned("REPLY", "STATUS"))
		agent = fleet.agent_for("Packing List", pl.name)
		assert agent, "agent PL harus dibuat"
		if not live:
			assert r == {"sent": 1, "draft": 0, "notif_owner": 0}, r
			r = case("topik tak dicentang", CUST_MAIL, f"BL {BL}", "Kirim copy BL", _canned("REPLY", "DOCUMENTS"))
			assert r == {"sent": 0, "draft": 1, "notif_owner": 0}, r
			r = case("tanya harga", CUST_MAIL, f"BL {BL}", "Berapa biaya storage?", _canned("REVIEW", "LAIN"))
			assert r == {"sent": 0, "draft": 1, "notif_owner": 0}, r
			r = case("FYI", CUST_MAIL, f"BL {BL}", "FYI saja", _canned("INFO", "LAIN"))
			assert r == {"sent": 0, "draft": 0, "notif_owner": 0}, r
			rule.enabled = 0
			r = case("aturan OFF", CUST_MAIL, f"BL {BL}", "Status?", _canned("REPLY", "STATUS"))
			assert r == {"sent": 0, "draft": 1, "notif_owner": 0}, r
			rule.enabled = 1
		else:
			case("harga (live)", CUST_MAIL, f"BL {BL}", "Berapa biaya storage per hari?", "")
			case("terima kasih (live)", CUST_MAIL, f"BL {BL}", "Terima kasih infonya.", "")
		r = case("pengirim asing", "someone@other.com", f"Status BL {BL}", "Status?", _canned("REPLY", "STATUS"))
		assert r["sent"] == 0 and r["notif_owner"] == 1, r
		for m in frappe.get_all("Agent Mail", filters={"agent_intake": agent}, fields=["role", "status", "auto", "subject"], order_by="creation"):
			print("  mail", m)
		if live:
			print("  sent", sent)
		print("OK")
	finally:
		fleet._settings = orig.get("_settings", fleet._settings)
		fleet.send_mail = orig.get("send_mail", fleet.send_mail)
		fleet._complete = orig.get("_complete", fleet._complete)
		frappe.enqueue = orig.get("enqueue", frappe.enqueue)
		frappe.db.commit = orig.get("commit", frappe.db.commit)
		frappe.db.rollback()

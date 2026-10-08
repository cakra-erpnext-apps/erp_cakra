"""Cek alur pemeriksaan: uji diam -> laporan -> final check -> pengecualian -> tutup sendiri.

bench --site <situs> execute assistant.assistant.test_audit.run
Butuh minimal satu Purchase Order tervalidasi yang lewat tanggal terima dan belum ber-PI.
Semua perubahan di-rollback.
"""

import frappe

from assistant.assistant import audit, orchestrator as orc


def _tasks(rule):
	return frappe.get_all("Agent Task", filters={"rule": rule.name, "status": ["!=", "Resolved"]},
	                      fields=["name", "reference_name", "shadow", "assigned_to", "status"])


def run():
	_fase_a()
	_fase_b()
	run_books()


def _fase_a():
	frappe.set_user("Administrator")
	try:
		rule = next(r for r in frappe.get_all("Orchestrator Rule", filters={"source": "Audit", "audit_check": "B1"},
		                                      fields=orc._RULE_FIELDS))
		rule.enabled, rule.shadow = 1, 1
		# mulai bersih apa pun keadaan lokalnya (di-rollback di akhir)
		open_tasks = frappe.get_all("Agent Task", filters={"rule": rule.name, "status": ["!=", "Resolved"]}, pluck="name")
		if open_tasks:
			frappe.db.delete("Agent Task Log", {"parent": ["in", open_tasks]})
			frappe.db.delete("Agent Task", {"name": ["in", open_tasks]})

		# 1. uji diam: temuan ada, tanpa PIC, Setuju tidak menjalankan perbaikan
		audit.scan_rule(rule)
		tasks = _tasks(rule)
		assert tasks, "tidak ada PO lewat tanggal untuk diuji"
		assert all(t.shadow and not t.assigned_to for t in tasks), tasks
		t0 = tasks[0]
		audit.decide(t0.name, "Setuju")
		d = frappe.get_doc("Agent Task", t0.name)
		assert d.decision == "Setuju" and not d.fix_result, "uji diam tidak boleh menjalankan perbaikan"

		# 2. uji diam dimatikan: temuan pindah ke PIC (pembuat PO yang aktif)
		pic = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User",
		                                      "name": ["not in", ["Administrator", "Guest"]]}, pluck="name", limit=1)[0]
		t1 = tasks[1]
		frappe.db.set_value("Purchase Order", t1.reference_name, "owner", pic, update_modified=False)
		rule.shadow = 0
		audit.scan_rule(rule)
		d = frappe.get_doc("Agent Task", t1.name)
		assert d.assigned_to == pic and not d.shadow, (d.assigned_to, d.shadow)
		rep = audit.report("team")
		assert any(r["name"] == t1.name for r in rep["todo"]), "temuan PIC harus ada di laporan tim"

		# 3. Setuju = Purchase Invoice draft dari PO; diulang tidak membuat draft kedua
		audit.decide(t1.name, "Setuju")
		d = frappe.get_doc("Agent Task", t1.name)
		pi = frappe.get_doc("Purchase Invoice", d.fix_result)
		assert pi.docstatus == 0 and pi.items[0].purchase_order == t1.reference_name
		assert audit.run_fix(d) == pi.name, "draft kedua tidak boleh dibuat"

		# 4. Tolak wajib alasan -> diajukan -> Controller setuju -> kondisi sama tidak muncul lagi
		t2 = tasks[2]
		try:
			audit.decide(t2.name, "Tolak")
			raise AssertionError("Tolak tanpa alasan harus ditolak")
		except frappe.ValidationError:
			pass
		audit.decide(t2.name, "Tolak", "PO jasa, tagihan vendor memang bulan depan")
		assert frappe.db.get_value("Agent Task", t2.name, "exception_status") == "Diajukan"
		audit.decide_exception(t2.name, 1)
		assert frappe.db.get_value("Agent Task", t2.name, ["status", "outcome"]) == ("Resolved", "Pengecualian")
		audit.scan_rule(rule)
		assert not frappe.db.exists("Agent Task", {"rule": rule.name, "reference_name": tasks[2].reference_name,
		                                           "status": ["!=", "Resolved"]}), "pengecualian harus meredam kondisi yang sama"

		# 5. kondisi beres -> tertutup sendiri
		t3 = tasks[3]
		frappe.db.set_value("Purchase Order", t3.reference_name, "per_billed", 100, update_modified=False)
		audit.scan_rule(rule)
		assert frappe.db.get_value("Agent Task", t3.name, "status") == "Resolved"

		# 6. reviewer: pemeriksaan yang sering ditolak turun ke "Perlu dicek"
		stats = audit.check_stats("B1")
		assert stats["Setuju"] >= 2 and stats["Tolak"] >= 1, stats
		print("test_audit OK", len(tasks), "temuan B1")
	finally:
		frappe.db.rollback()


def _fase_b():
	"""Otomatis: belum layak -> layak setelah 30 Setuju -> jalan atas nama PIC dalam batas nominal
	-> Batalkan menghapus draft dan menurunkan level -> eksekusi gagal juga menurunkan level."""
	frappe.set_user("Administrator")
	try:
		rule = next(r for r in frappe.get_all("Orchestrator Rule", filters={"source": "Audit", "audit_check": "B1"},
		                                      fields=orc._RULE_FIELDS))
		frappe.db.set_value("Orchestrator Rule", rule.name, {"enabled": 1, "shadow": 0, "autonomy": "Final check"})
		rule.update(enabled=1, shadow=0, autonomy="Final check")
		old = frappe.get_all("Agent Task", filters={"source": "Audit", "audit_check": "B1"}, pluck="name")
		if old:
			frappe.db.delete("Agent Task Log", {"parent": ["in", old]})
			frappe.db.delete("Agent Task", {"name": ["in", old]})
		assert not audit.promotion(rule)["eligible"]

		# 30 keputusan Setuju -> layak
		for i in range(audit.PROMOTE_MIN):
			frappe.get_doc({"doctype": "Agent Task", "subject": f"riwayat {i}", "source": "Audit", "status": "Resolved",
			                "audit_check": "B1", "decision": "Setuju", "decision_at": frappe.utils.now_datetime(),
			                "dedupe_key": f"test:hist:{i}"}).insert(ignore_permissions=True)
		p = audit.promotion(rule)
		assert p["eligible"], p["reasons"]

		# PIC = user dengan izin buat PI; dua PO: satu di bawah batas, satu di atas
		pic = frappe.get_doc({"doctype": "User", "email": "audit.pic@test.local", "first_name": "PIC", "send_welcome_email": 0,
		                      "roles": [{"role": "Accounts User"}, {"role": "Purchase User"}]}).insert(ignore_permissions=True).name
		pos = frappe.db.sql("""select name, base_grand_total from `tabPurchase Order` where docstatus = 1
		                       and status not in ('Closed', 'Completed') and per_billed < 100
		                       and schedule_date < curdate() - interval 3 day order by base_grand_total""", as_dict=True)
		small, big = pos[0], pos[-1]
		assert small.base_grand_total < big.base_grand_total, "butuh PO dengan nilai berbeda"
		for po in pos:
			frappe.db.set_value("Purchase Order", po.name, "owner", pic, update_modified=False)
		audit.set_autonomy(rule.name, "Otomatis", max_amount=small.base_grand_total)
		rule.update(frappe.db.get_value("Orchestrator Rule", rule.name, ["autonomy", "max_amount"], as_dict=True))
		audit.scan_rule(rule)
		t_small = frappe.get_doc("Agent Task", {"dedupe_key": f"audit:B1:{small.name}"})
		t_big = frappe.get_doc("Agent Task", {"dedupe_key": f"audit:B1:{big.name}"})
		assert t_small.decision == "Otomatis" and t_small.fix_result, (t_small.decision, t_small.fix_result)
		assert frappe.db.get_value("Purchase Invoice", t_small.fix_result, "owner") == pic
		assert not t_big.decision, "di atas batas nominal harus tetap ke final check"

		# Batalkan hasil otomatis -> draft hilang, temuan kembali, level turun
		pi = t_small.fix_result
		audit.undo(t_small.name)
		assert not frappe.db.exists("Purchase Invoice", pi)
		t_small.reload()
		assert t_small.undone and not t_small.decision and t_small.status == "Open"
		assert frappe.db.get_value("Orchestrator Rule", rule.name, "autonomy") == "Final check"

		# eksekusi gagal (PIC tanpa izin) -> level turun, temuan tetap menunggu final check
		frappe.db.set_value("Orchestrator Rule", rule.name, "autonomy", "Otomatis")
		rule.autonomy, rule.max_amount = "Otomatis", 0
		nobody = frappe.get_doc({"doctype": "User", "email": "audit.noperm@test.local", "first_name": "NoPerm",
		                         "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.db.set_value("Agent Task", t_big.name, "assigned_to", nobody.name)
		audit.scan_rule(rule)
		assert not frappe.db.get_value("Agent Task", t_big.name, "decision")
		assert frappe.db.get_value("Orchestrator Rule", rule.name, "autonomy") == "Final check"
		print("test_audit fase B OK")
	finally:
		frappe.set_user("Administrator")
		frappe.db.rollback()


def run_books():
	"""Kesehatan Buku dan E1 atas data buatan (rollback)."""
	frappe.set_user("Administrator")
	rule = frappe._dict(threshold_hours=0)
	try:
		# K1 + K2: satu baris GL tambahan membuat voucher dan neraca saldo tidak seimbang
		gle = frappe.get_all("GL Entry", filters={"is_cancelled": 0, "voucher_type": "Journal Entry"},
		                     fields=["name", "voucher_no", "company"], limit=1)[0]
		row = frappe.get_doc("GL Entry", gle.name).as_dict()
		row.update(name="test-k1", debit=1234, credit=0, debit_in_account_currency=1234, credit_in_account_currency=0)
		cols = [c for c in frappe.db.get_table_columns("GL Entry") if c in row]
		frappe.db.sql(f"insert into `tabGL Entry` ({', '.join(f'`{c}`' for c in cols)}) values ({', '.join(['%s'] * len(cols))})",
		              [row[c] for c in cols])
		assert any(f.name == gle.voucher_no for f in audit.check_k1(rule)), "K1"
		assert any(f.name == gle.company for f in audit.check_k2(rule)), "K2"

		# K6: Payment Entry tervalidasi yang jurnalnya hilang
		pe = frappe.get_all("Payment Entry", filters={"docstatus": 1}, pluck="name", limit=1)
		if pe:
			frappe.db.delete("GL Entry", {"voucher_type": "Payment Entry", "voucher_no": pe[0]})
			assert any(f.name == pe[0] for f in audit.check_k6(rule)), "K6"

		# K8: tutup bulanan aktif, bulan lalu ber-GL, belum ada PCV
		cp = frappe.get_all("CMI Period Close", filters={"parenttype": "ERPNext Custom Setting"}, fields=["name", "company"], limit=1)
		if cp:
			frappe.db.set_value("CMI Period Close", cp[0].name, "monthly_roll", 1)
			k8 = audit.check_k8(frappe._dict(threshold_hours=1))
			has_gl = frappe.db.exists("GL Entry", {"company": cp[0].company, "posting_date": ["<", frappe.utils.get_first_day(frappe.utils.today())]})
			assert bool(k8) == bool(has_gl and not frappe.db.exists("Period Closing Voucher", {"company": cp[0].company, "docstatus": 1})), k8

		# E1: 5 job dengan estimasi sama selalu memakai item X; job keenam belum -> temuan
		est, item = "TEST-EST-E1", frappe.get_all("Item", pluck="name", limit=1)[0]
		frappe.db.sql("""insert into `tabCRM Estimation Detail` (name, parent, parenttype, parentfield, type_id, is_expense)
		                 values ('TEST-ESTD-E1', %s, 'CRM Estimation', 'expense_items', %s, 1)""", (est, item))
		old = frappe.utils.add_days(frappe.utils.today(), -40)
		for i in range(6):
			pl = f"TEST-E1-{i}"
			frappe.db.sql("insert into `tabPacking List` (name, date, estimation, void, closed, docstatus) values (%s, %s, %s, 0, %s, 0)",
			              (pl, old, est, 1 if i < 5 else 0))
			if i < 5:
				frappe.db.sql("insert into `tabExpense Note` (name, packing_list, void, docstatus) values (%s, %s, 0, 0)", (f"TEST-EN-{i}", pl))
				frappe.db.sql("""insert into `tabExpense Note Item` (name, parent, parenttype, parentfield, item)
				                 values (%s, %s, 'Expense Note', 'items', %s)""", (f"TEST-ENI-{i}", f"TEST-EN-{i}", item))
		e1 = audit.check_e1(rule)
		assert any(f.name == "TEST-E1-5" and item in f.subject for f in e1), [f.subject for f in e1]
		assert not any(f.name.startswith("TEST-E1-") and f.name != "TEST-E1-5" for f in e1)
		print("test_audit kesehatan buku + E1 OK")
	finally:
		frappe.db.rollback()

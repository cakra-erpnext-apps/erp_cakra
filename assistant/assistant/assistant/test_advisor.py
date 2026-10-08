"""Cek penasihat: aturan saran (angka buatan) + tinjauan atas data situs (di-rollback).

bench --site <situs> execute assistant.assistant.test_advisor.run
"""

import frappe

from assistant.assistant import advisor as adv


def run():
	# customer: piutang menua -> saran; telat bayar memburuk -> saran; baik-baik saja -> tidak
	c = adv.flag_customers([
		{"customer": "A", "overdue": 5_000_000, "oldest_days": 75, "late_now": [], "late_prev": []},
		{"customer": "B", "overdue": 0, "oldest_days": 0, "late_now": [30, 34], "late_prev": [5, 10]},
		{"customer": "C", "overdue": 500_000, "oldest_days": 90, "late_now": [3, 4], "late_prev": [2]},
	])
	assert [x["key"] for x in c] == ["A", "B"], c
	assert "mulai telat bayar" in c[1]["subject"]

	# vendor: naik 50% dan 10 jt -> saran; naik 50% tapi cuma 1 jt -> tidak; vendor baru -> tidak
	v = adv.flag_vendor_cost([{"vendor": "X", "now": 30_000_000, "prev_avg": 20_000_000},
	                          {"vendor": "Y", "now": 3_000_000, "prev_avg": 2_000_000},
	                          {"vendor": "Z", "now": 9_000_000, "prev_avg": 0}])
	assert [x["key"] for x in v] == ["X"], v

	late = adv.flag_vendor_late([{"vendor": "L", "delays": [10, 8, 12]}, {"vendor": "M", "delays": [20, 30]}])
	assert [x["key"] for x in late] == ["L"], late  # M baru 2 PI

	# rute: margin 30% -> 10% turun 20 poin -> saran; margin negatif -> saran; 1 job -> tidak
	r = adv.flag_routes([
		{"route": "P ke Q", "now": {"jobs": 3, "rev": 100, "cost": 90}, "prev": {"jobs": 4, "rev": 100, "cost": 70}, "top_vendor": ("V", 50)},
		{"route": "R ke S", "now": {"jobs": 2, "rev": 100, "cost": 120}, "prev": {"jobs": 0, "rev": 0, "cost": 0}, "top_vendor": None},
		{"route": "T ke U", "now": {"jobs": 1, "rev": 100, "cost": 150}, "prev": {"jobs": 0, "rev": 0, "cost": 0}, "top_vendor": None},
	])
	assert {x["key"] for x in r} == {"P ke Q", "R ke S"}, r
	assert "V" in next(x for x in r if x["key"] == "P ke Q")["facts"]

	# tinjauan atas data situs: tidak error, saran jadi task, keputusan tercatat
	frappe.set_user("Administrator")
	commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		items, start, end = adv.review()
		res = adv.run_month(force=1)
		print("tinjauan", res, [i["subject"] for i in items])
		names = frappe.get_all("Agent Task", filters={"source": "Advisor", "status": "Open"}, pluck="name")
		if not names:  # data situs belum memicu saran: pakai satu saran buatan
			names = [frappe.get_doc({"doctype": "Agent Task", "subject": "uji saran", "source": "Advisor", "status": "Open",
			                         "audit_check": "customer", "dedupe_key": "test:advisor"}).insert(ignore_permissions=True).name]
		if names:
			follow = adv.decide(names[0], "Tindak lanjuti", "uji", assign_to="Administrator")
			assert frappe.db.get_value("Agent Task", names[0], ["status", "decision"]) == ("Resolved", "Tindak lanjuti")
			assert frappe.db.get_value("Agent Task", follow, "source") == "Manual"
		rep = adv.report()
		assert {u["kind"] for u in rep["useful"]} == set(adv.KINDS)
		print("test_advisor OK")
	finally:
		frappe.db.commit = commit
		frappe.db.rollback()

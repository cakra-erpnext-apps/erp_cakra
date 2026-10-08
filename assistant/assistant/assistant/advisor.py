"""Penasihat (Fase D Tangga Otonomi Agent): tinjauan bulanan dengan saran keputusan bisnis.

Agent tidak bertindak, hanya menyarankan dengan angka pendukung. Controller memutuskan:
Tindak lanjuti (boleh langsung jadi task manual untuk orang lain) atau Abaikan (wajib alasan).
Keputusan itu dihitung per jenis saran, supaya terlihat saran mana yang berguna.

Tiga tinjauan, semua rumus pasti (AI tetap tersedia lewat "Tanya Agent" di task):
- Customer: piutang lewat jatuh tempo dan rata-rata hari telat bayar, dibanding 3 bulan sebelumnya.
- Vendor: biaya Expense Note naik tajam dibanding rata-rata 3 bulan sebelumnya; vendor yang
  Purchase Invoice-nya rata-rata jauh lewat tanggal terima PO.
- Rute: margin per rute (pendapatan Sales Invoice - biaya Expense Note per job), 3 bulan terakhir
  dibanding 3 bulan sebelumnya.

Saran = Agent Task sumber "Advisor", satu per hal per bulan. Saran bulan lalu yang belum
diputuskan ditutup saat tinjauan berikutnya jalan (sudah diganti angka baru).
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, date_diff, flt, get_first_day, get_last_day, getdate, now_datetime, today

from assistant.assistant import orchestrator as orc
from assistant.assistant.audit import _money

TOP = 10
CONTROLLER = "Orchestrator Controller"
# ambang saran
CUST_OVERDUE_DAYS, CUST_OVERDUE_MIN, CUST_LATE_JUMP = 60, 1_000_000, 15
VENDOR_JUMP_PCT, VENDOR_JUMP_MIN = 0.30, 5_000_000
VENDOR_LATE_DAYS, VENDOR_LATE_MIN_N = 7, 3
ROUTE_DROP_PTS, ROUTE_MIN_JOBS = 10, 2
KINDS = {"customer": _("Customer"), "vendor_cost": _("Biaya vendor"), "vendor_late": _("Vendor telat"), "route": _("Margin rute")}


def _on():
	v = frappe.db.sql("select value from `tabSingles` where doctype = 'ERPNext Custom Setting' and field = 'orchestrator_advisor_enabled'")
	return orc.switch_on() and bool(v and cint(v[0][0]))


def _avg(xs):
	return sum(xs) / len(xs) if xs else None


# --- aturan saran (fungsi murni: data masuk, saran keluar) ----------------------------------


def flag_customers(rows):
	"""rows: [{customer, overdue, oldest_days, late_now: [hari], late_prev: [hari]}]"""
	out = []
	for r in rows:
		now, prev = _avg(r["late_now"]), _avg(r["late_prev"])
		aging = r["overdue"] >= CUST_OVERDUE_MIN and r["oldest_days"] >= CUST_OVERDUE_DAYS
		worse = now is not None and prev is not None and len(r["late_now"]) >= 2 and now - prev >= CUST_LATE_JUMP
		if not (aging or worse):
			continue
		facts = [_("Piutang lewat jatuh tempo {0}, tertua {1} hari.").format(_money(r["overdue"]), r["oldest_days"])] if r["overdue"] else []
		if now is not None:
			facts.append(_("Rata-rata telat bayar periode ini {0} hari ({1} invoice){2}.").format(
				round(now), len(r["late_now"]), _(", 3 bulan sebelumnya {0} hari").format(round(prev)) if prev is not None else ""))
		out.append({"kind": "customer", "key": r["customer"], "amount": r["overdue"],
		            "subject": _("{0} mulai telat bayar").format(r["customer"]) if worse else _("{0}: piutang menua").format(r["customer"]),
		            "facts": " ".join(facts),
		            "advice": _("Hubungi customer untuk jadwal bayar, pertimbangkan menahan kredit atau minta uang muka untuk job berikutnya.")})
	return sorted(out, key=lambda x: -x["amount"])[:TOP]


def flag_vendor_cost(rows):
	"""rows: [{vendor, now, prev_avg}] biaya bulan ini vs rata-rata 3 bulan sebelumnya."""
	out = []
	for r in rows:
		if r["prev_avg"] <= 0:
			continue
		jump = r["now"] - r["prev_avg"]
		if jump >= VENDOR_JUMP_MIN and jump / r["prev_avg"] >= VENDOR_JUMP_PCT:
			out.append({"kind": "vendor_cost", "key": r["vendor"], "amount": jump,
			            "subject": _("Biaya {0} naik {1}%").format(r["vendor"], round(100 * jump / r["prev_avg"])),
			            "facts": _("Biaya bulan ini {0}, rata-rata 3 bulan sebelumnya {1}.").format(_money(r["now"]), _money(r["prev_avg"])),
			            "advice": _("Cek apakah karena volume job naik atau tarif naik. Kalau tarif, bandingkan dengan vendor lain atau negosiasi ulang.")})
	return sorted(out, key=lambda x: -x["amount"])[:TOP]


def flag_vendor_late(rows):
	"""rows: [{vendor, delays: [hari PI lewat tanggal terima PO]}]"""
	out = []
	for r in rows:
		avg = _avg(r["delays"])
		if avg is not None and len(r["delays"]) >= VENDOR_LATE_MIN_N and avg >= VENDOR_LATE_DAYS:
			out.append({"kind": "vendor_late", "key": r["vendor"], "amount": avg * len(r["delays"]),
			            "subject": _("{0} sering telat, rata-rata {1} hari").format(r["vendor"], round(avg)),
			            "facts": _("{0} Purchase Invoice 90 hari terakhir, rata-rata {1} hari lewat tanggal terima PO, paling lama {2} hari.").format(
			                len(r["delays"]), round(avg), max(r["delays"])),
			            "advice": _("Bicarakan jadwal kirim dengan vendor, majukan tanggal PO, atau siapkan vendor cadangan.")})
	return sorted(out, key=lambda x: -x["amount"])[:TOP]


def flag_routes(rows):
	"""rows: [{route, now: {jobs, rev, cost}, prev: {jobs, rev, cost}, top_vendor}]"""
	out = []
	for r in rows:
		n, p = r["now"], r["prev"]
		if n["jobs"] < ROUTE_MIN_JOBS or n["rev"] <= 0:
			continue
		m_now = (n["rev"] - n["cost"]) / n["rev"]
		m_prev = (p["rev"] - p["cost"]) / p["rev"] if p["rev"] > 0 and p["jobs"] >= ROUTE_MIN_JOBS else None
		if not (m_now < 0 or (m_prev is not None and (m_prev - m_now) * 100 >= ROUTE_DROP_PTS)):
			continue
		facts = _("{0} job, pendapatan {1}, biaya {2}, margin {3}%{4}.").format(
			n["jobs"], _money(n["rev"]), _money(n["cost"]), round(100 * m_now),
			_(" (3 bulan sebelumnya {0}%)").format(round(100 * m_prev)) if m_prev is not None else "")
		if r.get("top_vendor"):
			facts += " " + _("Biaya terbesar: {0} ({1}).").format(r["top_vendor"][0], _money(r["top_vendor"][1]))
		out.append({"kind": "route", "key": r["route"], "amount": n["rev"] - n["cost"],
		            "subject": _("Margin rute {0} {1}").format(r["route"], _("negatif") if m_now < 0 else _("turun")),
		            "facts": facts,
		            "advice": _("Tinjau tarif quotation rute ini dan biaya vendor terbesarnya sebelum menerima job berikutnya.")})
	return sorted(out, key=lambda x: x["amount"])[:TOP]


# --- data -----------------------------------------------------------------------------------


def _customer_rows(start, end):
	prev_start = add_months(start, -3)
	overdue = {r.customer: r for r in frappe.db.sql(
		"""select customer, sum(base_grand_total * outstanding_amount / grand_total) overdue, min(due_date) oldest
		   from `tabSales Invoice` where docstatus = 1 and is_return = 0 and outstanding_amount > 0
		     and grand_total > 0 and due_date < %s group by customer""", end, as_dict=True)}
	paid = frappe.db.sql(
		"""select si.customer, si.due_date, max(ple.posting_date) paid_on
		   from `tabSales Invoice` si join `tabPayment Ledger Entry` ple
		     on ple.against_voucher_type = 'Sales Invoice' and ple.against_voucher_no = si.name
		    and ple.voucher_no != si.name and ple.delinked = 0
		   where si.docstatus = 1 and si.is_return = 0 and si.outstanding_amount <= 0
		   group by si.name having paid_on between %s and %s""", (prev_start, end), as_dict=True)
	late = {}
	for p in paid:
		bucket = "now" if getdate(p.paid_on) >= getdate(start) else "prev"
		late.setdefault(p.customer, {"now": [], "prev": []})[bucket].append(max(date_diff(p.paid_on, p.due_date), 0))
	out = []
	for c in set(overdue) | set(late):
		o = overdue.get(c)
		out.append({"customer": c, "overdue": flt(o.overdue) if o else 0,
		            "oldest_days": date_diff(end, o.oldest) if o else 0,
		            "late_now": late.get(c, {}).get("now", []), "late_prev": late.get(c, {}).get("prev", [])})
	return out


def _vendor_cost_rows(start, end):
	prev_start = add_months(start, -3)
	rows = frappe.db.sql(
		"""select vendor, sum(if(date >= %(s)s, cost, 0)) now, sum(if(date < %(s)s, cost, 0)) / 3 prev_avg
		   from (select vendor, date, net_total * ifnull(nullif(conversion_rate, 0), 1) cost from `tabExpense Note`
		         where validated = 1 and void = 0 and date between %(p)s and %(e)s) x
		   group by vendor""", {"s": start, "p": prev_start, "e": end}, as_dict=True)
	return [{"vendor": r.vendor, "now": flt(r.now), "prev_avg": flt(r.prev_avg)} for r in rows if r.vendor]


def _vendor_late_rows(end):
	rows = frappe.db.sql(
		"""select pi.supplier, datediff(pi.posting_date, po.schedule_date) delay
		   from `tabPurchase Invoice` pi
		   join (select distinct parent, purchase_order from `tabPurchase Invoice Item` where ifnull(purchase_order, '') != '') i
		     on i.parent = pi.name
		   join `tabPurchase Order` po on po.name = i.purchase_order
		   where pi.docstatus = 1 and pi.posting_date between %s and %s""", (add_months(end, -3), end), as_dict=True)
	by = {}
	for r in rows:
		by.setdefault(r.supplier, []).append(max(cint(r.delay), 0))
	return [{"vendor": v, "delays": d} for v, d in by.items()]


def _route_rows(end):
	"""Job tertagih per rute, 3 bulan terakhir vs 3 bulan sebelumnya (tanggal job)."""
	now_start, prev_start = add_months(end, -3), add_months(end, -6)
	jobs = []
	for dt, origin, dest in (("Packing List", "origin_location", "destination_location"),
	                         ("Shipping List", "origin_location", "destination_location")):
		jobs += [dict(r, dt=dt) for r in frappe.db.sql(
			f"""select name, date, {origin} origin, {dest} dest from `tab{dt}`
			    where ifnull(void, 0) = 0 and date between %s and %s
			      and ifnull({origin}, '') != '' and ifnull({dest}, '') != ''""", (prev_start, end), as_dict=True)]
	if not jobs:
		return []
	names = [j["name"] for j in jobs]
	rev = dict(frappe.db.sql(
		"""select i.custom_source, sum(i.base_net_amount) from `tabSales Invoice Item` i
		   join `tabSales Invoice` si on si.name = i.parent
		   where si.docstatus = 1 and ifnull(si.custom_invoice_behavior, '') != 'Reimburse' and i.custom_source in %s
		   group by i.custom_source""", [names]))
	cost_rows = frappe.db.sql(
		"""select coalesce(nullif(packing_list, ''), shipping_list) job, vendor, sum(net_total * ifnull(nullif(conversion_rate, 0), 1)) cost
		   from `tabExpense Note` where validated = 1 and void = 0 and is_reimburse = 0
		     and coalesce(nullif(packing_list, ''), shipping_list) in %s group by job, vendor""", [names], as_dict=True)
	cost, vendor_cost = {}, {}
	for c in cost_rows:
		cost[c.job] = cost.get(c.job, 0) + flt(c.cost)
		vendor_cost[(c.job, c.vendor)] = flt(c.cost)
	routes = {}
	for j in jobs:
		if not flt(rev.get(j["name"])):
			continue  # belum ditagih: margin belum bisa dihitung
		r = routes.setdefault(f"{j['origin']} ke {j['dest']}", {"now": {"jobs": 0, "rev": 0, "cost": 0},
		                                                        "prev": {"jobs": 0, "rev": 0, "cost": 0}, "vendors": {}})
		b = r["now"] if getdate(j["date"]) > getdate(now_start) else r["prev"]
		b["jobs"] += 1
		b["rev"] += flt(rev[j["name"]])
		b["cost"] += cost.get(j["name"], 0)
		if b is r["now"]:
			for (job, v), c in vendor_cost.items():
				if job == j["name"]:
					r["vendors"][v] = r["vendors"].get(v, 0) + c
	return [{"route": k, "now": v["now"], "prev": v["prev"],
	         "top_vendor": max(v["vendors"].items(), key=lambda x: x[1]) if v["vendors"] else None} for k, v in routes.items()]


# --- tinjauan -------------------------------------------------------------------------------


def review(month_end=None):
	"""Semua saran untuk bulan yang berakhir di month_end (bawaan: bulan lalu)."""
	end = getdate(month_end) if month_end else get_last_day(add_months(today(), -1))
	start = get_first_day(end)
	return (flag_customers(_customer_rows(start, end)) + flag_vendor_cost(_vendor_cost_rows(start, end))
	        + flag_vendor_late(_vendor_late_rows(end)) + flag_routes(_route_rows(end))), start, end


def _period(start):
	return getdate(start).strftime("%Y-%m")


@frappe.whitelist()
def run_month(month_end=None, force=0):
	"""Tinjauan bulanan (cron tanggal 1). force=1 dari tombol Jalankan Sekarang, walau saklar mati."""
	if not cint(force) and not _on():
		return {"skipped": True}
	if cint(force):
		orc._need_manager()
	items, start, end = review(month_end)
	period = _period(start)
	made = []
	for it in items:
		key = f"advisor:{period}:{it['kind']}:{it['key']}"
		if frappe.db.exists("Agent Task", {"dedupe_key": key}):
			continue
		desc = f"{it['facts']}\n{_('Saran')}: {it['advice']}"
		doc = frappe.get_doc({
			"doctype": "Agent Task", "subject": it["subject"][:140], "source": "Advisor", "status": "Open", "severity": "Medium",
			"dedupe_key": key, "description": desc, "event_at": now_datetime(), "amount": flt(it["amount"]),
			"category": KINDS[it["kind"]], "audit_check": it["kind"], "since_date": start,
			"workflow": _("Tinjauan {0}").format(period),
		})
		orc._log(doc, "event", desc, actor="agent")
		doc.insert(ignore_permissions=True)
		made.append(doc.name)
	# saran bulan sebelumnya yang belum diputuskan sudah diganti angka baru
	for name in frappe.get_all("Agent Task", filters={"source": "Advisor", "status": "Open", "decision": ["in", ["", None]],
	                                                  "since_date": ["<", start]}, pluck="name"):
		orc._resolve(frappe.get_doc("Agent Task", name), "Normal", _("Diganti tinjauan {0}.").format(period), "agent")
	if made:
		users = orc._role_users(CONTROLLER)
		subject = _("Tinjauan {0}: {1} saran dari agent").format(period, len(made))
		for u in users:
			frappe.get_doc({"doctype": "Notification Log", "subject": subject, "for_user": u, "type": "Alert",
			                "link": "/app/orchestrator?view=advice"}).insert(ignore_permissions=True)
		emails = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
		if emails:
			frappe.sendmail(recipients=emails, subject=subject, message=_digest(made, period))
	frappe.db.commit()
	orc._changed()
	return {"period": period, "made": len(made), "found": len(items)}


def monthly():
	run_month()


def _digest(names, period):
	rows = frappe.get_all("Agent Task", filters={"name": ["in", names]}, fields=["subject", "description", "category"])
	esc = frappe.utils.escape_html
	items = "".join(f"<li><b>{esc(r.category)}: {esc(r.subject)}</b><br><span style='white-space:pre-line'>{esc(r.description)}</span></li>" for r in rows)
	return (f"<p>{_('Tinjauan bulan {0}. Agent hanya menyarankan; putuskan Tindak lanjuti atau Abaikan di halaman Orchestrator.').format(period)}</p>"
	        f"<ul>{items}</ul><p><a href='{frappe.utils.get_url()}/app/orchestrator?view=advice'>{_('Buka saran')}</a></p>")


# --- keputusan & laporan --------------------------------------------------------------------


@frappe.whitelist()
def decide(task, decision, note, assign_to=None):
	"""Tindak lanjuti (catat tindakan; boleh langsung jadi task manual untuk orang lain) atau Abaikan."""
	orc._need_manager()
	note = (note or "").strip()
	if decision not in ("Tindak lanjuti", "Abaikan") or not note:
		frappe.throw(_("Pilih Tindak lanjuti atau Abaikan, dan tulis tindakan atau alasannya."))
	doc = frappe.get_doc("Agent Task", task)
	if doc.source != "Advisor" or doc.status == "Resolved":
		frappe.throw(_("Saran ini sudah diputuskan."))
	doc.update({"decision": decision, "decision_note": note, "decision_by": frappe.session.user, "decision_at": now_datetime()})
	follow = None
	if decision == "Tindak lanjuti" and assign_to:
		follow = orc.create_manual(subject=doc.subject, description=f"{doc.description}\n\n{_('Tindakan')}: {note}",
		                           assign_to=assign_to, response_minutes=1440)
		note = f"{note} ({_('task {0} untuk {1}').format(follow, assign_to)})"
	orc._resolve(doc, "Ditangani" if decision == "Tindak lanjuti" else "Normal", note, frappe.session.user)
	return follow


@frappe.whitelist()
def report():
	orc._need_manager()
	rows = frappe.get_all("Agent Task", filters={"source": "Advisor", "status": "Open"},
	                      fields=["name", "subject", "description", "category", "audit_check", "amount", "since_date", "creation"],
	                      order_by="creation desc", limit=200)
	useful = {k: dict(frappe.db.sql(
		"""select decision, count(*) from `tabAgent Task` where source = 'Advisor' and audit_check = %s
		   and decision in ('Tindak lanjuti', 'Abaikan') and decision_at > %s group by decision""",
		(k, add_months(today(), -12)))) for k in KINDS}
	return {"rows": rows, "enabled": _on(),
	        "useful": [{"kind": k, "title": v, "follow": useful[k].get("Tindak lanjuti", 0), "ignore": useful[k].get("Abaikan", 0)}
	                   for k, v in KINDS.items()]}

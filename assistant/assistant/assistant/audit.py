"""Pemeriksaan (tahap 2 Tangga Otonomi Agent): agent memeriksa, mereview, menyusun laporan;
user hanya final check.

- Benar/salah ditentukan aturan pasti (SQL) di CHECKS, bukan AI. Hasilnya bisa diulang dan
  murah dijalankan. AI tetap tersedia lewat "Analisa Agent" di task (orchestrator.write_agent_note).
- Satu baris Orchestrator Rule bersumber "Audit" = satu pemeriksaan (kolom audit_check).
  threshold_hours = masa tenggang sebelum jadi temuan.
- review() = pemeriksa kedua: buang temuan yang sudah dikecualikan Controller (selama kondisinya
  sama), turunkan keyakinan pemeriksaan yang sering ditolak, alihkan temuan tanpa PIC ke Controller.
- Uji Diam (rule.shadow): temuan dibuat tapi hanya terlihat Controller/Admin, dan Setujui tidak
  menjalankan perbaikan. Dipakai mengukur temuan palsu sebelum laporan sampai ke user.
- Temuan = Agent Task source "Audit" tanpa batas menit (due_at kosong): tidak dieskalasi per
  menit, tidak dikabari satu per satu. User menerima satu laporan harian (send_digest).
- Kondisi beres -> task tertutup sendiri. Keputusan user disimpan terstruktur (buku keputusan).
- Tahap 3 (rule.autonomy = "Otomatis"): agent menjalankan perbaikan sendiri atas nama PIC,
  memverifikasi hasilnya, mencatat jejak sebelum/sesudah. Naik level hanya oleh Admin setelah
  promotion() terpenuhi; turun sendiri (_demote) kalau hasilnya dibatalkan user atau gagal.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, date_diff, flt, fmt_money, get_url, getdate, now_datetime, today

from assistant.assistant import orchestrator as orc

PASTI, CEK = "Pasti", "Perlu dicek"
# Pemeriksaan dengan keputusan sebanyak ini atau lebih, dan ditolak/dikoreksi sesering ini,
# keyakinannya diturunkan ke "Perlu dicek" (tidak ikut Setujui Semua).
REVIEW_MIN_DECISIONS, REVIEW_MAX_REJECT = 5, 0.2
REPORT_MAX_ROWS = 30
# Syarat naik ke Otomatis: minimal sekian keputusan user, sekian persen Setuju tanpa koreksi,
# dan sekian keputusan terakhir bersih dari Tolak maupun Batal.
PROMOTE_MIN, PROMOTE_RATE, PROMOTE_CLEAN = 30, 0.95, 20
AUTO = "Otomatis"


def _f(**kw):
	return frappe._dict(kw)


def _cutoff(rule, default_days):
	hours = cint(rule.threshold_hours) or default_days * 24
	return add_to_date(now_datetime(), hours=-hours).date()


def _holder(doctype, name):
	return orc._doc_holder(doctype, name)


def _money(v):
	return fmt_money(flt(v), currency="IDR", precision=0)


# --- pemeriksaan ----------------------------------------------------------------------------


def check_s1(rule):
	"""Sales Order lewat tanggal kirim, belum ditagih penuh."""
	out = []
	for so in frappe.db.sql(
		"""select name, customer, delivery_date, per_billed, base_grand_total
		   from `tabSales Order`
		   where docstatus = 1 and status not in ('Closed', 'Completed', 'On Hold')
		     and per_billed < 100 and delivery_date < %(cut)s""",
		{"cut": _cutoff(rule, 1)}, as_dict=True):
		dn = frappe.db.sql(
			"""select distinct dn.name from `tabDelivery Note Item` i join `tabDelivery Note` dn on dn.name = i.parent
			   where i.against_sales_order = %s and dn.docstatus = 1 and dn.per_billed < 100
			   order by dn.posting_date limit 1""", so.name)
		dn = dn[0][0] if dn else None
		rest = flt(so.base_grand_total) * (100 - flt(so.per_billed)) / 100
		late = date_diff(today(), so.delivery_date)
		out.append(_f(
			key=so.name, doctype="Sales Order", name=so.name, since=so.delivery_date, amount=rest,
			pic=_holder("Sales Order", so.name),
			subject=_("SO {0} lewat tanggal kirim {1} hari, belum ditagih ({2})").format(so.name, late, so.customer),
			evidence=_("Tanggal kirim {0}. Sudah ditagih {1}%. Sisa {2}. {3}").format(
				so.delivery_date, round(flt(so.per_billed)), _money(rest),
				_("Delivery Note terkirim belum ditagih: {0}.").format(dn) if dn else _("Belum ada Delivery Note terkirim.")),
			fix={"kind": "draft_si_from_dn", "source": dn} if dn else None,
		))
	return out


def check_b1(rule):
	"""Purchase Order lewat tanggal terima, belum ada Purchase Invoice."""
	out = []
	for po in frappe.db.sql(
		"""select name, supplier, schedule_date, per_billed, base_grand_total
		   from `tabPurchase Order`
		   where docstatus = 1 and status not in ('Closed', 'Completed', 'On Hold', 'Delivered')
		     and per_billed < 100 and schedule_date < %(cut)s""",
		{"cut": _cutoff(rule, 3)}, as_dict=True):
		rest = flt(po.base_grand_total) * (100 - flt(po.per_billed)) / 100
		late = date_diff(today(), po.schedule_date)
		out.append(_f(
			key=po.name, doctype="Purchase Order", name=po.name, since=po.schedule_date, amount=rest,
			pic=_holder("Purchase Order", po.name),
			subject=_("PO {0} lewat tanggal terima {1} hari, belum ada Purchase Invoice ({2})").format(po.name, late, po.supplier),
			evidence=_("Tanggal terima {0}. Sudah ditagih vendor {1}%. Sisa {2}.").format(
				po.schedule_date, round(flt(po.per_billed)), _money(rest)),
			fix={"kind": "draft_pi_from_po", "source": po.name},
		))
	return out


def _job_invoiced(jobs):
	"""Master Job (nama PL/SL) yang sudah punya Sales Invoice tidak batal: lewat container
	(invoice Expedition) atau lewat baris Reimburse yang menunjuk EN job itu."""
	if not jobs:
		return set()
	jobs = list(jobs)
	done = {r[0] for r in frappe.db.sql(
		"""select distinct c.source_name from `tabInvoice Container` c join `tabSales Invoice` si on si.name = c.parent
		   where c.parenttype = 'Sales Invoice' and si.docstatus != 2 and c.source_name in %(j)s""", {"j": jobs})}
	done |= {r[0] for r in frappe.db.sql(
		"""select distinct coalesce(en.packing_list, en.shipping_list)
		   from `tabSales Invoice Reimburse` r join `tabSales Invoice` si on si.name = r.parent
		   join `tabExpense Note` en on en.name = r.expense_note
		   where r.parenttype = 'Sales Invoice' and si.docstatus != 2
		     and coalesce(en.packing_list, en.shipping_list) in %(j)s""", {"j": jobs})}
	return done


def check_e2(rule):
	"""Master Job masih terbuka, biayanya sudah keluar (EN tervalidasi), belum ada tagihan sama sekali."""
	rows = frappe.db.sql(
		"""select if(ifnull(en.packing_list, '') != '', 'Packing List', 'Shipping List') dt,
		          coalesce(nullif(en.packing_list, ''), en.shipping_list) job,
		          count(*) n, sum(en.net_total * ifnull(nullif(en.conversion_rate, 0), 1)) cost, min(en.date) since
		   from `tabExpense Note` en
		   where en.validated = 1 and en.void = 0
		     and (ifnull(en.packing_list, '') != '' or ifnull(en.shipping_list, '') != '')
		   group by dt, job having since < %(cut)s""",
		{"cut": _cutoff(rule, 14)}, as_dict=True)
	billed = _job_invoiced({r.job for r in rows})
	out = []
	for r in rows:
		if r.job in billed:
			continue
		state = frappe.db.get_value(r.dt, r.job, ["closed", "void"], as_dict=True) or {}
		if state.get("closed") or state.get("void"):
			continue
		out.append(_f(
			key=r.job, doctype=r.dt, name=r.job, since=r.since, amount=r.cost, pic=_holder(r.dt, r.job),
			subject=_("{0} {1}: biaya {2} sudah keluar, belum ditagih ke customer").format(r.dt, r.job, _money(r.cost)),
			evidence=_("{0} Expense Note tervalidasi sejak {1}, total {2}. Belum ada Sales Invoice (Expedition maupun Reimburse) untuk job ini.").format(
				r.n, r.since, _money(r.cost)),
			fix=None,
		))
	return out


def check_e3(rule):
	"""Packing List terbuka lebih dari 30 hari tanpa biaya dan tanpa tagihan."""
	pls = frappe.db.sql(
		"""select pl.name, pl.customer, pl.date from `tabPacking List` pl
		   where pl.closed = 0 and pl.void = 0 and pl.date < %(cut)s
		     and not exists (select 1 from `tabExpense Note` en where en.packing_list = pl.name and en.void = 0)
		     and not exists (select 1 from `tabExpense Note Item` i join `tabExpense Note` en on en.name = i.parent
		                     where i.packing_list = pl.name and en.void = 0)""",
		{"cut": _cutoff(rule, 30)}, as_dict=True)
	billed = _job_invoiced({p.name for p in pls})
	return [_f(
		key=p.name, doctype="Packing List", name=p.name, since=p.date, amount=0, pic=_holder("Packing List", p.name),
		subject=_("Packing List {0} kosong {1} hari ({2})").format(p.name, date_diff(today(), p.date), p.customer or "-"),
		evidence=_("Dibuat {0}. Tidak ada Expense Note dan tidak ada Sales Invoice.").format(p.date),
		fix={"kind": "close_packing_list", "source": p.name},
	) for p in pls if p.name not in billed]


def check_e4(rule):
	"""Biaya dobel: dua EN beda, vendor sama, job sama, item + container + nominal sama, selisih <= 7 hari."""
	rows = frappe.db.sql(
		"""select a.parent first, b.parent second, b.item, b.container_no, b.amount, eb.vendor,
		          coalesce(nullif(eb.packing_list, ''), eb.shipping_list) job, eb.date
		   from `tabExpense Note Item` a
		   join `tabExpense Note Item` b on b.item = a.item and b.container_no = a.container_no
		        and b.amount = a.amount and b.parent > a.parent
		   join `tabExpense Note` ea on ea.name = a.parent
		   join `tabExpense Note` eb on eb.name = b.parent
		   where a.parenttype = 'Expense Note' and b.parenttype = 'Expense Note'
		     and ea.void = 0 and eb.void = 0 and ea.vendor = eb.vendor and a.amount > 0
		     and ifnull(a.container_no, '') != ''
		     and coalesce(nullif(ea.packing_list, ''), ea.shipping_list) = coalesce(nullif(eb.packing_list, ''), eb.shipping_list)
		     and abs(datediff(ea.date, eb.date)) <= 7""", as_dict=True)
	return [_f(
		key=f"{r.second}:{r.item}:{r.container_no}", doctype="Expense Note", name=r.second, since=r.date,
		amount=r.amount, pic=_holder("Expense Note", r.second),
		subject=_("Biaya dobel? {0} sama dengan {1} ({2}, container {3})").format(r.second, r.first, r.item, r.container_no),
		evidence=_("Vendor {0}, job {1}. Item {2} untuk container {3} senilai {4} sudah ada di {5}.").format(
			r.vendor, r.job or "-", r.item, r.container_no, _money(r.amount), r.first),
		fix=None,
	) for r in rows]


def check_r1(rule):
	"""Expense Note reimburse tervalidasi yang barisnya belum ditagih ke customer."""
	try:
		from erpnext_custom.connection import used_reimburse_keys
	except ImportError:
		return []
	used = used_reimburse_keys()
	ens = frappe.get_all("Expense Note", filters={"is_reimburse": 1, "validated": 1, "void": 0, "date": ["<", _cutoff(rule, 7)]},
	                     fields=["name", "date", "reimburse_to_customer", "conversion_rate"])
	out = []
	for en in ens:
		items = frappe.get_all("Expense Note Item", filters={"parent": en.name, "parenttype": "Expense Note"},
		                       fields=["item", "expense_class", "amount"])
		open_rows = [i for i in items if (en.name, i.item, i.expense_class) not in used]
		if not open_rows:
			continue
		amount = sum(flt(i.amount) for i in open_rows) * (flt(en.conversion_rate) or 1)
		out.append(_f(
			key=en.name, doctype="Expense Note", name=en.name, since=en.date, amount=amount, pic=_holder("Expense Note", en.name),
			subject=_("Reimburse {0} belum ditagih ke {1}").format(en.name, en.reimburse_to_customer or "-"),
			evidence=_("{0} dari {1} baris biaya belum masuk Sales Invoice Reimburse, senilai {2}. Tanggal EN {3}.").format(
				len(open_rows), len(items), _money(amount), en.date),
			fix=None,
		))
	return out


# E1 belajar dari riwayat: biaya estimasi yang hampir selalu muncul di job dengan estimasi itu.
E1_MIN_JOBS, E1_MIN_RATE = 5, 0.9


def check_e1(rule):
	"""Packing List terbuka lewat tenggang: biaya yang menurut riwayat estimasinya hampir selalu ada
	(muncul di 90% atau lebih dari minimal 5 job sebelumnya) belum ada Expense Note-nya."""
	cut = _cutoff(rule, 14)
	jobs = frappe.db.sql(
		"""select pl.name, pl.date, pl.closed, pl.customer,
		          coalesce(nullif(pl.estimation, ''), (select i.estimation from `tabPacking List Item` i
		           where i.parent = pl.name and ifnull(i.estimation, '') != '' limit 1)) est
		   from `tabPacking List` pl where pl.void = 0""", as_dict=True)
	jobs = [j for j in jobs if j.est]
	if not jobs:
		return []
	used = {}
	for r in frappe.db.sql(
		"""select coalesce(nullif(en.packing_list, ''), i.packing_list) job, i.item
		   from `tabExpense Note Item` i join `tabExpense Note` en on en.name = i.parent
		   where en.void = 0 and ifnull(i.item, '') != ''""", as_dict=True):
		used.setdefault(r.job, set()).add(r.item)
	planned = {}
	for r in frappe.db.sql("""select parent, type_id from `tabCRM Estimation Detail`
	                          where parentfield = 'expense_items' and ifnull(type_id, '') != ''""", as_dict=True):
		planned.setdefault(r.parent, set()).add(r.type_id)
	# riwayat = job yang sudah lewat tenggang dan punya biaya sama sekali
	history = [j for j in jobs if getdate(j.date) < cut and used.get(j.name)]
	out = []
	for j in jobs:
		if j.closed or getdate(j.date) >= cut:
			continue
		peers = [h for h in history if h.est == j.est and h.name != j.name]
		if len(peers) < E1_MIN_JOBS:
			continue
		for item in sorted(planned.get(j.est, set()) - used.get(j.name, set())):
			hit = sum(1 for h in peers if item in used.get(h.name, set()))
			if hit / len(peers) < E1_MIN_RATE:
				continue
			out.append(_f(
				key=f"{j.name}:{item}", doctype="Packing List", name=j.name, since=j.date, amount=0, pic=_holder("Packing List", j.name),
				subject=_("{0}: biaya {1} belum ada").format(j.name, item),
				evidence=_("Estimasi {0}. Biaya {1} muncul di {2} dari {3} job sebelumnya dengan estimasi yang sama, tapi belum ada Expense Note-nya di job ini (dibuat {4}).").format(
					j.est, item, hit, len(peers), j.date),
				fix=None,
			))
	return out


# --- Kesehatan Buku (K1-K8) ----------------------------------------------------------------
# Memberi tahu, tidak menolak transaksi; agent menjelaskan lewat Tanya Agent, tidak membuat jurnal.

GL_LOOKBACK_DAYS = 400


def check_k1(rule):
	"""Voucher yang jurnalnya tidak seimbang."""
	rows = frappe.db.sql(
		"""select voucher_type, voucher_no, company, min(posting_date) d, sum(debit) dr, sum(credit) cr
		   from `tabGL Entry` where is_cancelled = 0 and posting_date >= %s
		   group by voucher_type, voucher_no, company having abs(sum(debit) - sum(credit)) > 0.5""",
		add_days(today(), -GL_LOOKBACK_DAYS), as_dict=True)
	return [_f(
		key=f"{r.voucher_type}:{r.voucher_no}", doctype=r.voucher_type, name=r.voucher_no, since=r.d, amount=abs(flt(r.dr) - flt(r.cr)),
		pic=_holder(r.voucher_type, r.voucher_no),
		subject=_("Jurnal {0} {1} tidak seimbang").format(r.voucher_type, r.voucher_no),
		evidence=_("Debit {0}, kredit {1}, selisih {2}. Neraca saldo {3} ikut tidak seimbang sebesar itu.").format(
			_money(r.dr), _money(r.cr), _money(abs(flt(r.dr) - flt(r.cr))), r.company),
		fix=None) for r in rows]


def check_k2(rule):
	"""Neraca saldo per company tidak seimbang."""
	rows = frappe.db.sql("""select company, sum(debit) dr, sum(credit) cr from `tabGL Entry` where is_cancelled = 0
	                        group by company having abs(sum(debit) - sum(credit)) > 0.5""", as_dict=True)
	return [_f(
		key=r.company, doctype="Company", name=r.company, since=today(), amount=abs(flt(r.dr) - flt(r.cr)), pic=None,
		subject=_("Neraca saldo {0} tidak seimbang").format(r.company),
		evidence=_("Total debit {0}, total kredit {1}, selisih {2}. Lihat temuan Jurnal tidak seimbang untuk voucher penyebabnya.").format(
			_money(r.dr), _money(r.cr), _money(abs(flt(r.dr) - flt(r.cr)))),
		fix=None) for r in rows]


def _suspense_accounts():
	raw = frappe.db.get_single_value("ERPNext Custom Setting", "orchestrator_suspense_accounts") \
		if frappe.get_meta("ERPNext Custom Setting").has_field("orchestrator_suspense_accounts") else ""
	names = [a.strip() for a in (raw or "").splitlines() if a.strip()]
	if names:
		return names
	return frappe.db.sql_list("""select name from tabAccount where is_group = 0 and (account_name like '%%suspen%%'
	                             or account_name like '%%penampung%%' or account_name like '%%sementara%%')""")


def _balance(account, upto=None):
	return flt(frappe.db.sql("""select sum(debit) - sum(credit) from `tabGL Entry` where account = %s and is_cancelled = 0
	                            and posting_date <= %s""", (account, upto or today()))[0][0])


def check_k3(rule):
	"""Akun penampung yang saldonya mengendap lewat tenggang."""
	cut = _cutoff(rule, 30)
	out = []
	for acc in _suspense_accounts():
		now, then = _balance(acc), _balance(acc, cut)
		if abs(now) < 1 or abs(then) < 1:
			continue
		out.append(_f(
			key=acc, doctype="Account", name=acc, since=cut, amount=abs(now), pic=None,
			subject=_("Akun penampung {0} bersaldo {1}").format(acc, _money(now)),
			evidence=_("Saldo sekarang {0}; {1} hari lalu sudah {2} (berubah {3}). Saldo penampung seharusnya dibersihkan ke akun tujuannya.").format(
				_money(now), date_diff(today(), cut), _money(then), _money(now - then)),
			fix=None))
	return out


def check_k4(rule):
	"""Buku pembantu piutang/hutang (Payment Ledger) tidak sama dengan saldo GL akunnya."""
	gl = dict(frappe.db.sql("""select g.account, sum(g.debit) - sum(g.credit) from `tabGL Entry` g
	                           join tabAccount a on a.name = g.account
	                           where g.is_cancelled = 0 and a.account_type in ('Receivable', 'Payable') group by g.account"""))
	# Payment Ledger menyimpan akun Payable dengan tanda terbalik (kredit - debit)
	ple = dict(frappe.db.sql("""select p.account, sum(if(a.account_type = 'Payable', -p.amount, p.amount))
	                            from `tabPayment Ledger Entry` p join tabAccount a on a.name = p.account
	                            where p.delinked = 0 group by p.account"""))
	out = []
	for acc in set(gl) | set(ple):
		g, p = flt(gl.get(acc)), flt(ple.get(acc))
		if abs(g - p) > 1:
			out.append(_f(
				key=acc, doctype="Account", name=acc, since=today(), amount=abs(g - p), pic=None,
				subject=_("Buku pembantu {0} beda dengan GL").format(acc),
				evidence=_("Saldo GL {0}, total Payment Ledger (per party) {1}, selisih {2}. Umur piutang/hutang dan saldo neraca tidak akan cocok.").format(
					_money(g), _money(p), _money(g - p)),
				fix=None))
	return out


def check_k5(rule):
	"""Kas/bank bersaldo minus."""
	rows = frappe.db.sql("""select g.account, sum(g.debit) - sum(g.credit) bal from `tabGL Entry` g join tabAccount a on a.name = g.account
	                        where g.is_cancelled = 0 and a.account_type in ('Bank', 'Cash') group by g.account having bal < -1""", as_dict=True)
	return [_f(
		key=r.account, doctype="Account", name=r.account, since=today(), amount=abs(flt(r.bal)), pic=None,
		subject=_("Saldo {0} minus {1}").format(r.account, _money(abs(flt(r.bal)))),
		evidence=_("Saldo kas/bank menurut buku {0}. Kalau bukan rekening overdraft, ada penerimaan yang belum dicatat atau pengeluaran tercatat dobel.").format(_money(r.bal)),
		fix=None) for r in rows]


def check_k6(rule):
	"""Payment Entry tervalidasi tanpa jurnal."""
	rows = frappe.db.sql("""select pe.name, pe.posting_date, pe.base_paid_amount from `tabPayment Entry` pe
	                        where pe.docstatus = 1 and not exists (select 1 from `tabGL Entry` g
	                          where g.voucher_type = 'Payment Entry' and g.voucher_no = pe.name and g.is_cancelled = 0)""", as_dict=True)
	return [_f(
		key=r.name, doctype="Payment Entry", name=r.name, since=r.posting_date, amount=flt(r.base_paid_amount),
		pic=_holder("Payment Entry", r.name),
		subject=_("Payment Entry {0} tanpa jurnal").format(r.name),
		evidence=_("Tervalidasi tanggal {0} senilai {1}, tapi tidak ada GL Entry. Saldo bank dan piutang/hutang tidak berubah.").format(
			r.posting_date, _money(r.base_paid_amount)),
		fix=None) for r in rows]


def check_k7(rule):
	"""Jurnal bertanggal masa depan."""
	rows = frappe.db.sql("""select voucher_type, voucher_no, min(posting_date) d, sum(debit) dr from `tabGL Entry`
	                        where is_cancelled = 0 and posting_date > %s group by voucher_type, voucher_no""",
	                     add_days(today(), max(cint(rule.threshold_hours) // 24, 0)), as_dict=True)
	return [_f(
		key=f"{r.voucher_type}:{r.voucher_no}", doctype=r.voucher_type, name=r.voucher_no, since=today(), amount=flt(r.dr),
		pic=_holder(r.voucher_type, r.voucher_no),
		subject=_("{0} {1} bertanggal {2}").format(r.voucher_type, r.voucher_no, r.d),
		evidence=_("Jurnal senilai {0} bertanggal {1}, di masa depan. Laporan bulan ini belum memuatnya; cek apakah salah ketik tahun atau bulan.").format(
			_money(r.dr), r.d),
		fix=None) for r in rows]


def check_k8(rule):
	"""Laba rugi bulan lalu belum ditutup (Period Closing Voucher) untuk company yang memakai tutup bulanan."""
	if not frappe.db.exists("DocType", "CMI Period Close"):
		return []
	from frappe.utils import get_first_day, get_last_day
	month_end = get_last_day(add_days(get_first_day(today()), -1))
	grace = cint(rule.threshold_hours) // 24 if rule.threshold_hours is not None else 10
	if date_diff(today(), month_end) < grace:
		return []
	out = []
	for c in frappe.get_all("CMI Period Close", filters={"parenttype": "ERPNext Custom Setting", "monthly_roll": 1}, pluck="company"):
		if not frappe.db.exists("GL Entry", {"company": c, "is_cancelled": 0, "posting_date": ["<=", month_end]}):
			continue
		if frappe.db.exists("Period Closing Voucher", {"company": c, "docstatus": 1, "period_end_date": [">=", month_end]}):
			continue
		out.append(_f(
			key=f"{c}:{month_end}", doctype="Company", name=c, since=month_end, amount=0, pic=None,
			subject=_("Laba rugi {0} bulan {1} belum ditutup").format(c, month_end.strftime("%m/%Y")),
			evidence=_("Belum ada Period Closing Voucher sampai {0}. Neraca belum memuat laba bulan itu dan posting mundur ke bulan itu masih terbuka.").format(month_end),
			fix=None))
	return out


# code -> (judul, kategori, keyakinan bawaan, fungsi, tenggang bawaan dalam hari)
CHECKS = {
	"S1": (_("SO lewat tanggal kirim belum ditagih"), "Outstanding", PASTI, check_s1, 1),
	"B1": (_("PO lewat tanggal terima belum ada PI"), "Outstanding", PASTI, check_b1, 3),
	"E2": (_("Biaya job keluar, belum ditagih"), "Outstanding", PASTI, check_e2, 14),
	"E3": (_("Packing List kosong"), "Kelengkapan", CEK, check_e3, 30),
	"E4": (_("Biaya dobel"), "Ketelitian", CEK, check_e4, 0),
	"R1": (_("Reimburse belum ditagih"), "Outstanding", PASTI, check_r1, 7),
	"E1": (_("Biaya estimasi belum ada EN"), "Kelengkapan", CEK, check_e1, 14),
	"K1": (_("Jurnal tidak seimbang"), "Kesehatan Buku", PASTI, check_k1, 0),
	"K2": (_("Neraca saldo tidak seimbang"), "Kesehatan Buku", PASTI, check_k2, 0),
	"K3": (_("Akun penampung bersaldo"), "Kesehatan Buku", CEK, check_k3, 30),
	"K4": (_("Buku pembantu beda dengan GL"), "Kesehatan Buku", PASTI, check_k4, 0),
	"K5": (_("Kas/bank minus"), "Kesehatan Buku", CEK, check_k5, 0),
	"K6": (_("Payment Entry tanpa jurnal"), "Kesehatan Buku", PASTI, check_k6, 0),
	"K7": (_("Jurnal bertanggal masa depan"), "Kesehatan Buku", CEK, check_k7, 0),
	"K8": (_("Laba rugi bulan lalu belum ditutup"), "Kesehatan Buku", PASTI, check_k8, 10),
}
# Pemeriksaan yang membaca seluruh GL: paling sering sekali per sekian menit, bukan tiap 15 menit.
HEAVY = {"K1": 60, "K2": 60, "K4": 60}

# Penjelasan untuk user (daftar "Apa saja yang diperiksa" di laporan). Kode: S = Selling,
# B = Buying, E = Expedition, R = Reimburse.
MEANING = {
	"S1": _("Sales Order yang tanggal kirimnya lewat, tapi belum ditagih penuh. Barang sudah jalan, uangnya belum ditagih."),
	"B1": _("Purchase Order yang tanggal terimanya lewat, tapi belum ada Purchase Invoice. Stok atau biaya belum diakui, hutang ke vendor belum tercatat."),
	"E2": _("Packing/Shipping List yang biayanya sudah keluar (Expense Note tervalidasi), tapi belum ada invoice sama sekali ke customer. Biaya sudah dibayar, lupa ditagih."),
	"E3": _("Packing List terbuka tanpa Expense Note dan tanpa invoice. Kemungkinan job batal atau dobel."),
	"E4": _("Dua Expense Note dengan vendor, job, item, container, dan nominal sama dalam 7 hari. Vendor bisa terbayar dua kali."),
	"R1": _("Expense Note reimburse yang belum masuk invoice Reimburse. Talangan untuk customer belum diminta kembali."),
	"E1": _("Biaya yang menurut riwayat estimasinya hampir selalu ada (90% dari minimal 5 job) belum ada Expense Note-nya. Biaya bisa lupa dicatat dan lupa ditagih."),
	"K1": _("Voucher yang debit dan kreditnya tidak sama. Membuat neraca saldo tidak seimbang."),
	"K2": _("Total debit dan kredit seluruh jurnal satu company tidak sama."),
	"K3": _("Akun penampung (suspend, sementara) yang saldonya mengendap lewat tenggang. Seharusnya dibersihkan ke akun tujuannya."),
	"K4": _("Saldo piutang/hutang di buku pembantu (per customer/vendor) tidak sama dengan saldo akunnya di GL."),
	"K5": _("Akun kas atau bank bersaldo minus."),
	"K6": _("Payment Entry tervalidasi yang tidak punya jurnal. Saldo bank dan piutang/hutang tidak berubah."),
	"K7": _("Jurnal bertanggal di masa depan, biasanya salah ketik tanggal."),
	"K8": _("Company yang memakai tutup laba rugi bulanan tapi bulan lalu belum ditutup lewat tenggang."),
}

FIX_LABEL = {
	"draft_si_from_dn": _("Buat Sales Invoice draft dari Delivery Note {0}"),
	"draft_pi_from_po": _("Buat Purchase Invoice draft dari {0}"),
	"close_packing_list": _("Close Packing List {0}"),
}


def fix_label(fix):
	fix = _fix(fix)
	return FIX_LABEL[fix["kind"]].format(fix["source"]) if fix and fix.get("kind") in FIX_LABEL else ""


# --- reviewer -------------------------------------------------------------------------------


def _fingerprint(f):
	return hashlib.md5(f"{flt(f.amount, 2)}|{f.since}|{f.evidence}".encode()).hexdigest()[:12]


def check_stats(code, days=90):
	"""Keputusan user atas temuan pemeriksaan ini: bahan reviewer dan halaman Uji Diam."""
	rows = frappe.db.sql(
		"""select decision, count(*) n from `tabAgent Task`
		   where source = 'Audit' and audit_check = %s and ifnull(decision, '') != '' and decision_at > %s
		   group by decision""", (code, add_days(today(), -days)))
	s = {"Setuju": 0, "Koreksi": 0, "Tolak": 0, AUTO: 0}
	s.update({d: n for d, n in rows})
	s["total"] = s["Setuju"] + s["Koreksi"] + s["Tolak"]
	s["Batal"] = frappe.db.count("Agent Task", {"source": "Audit", "audit_check": code, "undone": 1,
	                                            "undone_at": [">", add_days(today(), -days)]})
	return s


def review(rule, findings):
	"""Pemeriksa kedua sebelum temuan masuk laporan."""
	code = rule.audit_check
	confidence = CHECKS[code][2]
	s = check_stats(code)
	if s["total"] >= REVIEW_MIN_DECISIONS and (s["Tolak"] + s["Koreksi"] + s["Batal"]) / s["total"] >= REVIEW_MAX_REJECT:
		confidence = CEK
	# pengecualian yang disetujui Controller berlaku selama kondisinya sama persis
	excepted = {(r.dedupe_key, r.fingerprint) for r in frappe.get_all(
		"Agent Task", filters={"source": "Audit", "audit_check": code, "exception_status": "Disetujui"},
		fields=["dedupe_key", "fingerprint"])}
	out = []
	for f in findings:
		f.dedupe_key = f"audit:{code}:{f.key}"
		f.fingerprint = _fingerprint(f)
		if (f.dedupe_key, f.fingerprint) in excepted:
			continue
		f.confidence = confidence
		# pembuat legacy/impor (Administrator) atau user nonaktif bukan PIC: ke Controller
		if f.pic and (f.pic in ("Administrator", "Guest") or not frappe.db.get_value("User", f.pic, "enabled")):
			f.pic = None
		out.append(f)
	return out


# --- scan -----------------------------------------------------------------------------------


def _upsert(rule, f):
	shadow = cint(rule.shadow)
	fix = json.dumps(f.fix) if f.fix else None
	desc = f.evidence + (f"\n{_('Disiapkan')}: {fix_label(f.fix)}" if f.fix else "")
	name = frappe.db.get_value("Agent Task", {"dedupe_key": f.dedupe_key, "status": ["!=", "Resolved"]})
	if name:
		doc = frappe.get_doc("Agent Task", name)
		changed = False
		if doc.description != desc:
			doc.description, doc.event_at = desc, now_datetime()
			orc._log(doc, "event", desc, actor="agent")
			changed = True
		for k, v in {"amount": flt(f.amount), "confidence": f.confidence, "fix": fix, "fingerprint": f.fingerprint,
		             "subject": f.subject[:140]}.items():
			if (doc.get(k) or None) != (v or None):
				doc.set(k, v)
				changed = True
		if doc.shadow and not shadow:
			doc.shadow = 0
			doc.assigned_to = f.pic
			orc._add_watchers(doc, [f.pic] if f.pic else orc._role_users(rule.controller_role))
			orc._log(doc, "action", _("Uji diam selesai: temuan masuk laporan."), actor="agent")
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return
	doc = frappe.get_doc({
		"doctype": "Agent Task", "subject": f.subject[:140], "source": "Audit", "status": "Open",
		"severity": rule.severity or "Medium", "dedupe_key": f.dedupe_key,
		"reference_doctype": f.doctype, "reference_name": f.name,
		"assigned_to": None if shadow else f.pic, "description": desc, "event_at": now_datetime(),
		"rule": rule.name, "workflow": orc._label(rule) or CHECKS[rule.audit_check][0],
		"audit_check": rule.audit_check, "category": CHECKS[rule.audit_check][1], "confidence": f.confidence,
		"amount": flt(f.amount), "since_date": f.since, "fix": fix, "fingerprint": f.fingerprint, "shadow": shadow,
	})
	if not shadow:
		orc._add_watchers(doc, [f.pic] if f.pic else orc._role_users(rule.controller_role))
	orc._log(doc, "event", desc, actor="agent")
	doc.insert(ignore_permissions=True)
	orc._stat("new")


def scan_rule(rule):
	code = rule.audit_check
	if code not in CHECKS:
		frappe.throw(_("Pemeriksaan {0} tidak dikenal.").format(code or "-"))
	findings = review(rule, CHECKS[code][3](rule))
	orc._stat("checked", len(findings))
	keys = set()
	for f in findings:
		keys.add(f.dedupe_key)
		_upsert(rule, f)
	if rule.get("autonomy") == AUTO and not cint(rule.shadow):
		_run_auto(rule)
	# kondisi sudah beres (atau dikecualikan) -> tutup sendiri
	for t in frappe.get_all("Agent Task", filters={"source": "Audit", "rule": rule.name, "status": ["!=", "Resolved"]},
	                        fields=["name", "dedupe_key", "exception_status"]):
		if t.dedupe_key not in keys and t.exception_status != "Diajukan":
			orc._resolve(frappe.get_doc("Agent Task", t.name), "Ditangani", _("Kondisi sudah beres."), "agent")
	if findings or keys:
		orc._changed()


def audit_rules():
	return [r for r in orc._rules("Audit") if r.audit_check]


def scan():
	"""Tiap 15 menit (orchestrator.tick_slow). Satu pemeriksaan gagal tidak menghentikan yang lain;
	errornya tampil di laporan sebagai 'pemeriksaan tidak jalan'."""
	if not orc.switch_on("orchestrator_audit_enabled"):
		return
	runs = frappe.cache().hgetall("orchestrator:runs") or {}
	runs = {(k.decode() if isinstance(k, bytes) else k): v for k, v in runs.items()}
	for rule in audit_rules():
		every = HEAVY.get(rule.audit_check)
		last = (runs.get(rule.name) or {}).get("at")
		if every and last and frappe.utils.time_diff_in_seconds(now_datetime(), last) < every * 60:
			continue
		orc._safe(lambda rule=rule: scan_rule(rule), rule.name)


# --- perbaikan ------------------------------------------------------------------------------


def _fix(fix):
	if isinstance(fix, str):
		try:
			return json.loads(fix) if fix.strip() else None
		except ValueError:
			return None
	return fix


def _existing_draft(target, link_field, source):
	child = {"Purchase Invoice": "Purchase Invoice Item", "Sales Invoice": "Sales Invoice Item"}[target]
	rows = frappe.db.sql(
		f"""select p.name from `tab{child}` i join `tab{target}` p on p.name = i.parent
		    where i.{link_field} = %s and p.docstatus = 0 limit 1""", source)
	return rows[0][0] if rows else None


def run_fix(doc):
	"""Jalankan perbaikan yang disiapkan, sebagai user yang memutuskan (izin dia yang berlaku).
	Jenis perbaikan hanya dari daftar di kode; isi JSON task cuma menunjuk dokumen sumber."""
	fix = _fix(doc.fix)
	if not fix:
		return None
	kind, source = fix.get("kind"), fix.get("source")
	if kind in ("draft_pi_from_po", "draft_si_from_dn"):
		# mapper Cakra (erpnext_custom) dulu: sama dengan tombol di desk, mengisi Invoice Type dll.
		target, methods, link = {
			"draft_pi_from_po": ("Purchase Invoice", ("erpnext_custom.purchase_invoice.mapping.make_purchase_invoice",
			                                          "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice"), "purchase_order"),
			"draft_si_from_dn": ("Sales Invoice", ("erpnext_custom.sales_invoice.mapping.make_sales_invoice_from_delivery_note",
			                                       "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice"), "delivery_note"),
		}[kind]
		method = methods[0] if "erpnext_custom" in frappe.get_installed_apps() else methods[1]
		existing = _existing_draft(target, link, source)
		if existing:
			return existing  # jangan bikin draft kedua
		if not frappe.has_permission(target, "create"):
			frappe.throw(_("Anda tidak punya izin membuat {0}.").format(_(target)), frappe.PermissionError)
		new = frappe.get_attr(method)(source)
		new.insert()
		return new.name
	if kind == "close_packing_list":
		from erpnext_custom.workflow import close_doc
		close_doc("Packing List", source, _("Kosong, ditutup dari laporan pemeriksaan {0}").format(doc.name))
		return source
	frappe.throw(_("Jenis perbaikan {0} tidak dikenal.").format(kind))


# --- tahap 3: otomatis ----------------------------------------------------------------------

# Perbaikan yang bisa dibatalkan (syarat Otomatis): draft dihapus, Packing List dibuka lagi.
_TARGET = {"draft_pi_from_po": ("Purchase Invoice", "purchase_order"),
           "draft_si_from_dn": ("Sales Invoice", "delivery_note")}
REVERSIBLE = set(_TARGET) | {"close_packing_list"}


def _is_admin():
	return bool({"System Manager", "Orchestrator Admin"} & set(frappe.get_roles()))


def _check_has_fix(code):
	"""Pemeriksaan yang memang menyiapkan perbaikan (bukan cuma melapor)."""
	return code in ("S1", "B1", "E3")


def promotion(rule):
	"""Apakah pemeriksaan ini layak naik ke Otomatis, dan kalau belum, kenapa."""
	code = rule.audit_check
	reasons = []
	if not _check_has_fix(code):
		reasons.append(_("Pemeriksaan ini hanya melapor, tidak punya perbaikan yang bisa dijalankan."))
	if cint(rule.shadow):
		reasons.append(_("Masih uji diam."))
	s = check_stats(code, days=3650)
	if s["total"] < PROMOTE_MIN:
		reasons.append(_("Butuh {0} keputusan user, baru {1}.").format(PROMOTE_MIN, s["total"]))
	elif s["Setuju"] / s["total"] < PROMOTE_RATE:
		reasons.append(_("Setuju tanpa koreksi {0}%, butuh {1}%.").format(round(100 * s["Setuju"] / s["total"]), round(100 * PROMOTE_RATE)))
	last = frappe.get_all("Agent Task", filters={"source": "Audit", "audit_check": code,
	                                              "decision": ["in", ["Setuju", "Koreksi", "Tolak"]]},
	                      fields=["decision", "undone"], order_by="decision_at desc", limit=PROMOTE_CLEAN)
	bad = sum(1 for r in last if r.decision == "Tolak" or r.undone)
	if bad:
		reasons.append(_("{0} dari {1} keputusan terakhir ditolak atau dibatalkan.").format(bad, len(last)))
	return {"eligible": not reasons, "reasons": reasons, "stats": s}


def _admins(rule):
	return orc._role_users(rule.get("admin_role") or "Orchestrator Admin")


def _tell(users, subject):
	for u in dict.fromkeys(users):
		try:
			frappe.get_doc({"doctype": "Notification Log", "subject": subject[:140], "for_user": u, "type": "Alert"}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "audit._tell")


def _rule_comment(text):
	"""Jejak naik/turun level: komentar di Assistant Settings (siapa, kapan, kenapa)."""
	frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Assistant Settings",
	                "reference_name": "Assistant Settings", "content": text}).insert(ignore_permissions=True)


def _demote(rule, reason):
	if frappe.db.get_value("Orchestrator Rule", rule.name, "autonomy") != AUTO:
		return
	frappe.db.set_value("Orchestrator Rule", rule.name, "autonomy", "Final check")
	rule.autonomy = "Final check"
	msg = _("{0} turun ke Final check: {1}").format(orc._label(rule), reason)
	_rule_comment(msg)
	_tell(_admins(rule), msg)


@frappe.whitelist()
def set_autonomy(name, mode, max_amount=0):
	"""Admin menaikkan pemeriksaan ke Otomatis (hanya kalau promotion() terpenuhi) atau
	mengembalikannya ke Final check."""
	if not _is_admin():
		frappe.throw(_("Hanya Orchestrator Admin yang mengubah mode pemeriksaan."), frappe.PermissionError)
	rule = frappe.db.get_value("Orchestrator Rule", name, orc._RULE_FIELDS, as_dict=True)
	if not rule or rule.source != "Audit":
		frappe.throw(_("Pemeriksaan tidak ditemukan."))
	if mode == AUTO:
		p = promotion(rule)
		if not p["eligible"]:
			frappe.throw(_("Belum layak otomatis:<br>{0}").format("<br>".join(p["reasons"])))
		frappe.db.set_value("Orchestrator Rule", name, {"autonomy": AUTO, "max_amount": flt(max_amount)})
		_rule_comment(_("{0} dinaikkan ke Otomatis oleh {1}, batas nominal {2}.").format(
			orc._label(rule), frappe.session.user, _money(max_amount) if flt(max_amount) else _("tanpa batas")))
	else:
		frappe.db.set_value("Orchestrator Rule", name, "autonomy", "Final check")
		_rule_comment(_("{0} dikembalikan ke Final check oleh {1}.").format(orc._label(rule), frappe.session.user))
	return mode


def _before(kind, source):
	if kind in _TARGET:
		return _("belum ada {0} draft untuk {1}").format(_TARGET[kind][0], source)
	return _("Packing List {0} terbuka").format(source)


def _verify(kind, source, result):
	"""Hasil perbaikan benar-benar ada dan tertaut ke sumbernya."""
	if kind in _TARGET:
		target, link = _TARGET[kind]
		return bool(result) and _existing_draft(target, link, source) == result
	return cint(frappe.db.get_value("Packing List", source, "closed")) == 1


def _run_auto(rule):
	"""Temuan Pasti yang belum diputuskan, ber-PIC, dalam batas nominal -> perbaikan dijalankan
	atas nama PIC (izin dan pemilik dokumen = PIC). Satu gagal = berhenti dan turun level."""
	limit = flt(rule.get("max_amount"))
	tasks = frappe.get_all("Agent Task", filters={
		"source": "Audit", "rule": rule.name, "status": ["!=", "Resolved"], "shadow": 0, "undone": 0,
		"confidence": PASTI, "decision": ["in", ["", None]], "exception_status": ["in", ["", None]],
		"fix": ["is", "set"], "assigned_to": ["is", "set"]}, fields=["name", "amount", "assigned_to"])
	original = frappe.session.user
	for t in tasks:
		if limit and flt(t.amount) > limit:
			continue
		doc = frappe.get_doc("Agent Task", t.name)
		fix = _fix(doc.fix) or {}
		kind, source = fix.get("kind"), fix.get("source")
		if kind not in REVERSIBLE:
			continue
		frappe.db.savepoint("audit_auto")
		try:
			frappe.set_user(t.assigned_to)
			result = run_fix(doc)
			if not _verify(kind, source, result):
				frappe.throw(_("Verifikasi gagal: hasil {0} tidak ditemukan atau tidak tertaut ke {1}.").format(result or "-", source))
		except Exception as e:
			frappe.set_user(original)
			frappe.db.rollback(save_point="audit_auto")
			doc.reload()
			why = frappe.utils.strip_html(str(e))[:300]
			orc._log(doc, "agent", _("Otomatis gagal, dikembalikan ke final check: {0}").format(why), actor="agent")
			doc.save(ignore_permissions=True)
			_demote(rule, _("perbaikan {0} gagal ({1})").format(doc.name, why))
			return
		finally:
			frappe.set_user(original)
		doc.reload()
		doc.update({"decision": AUTO, "decision_at": now_datetime(), "fix_result": result, "status": "In Progress",
		            "decision_note": _("Dijalankan otomatis atas nama {0}.").format(t.assigned_to)})
		orc._log(doc, "agent", _("Otomatis: {0}. Sebelum: {1}. Sesudah: {2}.").format(
			fix_label(fix), _before(kind, source), result), actor="agent")
		doc.save(ignore_permissions=True)
		orc._stat("auto")


@frappe.whitelist()
def undo(task):
	"""Batalkan hasil perbaikan (otomatis atau dari Setujui): draft dihapus, Packing List dibuka
	lagi. Temuan kembali ke final check. Hasil otomatis yang dibatalkan menurunkan level."""
	doc = frappe.get_doc("Agent Task", task)
	_can_decide(doc)
	fix = _fix(doc.fix) or {}
	kind, source = fix.get("kind"), fix.get("source")
	if not doc.fix_result or kind not in REVERSIBLE:
		frappe.throw(_("Tidak ada hasil perbaikan yang bisa dibatalkan."))
	if kind in _TARGET:
		target = _TARGET[kind][0]
		if frappe.db.exists(target, doc.fix_result):
			if frappe.db.get_value(target, doc.fix_result, "docstatus") != 0:
				frappe.throw(_("{0} sudah divalidasi. Batalkan lewat Void di dokumennya.").format(doc.fix_result))
			frappe.delete_doc(target, doc.fix_result)
		what = _("{0} {1} dihapus").format(target, doc.fix_result)
	else:
		from erpnext_custom.workflow import open_doc
		if cint(frappe.db.get_value("Packing List", source, "closed")):
			open_doc("Packing List", source)
		what = _("Packing List {0} dibuka lagi").format(source)
	was_auto = doc.decision == AUTO
	doc.update({"undone": 1, "undone_by": frappe.session.user, "undone_at": now_datetime(), "fix_result": None,
	            "decision": None, "decision_note": None, "decision_by": None, "decision_at": None, "status": "Open"})
	orc._log(doc, "action", _("Dibatalkan: {0}. Temuan kembali ke final check.").format(what))
	doc.save(ignore_permissions=True)
	if was_auto:
		rule = frappe._dict(orc._rule_of(doc))
		_demote(rule, _("hasil otomatis {0} dibatalkan {1}").format(task, frappe.session.user))
	orc._changed()
	return what


# --- API laporan & final check --------------------------------------------------------------


def _can_decide(doc):
	if doc.source != "Audit":
		frappe.throw(_("Bukan temuan pemeriksaan."))
	if doc.status == "Resolved":
		frappe.throw(_("Temuan sudah selesai."))
	if not (orc._is_manager() or doc.assigned_to == frappe.session.user):
		frappe.throw(_("Temuan ini bukan untuk Anda."), frappe.PermissionError)


def _decide(doc, decision, note=None):
	user = frappe.session.user
	doc.decision, doc.decision_note, doc.decision_by, doc.decision_at = decision, note, user, now_datetime()
	if decision == "Setuju":
		if doc.shadow:
			msg = _("Setuju (uji diam: perbaikan tidak dijalankan).")
		else:
			result = run_fix(doc)
			doc.fix_result = result
			msg = _("Setuju. {0}").format(_("Hasil: {0}.").format(result) if result else _("Ditangani manual."))
	elif decision == "Koreksi":
		msg = _("Koreksi: {0}").format(note)
	else:
		doc.exception_status = "Diajukan"
		msg = _("Ditolak, diajukan sebagai pengecualian: {0}").format(note)
		rule = orc._rule_of(doc)
		orc._notify(doc, orc._role_users(rule.get("controller_role") or "Orchestrator Controller"),
		            _("Pengecualian perlu persetujuan: {0}").format(doc.subject), rule)
	doc.status = "In Progress"
	doc.assigned_to = doc.assigned_to or user
	orc._log(doc, "action", msg)
	doc.save(ignore_permissions=True)
	return msg


@frappe.whitelist()
def decide(task, decision, note=None):
	"""Final check satu temuan: Setuju (jalankan perbaikan), Koreksi, atau Tolak (wajib alasan,
	jadi pengecualian setelah disetujui Controller)."""
	if decision not in ("Setuju", "Koreksi", "Tolak"):
		frappe.throw(_("Keputusan tidak dikenal."))
	note = (note or "").strip()
	if decision != "Setuju" and not note:
		frappe.throw(_("Tulis alasannya: dipakai untuk mengukur ketepatan pemeriksaan."))
	doc = frappe.get_doc("Agent Task", task)
	_can_decide(doc)
	msg = _decide(doc, decision, note or None)
	orc._changed()
	return msg


@frappe.whitelist()
def approve_all():
	"""Setujui semua temuan Pasti milik saya yang belum diputuskan. Satu gagal tidak menghentikan yang lain."""
	user = frappe.session.user
	names = frappe.get_all("Agent Task", filters={"source": "Audit", "status": ["!=", "Resolved"], "assigned_to": user,
	                                              "confidence": PASTI, "decision": ["in", ["", None]], "shadow": 0}, pluck="name")
	done, failed = 0, []
	for name in names:
		try:
			_decide(frappe.get_doc("Agent Task", name), "Setuju")
			frappe.db.commit()
			done += 1
		except Exception as e:
			frappe.db.rollback()
			failed.append(f"{name}: {frappe.utils.strip_html(str(e))[:200]}")
	orc._changed()
	return {"done": done, "failed": failed}


@frappe.whitelist()
def decide_exception(task, approve, note=None):
	"""Controller memutuskan pengajuan pengecualian. Disetujui = temuan dengan kondisi sama tidak
	muncul lagi; kondisi berubah (nilai/tanggal/bukti) = muncul lagi."""
	if not orc._is_manager():
		frappe.throw(_("Hanya Controller/Admin yang memutuskan pengecualian."), frappe.PermissionError)
	doc = frappe.get_doc("Agent Task", task)
	if doc.exception_status != "Diajukan":
		frappe.throw(_("Tidak ada pengajuan pengecualian di temuan ini."))
	doc.exception_by = frappe.session.user
	if cint(approve):
		doc.exception_status = "Disetujui"
		orc._resolve(doc, "Pengecualian", _("Pengecualian disetujui: {0}").format(doc.decision_note or note or ""),
		             frappe.session.user)
	else:
		doc.exception_status = "Ditolak"
		doc.status = "Open"
		doc.decision = None
		orc._log(doc, "action", _("Pengecualian ditolak Controller{0}").format(f": {note}" if note else "."))
		orc._notify(doc, [doc.decision_by or doc.assigned_to], _("Pengecualian ditolak: {0}").format(doc.subject), orc._rule_of(doc))
		doc.save(ignore_permissions=True)
	orc._changed()


@frappe.whitelist()
def toggle_shadow(name, shadow):
	orc._need_manager()
	if frappe.db.get_value("Orchestrator Rule", name, "source") != "Audit":
		frappe.throw(_("Uji Diam hanya untuk pemeriksaan."))
	frappe.db.set_value("Orchestrator Rule", name, "shadow", cint(shadow))
	return cint(shadow)


def _failed_checks():
	runs = {(k.decode() if isinstance(k, bytes) else k): v for k, v in (frappe.cache().hgetall("orchestrator:runs") or {}).items()}
	out = []
	for r in audit_rules():
		run = runs.get(r.name) or {}
		if run.get("error"):
			out.append({"check": CHECKS.get(r.audit_check, ("-",))[0], "error": run["error"], "at": run.get("at")})
	return out


def _row(t):
	age = date_diff(today(), t.since_date) if t.since_date else 0
	return {
		"name": t.name, "subject": t.subject, "description": t.description, "status": t.status,
		"check": t.audit_check, "check_title": CHECKS.get(t.audit_check, ("-",))[0], "category": t.category,
		"confidence": t.confidence, "amount": flt(t.amount), "age": age, "since": t.since_date,
		"reference_doctype": t.reference_doctype, "reference_name": t.reference_name,
		"fix_label": fix_label(t.fix), "fix_kind": (_fix(t.fix) or {}).get("kind"), "fix_result": t.fix_result, "decision": t.decision,
		"decision_note": t.decision_note, "exception_status": t.exception_status, "assigned_to": t.assigned_to,
		"assigned_name": frappe.db.get_value("User", t.assigned_to, "full_name") if t.assigned_to else "",
		"shadow": t.shadow, "new": False, "undone": t.undone,
		# prioritas: nilai x umur; temuan tanpa nilai tetap naik pelan menurut umur
		"priority": (flt(t.amount) + 1_000_000) * (1 + age / 30),
	}


_TASK_FIELDS = ["name", "subject", "description", "status", "audit_check", "category", "confidence", "amount",
                "since_date", "reference_doctype", "reference_name", "fix", "fix_result", "decision", "decision_note",
                "exception_status", "assigned_to", "shadow", "creation", "resolved_at", "outcome", "undone"]


def _last_digest(user):
	return frappe.cache().get_value(f"audit:digest_at:{user}")


@frappe.whitelist()
def report(view="mine"):
	"""Laporan untuk final check. mine = temuan saya; team = semua temuan + pengajuan pengecualian
	+ temuan tanpa PIC (Controller/Admin); shadow = temuan uji diam + ketepatan per pemeriksaan."""
	user = frappe.session.user
	manager = orc._is_manager()
	if view != "mine" and not manager:
		view = "mine"
	filters = {"source": "Audit", "status": ["!=", "Resolved"], "shadow": 1 if view == "shadow" else 0}
	if view == "mine":
		filters["assigned_to"] = user
	tasks = frappe.get_all("Agent Task", filters=filters, fields=_TASK_FIELDS, limit=2000)
	since = _last_digest(user)
	rows = [_row(t) for t in tasks]
	for r, t in zip(rows, tasks):
		r["new"] = bool(since and t.creation > frappe.utils.get_datetime(since))
	rows.sort(key=lambda r: -r["priority"])
	todo = [r for r in rows if not r["decision"] and r["exception_status"] != "Diajukan"]
	resolved_filters = {"source": "Audit", "status": "Resolved", "shadow": filters["shadow"],
	                    "resolved_at": [">", since or add_days(now_datetime(), -1)]}
	if view == "mine":
		resolved_filters["assigned_to"] = user
	out = {
		"view": view, "is_manager": manager,
		"summary": {
			"count": len(rows), "todo": len(todo), "amount": sum(r["amount"] for r in rows),
			"oldest": max([r["age"] for r in rows] or [0]),
			"new": sum(1 for r in rows if r["new"]),
			"resolved": frappe.db.count("Agent Task", resolved_filters),
			"since": since,
			"approvable": sum(1 for r in todo if r["confidence"] == PASTI and r["assigned_to"] == user),
			"auto": frappe.db.count("Agent Task", {**({"assigned_to": user} if view == "mine" else {}), "source": "Audit",
			                                       "decision": AUTO, "decision_at": [">", since or add_days(now_datetime(), -1)]}),
		},
		"todo": todo,
		"exceptions": [r for r in rows if r["exception_status"] == "Diajukan"],
		"working": [r for r in rows if r["decision"] and r["decision"] != AUTO and r["exception_status"] != "Diajukan"],
		"auto": [r for r in rows if r["decision"] == AUTO],
		"failed": _failed_checks(),
		"legend": [{"code": r.audit_check, "title": CHECKS[r.audit_check][0], "meaning": MEANING.get(r.audit_check, ""),
		            "days": cint(r.threshold_hours) // 24} for r in audit_rules() if r.audit_check in CHECKS],
		"enabled": orc.switch_on() and orc.switch_on("orchestrator_audit_enabled"),
	}
	if manager:
		# untuk pesan kosong: temuan yang ada di tampilan lain
		out["elsewhere"] = {v: frappe.db.count("Agent Task", {"source": "Audit", "status": ["!=", "Resolved"], "shadow": int(v == "shadow")})
		                    for v in ("team", "shadow") if v != view}
	if view == "team":
		out["unassigned"] = sum(1 for r in rows if not r["assigned_to"])
	if view in ("team", "shadow"):
		out["checks"] = []
		for r in audit_rules():
			if r.audit_check not in CHECKS:
				continue
			p = promotion(r)
			out["checks"].append({"name": r.name, "code": r.audit_check, "title": CHECKS[r.audit_check][0],
			                      "shadow": cint(r.shadow), "autonomy": r.autonomy or "Final check",
			                      "open": sum(1 for x in rows if x["check"] == r.audit_check), **check_stats(r.audit_check),
			                      "eligible": p["eligible"], "reasons": p["reasons"]})
		out["is_admin"] = _is_admin()
	return out


@frappe.whitelist()
def my_count():
	"""Angka di item sidebar "Laporan Saya": jumlah Tugas Saya (orchestrator.my_tasks)."""
	return orc.my_task_count()


# --- laporan harian -------------------------------------------------------------------------


def _report_link(view):
	"""Temuan sendiri -> Laporan Saya; tampilan tim / uji diam -> konsol Orchestrator."""
	return "/app/laporan-saya" if view == "mine" else f"/app/orchestrator?view={view}"


def _digest_html(rep, title):
	s = rep["summary"]
	link = get_url() + _report_link(rep["view"])
	lines = "".join(
		f"<tr><td style='padding:4px 8px'>{frappe.utils.escape_html(r['confidence'] or '')}</td>"
		f"<td style='padding:4px 8px'>{frappe.utils.escape_html(r['subject'])}"
		f"{('<br><small>' + frappe.utils.escape_html(_('Disiapkan') + ': ' + r['fix_label']) + '</small>') if r['fix_label'] else ''}</td></tr>"
		for r in rep["todo"][:10])
	failed = "".join(f"<p style='color:#b42318'>{frappe.utils.escape_html(_('Pemeriksaan tidak jalan: {0}').format(f['check']))}</p>"
	                 for f in rep["failed"])
	return (
		f"<p><b>{frappe.utils.escape_html(title)}</b></p>"
		f"<p>{_('{0} temuan, {1} perlu keputusan, nilai tertahan {2}, tertua {3} hari. Sejak laporan lalu: {4} baru, {5} beres, {6} dikerjakan agent otomatis.').format(s['count'], s['todo'], _money(s['amount']), s['oldest'], s['new'], s['resolved'], s['auto'])}</p>"
		f"{failed}<table>{lines}</table>"
		f"<p><a href='{link}'>{_('Buka laporan dan lakukan final check')}</a></p>"
	)


def _send(user, rep, title):
	s = rep["summary"]
	if not (s["count"] or s["resolved"] or rep["failed"]):
		return False
	subject = _("Laporan pemeriksaan: {0} temuan, {1} perlu keputusan").format(s["count"], s["todo"])
	try:
		frappe.get_doc({"doctype": "Notification Log", "subject": subject, "for_user": user, "type": "Alert",
		                "link": _report_link(rep["view"]),
		                "email_content": _digest_html(rep, title)}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "audit.digest notify")
	email = frappe.db.get_value("User", user, "email")
	if email and any(cint(r.send_email) for r in audit_rules()):
		frappe.sendmail(recipients=[email], subject=subject, message=_digest_html(rep, title))
	return True


def send_digest():
	"""Satu laporan per orang per hari (cron di hooks): PIC = temuannya sendiri, Controller = tim,
	Admin = uji diam. Delta 'baru/beres' dihitung dari laporan sebelumnya."""
	rules = audit_rules()
	if not rules or not (orc.switch_on() and orc.switch_on("orchestrator_audit_enabled")):
		return
	original = frappe.session.user
	pics = {u for u in frappe.get_all("Agent Task", filters={"source": "Audit", "status": ["!=", "Resolved"], "shadow": 0},
	                                   pluck="assigned_to") if u}
	controllers = {u for r in rules for u in orc._role_users(r.controller_role)}
	admins = {u for r in rules if cint(r.shadow) for u in orc._role_users(r.admin_role)}
	plan = [(u, "mine", _("Temuan Anda")) for u in pics] + [(u, "team", _("Ringkasan tim")) for u in controllers] \
		+ [(u, "shadow", _("Uji diam: temuan yang belum dikirim ke user")) for u in admins]
	sent = set()
	for user, view, title in plan:
		try:
			frappe.set_user(user)
			if _send(user, report(view), title):
				sent.add(user)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"audit.digest {user}")
		finally:
			frappe.set_user(original)
	for user in sent:
		frappe.cache().set_value(f"audit:digest_at:{user}", str(now_datetime()))
	frappe.db.commit()

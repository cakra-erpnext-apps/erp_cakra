"""Jurnal AP Note (APNotes) & AR Note (ARNotes). Jalankan lewat bench console:

	from erp.fico import test_notes; test_notes.run()

(bench execute menyembunyikan error asli jadi "name 'erp' is not defined".)
Yang dijaga: Validate memposting JE dengan baris party di sisi yang benar (AR = Dr Piutang
Customer, AP = Cr Hutang Supplier) sebesar Net Total, outstanding di Payment Ledger = Net
Total, kode Type ikut nomor; batal validasi menghapus jurnal; Don't Post To GL = tanpa
jurnal; Skip Payable ditolak di Payment Entry. Semuanya di-rollback di akhir.
"""

import frappe
from frappe.utils import flt


def run():
	try:
		for dt in ("APNote Type", "ARNote Type"):
			frappe.get_doc({"doctype": dt, "code": "ZTST", "title": "Test"}).insert()
		_check("ARNotes", "Customer", "Income", "AR/ZTST/", "debit")
		_check("APNotes", "Supplier", "Expense", "AP/ZTST/", "credit")
		_check_flags()
		_check_payment("APNotes", "Pay", "Supplier")
		_check_payment("ARNotes", "Receive", "Customer")
		_check_landed_cost()
		print("Notes OK")
	finally:
		frappe.db.rollback()


def _new(doctype, root_type="Expense", **extra):
	company = frappe.defaults.get_global_default("company")
	account = frappe.get_all("Account", {"root_type": root_type, "is_group": 0, "disabled": 0, "company": company, "account_type": ["not in", ["Receivable", "Payable"]]}, pluck="name", limit=1)[0]
	return frappe.get_doc({
		"doctype": doctype,
		"note_type": "ZTST",
		"associate": frappe.get_all("Supplier" if doctype == "APNotes" else "Customer", pluck="name", limit=1)[0],
		"date": frappe.utils.today(),
		"cost_center": frappe.get_all("Cost Center", {"is_group": 0, "company": company}, pluck="name", limit=1)[0],
		"tax_pct": 11,
		"pph_pct": 2,
		"items": [
			{"description": "Baris 1", "account": account, "qty": 2, "price": 500000},
			{"description": "Baris 2", "account": account, "qty": 1, "price": 250000},
		],
		**extra,
	}).insert()


def _check(doctype, party_type, root_type, prefix, party_side):
	doc = _new(doctype, root_type)
	assert doc.name.startswith(prefix), doc.name
	assert flt(doc.net_total) == 1250000 + 137500 - 25000, doc.net_total

	doc.validated = 1
	doc.save()
	assert doc.status == "Validated" and doc.journal_entry
	je = frappe.get_doc("Journal Entry", doc.journal_entry)
	assert je.docstatus == 1
	party_rows = [a for a in je.accounts if a.party_type == party_type]
	assert len(party_rows) == 1 and flt(party_rows[0].get(party_side)) == flt(doc.net_total), party_rows
	outstanding = frappe.db.sql(
		"select sum(amount) from `tabPayment Ledger Entry` where voucher_no=%s and delinked=0", je.name
	)[0][0]
	# PLE hutang bertanda negatif; yang dijaga besarnya.
	assert abs(flt(outstanding)) == flt(doc.net_total), outstanding

	doc.validated = 0
	doc.save()
	assert not doc.journal_entry and not frappe.db.exists("Journal Entry", je.name)


def _check_flags():
	from erp.fico.notes import guard_payment_entry

	# Don't Post To GL: Validate tanpa jurnal.
	doc = _new("APNotes", dont_post_to_gl=1)
	doc.validated = 1
	doc.save()
	assert doc.status == "Validated" and not doc.journal_entry

	# Skip Payable: jurnal ada, tapi PV yang mereferensikannya ditolak.
	doc = _new("APNotes", skip_payable=1)
	doc.validated = 1
	doc.save()
	assert doc.journal_entry
	pe = frappe._dict(references=[frappe._dict(reference_doctype="Journal Entry", reference_name=doc.journal_entry)])
	try:
		guard_payment_entry(pe)
		raise AssertionError("Skip Payable lolos ke PV")
	except frappe.ValidationError as e:
		assert "Skip Payable" in str(e), e

	# Cost Center per baris (modal Add Item) ikut ke baris jurnalnya; kosong = header.
	company = frappe.defaults.get_global_default("company")
	ccs = frappe.get_all("Cost Center", {"is_group": 0, "company": company}, pluck="name", limit=2)
	if len(ccs) == 2:
		doc = _new("APNotes")
		doc.items[0].cost_center = ccs[1]
		doc.cost_center = ccs[0]
		doc.validated = 1
		doc.save()
		je = frappe.get_doc("Journal Entry", doc.journal_entry)
		debit_ccs = {a.cost_center for a in je.accounts if a.debit and a.account == doc.items[0].account}
		assert debit_ccs == {ccs[0], ccs[1]}, debit_ccs

	# Save: baris Amount 0 dibuang, baris tanpa Account Code ditolak.
	doc = _new("APNotes")
	doc.append("items", {"description": "kosong", "account": doc.items[0].account, "qty": 1, "price": 0})
	doc.save()
	assert len(doc.items) == 2 and [it.idx for it in doc.items] == [1, 2], [(it.idx, it.amount) for it in doc.items]
	doc.append("items", {"description": "tanpa akun", "qty": 1, "price": 5})
	try:
		doc.save()
		raise AssertionError("baris tanpa Account Code lolos")
	except frappe.ValidationError as e:
		assert "Account Code" in str(e), e

	# Smart input: PPN nominal (tanpa persen) dipakai apa adanya, persen dihitung dari total.
	doc = _new("APNotes", tax_pct=0, tax_amount=150000, pph_pct=2)
	assert flt(doc.tax_amount) == 150000 and flt(doc.pph_amount) == 25000, (doc.tax_amount, doc.pph_amount)
	assert flt(doc.net_total) == 1250000 + 150000 - 25000, doc.net_total


def _check_payment(doctype, payment_type, party_type):
	"""Note Validated muncul di Add Items PE yang sesuai, jadi referensi Journal Entry, dan
	PE yang di-Validate (submit) mengisi Amount Paid in PV + status Paid."""
	from erp.fico.notes import payment_outstanding
	from erpnext_custom.overrides.payment_entry import _all_payment_items

	company = frappe.defaults.get_global_default("company")
	draft = _new(doctype, "Income" if doctype == "ARNotes" else "Expense")
	assert not payment_outstanding(doctype, draft.associate, company) or all(
		r["transaction"] != draft.name for r in payment_outstanding(doctype, draft.associate, company)), "Draft ikut ditawarkan"
	draft.validated = 1
	draft.save()
	frappe.cache().delete_keys("cmi_payment_items:")
	rows = [r for r in _all_payment_items(party_type, draft.associate, company, payment_type) if r["transaction"] == draft.name]
	assert len(rows) == 1 and flt(rows[0]["outstanding"]) == flt(draft.net_total), rows
	other = "Receive" if payment_type == "Pay" else "Pay"
	assert not [r for r in _all_payment_items(party_type, draft.associate, company, other) if r["transaction"] == draft.name]

	bank = frappe.get_all("Account", {"account_type": ["in", ["Bank", "Cash"]], "is_group": 0, "disabled": 0,
	                                  "company": company, "account_currency": frappe.get_cached_value("Company", company, "default_currency")},
	                      pluck="name", limit=1)[0]
	pe = frappe.new_doc("Payment Entry")
	pe.update({"payment_type": payment_type, "party_type": party_type, "party": draft.associate,
	           "company": company, "posting_date": frappe.utils.today(),
	           "paid_from" if payment_type == "Pay" else "paid_to": bank,
	           "cost_center": draft.cost_center})
	r = rows[0]
	pe.append("custom_items", {"document_type": doctype, "document_no": draft.name, "doc_label": r["doc_label"],
	                           "journal_entry": r["journal_entry"], "grand_total": r["grand_total"],
	                           "outstanding": r["outstanding"], "amount": r["outstanding"], "currency": r["currency"]})
	# Di layar diisi JS (cmi_sync_paid); di tes diisi langsung.
	pe.paid_amount = pe.received_amount = flt(r["outstanding"])
	pe.source_exchange_rate = pe.target_exchange_rate = 1
	pe.insert()
	refs = [x for x in pe.references if x.reference_doctype == "Journal Entry" and x.reference_name == draft.journal_entry]
	assert len(refs) == 1 and flt(refs[0].allocated_amount) == flt(draft.net_total), [(x.reference_doctype, x.reference_name, x.allocated_amount) for x in pe.references]
	pe.flags.cmi_action_ok = True
	pe.submit()
	draft.reload()
	assert flt(draft.paid_amount) == flt(draft.net_total) and draft.status == "Paid", (draft.paid_amount, draft.status)


def _check_landed_cost():
	"""AP Note ber-Purchase Invoice (biaya HPP, pola Ascend APNote.HPP): baris dijurnal ke
	Persediaan In Transit, Landed Cost Voucher memindahkannya ke nilai persediaan barang PI
	(GL PI: Cr In Transit), dan batal validasi mengembalikan semuanya."""
	from erpnext_custom.in_transit import transit_account

	company = frappe.defaults.get_global_default("company")
	transit = transit_account(company)
	pi = frappe.db.sql("""select pi.name from `tabPurchase Invoice` pi
		join `tabPurchase Invoice Item` i on i.parent = pi.name
		join tabItem it on it.name = i.item_code and it.is_stock_item = 1
		where pi.docstatus = 1 and pi.update_stock = 1 and pi.company = %s and ifnull(i.warehouse, '') != ''
		limit 1""", company)
	if not (transit and pi):
		print("Landed cost dilewati: butuh Company.custom_in_transit_account + PI update_stock")
		return
	pi = pi[0][0]

	def transit_credit():
		return flt(frappe.db.sql("""select sum(credit) - sum(debit) from `tabGL Entry`
			where voucher_type = 'Purchase Invoice' and voucher_no = %s and account = %s and is_cancelled = 0""",
			(pi, transit))[0][0])

	before = transit_credit()
	doc = _new("APNotes", purchase_invoice=pi, tax_pct=0, tax_amount=0, pph_pct=0, pph_amount=0)
	assert {it.account for it in doc.items} == {transit}, [it.account for it in doc.items]
	doc.validated = 1
	doc.save()
	assert doc.journal_entry and doc.landed_cost_voucher
	je_transit = sum(flt(a.debit) for a in frappe.get_doc("Journal Entry", doc.journal_entry).accounts if a.account == transit)
	assert je_transit == flt(doc.total_amount), je_transit
	assert frappe.db.get_value("Landed Cost Voucher", doc.landed_cost_voucher, "docstatus") == 1
	assert flt(transit_credit() - before, 2) == flt(doc.total_amount), (transit_credit(), before)

	lcv = doc.landed_cost_voucher
	doc.validated = 0
	doc.save()
	assert not doc.landed_cost_voucher and not frappe.db.exists("Landed Cost Voucher", lcv)
	assert flt(transit_credit(), 2) == flt(before, 2), (transit_credit(), before)

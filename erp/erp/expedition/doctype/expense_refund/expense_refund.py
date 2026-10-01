"""Expense Refund — kebalikan Expense Note: mengembalikan biaya yang sudah dikeluarkan
(dibayar) ke Supplier, penuh atau sebagian.

Sama seperti Expense Note, dokumen ini TIDAK memakai Frappe submit (docstatus), tapi
triplet ``validated`` / ``void`` manual. Saat Validate, dibuat Journal Entry sendiri
(Debit Hutang Supplier — Credit akun biaya asal, kebalikan jurnal Expense Note), lalu
JE itu "ditarik" ke Payment Entry (Receive, party Supplier) untuk benar-benar mencairkan
uangnya — persis pola Expense Note ditarik-bayar, tinggal arahnya dibalik.
"""

from frappe.model.document import Document
from frappe.utils import flt, now_datetime

import frappe


class ExpenseRefund(Document):
	def validate(self):
		self._guard_locked()
		if self.void and not (self.void_reason or "").strip():
			frappe.throw("Alasan Void wajib diisi.")
		self._default_company()
		self._require_same_source()
		self._calculate_totals()
		self._require_within_paid()
		self._sync_state()

	def _guard_locked(self):
		"""Setelah Validate atau Void, dokumen terkunci — mirror Expense Note."""
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		is_mgr = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
		if before.validated:
			if self.validated:
				frappe.throw(
					"Expense Refund ini sudah <b>Tervalidasi</b> dan terkunci. "
					"Batalkan validasi dulu untuk mengubah."
				)
			if not is_mgr:
				frappe.throw("Hanya Accounts Manager / System Manager yang boleh membatalkan validasi.")
		if before.void:
			if self.void:
				frappe.throw(
					"Expense Refund ini sudah di-<b>Void</b> dan terkunci. "
					"Batalkan Void dulu untuk mengubah."
				)
			if not is_mgr:
				frappe.throw("Hanya Accounts Manager / System Manager yang boleh membuka Void.")

	def _default_company(self):
		if not self.company:
			self.company = (
				frappe.defaults.get_global_default("company")
				or (frappe.get_all("Company", pluck="name", limit_page_length=1) or [None])[0]
			)

	def _require_same_source(self):
		"""Semua baris harus dari Expense Note vendor & mata uang yang sama dengan header —
		satu Expense Refund cuma bisa ditarik ke satu Payment Entry (satu party, satu currency)."""
		ens = {it.expense_note for it in (self.items or []) if it.expense_note}
		if not ens:
			return
		rows = frappe.get_all(
			"Expense Note", filters={"name": ["in", list(ens)]},
			fields=["name", "vendor", "currency", "conversion_rate"],
		)
		by_name = {r.name: r for r in rows}
		for en in ens:
			src = by_name.get(en)
			if not src:
				continue
			if self.vendor and src.vendor != self.vendor:
				frappe.throw(
					f"Baris dari <b>{en}</b> (Supplier {src.vendor}) beda Supplier dengan "
					f"header (<b>{self.vendor}</b>). Pisahkan jadi Expense Refund lain."
				)
			if self.currency and src.currency and src.currency != self.currency:
				frappe.throw(
					f"Baris dari <b>{en}</b> mata uang <b>{src.currency}</b>, beda dengan "
					f"header (<b>{self.currency}</b>). Satu Expense Refund harus satu mata uang."
				)

	# ---- totals -----------------------------------------------------------
	def _calculate_totals(self):
		subtotal = discount = tax = pph = materai = 0.0
		for it in self.items or []:
			subtotal += flt(it.refund_amount)
			discount += flt(it.discount)
			tax += flt(it.tax)
			pph += flt(it.pph)
			materai += flt(it.materai)
		self.subtotal = subtotal
		self.discount_amount = discount
		self.tax_amount = tax
		self.pph_amount = pph
		self.materai_amount = materai
		self.net_total = flt(subtotal) - discount + tax - pph + materai

	def _require_within_paid(self):
		"""Total refund per Expense Note (bersih: base - discount + tax - pph + materai)
		tidak boleh melebihi sisa yang sudah dibayar EN itu (paid_amount dikurangi yang
		sudah direfund dokumen LAIN)."""
		if not self.validated or self.void:
			return
		by_en = {}
		for it in self.items or []:
			if not it.expense_note:
				continue
			g = by_en.setdefault(it.expense_note, {"amt": 0.0, "tax": 0.0, "pph": 0.0,
			                                        "discount": 0.0, "materai": 0.0})
			g["amt"] += flt(it.refund_amount)
			g["tax"] += flt(it.tax)
			g["pph"] += flt(it.pph)
			g["discount"] += flt(it.discount)
			g["materai"] += flt(it.materai)
		for en, g in by_en.items():
			net = flt(g["amt"]) - g["discount"] + g["tax"] - g["pph"] + g["materai"]
			if net <= 0.005:
				continue
			paid = flt(frappe.db.get_value("Expense Note", en, "paid_amount"))
			already = other_refunded_amount(en, exclude_er=self.name if not self.is_new() else None)
			if net > (paid - already) + 0.005:
				frappe.throw(
					f"Refund untuk <b>{en}</b> ({frappe.utils.fmt_money(net)}) melebihi sisa yang "
					f"bisa direfund (sudah dibayar {frappe.utils.fmt_money(paid)}, sudah direfund "
					f"dokumen lain {frappe.utils.fmt_money(already)})."
				)

	# ---- state machine ------------------------------------------------------
	def _sync_state(self):
		user = frappe.session.user
		now = now_datetime()
		if self.validated:
			if not self.validated_by:
				self.validated_by = user
				self.validated_date = now
		else:
			self.validated_by = None
			self.validated_date = None
		if self.void:
			if not self.void_by:
				self.void_by = user
				self.void_datetime = now
		else:
			self.void_by = None
			self.void_datetime = None
		self.status = derive_status(self)

	# ---- Journaling: Debit Hutang Supplier — Credit akun biaya asal ----------
	def on_update(self):
		self._sync_journal()

	def _sync_journal(self):
		should_post = bool(self.validated) and not bool(self.void)
		je = self.journal_entry
		ens = {it.expense_note for it in (self.items or []) if it.expense_note}
		if should_post and not je:
			self.db_set("journal_entry", self._create_journal_entry())
		elif (not should_post) and je:
			self.db_set("journal_entry", None)
			self._cancel_journal_entry(je)
			if self.received:
				self.db_set({"received": 0, "received_date": None})
		_refresh_source_refunded_amounts(ens)

	def _create_journal_entry(self):
		rate = flt(self.conversion_rate) or 1.0
		root_cache = {}
		debit_by_account = {}
		for it in self.items or []:
			acc = it.expense_account
			if not acc:
				frappe.throw(f"Baris '{it.description or it.expense_note}' belum punya Expense Account.")
			if acc not in root_cache:
				root_cache[acc] = frappe.db.get_value("Account", acc, "account_type")
			debit_by_account[acc] = flt(debit_by_account.get(acc, 0)) + flt(it.refund_amount) * rate
		debit_by_account = {a: flt(v, 2) for a, v in debit_by_account.items() if flt(v, 2)}
		if not debit_by_account and not (self.tax_amount or self.pph_amount or self.discount_amount or self.materai_amount):
			frappe.throw("Tidak ada nominal refund untuk dijurnal.")

		from erpnext.accounts.party import get_party_account

		payable = get_party_account("Supplier", self.vendor, self.company)
		if not payable:
			payable = frappe.db.get_single_value("ERPNext Custom Setting", "default_payable_account")
		if not payable:
			frappe.throw(
				f"Supplier <b>{self.vendor}</b> belum punya akun Hutang (Payable) default, dan "
				"<b>Default Hutang</b> di ERPNext Custom Setting juga kosong."
			)

		cc = self.cost_center
		s = frappe.get_cached_doc("ERPNext Custom Setting")
		adj = s.get("adjustment_account")

		def comp_acc(field, label):
			acc = s.get(field) or adj
			if not acc:
				frappe.throw(
					f"Set <b>Akun {label}</b> di <b>ERPNext Custom Setting</b> "
					"(atau isi Akun Pajak & Penyesuaian sebagai fallback)."
				)
			return acc

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.is_system_generated = 1
		je.posting_date = self.refund_date
		je.company = self.company
		je.cheque_date = self.refund_date
		en_list = ", ".join(sorted({it.expense_note for it in (self.items or []) if it.expense_note}))
		je.user_remark = f"Expense Refund {self.name} ({en_list})" + (f" — {self.remark}" if self.remark else "")
		je.name = self.name
		je.flags.name_set = True

		def add(account, drcr, amt, remark=None, party=False):
			row = {"account": account, "cost_center": cc, drcr: amt}
			if party:
				row.update({"party_type": "Supplier", "party": self.vendor})
			if remark:
				row["user_remark"] = remark
			je.append("accounts", row)

		# Credit balik ke akun biaya asal (kebalikan Debit di jurnal Expense Note).
		for acc, amt in debit_by_account.items():
			add(acc, "credit_in_account_currency", amt, en_list, party=(root_cache.get(acc) == "Payable"))

		# Komponen: arah DIBALIK dari Expense Note (tax debit->credit, pph/discount
		# credit->debit, materai debit->credit).
		comp_total = {"tax": 0.0, "pph": 0.0, "discount": 0.0, "materai": 0.0}
		comp_def = (
			("tax", "tax_account", "PPN (Masukan)", "credit_in_account_currency", "PPN"),
			("pph", "pph_account", "PPh", "debit_in_account_currency", "PPh"),
			("discount", "discount_account", "Discount", "debit_in_account_currency", "Discount"),
			("materai", "materai_account", "Materai", "credit_in_account_currency", "Materai"),
		)
		for f, acc_field, acc_label, drcr, lbl in comp_def:
			amt = flt(flt(self.get(f + "_amount")) * rate, 2)
			if amt > 0:
				add(comp_acc(acc_field, acc_label), drcr, amt, lbl)
				comp_total[f] = amt

		# Debit: Hutang Supplier (Net Total refund).
		net = flt(flt(self.net_total) * rate, 2)
		je.append("accounts", {
			"account": payable, "party_type": "Supplier", "party": self.vendor,
			"debit_in_account_currency": net,
		})

		subtotal = flt(sum(debit_by_account.values()), 2)
		resid = flt(
			(subtotal + comp_total["pph"] + comp_total["discount"])
			- (comp_total["tax"] + comp_total["materai"] + net), 2)
		if abs(resid) > 0.005:
			if not adj:
				frappe.throw(
					"Set <b>Akun Pajak & Penyesuaian</b> di ERPNext Custom Setting (selisih pembulatan)."
				)
			line = {"account": adj, "cost_center": cc}
			line["debit_in_account_currency" if resid > 0 else "credit_in_account_currency"] = abs(resid)
			je.append("accounts", line)

		je.flags.ignore_permissions = True
		je.insert()
		je.title = f"{self.name} - {self.vendor}"
		je.submit()
		frappe.msgprint(f"Journal Entry <b>{je.name}</b> dibuat.", alert=True)
		return je.name

	def _cancel_journal_entry(self, je_name):
		"""Batalkan lalu hapus JE milik Expense Refund ini — sama seperti Expense Note."""
		if not je_name or not frappe.db.exists("Journal Entry", je_name):
			return
		je = frappe.get_doc("Journal Entry", je_name)
		if je.docstatus == 1:
			je.flags.ignore_permissions = True
			je.cancel()
		for ple in frappe.get_all(
			"Payment Ledger Entry", filters={"voucher_no": je_name, "delinked": 0}, pluck="name"
		):
			frappe.db.set_value("Payment Ledger Entry", ple, "delinked", 1, update_modified=False)
		frappe.delete_doc(
			"Journal Entry", je_name,
			force=1, ignore_permissions=True, delete_permanently=True,
		)


def derive_status(doc):
	get = doc.get
	if get("void"):
		return "Void"
	if get("received"):
		return "Received"
	if get("receipt_status") == "Partial":
		return "Partial Received"
	if get("validated"):
		return "Validated"
	return "Draft"


def refresh_status(er_name):
	row = frappe.db.get_value(
		"Expense Refund", er_name,
		["void", "received", "receipt_status", "validated"], as_dict=True,
	)
	if not row:
		return None
	status = derive_status(row)
	frappe.db.set_value("Expense Refund", er_name, "status", status, update_modified=False)
	return status


def other_refunded_amount(en_name, exclude_er=None):
	"""Total refund bersih (base - discount + tax - pph + materai) untuk satu Expense Note,
	dari Expense Refund LAIN yang sudah Validated & bukan Void. `exclude_er` = dokumen yang
	sedang diedit (biar bisa direvisi tanpa dianggap "menabrak dirinya sendiri")."""
	row = frappe.db.sql(
		"""select sum(i.refund_amount) amt, sum(i.discount) disc, sum(i.tax) tax,
		          sum(i.pph) pph, sum(i.materai) mat
		   from `tabExpense Refund Item` i
		   join `tabExpense Refund` er on er.name = i.parent
		   where i.expense_note = %(en)s and er.validated = 1 and er.void = 0
		     and er.name != %(exclude)s""",
		{"en": en_name, "exclude": exclude_er or ""},
		as_dict=True,
	)
	r = row[0] if row else {}
	return flt(r.get("amt")) - flt(r.get("disc")) + flt(r.get("tax")) - flt(r.get("pph")) + flt(r.get("mat"))


def refunded_amount_for_en(en_name):
	"""Total refund bersih SEMUA Expense Refund (Validated, non-void) untuk satu EN —
	dipakai mengisi ulang Expense Note.refunded_amount."""
	return other_refunded_amount(en_name, exclude_er=None)


def _refresh_source_refunded_amounts(en_names):
	for en in {n for n in (en_names or []) if n}:
		if not frappe.db.exists("Expense Note", en):
			continue
		frappe.db.set_value(
			"Expense Note", en, "refunded_amount", refunded_amount_for_en(en), update_modified=False,
		)


def _payment_entries(er_name):
	"""Payment Entry yang menarik Expense Refund ini — draft ikut dihitung (mirror Expense Note)."""
	if not er_name:
		return []
	return frappe.db.sql_list(
		"""select distinct parent from `tabPayment Entry Reference`
		   where custom_expense_refund = %(er)s and parenttype = 'Payment Entry' and docstatus < 2""",
		{"er": er_name},
	)


def sync_document_links(er_names):
	"""Isi kolom list view Payment dari Payment Entry yang menariknya — mirror Expense Note."""
	for er in {n for n in (er_names or []) if n}:
		if not frappe.db.exists("Expense Refund", er):
			continue
		frappe.db.set_value(
			"Expense Refund", er,
			{"payment_no": ", ".join(sorted(_payment_entries(er))) or None},
			update_modified=False,
		)


def _expense_note_candidates(vendor, company=None):
	"""Baris item Expense Note (Validated, non-void) milik `vendor` yang EN-nya masih ada
	sisa dibayar untuk direfund (paid_amount - refunded_amount > 0) — satu baris per baris
	item, bukan per dokumen (tiap baris bisa beda expense_account/pajak)."""
	filters = {"vendor": vendor, "validated": 1, "void": 0}
	if company:
		filters["company"] = company
	ens = frappe.get_all(
		"Expense Note", filters=filters,
		fields=["name", "date", "currency", "conversion_rate", "paid_amount", "refunded_amount"],
		order_by="date asc, name asc",
	)
	rows = []
	for en in ens:
		sisa_en = flt(en.paid_amount) - flt(en.refunded_amount)
		if sisa_en <= 0.005:
			continue
		items = frappe.get_all(
			"Expense Note Item", filters={"parent": en.name, "parenttype": "Expense Note"},
			fields=["name", "description", "expense_account", "amount", "tax", "pph", "discount", "materai"],
			order_by="idx",
		)
		for it in items:
			if not it.expense_account or not flt(it.amount):
				continue
			rows.append({
				"transaction": it.name,
				"expense_note": en.name,
				"expense_note_item": it.name,
				"description": it.description or "",
				"expense_account": it.expense_account,
				"date": str(en.date or ""),
				"currency": en.currency,
				"conversion_rate": en.conversion_rate,
				"sisa_en": sisa_en,
				"amount": flt(it.amount),
				"tax": flt(it.tax), "pph": flt(it.pph),
				"discount": flt(it.discount), "materai": flt(it.materai),
			})
	return rows


@frappe.whitelist()
def get_expense_note_transactions(vendor, company=None):
	"""Baris Expense Note yang bisa direfund milik `vendor` — flat list, dikelompokkan di
	client per Expense Note (mirror get_reimburse_expense_notes Sales Invoice: satu
	frappe.call, tanpa paging server — volumenya kecil per vendor)."""
	if not (vendor and frappe.has_permission("Expense Refund", "read")):
		return []
	return _expense_note_candidates(vendor, company)

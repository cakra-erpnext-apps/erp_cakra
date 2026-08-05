"""Payment Entry — kustomisasi "Tarik Expense Note".

Expense Note (app `erp`) saat Validate memposting Journal Entry:
    Dr Akun Biaya — Cr Hutang Supplier (party_type=Supplier, party=vendor).
JE itu otomatis jadi *outstanding* di akun Hutang supplier (terlacak di Payment
Ledger Entry). Tombol "Tarik Expense Note" di Payment Entry (Pay → Supplier)
menarik JE tsb sebagai baris References, sehingga saat Payment Entry di-submit:
    Dr Hutang Usaha — Cr Bank (paid_from)   ⇒  "Hutang Usaha X Bank Mandiri"
dan sisa hutang Expense Note berkurang.

Catatan: TIDAK ada logika outstanding yang ditulis ulang di sini. Angka diambil
dari helper ERPNext `get_outstanding_on_journal_entry` — sumber kebenaran yang
SAMA dipakai Payment Entry saat menghitung/submit, jadi tak akan beda.
"""

import re

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import getdate, today
from frappe.utils.data import flt

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

# Bulan romawi untuk penomoran (PV/MDR/0001/CMI/XI/26).
_ROMAN_MONTHS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
                 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII"}


def _pe_name_parts(no, seg, company, roman, yy):
    """Bagian nomor PE selain counter. `seg` (segmen sebelum nomor) kosong -> tak
    ada segmennya, jadi tidak muncul '//'. Dipakai dua kali: gabungan head+tail jadi
    KEY reset counter, dan counter disisipkan di antara head & tail untuk nama akhir.
        head=[PV,MDR] tail=[CMI,XI,26] -> key 'PV/MDR/CMI/XI/26/', nama 'PV/MDR/0001/CMI/XI/26'
        head=[PV]     tail=[CMI,XI,26] -> nama 'PV/0001/CMI/XI/26'  (expense/income)
    """
    head = [no] + ([seg] if seg else [])
    return head, [company, roman, yy]


def _bank_code(doc):
    """Kode bank untuk nomor dokumen = kata pertama account_name akun sisi bank
    (mis. "MDR 167-00-0792787-3" -> MDR). Settlement memakai akun settlement-nya."""
    side = "paid_to" if doc.payment_type == "Receive" else "paid_from"
    acc = doc.get(side) or doc.get("custom_settlement_account")
    if not acc and doc.get("bank_account"):
        acc = frappe.db.get_value("Bank Account", doc.bank_account, "account")
    name = frappe.db.get_value("Account", acc, "account_name") if acc else ""
    code = (name or "").split()[0] if name else ""
    code = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    return code or "XXX"


def _is_settlement(doc):
	"""Settlement = Mode of Payment "Settlement" (user pilih akun pengganti sisi bank).

	Checkbox custom_settlement (cara lama, field-nya kini hidden) tetap dihormati: dokumen
	lama menyimpannya tercentang dengan mode of payment apa pun, dan mengabaikannya di sini
	membuat jurnalnya berpindah ke bank saat dokumen itu dibuka & disimpan ulang."""
	return (doc.get("mode_of_payment") or "").strip().lower() == "settlement" or bool(
		doc.get("custom_settlement")
	)


def _apply_direct_and_settlement(doc):
	"""Mode tambahan Payment Entry (CMI):

	- custom_direct ("Expense / Income"): TANPA party & tanpa tarikan transaksi.
	  Nominal per baris custom_direct_items (note + account wajib + amount) diposting
	  langsung: Pay -> Dr tiap akun item, Cr Bank; Receive -> Dr Bank, Cr tiap akun
	  item. Penerima/pengirim dicatat di field teks custom_payto.
	- Mode of Payment "Settlement": sisi BANK diganti akun custom_settlement_account
	  (Pay: paid_from, Receive: paid_to) — pelunasan via akun perantara, bukan bank.
	Default (tanpa Expense/Income & mode of payment lain): perilaku native (party -> bank).
	"""
	# Settlement diproses DULUAN: sisi bank diganti akun settlement, sehingga
	# placeholder mode direct di bawah bisa menyalin akun yang sudah final.
	if _is_settlement(doc):
		if not doc.get("custom_settlement_account"):
			frappe.throw(_(
				"Mode of Payment <b>Settlement</b>: pilih <b>Settlement Account</b> "
				"(akun pengganti sisi Bank)."
			))
		if doc.payment_type == "Pay":
			doc.paid_from = doc.custom_settlement_account
		elif doc.payment_type == "Receive":
			doc.paid_to = doc.custom_settlement_account
	if doc.get("custom_direct"):
		doc.party_type = None
		doc.party = None
		doc.party_name = None
		doc.set("references", [])
		doc.set("custom_expense_notes", [])
		# Satu grid dua mode: baris direct = custom_items ber-Account (tanpa dokumen).
		items = [d for d in (doc.get("custom_items") or []) if flt(d.amount)]
		if not items:
			frappe.throw(_("Mode Expense / Income: isi minimal 1 baris item (account + amount) di tabel Items."))
		missing = [d.idx for d in items if not d.get("account")]
		if missing:
			frappe.throw(_("Mode Expense / Income: baris {0} belum punya Account.").format(
				", ".join(str(i) for i in missing)))
		total = sum(flt(d.amount) for d in items)
		doc.paid_amount = total
		doc.received_amount = total
		# Satu mata uang transaksi; sisi party kosong membuat kurs target tidak terisi.
		doc.source_exchange_rate = doc.source_exchange_rate or 1
		doc.target_exchange_rate = doc.target_exchange_rate or 1
		# Skema PE mewajibkan paid_from & paid_to terisi. Sisi party tidak dipakai
		# GL pada mode direct (add_party_gl_entries kita yang jalan) — isi placeholder
		# = akun bank supaya lolos mandatory tanpa efek jurnal.
		company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		if doc.payment_type == "Pay":
			doc.paid_to = doc.paid_to or doc.paid_from
			bank_account = doc.paid_from
		else:
			doc.paid_from = doc.paid_from or doc.paid_to
			bank_account = doc.paid_to
		transaction_currency = (
			frappe.get_cached_value("Account", bank_account, "account_currency")
			if bank_account else None
		) or company_currency
		doc.paid_from_account_currency = transaction_currency
		doc.paid_to_account_currency = transaction_currency


class CMIPaymentEntry(PaymentEntry):
	"""Override controller core Payment Entry tanpa mengedit erpnext."""

	def autoname(self):
		"""Nomor PE: {PV|RV}/{seg}/{####}/{CMI}/{roman}/{yy}, counter DI TENGAH.

		`seg` (segmen sebelum nomor):
		  - Settlement (Pay/Receive)  -> "STL", WALAU bank dipilih.
		  - Expense/Income (direct)   -> kosong -> nomor jadi PV/0001/CMI/XI/26.
		  - selain itu                -> kode bank (mis. MDR).

		Counter di tengah tak bisa via naming-series `.####.` (Frappe mengunci reset pada
		bagian SEBELUM ####). Jadi counter dihitung sendiri lewat getseries dengan key =
		seluruh bagian nama tanpa counter -> reset per (type, seg, company, bulan, tahun),
		sama seperti Sales Invoice (parse_inv_counter). Tahun/bulan dari POSTING DATE.
		Dokumen amend tidak lewat sini (Frappe menamai NAMA-1 lebih dulu, lihat set_new_name).
		"""
		from erpnext_custom.overrides.sales_invoice import _company_code

		# Pastikan sisi bank terisi sebelum kode bank diambil (autoname jalan lebih
		# dulu dari before_validate). Idempoten — aman dipanggil dua kali.
		_apply_direct_and_settlement(self)
		_fill_bank_side(self)
		_apply_direct_and_settlement(self)

		d = getdate(self.posting_date or today())
		no = {"Pay": "PV", "Receive": "RV"}.get(self.payment_type, "PE")
		if _is_settlement(self):
			seg = "STL"
		elif self.get("custom_direct"):
			seg = ""
		else:
			seg = _bank_code(self)
		company = _company_code(self.company)
		roman = _ROMAN_MONTHS[d.month]
		yy = d.strftime("%y")

		head, tail = _pe_name_parts(no, seg, company, roman, yy)
		counter = getseries("/".join(head + tail) + "/", 4)
		self.name = "/".join(head + [counter] + tail)

		# Komponen tampilan (field hidden, dipakai print/laporan).
		self.custom_no_code = no
		self.custom_bank_code = seg
		self.custom_company_code = company
		self.custom_year = yy
		self.custom_month_roman = roman

	def validate_transaction_reference(self):
		"""Cheque/Reference No & Date TIDAK wajib.

		ERPNext mewajibkannya begitu sisi bank berupa akun bertipe Bank. Untuk CMI itu
		menghambat: sebagian besar pembayaran ditarik dari Expense Note/invoice dan nomor
		referensi banknya baru diketahui belakangan. Fieldnya tetap ada, cuma tidak memaksa.
		"""
		return

	def set_missing_values(self):
		if self.get("custom_direct"):
			# Tanpa party — core melempar "Party is mandatory".
			self.references = []
			return
		super().set_missing_values()

	def set_missing_ref_details(self, *args, **kwargs):
		if self.get("custom_direct"):
			return
		return super().set_missing_ref_details(*args, **kwargs)

	def set_unallocated_amount(self):
		# EN valas: pelunasan penuh via custom_items (bukan reference native), jadi native
		# mengira SELURUH paid belum teralokasi (Outstanding jadi angka penuh & menyesatkan).
		# Untuk mode ini Outstanding = 0 (memang lunas).
		if _valas_en_ctx(self):
			self.unallocated_amount = 0
		else:
			super().set_unallocated_amount()
		# Kolom list "Paid" (mata uang bayar) = paid_amount. Dihitung di sini karena
		# paid_amount sudah final saat set_unallocated_amount dipanggil (dalam set_amounts).
		self.custom_paid = flt(self.paid_amount)

	def set_difference_amount(self):
		if self.get("custom_direct"):
			# Sisi party digantikan baris item: selisih = nominal bank - total item
			# - deductions (harus 0 supaya jurnal balance).
			items_total = sum(flt(d.amount) for d in self.get("custom_items") or [])
			base = self.base_paid_amount if self.payment_type == "Pay" else self.base_received_amount
			total_deductions = sum(flt(d.amount) for d in self.get("deductions") or [])
			self.difference_amount = flt(
				flt(base) - items_total - total_deductions, self.precision("difference_amount")
			)
			return
		if _valas_en_ctx(self):
			# GL valas dibangun sendiri (Dr Hutang@buku + Selisih Kurs + Cr Bank@bayar) dan sudah
			# balance by construction; jangan biarkan core menghitung selisih dari reference.
			self.difference_amount = 0
			return
		super().set_difference_amount()

	def make_gl_entries(self, *args, **kwargs):
		# Dont Post To GL: submit tanpa jurnal (dokumen catatan). Konsekuensi: outstanding
		# dokumen referensi TIDAK berkurang (tidak ada Payment Ledger Entry).
		if self.get("custom_dont_post_to_gl"):
			return
		ctx = _valas_en_ctx(self)
		if ctx and self.payment_type == "Pay":
			return self._make_valas_en_gl(ctx)
		return super().make_gl_entries(*args, **kwargs)

	def _make_valas_en_gl(self, ctx):
		"""GL pembayaran Expense Note valas. Kurs BUKU dari EN, kurs BAYAR = source_exchange_rate
		(sisi bank native). Per baris EN:
		    Dr Hutang (payable IDR)  = alokasi * kurs buku   (di-link ke JE EN utk rekonsiliasi)
		    Cr Bank (mata uang bank) = alokasi (acc-cur) / alokasi * kurs bayar (base IDR)
		    Dr/Cr Selisih Kurs       = alokasi * (kurs bayar - kurs buku)
		"""
		from erpnext.accounts.general_ledger import make_gl_entries as _post
		company_cur = frappe.get_cached_value("Company", self.company, "default_currency")
		bank_cur = self.paid_from_account_currency or company_cur
		pay_rate = _valas_en_pay_rate(self, ctx)
		gl = []
		total_bank_base = 0.0
		total_alloc = 0.0
		total_fx = 0.0
		for c in ctx:
			if not c.alloc:
				continue
			dr_base = flt(c.alloc * c.book_rate, 2)
			bank_base = flt(c.alloc * pay_rate, 2)
			total_bank_base += bank_base
			total_alloc += c.alloc
			total_fx += (bank_base - dr_base)
			gl.append(self.get_gl_dict({
				"account": c.payable,
				"party_type": "Supplier",
				"party": c.vendor,
				"against": self.paid_from,
				"cost_center": self.cost_center,
				"debit": dr_base,
				"debit_in_account_currency": dr_base,
				"against_voucher_type": "Journal Entry" if c.je else None,
				"against_voucher": c.je or None,
			}, item=c.row))
		# Komponen di luar tabel (semua nominal MATA UANG PEMBAYARAN × kurs bayar):
		#   Tax (PPN Masukan), Materai, Admin bank -> DEBIT (menambah bayar)
		#   PPh -> KREDIT hutang PPh (dipotong)
		comp = _valas_components(self)
		acc = _valas_component_accounts(self.company)
		for key, sett in (("tax", "tax"), ("materai", "materai"), ("admin", "admin")):
			amt = flt(comp.get(key))
			if amt:
				if not acc.get(sett):
					frappe.throw(_("Akun untuk <b>{0}</b> belum di-set di ERPNext Custom Setting.").format(key))
				total_alloc += amt
				gl.append(self.get_gl_dict({
					"account": acc[sett], "against": self.paid_from, "cost_center": self.cost_center,
					"debit": flt(amt * pay_rate, 2), "debit_in_account_currency": flt(amt * pay_rate, 2),
				}, item=self))
		if flt(comp.pph):
			total_alloc -= flt(comp.pph)
			gl.append(self.get_gl_dict({
				"account": acc["pph"], "against": self.paid_from, "cost_center": self.cost_center,
				"credit": flt(comp.pph * pay_rate, 2), "credit_in_account_currency": flt(comp.pph * pay_rate, 2),
			}, item=self))
		# Credit/Debit Note per baris (× kurs): Credit account DIDEBIT, Debit account DIKREDIT.
		for c in ctx:
			cn, dn = flt(c.row.get("credit_amount")), flt(c.row.get("debit_amount"))
			if cn and c.row.get("credit_account"):
				total_alloc += cn
				gl.append(self.get_gl_dict({
					"account": c.row.credit_account, "against": self.paid_from,
					"cost_center": c.row.get("credit_cost_center") or self.cost_center,
					"debit": flt(cn * pay_rate, 2), "debit_in_account_currency": flt(cn * pay_rate, 2),
				}, item=c.row))
			if dn and c.row.get("debit_account"):
				total_alloc -= dn
				gl.append(self.get_gl_dict({
					"account": c.row.debit_account, "against": self.paid_from,
					"cost_center": c.row.get("debit_cost_center") or self.cost_center,
					"credit": flt(dn * pay_rate, 2), "credit_in_account_currency": flt(dn * pay_rate, 2),
				}, item=c.row))
		total_bank_base = flt(total_alloc * pay_rate, 2)  # kas keluar = (alokasi + komponen) × kurs
		# Sisi bank (Cr). Bank valas (USD): account-currency = total alokasi (USD), base = IDR.
		funding = self._pending_cash_funding() if self.payment_type == "Pay" else []
		for item in funding:
			gl.append(self.get_gl_dict({
				"account": item["account"],
				"party_type": item["party_type"],
				"party": item["party"],
				"against": self.party or c.vendor,
				"cost_center": self.cost_center,
				"credit": item["base_amount"],
				"credit_in_account_currency": item["account_amount"],
			}, item=self))
		bank_base = total_bank_base - sum(item["base_amount"] for item in funding)
		if bank_base < -0.005:
			frappe.throw(_("Pending Cash melebihi nilai pembayaran Payment Entry."))

		bank_row = {
			"account": self.paid_from,
			"against": self.party or c.vendor,
			"cost_center": self.cost_center,
			"credit": flt(max(bank_base, 0), 2),
			"credit_in_account_currency": (
				flt(max(bank_base, 0), 2)
				if bank_cur == company_cur else flt(max(bank_base, 0) / pay_rate, 2)
			),
		}
		if bank_base > 0.005:
			gl.append(self.get_gl_dict(bank_row, item=self))
		# Selisih kurs (rugi = debit, laba = credit).
		if abs(total_fx) > 0.005:
			fx_acc = frappe.get_cached_value("Company", self.company, "exchange_gain_loss_account")
			if not fx_acc:
				frappe.throw(_("Set <b>Exchange Gain/Loss Account</b> di Company untuk pembayaran valas."))
			line = {"account": fx_acc, "against": self.party or c.vendor, "cost_center": self.cost_center}
			line["debit" if total_fx > 0 else "credit"] = abs(flt(total_fx, 2))
			gl.append(self.get_gl_dict(line, item=self))
		_post(gl, cancel=(self.docstatus == 2), merge_entries=False, update_outstanding="Yes")

	def get_gl_dict(self, args, account_currency=None, item=None):
		from erpnext_custom.overrides import fill_cost_center

		return fill_cost_center(self, super().get_gl_dict(args, account_currency, item), item)

	# Credit/Debit Note per baris tarikan TIDAK punya baris GL sendiri lagi: _apply_items_adjustment
	# menerjemahkannya jadi baris tabel `deductions` bawaan, jadi add_deductions_gl_entries core
	# yang memposting sekaligus menghitungnya di difference_amount / unallocated_amount.
	# `allocation_date` SENGAJA tetap tidak dipakai sebagai posting_date: satu voucher dengan
	# beberapa tanggal posting membuat tutup buku & rekonsiliasi tidak konsisten.

	# ---- Pembayaran yang didanai UANG MUKA (tabel Pending Cash) --------------------
	# Pending Cash saat Paid mencatat: Dr Uang Muka (party = penerima) / Cr Bank — uangnya
	# SUDAH keluar dari bank saat itu. Jadi ketika uang muka itu dipakai membayar tagihan di
	# Payment Entry ini, yang berkurang adalah uang mukanya, BUKAN bank lagi:
	#     Dr Hutang (party PE)                         <- add_party_gl_entries (bawaan)
	#     Cr Uang Muka (party penerima uang muka)      <- add_bank_gl_entries di bawah
	# Menagih ulang ke bank berarti uang yang sama keluar dua kali dari kas.

	def _pending_cash_funding(self):
		"""[(account, party_type, party, amount)] — kredit uang muka pengganti sisi bank.

		Akun & party diambil dari JURNAL Pending Cash-nya, bukan dihitung ulang dari master:
		yang harus ditutup adalah baris yang benar-benar diposting dulu. Party-nya penerima
		uang muka (mis. Andi) — belum tentu party Payment Entry ini (mis. BPJS KESEHATAN);
		memakai party PE membuat saldo uang muka penerimanya tidak pernah tertutup.
		"""
		out = []
		for r in self.get("custom_pending_items") or []:
			amount = flt(r.allocated)
			if not (amount and r.transaction):
				continue
			je = frappe.db.get_value("Pending Cash", r.transaction, "journal_entry")
			if not je:
				frappe.throw(_(
					"Pending Cash <b>{0}</b> belum punya Journal Entry (belum Paid?), "
					"tidak bisa dipakai membayar."
				).format(r.transaction))
			side = frappe.db.get_value(
				"Journal Entry Account", {"parent": je, "debit": [">", 0]},
				["account", "party_type", "party", "debit", "debit_in_account_currency"],
				as_dict=True,
			)
			if not side:
				frappe.throw(_(
					"Journal Entry <b>{0}</b> milik Pending Cash <b>{1}</b> tidak punya baris "
					"debit uang muka."
				).format(je, r.transaction))
			account_rate = (
				flt(side.debit) / flt(side.debit_in_account_currency)
				if flt(side.debit_in_account_currency) else 1
			)
			out.append({
				"account": side.account,
				"party_type": side.party_type,
				"party": side.party,
				# allocated Pending Cash disimpan dalam mata uang company.
				"base_amount": amount,
				"account_amount": amount / (account_rate or 1),
			})
		return out

	def add_bank_gl_entries(self, gl_entries):
		funding = self._pending_cash_funding() if self.payment_type == "Pay" else []
		if not funding:
			return super().add_bank_gl_entries(gl_entries)

		rate = flt(self.source_exchange_rate) or 1.0
		for item in funding:
			gl_entries.append(self.get_gl_dict({
				"account": item["account"],
				"party_type": item["party_type"],
				"party": item["party"],
				"against": self.party or self.paid_to,
				"account_currency": frappe.get_cached_value(
					"Account", item["account"], "account_currency"
				),
				"credit_in_account_currency": item["account_amount"],
				"credit": item["base_amount"],
				"cost_center": self.cost_center,
				"post_net_value": True,
			}, item=self))

		# Kelebihan di luar uang muka tetap keluar dari bank (mis. uang muka 2jt dipakai
		# membayar tagihan 3jt -> 1jt sisanya dari bank).
		from_bank_base = flt(self.base_paid_amount) - sum(f["base_amount"] for f in funding)
		if from_bank_base > 0.005:
			gl_entries.append(self.get_gl_dict({
				"account": self.paid_from,
				"account_currency": self.paid_from_account_currency,
				"against": self.party or self.paid_to,
				"credit_in_account_currency": from_bank_base / rate,
				"credit": from_bank_base,
				"cost_center": self.cost_center,
				"post_net_value": True,
			}, item=self))

	def _pending_cash_against(self, gl_entries, start):
		"""Kolom "against" sisi party dibuat core = akun bank; padahal lawannya kini akun
		uang muka. Dibetulkan supaya laporan tidak menyebut bank yang tak dipakai."""
		funding = self._pending_cash_funding() if self.payment_type == "Pay" else []
		if not funding:
			return
		accounts = list(dict.fromkeys(f["account"] for f in funding))
		if flt(self.base_paid_amount) - sum(f["base_amount"] for f in funding) > 0.005:
			accounts.append(self.paid_from)
		against = ", ".join(accounts)
		for row in gl_entries[start:]:
			if row.get("party"):
				row["against"] = against

	def add_party_gl_entries(self, gl_entries):
		if not self.get("custom_direct"):
			start = len(gl_entries)
			super().add_party_gl_entries(gl_entries)
			self._pending_cash_against(gl_entries, start)
			return
		# Mode Expense / Income: baris GL dari tiap item (lawan = sisi bank/settlement).
		against = self.paid_from if self.payment_type == "Pay" else self.paid_to
		default_cc = self.cost_center or frappe.get_cached_value("Company", self.company, "cost_center")
		for it in self.get("custom_items") or []:
			amt = flt(it.amount)
			if not amt:
				continue
			row = {
				"account": it.account,
				"against": against,
				"cost_center": it.cost_center or default_cc,
				"remarks": " - ".join(x for x in (it.get("description"), it.get("note")) if x) or self.remarks,
			}
			if self.payment_type == "Pay":
				row.update({"debit": amt, "debit_in_account_currency": amt})
			else:
				row.update({"credit": amt, "credit_in_account_currency": amt})
			gl_entries.append(self.get_gl_dict(row, item=it))


def _fill_bank_side(doc):
    """Sisi BANK (Pay: paid_from, Receive: paid_to) diisi otomatis kalau kosong,
    supaya user cukup pilih supplier + item lalu Save → jurnal Dr Hutang / Cr Bank.

    Urutan sumber: akun default Mode of Payment (per company) → Company Default Bank
    Account → Company Default Cash Account. Pilihan user / mode Settlement (yang sudah
    mengganti sisi bank) TIDAK ditimpa. Field account-currency (disembunyikan dari form)
    selalu diisi dari akunnya — inilah yang memicu error mandatory "Account Currency
    (From)" kalau dibiarkan kosong."""
    side = "paid_from" if doc.payment_type == "Pay" else "paid_to"
    if not doc.get(side):
        acc = None
        # 1) Bank Account terpilih -> akun GL-nya; 2) Bank terpilih -> rekening company
        # bank itu (sekalian mengisi bank_account).
        if doc.get("bank_account"):
            acc = frappe.db.get_value("Bank Account", doc.bank_account, "account")
        if not acc and doc.get("custom_bank"):
            ba_filters = {"bank": doc.custom_bank, "is_company_account": 1}
            if doc.company:
                ba_filters["company"] = doc.company
            ba = frappe.db.get_value("Bank Account", ba_filters, ["name", "account"], as_dict=True)
            if ba:
                doc.bank_account = doc.bank_account or ba.name
                acc = ba.account
        if not acc and doc.get("mode_of_payment"):
            acc = frappe.db.get_value(
                "Mode of Payment Account",
                {"parent": doc.mode_of_payment, "company": doc.company},
                "default_account",
            )
        if not acc:
            acc = frappe.get_cached_value("Company", doc.company, "default_bank_account") \
                or frappe.get_cached_value("Company", doc.company, "default_cash_account")
        if acc:
            doc.set(side, acc)
        else:
            frappe.throw(_(
                "Akun Bank belum terisi. Pilih <b>Account Paid From</b> (akun Bank/Kas), "
                "atau set akun default di <b>Mode of Payment</b> / <b>Default Bank Account</b> "
                "di Company supaya terisi otomatis."
            ))
    # Account currency (field-nya hidden) — isi dari akun masing-masing sisi.
    # Dokumen legacy sering hanya punya paid_from/paid_to, sementara Bank Account dan
    # custom_bank kosong. Turunkan keduanya dari akun GL final supaya setelah Validate
    # pilihan Bank tetap terlihat dan konsisten dengan akun yang benar-benar dijurnal.
    if doc.get(side) and (not doc.get("bank_account") or not doc.get("custom_bank")):
        ba = frappe.db.get_value(
            "Bank Account",
            {
                "account": doc.get(side),
                "company": doc.company,
                "is_company_account": 1,
            },
            ["name", "bank"],
            as_dict=True,
        )
        if ba:
            doc.bank_account = doc.bank_account or ba.name
            doc.custom_bank = doc.custom_bank or ba.bank
    for cur_f, acc_f in (("paid_from_account_currency", "paid_from"),
                         ("paid_to_account_currency", "paid_to")):
        if doc.get(acc_f) and not doc.get(cur_f):
            doc.set(cur_f, frappe.get_cached_value("Account", doc.get(acc_f), "account_currency"))


def _apply_remark(doc):
    """Field "Remark" (custom_remark_note, section paling bawah) = remarks dokumen.
    custom_remarks=1 memberi tahu ERPNext supaya set_remarks() TIDAK menimpanya dengan
    kalimat generated ("Amount X received from ...")."""
    note = (doc.get("custom_remark_note") or "").strip()
    if note:
        doc.remarks = note
        doc.custom_remarks = 1


def _apply_pe_smart_inputs(doc):
    """Smart input Amount Tax / PPh di bawah Payment Item — parse "11%"/"150000" ke
    storage pct/amount (mirror Sales Invoice). Materai = Currency nominal biasa.
    CATATAN: nilainya BELUM diposting ke GL / memengaruhi paid_amount — menunggu
    desain jurnalnya (permintaan user: bangun tabelnya dulu)."""
    from erpnext_custom.overrides.sales_invoice import _parse_smart

    for in_f, pct_f, amt_f in (
        ("custom_tax_input", "custom_tax_pct", "custom_tax_amount"),
        ("custom_pph_input", "custom_pph_pct", "custom_pph_amount"),
    ):
        raw = doc.get(in_f)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            doc.set(pct_f, 0)
            doc.set(amt_f, 0)
            continue
        mode, num = _parse_smart(str(raw))
        if mode == "pct":
            doc.set(pct_f, num)
            base = sum(flt(r.amount) for r in (doc.get("custom_items") or []))
            doc.set(amt_f, flt(base) * num / 100.0)
        else:
            doc.set(pct_f, 0)
            doc.set(amt_f, num)


def _default_cost_center(doc):
    return doc.get("cost_center") or frappe.get_cached_value("Company", doc.company, "cost_center")


# Penanda baris Deductions yang DIBUAT dari kolom Credit/Debit Note (dibangun ulang tiap
# save). Baris Deductions yang diketik manual user & baris selisih kurs core tidak disentuh.
_ADJ_PREFIX = ("Credit Note ", "Debit Note ")

# Komponen header (di luar tabel: Tax/PPh/Materai/Biaya Admin) -> baris "Deductions or Loss"
# bawaan pada PE NON-valas, jadi paid_amount, GL, & difference core ikut menghitungnya tanpa
# baris GL buatan sendiri. (field custom, label baris, kunci akun, arah)
#   arah +1 = akun DIDEBIT, nambah bayar (Tax/Materai/Admin); -1 = akun DIKREDIT, ngurang (PPh).
# Mode valas: komponen diposting jalur GL sendiri (× kurs) di _make_valas_en_gl, bukan di sini.
_COMP_SPEC = (
    ("custom_tax_amount", "Tax (PPN)", "tax", 1),
    ("custom_materai_amount", "Materai", "materai", 1),
    ("custom_admin_fee", "Biaya Admin", "admin", 1),
    ("custom_pph_amount", "PPh", "pph", -1),
)
_COMP_LABELS = tuple(lbl for _, lbl, _, _ in _COMP_SPEC)


def _apply_items_adjustment(doc):
    """Credit / Debit Note per baris tarikan -> baris "Deductions or Loss" BAWAAN ERPNext.

    Arahnya tidak tergantung Pay/Receive (aturan yang sama dipakai sistem lama):
        Credit Note -> akunnya DIDEBIT   (PV: bayar lebih | RV: terima kurang)
        Debit Note  -> akunnya DIKREDIT  (PV: bayar kurang | RV: terima lebih)
    sehingga pelunasan dokumennya tetap penuh sementara uang bank yang bergerak berbeda:
        PV: paid = alokasi + CN - DN     RV: received = alokasi + DN - CN

    Kenapa lewat tabel `deductions` dan bukan baris GL sendiri: `deductions` ikut dihitung
    core di set_difference_amount & set_unallocated_amount, jadi CN/DN boleh TIDAK sama
    besar (dulu wajib sama, karena baris GL buatan sendiri tak dikenal core sehingga harus
    seimbang sendiri). Nilainya mata uang company — itu syarat core untuk tabel ini.

    Dokumen bersifat retur ditarik dengan alokasi NEGATIF; kedua leg ikut dibalik tandanya
    (padanan IsPositive di sistem lama).

    Hanya untuk baris MODE TARIKAN (punya document_no). Baris Expense/Income memakai
    Account + Amount-nya sendiri.
    """
    # Mode valas EN: Credit/Debit Note diposting jalur GL sendiri (× kurs), bukan lewat
    # tabel deductions company-currency. Jadi jangan dibangun deductions di sini.
    if _valas_en_ctx(doc):
        return
    default_cc = None
    new_rows = []
    for r in doc.get("custom_items") or []:
        if not r.get("document_no"):
            continue
        # Default Allocation Date = tanggal dokumen yang ditarik (bukan posting date PE).
        r.allocation_date = r.allocation_date or r.get("date") or doc.posting_date
        cn, dn = flt(r.credit_amount), flt(r.debit_amount)
        if not (cn or dn):
            continue  # baris tanpa penyesuaian — normal, mayoritas begini
        if cn and not r.get("credit_account"):
            frappe.throw(_("Baris <b>{0}</b>: <b>Credit Note</b> terisi, <b>Credit Account</b> belum.")
                         .format(r.document_no))
        if dn and not r.get("debit_account"):
            frappe.throw(_("Baris <b>{0}</b>: <b>Debit Note</b> terisi, <b>Debit Account</b> belum.")
                         .format(r.document_no))
        if default_cc is None:
            default_cc = _default_cost_center(doc)
        r.credit_cost_center = r.credit_cost_center or default_cc
        r.debit_cost_center = r.debit_cost_center or default_cc
        sign = -1 if flt(r.amount) < 0 else 1
        note = r.get("remark") or r.get("note") or r.get("description")
        if cn:
            new_rows.append((r.credit_account, r.credit_cost_center, sign * cn,
                             _ADJ_PREFIX[0] + r.document_no, r.get("note_credit") or note))
        if dn:
            new_rows.append((r.debit_account, r.debit_cost_center, -sign * dn,
                             _ADJ_PREFIX[1] + r.document_no, r.get("note_debit") or note))

    # Komponen header (Tax/PPh/Materai/Biaya Admin) -> baris Deductions (hanya arah Pay).
    if doc.payment_type == "Pay":
        # Default cost center ikut PE, TAPI kalau user sudah revisi cost center di baris
        # komponennya, pertahankan (baris dibangun ulang tiap save, tanpa ini revisi ke-reset).
        prev_cc = {(d.get("description") or ""): d.get("cost_center")
                   for d in (doc.get("deductions") or [])
                   if (d.get("description") or "") in _COMP_LABELS}
        acc = None
        for field, label, key, direction in _COMP_SPEC:
            amt = flt(doc.get(field))
            if not amt:
                continue
            if acc is None:
                acc = _valas_component_accounts(doc.company)
                if default_cc is None:
                    default_cc = _default_cost_center(doc)
            account = acc.get(key)
            if not account:
                frappe.throw(_("Akun untuk <b>{0}</b> belum di-set di ERPNext Custom Setting.").format(label))
            new_rows.append((account, prev_cc.get(label) or default_cc, direction * amt, label, None))

    keep = [d for d in (doc.get("deductions") or [])
            if not (d.get("description") or "").startswith(_ADJ_PREFIX + _COMP_LABELS)]
    if not (new_rows or len(keep) != len(doc.get("deductions") or [])):
        return  # tak ada CN/DN sekarang maupun sebelumnya
    doc.set("deductions", keep)
    for account, cost_center, amount, desc, note in new_rows:
        doc.append("deductions", {
            "account": account,
            "cost_center": cost_center,
            "amount": amount,
            "description": " - ".join(x for x in (desc, note) if x),
        })

    # Uang bank = alokasi digeser penyesuaian. Diisi di sini (bukan diserahkan ke user)
    # supaya difference_amount core jatuh nol tanpa hitung-hitungan manual.
    alloc = sum(flt(x.allocated_amount) for x in doc.get("references") or [])
    adj = sum(flt(d.amount) for d in doc.get("deductions") or [] if not d.get("is_exchange_gain_loss"))
    if not (alloc or adj):
        return
    paid = alloc + adj if doc.payment_type == "Pay" else alloc - adj
    doc.paid_amount = paid
    if flt(doc.source_exchange_rate or 0) in (0, 1) and flt(doc.target_exchange_rate or 0) in (0, 1):
        doc.received_amount = paid


def before_validate(doc, method=None):
    _apply_direct_and_settlement(doc)
    _fill_bank_side(doc)  # sisi bank auto (Mode of Payment / default Company)
    _apply_direct_and_settlement(doc)  # sinkronkan placeholder + currency dari akun bank final
    _apply_pe_smart_inputs(doc)
    _apply_remark(doc)
    _derive_references(doc)
    _apply_valas_en(doc)  # EN valas: paid_amount = Σ alokasi * kurs bayar (GL diposting terpisah)
    _apply_items_adjustment(doc)
    _apply_pending_cash(doc)  # setelah _derive_references: butuh paid_amount yang final
    _apply_item_summary(doc)  # Summary per baris = Pelunasan + Credit Note − Debit Note
    _apply_reference_summary(doc)  # paling akhir: baca references yang sudah final


def _apply_item_summary(doc):
    """Field Summary DI BAWAH tabel = total pelunasan bersih dari tabel
    = Σ (Pelunasan + Credit Note − Debit Note). Field tampilan; tidak memengaruhi GL."""
    total = sum(
        flt(r.amount) + flt(r.get("credit_amount")) - flt(r.get("debit_amount"))
        for r in (doc.get("custom_items") or []) if r.get("document_no")
    )
    doc.custom_summary = flt(total, 2)


def _apply_valas_en(doc):
    """Mode pembayaran Expense Note valas: baris EN-nya TIDAK jadi reference (diposting jalur
    GL sendiri saat submit). Mata uang & kurs diambil dari sisi BANK NATIVE:
        - mata uang bank (paid_from_account_currency) harus = mata uang EN (mis. USD)
        - kurs bayar = source_exchange_rate (IDR per USD)
    Yang disiapkan di sini: paid/received supaya lolos validasi core (GL asli tetap kita
    override). paid_amount = Σ alokasi (mata uang bank), received = base (IDR)."""
    ctx = _valas_en_ctx(doc)
    if not ctx or doc.payment_type != "Pay":
        return
    # Gerbang #2: satu PE satu mata uang; tak boleh campur EN mata uang lain / EN IDR.
    currencies = {c.currency for c in ctx}
    if len(currencies) > 1:
        frappe.throw(_("Satu Payment Entry hanya untuk satu mata uang. Ditemukan: {0}.").format(
            ", ".join(sorted(currencies))))
    other_en = [
        r for r in (doc.get("custom_items") or [])
        if r.get("document_type") == "Expense Note" and r.get("document_no")
        and r.document_no not in {c.en for c in ctx}
    ]
    if other_en:
        frappe.throw(_(
            "Tidak boleh mencampur Expense Note valas ({0}) dengan Expense Note mata uang lain "
            "dalam satu Payment Entry."
        ).format(currencies.pop()))
    # Mata uang BANK harus cocok dengan EN valas: bayar EN USD -> pakai bank USD.
    en_cur = ctx[0].currency
    if (doc.paid_from_account_currency or "") != en_cur:
        frappe.throw(_(
            "Expense Note ini <b>{0}</b>. Pilih <b>Account Paid From</b> (bank) bermata uang "
            "<b>{0}</b>, lalu isi <b>Exchange Rate</b>-nya."
        ).format(en_cur))
    alloc = _valas_en_alloc_total(ctx)                     # mis. 12.000 USD
    comp = _valas_components(doc)                           # tax/materai/admin/pph/CN/DN (USD)
    paid = flt(alloc + comp.net, 2)                        # USD keluar dari bank (total)
    rate = _valas_en_pay_rate(doc, ctx)                    # source_exchange_rate (IDR per USD)
    doc.source_exchange_rate = rate
    doc.paid_amount = paid
    doc.base_paid_amount = flt(paid * rate, 2)             # Paid Amount (IDR) = Paid USD × kurs
    # Sisi terima (party account IDR): received dalam IDR = base bank.
    doc.paid_to_account_currency = doc.paid_to_account_currency or \
        frappe.get_cached_value("Company", doc.company, "default_currency")
    doc.target_exchange_rate = 1
    doc.received_amount = flt(paid * rate, 2)
    doc.base_received_amount = flt(paid * rate, 2)


def _apply_reference_summary(doc):
    """Ringkas nomor dokumen di tabel References jadi satu Data, untuk kolom list.

    Kolom list HARUS field di dokumen induk — tabel anak tidak bisa jadi kolom. Field ini
    murni turunan (read-only, tidak pernah diisi manual), jadi dihitung ulang tiap simpan;
    baris References yang berubah otomatis ikut.

    Dipanggil PALING AKHIR di before_validate karena _derive_references dan
    _apply_pending_cash masih bisa menambah/mengubah baris References.
    """
    seen, names = set(), []
    for r in doc.get("references") or []:
        ref = (r.get("reference_name") or "").strip()
        # satu invoice bisa muncul >1 baris (mis. alokasi terpisah) — cukup sekali di ringkasan
        if ref and ref not in seen:
            seen.add(ref)
            names.append(ref)
    doc.custom_references = ", ".join(names)


def _apply_pending_cash(doc):
    """Isi tiap baris Pending Cash: Sisa (saat ini) + berapa yang TERPAKAI di Payment Entry ini.

    Yang terpakai BUKAN sebesar total Pending Cash-nya. Uang muka Rp 2.000.000 yang dipakai
    membayar tagihan Rp 22.200 hanya terpakai 22.200 — Rp 1.977.800 sisanya tetap milik
    supplier itu dan harus tetap bisa ditarik ke Payment Entry lain. Angka `allocated` inilah
    yang dijumlahkan _pending_cash_used saat menghitung sisa di dialog Add Pending Cash, jadi
    kesalahan di sini membuat uang muka hangus diam-diam.

    Pembagian mengikuti urutan baris: baris teratas menyerap dulu sampai nominal bayar PE ini
    habis. Nominal yang melebihi seluruh uang muka berarti dibayar dari bank — bukan urusan
    tabel ini. Dihitung di SERVER, bukan di form, supaya dokumen lewat API/import ikut benar.
    """
    # Pending Cash = uang muka yang kita BAYARKAN ke penerima, jadi hanya masuk akal untuk
    # arah Pay; Receive tidak mengenalnya. Barisnya DIBUANG, bukan sekadar dilewati: nilai
    # `allocated` yang tertinggal tetap dihitung _pending_cash_used sebagai "sudah terpakai"
    # (query-nya tidak melihat payment_type), sehingga uang muka itu terkunci di dokumen yang
    # tidak pernah memakainya dan hilang diam-diam dari dialog Add Pending Cash. Section-nya
    # memang sudah hidden saat Receive, tapi baris masih bisa terbawa dari draft yang arahnya
    # diubah, hasil copy/amend, atau dokumen lewat API.
    if doc.payment_type != "Pay":
        doc.set("custom_pending_items", [])
        doc.custom_pending_amount = 0
        return

    rows = [r for r in (doc.get("custom_pending_items") or []) if r.get("transaction")]
    if not rows:
        doc.custom_pending_amount = 0
        return

    names = [r.transaction for r in rows]
    totals = {
        r.name: flt(r.total)
        for r in frappe.get_all("Pending Cash", filters={"name": ["in", names]},
                                fields=["name", "total"])
    }
    # Dokumen ini sendiri dikecualikan: barisnya sedang dihitung ulang di sini.
    used = _pending_cash_used(names, exclude_parent=doc.name)

    # Pending Cash dalam mata uang company, sementara paid_amount mengikuti mata uang bank.
    # Bandingkan dengan nilai base agar cashbon IDR tidak dianggap sebagai nominal USD.
    # before_validate berjalan sebelum core menyegarkan base_paid_amount, jadi hitung dari
    # paid_amount × kurs sumber agar tidak memakai nilai base lama dari save sebelumnya.
    remaining = flt(doc.paid_amount) * (flt(doc.source_exchange_rate) or 1)
    for r in rows:
        available = flt(totals.get(r.transaction)) - flt(used.get(r.transaction))
        if available <= 0.005:
            frappe.throw(_(
                "Pending Cash <b>{0}</b> sudah habis dipakai di Payment Entry lain — "
                "hapus barisnya."
            ).format(r.transaction))
        r.grand_total = flt(totals.get(r.transaction))
        r.outstanding = available  # sisa SEBELUM Payment Entry ini
        take = min(available, remaining) if remaining > 0 else 0
        r.allocated = take
        remaining -= take
    # Ringkasan tampilan mengikuti nominal Pending Cash yang ditarik ke tabel
    # (Sisa sebelum PE ini), bukan nominal yang terpakai membayar PE (`allocated`).
    doc.custom_pending_amount = flt(sum(flt(r.outstanding) for r in rows), 2)


def _expense_note_journal(en):
    je = frappe.db.get_value("Expense Note", en, "journal_entry")
    if not je:
        frappe.throw(
            f"Expense Note <b>{en}</b> belum punya Journal Entry (belum Validate?), tidak bisa dibayar."
        )
    return je


# ============================================================================
# Pembayaran Expense Note VALAS (mata uang EN != mata uang company)
# ----------------------------------------------------------------------------
# Alur: EN valas tetap membukukan JE-nya di IDR (kurs buku) — pengakuan biaya IDR.
# Payment Entry membaca LANGSUNG dari Expense Note (bukan dari outstanding JE yang IDR):
# sisa dilacak dalam mata uang EN, dan saat submit GL diposting per baris EN:
#     Dr Hutang (akun payable IDR)  = alokasi * kurs BUKU EN
#     Dr/Cr Selisih Kurs            = alokasi * (kurs BAYAR - kurs BUKU)
#     Cr Bank                       = alokasi * kurs BAYAR
# EN IDR TIDAK lewat sini (jalur JE-reference lama tetap dipakai) — dijaga oleh cek
# currency != company currency. Jadi jalur pembayaran non-valas sama sekali tak berubah.
# ============================================================================

def _en_payable_account(company, vendor, je):
    """Akun Hutang (payable, IDR) tempat hutang EN berada. Diambil dari baris party JE
    EN-nya supaya konsisten dengan yang dulu diposting; fallback ke akun default supplier."""
    if je:
        acc = frappe.db.get_value(
            "Journal Entry Account",
            {"parent": je, "party_type": "Supplier", "party": vendor},
            "account",
        )
        if acc:
            return acc
    from erpnext.accounts.party import get_party_account
    return get_party_account("Supplier", vendor, company)


def _valas_en_ctx(doc):
    """Konteks baris custom_items yang membayar Expense Note VALAS.

    Kembalikan list frappe._dict(row, en, vendor, book_rate, payable, je, alloc) untuk tiap
    baris EN yang mata uangnya != mata uang company. KOSONG => mode valas tidak aktif dan
    seluruh jalur pembayaran lama dipakai apa adanya."""
    company_cur = frappe.get_cached_value("Company", doc.company, "default_currency")
    out = []
    for r in (doc.get("custom_items") or []):
        if r.get("document_type") != "Expense Note" or not r.get("document_no"):
            continue
        en = frappe.db.get_value(
            "Expense Note", r.document_no,
            ["currency", "conversion_rate", "vendor", "journal_entry"], as_dict=True,
        )
        if not en or (en.currency or company_cur) == company_cur:
            continue  # EN IDR -> jalur lama (reference JE), bukan mode valas
        out.append(frappe._dict(
            row=r, en=r.document_no, vendor=en.vendor, currency=en.currency,
            book_rate=flt(en.conversion_rate) or 1.0,
            payable=_en_payable_account(doc.company, en.vendor, en.journal_entry),
            je=en.journal_entry, alloc=flt(r.amount),
        ))
    return out


def _valas_en_pay_rate(doc, ctx):
    """Kurs bayar = exchange rate NATIVE sisi bank (source_exchange_rate) = IDR per 1 unit
    mata uang bank. Fallback ke kurs buku EN pertama kalau belum diisi (selisih kurs 0)."""
    return flt(doc.get("source_exchange_rate")) or (ctx[0].book_rate if ctx else 1.0)


def _valas_en_alloc_total(ctx):
    """Total alokasi dalam mata uang EN/bank (mis. USD)."""
    return flt(sum(c.alloc for c in ctx), 2)


def _valas_component_accounts(company):
    """Akun GL untuk komponen nominal (di luar tabel): tax(PPN), pph, materai, admin bank."""
    s = frappe.get_cached_doc("ERPNext Custom Setting")
    admin = frappe.db.get_value(
        "Account", {"account_number": "6210.001", "company": company}, "name"
    ) or s.get("adjustment_account")
    return {"tax": s.get("tax_account"), "materai": s.get("materai_account"),
            "pph": s.get("pph_account"), "admin": admin}


def _valas_components(doc):
    """Nominal komponen dalam MATA UANG PEMBAYARAN (mis. USD), + arah ke paid_amount:
    Tax, Materai, Admin menambah (dibayar lebih); PPh mengurangi (dipotong). Plus Credit/
    Debit Note per baris item (Credit menambah, Debit mengurangi)."""
    tax = flt(doc.get("custom_tax_amount"))
    materai = flt(doc.get("custom_materai_amount"))
    admin = flt(doc.get("custom_admin_fee"))
    pph = flt(doc.get("custom_pph_amount"))
    cn = sum(flt(r.credit_amount) for r in (doc.get("custom_items") or []) if r.get("document_no"))
    dn = sum(flt(r.debit_amount) for r in (doc.get("custom_items") or []) if r.get("document_no"))
    net = tax + materai + admin - pph + cn - dn  # tambahan (+) / potongan (−) ke paid_amount
    return frappe._dict(tax=tax, materai=materai, admin=admin, pph=pph, cn=flt(cn), dn=flt(dn),
                        net=flt(net, 2))


def expense_note_paid_amount(en, exclude_pe=None):
    """Berapa (dalam mata uang EN) sudah dialokasi untuk EN ini, dari Payment Entry yang
    menariknya (baris custom_items). Dipakai menghitung sisa EN untuk dialog Add Items.

    Termasuk PE DRAFT (docstatus 0), bukan hanya submitted: begitu EN dialokasi penuh di
    sebuah PE (walau belum disubmit), sisanya jadi 0 -> tak bisa ditarik lagi di PE lain.
    Cancelled (docstatus 2) TIDAK dihitung; batalkan/hapus PE untuk membebaskan EN-nya."""
    conds = ("pe.docstatus in (0, 1) and it.document_type = 'Expense Note' "
             "and it.document_no = %(en)s")
    vals = {"en": en}
    if exclude_pe:
        conds += " and pe.name != %(ex)s"
        vals["ex"] = exclude_pe
    total = frappe.db.sql(
        f"""select sum(it.amount) from `tabPayment Entry Items` it
            join `tabPayment Entry` pe on pe.name = it.parent
            where {conds}""",
        vals,
    )
    return flt(total[0][0]) if total and total[0][0] else 0.0


def _derive_references(doc):
    """Turunkan baris References dari grid gabungan custom_items (tabel = sumber kebenaran):

    - baris Expense Note   -> reference JOURNAL ENTRY (JE yang dibuat EN saat Validate),
      ditandai custom_expense_note (dipakai update_expense_note_paid_status).
    - baris invoice (Purchase/Sales Invoice, termasuk Debit/Credit Note) -> reference
      dokumen itu sendiri, ditandai custom_from_transaction.
    Allocated = kolom "Dibayar" (default = sisa; untuk Debit/Credit Note nilainya NEGATIF).
    References manual (tanpa tanda) dibiarkan. paid_amount diisi = total alokasi bila kosong.

    custom_expense_notes = tabel LAMA (sebelum tombol Add Items disatukan). Fieldnya sudah
    hidden, tapi tetap diturunkan supaya dokumen lama yang masih draft tak berubah artinya.
    """
    en_rows = doc.get("custom_expense_notes") or []
    # Baris EN VALAS diposting jalur GL sendiri (mode valas) — JANGAN dijadikan reference JE
    # (kalau dijadikan, hutangnya dobel diposting). Sisanya (invoice, EN IDR) tetap seperti biasa.
    _valas_ens = {c.en for c in _valas_en_ctx(doc)}
    # Grid gabungan: baris tarikan = yang punya document_no (baris direct tidak punya).
    txn_rows = [
        r for r in (doc.get("custom_items") or [])
        if r.get("document_no") and r.get("document_no") not in _valas_ens
    ]
    has_derived = any(
        (r.get("custom_expense_note") or r.get("custom_from_transaction"))
        for r in (doc.get("references") or [])
    )
    if not en_rows and not txn_rows and not has_derived:
        return  # tak ada tabel tarikan di dokumen ini

    # Pertahankan References manual, buang yang turunan tabel lalu bangun ulang.
    manual_refs = [
        r for r in (doc.get("references") or [])
        if not (r.get("custom_expense_note") or r.get("custom_from_transaction"))
    ]
    doc.set("references", manual_refs)

    total_alloc = 0.0
    for r in en_rows:  # tabel lama (hidden) — hanya untuk dokumen lama
        if not r.expense_note:
            continue
        r.journal_entry = r.journal_entry or _expense_note_journal(r.expense_note)
        alloc = flt(r.allocated) if flt(r.allocated) else flt(r.outstanding)
        r.allocated = alloc
        total_alloc += alloc
        doc.append("references", {
            "reference_doctype": "Journal Entry",
            "reference_name": r.journal_entry,
            "allocated_amount": alloc,
            "custom_expense_note": r.expense_note,
        })

    for r in txn_rows:
        # Debit/Credit Note: outstanding NEGATIF -> alokasi negatif (pengurang). Karena itu
        # cek `if flt(...)`, BUKAN `> 0` — pakai > 0 baris retur akan ditimpa jadi 0.
        # Kolom nominal grid gabungan = `amount` ("Dibayar").
        alloc = flt(r.amount) if flt(r.amount) else flt(r.outstanding)
        r.amount = alloc
        total_alloc += alloc
        if r.document_type == "Expense Note":
            # Hutangnya ada di Journal Entry EN, bukan di dokumen EN itu sendiri.
            r.journal_entry = r.journal_entry or _expense_note_journal(r.document_no)
            doc.append("references", {
                "reference_doctype": "Journal Entry",
                "reference_name": r.journal_entry,
                "allocated_amount": alloc,
                "custom_expense_note": r.document_no,
                "custom_from_transaction": 1,
            })
            continue
        doc.append("references", {
            "reference_doctype": r.document_type,
            "reference_name": r.document_no,
            "total_amount": flt(r.grand_total),
            "outstanding_amount": flt(r.outstanding),
            "allocated_amount": alloc,
            "custom_from_transaction": 1,
        })

    _sync_party_account(doc)

    # Bila user belum mengisi paid_amount, set = total alokasi (uang yang keluar dari bank).
    if total_alloc > 0 and flt(doc.paid_amount) <= 0:
        doc.paid_amount = total_alloc
        if flt(doc.source_exchange_rate or 0) in (0, 1) and flt(doc.target_exchange_rate or 0) in (0, 1):
            doc.received_amount = total_alloc


def _ref_party_account(doc, ref):
    """Akun piutang/hutang yang dipakai satu baris References."""
    if ref.reference_doctype == "Journal Entry":  # baris Expense Note
        return frappe.db.get_value(
            "Journal Entry Account",
            {"parent": ref.reference_name, "party_type": doc.party_type, "party": doc.party},
            "account",
        )
    if ref.reference_doctype == "Sales Invoice":
        return frappe.db.get_value("Sales Invoice", ref.reference_name, "debit_to")
    if ref.reference_doctype == "Purchase Invoice":
        return frappe.db.get_value("Purchase Invoice", ref.reference_name, "credit_to")
    return None


def _sync_party_account(doc):
    """Sisi party (Receive: paid_from, Pay: paid_to) = akun piutang/hutang dokumen yang ditarik.

    ERPNext MEWAJIBKAN akun ini sama persis dengan akun di dokumen referensi ("{0} {1} is
    associated with {2}, but Party Account is {3}"), sedangkan akun default party belum tentu
    yang dipakai invoice-nya. Karena field akun sekarang read-only, di sinilah nilainya diisi.
    Dokumen dengan akun berbeda tidak bisa dibayar sekaligus — itu batasan ERPNext, bukan kita.
    """
    field = "paid_from" if doc.payment_type == "Receive" else "paid_to"
    accounts, docs_by_account = [], {}
    for r in doc.get("references") or []:
        acc = _ref_party_account(doc, r)
        if acc and acc not in accounts:
            accounts.append(acc)
            docs_by_account[acc] = r.get("custom_expense_note") or r.reference_name
    if not accounts:
        return
    if len(accounts) > 1:
        frappe.throw(_(
            "Dokumen yang ditarik memakai akun {0} berbeda: {1}. ERPNext hanya bisa membayar "
            "dokumen dengan akun yang sama dalam satu Payment Entry — pisahkan jadi beberapa "
            "Payment Entry."
        ).format(
            _("piutang") if doc.payment_type == "Receive" else _("hutang"),
            ", ".join(f"<b>{a}</b> ({docs_by_account[a]})" for a in accounts),
        ))
    doc.set(field, accounts[0])


def update_expense_note_paid_status(doc, method=None):
	"""Setelah Payment Entry submit/cancel: set flag `paid` di tiap Expense Note yang
	ditarik (references ber-custom_expense_note). Paid = sisa hutang JE-nya <= 0,
	dihitung dengan helper ERPNext yang sama dipakai saat menarik EN."""
	ens = {r.get("custom_expense_note") for r in (doc.get("references") or []) if r.get("custom_expense_note")}
	if not ens:
		return
	get_outstanding_on_journal_entry = frappe.get_attr(
		"erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_on_journal_entry"
	)
	for en in ens:
		if not frappe.db.exists("Expense Note", en):
			continue
		je, vendor, validated = frappe.db.get_value(
			"Expense Note", en, ["journal_entry", "vendor", "validated"]
		)
		paid = 0
		status = ""
		if je and validated:
			outstanding, total = get_outstanding_on_journal_entry(je, "Supplier", vendor)
			# outstanding None = JE-nya TIDAK punya baris hutang ber-party (mis. EN reimburse
			# yang sisi kreditnya ke akun Aset "Reimbursement", bukan Hutang Usaha). Tidak ada
			# yang bisa dilunasi, jadi JANGAN dianggap lunas: `flt(None)` = 0 dan itu membuat
			# EN semacam ini terbaca Paid padahal belum pernah dibayar (terjadi pada 8 EN
			# EN/IMP/OGM/2026/*, ketemu saat semua Payment Entry dikembalikan ke draft).
			if outstanding is None:
				frappe.db.set_value("Expense Note", en, {"paid": 0, "paid_date": None,
				                                         "payment_status": "Unpaid"}, update_modified=False)
				continue
			paid = 1 if flt(outstanding) <= 0.005 else 0
			# Tiga keadaan, bukan dua: EN yang ditarik SEBAGIAN dulu terbaca "belum bayar"
			# sama seperti yang belum disentuh sama sekali. `paid` (checkbox) dipertahankan
			# apa adanya karena dipakai indeks per BL di Shipping List.
			if paid:
				status = "Paid"
			elif flt(outstanding) < flt(total) - 0.005:
				status = "Partial"
			else:
				status = "Unpaid"
		payload = {"paid": paid, "paid_date": frappe.utils.now() if paid else None}
		if frappe.get_meta("Expense Note").has_field("payment_status"):
			payload["payment_status"] = status
		frappe.db.set_value("Expense Note", en, payload, update_modified=False)


def payment_entries_of(reference_doctype, reference_name, field="reference_name"):
	"""Payment Entry yang menarik dokumen ini — DRAFT ikut dihitung.

	Draft pun sudah mengklaim dokumennya (barisnya ada di PV dan sisa tagihannya sudah
	berkurang di dialog tarikan), jadi kolom Payment harus menunjukkannya; kalau hanya yang
	submitted, dokumen yang pembayarannya sedang diproses terlihat seolah belum tersentuh."""
	filters = {field: reference_name, "parenttype": "Payment Entry", "docstatus": ["<", 2]}
	if field == "reference_name":
		filters["reference_doctype"] = reference_doctype
	return sorted(
		set(frappe.get_all("Payment Entry Reference", filters=filters, pluck="parent"))
	)


def sync_payment_links(doc, method=None):
	"""Kolom Payment di list Sales Invoice & Expense Note — jalan sejak PV masih DRAFT.

	Baris yang SEBELUMNYA ada ikut disinkron supaya dokumen yang barusan dilepas dari PV ini
	kolomnya ikut bersih. Kegagalan di sini tidak boleh menjatuhkan simpan/submit PV:
	ini kolom informasi, bukan angka pembukuan."""
	rows = list(doc.get("references") or [])
	before = doc.get_doc_before_save() if not doc.is_new() else None
	if before:
		rows += list(before.get("references") or [])

	invoices = {
		r.get("reference_name")
		for r in rows
		if r.get("reference_doctype") == "Sales Invoice" and r.get("reference_name")
	}
	expense_notes = {r.get("custom_expense_note") for r in rows if r.get("custom_expense_note")}

	try:
		for si in invoices:
			if frappe.db.exists("Sales Invoice", si):
				frappe.db.set_value(
					"Sales Invoice",
					si,
					"custom_payment_no",
					", ".join(payment_entries_of("Sales Invoice", si)) or None,
					update_modified=False,
				)
		if expense_notes:
			from erp.expedition.doctype.expense_note.expense_note import sync_document_links

			sync_document_links(expense_notes)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "sync_payment_links Payment Entry")


def _full_names(users):
    """{user: full_name} dalam SATU query — bukan per baris (bisa ribuan baris)."""
    users = {u for u in users if u}
    if not users:
        return {}
    rows = frappe.get_all(
        "User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"],
        ignore_permissions=True,
    )
    return {r.name: (r.full_name or r.name) for r in rows}


def _party_accounts(party_type, party, company):
    """SEMUA akun piutang/hutang yang benar-benar dipakai party ini (dari Payment Ledger),
    bukan cuma akun default-nya.

    Kenapa: get_outstanding_reference_documents memfilter `ple.account IN (party_account)`.
    Kalau invoice di-book ke akun non-default (mis. "Piutang Lain-lain", bukan "Piutang Dagang"),
    memakai akun default saja membuat invoice itu TAK PERNAH muncul. Jadi kita sapu semua akun
    yang dipakai, lalu tanya mesin ERPNext sekali per akun.
    """
    from erpnext.accounts.party import get_party_account

    accounts = []
    default = get_party_account(party_type, party, company)
    if default:
        accounts.append(default)
    for acc in frappe.get_all(
        "Payment Ledger Entry",
        filters={"party_type": party_type, "party": party, "company": company, "delinked": 0},
        distinct=True, pluck="account",
    ):
        if acc and acc not in accounts:
            accounts.append(acc)
    return accounts


def _invoice_outstanding(party_type, party, company, payment_type):
    """Invoice outstanding milik party, dari mesin ERPNext (get_outstanding_reference_documents)
    — sumber yang SAMA dipakai dialog native Get Outstanding Invoices, jadi tak akan beda.

      Pay     -> Supplier: Purchase Invoice + returnya (is_return=1) = DEBIT NOTE
      Receive -> Customer: Sales Invoice    + returnya (is_return=1) = CREDIT NOTE

    Baris return SENGAJA ikut walau outstanding-nya NEGATIF: itu memang pengurang tagihan
    (dialog native pun mengalokasikannya negatif).
    """
    get_docs = frappe.get_attr(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_reference_documents"
    )
    want = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"

    docs, seen = [], set()
    for account in _party_accounts(party_type, party, company):
        args = {
            "posting_date": frappe.utils.nowdate(),
            "company": company,
            "party_type": party_type,
            "party": party,
            "party_account": account,
            "payment_type": payment_type,
            "get_outstanding_invoices": 1,
        }
        for d in get_docs(args) or []:
            no = d.get("voucher_no")
            if d.get("voucher_type") != want or no in seen or not flt(d.get("outstanding_amount")):
                continue
            seen.add(no)
            docs.append(d)
    if not docs:
        return []

    # Return (is_return=1) -> Debit Note (PI) / Credit Note (SI). Sekalian ambil owner.
    names = [d.get("voucher_no") for d in docs]
    meta = {
        r.name: r for r in frappe.get_all(
            want, filters={"name": ["in", names]}, fields=["name", "is_return", "owner"],
            ignore_permissions=True,
        )
    }
    return_label = "Debit Note" if want == "Purchase Invoice" else "Credit Note"
    names_by_user = _full_names(m.owner for m in meta.values())

    out = []
    for d in docs:
        name = d.get("voucher_no")
        m = meta.get(name) or {}
        out.append({
            "reference_doctype": want,
            "doc_label": return_label if m.get("is_return") else want,
            "transaction": name,
            "journal_entry": None,
            "date": str(d.get("posting_date") or ""),
            "owner": m.get("owner"),
            "owner_name": names_by_user.get(m.get("owner"), m.get("owner") or ""),
            "grand_total": flt(d.get("invoice_amount")),
            "outstanding": flt(d.get("outstanding_amount")),
        })
    return out


def _all_payment_items(party_type, party, company, payment_type):
    """Daftar LENGKAP dokumen yang bisa ditarik:

      Pay     -> Supplier: Expense Note (Validated) + Purchase Invoice + Debit Note
      Receive -> Customer: Sales Invoice + Credit Note

    Semua sudah submit/validate; angka outstanding dari mesin ERPNext.

    Di-CACHE 2 menit per (party, company, payment_type). Alasannya: menghitung outstanding
    itu mahal (satu query berat per akun party), sedangkan dialog Add Items memanggil ulang
    tiap ketik pencarian / pindah halaman. Tanpa cache, supplier dengan ribuan transaksi akan
    membuat setiap ketikan menghitung ulang semuanya.
    """
    key = f"cmi_payment_items:{payment_type}:{party_type}:{party}:{company}"
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    rows = []
    if payment_type == "Pay" and party_type == "Supplier":
        rows += get_expense_note_outstanding(party, company)
    rows += _invoice_outstanding(party_type, party, company, payment_type)
    frappe.cache().set_value(key, rows, expires_in_sec=120)
    return rows


@frappe.whitelist()
def get_payment_items(
    party_type, party, company, payment_type,
    search=None, exclude=None, start=0, page_length=20, refresh=0,
):
    """Satu HALAMAN dokumen untuk dialog "Add Items" — pencarian & paging di SERVER.

    Party dengan ribuan transaksi tidak boleh dikirim sekaligus ke browser (render-nya berat).
    Jadi: hitung daftar penuh (cached), saring `search` + `exclude` (yang sudah ada di tabel),
    lalu potong satu halaman. Kembali: {rows, total, start, page_length}.
    """
    if not (party_type and party):
        return {"rows": [], "total": 0, "start": 0, "page_length": 0}

    start = int(start or 0)
    page_length = max(1, int(page_length or 20))
    if int(refresh or 0):
        frappe.cache().delete_value(
            f"cmi_payment_items:{payment_type}:{party_type}:{party}:{company}"
        )

    rows = _all_payment_items(party_type, party, company, payment_type)

    taken = set(frappe.parse_json(exclude) if isinstance(exclude, str) else (exclude or []))
    if taken:
        rows = [r for r in rows if r["transaction"] not in taken]

    term = (search or "").strip().lower()
    if term:
        rows = [
            r for r in rows
            if term in (r["transaction"] or "").lower()
            or term in (r["doc_label"] or "").lower()
            or term in (r.get("owner_name") or "").lower()
        ]

    total = len(rows)
    if start >= total:
        start = max(0, (total - 1) // page_length * page_length) if total else 0
    return {
        "rows": rows[start:start + page_length],
        "total": total,
        "start": start,
        "page_length": page_length,
    }


def _pending_cash_used(names, exclude_parent=None):
    """{pending cash: nominal yang SUDAH dipakai di Payment Entry lain}.

    Pending Cash belum punya ledger sendiri (barisnya belum diposting ke GL), jadi "sisa"
    dihitung dari tabel Pending Cash di Payment Entry itu sendiri — SATU query untuk semua
    nama sekaligus, bukan per baris.

    Yang dihitung: baris di PE draft MAUPUN tervalidasi (docstatus < 2). Draft ikut karena
    kalau tidak, satu Pending Cash bisa ditarik ke dua draft sekaligus lalu dua-duanya
    divalidasi — uang muka yang sama terpakai dua kali tanpa ada yang menyadari. PE yang
    di-void (docstatus 2) melepas kembali jatahnya.

    exclude_parent = Payment Entry yang sedang dibuka: barisnya ada di layar dan bisa saja
    belum tersimpan, jadi tabel di form-lah yang jadi acuan — bukan versi DB-nya.
    """
    if not names:
        return {}
    filters = {
        "parenttype": "Payment Entry",
        "parentfield": "custom_pending_items",
        "reference_doctype": "Pending Cash",
        "transaction": ["in", list(names)],
        "docstatus": ["<", 2],
    }
    if exclude_parent:
        filters["parent"] = ["!=", exclude_parent]

    used = {}
    for r in frappe.get_all(
        "Payment Entry Transaction",
        parent_doctype="Payment Entry",  # wajib untuk query tabel anak
        filters=filters,
        fields=["transaction", "allocated"],
        ignore_permissions=True,
    ):
        used[r.transaction] = used.get(r.transaction, 0.0) + flt(r.allocated)
    return used


@frappe.whitelist()
def get_pending_cash_items(
    supplier=None, company=None, search=None, exclude=None, exclude_parent=None,
    start=0, page_length=20,
):
    """Satu HALAMAN Pending Cash outstanding milik `supplier`, untuk dialog "Add Pending Cash".

    Dua saringan yang menentukan:
      1. PAID saja (dan belum Void). Pending Cash baru menjadi pengeluaran uang saat Paid —
         di situlah jurnalnya terbentuk (Dr uang muka / Cr bank). Yang masih Draft/Validated
         belum ada uang keluar, jadi tidak ada yang bisa ditarik.
      2. Masih bersisa: total dikurangi yang sudah dipakai di Payment Entry lain
         (_pending_cash_used). Yang sudah habis tidak muncul.

    Supplier WAJIB: tanpa itu daftarnya se-company dan sisanya harus dihitung untuk semua
    dokumen sekaligus — mahal, padahal satu Payment Entry hanya membayar satu supplier.

    Sisa dihitung untuk SELURUH kandidat supplier ini dulu, baru disaring `search` dan
    dipotong satu halaman — kalau tidak, dokumen yang sudah habis akan membuat halaman bolong
    dan totalnya salah.
    """
    start = int(start or 0)
    page_length = max(1, int(page_length or 20))
    empty = {"rows": [], "total": 0, "start": 0, "page_length": page_length}
    if not supplier:
        return empty

    filters = {"paid": 1, "void": 0, "pay_to": supplier}
    if company:
        filters["company"] = company
    taken = frappe.parse_json(exclude) if isinstance(exclude, str) else (exclude or [])
    if taken:
        filters["name"] = ["not in", list(taken)]

    cands = frappe.get_all(
        "Pending Cash",
        filters=filters,
        fields=["name", "pay_to", "date", "paid_date", "total", "currency", "owner"],
        order_by="paid_date desc, name desc",
        limit_page_length=0,
    )
    if not cands:
        return empty

    used = _pending_cash_used([c.name for c in cands], exclude_parent)
    names_by_user = _full_names(c.owner for c in cands)

    rows = []
    for c in cands:
        outstanding = flt(c.total) - flt(used.get(c.name))
        if outstanding <= 0.005:  # sudah habis dipakai di Payment Entry lain
            continue
        rows.append({
            "reference_doctype": "Pending Cash",
            "doc_label": "Pending Cash",
            "transaction": c.name,
            "pay_to": c.pay_to,
            "date": str(c.paid_date or c.date or ""),
            "owner": c.owner,
            "owner_name": names_by_user.get(c.owner, c.owner or ""),
            "grand_total": flt(c.total),
            "outstanding": outstanding,
            "currency": c.currency,
        })

    # Pencarian mengikuti apa yang TAMPAK di tabel (nomor & owner) — bukan field tersembunyi,
    # supaya hasilnya tidak terasa acak bagi user.
    term = (search or "").strip().lower()
    if term:
        rows = [
            r for r in rows
            if term in (r["transaction"] or "").lower()
            or term in (r["owner_name"] or "").lower()
        ]

    total = len(rows)
    if start >= total:
        start = max(0, (total - 1) // page_length * page_length) if total else 0
    return {
        "rows": rows[start:start + page_length],
        "total": total,
        "start": start,
        "page_length": page_length,
    }


@frappe.whitelist()
def get_expense_note_outstanding(supplier, company=None):
    """Expense Note (Validated, belum Void) milik `supplier` yang masih punya sisa hutang.
    Untuk dialog "Tarik Expense Note".

    - EN mata uang company (IDR): sisa dibaca dari outstanding Journal Entry (jalur lama).
    - EN VALAS (mata uang != company): sisa dibaca LANGSUNG dari EN dalam mata uangnya
      (net_total - yang sudah dibayar di PE lain). `book_rate` disertakan supaya dialog bisa
      mengisi Kurs Bayar otomatis."""
    get_outstanding_on_journal_entry = frappe.get_attr(
        "erpnext.accounts.doctype.payment_entry.payment_entry.get_outstanding_on_journal_entry"
    )

    if not supplier:
        return []

    filters = {"vendor": supplier, "validated": 1, "void": 0}
    if company:
        filters["company"] = company

    ens = frappe.get_all(
        "Expense Note",
        filters=filters,
        fields=["name", "journal_entry", "net_total", "date", "currency", "owner",
                "conversion_rate", "company"],
        order_by="date asc, name asc",
    )

    names_by_user = _full_names(en.owner for en in ens)
    company_cur_cache = {}

    def company_cur(comp):
        if comp not in company_cur_cache:
            company_cur_cache[comp] = frappe.get_cached_value("Company", comp, "default_currency")
        return company_cur_cache[comp]

    out = []
    for en in ens:
        if not en.journal_entry:
            continue  # gerbang #4: EN harus sudah validate (JE ada)
        is_valas = (en.currency or company_cur(en.company)) != company_cur(en.company)
        if is_valas:
            # Sisa dalam mata uang EN, dibaca langsung dari EN (bukan outstanding JE yang IDR).
            outstanding = flt(en.net_total) - expense_note_paid_amount(en.name)
        else:
            outstanding, _total = get_outstanding_on_journal_entry(
                en.journal_entry, "Supplier", supplier
            )
        if flt(outstanding) <= 0.005:  # gerbang #3: masih ada sisa
            continue
        out.append({
            # Bentuk baris SERAGAM dengan _invoice_outstanding (satu tabel custom_transactions).
            "reference_doctype": "Expense Note",
            "doc_label": "Expense Note",
            "transaction": en.name,
            "journal_entry": en.journal_entry,
            "date": str(en.date) if en.date else "",
            "owner": en.owner,
            "owner_name": names_by_user.get(en.owner, en.owner or ""),
            "grand_total": flt(en.net_total),
            "outstanding": flt(outstanding),
            "currency": en.currency,
            "book_rate": flt(en.conversion_rate) or 1.0,
        })
    return out

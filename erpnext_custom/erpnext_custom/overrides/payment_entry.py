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
from frappe.utils import getdate, today
from frappe.utils.data import flt

from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

# Bulan romawi untuk penomoran (PV/MDR/CMI/2026/VII/0001).
_ROMAN_MONTHS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
                 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII"}


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
		# Satu mata uang company; sisi party kosong membuat kurs target tidak terisi.
		doc.source_exchange_rate = doc.source_exchange_rate or 1
		doc.target_exchange_rate = doc.target_exchange_rate or 1
		# Skema PE mewajibkan paid_from & paid_to terisi. Sisi party tidak dipakai
		# GL pada mode direct (add_party_gl_entries kita yang jalan) — isi placeholder
		# = akun bank supaya lolos mandatory tanpa efek jurnal.
		company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
		if doc.payment_type == "Pay":
			doc.paid_to = doc.paid_to or doc.paid_from
		else:
			doc.paid_from = doc.paid_from or doc.paid_to
		doc.paid_from_account_currency = doc.paid_from_account_currency or company_currency
		doc.paid_to_account_currency = doc.paid_to_account_currency or company_currency


class CMIPaymentEntry(PaymentEntry):
	"""Override controller core Payment Entry tanpa mengedit erpnext."""

	def autoname(self):
		"""Isi komponen penomoran lalu SERAHKAN penamaan ke NAMING SERIES.

		Pola nomor tidak di-hardcode di sini — hidup di naming series Payment Entry
		(install.PE_NAMING_SERIES) sehingga bisa diedit user lewat Document Naming
		Settings. Contoh hasil: PV/MDR/CMI/2026/VII/0001. Pay=PV, Receive=RV.
		Tahun & bulan romawi diambil dari POSTING DATE (bukan hari ini); karena
		keduanya bagian prefix, counter reset otomatis tiap bulan/tahun. Dokumen
		amend tidak lewat sini (Frappe menamai NAMA-1 lebih dulu).
		"""
		from erpnext_custom.overrides.sales_invoice import _company_code

		# Pastikan sisi bank terisi sebelum kode bank diambil (autoname jalan lebih
		# dulu dari before_validate). Idempoten — aman dipanggil dua kali.
		_apply_direct_and_settlement(self)
		_fill_bank_side(self)

		d = getdate(self.posting_date or today())
		self.custom_no_code = {"Pay": "PV", "Receive": "RV"}.get(self.payment_type, "PE")
		self.custom_bank_code = _bank_code(self)
		self.custom_company_code = _company_code(self.company)
		self.custom_year = str(d.year)
		self.custom_month_roman = _ROMAN_MONTHS[d.month]

		# JANGAN set self.name — biarkan Frappe memakai naming series (pola editable).
		if not self.naming_series:
			opts = (frappe.get_meta("Payment Entry").get_field("naming_series").options or "").strip()
			self.naming_series = opts.splitlines()[0] if opts else None

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
		super().set_difference_amount()

	def make_gl_entries(self, *args, **kwargs):
		# Dont Post To GL: submit tanpa jurnal (dokumen catatan). Konsekuensi: outstanding
		# dokumen referensi TIDAK berkurang (tidak ada Payment Ledger Entry).
		if self.get("custom_dont_post_to_gl"):
			return
		return super().make_gl_entries(*args, **kwargs)

	def get_gl_dict(self, args, account_currency=None, item=None):
		from erpnext_custom.overrides import fill_cost_center

		return fill_cost_center(self, super().get_gl_dict(args, account_currency, item), item)

	def build_gl_map(self):
		"""Jurnal bawaan + baris penyesuaian per baris tarikan (Dr/Cr di tabel Payment Item).

		Disisipkan di build_gl_map (BUKAN di add_*_gl_entries): di sinilah ERPNext merakit
		daftar GL-nya lalu menyerahkannya ke process_gl_map, jadi baris kita ikut diproses
		sama persis tanpa perlu menyentuh logika Dr Hutang / Cr Bank yang sudah jalan.
		"""
		gl_entries = super().build_gl_map()
		self._add_item_adjustment_gl_entries(gl_entries)
		return gl_entries

	def _add_item_adjustment_gl_entries(self, gl_entries):
		"""Tiap baris tarikan ber-Dr/Cr menambah SEPASANG baris GL yang seimbang sendiri.

		Nominalnya sudah dijamin Dr == Cr oleh _apply_items_adjustment, jadi total voucher
		tetap seimbang tanpa mengubah paid_amount / difference_amount. `allocation_date`
		SENGAJA tidak dipakai sebagai posting_date: satu voucher dengan beberapa tanggal
		posting membuat tutup buku & rekonsiliasi tidak konsisten — tanggalnya catatan baris.
		"""
		rate = flt(self.source_exchange_rate) or 1.0
		for r in self.get("custom_items") or []:
			if not r.get("document_no"):
				continue
			amt = flt(r.debit_amount)
			if not (amt and r.get("debit_account") and r.get("credit_account")):
				continue
			# Catatan baris: Note Debit / Note Credit per sisi, mundur ke Remark baris.
			fallback = r.get("remark") or r.get("note") or r.get("description")
			for account, cost_center, note, side in (
				(r.debit_account, r.debit_cost_center, r.get("note_debit"), "debit"),
				(r.credit_account, r.credit_cost_center, r.get("note_credit"), "credit"),
			):
				row = {
					"account": account,
					"against": r.credit_account if side == "debit" else r.debit_account,
					"cost_center": cost_center or self.cost_center,
					"account_currency": frappe.get_cached_value(
						"Account", account, "account_currency"),
					"remarks": " - ".join(x for x in (
						_("Penyesuaian"), r.document_no, note or fallback) if x),
					side: amt * rate,
					side + "_in_account_currency": amt,
				}
				gl_entries.append(self.get_gl_dict(row, item=r))

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
				["account", "party_type", "party"], as_dict=True,
			)
			if not side:
				frappe.throw(_(
					"Journal Entry <b>{0}</b> milik Pending Cash <b>{1}</b> tidak punya baris "
					"debit uang muka."
				).format(je, r.transaction))
			out.append((side.account, side.party_type, side.party, amount))
		return out

	def add_bank_gl_entries(self, gl_entries):
		funding = self._pending_cash_funding() if self.payment_type == "Pay" else []
		if not funding:
			return super().add_bank_gl_entries(gl_entries)

		rate = flt(self.source_exchange_rate) or 1.0
		for account, party_type, party, amount in funding:
			gl_entries.append(self.get_gl_dict({
				"account": account,
				"party_type": party_type,
				"party": party,
				"against": self.party or self.paid_to,
				"account_currency": frappe.get_cached_value("Account", account, "account_currency"),
				"credit_in_account_currency": amount,
				"credit": amount * rate,
				"cost_center": self.cost_center,
				"post_net_value": True,
			}, item=self))

		# Kelebihan di luar uang muka tetap keluar dari bank (mis. uang muka 2jt dipakai
		# membayar tagihan 3jt -> 1jt sisanya dari bank).
		from_bank = flt(self.paid_amount) - sum(f[3] for f in funding)
		if from_bank > 0.005:
			gl_entries.append(self.get_gl_dict({
				"account": self.paid_from,
				"account_currency": self.paid_from_account_currency,
				"against": self.party or self.paid_to,
				"credit_in_account_currency": from_bank,
				"credit": from_bank * rate,
				"cost_center": self.cost_center,
				"post_net_value": True,
			}, item=self))

	def _pending_cash_against(self, gl_entries, start):
		"""Kolom "against" sisi party dibuat core = akun bank; padahal lawannya kini akun
		uang muka. Dibetulkan supaya laporan tidak menyebut bank yang tak dipakai."""
		funding = self._pending_cash_funding() if self.payment_type == "Pay" else []
		if not funding:
			return
		accounts = list(dict.fromkeys(f[0] for f in funding))
		if flt(self.paid_amount) - sum(f[3] for f in funding) > 0.005:
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


def _apply_items_adjustment(doc):
    """Penyesuaian per baris tarikan: pasangan Dr/Cr yang jadi baris jurnal TAMBAHAN.

    Dipakai untuk menambah/mengurangi sesuatu yang menempel pada satu dokumen tarikan
    (mis. potongan, biaya bank, selisih) tanpa mengubah jurnal pembayarannya sendiri —
    Dr Hutang / Cr Bank tetap apa adanya, pasangan ini MENAMBAH baris (lihat
    CMIPaymentEntry._add_item_adjustment_gl_entries).

    Karena jurnal bawaan tidak diutak-atik, pasangan ini WAJIB seimbang sendiri: kalau
    Dr != Cr, seluruh voucher jadi timpang dan ERPNext menolaknya di ujung dengan pesan
    yang tidak menyebut baris mana yang salah. Karena itu dicegat di sini, per baris,
    dengan nomor dokumennya.

    Hanya untuk baris MODE TARIKAN (punya document_no). Baris Expense/Income memakai
    Account + Amount-nya sendiri.
    """
    default_cc = None
    for r in doc.get("custom_items") or []:
        if not r.get("document_no"):
            continue
        # Default Allocation Date = tanggal dokumen yang ditarik (bukan posting date PE).
        r.allocation_date = r.allocation_date or r.get("date") or doc.posting_date
        dr, cr = flt(r.debit_amount), flt(r.credit_amount)
        if not (r.get("debit_account") or r.get("credit_account") or dr or cr):
            continue  # baris tanpa penyesuaian — normal, mayoritas begini
        if not (r.get("debit_account") and r.get("credit_account")):
            frappe.throw(_(
                "Baris <b>{0}</b>: penyesuaian butuh <b>Debit Account</b> DAN "
                "<b>Credit Account</b> terisi dua-duanya."
            ).format(r.document_no))
        if dr <= 0 or cr <= 0:
            frappe.throw(_(
                "Baris <b>{0}</b>: Debit Note & Credit Note harus lebih dari 0."
            ).format(r.document_no))
        if abs(dr - cr) > 0.005:
            frappe.throw(_(
                "Baris <b>{0}</b>: Debit Note ({1}) harus SAMA dengan Credit Note ({2}) — "
                "penyesuaian ini baris jurnal tambahan, jadi harus seimbang sendiri."
            ).format(r.document_no, frappe.format_value(dr, "Currency"),
                     frappe.format_value(cr, "Currency")))
        if default_cc is None:
            default_cc = _default_cost_center(doc)
        r.debit_cost_center = r.debit_cost_center or default_cc
        r.credit_cost_center = r.credit_cost_center or default_cc


def before_validate(doc, method=None):
    _apply_direct_and_settlement(doc)
    _fill_bank_side(doc)  # sisi bank auto (Mode of Payment / default Company)
    _apply_pe_smart_inputs(doc)
    _apply_remark(doc)
    _derive_references(doc)
    _apply_items_adjustment(doc)
    _apply_pending_cash(doc)  # setelah _derive_references: butuh paid_amount yang final
    _apply_reference_summary(doc)  # paling akhir: baca references yang sudah final


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
        return

    rows = [r for r in (doc.get("custom_pending_items") or []) if r.get("transaction")]
    if not rows:
        return

    names = [r.transaction for r in rows]
    totals = {
        r.name: flt(r.total)
        for r in frappe.get_all("Pending Cash", filters={"name": ["in", names]},
                                fields=["name", "total"])
    }
    # Dokumen ini sendiri dikecualikan: barisnya sedang dihitung ulang di sini.
    used = _pending_cash_used(names, exclude_parent=doc.name)

    remaining = flt(doc.paid_amount)
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


def _expense_note_journal(en):
    je = frappe.db.get_value("Expense Note", en, "journal_entry")
    if not je:
        frappe.throw(
            f"Expense Note <b>{en}</b> belum punya Journal Entry (belum Validate?), tidak bisa dibayar."
        )
    return je


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
    # Grid gabungan: baris tarikan = yang punya document_no (baris direct tidak punya).
    txn_rows = [r for r in (doc.get("custom_items") or []) if r.get("document_no")]
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
		if je and validated:
			outstanding, _total = get_outstanding_on_journal_entry(je, "Supplier", vendor)
			paid = 1 if flt(outstanding) <= 0.005 else 0
		frappe.db.set_value(
			"Expense Note",
			en,
			{"paid": paid, "paid_date": frappe.utils.now() if paid else None},
			update_modified=False,
		)


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
    """Expense Note (Validated, belum Void) milik `supplier` yang Journal Entry-nya
    masih punya sisa hutang di akun payable supplier. Untuk dialog "Tarik Expense Note"."""
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
        fields=["name", "journal_entry", "net_total", "date", "currency", "owner"],
        order_by="date asc, name asc",
    )

    names_by_user = _full_names(en.owner for en in ens)

    out = []
    for en in ens:
        if not en.journal_entry:
            continue
        outstanding, total = get_outstanding_on_journal_entry(
            en.journal_entry, "Supplier", supplier
        )
        if flt(outstanding) <= 0.005:
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
        })
    return out

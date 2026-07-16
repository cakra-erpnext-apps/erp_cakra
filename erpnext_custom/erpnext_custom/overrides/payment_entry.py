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
	"""Settlement = checkbox custom_settlement (user pilih akun pengganti sisi bank).
	Mode of Payment bernama "Settlement" tetap dihormati untuk dokumen lama."""
	return bool(doc.get("custom_settlement")) or (
		(doc.get("mode_of_payment") or "").strip().lower() == "settlement"
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
			frappe.throw(_("Settlement dicentang: pilih <b>Settlement Account</b> (akun pengganti sisi Bank)."))
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

	def add_party_gl_entries(self, gl_entries):
		if not self.get("custom_direct"):
			return super().add_party_gl_entries(gl_entries)
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


def before_validate(doc, method=None):
    _apply_direct_and_settlement(doc)
    _fill_bank_side(doc)  # sisi bank auto (Mode of Payment / default Company)
    _apply_pe_smart_inputs(doc)
    _apply_remark(doc)
    _derive_references(doc)


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

"""Logika bersama AP Note (doctype APNotes) dan AR Note (doctype ARNotes).

Dua doctype, dua tabel, dua master Type — logikanya satu, dibedakan konfigurasi CFG:

  AP Note = cermin Expense Note tipe Tanpa Job: hutang ke supplier.
      Dr akun tiap baris (biaya) + Dr PPN Masukan, Cr PPh,
      Cr Hutang supplier (party Supplier) = Net Total.
  AR Note = nota debit piutang ke customer.
      Dr Piutang customer (party Customer) = Net Total, Dr PPh dipotong customer,
      Cr akun tiap baris (pendapatan) + Cr PPN Keluaran.

Flag header: Don't Post To GL = Validate tanpa jurnal; Skip Payable = jurnal ada tapi
ditolak di Payment Entry; Confidential = hanya pembuat + Accounts/System Manager.
Amount Paid in PV dihitung dari Payment Entry submitted yang mereferensikan jurnalnya.
Pelunasan lewat Payment Entry biasa: JE ber-party itu otomatis muncul di Get Outstanding
Invoices. Status manual validated/void seperti Expense Note, tanpa docstatus.
"""

from frappe.model.document import Document
from frappe.utils import flt, now_datetime

import frappe

from erpnext_custom.item_scope import item_account

# Akun komponen = field ERPNext Custom Setting. AP memakai akun yang sama dengan Expense
# Note; AR yang sama dengan Sales Invoice.
CFG = {
    "APNotes": {
        "label": "AP Note", "party": "Supplier", "prefix": "AP", "item_account": "expense_account",
        "party_side": "credit", "line_side": "debit",
        "comps": (
            ("tax_amount", "tax_account", "Akun PPN (Masukan)", "debit"),
            ("pph_amount", "pph_account", "Akun PPh", "credit"),
        ),
    },
    "ARNotes": {
        "label": "AR Note", "party": "Customer", "prefix": "AR", "item_account": "income_account",
        "party_side": "debit", "line_side": "credit",
        "comps": (
            ("tax_amount", "sales_tax_account", "Tax (PPN) Account", "credit"),
            ("pph_amount", "pph23_account", "PPh 23 Account", "debit"),
        ),
    },
}

# Label tampilan. Nama doctype sengaja mengikuti nama tabel (tabAPNotes dst); yang dibaca
# user diganti lewat Translation (ensure_labels, dipanggil after_migrate).
LABELS = {
    "APNotes": "AP Note",
    "APNote Details": "AP Note Details",
    "APNote Type": "AP Note Type",
    "ARNotes": "AR Note",
    "ARNote Details": "AR Note Details",
    "ARNote Type": "AR Note Type",
}


class NoteBase(Document):
    @property
    def _t(self):
        return CFG[self.doctype]

    def autoname(self):
        # Token .cmi_company_abbr. di naming series butuh company terisi sebelum penamaan.
        self._default_company()
        self.naming_series = self._t["prefix"] + "/.cmi_type_code./.cmi_company_abbr./.cmi_yyyy./.####"

    def validate(self):
        self._guard_locked()
        if self.void and not (self.void_reason or "").strip():
            frappe.throw("Alasan Void wajib diisi.")
        self._default_company()
        if frappe.db.get_value(self.meta.get_field("note_type").options, self.note_type, "disabled"):
            frappe.throw(f"Type <b>{self.note_type}</b> sudah Disabled.")
        if not self.currency:
            self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
        self.conversion_rate = flt(self.conversion_rate) or 1.0
        self._resolve_accounts()
        self._clean_rows()
        self._calculate_totals()
        self._sync_state()

    def _default_company(self):
        if not self.company:
            self.company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")

    def _guard_locked(self):
        """Sama dengan Expense Note: sesudah Validate/Void terkunci; membukanya lagi hanya
        Accounts Manager / System Manager."""
        before = None if self.is_new() else self.get_doc_before_save()
        if not before:
            return
        is_mgr = bool(set(frappe.get_roles()) & {"Accounts Manager", "System Manager"})
        for flag, label in (("validated", "Tervalidasi"), ("void", "Void")):
            if before.get(flag):
                if self.get(flag):
                    frappe.throw(f"{self._t['label']} ini sudah <b>{label}</b> dan terkunci.")
                if not is_mgr:
                    frappe.throw("Hanya Accounts Manager / System Manager yang boleh membukanya lagi.")

    def _resolve_accounts(self):
        # Baris ber-Item: akun ikut Default Expense/Income Account Item -> Item Group.
        for it in self.items:
            if it.item:
                it.account = item_account(it.item, self.company, self._t["item_account"]) or it.account
                it.description = it.description or frappe.db.get_value("Item", it.item, "item_name")

    def _clean_rows(self):
        """Cek semua baris tiap Save: Amount kosong/0 = baris dibuang (dianggap dihapus),
        sisanya wajib punya Account Code."""
        rows = [it for it in self.items if flt(flt(it.qty) * flt(it.price), 2)]
        if len(rows) != len(self.items):
            for i, it in enumerate(rows, 1):
                it.idx = i
            self.set("items", rows)
        missing = [str(it.idx) for it in rows if not it.account]
        if missing:
            frappe.throw("Baris berikut belum punya <b>Account Code</b>: #{0}".format(", #".join(missing)))
        if not rows:
            frappe.throw("Isi minimal satu baris dengan Amount lebih dari 0.")

    def _calculate_totals(self):
        total = 0.0
        for it in self.items:
            it.amount = flt(it.qty) * flt(it.price)
            total += it.amount
        self.total_amount = total
        # Smart input PPN/PPh (pola Expense Note): persen -> dihitung ulang dari Amount Total
        # tiap save; nominal -> dipakai apa adanya (tax_input/pph_input cuma tampilan).
        for k in ("tax", "pph"):
            if flt(self.get(k + "_pct")):
                self.set(k + "_amount", flt(total * flt(self.get(k + "_pct")) / 100, 2))
        self.net_total = flt(total + self.tax_amount - self.pph_amount, 2)

    def _sync_state(self):
        user, now = frappe.session.user, now_datetime()
        if self.validated:
            if not self.validated_by:
                self.validated_by, self.validated_date = user, now
        else:
            self.validated_by = self.validated_date = None
        if self.void:
            if not self.void_datetime:
                self.void_by, self.void_datetime = user, now
        else:
            self.void_by = self.void_datetime = None
        self.status = derive_status(self)

    # ---- Jurnal: dibuat saat Validate, dibatalkan+dihapus saat un-validate / void ----
    def on_update(self):
        should_post = bool(self.validated) and not self.void and not self.dont_post_to_gl
        if should_post and not self.journal_entry:
            self.db_set("journal_entry", self._create_journal_entry())
        elif not should_post and self.journal_entry:
            je = self.journal_entry
            self.db_set("journal_entry", None)
            _delete_journal_entry(je)

    def _create_journal_entry(self):
        from erpnext.accounts.party import get_party_account

        t = self._t
        s = frappe.get_cached_doc("ERPNext Custom Setting")

        def need(field, label):
            if not s.get(field):
                frappe.throw(f"Set <b>{label}</b> di ERPNext Custom Setting.")
            return s.get(field)

        party_acc = get_party_account(t["party"], self.associate, self.company)
        if not party_acc and t["party"] == "Supplier":
            # sama dengan Expense Note: supplier tanpa akun hutang -> Default Hutang setting
            party_acc = s.get("default_payable_account")
        if not party_acc:
            frappe.throw(f"{t['party']} <b>{self.associate}</b> belum punya akun Hutang/Piutang default.")

        lines = {}
        for it in self.items:
            if not flt(it.amount):
                continue
            # Akun party di baris biaya/pendapatan menuntut party lain / saling meniadakan
            # dengan hutang-piutangnya sendiri di Payment Ledger -> ditolak.
            if frappe.db.get_value("Account", it.account, "account_type") in ("Receivable", "Payable"):
                frappe.throw(f"Akun <b>{it.account}</b> bertipe Receivable/Payable, tidak bisa dipakai di baris {t['label']}.")
            # Cost Center per baris (modal Add Item); kosong = Cost Center header.
            key = (it.account, it.cost_center or self.cost_center)
            lines[key] = flt(lines.get(key)) + flt(it.amount)
        if not lines:
            frappe.throw("Tidak ada baris untuk dijurnal.")

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.is_system_generated = 1
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.ref or self.name
        je.cheque_date = self.date
        je.user_remark = f"{t['label']} {self.name}" + (f" - {self.remark}" if self.remark else "")
        je.name = self.name
        je.flags.name_set = True

        rate = flt(self.conversion_rate) or 1.0

        # Nominal dokumen x Rate -> mata uang company (akun diasumsikan mata uang company,
        # sama dengan Expense Note).
        def add(account, drcr, amt, cost_center=None, **extra):
            if flt(flt(amt) * rate, 2):
                je.append("accounts", {"account": account, "cost_center": cost_center or self.cost_center,
                                       f"{drcr}_in_account_currency": flt(flt(amt) * rate, 2), **extra})

        add(party_acc, t["party_side"], self.net_total, party_type=t["party"], party=self.associate)
        for (acc, cc), amt in lines.items():
            add(acc, t["line_side"], amt, cost_center=cc)
        for amt_field, acc_field, label, side in t["comps"]:
            if flt(self.get(amt_field)):
                add(need(acc_field, label), side, self.get(amt_field))
        # Sisa pembulatan (Net Total vs jumlah baris) -> Akun Pajak & Penyesuaian.
        resid = flt(sum(flt(r.debit_in_account_currency) - flt(r.credit_in_account_currency) for r in je.accounts), 2)
        if resid:
            je.append("accounts", {"account": need("adjustment_account", "Akun Pajak & Penyesuaian"),
                                   "cost_center": self.cost_center,
                                   ("credit" if resid > 0 else "debit") + "_in_account_currency": abs(resid)})

        je.flags.ignore_permissions = True
        je.insert()
        je.title = f"{self.name} - {self.associate}"
        je.submit()
        frappe.msgprint(f"Journal Entry <b>{je.name}</b> dibuat.", alert=True)
        return je.name


def _delete_journal_entry(je_name):
    """Cancel lalu hapus JE milik note ini (pola Expense Note: jejak audit tetap di note).
    JE yang sudah dilunasi Payment Entry ditolak ERPNext saat cancel — PE-nya dulu."""
    if not frappe.db.exists("Journal Entry", je_name):
        return
    je = frappe.get_doc("Journal Entry", je_name)
    if je.docstatus == 1:
        je.flags.ignore_permissions = True
        je.cancel()
    frappe.delete_doc("Journal Entry", je_name, force=1, ignore_permissions=True, delete_permanently=True)


def derive_status(doc):
    if doc.get("void"):
        return "Void"
    if doc.get("validated") and flt(doc.get("net_total")) and flt(doc.get("paid_amount")) >= flt(doc.get("net_total")) - 0.005:
        return "Paid"
    return "Validated" if doc.get("validated") else "Draft"


# ---- Confidential: pola Pending Cash (query untuk list/report, has_permission per dokumen) ----
def _may_see_confidential(user):
    return bool({"System Manager", "Accounts Manager"} & set(frappe.get_roles(user)))


def _confidential_query(doctype, user):
    user = user or frappe.session.user
    if _may_see_confidential(user):
        return ""
    return f"(`tab{doctype}`.confidential = 0 or `tab{doctype}`.owner = {frappe.db.escape(user)})"


def ap_permission_query(user=None):
    return _confidential_query("APNotes", user)


def ar_permission_query(user=None):
    return _confidential_query("ARNotes", user)


def has_permission(doc, ptype=None, user=None):
    if not doc.get("confidential"):
        return True
    user = user or frappe.session.user
    return doc.owner == user or _may_see_confidential(user)


# ---- Payment Entry (hook di erpnext_custom: app erp steril dari core ERPNext) ----------
# Nama jurnal = nama note (je.name = self.name), jadi baris References PE yang menunjuk
# Journal Entry bernama sama dengan note = pembayaran note itu.
def _notes_in(pe):
    names = {r.reference_name for r in pe.get("references") or [] if r.reference_doctype == "Journal Entry"}
    if not names:
        return []
    out = []
    for dt in CFG:
        for n in frappe.get_all(dt, filters={"journal_entry": ["in", list(names)]},
                                fields=["name", "journal_entry", "skip_payable", "net_total", "validated",
                                        "void", "conversion_rate"]):
            n.doctype = dt
            out.append(n)
    return out


def guard_payment_entry(doc, method=None):
    """Note ber-centang Skip Payable tidak boleh dibayar lewat PV."""
    bad = [n.name for n in _notes_in(doc) if n.skip_payable]
    if bad:
        frappe.throw("Note berikut dicentang <b>Skip Payable</b>, tidak bisa ditarik ke Payment Entry: "
                     "<b>{0}</b>.".format(", ".join(bad)))


def sync_paid_from_payment(doc, method=None):
    """Amount Paid in PV = total alokasi PE SUBMITTED ke jurnal note (dalam mata uang note)."""
    for n in _notes_in(doc):
        paid = flt(frappe.db.sql(
            """select sum(allocated_amount) from `tabPayment Entry Reference`
               where reference_doctype = 'Journal Entry' and reference_name = %s and docstatus = 1""",
            n.journal_entry)[0][0])
        n.paid_amount = flt(paid / (flt(n.conversion_rate) or 1.0), 2)
        frappe.db.set_value(n.doctype, n.name, {"paid_amount": n.paid_amount, "status": derive_status(n)},
                            update_modified=False)


# ---- Payment Entry: AP Note -> PE Pay (Supplier), AR Note -> PE Receive (Customer) ----------
# Dipanggil erpnext_custom.overrides.payment_entry (dialog Add Items + _derive_references).
# Akses mengikuti role Payment Entry (seperti Expense Note), kecuali note Confidential yang
# tetap hanya untuk pembuatnya + Accounts/System Manager.
PE_DOCTYPES = {"Pay": "APNotes", "Receive": "ARNotes"}


def _allocated_in_payments(doctype, name):
    """Yang sudah dialokasikan PE lain (draft ikut) ke note ini, mata uang company."""
    return flt(frappe.db.sql(
        """select sum(it.amount) from `tabPayment Entry Items` it
           join `tabPayment Entry` pe on pe.name = it.parent
           where pe.docstatus in (0, 1) and it.document_type = %s and it.document_no = %s""",
        (doctype, name))[0][0])


def payment_outstanding(doctype, party, company=None):
    """Baris kandidat dialog Add Items PE: note Validated milik `party` yang masih ada sisa.

    Nominal dalam mata uang COMPANY (Net Total x Rate), sama dengan baris party di jurnal
    note — alokasi referensi Journal Entry di PE memang dalam mata uang company, dan
    sync_paid_from_payment membaginya lagi dengan Rate."""
    if not party:
        return []
    filters = {"associate": party, "validated": 1, "void": 0, "skip_payable": 0,
               "dont_post_to_gl": 0, "journal_entry": ["is", "set"]}
    if company:
        filters["company"] = company
    user = frappe.session.user
    see_all = _may_see_confidential(user)
    label = CFG[doctype]["label"]
    out = []
    for n in frappe.get_all(doctype, filters=filters, order_by="date asc, name asc",
                            fields=["name", "journal_entry", "net_total", "conversion_rate", "date",
                                    "owner", "confidential", "company"]):
        if n.confidential and not see_all and n.owner != user:
            continue
        total = flt(flt(n.net_total) * (flt(n.conversion_rate) or 1.0), 2)
        outstanding = flt(total - _allocated_in_payments(doctype, n.name), 2)
        if outstanding <= 0.005:
            continue
        out.append({
            "reference_doctype": doctype,
            "doc_label": label,
            "transaction": n.name,
            "journal_entry": n.journal_entry,
            "date": str(n.date) if n.date else "",
            "owner": n.owner,
            "owner_name": frappe.get_cached_value("User", n.owner, "full_name") or n.owner,
            "grand_total": total,
            "outstanding": outstanding,
            "currency": frappe.get_cached_value("Company", n.company, "default_currency"),
        })
    return out


def payment_journal(doctype, name):
    """Journal Entry note untuk referensi PE — dicek ulang saat PE disimpan: note harus
    masih Validated, tidak Void, dan punya jurnal (bisa saja berubah sejak ditarik)."""
    n = frappe.db.get_value(doctype, name, ["validated", "void", "journal_entry"], as_dict=True)
    label = CFG[doctype]["label"]
    if not n:
        frappe.throw(f"{label} <b>{name}</b> tidak ditemukan.")
    if n.void or not n.validated or not n.journal_entry:
        frappe.throw(f"{label} <b>{name}</b> harus <b>Validated</b> (dan tidak Void) sebelum dibayar lewat Payment Entry.")
    return n.journal_entry


def ensure_labels():
    """Nama tampilan doctype (Translation en). Idempoten; dipanggil after_migrate."""
    for source, label in LABELS.items():
        name = frappe.db.exists("Translation", {"source_text": source, "language": "en"})
        if name:
            frappe.db.set_value("Translation", name, "translated_text", label)
        else:
            frappe.get_doc({"doctype": "Translation", "language": "en", "source_text": source,
                            "translated_text": label}).insert(ignore_permissions=True)

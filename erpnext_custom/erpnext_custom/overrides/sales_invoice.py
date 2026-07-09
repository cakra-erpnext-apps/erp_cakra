"""Server-side customizations untuk core Sales Invoice (erpnext_custom).

Tanggal:  invoice_date -> posting_date ; term_of_payment -> due_date

GL (B2): Discount/Tax/PPh/Materai disuntik ke NATIVE discount + Sales Taxes and
Charges (akun dari CMI Invoice Settings) supaya grand_total -> GL benar.
  Discount : additional_discount (Apply on Net Total)  -- % atau nominal
  Tax (PPN): baris pajak On Net Total / Actual          -- 0 kalau Ignore Tax
  PPh      : baris pajak NEGATIF (potongan)
  Materai  : baris pajak Actual (nominal)

Reimburse: line_amount = amount(Expense Note net_total) * rate. Ikut ke AmountTotal
& NetTotal (tampilan); belum diposting ke GL (pakai Don't Post to GL atau wiring
akun pendapatan menyusul).

custom_net_total = grand_total (item+pajak) + total reimburse + adjustment.
dont_post_to_gl -> Submit tanpa GL. Audit: validated_by / voided_by.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

TAX_DESC = "CMI: Tax"
PPH_DESC = "CMI: PPh"
MATERAI_DESC = "CMI: Materai"
_CMI_DESCS = (TAX_DESC, PPH_DESC, MATERAI_DESC)

# Field gabungan (Data) -> storage tersembunyi (percent, amount). User mengetik "10%"
# (persen) ATAU "50000" (nominal) di satu field; di-parse ke percent/amount yang
# dikonsumsi logika GL/validate/print. UI: sales_invoice.js (cmi_apply_input).
_SMART_INPUTS = (
    ("custom_discount_input", "custom_discount_percent", "custom_discount_amount"),
    ("custom_pph_input", "custom_pph_percent", "custom_pph_amount"),
    ("custom_tax_input", "custom_tax_percent", "custom_tax_amount"),
)


def _currency_precision():
    """Presisi desimal nominal = default sistem (System Settings > Currency Precision)."""
    from frappe.utils import cint

    return cint(frappe.db.get_default("currency_precision")) or 2


def _parse_smart(raw):
    """'10%' -> ('pct', 10.0); '10.000,001' -> ('amt', dibulatkan ke presisi default).

    Locale Indonesia: titik = pemisah ribuan, koma = desimal.
    """
    s = ("" if raw is None else str(raw)).strip()
    if not s:
        return (None, 0.0)
    is_pct = "%" in s
    cleaned = re.sub(r"[^\d,.-]", "", s).replace(".", "").replace(",", ".")
    try:
        num = float(cleaned)
    except ValueError:
        num = 0.0
    return ("pct", num) if is_pct else ("amt", flt(num, _currency_precision()))


def _apply_smart_inputs(doc):
    """Isi percent/amount tersembunyi dari field gabungan (kalau diisi).

    Kalau field gabungan kosong, percent/amount yang sudah ada DIPERTAHANKAN (mis.
    diset langsung oleh agent/API). Amount dalam mode persen dihitung ulang di validate().
    Nilai numerik murni (kiriman API) dianggap nominal apa adanya (tanpa parse locale).
    """
    for in_f, pct_f, amt_f in _SMART_INPUTS:
        raw = doc.get(in_f)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if not isinstance(raw, str):
            doc.set(pct_f, 0)
            doc.set(amt_f, flt(raw, _currency_precision()))
            continue
        mode, num = _parse_smart(raw)
        if mode == "pct":
            doc.set(pct_f, num)
            doc.set(amt_f, 0)
        else:
            doc.set(pct_f, 0)
            doc.set(amt_f, num)


def _settings():
    return frappe.get_cached_doc("CMI Invoice Settings")


def _need(account, label):
    if not account:
        frappe.throw(_("Set akun '{0}' di CMI Invoice Settings.").format(label))
    return account


def sync_header_address(doc, method=None):
    """Alamat header: field custom (di samping Customer) adalah sumber kebenaran;
    sinkronkan ke field core customer_address/address_display (dipakai print out).
    Dipanggil dari before_validate (draft) DAN before_update_after_submit (invoice
    submitted — field ber-allow_on_submit)."""
    if doc.get("custom_customer_address"):
        from frappe.contacts.doctype.address.address import get_address_display

        doc.customer_address = doc.custom_customer_address
        doc.address_display = get_address_display(
            frappe.get_doc("Address", doc.custom_customer_address).as_dict()
        )
    elif doc.get("customer_address") and not doc.get("custom_customer_address"):
        # Kompatibel mundur: kalau core terisi (mis. via API lama), angkat ke field custom.
        doc.custom_customer_address = doc.customer_address


def before_validate(doc, method=None):
    _apply_smart_inputs(doc)  # field gabungan "10%"/"50000" -> percent/amount tersembunyi
    sync_header_address(doc)

    # Tanggal: invoice_date -> posting_date; kalau kosong, default hari ini.
    if not doc.get("invoice_date"):
        doc.invoice_date = today()
    # set_posting_time=1 WAJIB: tanpa ini ERPNext memaksa posting_date = hari ini
    # (mengabaikan invoice_date) -> memicu "Due Date cannot be before Posting Date".
    doc.set_posting_time = 1
    doc.posting_date = doc.invoice_date
    # due_date HARUS di-set di sini (before_validate) — sebelum validate inti ERPNext
    # yang melempar "Due Date cannot be before Posting Date". Default = posting_date
    # (net 0 hari); pakai term_of_payment kalau ada; tak pernah lebih awal dari posting.
    due = doc.get("term_of_payment") or doc.posting_date
    if doc.get("posting_date") and getdate(due) < getdate(doc.posting_date):
        due = doc.posting_date
    doc.due_date = due
    # payment_schedule lama bisa stale (due dari posting lama) -> kosongkan agar ERPNext
    # bangun ulang dari posting_date baru (cegah due schedule < posting). Skip kalau ada
    # payment_terms_template (biar ERPNext hitung dari template).
    if not doc.get("payment_terms_template"):
        doc.set("payment_schedule", [])

    # Discount -> native (Apply on Net Total). % menang kalau diisi, else nominal.
    doc.apply_discount_on = "Net Total"
    if flt(doc.get("custom_discount_percent")):
        doc.additional_discount_percentage = flt(doc.custom_discount_percent)
        doc.discount_amount = 0
    else:
        doc.additional_discount_percentage = 0
        doc.discount_amount = flt(doc.get("custom_discount_amount"))

    # Bangun ulang baris pajak CMI (pertahankan baris lain yang dibuat manual).
    s = _settings()
    kept = [t for t in (doc.get("taxes") or []) if (t.get("description") or "") not in _CMI_DESCS]
    doc.set("taxes", kept)

    def add_pct(account, desc, pct, sign=1):
        doc.append("taxes", {"charge_type": "On Net Total", "account_head": account,
                             "description": desc, "rate": sign * flt(pct)})

    def add_amt(account, desc, amt, sign=1):
        doc.append("taxes", {"charge_type": "Actual", "account_head": account,
                             "description": desc, "rate": 0, "tax_amount": sign * flt(amt)})

    # Tax (PPN) — % menang; di-skip kalau Ignore Tax.
    if not doc.get("custom_ignore_tax"):
        if flt(doc.get("custom_tax_percent")):
            add_pct(_need(s.tax_account, "Tax (PPN)"), TAX_DESC, doc.custom_tax_percent, 1)
        elif flt(doc.get("custom_tax_amount")):
            add_amt(_need(s.tax_account, "Tax (PPN)"), TAX_DESC, doc.custom_tax_amount, 1)
    # PPh — potongan (negatif).
    if flt(doc.get("custom_pph_percent")):
        add_pct(_need(s.pph23_account, "PPh 23"), PPH_DESC, doc.custom_pph_percent, -1)
    elif flt(doc.get("custom_pph_amount")):
        add_amt(_need(s.pph23_account, "PPh 23"), PPH_DESC, doc.custom_pph_amount, -1)
    # Materai — nominal tetap.
    if flt(doc.get("custom_materai")):
        add_amt(_need(s.materai_account, "Materai"), MATERAI_DESC, doc.custom_materai, 1)


_HEADER_REQUIRED = [
    ("custom_invoice_type", "Invoice Type"),
    ("custom_invoice_type_no", "Invoice Type No"),
    ("customer", "Customer"),
    ("invoice_date", "Invoice Date"),
]


def _require_header(doc):
    """Header wajib lengkap sebelum ada isi Items/Reimburse."""
    has_content = any(it.get("item_code") for it in (doc.get("items") or [])) or any(
        r.get("expense_note") for r in (doc.get("custom_reimburse_items") or [])
    )
    if not has_content:
        return
    missing = [lbl for fn, lbl in _HEADER_REQUIRED if not doc.get(fn)]
    if missing:
        frappe.throw(_("Lengkapi dulu: {0} sebelum mengisi Items / Reimburse.").format(", ".join(missing)))


def validate(doc, method=None):
    _require_header(doc)
    # (due_date sudah di-set di before_validate, sebelum validate inti ERPNext.)

    # Mirror Amount dari % (kalau pakai %) supaya field Amount menampilkan Rp.
    total = flt(doc.get("total"))
    if flt(doc.get("custom_discount_percent")):
        doc.custom_discount_amount = total * flt(doc.custom_discount_percent) / 100.0
    discount = flt(doc.get("custom_discount_amount"))
    dpp = total - discount
    if doc.get("custom_ignore_tax"):
        doc.custom_tax_amount = 0
    elif flt(doc.get("custom_tax_percent")):
        doc.custom_tax_amount = dpp * flt(doc.custom_tax_percent) / 100.0
    if flt(doc.get("custom_pph_percent")):
        doc.custom_pph_amount = dpp * flt(doc.custom_pph_percent) / 100.0

    # Reimburse: line_amount = amount * rate ; ikut ke total.
    reimb_total = 0.0
    for r in (doc.get("custom_reimburse_items") or []):
        r.line_amount = flt(r.amount) * flt(r.rate or 1)
        reimb_total += flt(r.line_amount)

    doc.custom_amount_total = total + reimb_total
    doc.custom_net_total = flt(doc.get("grand_total")) + reimb_total + flt(doc.get("custom_adjustment"))


INV_DRAFT_PREFIX = "DRAFT-"


def _is_inv_draft_name(name):
    return bool(name) and str(name).startswith(INV_DRAFT_PREFIX)


def _company_code(company):
    """Kode company untuk penomoran = Company.abbr (dari tabCompany, sama spt Company Settings).

    DINAMIS per-deployment: abbr "CMI" di lokal, "OGM" di server OGM, dst. Fallback "CMI"
    kalau company/abbr kosong.
    """
    return (frappe.db.get_value("Company", company, "abbr") if company else None) or "CMI"


def _invoice_autoname_pattern(doc):
    """Pola nomor invoice: {InvoiceTypeNo}/{#####}/{abbr}/{YY}.

    Counter di-reset per (InvoiceTypeNo, abbr, tahun) — mis. C/E/00001/CMI/26, C/E/00001/OGM/26.
    """
    return ".custom_invoice_type_no./.#####./%s/.YY." % _company_code(doc.get("company"))


class CMISalesInvoice(SalesInvoice):
    """Override controller core Sales Invoice tanpa mengedit erpnext."""

    def autoname(self):
        # Draft buatan agent: nama sementara, seri BELUM dipakai. Nomor asli diberikan
        # saat user Save/Confirm (assign_invoice_number).
        if self.flags.get("agent_draft"):
            self.name = INV_DRAFT_PREFIX + frappe.generate_hash(length=10)
            return
        # Non-agent: nomor langsung. Kode company DINAMIS dari Company.abbr (CMI/OGM/...)
        # dibangun eksplisit di sini — TIDAK bergantung pada Property Setter autoname yg
        # statis (yg kalau tak ter-apply di server bikin nomor jatuh ke "00001" polos).
        from frappe.model.naming import make_autoname

        self.name = make_autoname(_invoice_autoname_pattern(self), "Sales Invoice", self)

    def get_print_settings(self):
        # Sidebar print view: tambah input "Invoice Title" (field custom di Print
        # Settings) untuk mengganti judul print out, mis. INVOICE -> DEBIT NOTE.
        fields = super().get_print_settings() or []
        fields.append("invoice_title")
        return fields

    def make_gl_entries(self, *args, **kwargs):
        if self.get("dont_post_to_gl"):
            return
        return super().make_gl_entries(*args, **kwargs)

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)


@frappe.whitelist()
def get_reimburse_expense_notes(customer, currency=None):
    """Expense Note reimburse yang BELUM dipakai di invoice mana pun.

    Filter: is_reimburse=1, validated=1 (belum void), currency cocok, reimburse_to_customer
    cocok dgn customer invoice (best-effort by NAME), dan belum ada di Reimburse Item.

    NB: Expense Note tidak punya field `status` — status "Validated" = validated=1 & void!=1.
    """
    used = set(frappe.get_all("Reimburse Item", pluck="expense_note") or [])
    filters = {"is_reimburse": 1, "validated": 1, "void": ["!=", 1]}
    if currency:
        filters["currency"] = currency
    # reimburse_to_customer = CRM Organization; cocokkan by nama customer (best-effort).
    cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    filters["reimburse_to_customer"] = ["in", list({customer, cust_name})]
    rows = frappe.get_all(
        "Expense Note",
        filters=filters,
        fields=["name", "date", "ref", "currency", "net_total", "remark"],
    )
    out = []
    for r in rows:
        if r["name"] in used:
            continue
        out.append({
            "expense_note": r["name"],
            "document_date": r["date"],
            "document_no_fp": r.get("ref"),
            "note": r.get("remark"),
            "currency": r.get("currency"),
            "amount": flt(r.get("net_total")),
        })
    return out


@frappe.whitelist()
def assign_invoice_number(docname):
    """Beri nomor asli ke Sales Invoice draft yang masih bernama sementara (DRAFT-...).

    Dipanggil saat user Save/Confirm. Seri (autoname Property Setter — kode company
    dinamis dari Abbr) baru dipakai DI SINI, lalu invoice di-rename dari nama sementara
    ke nomor asli.
    """
    from frappe.model.naming import make_autoname

    if not _is_inv_draft_name(docname):
        return {"name": docname, "changed": False}

    doc = frappe.get_doc("Sales Invoice", docname)
    # Kode company dinamis dari Company.abbr (sama dgn CMISalesInvoice.autoname).
    new_name = make_autoname(_invoice_autoname_pattern(doc), "Sales Invoice", doc)
    doc.rename(new_name, force=True)  # mengubah doc.name -> new_name lalu reload
    frappe.db.commit()
    return {"name": new_name, "changed": True}


@frappe.whitelist()
def revise_invoice(docname):
    """Tombol "Revisi": cancel + buat ulang invoice sebagai draft dengan NOMOR SAMA.

    Alternatif Amend tanpa nomor "-1": GL invoice lama dibatalkan, dokumen lama
    dihapus, lalu salinannya dibuat kembali memakai nomor yang sama sebagai draft
    yang bebas diedit. Hanya Accounts Manager / System Manager. Pembayaran yang
    masih aktif harus dibatalkan dulu.
    """
    if not set(frappe.get_roles()) & {"Accounts Manager", "System Manager"}:
        frappe.throw(_("Hanya Accounts Manager / System Manager yang boleh merevisi invoice."))
    doc = frappe.get_doc("Sales Invoice", docname)
    if doc.docstatus != 1:
        frappe.throw(_("Hanya invoice yang sudah Submitted yang bisa direvisi."))
    pe = frappe.db.sql(
        """SELECT DISTINCT parent FROM `tabPayment Entry Reference`
           WHERE reference_doctype='Sales Invoice' AND reference_name=%s AND docstatus=1""",
        docname,
    )
    if pe:
        frappe.throw(
            _("Batalkan dulu Payment Entry terkait: {0}").format(", ".join(p[0] for p in pe))
        )

    new = frappe.copy_doc(doc)  # salinan lengkap (items, taxes, containers), docstatus 0
    new.amended_from = None

    doc.flags.cmi_action_ok = True  # lolos guard_cancel (revisi = jalur resmi)
    doc.flags.ignore_permissions = True
    doc.cancel()
    frappe.delete_doc("Sales Invoice", docname, force=1, ignore_permissions=True)

    new.name = docname
    new.flags.name_set = True  # pakai nomor lama, tidak menarik seri baru
    new.flags.ignore_permissions = True
    new.insert()
    frappe.db.commit()
    return new.name


# ---- Validate / Void (pengganti Submit / Cancel bawaan) --------------------
# Tombol Submit & Cancel bawaan disembunyikan (permission submit/cancel dicabut).
# Submit hanya lewat tombol "Validate" (role Invoice Validate) dan cancel hanya
# lewat tombol "Void" (role Invoice Void) / "Revisi". Guard di bawah memblokir
# jalur API langsung.

def _has_role(*roles):
    return bool(set(frappe.get_roles()) & (set(roles) | {"System Manager"}))


def guard_submit(doc, method=None):
    if doc.flags.get("cmi_action_ok"):
        return
    if not _has_role("Invoice Validate"):
        frappe.throw(_("Hanya user dengan role <b>Invoice Validate</b> yang boleh memvalidasi invoice."))


def guard_cancel(doc, method=None):
    if doc.flags.get("cmi_action_ok"):
        return
    if not _has_role("Invoice Void"):
        frappe.throw(_("Hanya user dengan role <b>Invoice Void</b> yang boleh mem-void invoice."))


@frappe.whitelist()
def validate_invoice(docname):
    """Tombol "Validate": submit invoice (posting ke GL)."""
    if not _has_role("Invoice Validate"):
        frappe.throw(_("Hanya user dengan role <b>Invoice Validate</b> yang boleh memvalidasi invoice."))
    doc = frappe.get_doc("Sales Invoice", docname)
    if doc.docstatus != 0:
        frappe.throw(_("Hanya invoice draft yang bisa divalidasi."))
    doc.flags.cmi_action_ok = True
    doc.flags.ignore_permissions = True
    doc.submit()
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def void_invoice(docname, reason=None):
    """Tombol "Void": cancel invoice (jurnal dibalik), alasan dicatat sebagai komentar."""
    if not _has_role("Invoice Void"):
        frappe.throw(_("Hanya user dengan role <b>Invoice Void</b> yang boleh mem-void invoice."))
    doc = frappe.get_doc("Sales Invoice", docname)
    if doc.docstatus != 1:
        frappe.throw(_("Hanya invoice yang sudah tervalidasi yang bisa di-void."))
    pe = frappe.db.sql(
        """SELECT DISTINCT parent FROM `tabPayment Entry Reference`
           WHERE reference_doctype='Sales Invoice' AND reference_name=%s AND docstatus=1""",
        docname,
    )
    if pe:
        frappe.throw(_("Batalkan dulu Payment Entry terkait: {0}").format(", ".join(p[0] for p in pe)))
    doc.flags.cmi_action_ok = True
    doc.flags.ignore_permissions = True
    doc.cancel()
    if reason:
        doc.add_comment("Comment", _("VOID oleh {0}: {1}").format(frappe.session.user, reason))
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def mark_customer_paid(docname, paid_date=None, note=None, attachment=None):
    """Tombol "Customer Paid": catat pembayaran customer (paid date, note, attachment).

    Dipakai baik saat draft maupun sudah submitted; pakai db_set supaya field read-only
    tetap tersimpan walau invoice sudah tervalidasi (docstatus=1).
    """
    doc = frappe.get_doc("Sales Invoice", docname)
    paid_date = paid_date or today()
    doc.db_set({
        "custom_customer_paid": 1,
        "custom_paid_date": paid_date,
        "custom_paid_note": note or "",
        "custom_paid_attachment": attachment or "",
    })
    doc.add_comment(
        "Comment",
        _("Customer Paid oleh {0} (tgl {1}){2}").format(
            frappe.session.user, paid_date, ": " + note if note else ""
        ),
    )
    frappe.db.commit()
    return doc.name

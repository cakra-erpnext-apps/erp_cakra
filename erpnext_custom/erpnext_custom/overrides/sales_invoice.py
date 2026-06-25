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


def _parse_smart(raw):
    """'10%' -> ('pct', 10.0); '50.000' / 'Rp 50.000' -> ('amt', 50000.0); kosong -> (None, 0).

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
    return ("pct", num) if is_pct else ("amt", num)


def _apply_smart_inputs(doc):
    """Isi percent/amount tersembunyi dari field gabungan (kalau diisi).

    Kalau field gabungan kosong, percent/amount yang sudah ada DIPERTAHANKAN (mis.
    diset langsung oleh agent/API). Amount dalam mode persen dihitung ulang di validate().
    """
    for in_f, pct_f, amt_f in _SMART_INPUTS:
        raw = doc.get(in_f)
        if raw is None or not str(raw).strip():
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


def before_validate(doc, method=None):
    _apply_smart_inputs(doc)  # field gabungan "10%"/"50000" -> percent/amount tersembunyi

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


class CMISalesInvoice(SalesInvoice):
    """Override controller core Sales Invoice tanpa mengedit erpnext."""

    def autoname(self):
        # Draft buatan agent: nama sementara, seri BELUM dipakai. Nomor asli diberikan
        # saat user Save/Confirm (assign_invoice_number). Untuk invoice non-agent,
        # biarkan kosong -> Frappe pakai autoname Property Setter (.custom_invoice_type_no.
        # /.#####./CMI/.YY.) seperti biasa.
        if self.flags.get("agent_draft"):
            self.name = INV_DRAFT_PREFIX + frappe.generate_hash(length=10)

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

    Dipanggil saat user Save/Confirm. Seri (.custom_invoice_type_no./.#####./CMI/.YY.)
    baru dipakai DI SINI, lalu invoice di-rename dari nama sementara ke nomor asli.
    """
    from frappe.model.naming import make_autoname

    if not _is_inv_draft_name(docname):
        return {"name": docname, "changed": False}

    doc = frappe.get_doc("Sales Invoice", docname)
    autoname = doc.meta.autoname or ""
    if not autoname:
        frappe.throw(_("Sales Invoice belum punya pola autoname (Property Setter)."))

    new_name = make_autoname(autoname, "Sales Invoice", doc)
    doc.rename(new_name, force=True)  # mengubah doc.name -> new_name lalu reload
    frappe.db.commit()
    return {"name": new_name, "changed": True}

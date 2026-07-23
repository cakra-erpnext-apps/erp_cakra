"""Server-side customizations untuk core Purchase Order & Purchase Invoice (erpnext_custom).

Mirror pola Sales Invoice (lihat overrides/sales_invoice.py): Discount/Tax(PPN)/PPh/
Materai dari field gabungan (Data, "10%" / "50000") disuntik ke NATIVE Purchase Taxes
and Charges supaya grand_total -> GL benar.

  Discount : additional_discount (Apply on Net Total)  -- % atau nominal
  Tax (PPN Masukan) : baris pajak positif (asset / pajak masukan dikreditkan)
  PPh      : baris pajak NEGATIF (CMI memotong PPh dari vendor -> utang pajak)
  Materai  : baris pajak Actual (nominal)

PENTING — akun PEMBELIAN beda dari penjualan. Set di ERPNext Custom Setting (tab Invoice Setting, bagian
Purchase): `purchase_tax_account` (PPN Masukan, asset), `purchase_pph_account`
(PPh terutang dipotong, liability), `purchase_materai_account`. Draft aman tanpa akun;
saat akun dipakai (ada nilai Tax/PPh/Materai) `_need()` mewajibkan akun ter-set.

Purchase Order TIDAK posting GL (dokumen order) -> injeksi hanya mempengaruhi
grand_total PO. Purchase Invoice posting GL; `dont_post_to_gl` -> skip make_gl_entries.
Audit: validated_by saat submit, voided_by saat cancel.
"""

import frappe
from frappe import _
from frappe.utils import flt
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

from erpnext_custom.overrides import fill_cost_center

# Pakai ulang parser field gabungan milik Sales Invoice (field-name & locale identik).
from erpnext_custom.overrides.sales_invoice import _apply_smart_inputs

TAX_DESC = "CMI: Tax"
PPH_DESC = "CMI: PPh"
MATERAI_DESC = "CMI: Materai"
_CMI_DESCS = (TAX_DESC, PPH_DESC, MATERAI_DESC)


def _settings():
    return frappe.get_cached_doc("ERPNext Custom Setting")


def _need(account, label):
    if not account:
        frappe.throw(_("Set akun '{0}' (bagian Purchase) di ERPNext Custom Setting.").format(label))
    return account


def _inject_amounts(doc):
    """Suntik Discount/PPN/PPh/Materai ke native Purchase Taxes and Charges."""
    _apply_smart_inputs(doc)  # field gabungan "10%"/"50000" -> percent/amount tersembunyi

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

    # Tax (PPN Masukan) — % menang; di-skip kalau Ignore Tax.
    if not doc.get("custom_ignore_tax"):
        if flt(doc.get("custom_tax_percent")):
            add_pct(_need(s.get("purchase_tax_account"), "Tax (PPN Masukan)"), TAX_DESC, doc.custom_tax_percent, 1)
        elif flt(doc.get("custom_tax_amount")):
            add_amt(_need(s.get("purchase_tax_account"), "Tax (PPN Masukan)"), TAX_DESC, doc.custom_tax_amount, 1)
    # PPh — potongan (negatif): mengurangi yang dibayar ke vendor.
    if flt(doc.get("custom_pph_percent")):
        add_pct(_need(s.get("purchase_pph_account"), "PPh terutang dipotong"), PPH_DESC, doc.custom_pph_percent, -1)
    elif flt(doc.get("custom_pph_amount")):
        add_amt(_need(s.get("purchase_pph_account"), "PPh terutang dipotong"), PPH_DESC, doc.custom_pph_amount, -1)
    # Materai — nominal tetap.
    if flt(doc.get("custom_materai")):
        add_amt(_need(s.get("purchase_materai_account"), "Materai"), MATERAI_DESC, doc.custom_materai, 1)


def _compute_display(doc):
    """Mirror Amount dari % (supaya field Amount menampilkan Rp) + AmountTotal/NetTotal."""
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
    doc.custom_amount_total = total
    # grand_total sudah memperhitungkan diskon + baris pajak CMI -> net = grand_total + adjustment.
    doc.custom_net_total = flt(doc.get("grand_total")) + flt(doc.get("custom_adjustment"))


# --- doc_events (PO & PI berbagi logika yang sama) ------------------------------
def before_validate(doc, method=None):
    _inject_amounts(doc)


def validate(doc, method=None):
    _compute_display(doc)


class CMIPurchaseOrder(PurchaseOrder):
    """Override controller core Purchase Order (audit)."""

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)


class CMIPurchaseInvoice(PurchaseInvoice):
    """Override controller core Purchase Invoice (dont_post_to_gl + audit)."""

    def make_gl_entries(self, *args, **kwargs):
        if self.get("dont_post_to_gl"):
            return
        return super().make_gl_entries(*args, **kwargs)

    def get_gl_dict(self, args, account_currency=None, item=None):
        return fill_cost_center(self, super().get_gl_dict(args, account_currency, item), item)

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)

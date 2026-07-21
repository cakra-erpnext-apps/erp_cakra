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

from erpnext_custom.overrides import fill_cost_center

TAX_DESC = "CMI: Tax"
PPH_DESC = "CMI: PPh"
MATERAI_DESC = "CMI: Materai"
REIMBURSE_TAX_DESC = "CMI: Reimburse PPN"
_CMI_DESCS = (TAX_DESC, PPH_DESC, MATERAI_DESC, REIMBURSE_TAX_DESC)

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


def _to_number(s):
    """String angka bebas locale -> float (selaras cmi_to_number/en_to_number di JS).

    Kalau ada titik DAN koma, pemisah yang muncul TERAKHIR = desimal ("1.234,56" &
    "1,234.56" -> 1234.56). Kalau satu jenis saja, pola kelompok-3 = ribuan
    ("2,000,000"/"2.000.000" -> 2000000 — dulu "2,000,000" salah dibaca 2); selain
    pola itu = desimal ("11,5" -> 11.5; "1000.00" -> 1000, bukan 100000).
    """
    s = re.sub(r"[^\d.,-]", "", s or "")
    if not s:
        return 0.0
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    dec = None
    if last_dot != -1 and last_comma != -1:
        dec = "." if last_dot > last_comma else ","
    elif last_comma != -1:
        dec = None if re.match(r"^-?\d{1,3}(,\d{3})+$", s) else ","
    elif last_dot != -1:
        dec = None if re.match(r"^-?\d{1,3}(\.\d{3})+$", s) else "."
    if dec:
        i = s.rfind(dec)
        intp, frac = s[:i], s[i + 1 :]
    else:
        intp, frac = s, ""
    intp = re.sub(r"[.,]", "", intp)
    frac = re.sub(r"[.,]", "", frac)
    try:
        return float(intp + ("." + frac if frac else ""))
    except ValueError:
        return 0.0


def _parse_smart(raw):
    """'10%' -> ('pct', 10.0); '10.000,001' -> ('amt', dibulatkan ke presisi default)."""
    s = ("" if raw is None else str(raw)).strip()
    if not s:
        return (None, 0.0)
    is_pct = "%" in s
    num = _to_number(s)
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


def _sync_shipping_list_nos(doc, method=None):
    """Kolom list view "Shipping List" (custom_shipping_list_nos): nomor Shipping List
    invoice ini — dari Connection (custom_shipping_list) DAN dari tiap Expense Note di
    Reimburse Items. Distinct, dipisah koma kalau lebih dari satu."""
    nos = []
    if doc.get("custom_shipping_list"):
        nos.append(doc.custom_shipping_list)
    ens = [r.expense_note for r in (doc.get("custom_reimburse_items") or []) if r.get("expense_note")]
    if ens:
        for r in frappe.get_all(
            "Expense Note",
            filters={"name": ["in", list(dict.fromkeys(ens))]},
            fields=["name", "shipping_list"],
        ):
            if r.shipping_list:
                nos.append(r.shipping_list)
    doc.custom_shipping_list_nos = ", ".join(dict.fromkeys(nos))


# Tabel isi per Invoice Type / Input Mode. Tabel yang TIDAK dipakai dikosongkan saat save
# supaya sisa isian dari mode lain tidak ikut tersimpan (cegah dobel).
_TABLE_LABEL = {
    "items": "Items",
    "custom_reimburse_items": "Reimburse Items",
    "custom_dn_items": "Debit Note Items",
}


def _unused_tables(doc):
    # Behavior (Normal/Reimburse/Debit Note), bukan nama tipe — tipe kini dinamis.
    behavior = doc.get("custom_invoice_behavior")
    if behavior == "Reimburse":
        # `items` TIDAK dikosongkan lagi: isinya diturunkan dari Reimburse Items
        # (_sync_reimburse_items) supaya invoice punya nilai yang bisa dijurnal.
        return ["custom_dn_items"]
    if behavior == "Debit Note":
        # Manual -> pakai custom_dn_items; selain itu (Item) -> pakai items.
        other = "items" if doc.get("custom_dn_input_mode") == "Manual" else "custom_dn_items"
        return ["custom_reimburse_items", other]
    # Normal -> hanya Items.
    return ["custom_reimburse_items", "custom_dn_items"]


def _clear_unused_tables(doc):
    dropped = []
    for fn in _unused_tables(doc):
        rows = doc.get(fn) or []
        if rows:
            dropped.append("{0} ({1} baris)".format(_TABLE_LABEL.get(fn, fn), len(rows)))
            doc.set(fn, [])
    if dropped:
        frappe.msgprint(
            _("Baris pada tabel yang tidak dipakai tipe ini tidak disimpan: {0}").format(", ".join(dropped)),
            indicator="orange",
            alert=True,
        )


# Baris reimburse tidak punya Item master (satuannya tidak relevan), tapi `uom` wajib
# diisi ERPNext. "Nos" = satuan generik bawaan.
_REIMBURSE_UOM = "Nos"


def _reimburse_tax_account():
    """Akun PPN reimburse = akun yang DIDEBIT Expense Note saat mencatat PPN Masukan.

    Sengaja mengambil dari Expense Note Settings, bukan setting sendiri: kredit di invoice
    ini harus mendarat di akun yang PERSIS sama dengan debitnya di Expense Note, kalau tidak
    PPN Masukan-nya menggantung selamanya.
    """
    return frappe.db.get_single_value("Expense Note Settings", "tax_account")


def _sync_reimburse_items(doc):
    """Reimburse: turunkan tiap baris Reimburse Items jadi baris `items` senilai DPP-nya.

    Dulu tabel `items` sengaja dikosongkan, jadi grand_total invoice 0 dan tidak ada yang
    bisa dijurnal — invoicenya tercetak bernilai tapi tak pernah masuk buku (dan tak bisa
    ditagih lewat Payment Entry karena outstanding-nya 0). Dengan diturunkan ke `items`,
    seluruh mesin ERPNext jalan apa adanya: GL, piutang, outstanding, sampai pelunasan.

    Kredit tiap baris = akun tipe Reimburse (dipasang _apply_type_income_account, mis.
    1510.001 Reimbursement) sehingga aset yang dicatat Expense Note tertutup saat ditagihkan.
    PPN-nya baris pajak terpisah (REIMBURSE_TAX_DESC).

    Baris `items` di sini SEPENUHNYA turunan: dibangun ulang tiap save, jadi isian manual
    di grid Items akan tertimpa (grid-nya memang disembunyikan untuk tipe Reimburse).
    """
    if doc.get("custom_invoice_behavior") != "Reimburse":
        return
    rows = [r for r in (doc.get("custom_reimburse_items") or []) if r.get("expense_note")]
    doc.set("items", [])
    # Baris turunan tidak lewat set_missing_values item master, jadi cost center-nya diisi
    # sendiri: Cost Center dokumen, mundur ke default company.
    cc = doc.get("cost_center") or frappe.get_cached_value("Company", doc.company, "cost_center")
    for r in rows:
        rate = flt(r.get("rate") or 1)
        doc.append("items", {
            "cost_center": cc,
            "item_name": (r.get("alias") or r.get("expense_class") or r.expense_note)[:140],
            "description": r.get("note") or r.get("expense_class") or r.expense_note,
            "qty": 1,
            "uom": _REIMBURSE_UOM,
            "stock_uom": _REIMBURSE_UOM,
            "conversion_factor": 1,
            # Mengikuti model currency per-item (_apply_item_currency): price dalam mata uang
            # baris, rate core dalam mata uang header.
            "custom_currency": r.get("currency") or doc.get("currency"),
            "custom_exchange_rate": rate,
            "custom_item_price": flt(r.get("amount")),
            "rate": flt(r.get("amount")) * rate,
            "price_list_rate": flt(r.get("amount")) * rate,
        })


def _apply_type_income_account(doc):
    """Pasang akun pendapatan (Cr) tiap baris Items dari Default Account tipe invoice
    (Selling Settings > Invoice Type). OTORITATIF: nama tipe -> satu akun, jadi kredit GL
    konsisten per tipe (Expedition -> Trucking, Trading -> Penjualan Barang Dagang).

    Hanya menyentuh tabel `items`. Reimburse (pakai custom_reimburse_items) & Debit Note
    mode Manual (custom_dn_items) tak punya baris items -> tak terpengaruh. Kalau tipe belum
    punya Default Account (belum di-set / tipe tak dikenal), item dibiarkan -> jatuh ke
    set_missing_values ERPNext (item default -> Company default income) seperti biasa."""
    from erpnext_custom.invoice_types import income_account_of

    acc = income_account_of(doc.get("custom_invoice_type"))
    if not acc:
        return
    for it in doc.get("items") or []:
        it.income_account = acc


def _apply_item_currency(doc):
    """Currency & rate per baris item -> `rate` core dalam mata uang HEADER.

    Tiap item boleh beda mata uang dari header (row IDR, row USD). User isi Price dalam mata
    uang item (custom_item_price); kita set `rate` core = price * exchange_rate, jadi nilainya
    dalam mata uang header dan amount/total/pajak/GL ERPNext otomatis benar (tak ada mesin inti
    yang diubah). WAJIB jalan SEBELUM calculate core (dari before_validate).

      custom_currency default = mata uang header.
      custom_currency == header -> exchange_rate 1 (dikunci).
      custom_currency != header -> exchange_rate WAJIB diisi (kurs item->header).

    Kompat mundur: baris lama yang hanya punya `rate` (tanpa custom_item_price) diangkat jadi
    price=rate, currency=header, exchange_rate=1 — nilainya tidak berubah.
    """
    header_cur = doc.get("currency") or frappe.get_cached_value("Company", doc.company, "default_currency")
    for i, it in enumerate(doc.get("items") or [], start=1):
        cur = it.get("custom_currency") or header_cur
        it.custom_currency = cur

        # Backfill baris lama: rate ada tapi custom_item_price belum -> price = rate (IDR).
        if not flt(it.get("custom_item_price")) and flt(it.get("rate")):
            it.custom_item_price = flt(it.rate)
            if not it.get("custom_exchange_rate"):
                it.custom_exchange_rate = 1

        if cur == header_cur:
            it.custom_exchange_rate = 1
        elif flt(it.get("custom_exchange_rate")) <= 0:
            frappe.throw(_(
                "Item baris {0} memakai mata uang <b>{1}</b> (beda dari header <b>{2}</b>): isi <b>Rate</b> (kurs)."
            ).format(i, cur, header_cur))

        # rate core = harga dalam mata uang HEADER. Set price_list_rate = rate juga supaya
        # mesin diskon/price-list core tidak menimpanya balik saat calculate.
        it.rate = flt(it.get("custom_item_price")) * flt(it.get("custom_exchange_rate") or 1)
        it.price_list_rate = it.rate

        # WAJIB: matikan mesin Margin/Diskon per-item milik core. Di sini `rate` SEPENUHNYA
        # ditentukan price x exchange_rate — tidak ada konsep margin/diskon per baris (diskon
        # CMI ada di header, apply_discount_on="Net Total").
        #
        # Kalau tidak dibersihkan: saat user MENAIKKAN kurs, client core (transaction.js)
        # melihat rate baru > price_list_rate LAMA lalu mengira user menaikkan harga manual,
        # dan menandai margin_type="Amount", margin_rate_or_amount = rate_baru - plr_lama.
        # Server lalu menyamakan plr = rate, tapi calculate_margin core tetap memakai margin
        # basi itu -> rate = plr + margin = HAMPIR DUA KALI LIPAT. Hanya terjadi saat kurs
        # dinaikkan, itu sebabnya gejalanya terasa acak.
        it.margin_type = ""
        it.margin_rate_or_amount = 0
        it.rate_with_margin = 0
        it.base_rate_with_margin = 0
        it.discount_percentage = 0
        it.discount_amount = 0


def _apply_debit_to(doc):
    """Isi Debit To (piutang) di SERVER kalau kosong.

    Form sudah mengisinya saat onload (cmi_fill_required_accounts), tapi itu tidak menolong
    dokumen lama/impor yang disimpan lewat API, bulk edit, atau form yang keburu di-save
    sebelum isian jalan — gagalnya cuma "Mandatory fields required in Sales Invoice".
    Akunnya dari ERPNext sendiri: Party Account customer dulu, baru default Company.
    """
    if doc.get("debit_to") or not (doc.get("customer") and doc.get("company")):
        return
    from erpnext.accounts.party import get_party_account

    acc = get_party_account("Customer", doc.customer, doc.company)
    if not acc:
        frappe.throw(_(
            "Akun piutang (<b>Debit To</b>) belum di-set. Isi <b>Default Receivable Account</b> "
            "di Company <b>{0}</b>, atau Accounts di master Customer <b>{1}</b>."
        ).format(doc.company, doc.customer))
    doc.debit_to = acc


def before_validate(doc, method=None):
    _apply_smart_inputs(doc)  # field gabungan "10%"/"50000" -> percent/amount tersembunyi
    _apply_item_currency(doc)  # currency/rate per item -> rate core (mata uang header); SEBELUM calc
    sync_header_address(doc)
    _clear_unused_tables(doc)  # WAJIB sebelum hitung total (total ikut state bersih)
    _sync_reimburse_items(doc)  # Reimburse Items -> baris `items` (sebelum income account)
    _sync_shipping_list_nos(doc)  # kolom list view Shipping List (koma kalau >1)
    _apply_type_income_account(doc)  # Cr account tiap item dari Default Account tipe invoice
    _apply_debit_to(doc)  # Db piutang: dokumen lama/impor sering kosong

    # Status Customer Paid DITURUNKAN dari Paid Date (checkbox-nya hidden). Kalau user salah
    # isi, cukup KOSONGKAN Paid Date -> status kembali belum dibayar.
    doc.custom_customer_paid = 1 if doc.get("custom_paid_date") else 0
    # Watermark PAID hanya boleh hidup selama invoice memang berstatus paid.
    if not doc.custom_customer_paid:
        doc.custom_watermark_paid = 0

    # Invoice TANPA item (mis. Reimburse — nilainya di custom_reimburse_items, tabel Items
    # sengaja kosong) bikin ERPNext `set_total_in_words` crash: abs(base_rounded_total=None).
    # Matikan rounded total → pakai base_grand_total (0) yang aman. Item juga tidak wajib.
    if not (doc.get("items") or []):
        doc.disable_rounded_total = 1

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

    # Reimburse: PPN yang dulu dibayar ke vendor diteruskan ke customer. Akunnya SAMA
    # dengan yang didebit Expense Note, jadi kreditnya di sini menutup PPN Masukan itu
    # (pass-through: PPN vendor tidak dikreditkan perusahaan).
    reimb_ppn = sum(
        flt(r.get("tax")) * flt(r.get("rate") or 1)
        for r in (doc.get("custom_reimburse_items") or [])
        if r.get("expense_note")
    )
    if flt(reimb_ppn):
        add_amt(_need(_reimburse_tax_account(), "PPN (Masukan) di Expense Note Settings"),
                REIMBURSE_TAX_DESC, reimb_ppn, 1)


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

    # Reimburse: net_total = amount + tax (PPN) per class; line_amount = net_total * rate.
    reimb_total = 0.0
    for r in (doc.get("custom_reimburse_items") or []):
        r.net_total = flt(r.amount) + flt(r.tax)
        r.line_amount = flt(r.net_total) * flt(r.rate or 1)
        reimb_total += flt(r.line_amount)
    # Nilainya kini SUDAH masuk total/grand_total core lewat baris `items` + baris pajak
    # turunan (_sync_reimburse_items) — menambahkannya lagi di sini berarti dobel.
    if doc.get("custom_invoice_behavior") == "Reimburse":
        reimb_total = 0.0

    # Debit Note (tabel manual): amount = qty * price.
    dn_total = 0.0
    for r in (doc.get("custom_dn_items") or []):
        r.amount = flt(r.qty) * flt(r.price)
        dn_total += flt(r.amount)

    doc.custom_amount_total = total + reimb_total + dn_total
    doc.custom_net_total = (
        flt(doc.get("grand_total")) + reimb_total + dn_total + flt(doc.get("custom_adjustment"))
    )


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
    return ".custom_invoice_type_no./.####./%s/.YY." % _company_code(doc.get("company"))


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
        # Field yang tampil di sidebar print view. Semuanya setelan PRINT — sengaja tidak
        # ditampilkan di form invoice; nilainya persisten per-dokumen (lihat
        # public/js/print_view.js yang men-seed dari dokumen & menyimpan balik saat Print).
        #
        # get_print_settings_to_show memanggil method ini PADA DOKUMENNYA (bukan class),
        # jadi kondisi per-dokumen bisa dievaluasi di sini.
        fields = super().get_print_settings() or []
        fields += ["invoice_title", "print_as_currency", "printed_by", "branch_office"]
        # Watermark PAID hanya relevan kalau invoice memang sudah dibayar customer.
        if self.get("custom_customer_paid"):
            fields.append("watermark_paid")
        return fields

    def set_total_in_words(self):
        # Invoice TANPA item (Reimburse) bisa punya total None -> ERPNext abs(None) crash
        # (selling_controller.set_total_in_words). Coalesce None -> 0 dulu.
        for f in ("base_grand_total", "base_rounded_total", "grand_total", "rounded_total",
                  "base_net_total", "net_total", "base_total", "total"):
            if self.get(f) is None:
                self.set(f, 0)
        return super().set_total_in_words()

    def make_gl_entries(self, *args, **kwargs):
        if self.get("dont_post_to_gl"):
            return
        return super().make_gl_entries(*args, **kwargs)

    def get_gl_dict(self, args, account_currency=None, item=None):
        """Ledger per BARIS ITEM, dan setiap baris punya cost center.

        ERPNext menggabungkan baris ledger dengan akun+cost center yang sama
        (SalesInvoice.get_gl_entries -> merge_similar_entries), jadi 4 baris invoice yang
        akunnya sama muncul cuma 1 baris berisi totalnya di ledger — tidak bisa dicocokkan
        balik ke barisnya. `_skip_merge` adalah bendera bawaan ERPNext untuk itu (dipakai
        sendiri oleh Purchase Invoice), jadi tidak ada logika merge yang perlu ditiru.
        Baris pajak sengaja TIDAK ikut dipecah: pajaknya memang satu per akun.
        """
        gl_dict = super().get_gl_dict(args, account_currency, item)
        if item is not None and item.get("doctype") == "Sales Invoice Item":
            gl_dict["_skip_merge"] = True
        return fill_cost_center(self, gl_dict, item)

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)


@frappe.whitelist()
def get_reimburse_expense_notes(customer, currency=None, current_invoice=None):
    """Expense Note reimburse untuk picker "Get Expense Notes" -> di-EXPLODE per Expense Class.

    Satu Expense Note punya banyak item, tiap item ber-expense_class; jadi satu EN bisa
    banyak class. Amount & tax (PPN) dijumlah PER (EN, expense_class) → satu baris per
    class: amount, tax, net_total = amount + tax. Tiap baris membawa `status`:
      - "ready"       : EN tervalidasi & belum ditarik → bisa dipilih.
      - "outstanding" : EN BELUM divalidasi (maks 50 EN terbaru) → tampil READ-ONLY
                        sebagai info "masih outstanding", tidak bisa dipilih.

    Filter EN: is_reimburse=1, belum void, currency cocok, reimburse_to_customer cocok
    dgn customer invoice (best-effort by NAME). Pemakaian (Reimburse Item) dari invoice
    LAIN saja yang mengecualikan — baris milik `current_invoice` diabaikan supaya baris
    yang baru dihapus user dari grid (belum tersimpan) langsung bisa ditarik lagi.
    Kunci pengecualian = (Expense Note, Expense Class): class A sudah ditagih ≠ class B
    ikut hilang.
    """
    used_filters = {}
    if current_invoice:
        used_filters["parent"] = ["!=", current_invoice]
    used = {
        (r.expense_note, r.expense_class)
        for r in frappe.get_all(
            "Sales Invoice Reimburse", filters=used_filters, fields=["expense_note", "expense_class"]
        )
    }

    base = {"is_reimburse": 1, "void": ["!=", 1]}
    if currency:
        base["currency"] = currency
    # reimburse_to_customer = CRM Organization; cocokkan by nama customer (best-effort).
    cust_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    base["reimburse_to_customer"] = ["in", list({customer, cust_name})]

    en_fields = ["name", "date", "ref", "currency", "remark",
                 "shipping_list", "packing_list", "bl_no", "validated"]
    ready = frappe.get_all("Expense Note", filters={**base, "validated": 1}, fields=en_fields)
    # Outstanding (belum validate): info saja, dibatasi 50 EN terbaru supaya ringan.
    outstanding = frappe.get_all(
        "Expense Note", filters={**base, "validated": 0}, fields=en_fields,
        order_by="modified desc", limit_page_length=50,
    )

    ens = ready + outstanding
    if not ens:
        return []
    # SATU query agregat untuk semua EN (bukan query per-EN — berat kalau EN banyak).
    sums = frappe.db.sql(
        """SELECT parent, expense_class, SUM(amount) AS amount, SUM(tax) AS tax
           FROM `tabExpense Note Item` WHERE parent IN %(names)s
           GROUP BY parent, expense_class ORDER BY parent, expense_class""",
        {"names": [e["name"] for e in ens]},
        as_dict=True,
    )
    by_en = {}
    for s in sums:
        by_en.setdefault(s.parent, []).append(s)

    out = []
    for en in ens:
        status = "ready" if en.get("validated") else "outstanding"
        for c in by_en.get(en["name"], []):
            if (en["name"], c.get("expense_class")) in used:
                continue
            amt = flt(c.get("amount"))
            tax = flt(c.get("tax"))
            out.append({
                "expense_note": en["name"],
                "expense_class": c.get("expense_class"),
                "amount": amt,
                "tax": tax,
                "net_total": amt + tax,
                "currency": en.get("currency"),
                "document_date": en.get("date"),
                "document_no_fp": en.get("ref"),
                "note": en.get("remark"),
                "shipping_list": en.get("shipping_list"),
                "packing_list": en.get("packing_list"),
                "bl_no": en.get("bl_no"),
                "status": status,
            })
    return out


@frappe.whitelist()
def get_reimburse_connection(expense_notes):
    """Sumber Connection dari Expense Note terpilih: Shipping/Packing List, BL No, containers.

    Dipakai invoice Reimburse supaya tab Connection otomatis tertaut ke Master Job asal
    biayanya. Kalau EN menunjuk sumber berbeda-beda, yang dipakai adalah yang PERTAMA
    ditemukan (satu invoice hanya punya satu shipping/packing list + satu BL).
    Containers digabung dari semua EN, dedup per (source_name, container_no).
    """
    names = frappe.parse_json(expense_notes) if isinstance(expense_notes, str) else (expense_notes or [])
    out = {"shipping_list": None, "packing_list": None, "bl_no": None, "containers": []}
    seen = set()
    for en_name in names:
        en = frappe.db.get_value(
            "Expense Note", en_name, ["shipping_list", "packing_list", "bl_no"], as_dict=True
        )
        if not en:
            continue
        out["shipping_list"] = out["shipping_list"] or en.get("shipping_list")
        out["packing_list"] = out["packing_list"] or en.get("packing_list")
        out["bl_no"] = out["bl_no"] or en.get("bl_no")

        src_name = en.get("shipping_list") or en.get("packing_list")
        src_doctype = "Shipping List" if en.get("shipping_list") else ("Packing List" if en.get("packing_list") else None)
        if not src_name:
            continue
        for c in frappe.get_all(
            "Expense Note Container",
            filters={"parent": en_name},
            fields=["container_no", "seal_no", "container_size", "customer"],
        ):
            key = (src_name, c.get("container_no") or "")
            if key in seen:
                continue
            seen.add(key)
            out["containers"].append({
                "source_doctype": src_doctype,
                "source_name": src_name,
                "bl_no": en.get("bl_no"),
                "container_no": c.get("container_no"),
                "seal_no": c.get("seal_no"),
                "container_size": c.get("container_size"),
                "customer": c.get("customer"),
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

"""Setup erpnext_custom — kustomisasi core Sales Invoice (tanpa edit erpnext core).

INVOICE_FIELDS   = custom field yang ditambahkan (header + amounts + audit + item).
HIDE_FIELDS      = field/section bawaan yang disembunyikan.
RELABEL/DEFAULTS = ubah label/default field bawaan.
INVOICE_AUTONAME = pola nomor invoice (mengikuti field custom_invoice_type_no).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "ERPNext Custom"

# Nomor invoice mengikuti InvoiceTypeNo (C/E, C/EA, T/E, C/T, IR):
#   C/E -> C/E/00001/CMI/26 . Counter per-kode (mengakumulasi prefix; JANGAN "format:").
INVOICE_AUTONAME = ".custom_invoice_type_no./.####./CMI/.YY."

# Awali "\n" supaya mulai KOSONG (user harus memilih, tidak default ke opsi pertama).
INVOICE_TYPE_OPT = "\nExpedition\nDepo\nTrading\nReimburse\nDebit Note"
INVOICE_TYPE_NO_OPT = "\nC/E\nC/EA\nT/E\nC/T\nIR\nDN"
UNIT_OPT = "%\nRp"


def _f(**kw):
    kw.setdefault("module", MODULE)
    return kw


INVOICE_FIELDS = {
    "Sales Invoice": [
        # ---------- Header: alamat customer (kolom 2, di samping Customer) ----------
        # Dulu Custom Field "yatim" (ada di DB, tidak dikelola install.py) -> sekarang dikelola.
        _f(fieldname="custom_customer_address", fieldtype="Link", label="Customer Address", options="Address",
           reqd=1, insert_after="column_break1",
           description="Alamat customer untuk invoice ini (dipakai Invoice Print Out)."),
        _f(fieldname="custom_address_display", fieldtype="Small Text", label="Address", read_only=1,
           insert_after="custom_customer_address"),

        # ---------- Section "Invoice" — 3 kolom ----------
        # Baris: 1) Type | Type No | Input Mode   2) Invoice Date | Due Date | Term Date
        #        3) Return Date | Voyage No | Don't Post to GL   4) Payment Term | Delivery Term
        # NB: Currency & Exchange Rate adalah field CORE — tidak bisa dipindah ke section ini
        # (Custom Field insert_after hanya memposisikan custom field). Tetap di section aslinya.
        _f(fieldname="custom_detail_sb", fieldtype="Section Break", label="Invoice", insert_after="customer"),
        _f(fieldname="custom_invoice_type", fieldtype="Select", label="Invoice Type", options=INVOICE_TYPE_OPT, reqd=1, insert_after="custom_detail_sb"),
        _f(fieldname="invoice_date", fieldtype="Date", label="Invoice Date", reqd=1, default="Today", insert_after="custom_invoice_type"),
        _f(fieldname="custom_return_date", fieldtype="Date", label="Return Date", insert_after="invoice_date"),
        _f(fieldname="custom_payment_term", fieldtype="Data", label="Payment Term", insert_after="custom_return_date",
           description='Syarat pembayaran, mis. "Net 30", "Cash", "TT".'),
        _f(fieldname="custom_detail_cb", fieldtype="Column Break", insert_after="custom_payment_term"),
        _f(fieldname="custom_invoice_type_no", fieldtype="Select", label="Invoice Type No", options=INVOICE_TYPE_NO_OPT, reqd=1, insert_after="custom_detail_cb"),
        _f(fieldname="term_of_payment", fieldtype="Date", label="Due Date", insert_after="custom_invoice_type_no"),
        _f(fieldname="custom_voyage_no", fieldtype="Data", label="Voyage No", insert_after="term_of_payment"),
        _f(fieldname="custom_delivery_term", fieldtype="Data", label="Delivery Term", insert_after="custom_voyage_no",
           description='Syarat penyerahan / incoterm, mis. "CIF", "FOB", "DDP".'),
        _f(fieldname="custom_detail_cb2", fieldtype="Column Break", insert_after="custom_delivery_term"),
        _f(fieldname="custom_dn_input_mode", fieldtype="Select", label="Input Mode", options="\nItem\nManual",
           depends_on="eval:doc.custom_invoice_type=='Debit Note'",
           mandatory_depends_on="eval:doc.custom_invoice_type=='Debit Note'", insert_after="custom_detail_cb2",
           description="Debit Note: pilih pakai tabel Item (pilih dari master) atau tabel Manual (isi bebas)."),
        _f(fieldname="custom_term_date", fieldtype="Date", label="Term Date", insert_after="custom_dn_input_mode"),
        _f(fieldname="dont_post_to_gl", fieldtype="Check", label="Don't Post to GL", insert_after="custom_term_date"),

        # ---------- Section "Customer Paid" — 3 kolom ----------
        # Checkbox di-HIDE (tidak perlu); statusnya diturunkan dari Paid Date (lihat before_validate).
        # Field-nya EDITABLE supaya user bisa mengosongkan tanggal kalau salah isi.
        _f(fieldname="custom_paid_sb", fieldtype="Section Break", label="Customer Paid", insert_after="dont_post_to_gl", collapsible=1),
        _f(fieldname="custom_customer_paid", fieldtype="Check", label="Customer Paid", read_only=1, hidden=1, insert_after="custom_paid_sb"),
        # read_only=0 WAJIB eksplisit: create_custom_fields TIDAK menghapus properti yang
        # dihilangkan dari definisi (field ini dulunya read_only=1).
        _f(fieldname="custom_paid_date", fieldtype="Date", label="Paid Date", read_only=0, insert_after="custom_customer_paid"),
        _f(fieldname="custom_paid_cb1", fieldtype="Column Break", insert_after="custom_paid_date"),
        _f(fieldname="custom_paid_note", fieldtype="Small Text", label="Notes", read_only=0, insert_after="custom_paid_cb1"),
        _f(fieldname="custom_paid_cb2", fieldtype="Column Break", insert_after="custom_paid_note"),
        _f(fieldname="custom_paid_attachment", fieldtype="Attach", label="Paid Attachment", read_only=0, insert_after="custom_paid_cb2"),

        # ---------- Section "Print" — 2 kolom (dulu Custom Field "yatim") ----------
        _f(fieldname="custom_print_sb", fieldtype="Section Break", label="Print", insert_after="custom_paid_attachment"),
        _f(fieldname="custom_print_as_currency", fieldtype="Link", label="Print As Currency", options="Currency", insert_after="custom_print_sb"),
        _f(fieldname="custom_print_cb", fieldtype="Column Break", insert_after="custom_print_as_currency"),
        _f(fieldname="custom_printed_by", fieldtype="Link", label="Printed By", options="User", insert_after="custom_print_cb"),
        _f(fieldname="custom_invoice_title", fieldtype="Data", label="Invoice Title", default="INVOICE",
           allow_on_submit=1, insert_after="custom_printed_by",
           description='Judul print out terakhir (otomatis tersimpan saat tombol Print ditekan, mis. "DEBIT NOTE").'),

        # ---------- Section "Tax" ----------
        _f(fieldname="custom_tax_sb", fieldtype="Section Break", label="Tax", insert_after="custom_invoice_title"),
        _f(fieldname="custom_tax_no", fieldtype="Data", label="Tax No", insert_after="custom_tax_sb"),

        # ---------- Reimburse (muncul saat InvoiceType = Reimburse) ----------
        _f(fieldname="custom_reimburse_sb", fieldtype="Section Break", label="Reimburse", insert_after="items", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),
        _f(fieldname="custom_get_expense_notes", fieldtype="Button", label="Get Expense Notes", insert_after="custom_reimburse_sb", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),
        _f(fieldname="custom_reimburse_items", fieldtype="Table", label="Reimburse Items", options="Reimburse Item", insert_after="custom_get_expense_notes", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),

        # ---------- Debit Note - tabel Manual (muncul saat Type=Debit Note & Input Mode=Manual) ----------
        _f(fieldname="custom_dn_sb", fieldtype="Section Break", label="Debit Note Items", insert_after="custom_reimburse_items",
           depends_on="eval:doc.custom_invoice_type=='Debit Note' && doc.custom_dn_input_mode=='Manual'"),
        _f(fieldname="custom_dn_items", fieldtype="Table", label="Debit Note Items", options="Debit Note Item", insert_after="custom_dn_sb",
           depends_on="eval:doc.custom_invoice_type=='Debit Note' && doc.custom_dn_input_mode=='Manual'"),

        # ---------- Amounts (bagian dari section "Items") ---------- (setelah native total)
        # Section break TANPA label supaya tampil menyatu di bawah tabel Items.
        _f(fieldname="custom_amount_sb", fieldtype="Section Break", label="", insert_after="total"),
        _f(fieldname="custom_amount_total", fieldtype="Currency", label="Amount Total", options="currency", read_only=1, insert_after="custom_amount_sb"),
        _f(fieldname="custom_row_in_sb", fieldtype="Section Break", insert_after="custom_amount_total"),
        _f(fieldname="custom_discount_input", fieldtype="Data", label="Discount",
           description='Ketik mis. "10%" atau "50000"', insert_after="custom_row_in_sb"),
        _f(fieldname="custom_discount_percent", fieldtype="Percent", label="Discount %", hidden=1, insert_after="custom_discount_input"),
        _f(fieldname="custom_discount_amount", fieldtype="Currency", label="Discount Amount", options="currency", read_only=1, hidden=1, insert_after="custom_discount_percent"),
        _f(fieldname="custom_cb_a1", fieldtype="Column Break", insert_after="custom_discount_amount"),
        _f(fieldname="custom_pph_input", fieldtype="Data", label="PPh",
           description='Ketik mis. "2%" atau "50000"', insert_after="custom_cb_a1"),
        _f(fieldname="custom_pph_percent", fieldtype="Percent", label="PPh %", hidden=1, insert_after="custom_pph_input"),
        _f(fieldname="custom_pph_amount", fieldtype="Currency", label="PPh Amount", options="currency", read_only=1, hidden=1, insert_after="custom_pph_percent"),
        _f(fieldname="custom_cb_a2", fieldtype="Column Break", insert_after="custom_pph_amount"),
        _f(fieldname="custom_tax_input", fieldtype="Data", label="Tax",
           description='Ketik mis. "11%" atau "50000"', insert_after="custom_cb_a2"),
        _f(fieldname="custom_tax_percent", fieldtype="Percent", label="Tax %", hidden=1, insert_after="custom_tax_input"),
        _f(fieldname="custom_tax_amount", fieldtype="Currency", label="Tax Amount", options="currency", read_only=1, hidden=1, insert_after="custom_tax_percent"),
        _f(fieldname="custom_cb_a3", fieldtype="Column Break", insert_after="custom_tax_amount"),
        _f(fieldname="custom_materai", fieldtype="Currency", label="Materai", options="currency", insert_after="custom_cb_a3"),
        _f(fieldname="custom_adjustment", fieldtype="Currency", label="Adjustment", options="currency", insert_after="custom_materai"),
        # Baris 3: Ignore Tax
        _f(fieldname="custom_row_ign_sb", fieldtype="Section Break", insert_after="custom_adjustment"),
        _f(fieldname="custom_ignore_tax", fieldtype="Check", label="Ignore Tax", insert_after="custom_row_ign_sb"),
        # Baris 4: Net Total
        _f(fieldname="custom_row_net_sb", fieldtype="Section Break", insert_after="custom_ignore_tax"),
        _f(fieldname="custom_net_total", fieldtype="Currency", label="Net Total", options="currency", read_only=1, bold=1, insert_after="custom_row_net_sb"),

        # ---------- Section "Remark" — full width (+ attach), lalu audit read-only ----------
        _f(fieldname="custom_other_sb", fieldtype="Section Break", label="Remark", insert_after="custom_net_total"),
        _f(fieldname="custom_remarks", fieldtype="Small Text", label="Remarks", insert_after="custom_other_sb"),
        _f(fieldname="custom_attachment", fieldtype="Attach", label="Attachment", insert_after="custom_remarks"),
        _f(fieldname="custom_validated_by", fieldtype="Data", label="Validated By", read_only=1, insert_after="custom_attachment"),
        _f(fieldname="custom_voided_by", fieldtype="Data", label="Voided By", read_only=1, insert_after="custom_validated_by"),

        # ---------- Connection (PL/SL -> BL -> Container) ----------
        _f(fieldname="custom_connection_tab", fieldtype="Tab Break", label="Connection", insert_after="custom_voided_by"),
        _f(fieldname="custom_conn_source_sb", fieldtype="Section Break", label="Source Documents", insert_after="custom_connection_tab"),
        _f(fieldname="custom_packing_list", fieldtype="Link", label="Packing List", options="Packing List", insert_after="custom_conn_source_sb"),
        _f(fieldname="custom_conn_cb", fieldtype="Column Break", insert_after="custom_packing_list"),
        _f(fieldname="custom_shipping_list", fieldtype="Link", label="Shipping List", options="Shipping List", insert_after="custom_conn_cb"),
        _f(fieldname="custom_reuse_master_job", fieldtype="Check", label="Re Use Master Job", insert_after="custom_shipping_list",
           description="Tampilkan kembali Master Job (Shipping/Packing List) yang sudah punya invoice, beserta semua containernya."),
        _f(fieldname="custom_bl_sb", fieldtype="Section Break", label="Bill of Lading", insert_after="custom_reuse_master_job"),
        _f(fieldname="custom_bl_no", fieldtype="Select", label="BL No", insert_after="custom_bl_sb",
           description="Pilih sumber dulu (Packing List / Shipping List); nomor BL terisi otomatis."),
        _f(fieldname="custom_containers_sb", fieldtype="Section Break", label="Containers", insert_after="custom_bl_no"),
        _f(fieldname="custom_reload_containers", fieldtype="Button", label="Reload Containers", insert_after="custom_containers_sb"),
        _f(fieldname="custom_pick_containers", fieldtype="Button", label="Pilih Containers (modal)", insert_after="custom_reload_containers",
           depends_on="eval:doc.custom_invoice_type && doc.custom_invoice_type!='Trading' && doc.custom_invoice_type!='Reimburse'"),
        _f(fieldname="custom_containers", fieldtype="Table", label="Containers", options="Invoice Container", insert_after="custom_pick_containers"),

        # ---------- Kolom list view (hidden di form) ----------
        # custom_shipping_list_nos: nomor SL invoice ini, koma kalau lebih dari satu
        # (custom_shipping_list + SL milik tiap EN di Reimburse Items) — dihitung di
        # before_validate (overrides.sales_invoice._sync_shipping_list_nos).
        # created_by/assigned_to: kosong; dirender dari owner/_assign oleh formatter
        # sales_invoice_list.js (mirror pola Expense Note).
        _f(fieldname="custom_shipping_list_nos", fieldtype="Data", label="Shipping List",
           read_only=1, hidden=1, in_list_view=1, allow_on_submit=1, insert_after="custom_containers"),
        _f(fieldname="custom_created_by", fieldtype="Data", label="Created By",
           read_only=1, hidden=1, in_list_view=1, insert_after="custom_shipping_list_nos"),
        _f(fieldname="custom_assigned_to", fieldtype="Data", label="Assign To",
           read_only=1, hidden=1, in_list_view=1, insert_after="custom_created_by"),

        # ---------- Assistant + Email (terhubung ke agent yang handle job ini) ----------
        _f(fieldname="custom_tab_assistant", fieldtype="Tab Break", label="Assistant", insert_after="custom_assigned_to"),
        _f(fieldname="custom_assistant_html", fieldtype="HTML", label="Assistant", insert_after="custom_tab_assistant"),
        _f(fieldname="custom_tab_email", fieldtype="Tab Break", label="Email", insert_after="custom_assistant_html"),
        _f(fieldname="custom_email_html", fieldtype="HTML", label="Email", insert_after="custom_tab_email"),
    ],
    "Company": [
        _f(fieldname="custom_company_code", fieldtype="Data", label="Code (for numbering)", insert_after="abbr",
           description="Kode perusahaan untuk penomoran, mis. CMI."),
    ],
}

# ===== Purchase Order & Purchase Invoice (strip + custom, mirror Sales Invoice) =====
# Penomoran: seri sederhana (tanpa taksonomi type) -> picker "Series" hilang.
PO_AUTONAME = "PO/.#####./CMI/.YY."
PI_AUTONAME = "PI/.#####./CMI/.YY."


def _assistant_tabs(insert_after="connections_tab"):
    # Tab Assistant + Email (shared dari app `agents`). Anchor di "connections_tab"
    # (tab native terakhir); kalau tidak ada, Frappe append di akhir.
    return [
        _f(fieldname="custom_tab_assistant", fieldtype="Tab Break", label="Assistant", insert_after=insert_after),
        _f(fieldname="custom_assistant_html", fieldtype="HTML", label="Assistant", insert_after="custom_tab_assistant"),
        _f(fieldname="custom_tab_email", fieldtype="Tab Break", label="Email", insert_after="custom_assistant_html"),
        _f(fieldname="custom_email_html", fieldtype="HTML", label="Email", insert_after="custom_tab_email"),
    ]


def _amounts_fields(after):
    # Section "Amounts" identik dgn Sales Invoice: field gabungan (Data, "10%"/"50000")
    # + storage tersembunyi (percent/amount, dikonsumsi server GL) + Net Total.
    return [
        _f(fieldname="custom_amount_sb", fieldtype="Section Break", label="Amounts", insert_after=after),
        _f(fieldname="custom_amount_total", fieldtype="Currency", label="Amount Total", options="currency", read_only=1, insert_after="custom_amount_sb"),
        _f(fieldname="custom_row_in_sb", fieldtype="Section Break", insert_after="custom_amount_total"),
        _f(fieldname="custom_discount_input", fieldtype="Data", label="Discount", description='Ketik mis. "10%" atau "50000"', insert_after="custom_row_in_sb"),
        _f(fieldname="custom_discount_percent", fieldtype="Percent", label="Discount %", hidden=1, insert_after="custom_discount_input"),
        _f(fieldname="custom_discount_amount", fieldtype="Currency", label="Discount Amount", options="currency", read_only=1, hidden=1, insert_after="custom_discount_percent"),
        _f(fieldname="custom_cb_a1", fieldtype="Column Break", insert_after="custom_discount_amount"),
        _f(fieldname="custom_pph_input", fieldtype="Data", label="PPh", description='Ketik mis. "2%" atau "50000"', insert_after="custom_cb_a1"),
        _f(fieldname="custom_pph_percent", fieldtype="Percent", label="PPh %", hidden=1, insert_after="custom_pph_input"),
        _f(fieldname="custom_pph_amount", fieldtype="Currency", label="PPh Amount", options="currency", read_only=1, hidden=1, insert_after="custom_pph_percent"),
        _f(fieldname="custom_cb_a2", fieldtype="Column Break", insert_after="custom_pph_amount"),
        _f(fieldname="custom_tax_input", fieldtype="Data", label="Tax", description='Ketik mis. "11%" atau "50000"', insert_after="custom_cb_a2"),
        _f(fieldname="custom_tax_percent", fieldtype="Percent", label="Tax %", hidden=1, insert_after="custom_tax_input"),
        _f(fieldname="custom_tax_amount", fieldtype="Currency", label="Tax Amount", options="currency", read_only=1, hidden=1, insert_after="custom_tax_percent"),
        _f(fieldname="custom_cb_a3", fieldtype="Column Break", insert_after="custom_tax_amount"),
        _f(fieldname="custom_materai", fieldtype="Currency", label="Materai", options="currency", insert_after="custom_cb_a3"),
        _f(fieldname="custom_row_ign_sb", fieldtype="Section Break", insert_after="custom_materai"),
        _f(fieldname="custom_ignore_tax", fieldtype="Check", label="Ignore Tax", insert_after="custom_row_ign_sb"),
        _f(fieldname="custom_row_net_sb", fieldtype="Section Break", insert_after="custom_ignore_tax"),
        _f(fieldname="custom_net_total", fieldtype="Currency", label="Net Total", options="currency", read_only=1, bold=1, insert_after="custom_row_net_sb"),
    ]


def _audit_fields(after):
    return [
        _f(fieldname="custom_other_sb", fieldtype="Section Break", label="Remark & Audit", insert_after=after),
        _f(fieldname="custom_remarks", fieldtype="Small Text", label="Remarks", insert_after="custom_other_sb"),
        _f(fieldname="custom_attachment", fieldtype="Attach", label="Attachment", insert_after="custom_remarks"),
        _f(fieldname="custom_audit_cb", fieldtype="Column Break", insert_after="custom_attachment"),
        _f(fieldname="custom_validated_by", fieldtype="Data", label="Validated By", read_only=1, insert_after="custom_audit_cb"),
        _f(fieldname="custom_voided_by", fieldtype="Data", label="Voided By", read_only=1, insert_after="custom_validated_by"),
    ]


def _detail_fields(extra=None):
    out = [
        _f(fieldname="custom_detail_sb", fieldtype="Section Break", label="Detail", insert_after="supplier"),
        _f(fieldname="custom_voyage_no", fieldtype="Data", label="Voyage No", insert_after="custom_detail_sb"),
        _f(fieldname="custom_tax_no", fieldtype="Data", label="Tax No", insert_after="custom_voyage_no"),
        _f(fieldname="custom_detail_cb", fieldtype="Column Break", insert_after="custom_tax_no"),
        _f(fieldname="custom_adjustment", fieldtype="Currency", label="Adjustment", options="currency", insert_after="custom_detail_cb"),
    ]
    return out + (extra or [])


PURCHASE_FIELDS = {
    "Purchase Order": (
        _detail_fields()
        + _amounts_fields("total")
        + _audit_fields("custom_net_total")
        + _assistant_tabs()
    ),
    "Purchase Invoice": (
        _detail_fields(extra=[
            _f(fieldname="dont_post_to_gl", fieldtype="Check", label="Don't Post to GL", insert_after="custom_adjustment"),
        ])
        + _amounts_fields("total")
        + _audit_fields("custom_net_total")
        + _assistant_tabs()
    ),
}

# Field bawaan PO/PI yang disembunyikan: totals/taxes native (diganti Amounts custom),
# diskon native, pajak. Konservatif dulu (sisanya bisa ditambah setelah dilihat).
HIDE_PURCHASE_COMMON = [
    "naming_series",
    "total_qty", "base_total", "base_net_total", "total", "net_total",
    "taxes_and_charges", "tax_category", "taxes",
    "total_taxes_and_charges", "base_total_taxes_and_charges",
    "grand_total", "base_grand_total", "rounding_adjustment", "base_rounding_adjustment",
    "rounded_total", "base_rounded_total", "in_words", "base_in_words", "disable_rounded_total",
    "apply_discount_on", "additional_discount_percentage", "discount_amount",
    "base_discount_amount", "other_charges_calculation",
]
HIDE_PO = HIDE_PURCHASE_COMMON + []
HIDE_PI = HIDE_PURCHASE_COMMON + ["apply_tds", "tax_withholding_category"]


# Payment Entry — sembunyikan field bawaan yang berisik supaya form bersih (mirip
# SI/PO/PI). AMAN: field wajib yang diisi user TIDAK termasuk — payment_type, party_type,
# party, paid_from, paid_to, paid_amount, received_amount, source/target_exchange_rate
# tetap tampil. Hapus/ tambah fieldname lalu jalankan after_migrate untuk ubah.
HIDE_PAYMENT = [
    # header noise (auto-set)
    "naming_series", "company", "party_name", "title", "status",
    "book_advance_payments_in_separate_party_account", "contact_person", "contact_email",
    # duplikat company-currency + terbilang
    "base_paid_amount", "base_received_amount", "base_total_allocated_amount",
    "base_in_words", "in_words",
    # varian after-tax (fitur advance tax — tak dipakai)
    "paid_amount_after_tax", "base_paid_amount_after_tax",
    "received_amount_after_tax", "base_received_amount_after_tax",
    # account currency (domestik IDR, auto dari akun)
    "paid_from_account_currency", "paid_to_account_currency",
    # pajak / withholding (tak dipakai untuk pembayaran ekspedisi)
    "apply_tds", "tax_withholding_category", "tax_withholding_group",
    "ignore_tax_withholding_threshold", "override_tax_withholding_entries",
    "tax_withholding_entries", "purchase_taxes_and_charges_template",
    "sales_taxes_and_charges_template", "taxes",
    "total_taxes_and_charges", "base_total_taxes_and_charges",
    # potongan / write-off
    "deductions",
    # remarks bawaan dipindah ke section "Remark" paling bawah (custom_remark_note);
    # custom_remarks = flag ERPNext "jangan timpa remarks", diset server, bukan user.
    "remarks", "custom_remarks",
    # cek/giro, rekonsiliasi bank, lain-lain
    "clearance_date", "project", "cost_center", "is_opening",
    "letter_head", "print_heading", "bank", "bank_account_no",
    "payment_order", "payment_order_status", "auto_repeat",
]


# Payment Entry — SATU section "Items": tombol "Add Items" mengisi tabel custom_transactions
# dengan dokumen outstanding milik party —
#     Pay     -> Supplier: Expense Note (Validated) + Purchase Invoice + Debit Note (PI retur)
#     Receive -> Customer: Sales Invoice + Credit Note (SI retur)
# Server (before_validate) menurunkan baris References dari tabel ini saat Save (baris Expense
# Note -> reference Journal Entry). Lihat public/js/payment_entry.js + overrides/payment_entry.py.
#
# custom_en_sb / custom_get_expense_notes / custom_expense_notes = tabel LAMA (dulu Expense Note
# punya section & tombol sendiri). Di-HIDE, bukan dihapus: dokumen lama masih menyimpan barisnya.
PAYMENT_FIELDS = {
    "Payment Entry": [
        _f(fieldname="custom_en_sb", fieldtype="Section Break", label="Expense Note",
           insert_after="received_amount", hidden=1),
        _f(fieldname="custom_get_expense_notes", fieldtype="Button", label="Tarik Expense Note",
           insert_after="custom_en_sb", hidden=1),
        _f(fieldname="custom_expense_notes", fieldtype="Table", label="Expense Notes",
           options="Payment Entry Expense Note", insert_after="custom_get_expense_notes", hidden=1,
           description="Tabel lama (digantikan Items). Disimpan untuk dokumen lama."),
        _f(fieldname="custom_txn_sb", fieldtype="Section Break", label="Items",
           insert_after="custom_expense_notes",
           depends_on="eval:doc.party && !doc.custom_direct"),
        _f(fieldname="custom_get_transactions", fieldtype="Button", label="Add Items",
           insert_after="custom_txn_sb"),
        _f(fieldname="custom_transactions", fieldtype="Table", label="Items",
           options="Payment Entry Transaction", insert_after="custom_get_transactions",
           description="Pay: Expense Note, Purchase Invoice, Debit Note. Receive: Sales Invoice, Credit Note. Baris References dibuat otomatis saat Save."),
        # Remark paling bawah (setelah field terakhir bawaan). Native `remarks` di-hide
        # (HIDE_PAYMENT) — isinya diturunkan dari sini di before_validate.
        _f(fieldname="custom_remark_sb", fieldtype="Section Break", label="Remark",
           insert_after="auto_repeat"),
        _f(fieldname="custom_remark_note", fieldtype="Small Text", label="Remark",
           insert_after="custom_remark_sb"),
    ],
    # Tampilkan nomor Expense Note di grid References (baris JE turunan dari tabel di atas)
    # + penanda baris turunan tabel Transaksi (untuk rebuild saat Save).
    "Payment Entry Reference": [
        _f(fieldname="custom_expense_note", fieldtype="Link", label="Expense Note",
           options="Expense Note", read_only=1, in_list_view=1, columns=2,
           insert_after="reference_name"),
        _f(fieldname="custom_from_transaction", fieldtype="Check", label="From Transaction",
           hidden=1, insert_after="custom_expense_note"),
    ],
}

# Judul dokumen di print format "Invoice Print Out" — input di sidebar print view
# (mis. "DEBIT NOTE"). Field ini harus ada di Print Settings karena sidebar print
# membaca meta Print Settings (CMISalesInvoice.get_print_settings menambahkannya).
# NILAI singleton Print Settings-nya SENGAJA dibiarkan KOSONG: judul persisten
# disimpan per-dokumen di Sales Invoice.custom_invoice_title (diisi saat tombol
# Print ditekan — lihat public/js/print_view.js); template fallback:
# input sidebar > custom_invoice_title dokumen > "INVOICE".
PRINT_SETTINGS_FIELDS = {
    "Print Settings": [
        _f(fieldname="invoice_title", fieldtype="Data", label="Invoice Title",
           insert_after="print_taxes_with_zero_amount",
           description='Judul di print out invoice, mis. "INVOICE" atau "DEBIT NOTE".'),
    ],
}

# Master named by name (Supplier Name / Customer Name); legacy code disimpan terpisah
# di field non-unik (kode supplier bisa duplikat antar perusahaan).
MASTER_FIELDS = {
    "Supplier": [
        _f(fieldname="code", fieldtype="Data", label="Code", insert_after="supplier_name", in_list_view=1, in_standard_filter=1),
    ],
    "Customer": [
        _f(fieldname="code", fieldtype="Data", label="Code", insert_after="customer_name", in_list_view=1, in_standard_filter=1),
    ],
}

# branch_office (Link CMI Office) untuk akses berbasis branch (custom role-based, config
# 'CMI Branch Access'). Handler "*" di crm_cakra otomatis memfilter SETIAP doctype yang
# punya field ini. Diisi otomatis dari branch pembuat (set_branch_from_user via doc_events "*").
# Hanya doctype TRANSAKSI (master data tidak di-scope).
def _branch_field(anchor, read_only=0):
    return _f(fieldname="branch_office", fieldtype="Link", label="Branch Office", options="CMI Office",
              insert_after=anchor, read_only=read_only,
              description="Diisi otomatis dari branch pembuat; dipakai untuk akses berbasis branch.")


BRANCH_FIELDS = {
    "Sales Invoice":    [_branch_field("custom_printed_by")],
    # Payment Entry: branch SELALU dari branch user (tak boleh dipilih manual).
    "Payment Entry":    [_branch_field("company", read_only=1)],
    # Sales
    "Quotation":        [_branch_field("company")],
    "Sales Order":      [_branch_field("company")],
    "Delivery Note":    [_branch_field("company")],
    # Purchase
    "Purchase Order":   [_branch_field("company")],
    "Purchase Invoice": [_branch_field("company")],
    "Purchase Receipt": [_branch_field("company")],
    # Accounts / Stock
    "Journal Entry":    [_branch_field("company")],
    "Stock Entry":      [_branch_field("company")],
    "Material Request": [_branch_field("company")],
}

# Field bawaan yang disembunyikan (TAMPIL: customer, currency, conversion_rate(Rate),
# items + field custom kita). Hidden per-field (hide section break TIDAK sembunyiin isinya).
HIDE_FIELDS = [
    # header noise
    "company", "company_address", "company_tax_id", "naming_series",
    "customer_name", "tax_id",
    "posting_date", "posting_time", "set_posting_time", "due_date",
    # Kolom ke-3 header kosong (isinya cuma is_pos yg hidden) -> sembunyikan column break-nya
    # supaya header jadi 2 kolom: Customer | Customer Address + Address.
    "column_break_14",
    # Divider core kosong antara tabel Items dan blok Amounts -> sembunyikan supaya Amounts
    # tampak menyatu di bawah section "Items".
    "section_break_30",
    "is_pos", "pos_profile", "is_consolidated", "is_return", "return_against",
    "update_outstanding_for_self", "update_billed_amount_in_sales_order",
    "update_billed_amount_in_delivery_note", "is_debit_note", "apply_tds",
    "amended_from", "is_created_using_pos", "pos_closing_entry", "has_subcontracted",
    "title", "cost_center", "project",
    # price list (currency + conversion_rate TETAP tampil)
    "selling_price_list", "price_list_currency", "plc_conversion_rate", "ignore_pricing_rule",
    # items area noise
    "scan_barcode", "last_scanned_warehouse", "update_stock", "set_warehouse", "set_target_warehouse",
    # native totals/taxes (diganti field Amounts custom)
    "total_qty", "total_net_weight", "base_total", "base_net_total", "total", "net_total",
    "tax_category", "taxes_and_charges", "shipping_rule", "incoterm", "named_place", "taxes",
    "base_total_taxes_and_charges", "total_taxes_and_charges", "use_company_roundoff_cost_center",
    "grand_total", "in_words", "disable_rounded_total", "rounding_adjustment", "rounded_total",
    "base_grand_total", "base_in_words", "base_rounding_adjustment", "base_rounded_total",
    "total_advance", "outstanding_amount",
    "tax_withholding_group", "ignore_tax_withholding_threshold", "override_tax_withholding_entries",
    "apply_discount_on", "base_discount_amount", "coupon_code", "additional_discount_percentage",
    "discount_amount", "is_cash_or_non_trade_discount", "other_charges_calculation",
    "tax_withholding_entries", "pricing_rule_details", "pricing_rules", "packed_items",
    "product_bundle_help", "timesheets", "total_billing_hours", "total_billing_amount",
    # tab lain
    "payments_tab", "contact_and_address_tab", "terms_tab", "more_info_tab", "connections_tab",
]

# (doctype, fieldname, label)
RELABEL = [
    ("Sales Invoice", "conversion_rate", "Rate"),
    ("Sales Invoice Item", "rate", "Price"),
    ("Sales Invoice Item", "item_code", "Item Code"),
]
# (doctype, fieldname, default)
DEFAULTS = [
    ("Sales Invoice Item", "qty", "1"),
]
# (doctype, fieldname, property, value, property_type) -- kolom grid item
GRID = [
    ("Sales Invoice Item", "item_name", "in_list_view", "1", "Check"),
    ("Sales Invoice Item", "item_name", "columns", "2", "Int"),
    ("Sales Invoice Item", "warehouse", "in_list_view", "0", "Check"),
    ("Sales Invoice Item", "warehouse", "hidden", "1", "Check"),
    # Items disembunyikan saat InvoiceType = Reimburse (kebalikan dari tabel Reimburse).
    ("Sales Invoice", "items_section", "depends_on", "eval:doc.custom_invoice_type!='Reimburse'", "Data"),
    ("Sales Invoice", "items", "depends_on", "eval:doc.custom_invoice_type!='Reimburse'", "Data"),
]
# Custom field lama yang sudah tidak dipakai -> dihapus.
OBSOLETE = [
    # Layout lama: audit pindah ke section "Remark" (tanpa column break); Tax jadi 1 kolom.
    ("Sales Invoice", "custom_audit_cb"), ("Sales Invoice", "custom_tax_cb"),
    ("Sales Invoice", "type"), ("Sales Invoice", "custom_amount_cb"),
    ("Sales Invoice", "custom_discount_value"), ("Sales Invoice", "custom_discount_unit"),
    ("Sales Invoice", "custom_amount_tax_value"), ("Sales Invoice", "custom_amount_tax_unit"),
    ("Sales Invoice", "custom_amount_pph_value"), ("Sales Invoice", "custom_amount_pph_unit"),
    # Layout lama Amounts (kolom %/Amount terpisah) -> diganti field gabungan Discount/PPh/Tax.
    ("Sales Invoice", "custom_row_disc_sb"), ("Sales Invoice", "custom_cb_d1"),
    ("Sales Invoice", "custom_cb_d2"), ("Sales Invoice", "custom_cb_d3"),
    ("Sales Invoice", "custom_row_tax_sb"), ("Sales Invoice", "custom_cb_t1"),
    ("Sales Invoice", "custom_cb_t2"),
    # Re-Use Containers (di section Containers) -> diganti "Re Use Master Job" di section atas.
    ("Sales Invoice", "custom_reuse_containers"),
]


def _field_prop(doctype, fieldname, prop, value, property_type="Data"):
    name = frappe.db.exists(
        "Property Setter",
        {"doc_type": doctype, "field_name": fieldname, "property": prop},
    )
    ps = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
    ps.update({
        "doctype_or_field": "DocField",
        "doc_type": doctype,
        "field_name": fieldname,
        "property": prop,
        "property_type": property_type,
        "value": value,
        "module": MODULE,
    })
    ps.save(ignore_permissions=True)


def _hide(doctype, fieldname):
    _field_prop(doctype, fieldname, "hidden", "1", "Check")


def _reset_hidden(doctype):
    # Hapus semua property setter "hidden" milik app ini supaya HIDE_FIELDS otoritatif
    # (hapus field dari HIDE_FIELDS = field muncul lagi).
    for n in frappe.get_all(
        "Property Setter",
        filters={"doc_type": doctype, "module": MODULE, "property": "hidden"},
        pluck="name",
    ):
        frappe.delete_doc("Property Setter", n, ignore_permissions=True, force=True)


def _set_doctype_prop(doctype, prop, value, property_type="Data"):
    name = frappe.db.exists(
        "Property Setter",
        {"doc_type": doctype, "property": prop, "doctype_or_field": "DocType"},
    )
    ps = frappe.get_doc("Property Setter", name) if name else frappe.new_doc("Property Setter")
    ps.update({
        "doctype_or_field": "DocType",
        "doc_type": doctype,
        "property": prop,
        "property_type": property_type,
        "value": value,
        "module": MODULE,
    })
    ps.save(ignore_permissions=True)


def _seed_company_code():
    company = frappe.defaults.get_global_default("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    if company and not frappe.db.get_value("Company", company, "custom_company_code"):
        abbr = frappe.db.get_value("Company", company, "abbr") or "CMI"
        frappe.db.set_value("Company", company, "custom_company_code", abbr, update_modified=False)


def _drop_obsolete():
    for dt, fn in OBSOLETE:
        name = f"{dt}-{fn}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def _ensure_settlement_mode_of_payment():
    # Mode of Payment "Settlement" memicu mode settlement Payment Entry (sisi bank
    # diganti custom_settlement_account — lihat overrides/payment_entry.py). Sengaja
    # TANPA default account: akun dipilih user per transaksi.
    if not frappe.db.exists("Mode of Payment", "Settlement"):
        frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": "Settlement",
            "type": "General",
            "enabled": 1,
        }).insert(ignore_permissions=True)


INVOICE_ROLES = ("Invoice Validate", "Invoice Void")
SI_CLIENT_SCRIPT = "CMI Sales Invoice Loader"

# JANGAN set System Settings.date_format ke format nama bulan ("dd MMM yyyy").
# Sudah dicoba 2026-07-09 dan GAGAL: server OK (formatdate -> "22 Jun 2026", getdate parse balik
# OK) TAPI frontend rusak — datepicker & validasi input hanya paham format NUMERIK, sehingga
# semua input tanggal ditolak: "Date Invalid date must be in format: dd MMM yyyy".
# Opsi resmi Frappe cuma numerik: yyyy-mm-dd, dd-mm-yyyy, dd/mm/yyyy, dd.mm.yyyy, mm/dd/yyyy, mm-dd-yyyy.
# Untuk tampilan "22 Jun 2026" pakai format EKSPLISIT di tempat yang butuh, mis. di print format:
#   {{ frappe.utils.formatdate(doc.invoice_date, "dd MMM yyyy") }}   <- Invoice Print Out sudah begini.
DATE_FORMAT = "dd-mm-yyyy"


def _ensure_roles(names):
    """Buat role kalau belum ada (idempoten). Dipakai untuk gate Validate/Void."""
    for r in names:
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(
                ignore_permissions=True
            )


def _revoke_submit_cancel(doctype):
    """Cabut permission submit & cancel semua role di `doctype` (via Custom DocPerm).

    Submit hanya lewat tombol Validate (validate_invoice) & cancel lewat Void/Revisi —
    yang pakai ignore_permissions, jadi pencabutan ini hanya menyembunyikan tombol
    bawaan Submit/Cancel. Idempoten: setup_custom_perms menyalin standard->custom
    sekali, lalu submit/cancel di-nol-kan.
    """
    from frappe.permissions import setup_custom_perms

    setup_custom_perms(doctype)
    changed = False
    for p in frappe.get_all(
        "Custom DocPerm", filters={"parent": doctype}, fields=["name", "submit", "cancel"]
    ):
        if p.submit or p.cancel:
            frappe.db.set_value("Custom DocPerm", p.name, {"submit": 0, "cancel": 0})
            changed = True
    if changed:
        frappe.clear_cache(doctype=doctype)


def _remove_conflicting_naming_rules(doctype):
    """Hapus Document Naming Rule untuk `doctype`.

    Penomoran invoice di-handle controller (CMISalesInvoice.autoname, kode company
    dinamis dari abbr). Di `frappe.model.naming.set_new_name`, `Document Naming Rule`
    dievaluasi SEBELUM controller autoname — jadi kalau ada rule (mis. dibuat via UI
    "Document Naming Settings"), dia MENANG & nomor jatuh ke counter polos "00001".
    Rule apa pun untuk doctype ini bentrok dgn controller, jadi dihapus.
    """
    for name in frappe.get_all(
        "Document Naming Rule", filters={"document_type": doctype}, pluck="name"
    ):
        frappe.delete_doc("Document Naming Rule", name, force=1, ignore_permissions=True)


def _ensure_sales_invoice_client_script():
    """HAPUS Client Script "CMI Sales Invoice Loader" (kalau ada).

    Dulu sales_invoice.js di-embed ke Client Script karena dikira doctype_js tidak
    termuat (/assets/erpnext_custom 404). Diagnosis itu KELIRU: hook doctype_js
    disuntik server-side lewat form meta (__js), bukan lewat /assets — jadi script
    termuat DUA KALI dan semua handler jalan dobel (mis. tombol Get Expense Notes
    membuka dua modal bertumpuk). Loader dihapus; doctype_js satu-satunya sumber.
    """
    if frappe.db.exists("Client Script", SI_CLIENT_SCRIPT):
        frappe.delete_doc("Client Script", SI_CLIENT_SCRIPT, force=1, ignore_permissions=True)
        frappe.clear_cache(doctype="Sales Invoice")


def after_install():
    after_migrate()


def after_migrate():
    _drop_obsolete()
    create_custom_fields(INVOICE_FIELDS, ignore_validate=True)
    create_custom_fields(PURCHASE_FIELDS, ignore_validate=True)
    create_custom_fields(PAYMENT_FIELDS, ignore_validate=True)
    create_custom_fields(MASTER_FIELDS, ignore_validate=True)
    create_custom_fields(BRANCH_FIELDS, ignore_validate=True)
    create_custom_fields(PRINT_SETTINGS_FIELDS, ignore_validate=True)
    # Singleton Print Settings.invoice_title HARUS kosong: kalau terisi, ia menutupi
    # judul per-dokumen (custom_invoice_title) pada render tanpa sidebar (PDF/email).
    if frappe.db.get_single_value("Print Settings", "invoice_title"):
        frappe.db.set_single_value("Print Settings", "invoice_title", "")
    _seed_company_code()
    _ensure_settlement_mode_of_payment()
    _reset_hidden("Sales Invoice")
    for fn in HIDE_FIELDS:
        _hide("Sales Invoice", fn)
    # naming_series disembunyikan + autoname pakai format custom → matikan reqd-nya. Kalau
    # field hidden + reqd + tanpa default, Frappe v16 memaksa tampil sbg "Series" di doc baru.
    _field_prop("Sales Invoice", "naming_series", "reqd", "0", "Check")
    # Purchase Order / Purchase Invoice: hide native + autoname seri (mirror SI).
    for dt, hide_list in (("Purchase Order", HIDE_PO), ("Purchase Invoice", HIDE_PI)):
        _reset_hidden(dt)
        for fn in hide_list:
            _hide(dt, fn)
        _field_prop(dt, "conversion_rate", "label", "Rate", "Data")
    _set_doctype_prop("Purchase Order", "autoname", PO_AUTONAME)
    _set_doctype_prop("Purchase Order", "naming_rule", "Expression (old style)")
    _set_doctype_prop("Purchase Invoice", "autoname", PI_AUTONAME)
    _set_doctype_prop("Purchase Invoice", "naming_rule", "Expression (old style)")
    # Payment Entry: rapikan form (hide noise). _reset_hidden bikin HIDE_PAYMENT otoritatif.
    _reset_hidden("Payment Entry")
    for fn in HIDE_PAYMENT:
        _hide("Payment Entry", fn)
    for dt, fn, label in RELABEL:
        _field_prop(dt, fn, "label", label, "Data")
    for dt, fn, dflt in DEFAULTS:
        _field_prop(dt, fn, "default", dflt, "Data")
    for dt, fn, prop, val, pt in GRID:
        _field_prop(dt, fn, prop, val, pt)
    # autoname berbasis InvoiceTypeNo. PENTING: set juga naming_rule != 'By "Naming Series" field',
    # kalau tidak ERPNext `erpnext.toggle_naming_series()` tetap MEMUNCULKAN field "Series" di
    # dokumen baru (cek naming_rule, bukan autoname). "Expression (old style)" = cocok format titik.
    _set_doctype_prop("Sales Invoice", "autoname", INVOICE_AUTONAME)
    _set_doctype_prop("Sales Invoice", "naming_rule", "Expression (old style)")
    _set_doctype_prop("Sales Invoice", "default_print_format", "Invoice Print Out")
    # Tabel Items (produk) WAJIB, KECUALI Invoice Type = Reimburse (nilainya di
    # custom_reimburse_items, tabel Items sengaja kosong). mandatory_depends_on = hanya
    # wajib saat tabel produk dipakai (non-Reimburse).
    # Section tabel items sudah berlabel "Items" secara core (`items_section`) — JANGAN relabel
    # `section_break_42` (itu sub-divider di dalamnya; kalau diberi label jadi "Items" dobel).
    _field_prop("Sales Invoice", "items", "reqd", "0", "Check")
    _field_prop("Sales Invoice", "items", "mandatory_depends_on",
                'eval:doc.custom_invoice_type != "Reimburse" && doc.custom_invoice_type != "Debit Note"', "Small Text")
    # Tabel Items disembunyikan saat tipe tidak memakainya, supaya user tak sempat mengisi tabel
    # yang nanti dibuang saat save (_clear_unused_tables):
    #   Reimburse            -> pakai custom_reimburse_items
    #   Debit Note + Manual  -> pakai custom_dn_items
    #   Debit Note (mode blm dipilih) -> dua-duanya hidden (user HARUS pilih dulu)
    _field_prop("Sales Invoice", "items", "depends_on",
                'eval:doc.custom_invoice_type != "Reimburse" && '
                '(doc.custom_invoice_type != "Debit Note" || doc.custom_dn_input_mode == "Item")',
                "Small Text")
    # Matikan Quick Entry modal: dulu child-table wajib `items` otomatis memaksa form penuh;
    # setelah items non-wajib (utk Reimburse), Frappe malah munculkan modal Quick Entry.
    # quick_entry=0 -> "New Sales Invoice" selalu buka form penuh, bukan modal.
    _set_doctype_prop("Sales Invoice", "quick_entry", "0", "Check")
    # Dropdown Customer tampak dobel ("PT ABC / PT ABC / alamat"):
    #  - title_field=customer_name = SAMA dgn name (Customer dinamai by Customer Name) -> baris
    #    kedua duplikat. Customer.name sudah = customer_name, jadi title_field dikosongkan (aman).
    #  - primary_address di search_fields: baris pertama alamat sering = nama customer -> dobel lagi.
    # Hasil: dropdown bersih (nama + Customer Group + Territory).
    _set_doctype_prop("Customer", "title_field", "", "Data")
    _set_doctype_prop("Customer", "search_fields", "customer_group,territory,mobile_no", "Small Text")
    frappe.db.commit()  # kunci Property Setter penomoran DULU sebelum langkah opsional di bawah
    # Workflow Validate/Void: role + pencabutan submit/cancel + embed Client Script (DB-level,
    # tidak ikut git → disinkron di sini supaya `bench migrate` men-deploy-nya ke server).
    # NON-FATAL: kalau salah satu gagal (mis. path file beda / permission), JANGAN batalkan
    # migrate — kalau after_migrate throw, Frappe rollback dan Property Setter penomoran di atas
    # ikut hilang → invoice jadi bernomor polos "00001". Karena itu tiap langkah di-guard.
    for _label, _step in (
        ("remove_naming_rules", lambda: _remove_conflicting_naming_rules("Sales Invoice")),
        ("ensure_roles", lambda: _ensure_roles(INVOICE_ROLES)),
        ("revoke_submit_cancel", lambda: _revoke_submit_cancel("Sales Invoice")),
        ("client_script", _ensure_sales_invoice_client_script),
    ):
        try:
            _step()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="erpnext_custom after_migrate: %s failed" % _label)

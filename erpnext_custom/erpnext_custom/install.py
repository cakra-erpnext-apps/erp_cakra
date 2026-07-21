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
        # Behavior tipe (Normal/Reimburse/Debit Note) diturunkan dari config Selling Settings.
        # HIDDEN — semua depends_on & logika server membaca ini, bukan nama tipe (yang kini bebas).
        _f(fieldname="custom_invoice_behavior", fieldtype="Data", label="Invoice Behavior", read_only=1, hidden=1, no_copy=1, insert_after="custom_invoice_type"),
        # invoice_date = tanggal yang TAMPIL di print out (Invoice Print Out membacanya).
        # TIDAK allow_on_submit: setelah submit tanggal invoice tak boleh diubah.
        _f(fieldname="invoice_date", fieldtype="Date", label="Invoice Date", reqd=1, default="Today", insert_after="custom_invoice_behavior"),
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
           depends_on="eval:doc.custom_invoice_behavior=='Debit Note'",
           mandatory_depends_on="eval:doc.custom_invoice_behavior=='Debit Note'", insert_after="custom_detail_cb2",
           description="Debit Note: pilih pakai tabel Item (pilih dari master) atau tabel Manual (isi bebas)."),
        _f(fieldname="custom_term_date", fieldtype="Date", label="Term Date", insert_after="custom_dn_input_mode"),
        _f(fieldname="dont_post_to_gl", fieldtype="Check", label="Don't Post to GL", default="0", insert_after="custom_term_date"),

        # ---------- Section "Customer Paid" — 3 kolom ----------
        # Checkbox di-HIDE (tidak perlu); statusnya diturunkan dari Paid Date (lihat before_validate).
        # Field-nya EDITABLE supaya user bisa mengosongkan tanggal kalau salah isi.
        _f(fieldname="custom_paid_sb", fieldtype="Section Break", label="Customer Paid", insert_after="dont_post_to_gl", collapsible=1),
        # in_list_view: dipakai sebagai kolom "Paid" di list (dirender jadi Paid/Unpaid oleh
        # formatter di sales_invoice_list.js) — hidden=1 tidak menghalangi jadi kolom list.
        _f(fieldname="custom_customer_paid", fieldtype="Check", label="Paid", read_only=1, hidden=1,
           in_list_view=1, insert_after="custom_paid_sb"),
        # read_only=0 WAJIB eksplisit: create_custom_fields TIDAK menghapus properti yang
        # dihilangkan dari definisi (field ini dulunya read_only=1).
        _f(fieldname="custom_paid_date", fieldtype="Date", label="Paid Date", read_only=0,
           in_list_view=1, insert_after="custom_customer_paid"),
        _f(fieldname="custom_paid_cb1", fieldtype="Column Break", insert_after="custom_paid_date"),
        _f(fieldname="custom_paid_note", fieldtype="Small Text", label="Notes", read_only=0, insert_after="custom_paid_cb1"),
        _f(fieldname="custom_paid_cb2", fieldtype="Column Break", insert_after="custom_paid_note"),
        _f(fieldname="custom_paid_attachment", fieldtype="Attach", label="Paid Attachment", read_only=0, insert_after="custom_paid_cb2"),

        # ---------- Section "Print" ----------
        # SELURUH isinya HIDDEN di form: setelan print diisi lewat sidebar print view saja
        # (lihat public/js/print_view.js + CMISalesInvoice.get_print_settings). Di sini
        # cuma tempat penyimpanan persistennya. Section + column break ikut hidden supaya
        # tidak menyisakan header section kosong.
        _f(fieldname="custom_print_sb", fieldtype="Section Break", label="Print", hidden=1, insert_after="custom_paid_attachment"),
        _f(fieldname="custom_print_as_currency", fieldtype="Link", label="Print As Currency", options="Currency",
           allow_on_submit=1, hidden=1, insert_after="custom_print_sb"),
        _f(fieldname="custom_print_cb", fieldtype="Column Break", hidden=1, insert_after="custom_print_as_currency"),
        # DATA, bukan Select/Link: invoice LAMA menyimpan user id (field ini dulunya Link
        # User) dan Select-validation akan menolaknya saat save. Template menerjemahkan
        # user id lama jadi full name. Lihat erpnext_custom/printed_by.py.
        _f(fieldname="custom_printed_by", fieldtype="Data", label="Printed By", options="",
           allow_on_submit=1, hidden=1, insert_after="custom_print_cb"),
        # Dua field di bawah HIDDEN di form: input-nya HANYA lewat sidebar print view
        # (lihat public/js/print_view.js); di sini cuma tempat penyimpanannya.
        _f(fieldname="custom_invoice_title", fieldtype="Data", label="Invoice Title", default="INVOICE",
           allow_on_submit=1, hidden=1, insert_after="custom_printed_by",
           description='Judul print out terakhir (otomatis tersimpan saat tombol Print ditekan, mis. "DEBIT NOTE").'),
        _f(fieldname="custom_watermark_paid", fieldtype="Check", label="Watermark Paid", default="0",
           allow_on_submit=1, hidden=1, no_copy=1, insert_after="custom_invoice_title",
           description="Cetak watermark PAID di print out. Hanya bisa dicentang kalau Customer Paid terisi."),

        # ---------- Section "Tax" ----------
        _f(fieldname="custom_tax_sb", fieldtype="Section Break", label="Tax", insert_after="custom_watermark_paid"),
        _f(fieldname="custom_tax_no", fieldtype="Data", label="Tax No", insert_after="custom_tax_sb"),

        # ---------- Reimburse (muncul saat InvoiceType = Reimburse) ----------
        _f(fieldname="custom_reimburse_sb", fieldtype="Section Break", label="Reimburse", insert_after="items", depends_on="eval:doc.custom_invoice_behavior=='Reimburse'"),
        _f(fieldname="custom_get_expense_notes", fieldtype="Button", label="Get Expense Notes", insert_after="custom_reimburse_sb", depends_on="eval:doc.custom_invoice_behavior=='Reimburse'"),
        _f(fieldname="custom_reimburse_items", fieldtype="Table", label="Reimburse Items", options="Sales Invoice Reimburse", insert_after="custom_get_expense_notes", depends_on="eval:doc.custom_invoice_behavior=='Reimburse'"),

        # ---------- Debit Note - tabel Manual (muncul saat Behavior=Debit Note & Input Mode=Manual) ----------
        _f(fieldname="custom_dn_sb", fieldtype="Section Break", label="Debit Note Items", insert_after="custom_reimburse_items",
           depends_on="eval:doc.custom_invoice_behavior=='Debit Note' && doc.custom_dn_input_mode=='Manual'"),
        _f(fieldname="custom_dn_items", fieldtype="Table", label="Debit Note Items", options="Debit Note Item", insert_after="custom_dn_sb",
           depends_on="eval:doc.custom_invoice_behavior=='Debit Note' && doc.custom_dn_input_mode=='Manual'"),

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
           depends_on="eval:doc.custom_invoice_behavior=='Normal'"),
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
    # paid_from/to_account_currency & exchange rate DITAMPILKAN (multi-currency);
    # nilainya tetap auto dari akun (lihat _fill_bank_side) kalau user tidak mengubah.
    # pajak / withholding (tak dipakai untuk pembayaran ekspedisi)
    "apply_tds", "tax_withholding_category", "tax_withholding_group",
    "ignore_tax_withholding_threshold", "override_tax_withholding_entries",
    "tax_withholding_entries", "purchase_taxes_and_charges_template",
    "sales_taxes_and_charges_template", "taxes",
    "total_taxes_and_charges", "base_total_taxes_and_charges",
    # deductions DITAMPILKAN (tidak lagi di-hide): tempat membukukan selisih kurs —
    # mis. EN kurs 10.000 dibayar saat kurs 11.000 -> selisih ke Exchange Gain/Loss.
    # remarks bawaan dipindah ke section "Remark" paling bawah (custom_remark_note);
    # custom_remarks = flag ERPNext "jangan timpa remarks", diset server, bukan user.
    "remarks", "custom_remarks",
    # cek/giro, rekonsiliasi bank, lain-lain. cost_center TIDAK di-hide: dipindah ke
    # section Information (di bawah Mode of Payment) — lihat PE_FIELD_ORDER.
    "clearance_date", "project", "is_opening",
    "letter_head", "print_heading", "bank", "bank_account_no",
    "payment_order", "payment_order_status", "auto_repeat",
    # tabel lama yang digantikan custom_items (Payment Entry Items) — satu grid dua mode.
    "custom_direct_items",
    # section Amount dihapus — Paid/Received Amount pindah ke bawah Biaya Admin;
    # sisa isinya (base/company-currency & target rate, semua hidden) ikut ke sini.
    "payment_amounts_section", "base_paid_amount", "column_break_21",
    "target_exchange_rate", "base_received_amount",
    # layout revamp: section/field bawaan yang digantikan section custom.
    # reference_no pindah ke Information ("Reference"); reference_date tidak dipakai.
    "type_of_payment", "transaction_references", "reference_date",
    "get_outstanding_invoices", "get_outstanding_orders",
    "section_break_12", "auto_repeat_section", "taxes_and_charges_section",
    "section_tax_withholding_entry", "section_break_60",
    # currency sisi party auto (Currency + Exchange Rate yang tampil = sisi bank, di Information)
    "paid_to_account_currency", "target_exchange_rate",
    # rekening bank milik PARTY tidak dipakai (Bank Account company menggantikan posisinya)
    "party_bank_account",
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

# Mode settlement dipicu MODE OF PAYMENT "Settlement" (dulu checkbox custom_settlement
# tersendiri — kini hidden, tapi tetap ikut dievaluasi supaya dokumen lama yang terlanjur
# mencentangnya tidak berubah arti). Padanan servernya: overrides/payment_entry._is_settlement.
_SETTLE = "(doc.mode_of_payment || '').toLowerCase()=='settlement' || doc.custom_settlement"
IS_SETTLEMENT = "eval:%s" % _SETTLE
NOT_SETTLEMENT = "eval:!(%s)" % _SETTLE

PAYMENT_FIELDS = {
    "Payment Entry": [
        _f(fieldname="custom_en_sb", fieldtype="Section Break", label="Expense Note",
           insert_after="received_amount", hidden=1),
        _f(fieldname="custom_get_expense_notes", fieldtype="Button", label="Tarik Expense Note",
           insert_after="custom_en_sb", hidden=1),
        _f(fieldname="custom_expense_notes", fieldtype="Table", label="Expense Notes",
           options="Payment Entry Expense Note", insert_after="custom_get_expense_notes", hidden=1,
           description="Tabel lama (digantikan Items). Disimpan untuk dokumen lama."),
        # SATU tabel untuk dua mode (Payment Entry Items): mode tarikan (dokumen
        # outstanding, kolom Document Type/No tampil) dan mode Expense/Income (kolom
        # Account/Note tampil, baris diisi manual). Kolom di-toggle dinamis di
        # payment_entry.js (cmi_pe_items_columns).
        # depends_on dikosongkan EKSPLISIT: grid gabungan dipakai kedua mode (dulu
        # section ini hilang saat Expense/Income dicentang — sisa aturan lama, dan
        # create_custom_fields tidak menghapus properti yang cuma dihilangkan).
        _f(fieldname="custom_txn_sb", fieldtype="Section Break", label="Payment Item",
           insert_after="custom_expense_notes", depends_on=""),
        _f(fieldname="custom_get_transactions", fieldtype="Button", label="Add Items",
           insert_after="custom_txn_sb", depends_on="eval:!doc.custom_direct"),
        # label & description DIKOSONGKAN EKSPLISIT (bukan cuma dihapus dari sini):
        # judul section "Payment Item" sudah menerangkan grid ini, dan
        # create_custom_fields tidak menghapus properti yang hanya dihilangkan.
        # Keterangan dua modenya (tarikan vs Expense/Income) pindah ke komentar berikut:
        #   Mode tarikan     -> Pay = Expense Note/Purchase Invoice/Debit Note,
        #                       Receive = Sales Invoice/Credit Note (References otomatis saat Save).
        #   Mode Expense/Income -> isi Account + Amount per baris.
        _f(fieldname="custom_items", fieldtype="Table", label="",
           options="Payment Entry Items", insert_after="custom_get_transactions",
           description=""),
        # Tabel LAMA (digantikan custom_items) — hidden, dipertahankan untuk histori.
        _f(fieldname="custom_transactions", fieldtype="Table", label="Items (lama)",
           options="Payment Entry Transaction", insert_after="custom_items", hidden=1),
        # Remark paling bawah (setelah field terakhir bawaan). Native `remarks` di-hide
        # (HIDE_PAYMENT) — isinya diturunkan dari sini di before_validate.
        _f(fieldname="custom_remark_sb", fieldtype="Section Break", label="Remark",
           insert_after="auto_repeat"),
        _f(fieldname="custom_remark_note", fieldtype="Small Text", label="Remark",
           insert_after="custom_remark_sb"),
        # Ringkasan nomor dokumen di tabel References, untuk KOLOM LIST (tabel anak tidak
        # bisa jadi kolom list). Diisi otomatis di before_validate — read_only supaya tidak
        # ada yang mengetiknya manual lalu meleset dari isi tabel. no_copy: hasil Duplicate
        # belum punya References, jadi ringkasan lama tidak boleh ikut terbawa.
        _f(fieldname="custom_references", fieldtype="Data", label="References",
           insert_after="references", read_only=1, no_copy=1),

        # ---------- Revamp layout (urutan diatur PE_FIELD_ORDER, bukan insert_after) ----------
        # Section Information (3 kolom): Payment Type|Posting Date|Mode of Payment,
        # Currency|Exchange Rate|Reference, Expense/Income|Dont Post To GL|Confidential.
        _f(fieldname="custom_info_sb", fieldtype="Section Break", label="Information",
           insert_after="payment_order_status"),
        _f(fieldname="custom_info_cb1", fieldtype="Column Break", insert_after="custom_info_sb"),
        _f(fieldname="custom_info_cb2", fieldtype="Column Break", insert_after="custom_info_cb1"),
        _f(fieldname="custom_dont_post_to_gl", fieldtype="Check", label="Dont Post To GL",
           default="0", insert_after="custom_info_cb2",
           description="Submit tanpa membuat jurnal GL (dokumen catatan saja)."),
        _f(fieldname="custom_confidential", fieldtype="Check", label="Confidential",
           insert_after="custom_dont_post_to_gl"),

        # Section Currency (di bawah Information): Currency | Exchange Rate.
        _f(fieldname="custom_currency_sb", fieldtype="Section Break", label="Currency",
           insert_after="custom_confidential"),
        _f(fieldname="custom_currency_cb", fieldtype="Column Break", insert_after="custom_currency_sb"),

        # Bank (Link ke master Bank) di section From/To — memilihnya mengisi Bank Account
        # (rekening company milik bank itu) otomatis; default dari Bank.custom_default_bank.
        # Disembunyikan saat mode Settlement (sisi bank diganti akun settlement).
        _f(fieldname="custom_bank", fieldtype="Link", label="Bank", options="Bank",
           insert_after="custom_currency_cb", depends_on=NOT_SETTLEMENT,
           read_only_depends_on="eval:!doc.__islocal",
           description="Pilih bank — Bank Account (rekening company) terisi otomatis. Terkunci setelah tersimpan."),

        # Checkbox Settlement LAMA — digantikan Mode of Payment "Settlement". Di-HIDE, bukan
        # dihapus: dokumen lama menyimpan custom_settlement=1 dan logikanya masih membacanya
        # (IS_SETTLEMENT / _is_settlement), jadi arti dokumen itu tidak berubah.
        # label & description dikosongkan EKSPLISIT: create_custom_fields tidak menghapus
        # properti yang hanya dihilangkan dari definisi.
        _f(fieldname="custom_settlement", fieldtype="Check", label="Settlement (lama)",
           insert_after="custom_direct", hidden=1, description=""),

        # ---------- Aturan sumber akun (4 mode) ----------
        # 1. Expense/Income OFF        -> party dipilih, akun party dari master Supplier/Customer.
        # 2. Mode of Payment biasa     -> Bank Account dipilih, sisi bank dari rekening itu.
        # 3. Expense/Income ON         -> akun diisi per baris Items (Pay=Debit, Receive=Credit).
        # 4. Mode of Payment Settlement-> user WAJIB pilih Settlement Account (pengganti sisi bank).
        _f(fieldname="custom_settlement_account", fieldtype="Link", label="Settlement Account",
           options="Account", insert_after="custom_settlement",
           depends_on=IS_SETTLEMENT,
           mandatory_depends_on=IS_SETTLEMENT,
           description="Akun pengganti sisi Bank saat Mode of Payment = Settlement (mis. akun perantara/write off)."),

        # Checkbox "Expense / Income" — dulu Custom Field "yatim" (ada di DB, tidak dikelola
        # install.py). description="" eksplisit: keterangan modenya sudah ada di komentar
        # cmi_pe_toggle / _apply_direct_and_settlement, tidak perlu paragraf di form.
        _f(fieldname="custom_direct", fieldtype="Check", label="Expense / Income",
           insert_after="payment_type", description=""),
        _f(fieldname="custom_payto", fieldtype="Data", label="Pay To",
           insert_after="custom_direct", depends_on="eval:doc.custom_direct",
           description="Nama penerima/pengirim (teks bebas) untuk mode Expense / Income."),

        # Section Pending Cash — hanya saat type Pay. Tabel pakai child yang sama
        # dengan Items (Payment Entry Transaction); sumber tarikan dokumennya menyusul.
        _f(fieldname="custom_pending_sb", fieldtype="Section Break", label="Pending Cash",
           depends_on="eval:doc.payment_type=='Pay'", insert_after="custom_transactions"),
        _f(fieldname="custom_get_pending", fieldtype="Button", label="Add Pending Cash",
           insert_after="custom_pending_sb", depends_on="eval:doc.payment_type=='Pay'"),
        # label dikosongkan: judul section "Pending Cash" sudah ada tepat di atasnya.
        _f(fieldname="custom_pending_items", fieldtype="Table", label="",
           options="Payment Entry Transaction", insert_after="custom_get_pending",
           depends_on="eval:doc.payment_type=='Pay'"),

        # Baris smart input di bawah tabel Payment Item: Amount Tax | PPh | Materai.
        # Persen/nominal di-parse server (_apply_pe_smart_inputs); BELUM diposting ke GL
        # (menunggu desain jurnalnya — "build dulu").
        _f(fieldname="custom_pe_tax_sb", fieldtype="Section Break", label="",
           insert_after="custom_pending_items", depends_on=""),
        _f(fieldname="custom_tax_input", fieldtype="Data", label="Amount Tax",
           description='Ketik mis. "11%" atau "150000"', insert_after="custom_pe_tax_sb"),
        _f(fieldname="custom_tax_pct", fieldtype="Percent", label="Tax %", hidden=1, insert_after="custom_tax_input"),
        _f(fieldname="custom_tax_amount", fieldtype="Currency", label="Amount Tax (nominal)", hidden=1, insert_after="custom_tax_pct"),
        _f(fieldname="custom_pe_tax_cb1", fieldtype="Column Break", insert_after="custom_tax_amount"),
        _f(fieldname="custom_pph_input", fieldtype="Data", label="PPh",
           description='Ketik mis. "2%" atau "50000"', insert_after="custom_pe_tax_cb1"),
        _f(fieldname="custom_pph_pct", fieldtype="Percent", label="PPh %", hidden=1, insert_after="custom_pph_input"),
        _f(fieldname="custom_pph_amount", fieldtype="Currency", label="PPh (nominal)", hidden=1, insert_after="custom_pph_pct"),
        _f(fieldname="custom_pe_tax_cb2", fieldtype="Column Break", insert_after="custom_pph_amount"),
        _f(fieldname="custom_materai_amount", fieldtype="Currency", label="Materai",
           insert_after="custom_pe_tax_cb2"),
        _f(fieldname="custom_admin_fee", fieldtype="Currency", label="Biaya Admin",
           insert_after="custom_materai_amount",
           description="Biaya admin bank/transfer (nominal)."),

        # ---------- Komponen penomoran (hidden; diisi autoname sebelum penamaan) ----------
        # Dipakai naming series PE_NAMING_SERIES di bawah — polanya bisa diedit user di
        # Document Naming Settings (pilih Payment Entry). PV/RV, kode bank, kode company,
        # tahun & bulan romawi dari posting_date. Bulan+tahun di prefix = counter reset
        # otomatis tiap bulan/tahun.
        _f(fieldname="custom_no_code", fieldtype="Data", label="No Code", hidden=1, read_only=1,
           print_hide=1, insert_after="custom_admin_fee"),
        _f(fieldname="custom_bank_code", fieldtype="Data", label="Bank Code", hidden=1, read_only=1,
           print_hide=1, insert_after="custom_no_code"),
        _f(fieldname="custom_company_code", fieldtype="Data", label="Company Code", hidden=1, read_only=1,
           print_hide=1, insert_after="custom_bank_code"),
        _f(fieldname="custom_year", fieldtype="Data", label="Year", hidden=1, read_only=1,
           print_hide=1, insert_after="custom_company_code"),
        _f(fieldname="custom_month_roman", fieldtype="Data", label="Month (Roman)", hidden=1, read_only=1,
           print_hide=1, insert_after="custom_year"),

        # Section Additional: Remark | Attachment (remark memakai custom_remark_note lama).
        _f(fieldname="custom_add_cb", fieldtype="Column Break", insert_after="custom_remark_note"),
        _f(fieldname="custom_attachment", fieldtype="Attach", label="Attachment",
           insert_after="custom_add_cb"),
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
        # Pola sama dengan invoice_title: field ini cuma "slot" supaya sidebar print
        # punya checkbox-nya; nilainya persisten per-dokumen di
        # Sales Invoice.custom_watermark_paid. Checkbox HANYA dirender kalau invoice
        # sudah Customer Paid (filter di public/js/print_view.js).
        _f(fieldname="watermark_paid", fieldtype="Check", label="Watermark Paid", default="0",
           insert_after="invoice_title",
           description="Cetak watermark PAID di print out invoice."),
        _f(fieldname="print_as_currency", fieldtype="Link", label="Print As Currency", options="Currency",
           insert_after="watermark_paid",
           description="Cetak nilai invoice dalam mata uang ini (dikali kurs header)."),
        # Select, BUKAN Link User: penandatangan sering bukan user sistem. Opsinya
        # disinkronkan dari Selling Settings > Printed By (erpnext_custom.printed_by).
        _f(fieldname="printed_by", fieldtype="Select", label="Printed By",
           insert_after="print_as_currency",
           description="Nama/keterangan di blok tanda tangan. Diatur di Selling Settings > Print."),
        # READ ONLY dan TIDAK ikut disimpan saat Print (tidak ada di FIELDS pada
        # public/js/print_view.js). branch_office adalah field KONTROL AKSES — diisi
        # otomatis dari branch pembuat dan menentukan siapa yang boleh melihat invoice.
        # Kalau bisa diubah dari sidebar print, siapa pun yang mencetak bisa memindahkan
        # invoice ke luar pandangan timnya sendiri. Di sini murni informasi.
        _f(fieldname="branch_office", fieldtype="Data", label="Branch Office", read_only=1,
           insert_after="printed_by",
           description="Branch pemilik invoice (otomatis dari branch pembuat)."),
    ],
}

# Selling Settings — tab "Invoice Type": tabel konfigurasi tipe invoice yang dinamis.
# Tiap baris: nama tipe, Behavior (Normal/Reimburse/Debit Note), Type No (koma), Role yang
# boleh memakai, Disabled. Enabled + sesuai role -> muncul di dropdown Invoice Type.
# Logika di erpnext_custom.invoice_types (sync opsi Select + validasi + filter role).
SELLING_SETTINGS_FIELDS = {
    "Selling Settings": [
        _f(fieldname="custom_invoice_types_tab", fieldtype="Tab Break", label="Invoice Type",
           insert_after="transaction_naming_html"),
        _f(fieldname="custom_invoice_types_html", fieldtype="HTML",
           insert_after="custom_invoice_types_tab",
           options="<p class='text-muted'>Tipe invoice yang dipakai di Sales Invoice. "
                   "<b>Enable</b> (hilangkan centang Disabled) supaya muncul di dropdown Invoice Type. "
                   "<b>Behavior</b> menentukan perilaku: Reimburse memunculkan Get Expense Notes, "
                   "Debit Note memunculkan Input Mode. <b>Roles</b> membatasi siapa yang boleh memakai "
                   "tipe (kosong = semua).</p>"),
        _f(fieldname="custom_invoice_types", fieldtype="Table", label="Invoice Types",
           options="CMI Invoice Type", insert_after="custom_invoice_types_html"),
        # Tab "Print" — daftar pilihan Printed By untuk sidebar print view.
        _f(fieldname="custom_print_tab", fieldtype="Tab Break", label="Print",
           insert_after="custom_invoice_types"),
        _f(fieldname="custom_printed_by_html", fieldtype="HTML",
           insert_after="custom_print_tab",
           options="<p class='text-muted'>Pilihan <b>Printed By</b> di sidebar print view Sales Invoice "
                   "(teks di blok tanda tangan). Isi bebas: nama orang, jabatan, atau keterangan. "
                   "Baris yang ditandai <b>Default</b> dipakai otomatis untuk invoice yang belum punya "
                   "pilihan sendiri, dan ikut tersimpan saat tombol Print ditekan. Hanya satu baris "
                   "yang boleh Default. <b>Disabled</b> menyembunyikan baris dari pilihan baru tapi "
                   "invoice lama yang memakainya tetap aman.</p>"),
        _f(fieldname="custom_printed_by_options", fieldtype="Table", label="Printed By",
           options="CMI Printed By", insert_after="custom_printed_by_html"),
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


# Sales Invoice Item — currency & rate per baris. Item bisa beda mata uang dari header
# (mis. row 1 IDR, row 2 USD). User isi Price dalam mata uang item; server men-set `rate`
# core = custom_item_price * custom_exchange_rate (nilai dalam mata uang HEADER), jadi
# amount/total/pajak/GL ERPNext otomatis benar. custom_currency default = mata uang header;
# exchange_rate = 1 kalau sama, WAJIB diisi kalau beda. Lihat overrides/sales_invoice._apply_item_currency.
ITEM_FIELDS = {
    "Sales Invoice Item": [
        # Urutan kolom grid: Item | Notes | Currency | Price | Rate | Qty | UOM | Amount.
        # custom_notes dikelola di sini (semula dibuat sesi lain setelah item_name) supaya
        # posisinya tepat SETELAH Item.
        _f(fieldname="custom_notes", fieldtype="Small Text", label="Notes",
           in_list_view=1, columns=2, insert_after="item_code"),
        _f(fieldname="custom_currency", fieldtype="Link", label="Currency", options="Currency",
           in_list_view=1, columns=1, insert_after="custom_notes",
           description="Mata uang baris ini. Default = mata uang invoice (header)."),
        _f(fieldname="custom_item_price", fieldtype="Currency", label="Price", options="custom_currency",
           in_list_view=1, columns=1, insert_after="custom_currency",
           description="Harga satuan dalam mata uang baris ini."),
        _f(fieldname="custom_exchange_rate", fieldtype="Float", label="Rate", precision="9", default="1",
           in_list_view=1, columns=1, insert_after="custom_item_price",
           description="Kurs ke mata uang header. 1 kalau mata uangnya sama; wajib diisi kalau beda."),
    ],
}


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
    # cost_center TIDAK di-hide: dipakai user, tampil di section "Accounting Dimensions"
    # (field CORE — tidak bisa dipindah ke section custom tanpa field_order penuh).
    "title", "project",
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
    # Core rate = harga satuan dalam mata uang HEADER (IDR), diturunkan server dari
    # custom_item_price * custom_exchange_rate. Kolomnya disembunyikan (user isi di Price/Currency/Rate).
    ("Sales Invoice Item", "rate", "Price (IDR)"),
    # Satu kolom item saja: Link Item menampilkan "code - name" (show_title_field_in_link
    # di Item), kolom item_name disembunyikan. Label jadi "Item".
    ("Sales Invoice Item", "item_code", "Item"),
    # Payment Entry — layout revamp
    ("Payment Entry", "paid_from", "Account From"),
    ("Payment Entry", "paid_to", "Account Paid To"),
    ("Payment Entry", "paid_from_account_currency", "Currency"),
    ("Payment Entry", "source_exchange_rate", "Exchange Rate"),
    ("Payment Entry", "bank_account", "Bank Account"),
    ("Payment Entry", "reference_no", "Reference"),
    ("Payment Entry", "payment_accounts_section", "Account"),
    ("Payment Entry", "custom_txn_sb", "Payment Item"),
    ("Payment Entry", "custom_remark_sb", "Additional"),
]
# (doctype, fieldname, default)
DEFAULTS = [
    ("Sales Invoice Item", "qty", "1"),
    ("Payment Entry", "mode_of_payment", "Bank Draft"),
]

# Pola nomor Payment Entry — DIEDIT USER di Document Naming Settings (pilih doctype
# Payment Entry). Komponen .custom_*. dihitung otomatis di CMIPaymentEntry.autoname
# sebelum penamaan: PV/RV, kode bank (kata pertama nama akun bank), kode company
# (abbr), tahun & bulan romawi dari posting_date. Karena tahun+bulan bagian dari
# prefix, counter #### reset otomatis per bulan (dan per tahun).
# Contoh hasil: PV/MDR/CMI/2026/VII/0001
PE_NAMING_SERIES = ".custom_no_code./.custom_bank_code./.custom_company_code./.custom_year./.custom_month_roman./.####."

# Urutan field Payment Entry (property setter `field_order` level doctype — satu-satunya
# cara menyusun ulang field CORE ke section custom). Field yang tidak disebut otomatis
# menempel di akhir (semuanya hidden).
PE_FIELD_ORDER = [
    # Information — 3 kolom
    "custom_info_sb",
    "payment_type", "custom_direct",
    "custom_info_cb1",
    "posting_date", "custom_dont_post_to_gl",
    "custom_info_cb2",
    # Settlement Account tepat di bawah Mode of Payment: hanya muncul saat mode-nya
    # "Settlement" (dulu dipicu checkbox custom_settlement — kini hidden).
    "mode_of_payment", "cost_center", "custom_settlement_account",
    "reference_no", "custom_confidential", "branch_office",
    # Currency — 2 kolom (default currency dari system; rate auto 1 utk sesama IDR)
    "custom_currency_sb", "paid_from_account_currency",
    "custom_currency_cb", "source_exchange_rate",
    # Mode Expense/Income: tinggal Pay To (tabelnya kini menyatu di custom_items)
    "custom_direct_sb", "custom_payto", "custom_direct_items",
    # Payment From / To — kolom kanan: Bank; party_bank_account disembunyikan (tak dipakai).
    "party_section", "party_type", "party", "party_name",
    "column_break_11", "custom_bank", "party_bank_account",
    # Account — Bank Account (rekening company) di bawah Account Paid To
    "payment_accounts_section", "paid_from", "paid_from_account_type",
    "column_break_18", "paid_to", "bank_account", "paid_to_account_type",
    "paid_to_account_currency",
    # Pending Cash (hanya Pay)
    "custom_pending_sb", "custom_get_pending", "custom_pending_items",
    # Payment Item (satu grid dua mode) + smart input pajak; nominal bayar (Paid/
    # Received Amount — bertukar sesuai arah) persis di bawah Biaya Admin.
    "custom_txn_sb", "custom_get_transactions", "custom_items", "custom_transactions",
    "custom_pe_tax_sb", "custom_tax_input", "custom_tax_pct", "custom_tax_amount",
    "custom_pe_tax_cb1", "custom_pph_input", "custom_pph_pct", "custom_pph_amount",
    "custom_pe_tax_cb2", "custom_materai_amount", "custom_admin_fee",
    "paid_amount", "received_amount",
    # References + alokasi + deductions (selisih kurs/potongan)
    "section_break_14", "get_outstanding_invoices", "get_outstanding_orders", "references",
    "deductions_or_loss_section", "deductions",
    "section_break_34", "total_allocated_amount", "base_total_allocated_amount",
    "column_break_36", "unallocated_amount", "difference_amount", "write_off_difference_amount",
    # Additional
    "custom_remark_sb", "custom_remark_note", "custom_add_cb", "custom_attachment",
    "amended_from",
    # ---- zona buangan (semua hidden) — WAJIB disebut eksplisit: field yang tidak ada
    # di daftar ini ditempel Frappe di dekat posisi relatif LAMANYA, sehingga column
    # break bawaan bisa nyasar ke tengah section custom dan merusak layout 3 kolom.
    "type_of_payment", "naming_series", "payment_order_status", "company",
    "column_break_5", "book_advance_payments_in_separate_party_account",
    "reconcile_on_advance_payment_date", "apply_tds", "tax_withholding_category",
    "contact_person", "contact_email",
    "paid_amount_after_tax", "base_paid_amount_after_tax",
    "custom_en_sb", "custom_get_expense_notes", "custom_expense_notes",
    "received_amount_after_tax", "base_received_amount_after_tax",
    "taxes_and_charges_section", "purchase_taxes_and_charges_template",
    "sales_taxes_and_charges_template", "taxes",
    "section_break_60", "base_total_taxes_and_charges", "column_break_61",
    "total_taxes_and_charges",
    "section_tax_withholding_entry", "tax_withholding_group",
    "ignore_tax_withholding_threshold", "override_tax_withholding_entries",
    "tax_withholding_entries",
    "transaction_references", "reference_date", "column_break_23", "clearance_date",
    "accounting_dimensions_section", "project", "dimension_col_break",
    "custom_settlement",
    "section_break_12", "status", "custom_remarks", "remarks", "base_in_words",
    "is_opening", "title", "column_break_16", "letter_head", "print_heading",
    "bank", "bank_account_no", "payment_order", "in_words",
    "auto_repeat_section", "auto_repeat",
    # komponen penomoran (hidden)
    "custom_no_code", "custom_bank_code", "custom_company_code",
    "custom_year", "custom_month_roman",
]
# Payment Entry — perilaku field bawaan (Property Setter; (doctype, fieldname, prop, value, type)).
PAYMENT_PROPS = [
    # Satu arah = satu tombol tarik: Pay bayar Purchase Order, Receive tagih Sales Invoice.
    ("Payment Entry", "get_outstanding_invoices", "depends_on",
     "eval:doc.docstatus==0 && doc.payment_type=='Receive'", "Data"),
    ("Payment Entry", "get_outstanding_orders", "depends_on",
     "eval:doc.docstatus==0 && doc.payment_type=='Pay'", "Data"),
    # Tabel References diisi OTOMATIS dari tabel Items saat Save -> sembunyikan selagi kosong
    # (kalau tampil kosong, user mengira harus mengisinya sendiri).
    ("Payment Entry", "references", "depends_on", "eval:doc.references && doc.references.length", "Data"),
    # Section Writeoff & Deductions (alokasi/selisih): tampil saat settlement ATAU ada
    # selisih/deductions (kasus bayar beda kurs — selisihnya dibukukan di sini).
    ("Payment Entry", "section_break_34", "depends_on",
     "eval:%s || doc.difference_amount || doc.unallocated_amount || (doc.deductions && doc.deductions.length)" % _SETTLE, "Data"),
    ("Payment Entry", "deductions_or_loss_section", "depends_on",
     "eval:%s || doc.difference_amount || doc.unallocated_amount || (doc.deductions && doc.deductions.length)" % _SETTLE, "Data"),
    ("Payment Entry", "mode_of_payment", "default", "Bank Draft", "Data"),
    # Mode of Payment WAJIB; Reference TIDAK (core memaksanya wajib saat akun bank
    # bertipe Bank via mandatory_depends_on — dinolkan; server juga sudah
    # meng-override validate_transaction_reference).
    ("Payment Entry", "mode_of_payment", "reqd", "1", "Check"),
    ("Payment Entry", "reference_no", "reqd", "0", "Check"),
    ("Payment Entry", "reference_no", "mandatory_depends_on", "", "Data"),
    # Pasangannya juga: Cheque/Reference Date ikut dipaksa wajib oleh core saat akun
    # bank bertipe Bank — padahal field-nya kita sembunyikan (mandatory tersembunyi
    # memblokir Save tanpa kelihatan).
    ("Payment Entry", "reference_date", "reqd", "0", "Check"),
    ("Payment Entry", "reference_date", "mandatory_depends_on", "", "Data"),
    # Akun party (Pay: paid_to, Receive: paid_from) baru TERISI OTOMATIS saat Save
    # (_sync_party_account dari dokumen tarikan) — jangan wajib di draft, kalau tidak
    # user terblokir "Account From mandatory" sebelum sempat menarik apa pun.
    ("Payment Entry", "paid_from", "reqd", "0", "Check"),
    ("Payment Entry", "paid_to", "reqd", "0", "Check"),
    # Bank Account (core) ikut tersembunyi saat mode Settlement.
    ("Payment Entry", "bank_account", "depends_on", NOT_SETTLEMENT, "Data"),
    # Section Amount SELALU tampil. Core menyembunyikannya sampai paid_from DAN paid_to
    # terisi — di alur kita paid_to baru terisi saat Save/tarik Items, jadi field
    # Paid Amount "selalu hilang" di dokumen baru.
    ("Payment Entry", "payment_amounts_section", "depends_on", "", "Data"),
    # SATU nominal untuk kedua arah: Paid Amount — Receive tampil sama persis dengan Pay.
    # Received Amount tetap terisi otomatis di belakang layar (cmi_sync_paid), cuma tidak
    # ditampilkan supaya tidak ada dua kotak nominal yang membingungkan.
    ("Payment Entry", "paid_amount", "depends_on", "", "Data"),
    ("Payment Entry", "received_amount", "depends_on", "eval:0", "Data"),
    # Exchange Rate default 1 — kurs sungguhan baru dihitung core saat currency akun
    # bank berbeda dari currency company (mis. rekening USD).
    ("Payment Entry", "source_exchange_rate", "default", "1", "Data"),
    # Setelah tersimpan: arah & sumber bank terkunci (nomor dokumen memuat PV/RV +
    # kode bank — mengubahnya membuat nomor bohong).
    ("Payment Entry", "payment_type", "read_only_depends_on", "eval:!doc.__islocal", "Data"),
    ("Payment Entry", "bank_account", "read_only_depends_on", "eval:!doc.__islocal", "Data"),
    # Section Currency harus SELALU tampil: core menyembunyikan currency di balik
    # depends_on paid_from (kosong saat Pay baru). Exchange Rate di-toggle JS core —
    # dipaksa tampil di payment_entry.js (cmi_pe_show_currency).
    ("Payment Entry", "paid_from_account_currency", "depends_on", "", "Data"),
]

# Default Bank per deployment: checkbox di master Bank; dipakai Payment Entry untuk
# mengisi Bank -> Bank Account -> Account From otomatis pada dokumen baru.
BANK_FIELDS = {
    # Detail bank untuk footer "Bank Detail" print out invoice — SEMUA di doctype Bank
    # (bukan Bank Account). Field yang SUDAH ada di Bank TIDAK diduplikasi: Bank Name =
    # bank_name, SWIFT = swift_number, dan pemilihan default sudah lewat custom_default_bank.
    # Yang ditambah hanya yang belum ada: Account Name, Bank Branch, Account Number.
    "Bank": [
        _f(fieldname="custom_default_bank", fieldtype="Check", label="Default Bank",
           insert_after="bank_name",
           description="Bank default company — otomatis terpilih di Payment Entry baru & dipakai di footer print out invoice."),
        _f(fieldname="custom_print_sb", fieldtype="Section Break", label="Print (Invoice)",
           insert_after="swift_number"),
        # description="" eksplisit: create_custom_fields tidak menghapus properti yang
        # dihilangkan dari definisi, jadi note lama harus dikosongkan langsung.
        _f(fieldname="custom_account_name", fieldtype="Data", label="Account Name",
           insert_after="custom_print_sb", description=""),
        _f(fieldname="custom_bank_branch", fieldtype="Data", label="Bank Branch",
           insert_after="custom_account_name", description=""),
        _f(fieldname="custom_account_number", fieldtype="Data", label="Account Number",
           insert_after="custom_bank_branch", description=""),
    ],
}

# (doctype, fieldname, property, value, property_type) -- kolom grid item
GRID = [
    # item_name digabung ke kolom item_code (Link "code - name") -> disembunyikan TOTAL.
    # hidden=1 (bukan cuma in_list_view=0): grid column user-settings (ikon gerigi) MENIMPA
    # in_list_view, jadi kolomnya tetap muncul; field hidden tak pernah jadi kolom.
    # reqd=0: Frappe selalu menampilkan field child mandatory. item_name auto-fetch dari
    # item_code, jadi aman non-mandatory & hidden — nilainya tetap terisi.
    ("Sales Invoice Item", "item_name", "in_list_view", "0", "Check"),
    ("Sales Invoice Item", "item_name", "reqd", "0", "Check"),
    ("Sales Invoice Item", "item_name", "hidden", "1", "Check"),
    # Budget kolom grid ~10. Urutan: Item | Notes | Currency | Price | Rate | Qty | UOM |
    # Amount = 2+2+1+1+1+1+1+1 = 10. Kolom custom (Notes/Currency/Price/Rate) diatur di ITEM_FIELDS.
    ("Sales Invoice Item", "item_code", "columns", "2", "Int"),
    ("Sales Invoice Item", "qty", "columns", "1", "Int"),
    ("Sales Invoice Item", "uom", "in_list_view", "1", "Check"),
    ("Sales Invoice Item", "uom", "columns", "1", "Int"),
    ("Sales Invoice Item", "amount", "columns", "1", "Int"),
    # custom_notes dulu punya Property Setter in_list_view=0 (dari sesi lain / iterasi lama).
    # Property Setter menang atas field def, jadi WAJIB ditimpa eksplisit ke 1 di sini.
    ("Sales Invoice Item", "custom_notes", "in_list_view", "1", "Check"),
    ("Sales Invoice Item", "custom_notes", "columns", "2", "Int"),
    # Core rate (Price IDR) diturunkan dari custom_item_price*rate -> sembunyikan kolomnya.
    ("Sales Invoice Item", "rate", "in_list_view", "0", "Check"),
    ("Sales Invoice Item", "warehouse", "in_list_view", "0", "Check"),
    ("Sales Invoice Item", "warehouse", "hidden", "1", "Check"),
    # Items disembunyikan saat behavior = Reimburse (kebalikan dari tabel Reimburse).
    ("Sales Invoice", "items_section", "depends_on", "eval:doc.custom_invoice_behavior!='Reimburse'", "Data"),
    ("Sales Invoice", "items", "depends_on", "eval:doc.custom_invoice_behavior!='Reimburse'", "Data"),
]
# Custom field lama yang sudah tidak dipakai -> dihapus.
OBSOLETE = [
    # Percobaan menaruh 2 tombol "Get Outstanding ..." sejajar lewat Column/Section Break.
    # TIDAK BISA: Meta.sort_fields sengaja menggeser custom break ke UJUNG section (mencari
    # break berikutnya), jadi Section Break-nya mendarat SESUDAH tabel References dan tabel
    # itu ikut terjebak di kolom kanan. Kedua tombol kini disejajarkan lewat CSS di
    # public/js/payment_entry.js.
    ("Payment Entry", "custom_ref_cb"), ("Payment Entry", "custom_ref_table_sb"),
    # Detail print bank DIPINDAH dari Bank Account ke Bank (Bank sudah punya default).
    ("Bank Account", "custom_print_sb"), ("Bank Account", "custom_account_name"),
    ("Bank Account", "custom_bank_branch"), ("Bank Account", "custom_print_default"),
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
    # Setting reimbursement lama di Accounts Settings -> diganti Expense Class.reimburse_account.
    ("Accounts Settings", "custom_reimbursement_account"),
    ("Accounts Settings", "custom_reimbursement_tab"),
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


# Kolom list Payment Entry, URUT kiri->kanan:
#   ID | Party | Type | Status | Posting Date | References | Currency | Rate | Bank |
#   Paid Amount | Outstanding | Remark
# "title" TIDAK dipakai: isinya cuma salinan `party`, dan Party sudah jadi kolom sendiri.
# Digantikan custom_references (ringkasan nomor dokumen di tabel References) supaya dari
# list langsung kelihatan pembayaran ini melunasi dokumen yang mana.
# "status_field" BUKAN fieldname — itu kode Frappe untuk kolom indikator status (lihat
# reorder_listview_fields di list_view.js); wujudnya diatur get_indicator di
# payment_entry_list.js (Draft / Validated / Void).
# ID tidak ikut didaftar: dia kolom Subject, selalu paling kiri (lihat _pe_list_columns).
PE_LIST_COLUMNS = [
    ("party", "Party"),
    ("payment_type", "Type"),
    ("status_field", "Status"),
    ("posting_date", "Posting Date"),
    ("custom_references", "References"),
    ("paid_from_account_currency", "Currency"),
    ("source_exchange_rate", "Rate"),
    ("custom_bank", "Bank"),
    ("paid_amount", "Paid Amount"),
    ("unallocated_amount", "Outstanding"),
    ("custom_remark_note", "Remark"),
]

# Kolom bawaan yang TIDAK diminta — akun From/To terlalu panjang untuk list.
# "title" dimatikan EKSPLISIT, bukan sekadar dikeluarkan dari PE_LIST_COLUMNS: install
# versi lama sudah menulis property setter in_list_view=1 untuknya, dan itu tetap ada
# sampai ditimpa. Tanpa baris ini kolom Title masih nongol di site yang sudah terpasang.
PE_LIST_DROP = ("paid_from", "paid_to", "title")


def _setup_payment_entry_list_columns():
    """Susun kolom list Payment Entry. Tiga lapis, ketiganya perlu:

    1. in_list_view per field — menentukan field mana yang BOLEH jadi kolom.
    2. title_field DIKOSONGKAN — selama title_field terisi, Frappe memaksa kolom pertama
       (Subject) = Title lalu menempelkan ID di ujung kanan (list_view.js setup_columns +
       reorder_listview_fields), jadi urutan "ID dulu, Title di tengah" mustahil. Dikosongkan
       -> Subject jadi ID. Efek sampingnya: judul form & preview link ikut memakai nomor
       dokumen, bukan nama party — untuk dokumen akuntansi itu justru yang dicari.
    3. List View Settings.fields — URUTAN kolom (dan posisi Status lewat "status_field").
    """
    import json as _json

    for fn, _label in PE_LIST_COLUMNS:
        if fn != "status_field":
            _field_prop("Payment Entry", fn, "in_list_view", "1", "Check")
    for fn in PE_LIST_DROP:
        _field_prop("Payment Entry", fn, "in_list_view", "0", "Check")

    # Label kolom = label field-nya. Dua field bawaan diberi nama sesuai istilah CMI:
    # "Exchange Rate" -> Rate (sama seperti conversion_rate di PO/PI), dan "Unallocated
    # Amount" -> Outstanding. Ikut berubah di FORM juga — memang disengaja supaya satu
    # istilah dipakai di semua tempat.
    _field_prop("Payment Entry", "source_exchange_rate", "label", "Rate", "Data")
    _field_prop("Payment Entry", "unallocated_amount", "label", "Outstanding", "Data")

    _set_doctype_prop("Payment Entry", "title_field", "", "Data")

    fields = _json.dumps([{"fieldname": fn, "label": label} for fn, label in PE_LIST_COLUMNS])
    lvs = (
        frappe.get_doc("List View Settings", "Payment Entry")
        if frappe.db.exists("List View Settings", "Payment Entry")
        else frappe.new_doc("List View Settings")
    )
    lvs.name = "Payment Entry"
    lvs.fields = fields
    lvs.save(ignore_permissions=True)


# Urutan kolom list Sales Invoice. Sebelumnya cuma ada di DB (List View Settings dibuat
# manual lewat UI) -> hilang tiap site di-rebuild. Sekarang dikelola di sini supaya
# konsisten. "status_field" = kolom Status bawaan (indicator).
SI_LIST_COLUMNS = [
    ("name", "ID"),
    ("status_field", "Status"),
    ("customer", "Customer"),
    ("custom_invoice_type", "Invoice Type"),
    ("invoice_date", "Invoice Date"),
    # Paid Date + Paid berdampingan dengan Invoice Date.
    ("custom_paid_date", "Paid Date"),
    ("custom_customer_paid", "Paid"),
    ("currency", "Currency"),
    ("conversion_rate", "Rate"),
    ("custom_discount_amount", "Discount Amount"),
    ("custom_pph_amount", "PPh Amount"),
    ("custom_tax_amount", "Tax Amount"),
    ("custom_net_total", "Net Total"),
    ("custom_shipping_list_nos", "Shipping List"),
    ("custom_created_by", "Created By"),
    ("custom_assigned_to", "Assign To"),
]


def _setup_sales_invoice_list_columns():
    import json as _json

    lvs = (
        frappe.get_doc("List View Settings", "Sales Invoice")
        if frappe.db.exists("List View Settings", "Sales Invoice")
        else frappe.new_doc("List View Settings")
    )
    lvs.name = "Sales Invoice"
    lvs.fields = _json.dumps([{"fieldname": fn, "label": label} for fn, label in SI_LIST_COLUMNS])
    lvs.save(ignore_permissions=True)


def _backfill_payment_entry_references():
    """Isi custom_references untuk Payment Entry lama.

    custom_references diturunkan di before_validate (_apply_reference_summary), jadi hanya
    terisi untuk dokumen yang disimpan setelah fitur ini ada — dokumen lama tampil kosong di
    kolom list sampai dihitung ulang. Dijalankan di after_migrate (bukan patch) supaya PASTI
    setelah custom field-nya dibuat: patch post_model_sync jalan sebelum after_migrate, jadi
    field-nya belum ada saat itu.

    Ringkasan dihitung langsung dari tabel References lewat SQL, tidak load+save dokumennya:
    Payment Entry submitted, dan load+save akan kena validasi submit yang bisa gagal di
    dokumen lama. custom_references cuma kolom turunan (read-only, tidak masuk GL), jadi aman
    ditulis lewat db.set_value. Logikanya dijaga identik dengan _apply_reference_summary —
    dedup reference_name sambil mempertahankan urutan. Idempoten: hanya baris yang berubah
    yang ditulis.
    """
    if not frappe.db.has_column("Payment Entry", "custom_references"):
        return
    rows = frappe.db.sql(
        """SELECT parent, reference_name FROM `tabPayment Entry Reference`
           WHERE ifnull(reference_name, '') != '' ORDER BY parent, idx""",
        as_dict=True,
    )
    by_parent = {}
    for r in rows:
        names = by_parent.setdefault(r.parent, [])
        if r.reference_name not in names:
            names.append(r.reference_name)
    for parent, names in by_parent.items():
        summary = ", ".join(names)
        if frappe.db.get_value("Payment Entry", parent, "custom_references") != summary:
            frappe.db.set_value(
                "Payment Entry", parent, "custom_references", summary, update_modified=False
            )


def _setup_gl_entry_title():
    """Tampilkan NOMOR TRANSAKSI sebagai judul GL Entry, bukan hash namanya.

    Nama dokumen GL Entry itu hash (mis. "281192e110") — tidak ada artinya buat orang dan
    tidak bisa dicari. Nomor transaksinya sudah ada di `voucher_no`; dijadikan title_field
    supaya kolom pertama list GL Entry langsung menampilkannya dan kotak search mencarinya.

    Sengaja TIDAK mengganti autoname jadi nomor transaksi. Satu voucher bisa punya belasan
    baris GL (sampai 26 baris untuk satu Journal Entry), jadi nomor transaksi saja tidak
    unik. Lebih parah: saat dokumen di-cancel ERPNext tidak menghapus GL Entry-nya, tapi
    menambah baris PEMBALIK dengan voucher_no yang sama — penomoran <voucher_no>-<urutan>
    akan tabrakan nama di situ dan menggagalkan cancel. title_field memberi manfaat
    pencarian yang sama tanpa menyentuh jalur posting sama sekali.

    show_title_field_in_link tidak diset: tidak ada doctype yang me-link ke GL Entry.
    """
    _set_doctype_prop("GL Entry", "title_field", "voucher_no", "Data")


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


def _ensure_invoice_types_default():
    from erpnext_custom import invoice_types
    invoice_types.ensure_default_types()


def _sync_invoice_type_options():
    from erpnext_custom import invoice_types
    invoice_types.sync_invoice_type_options()
    invoice_types.backfill_invoice_behavior()
    invoice_types.ensure_type_accounts()


def _ensure_submit_label():
    """Tombol bawaan "Submit" -> "Validate".

    Label tombol primary = `__(status)` (frappe/form/toolbar.js set_page_actions), jadi
    satu baris Translation sudah cukup — tak perlu meng-override toolbar. Berlaku global,
    dan itu memang yang diinginkan: guard_submit/guard_cancel (erpnext_custom.workflow)
    sudah menutup submit bawaan untuk SEMUA doctype yang dipakai, dan istilah resmi di
    sistem ini adalah Validate. Idempoten; hapus barisnya untuk mengembalikan.
    """
    name = frappe.db.exists("Translation", {"source_text": "Submit", "language": "en"})
    if name:
        return
    frappe.get_doc({
        "doctype": "Translation",
        "language": "en",
        "source_text": "Submit",
        "translated_text": "Validate",
    }).insert(ignore_permissions=True)


def _ensure_printed_by_default():
    from erpnext_custom import printed_by
    printed_by.ensure_defaults()


def _sync_printed_by_options():
    from erpnext_custom import printed_by
    printed_by.sync_printed_by_options()


def _ensure_settlement_mode_of_payment():
    # Mode of Payment "Settlement" memicu mode settlement Payment Entry (sisi bank
    # diganti custom_settlement_account — lihat overrides/payment_entry.py). Sengaja
    # TANPA default account: akun dipilih user per transaksi.
    #
    # enabled=1 DITEGAKKAN tiap migrate, bukan cuma saat membuat: Frappe menyaring
    # `enabled=1` di pencarian link, jadi Settlement yang ter-disable hilang dari dropdown
    # Mode of Payment — dan sejak pemicunya pindah ke sini (checkbox custom_settlement
    # sudah hidden), itu membuat mode settlement TIDAK BISA dipakai sama sekali.
    if not frappe.db.exists("Mode of Payment", "Settlement"):
        frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": "Settlement",
            "type": "General",
            "enabled": 1,
        }).insert(ignore_permissions=True)
    elif not frappe.db.get_value("Mode of Payment", "Settlement", "enabled"):
        frappe.db.set_value("Mode of Payment", "Settlement", "enabled", 1)


INVOICE_ROLES = ("Invoice Validate", "Invoice Void")

# Role alur transaksi (Validate / Invalidate / Void / Unvoid) — berlaku lintas doctype:
# Sales Invoice, Purchase Invoice, Purchase Order, Payment Entry, Expense Note, Pending Cash.
# Role INVOICE_ROLES lama tetap dihormati (lihat workflow.LEGACY_EQUIVALENT) supaya user
# yang sudah punya izin tidak kehilangan akses saat fitur ini dipasang.
from erpnext_custom.workflow import WORKFLOW_ROLES
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


# CATATAN: field "Reimbursement Account" di Accounts Settings DIHAPUS (2026-07-15).
# Desain final jurnal EN reimburse: kredit tetap Hutang Supplier; yang berbeda sisi
# DEBIT — memakai Expense Class.reimburse_account (field di master Expense Class,
# app erp). Definisi lama dibuang dari sini dan field DB-nya di-drop lewat
# _drop_obsolete supaya migrate tidak menghidupkannya lagi.


def after_migrate():
    _drop_obsolete()
    create_custom_fields(INVOICE_FIELDS, ignore_validate=True)
    create_custom_fields(PURCHASE_FIELDS, ignore_validate=True)
    create_custom_fields(PAYMENT_FIELDS, ignore_validate=True)
    create_custom_fields(BANK_FIELDS, ignore_validate=True)
    create_custom_fields(MASTER_FIELDS, ignore_validate=True)
    create_custom_fields(BRANCH_FIELDS, ignore_validate=True)
    create_custom_fields(PRINT_SETTINGS_FIELDS, ignore_validate=True)
    create_custom_fields(SELLING_SETTINGS_FIELDS, ignore_validate=True)
    create_custom_fields(ITEM_FIELDS, ignore_validate=True)
    # Singleton Print Settings.invoice_title HARUS kosong: kalau terisi, ia menutupi
    # judul per-dokumen (custom_invoice_title) pada render tanpa sidebar (PDF/email).
    # Field sidebar print HANYA "slot" supaya sidebar punya kontrolnya; nilai persistennya
    # per-dokumen di Sales Invoice.custom_*. Singleton Print Settings WAJIB kosong: kalau
    # terisi, ia menutupi nilai per-dokumen pada render tanpa sidebar (PDF/email).
    for _fn in ("invoice_title", "print_as_currency", "printed_by"):
        if frappe.db.get_single_value("Print Settings", _fn):
            frappe.db.set_single_value("Print Settings", _fn, "")
    if frappe.db.get_single_value("Print Settings", "watermark_paid"):
        frappe.db.set_single_value("Print Settings", "watermark_paid", 0)
    _setup_sales_invoice_list_columns()
    _seed_company_code()
    _ensure_settlement_mode_of_payment()
    _reset_hidden("Sales Invoice")
    for fn in HIDE_FIELDS:
        _hide("Sales Invoice", fn)
    # Section Cost Center dibuka (bawaan collapsible): isinya tinggal satu field yang memang
    # perlu diisi user, jadi tidak ada gunanya menyembunyikannya di balik satu klik.
    _field_prop("Sales Invoice", "accounting_dimensions_section", "collapsible", "0", "Check")
    _field_prop("Sales Invoice", "accounting_dimensions_section", "label", "Cost Center", "Data")
    # Reimburse: baris Items DITURUNKAN dari Reimburse Items tiap save (_sync_reimburse_items),
    # jadi grid-nya disembunyikan — isian manual di situ hanya akan tertimpa.
    _field_prop("Sales Invoice", "items", "depends_on",
                "eval:doc.custom_invoice_behavior!='Reimburse'", "Data")
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
    # Layout revamp: susun ulang field core+custom ke section Information / Currency /
    # From-To / Account / Amount / Pending Cash / Payment Item / Additional.
    import json as _json
    _set_doctype_prop("Payment Entry", "field_order", _json.dumps(PE_FIELD_ORDER), "Small Text")
    # Penomoran PV/RV — pola hidup di naming series supaya bisa diedit user lewat
    # Document Naming Settings (komponen dihitung di CMIPaymentEntry.autoname).
    _field_prop("Payment Entry", "naming_series", "options", PE_NAMING_SERIES, "Small Text")
    _field_prop("Payment Entry", "naming_series", "default", PE_NAMING_SERIES, "Small Text")
    # Currency default = default currency system (Global Defaults), dinamis per deployment.
    _field_prop("Payment Entry", "paid_from_account_currency", "default",
                frappe.defaults.get_global_default("currency") or "IDR", "Data")
    _setup_payment_entry_list_columns()
    _backfill_payment_entry_references()  # setelah kolom list + custom field pasti ada
    for dt, fn, prop, val, pt in PAYMENT_PROPS:
        _field_prop(dt, fn, prop, val, pt)
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
    _setup_gl_entry_title()
    # Tabel Items (produk) WAJIB, KECUALI Invoice Type = Reimburse (nilainya di
    # custom_reimburse_items, tabel Items sengaja kosong). mandatory_depends_on = hanya
    # wajib saat tabel produk dipakai (non-Reimburse).
    # Section tabel items sudah berlabel "Items" secara core (`items_section`) — JANGAN relabel
    # `section_break_42` (itu sub-divider di dalamnya; kalau diberi label jadi "Items" dobel).
    _field_prop("Sales Invoice", "items", "reqd", "0", "Check")
    _field_prop("Sales Invoice", "items", "mandatory_depends_on",
                'eval:doc.custom_invoice_behavior != "Reimburse" && doc.custom_invoice_behavior != "Debit Note"', "Small Text")
    # Tabel Items disembunyikan saat tipe tidak memakainya, supaya user tak sempat mengisi tabel
    # yang nanti dibuang saat save (_clear_unused_tables):
    #   Reimburse            -> pakai custom_reimburse_items
    #   Debit Note + Manual  -> pakai custom_dn_items
    #   Debit Note (mode blm dipilih) -> dua-duanya hidden (user HARUS pilih dulu)
    _field_prop("Sales Invoice", "items", "depends_on",
                'eval:doc.custom_invoice_behavior != "Reimburse" && '
                '(doc.custom_invoice_behavior != "Debit Note" || doc.custom_dn_input_mode == "Item")',
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
    # Item: kolom item tunggal di grid menampilkan "code - name". title_field=item_name
    # (bawaan) + show_title_field_in_link -> link menampilkan nama di samping kode; item_name
    # ditambah ke search_fields supaya bisa dicari lewat nama, bukan cuma kode.
    _set_doctype_prop("Item", "show_title_field_in_link", "1", "Check")
    _set_doctype_prop("Item", "search_fields", "item_name,item_group", "Small Text")
    # Cost Center: dropdown-nya SATU baris. search_fields bawaan (parent_cost_center, is_group)
    # dipakai jadi baris deskripsi ("PT CMI - PC, ..."), padahal parent-nya sama untuk semua
    # cost center di sini — jadi baris itu cuma bising, tidak membedakan pilihan. Nama cost
    # center sudah memuat teks yang dicari user, jadi pencarian tidak berkurang.
    _set_doctype_prop("Cost Center", "search_fields", "", "Small Text")
    frappe.db.commit()  # kunci Property Setter penomoran DULU sebelum langkah opsional di bawah
    # Workflow Validate/Void: role + pencabutan submit/cancel + embed Client Script (DB-level,
    # tidak ikut git → disinkron di sini supaya `bench migrate` men-deploy-nya ke server).
    # NON-FATAL: kalau salah satu gagal (mis. path file beda / permission), JANGAN batalkan
    # migrate — kalau after_migrate throw, Frappe rollback dan Property Setter penomoran di atas
    # ikut hilang → invoice jadi bernomor polos "00001". Karena itu tiap langkah di-guard.
    for _label, _step in (
        ("remove_naming_rules", lambda: _remove_conflicting_naming_rules("Sales Invoice")),
        ("ensure_roles", lambda: _ensure_roles(INVOICE_ROLES + WORKFLOW_ROLES)),
        ("revoke_submit_cancel", lambda: _revoke_submit_cancel("Sales Invoice")),
        ("client_script", _ensure_sales_invoice_client_script),
        # Invoice Type dinamis: isi default kalau tabel Selling Settings kosong, lalu
        # sinkronkan opsi Select custom_invoice_type / _type_no dari config -> Property Setter.
        ("invoice_types_default", _ensure_invoice_types_default),
        ("invoice_types_sync", _sync_invoice_type_options),
        # Printed By dinamis: mirror pola Invoice Type di atas.
        ("printed_by_default", _ensure_printed_by_default),
        ("printed_by_sync", _sync_printed_by_options),
        ("submit_label", _ensure_submit_label),
    ):
        try:
            _step()
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="erpnext_custom after_migrate: %s failed" % _label)

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
INVOICE_AUTONAME = ".custom_invoice_type_no./.#####./CMI/.YY."

# Awali "\n" supaya mulai KOSONG (user harus memilih, tidak default ke opsi pertama).
INVOICE_TYPE_OPT = "\nExpedition\nDepo\nTrading\nReimburse"
INVOICE_TYPE_NO_OPT = "\nC/E\nC/EA\nT/E\nC/T\nIR"
UNIT_OPT = "%\nRp"


def _f(**kw):
    kw.setdefault("module", MODULE)
    return kw


INVOICE_FIELDS = {
    "Sales Invoice": [
        # ---------- Invoice Detail ----------
        _f(fieldname="custom_detail_sb", fieldtype="Section Break", label="Invoice Detail", insert_after="customer"),
        _f(fieldname="custom_invoice_type", fieldtype="Select", label="Invoice Type", options=INVOICE_TYPE_OPT, reqd=1, insert_after="custom_detail_sb"),
        _f(fieldname="custom_invoice_type_no", fieldtype="Select", label="Invoice Type No", options=INVOICE_TYPE_NO_OPT, reqd=1, insert_after="custom_invoice_type"),
        _f(fieldname="invoice_date", fieldtype="Date", label="Invoice Date", insert_after="custom_invoice_type_no"),
        _f(fieldname="custom_return_date", fieldtype="Date", label="Return Date", insert_after="invoice_date"),
        _f(fieldname="custom_detail_cb", fieldtype="Column Break", insert_after="custom_return_date"),
        _f(fieldname="term_of_payment", fieldtype="Date", label="Terms", insert_after="custom_detail_cb"),
        _f(fieldname="custom_voyage_no", fieldtype="Data", label="Voyage No", insert_after="term_of_payment"),
        _f(fieldname="custom_tax_no", fieldtype="Data", label="Tax No", insert_after="custom_voyage_no"),
        _f(fieldname="custom_adjustment", fieldtype="Currency", label="Adjustment", options="currency", insert_after="custom_tax_no"),
        _f(fieldname="dont_post_to_gl", fieldtype="Check", label="Don't Post to GL", insert_after="custom_adjustment"),

        # ---------- Reimburse (muncul saat InvoiceType = Reimburse) ----------
        _f(fieldname="custom_reimburse_sb", fieldtype="Section Break", label="Reimburse", insert_after="items", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),
        _f(fieldname="custom_get_expense_notes", fieldtype="Button", label="Get Expense Notes", insert_after="custom_reimburse_sb", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),
        _f(fieldname="custom_reimburse_items", fieldtype="Table", label="Reimburse Items", options="Reimburse Item", insert_after="custom_get_expense_notes", depends_on="eval:doc.custom_invoice_type=='Reimburse'"),

        # ---------- Amounts ---------- (setelah native total)
        # Baris 1: Amount Total
        _f(fieldname="custom_amount_sb", fieldtype="Section Break", label="Amounts", insert_after="total"),
        _f(fieldname="custom_amount_total", fieldtype="Currency", label="Amount Total", options="currency", read_only=1, insert_after="custom_amount_sb"),
        # Baris 2: Discount | PPh | Tax | Materai
        # Discount/PPh/Tax = field GABUNGAN (Data): user ketik "10%" ATAU "50000" -> auto ke Rp.
        # percent + amount per jenis = STORAGE TERSEMBUNYI (dikonsumsi server GL, validate, print
        # format). Diisi dari parsing field gabungan -> UI: sales_invoice.js (cmi_apply_input),
        # server: _apply_smart_inputs. JANGAN ditampilkan/diedit langsung.
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
        # Baris 3: Ignore Tax
        _f(fieldname="custom_row_ign_sb", fieldtype="Section Break", insert_after="custom_materai"),
        _f(fieldname="custom_ignore_tax", fieldtype="Check", label="Ignore Tax", insert_after="custom_row_ign_sb"),
        # Baris 4: Net Total
        _f(fieldname="custom_row_net_sb", fieldtype="Section Break", insert_after="custom_ignore_tax"),
        _f(fieldname="custom_net_total", fieldtype="Currency", label="Net Total", options="currency", read_only=1, bold=1, insert_after="custom_row_net_sb"),

        # ---------- Remark & Audit ----------
        _f(fieldname="custom_other_sb", fieldtype="Section Break", label="Remark & Audit", insert_after="custom_net_total"),
        _f(fieldname="custom_remarks", fieldtype="Small Text", label="Remarks", insert_after="custom_other_sb"),
        _f(fieldname="custom_attachment", fieldtype="Attach", label="Attachment", insert_after="custom_remarks"),
        _f(fieldname="custom_audit_cb", fieldtype="Column Break", insert_after="custom_attachment"),
        _f(fieldname="custom_validated_by", fieldtype="Data", label="Validated By", read_only=1, insert_after="custom_audit_cb"),
        _f(fieldname="custom_voided_by", fieldtype="Data", label="Voided By", read_only=1, insert_after="custom_validated_by"),

        # ---------- Connection (PL/SL -> BL -> Container) ----------
        _f(fieldname="custom_connection_tab", fieldtype="Tab Break", label="Connection", insert_after="custom_voided_by"),
        _f(fieldname="custom_conn_source_sb", fieldtype="Section Break", label="Source Documents", insert_after="custom_connection_tab"),
        _f(fieldname="custom_packing_list", fieldtype="Link", label="Packing List", options="Packing List", insert_after="custom_conn_source_sb"),
        _f(fieldname="custom_conn_cb", fieldtype="Column Break", insert_after="custom_packing_list"),
        _f(fieldname="custom_shipping_list", fieldtype="Link", label="Shipping List", options="Shipping List", insert_after="custom_conn_cb"),
        _f(fieldname="custom_bl_sb", fieldtype="Section Break", label="Bill of Lading", insert_after="custom_shipping_list"),
        _f(fieldname="custom_bl_no", fieldtype="Select", label="BL No", insert_after="custom_bl_sb",
           description="Pilih sumber dulu (Packing List / Shipping List); nomor BL terisi otomatis."),
        _f(fieldname="custom_containers_sb", fieldtype="Section Break", label="Containers", insert_after="custom_bl_no"),
        _f(fieldname="custom_reload_containers", fieldtype="Button", label="Reload Containers", insert_after="custom_containers_sb"),
        _f(fieldname="custom_pick_containers", fieldtype="Button", label="Pilih Containers (modal)", insert_after="custom_reload_containers",
           depends_on="eval:doc.custom_invoice_type && doc.custom_invoice_type!='Trading' && doc.custom_invoice_type!='Reimburse'"),
        _f(fieldname="custom_containers", fieldtype="Table", label="Containers", options="Invoice Container", insert_after="custom_pick_containers"),

        # ---------- Assistant + Email (terhubung ke agent yang handle job ini) ----------
        _f(fieldname="custom_tab_assistant", fieldtype="Tab Break", label="Assistant", insert_after="custom_containers"),
        _f(fieldname="custom_assistant_html", fieldtype="HTML", label="Assistant", insert_after="custom_tab_assistant"),
        _f(fieldname="custom_tab_email", fieldtype="Tab Break", label="Email", insert_after="custom_assistant_html"),
        _f(fieldname="custom_email_html", fieldtype="HTML", label="Email", insert_after="custom_tab_email"),
    ],
    "Sales Invoice Item": [
        _f(fieldname="custom_notes", fieldtype="Small Text", label="Notes", insert_after="item_name", in_list_view=1, columns=2),
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

# Field bawaan yang disembunyikan (TAMPIL: customer, currency, conversion_rate(Rate),
# items + field custom kita). Hidden per-field (hide section break TIDAK sembunyiin isinya).
HIDE_FIELDS = [
    # header noise
    "company", "company_address", "company_tax_id", "naming_series",
    "customer_name", "tax_id",
    "posting_date", "posting_time", "set_posting_time", "due_date",
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
    ("Sales Invoice", "type"), ("Sales Invoice", "custom_amount_cb"),
    ("Sales Invoice", "custom_discount_value"), ("Sales Invoice", "custom_discount_unit"),
    ("Sales Invoice", "custom_amount_tax_value"), ("Sales Invoice", "custom_amount_tax_unit"),
    ("Sales Invoice", "custom_amount_pph_value"), ("Sales Invoice", "custom_amount_pph_unit"),
    # Layout lama Amounts (kolom %/Amount terpisah) -> diganti field gabungan Discount/PPh/Tax.
    ("Sales Invoice", "custom_row_disc_sb"), ("Sales Invoice", "custom_cb_d1"),
    ("Sales Invoice", "custom_cb_d2"), ("Sales Invoice", "custom_cb_d3"),
    ("Sales Invoice", "custom_row_tax_sb"), ("Sales Invoice", "custom_cb_t1"),
    ("Sales Invoice", "custom_cb_t2"),
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
        frappe.db.set_value("Company", company, "custom_company_code", "CMI", update_modified=False)


def _drop_obsolete():
    for dt, fn in OBSOLETE:
        name = f"{dt}-{fn}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def after_install():
    after_migrate()


def after_migrate():
    _drop_obsolete()
    create_custom_fields(INVOICE_FIELDS, ignore_validate=True)
    create_custom_fields(PURCHASE_FIELDS, ignore_validate=True)
    create_custom_fields(MASTER_FIELDS, ignore_validate=True)
    _seed_company_code()
    _reset_hidden("Sales Invoice")
    for fn in HIDE_FIELDS:
        _hide("Sales Invoice", fn)
    # Purchase Order / Purchase Invoice: hide native + autoname seri (mirror SI).
    for dt, hide_list in (("Purchase Order", HIDE_PO), ("Purchase Invoice", HIDE_PI)):
        _reset_hidden(dt)
        for fn in hide_list:
            _hide(dt, fn)
        _field_prop(dt, "conversion_rate", "label", "Rate", "Data")
    _set_doctype_prop("Purchase Order", "autoname", PO_AUTONAME)
    _set_doctype_prop("Purchase Invoice", "autoname", PI_AUTONAME)
    for dt, fn, label in RELABEL:
        _field_prop(dt, fn, "label", label, "Data")
    for dt, fn, dflt in DEFAULTS:
        _field_prop(dt, fn, "default", dflt, "Data")
    for dt, fn, prop, val, pt in GRID:
        _field_prop(dt, fn, prop, val, pt)
    # autoname berbasis InvoiceTypeNo -> picker "Series" otomatis hilang juga.
    _set_doctype_prop("Sales Invoice", "autoname", INVOICE_AUTONAME)

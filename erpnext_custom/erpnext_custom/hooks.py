app_name = "erpnext_custom"
app_title = "ERPNext Custom"
app_publisher = "Cakra ERPNext Apps"
app_description = "Customizations for ERPNext core doctypes (no core edits)"
app_email = "admin@example.com"
app_license = "MIT"
app_version = "0.0.1"

required_apps = ["frappe", "erpnext"]

# --- Customizations owned by this app -------------------------------------
# Custom Fields / Property Setters / Print Formats tagged with the "ERPNext Custom"
# module travel with this app (exported as fixtures). erpnext core is never edited.
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Print Format", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Client Script", "filters": [["module", "=", "ERPNext Custom"]]},
]

# Server-side logic on core doctypes lives here, not in erpnext.
doc_events = {
	"Sales Invoice": {
		"before_validate": [
			"erpnext_custom.overrides.sales_invoice.before_validate",
			# branch_office diturunkan dari job (custom_shipping_list/custom_packing_list).
			"crm_cakra.api.permissions.set_branch_from_job",
		],
		"validate": "erpnext_custom.overrides.sales_invoice.validate",
		"before_update_after_submit": [
			"erpnext_custom.overrides.sales_invoice.sync_header_address",
			"erpnext_custom.overrides.sales_invoice._sync_shipping_list_nos",
		],
		"before_submit": "erpnext_custom.overrides.sales_invoice.guard_submit",
		"before_cancel": "erpnext_custom.overrides.sales_invoice.guard_cancel",
		# Jaga indeks pencarian Inv/Exp (`fin_index`) di Shipping/Packing List (app erp).
		"on_update": "erp.expedition.financials.on_sales_invoice_change",
		"on_submit": "erp.expedition.financials.on_sales_invoice_change",
		"on_cancel": "erp.expedition.financials.on_sales_invoice_change",
		"on_trash": "erp.expedition.financials.on_sales_invoice_trash",
		"after_delete": "erp.expedition.financials.after_sales_invoice_delete",
	},
	"Purchase Order": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		"validate": "erpnext_custom.overrides.purchasing.validate",
		# Submit/cancel HARUS lewat tombol Validate/Void (supaya role terjaga).
		"before_submit": "erpnext_custom.workflow.guard_submit",
		"before_cancel": "erpnext_custom.workflow.guard_cancel",
	},
	"Purchase Invoice": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		"validate": "erpnext_custom.overrides.purchasing.validate",
		# Submit/cancel HARUS lewat tombol Validate/Void (supaya role terjaga).
		"before_submit": "erpnext_custom.workflow.guard_submit",
		"before_cancel": "erpnext_custom.workflow.guard_cancel",
	},
	"Payment Entry": {
		"before_validate": "erpnext_custom.overrides.payment_entry.before_validate",
		"before_submit": "erpnext_custom.workflow.guard_submit",
		"before_cancel": "erpnext_custom.workflow.guard_cancel",
		"on_submit": "erpnext_custom.overrides.payment_entry.update_expense_note_paid_status",
		"on_cancel": "erpnext_custom.overrides.payment_entry.update_expense_note_paid_status",
	},
}
# Akses branch = NATIVE Frappe User Permission (allow=CMI Office). Sales Invoice &
# Payment Entry punya field branch_office (Link CMI Office) -> otomatis terfilter.

# Override controller core (Sales Invoice & Purchase Invoice: 'Don't Post to GL' + audit).
override_doctype_class = {
	"Payment Entry": "erpnext_custom.overrides.payment_entry.CMIPaymentEntry",
	"Sales Invoice": "erpnext_custom.overrides.sales_invoice.CMISalesInvoice",
	"Purchase Order": "erpnext_custom.overrides.purchasing.CMIPurchaseOrder",
	"Purchase Invoice": "erpnext_custom.overrides.purchasing.CMIPurchaseInvoice",
}

# Halaman Print: judul print out Sales Invoice persisten (Invoice Title tersimpan
# ke dokumen saat tombol Print ditekan).
page_js = {"print": "public/js/print_view.js"}

# List view Sales Invoice: kolom Created By / Assign To (formatter) + lebar kolom ID.
doctype_list_js = {"Sales Invoice": "public/js/sales_invoice_list.js"}

# Client script di form (Sales Invoice: InvoiceType->InvoiceTypeNo; PO/PI: tab Assistant+Email;
# Payment Entry: tombol "Add Items").
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Payment Entry": "public/js/payment_entry.js",
}

# Idempotent setup (custom fields created in code) runs on every migrate.
after_install = "erpnext_custom.install.after_install"
after_migrate = "erpnext_custom.install.after_migrate"

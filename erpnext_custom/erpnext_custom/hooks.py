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
]

# Server-side logic on core doctypes lives here, not in erpnext.
doc_events = {
	"Sales Invoice": {
		"before_validate": "erpnext_custom.overrides.sales_invoice.before_validate",
		"validate": "erpnext_custom.overrides.sales_invoice.validate",
	},
	"Purchase Order": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		"validate": "erpnext_custom.overrides.purchasing.validate",
	},
	"Purchase Invoice": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		"validate": "erpnext_custom.overrides.purchasing.validate",
	},
	"Payment Entry": {
		"before_validate": "erpnext_custom.overrides.payment_entry.before_validate",
	},
}

# Override controller core (Sales Invoice & Purchase Invoice: 'Don't Post to GL' + audit).
override_doctype_class = {
	"Sales Invoice": "erpnext_custom.overrides.sales_invoice.CMISalesInvoice",
	"Purchase Order": "erpnext_custom.overrides.purchasing.CMIPurchaseOrder",
	"Purchase Invoice": "erpnext_custom.overrides.purchasing.CMIPurchaseInvoice",
}

# Client script di form (Sales Invoice: InvoiceType->InvoiceTypeNo; PO/PI: tab Assistant+Email;
# Payment Entry: tombol "Tarik Expense Note").
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Payment Entry": "public/js/payment_entry.js",
}

# Idempotent setup (custom fields created in code) runs on every migrate.
after_install = "erpnext_custom.install.after_install"
after_migrate = "erpnext_custom.install.after_migrate"

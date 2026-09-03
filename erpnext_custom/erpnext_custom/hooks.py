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
			# PALING AWAL: set custom_invoice_behavior + tegakkan role/enabled/type_no —
			# behavior dibaca oleh logika before_validate berikutnya (clear tables, dll).
			"erpnext_custom.invoice_types.validate_invoice_type",
			"erpnext_custom.overrides.sales_invoice.before_validate",
			# branch_office diturunkan dari job (custom_shipping_list/custom_packing_list).
			"crm_cakra.api.permissions.set_branch_from_job",
		],
		"validate": [
			"erpnext_custom.overrides.sales_invoice.validate",
			# Invoice Type/Type No ikut membentuk nomor -> terkunci begitu invoice bernomor.
			"erp.expedition.numbering.guard_type_change",
		],
		"before_update_after_submit": [
			"erpnext_custom.overrides.sales_invoice.sync_header_address",
			"erpnext_custom.overrides.sales_invoice._sync_shipping_list_nos",
		],
		"before_submit": "erpnext_custom.overrides.sales_invoice.guard_submit",
		"before_cancel": "erpnext_custom.overrides.sales_invoice.guard_cancel",
		# Jaga indeks pencarian Inv/Exp (`fin_index`) di Shipping/Packing List (app erp).
		# auto_validate PALING AKHIR: ia men-submit dokumen, jadi handler lain harus
		# sudah selesai dengan dokumen yang masih draft.
		"on_update": [
			"erp.expedition.financials.on_sales_invoice_change",
			"erpnext_custom.workflow.auto_validate_reimburse",
		],
		"on_submit": "erp.expedition.financials.on_sales_invoice_change",
		"on_cancel": "erp.expedition.financials.on_sales_invoice_change",
		"on_trash": "erp.expedition.financials.on_sales_invoice_trash",
		"after_delete": "erp.expedition.financials.after_sales_invoice_delete",
	},
	"Purchase Order": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		# Type ikut membentuk nomor PO -> terkunci begitu PO bernomor.
		"validate": [
			"erpnext_custom.overrides.purchasing.validate",
			"erp.expedition.numbering.guard_type_change",
		],
		# Submit/cancel HARUS lewat tombol Validate/Void (supaya role terjaga).
		"before_submit": "erpnext_custom.workflow.guard_submit",
		"before_cancel": "erpnext_custom.workflow.guard_cancel",
	},
	"Purchase Invoice": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		"validate": "erpnext_custom.overrides.purchasing.validate",
		# Kolom "Purchases" di list Purchase Order diturunkan dari PI yang menunjuk PO itu.
		# on_update menutupi save & submit; cancel TIDAK lewat sana (run_post_save_methods
		# hanya memanggil on_cancel), dan after_delete dipakai karena baris child baru
		# hilang sesudah dokumennya terhapus.
		"on_update": "erpnext_custom.overrides.purchasing.sync_purchase_order_invoices",
		"on_cancel": "erpnext_custom.overrides.purchasing.sync_purchase_order_invoices",
		"after_delete": "erpnext_custom.overrides.purchasing.sync_purchase_order_invoices",
		# Submit/cancel HARUS lewat tombol Validate/Void (supaya role terjaga).
		"before_submit": "erpnext_custom.workflow.guard_submit",
		# Sparepart ber-Vehicle: sama seperti PR, tapi hanya kalau PI ini yang menaikkan
		# stok (update_stock). PI turunan PR tidak menyentuh jalur ini.
		"on_submit": "erpnext_custom.sparepart.issue_on_submit",
		# Material Issue-nya dibatalkan DULU, kalau tidak cancel PI ditolak (stok minus).
		"before_cancel": [
			"erpnext_custom.workflow.guard_cancel",
			"erpnext_custom.sparepart.cancel_issue_before_cancel",
		],
	},
	"Purchase Receipt": {
		# PO memilih gudang, PR memilih rak di dalamnya. Dipasang dua kali karena
		# ERPNext mengisi ulang rak dari Default Warehouse Item di antaranya.
		"before_validate": "erpnext_custom.rack_suggest.split_gudang_from_rack",
		"validate": "erpnext_custom.rack_suggest.split_gudang_from_rack",
		"before_submit": "erpnext_custom.workflow.guard_submit",
		# Sparepart ber-Vehicle: stok yang barusan diterima langsung di-issue ke beban.
		"on_submit": "erpnext_custom.sparepart.issue_on_submit",
		# Material Issue-nya dibatalkan DULU, kalau tidak cancel PR ditolak (stok minus).
		"before_cancel": [
			"erpnext_custom.workflow.guard_cancel",
			"erpnext_custom.sparepart.cancel_issue_before_cancel",
		],
	},
	# Material Issue turunan PR hanya boleh dibatalkan lewat PR-nya (lihat sparepart.py).
	"Stock Entry": {
		"before_cancel": "erpnext_custom.sparepart.guard_issue_cancel",
	},
	"Pick List": {
		"validate": "erpnext_custom.picking_list.picking_list.validate_stock_availability",
		"before_submit": "erpnext_custom.picking_list.picking_list.validate_stock_availability",
	},
	"Sales Order": {
		"before_validate": "erpnext_custom.sales_order.sales_order.before_validate",
		"validate": "erpnext_custom.sales_order.sales_order.validate",
	},
	"Delivery Note": {
		"before_validate": "erpnext_custom.delivery_note.delivery_note.before_validate",
		"validate": "erpnext_custom.delivery_note.delivery_note.validate",
	},
	"Payment Entry": {
		"before_validate": "erpnext_custom.overrides.payment_entry.before_validate",
		"before_submit": "erpnext_custom.workflow.guard_submit",
		"before_cancel": "erpnext_custom.workflow.guard_cancel",
		# Kolom Payment di list Sales Invoice & Expense Note: ikut draft, jadi on_update juga.
		# on_update_after_submit terpisah: save PV yang SUDAH submit tidak memicu on_update.
		"on_update": "erpnext_custom.overrides.payment_entry.sync_payment_links",
		"on_update_after_submit": "erpnext_custom.overrides.payment_entry.sync_payment_links",
		# after_delete, bukan on_trash: baris referensinya baru benar-benar hilang setelah
		# dokumen terhapus, jadi hitungan on_trash masih memuat PV yang sedang dihapus.
		"after_delete": "erpnext_custom.overrides.payment_entry.sync_payment_links",
		"on_submit": [
			"erpnext_custom.overrides.payment_entry.update_expense_note_paid_status",
			"erpnext_custom.overrides.payment_entry.sync_payment_links",
		],
		"on_cancel": [
			"erpnext_custom.overrides.payment_entry.update_expense_note_paid_status",
			"erpnext_custom.overrides.payment_entry.sync_payment_links",
		],
	},
	# Reimburse -> auto Validate saat save (flag di ERPNext Custom Setting).
	"Expense Note": {
		"before_validate": "erpnext_custom.workflow.auto_validate_reimburse",
	},
	# Nama rak ber-skema A1/B3 -> auto-isi urutan jarak + level (lihat rack_suggest.py).
	"Warehouse": {
		"validate": "erpnext_custom.rack_suggest.set_position_from_name",
	},
	"Selling Settings": {
		"validate": "erpnext_custom.printed_by.validate_single_default",
		"on_update": "erpnext_custom.printed_by.sync_printed_by_options",
	},
	# Config Invoice Type berubah -> sinkronkan opsi Select + bersihkan cache.
	"ERPNext Custom Setting": {
		"on_update": "erpnext_custom.invoice_types.sync_invoice_type_options",
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
page_js = {
	"print": "public/js/print_view.js",
	# Kolom izin "Cancel" dibaca sebagai "Void" — hanya di halaman ini (lihat filenya).
	"permission-manager": "public/js/permission_manager.js",
}

# List view: Sales Invoice = kolom Created By / Assign To (formatter) + lebar kolom ID;
# Payment Entry = menu Actions Validate/Invalidate & Void/Unvoid (erpnext_custom.workflow).
doctype_list_js = {
	"Sales Invoice": "public/js/sales_invoice_list.js",
	"Purchase Order": "public/js/purchase_order_list.js",
	"Purchase Invoice": "public/js/purchase_invoice_list.js",
	"Purchase Receipt": "public/js/purchase_receipt_list.js",
	"Payment Entry": "public/js/payment_entry_list.js",
}

# Query bawaan hanya menampilkan Pick List yang setiap item-nya terhubung ke
# Sales Order. CMI juga mengizinkan Pick List Delivery manual.
override_whitelisted_methods = {
	"erpnext.stock.doctype.pick_list.pick_list.get_pick_list_query":
		"erpnext_custom.delivery_note.delivery_note.get_pick_list_query",
}

# Client script di form (Sales Invoice: InvoiceType->InvoiceTypeNo; PO/PI: tab Assistant+Email;
# Payment Entry: tombol "Add Items").
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Pick List": "public/js/picking_list.js",
	"Sales Order": "public/js/sales_order.js",
	"Delivery Note": "public/js/delivery_note.js",
	"Payment Entry": "public/js/payment_entry.js",
}

# Sembunyikan label grid yang sengaja dikosongkan (lihat css-nya).
app_include_css = "/assets/erpnext_custom/css/grid_label.css?v=4"
# Aksi bulk Validate/Void di list view — dipakai bersama Sales Invoice & Payment Entry,
# jadi harus sudah termuat sebelum doctype_list_js masing-masing jalan.
app_include_js = [
	"/assets/erpnext_custom/js/workflow_list.js?v=3",
	# menu Validate/Invalidate/Void/Unvoid di form PO/PR/PI (izin per doctype)
	"/assets/erpnext_custom/js/workflow_form.js?v=2",
	# angka notifikasi belum dibaca di ikon bel sidebar (nambal bug upstream, lihat filenya)
	"/assets/erpnext_custom/js/notification_badge.js?v=1",
	# sidebar desk kosong saat halaman dibuka langsung (nambal bug upstream, lihat filenya)
	"/assets/erpnext_custom/js/sidebar_fallback.js?v=1",
]

# Idempotent setup (custom fields created in code) runs on every migrate.
after_install = "erpnext_custom.install.after_install"
after_migrate = "erpnext_custom.install.after_migrate"

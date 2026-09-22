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
# Custom Field dipecah per area jadi custom_field_*.json (aslinya satu file 21.000 baris).
# Impor aman: import_fixtures membaca SEMUA *.json di folder ini. Yang perlu diingat,
# `bench export-fixtures` menulis balik SATU file `custom_field.json` per doctype — kalau
# itu dijalankan, pecahan di bawah jadi basi dan isinya ganda. Pecah ulang setelah export.
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Print Format", "filters": [["module", "=", "ERPNext Custom"]]},
	{"dt": "Client Script", "filters": [["module", "=", "ERPNext Custom"]]},
]

# Daftar Item Group per lingkup ikut boot: depends_on field Vehicle dievaluasi di client
# dan tidak bisa memanggil server.
extend_bootinfo = "erpnext_custom.item_scope.boot"

# Server-side logic on core doctypes lives here, not in erpnext.
doc_events = {
	# Nama lampiran email yang lebih panjang dari kolom File.file_name membatalkan
	# SELURUH penarikan email di batch itu, bukan cuma satu pesan (lihat filenya).
	"File": {
		"before_insert": "erpnext_custom.mail_inbox.trim_file_name",
	},
	# Tabel "Aturan Kemasan per Bin" di Stock Settings > tab Warehouse: angka nol dan
	# item kembar ditolak saat mengetiknya, Total per Bin dihitung di sana juga.
	# Tanpa penjaga ini, 1/(0*0) meledak di SETIAP simpan dokumen gudang.
	"Stock Settings": {
		"validate": "erpnext_custom.bin_layout.validate_packing_rules",
	},
	# Aset di kategori bercentang "Kendaraan" dipasangkan 1:1 dengan record Vehicle (Fleet).
	# Vehicle dibuat MANUAL lewat tombol "Buat Vehicle" di form aset (public/js/asset.js),
	# hook di bawah cuma menjaga tautan baliknya. Lihat erpnext_custom/vehicle_asset.py.
	"Asset": {
		"on_trash": "erpnext_custom.vehicle_asset.delete_vehicle",
	},
	"Vehicle": {
		"after_insert": "erpnext_custom.vehicle_asset.link_asset",
		"on_update": "erpnext_custom.vehicle_asset.link_asset",
		"on_trash": "erpnext_custom.vehicle_asset.unlink_asset",
	},
	# Kolom bantu di grid jadwal penyusutan: penyusutan tetap per periode + tanggal
	# versi "01 Mar 2026".
	"Asset Depreciation Schedule": {
		"validate": "erpnext_custom.asset_depreciation.set_display_columns",
	},
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
			"erpnext_custom.workflow.auto_validate",
		],
		"on_submit": [
			"erp.expedition.financials.on_sales_invoice_change",
			# Aset yang dijual: nomor invoicenya disalin ke record aset.
			"erpnext_custom.asset_disposal.link_sales_invoice",
			# Cuma berefek kalau SI ini yang mengurangi stok (update_stock).
			"erpnext_custom.bin_ledger.doc_hook",
		],
		"on_cancel": [
			"erp.expedition.financials.on_sales_invoice_change",
			"erpnext_custom.asset_disposal.link_sales_invoice",
			"erpnext_custom.bin_ledger.doc_hook",
		],
		"on_trash": "erp.expedition.financials.on_sales_invoice_trash",
		"after_delete": "erp.expedition.financials.after_sales_invoice_delete",
	},
	# Proforma Invoice = doctype sendiri (tabel sendiri), tapi field & aturan isinya cermin
	# Sales Invoice — jadi hook yang sama dipakai ulang. Yang SENGAJA tidak ikut: financials
	# (proforma bukan revenue Master Job), auto_validate, dan semua yang menyangkut jurnal.
	"Proforma Invoice": {
		"before_validate": [
			"erpnext_custom.invoice_types.validate_invoice_type",
			"erpnext_custom.overrides.sales_invoice.before_validate",
			"crm_cakra.api.permissions.set_branch_from_job",
		],
		"validate": "erpnext_custom.overrides.sales_invoice.validate",
		"before_update_after_submit": [
			"erpnext_custom.overrides.sales_invoice.sync_header_address",
			"erpnext_custom.overrides.sales_invoice._sync_shipping_list_nos",
		],
	},
	"Purchase Order": {
		"before_validate": "erpnext_custom.overrides.purchasing.before_validate",
		# Type ikut membentuk nomor PO -> terkunci begitu PO bernomor.
		"validate": [
			"erpnext_custom.overrides.purchasing.validate",
			"erp.expedition.numbering.guard_type_change",
		],
		# "Update Items" pada dokumen yang SUDAH submit tidak lewat `validate`, jadi field
		# tampilan (SubTotal/Amount Tax/Net Total) harus disegarkan di sini.
		"on_update_after_submit": "erpnext_custom.overrides.purchasing.refresh_display_after_submit",
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
		# Jadi list, BUKAN key kedua: dict literal dengan "on_cancel" dua kali akan
		# diam-diam membuang yang pertama, dan kolom Purchases di list PO ikut mati.
		"on_cancel": [
			"erpnext_custom.overrides.purchasing.sync_purchase_order_invoices",
			"erpnext_custom.bin_ledger.doc_hook",
		],
		"after_delete": "erpnext_custom.overrides.purchasing.sync_purchase_order_invoices",
		# "Update Items" pada dokumen yang SUDAH submit tidak lewat `validate`, jadi field
		# tampilan (SubTotal/Amount Tax/Net Total) harus disegarkan di sini.
		"on_update_after_submit": "erpnext_custom.overrides.purchasing.refresh_display_after_submit",
		# Submit/cancel HARUS lewat tombol Validate/Void (supaya role terjaga).
		"before_submit": "erpnext_custom.workflow.guard_submit",
		# bin_ledger DULUAN, alasan yang sama seperti di Purchase Receipt.
		"on_submit": [
			"erpnext_custom.bin_ledger.doc_hook",
			# Sparepart ber-Vehicle: sama seperti PR, tapi hanya kalau PI ini yang menaikkan
			# stok (update_stock). PI turunan PR tidak menyentuh jalur ini.
			"erpnext_custom.sparepart.issue_on_submit",
		],
		# Material Issue-nya dibatalkan DULU, kalau tidak cancel PI ditolak (stok minus).
		"before_cancel": [
			"erpnext_custom.workflow.guard_cancel",
			"erpnext_custom.sparepart.cancel_issue_before_cancel",
		],
	},
	"Purchase Receipt": {
		"before_submit": "erpnext_custom.workflow.guard_submit",
		# URUTAN PENTING: bin_ledger DULUAN. sparepart.issue_on_submit men-submit Stock
		# Entry Material Issue di dalam on_submit ini; kalau bin_ledger belum membukukan
		# penerimaannya, Material Issue itu memakan lapisan FIFO milik stok lama.
		"on_submit": [
			"erpnext_custom.bin_ledger.doc_hook",
			# Sparepart ber-Vehicle: stok yang barusan diterima langsung di-issue ke beban.
			"erpnext_custom.sparepart.issue_on_submit",
		],
		"on_cancel": "erpnext_custom.bin_ledger.doc_hook",
		# Material Issue-nya dibatalkan DULU, kalau tidak cancel PR ditolak (stok minus).
		"before_cancel": [
			"erpnext_custom.workflow.guard_cancel",
			"erpnext_custom.sparepart.cancel_issue_before_cancel",
		],
	},
	"Stock Entry": {
		# Stock Entry turunan dokumen lain hanya boleh dibatalkan lewat dokumen pemiliknya:
		# Material Issue milik PR (sparepart.py).
		"before_cancel": [
			"erpnext_custom.sparepart.guard_issue_cancel",
		],
		"on_submit": "erpnext_custom.bin_ledger.doc_hook",
		"on_cancel": "erpnext_custom.bin_ledger.doc_hook",
	},
	# Opname: tabBin diset langsung, jadi selisihnya diukur dan ditutup seperti biasa.
	"Stock Reconciliation": {
		"on_submit": "erpnext_custom.bin_ledger.doc_hook",
		"on_cancel": "erpnext_custom.bin_ledger.doc_hook",
	},
	"Pick List": {
		"validate": [
			"erpnext_custom.picking_list.picking_list.validate_stock_availability",
			"erpnext_custom.picking_list.picking_list.validate_pick_bins",
		],
		"before_submit": [
			"erpnext_custom.picking_list.picking_list.validate_stock_availability",
			"erpnext_custom.picking_list.picking_list.validate_pick_bins",
		],
		# Rak -> staging keluar, cermin Goods Receive yang arahnya sebaliknya.
		# Pindah bin murni: nol stok, nol jurnal, total per gudang tidak berubah.
		# Delivery Note turunannya mengambil dari staging keluar (bin_ledger._hints).
		"on_submit": "erpnext_custom.picking_list.picking_list.move_to_pick_staging",
		"on_cancel": "erpnext_custom.picking_list.picking_list.move_back_from_pick_staging",
	},
	"Sales Order": {
		"before_validate": "erpnext_custom.sales_order.sales_order.before_validate",
		"validate": "erpnext_custom.sales_order.sales_order.validate",
	},
	"Delivery Note": {
		"before_validate": "erpnext_custom.delivery_note.delivery_note.before_validate",
		"validate": "erpnext_custom.delivery_note.delivery_note.validate",
		"on_submit": "erpnext_custom.bin_ledger.doc_hook",
		"on_cancel": "erpnext_custom.bin_ledger.doc_hook",
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
			"erpnext_custom.overrides.purchasing.sync_po_advance_paid",
		],
		"on_cancel": [
			"erpnext_custom.overrides.payment_entry.update_expense_note_paid_status",
			"erpnext_custom.overrides.payment_entry.sync_payment_links",
			"erpnext_custom.overrides.purchasing.sync_po_advance_paid",
		],
	},
	# Uang muka lewat Pending Cash (Modul = Purchase Order) menggerakkan Advance Paid di PO.
	# on_update saja sudah menangkap semuanya: mark_paid / unmark_paid / void / unvoid semua
	# lewat doc.save() (lihat erpnext_custom.workflow).
	"Pending Cash": {
		"on_update": "erpnext_custom.overrides.purchasing.sync_po_advance_paid",
		"on_trash": "erpnext_custom.overrides.purchasing.sync_po_advance_paid",
	},
	# Refund kasbon uang muka: uangnya kembali, jadi Advance Paid PO harus turun.
	# Hook terpisah karena sync_refunded menulis ke induknya lewat frappe.db.set_value,
	# yang TIDAK memicu on_update Pending Cash di atas.
	"Pending Cash Refund": {
		"on_update": "erpnext_custom.overrides.purchasing.sync_po_advance_paid",
		"on_trash": "erpnext_custom.overrides.purchasing.sync_po_advance_paid",
	},
	# Auto Validate saat save: reimburse, atau semua Expense Item pas dengan estimation
	# (dua flag terpisah di ERPNext Custom Setting).
	"Expense Note": {
		"before_validate": "erpnext_custom.workflow.auto_validate",
	},
	# Jurnal otomatis core (depresiasi, pelepasan aset, selisih kurs) ditandai supaya
	# list Journal Entry bisa menyisakan jurnal adjust manual saja.
	"Journal Entry": {
		"before_validate": "erpnext_custom.journal_entry.mark_system_generated",
	},
	# Jaring pengaman: SLE yang lahir di luar submit/cancel dokumen (jalur tak terduga)
	# tetap menutup selisih bin. Jalur normal sudah ditangani doc_hook per dokumen.
	# Layout rak/bin sengaja TIDAK menyentuh stok maupun jurnal; lihat bin_ledger.py.
	"Stock Ledger Entry": {
		"on_submit": "erpnext_custom.bin_ledger.sle_hook",
	},
	"Selling Settings": {
		"validate": "erpnext_custom.printed_by.validate_single_default",
		"on_update": "erpnext_custom.printed_by.sync_printed_by_options",
	},
	# Config berubah -> sinkronkan opsi Select yang diturunkan darinya + bersihkan cache.
	"ERPNext Custom Setting": {
		"on_update": [
			"erpnext_custom.invoice_types.sync_invoice_type_options",
			# pilihan Modul di section Connection Pending Cash (tab Finance)
			"erp.fico.doctype.pending_cash.pending_cash.sync_connection_module_options",
		],
	},
}
# Akses branch = NATIVE Frappe User Permission (allow=CMI Office). Sales Invoice &
# Payment Entry punya field branch_office (Link CMI Office) -> otomatis terfilter.

# Override controller core (Sales Invoice & Purchase Invoice: 'Don't Post to GL' + audit).
override_doctype_class = {
	"Payment Entry": "erpnext_custom.overrides.payment_entry.CMIPaymentEntry",
	# Akun yang kirim lewat Microsoft Graph tidak punya sesi SMTP untuk diuji saat simpan.
	"Email Account": "erpnext_custom.graph_mail.CMIEmailAccount",
	"Sales Invoice": "erpnext_custom.overrides.sales_invoice.CMISalesInvoice",
	"Purchase Order": "erpnext_custom.overrides.purchasing.CMIPurchaseOrder",
	"Purchase Invoice": "erpnext_custom.overrides.purchasing.CMIPurchaseInvoice",
}

# Kirim email keluar lewat Microsoft Graph untuk Email Account yang diberi Connected App
# Graph (tenant Microsoft memblokir SMTP AUTH). Akun lain tetap lewat SMTP, dilayani di
# fungsi yang sama karena hook ini menggantikan seluruh jalur kirim bawaan.
override_email_send = "erpnext_custom.graph_mail.send"

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
	# Default filter: cuma jurnal adjust manual, jurnal otomatis disembunyikan.
	"Journal Entry": "public/js/journal_entry_list.js",
}

# Query bawaan hanya menampilkan Pick List yang setiap item-nya terhubung ke
# Sales Order. CMI juga mengizinkan Pick List Delivery manual.
override_whitelisted_methods = {
	"erpnext.stock.doctype.pick_list.pick_list.get_pick_list_query":
		"erpnext_custom.delivery_note.delivery_note.get_pick_list_query",
	# Tombol "Search for ..." balas 500 kalau index global search memuat baris dokumen yang
	# sudah dihapus (bug upstream); penggantinya membuang baris hantu itu dulu.
	"frappe.utils.global_search.search": "erpnext_custom.quick_search.global_search",
}

# Client script di form (Sales Invoice: InvoiceType->InvoiceTypeNo; PO/PI: tab Assistant+Email;
# Payment Entry: tombol "Add Items").
doctype_js = {
	"Asset": "public/js/asset.js",
	"User": "public/js/user.js",
	"Sales Invoice": "public/js/sales_invoice.js",
	# Proforma memakai file form Sales Invoice yang SAMA (semua handler-nya didaftarkan ke
	# dua doctype, lihat cmi_inv_on di filenya) + satu file kecil untuk controller hitung
	# sisi client.
	"Proforma Invoice": ["public/js/sales_invoice.js", "public/js/proforma_invoice.js"],
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Purchase Receipt": "public/js/purchase_receipt.js",
	"Pick List": "public/js/picking_list.js",
	"Sales Order": "public/js/sales_order.js",
	"Delivery Note": "public/js/delivery_note.js",
	"Payment Entry": "public/js/payment_entry.js",
	"Stock Entry": "public/js/stock_entry.js",
	"Repost Accounting Ledger": "public/js/repost_accounting_ledger.js",
	# GL Entry cuma satu baris; file ini menggambar seluruh voucher-nya ala Journal Entry.
	"GL Entry": "public/js/gl_entry.js",
}

# Sembunyikan label grid yang sengaja dikosongkan (lihat css-nya).
app_include_css = [
	"/assets/erpnext_custom/css/grid_label.css?v=10",
	# lantai lebar kolom Subject: nomor dokumen panjang terpotong (lihat filenya)
	"/assets/erpnext_custom/css/list_subject.css?v=2",
]
# Aksi bulk Validate/Void di list view — dipakai bersama Sales Invoice & Payment Entry,
# jadi harus sudah termuat sebelum doctype_list_js masing-masing jalan.
app_include_js = [
	"/assets/erpnext_custom/js/workflow_list.js?v=4",
	# menu Validate/Invalidate/Void/Unvoid di form PO/PR/PI (izin per doctype)
	"/assets/erpnext_custom/js/workflow_form.js?v=3",
	# angka notifikasi belum dibaca di ikon bel sidebar (nambal bug upstream, lihat filenya)
	"/assets/erpnext_custom/js/notification_badge.js?v=9",
	# sidebar desk kosong saat halaman dibuka langsung (nambal bug upstream, lihat filenya)
	"/assets/erpnext_custom/js/sidebar_fallback.js?v=3",
	# kolom query report tidak mengisi sisa lebar layar (nambal bug upstream, lihat filenya)
	"/assets/erpnext_custom/js/report_fit_width.js?v=2",
	# kotak search desk (Ctrl+K) ikut mencari nomor transaksi & isian dokumennya
	"/assets/erpnext_custom/js/awesomebar_documents.js?v=1",
]

# Idempotent setup (custom fields created in code) runs on every migrate.
after_install = "erpnext_custom.install.after_install"
after_migrate = "erpnext_custom.install.after_migrate"

app_name = "erp"
app_title = "ERP CMI"
app_publisher = "CMI"
app_description = "Custom ERP CMI"
app_email = "admin@cakraindo.com"
app_license = "mit"

# Installation
# ------------
after_install = "erp.install.after_install"
after_migrate = "erp.install.after_migrate"

# Kolom ID/Name di list view diberi lebar minimum (CSS satu aturan, aman).
app_include_css = "/assets/erp/css/list_id_fit.css?v=4"

# Aksi Validate/Pay Pending Cash: dipakai form DAN list view, sedangkan doctype JS tidak
# ikut termuat di halaman list -> dimuat app-wide supaya dialognya satu sumber.
app_include_js = "/assets/erp/js/pending_cash_actions.js?v=3"

# Fixtures: master "tipe" reference (tanpa link ke Account/Cost Center/Company),
# ikut terbawa otomatis saat install supaya tak perlu input ulang.
fixtures = [
	{"dt": "Container Size"},
	{"dt": "Cargo"},
	{"dt": "Shipment Type"},
	{"dt": "Packing List Type"},
	{"dt": "Expense Note Type"},
	{"dt": "Pending Cash Type"},
	{"dt": "Jenis Karantina"},
]

naming_series_variables = {
	"cmi_type_code": "erp.expedition.numbering.parse_type_code",      # kode tipe (master Type)
	"cmi_company_abbr": "erp.expedition.numbering.parse_company_abbr",  # abbr company (Sales Invoice)
	"cmi_yy": "erp.expedition.numbering.parse_yy",                    # tahun 2-digit dari TANGGAL dokumen
	"cmi_yyyy": "erp.expedition.numbering.parse_yyyy",                # tahun 4-digit dari TANGGAL dokumen
	"cmi_inv_counter": "erp.expedition.numbering.parse_inv_counter",  # counter tengah reset-tahunan (Sales Invoice)
}

# Jaga indeks pencarian Inv/Exp (`fin_index`) di Shipping/Packing List tetap sinkron saat
# Expense Note berubah/terhapus. (Sales Invoice ditangani di erpnext_custom — doctype core.)
doc_events = {
	"Expense Note": {
		"on_update": "erp.expedition.financials.on_expense_note_change",
		"after_delete": "erp.expedition.financials.on_expense_note_change",
		# branch_office diturunkan dari Shipping/Packing List yang tertaut (job).
		"before_validate": "crm_cakra.api.permissions.set_branch_from_job",
	},
	# branch_office job diturunkan dari branch Type-nya (Shipment Type / Packing List Type).
	"Shipping List": {"before_validate": "crm_cakra.api.permissions.set_branch_from_job"},
	"Packing List": {"before_validate": "crm_cakra.api.permissions.set_branch_from_job"},
}
# Akses branch = NATIVE Frappe User Permission (allow=CMI Office). Doctype Expedition
# punya field branch_office (Link CMI Office) -> otomatis terfilter. Tidak ada hook custom.

# CATATAN: seluruh Agent/Assistant (doctype, page, scheduler, inbound email, tab
# Assistant/Email) sudah DIPINDAH ke app `agents` (module Assistant). Doctype JS
# erp (Packing/Shipping/Expense) memuat tab Assistant via `assistant.assistant.api.assistant_js`.

# NOTE: erp sengaja STERIL terhadap core ERPNext — app ini hanya berisi
# doctype miliknya sendiri (Packing List, Shipping List, Invoice Type, dll).
# SEMUA kustomisasi core (Sales Invoice/Company: custom field, autoname, client
# script) tinggal di app `erpnext_custom`. Jangan tambahkan doctype_js / doc_events
# untuk doctype core ERPNext di sini.

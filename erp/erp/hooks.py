app_name = "erp"
app_title = "ERP CMI"
app_publisher = "CMI"
app_description = "Custom ERP CMI"
app_email = "you@cmi.com"
app_license = "mit"

# Installation
# ------------
after_install = "erp.install.after_install"
after_migrate = "erp.install.after_migrate"

# Kolom ID/Name di list view diberi lebar minimum (CSS satu aturan, aman).
app_include_css = "/assets/erp/css/list_id_fit.css?v=3"

# Fixtures: master "tipe" reference (tanpa link ke Account/Cost Center/Company),
# ikut terbawa otomatis saat install supaya tak perlu input ulang.
fixtures = [
	{"dt": "Container Size"},
	{"dt": "Cargo"},
	{"dt": "Shipment Type"},
	{"dt": "Packing List Type"},
	{"dt": "Expense Note Type"},
	{"dt": "Jenis Karantina"},
]

# Naming series variables — token dinamis untuk penomoran native (Document Naming
# Settings). Dipakai Expense Note: series `EXP/.cmi_type_code./.cmi_company_code./.YY./`
# → mis. EXP/IMP/CMI/26/00001, counter reset per tipe+company+tahun (via getseries).
naming_series_variables = {
	"cmi_type_code": "erp.expedition.numbering.parse_type_code",
	"cmi_company_code": "erp.expedition.numbering.parse_company_code",
}

# CATATAN: seluruh Agent/Assistant (doctype, page, scheduler, inbound email, tab
# Assistant/Email) sudah DIPINDAH ke app `agents` (module Assistant). Doctype JS
# erp (Packing/Shipping/Expense) memuat tab Assistant via `assistant.assistant.api.assistant_js`.

# NOTE: erp sengaja STERIL terhadap core ERPNext — app ini hanya berisi
# doctype miliknya sendiri (Packing List, Shipping List, Invoice Type, dll).
# SEMUA kustomisasi core (Sales Invoice/Company: custom field, autoname, client
# script) tinggal di app `erpnext_custom`. Jangan tambahkan doctype_js / doc_events
# untuk doctype core ERPNext di sini.

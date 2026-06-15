app_name = "erp_cmi"
app_title = "ERP CMI"
app_publisher = "CMI"
app_description = "Custom ERP CMI"
app_email = "you@cmi.com"
app_license = "mit"

# Installation
# ------------
after_install = "erp_cmi.install.after_install"
after_migrate = "erp_cmi.install.after_migrate"

# CATATAN: seluruh Agent/Assistant (doctype, page, scheduler, inbound email, tab
# Assistant/Email) sudah DIPINDAH ke app `agents` (module Assistant). Doctype JS
# erp_cmi (Packing/Shipping/Expense) memuat tab Assistant via `agents.agent.api.assistant_js`.

# NOTE: erp_cmi sengaja STERIL terhadap core ERPNext — app ini hanya berisi
# doctype miliknya sendiri (Packing List, Shipping List, Invoice Type, dll).
# SEMUA kustomisasi core (Sales Invoice/Company: custom field, autoname, client
# script) tinggal di app `erpnext_custom`. Jangan tambahkan doctype_js / doc_events
# untuk doctype core ERPNext di sini.

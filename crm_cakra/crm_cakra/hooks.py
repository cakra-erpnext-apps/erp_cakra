app_name = "crm_cakra"
app_title = "Frappe CRM"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "Kick-ass Open Source CRM"
app_email = "shariq@frappe.io"
app_license = "AGPLv3"
app_icon_url = "/assets/crm_cakra/images/logo.svg"
app_icon_title = "CRM"
app_icon_route = "/crm"

# Fixtures
# ------------------
# Export layout (Tab Data & Side Panel) CRM Quotation ke git supaya portable
# antar environment / bisa dikerjakan developer lain.
fixtures = [
    {"doctype": "CRM Fields Layout", "filters": [["dt", "in", ["CRM Inquiry", "CRM Quotation", "CRM Lead", "CRM Estimation"]]]},
    # Status workflow Inquiry (biar tampilan/kanban persis sama saat reinstall).
    {"doctype": "CRM Inquiry Status"},
    # Relabel Inquiry -> Inquiry di UI (lewat translation, tanpa ubah doctype/route).
    {"doctype": "Translation", "filters": [["translated_text", "like", "%Inquir%"]]},
    # Master Lead Source (pilihan sumber lead).
    {"doctype": "CRM Lead Source"},
    # Master Transportation Mode (multi-select di Inquiry).
    {"doctype": "CRM Transportation Mode"},
    # Master Type of Inquiry (multi-select type_inquiry di Inquiry).
    {"doctype": "CRM Type Inquiry"},
    # Custom field kategori Item (global: Revenue/Expense/Stock/Asset/Sparepart).
    {"doctype": "Custom Field", "filters": [["name", "in", ["Item-item_category", "User-branch"]]]},
    # Master kantor (alamat per office untuk print quotation).
    {"doctype": "CMI Office"},
    # Default print format CRM Quotation -> Quotation Print Out.
    {"doctype": "Property Setter", "filters": [["name", "=", "CRM Quotation-main-default_print_format"]]},
]

# Apps
# ------------------

# required_apps = []
add_to_apps_screen = [
	{
		"name": "crm_cakra",
		"logo": "/assets/crm_cakra/images/logo.svg",
		"title": "CRM",
		"route": "/crm",
		"has_permission": "crm_cakra.api.check_app_permission",
	}
]

get_site_info = "crm_cakra.activation.get_site_info"

export_python_type_annotations = True
require_type_annotated_api_methods = True

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/crm_cakra/css/crm.css"
# app_include_js = "/assets/crm_cakra/js/crm.js"

# include js, css files in header of web template
# web_include_css = "/assets/crm_cakra/css/crm.css"
# web_include_js = "/assets/crm_cakra/js/crm.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "crm/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# "Role": "home_page"
# }

website_route_rules = [
	{"from_route": "/crm/<path:app_path>", "to_route": "crm"},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# "methods": "crm_cakra.utils.jinja_methods",
# "filters": "crm_cakra.utils.jinja_filters"
# }

# Setup wizard
# setup_wizard_requires = "assets/crm/js/setup_wizard.js"
# setup_wizard_stages = "crm_cakra.setup.setup_wizard.setup_wizard.get_setup_stages"
setup_wizard_complete = "crm_cakra.demo.api.create_demo_data"
# setup_wizard_test = "crm_cakra.setup.setup_wizard.test_setup_wizard.run_setup_wizard_test"

# Installation
# ------------

before_install = "crm_cakra.install.before_install"
after_install = "crm_cakra.install.after_install"

# Uninstallation
# ------------

before_uninstall = "crm_cakra.uninstall.before_uninstall"
# after_uninstall = "crm_cakra.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "crm_cakra.utils.before_app_install"
# after_app_install = "crm_cakra.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "crm_cakra.utils.before_app_uninstall"
# after_app_uninstall = "crm_cakra.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "crm_cakra.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Akses berbasis branch (CUSTOM role-based, config 'CMI Branch Access'). SATU handler
# wildcard "*" berlaku ke SEMUA doctype yang punya field branch_office — lintas modul.
# Menambah modul = cukup tambah field branch_office ke doctype-nya (tanpa ubah hook).
permission_query_conditions = {
	"*": "crm_cakra.api.permissions.branch_query_conditions",
}
has_permission = {
	"*": "crm_cakra.api.permissions.branch_has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Contact": "crm_cakra.overrides.contact.CustomContact",
	"Email Template": "crm_cakra.overrides.email_template.CustomEmailTemplate",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Contact": {
		"validate": ["crm_cakra.api.contact.validate"],
	},
	"ToDo": {
		"after_insert": ["crm_cakra.api.todo.after_insert"],
		"on_update": ["crm_cakra.api.todo.on_update"],
	},
	"Communication": {
		"after_insert": ["crm_cakra.utils.on_communication_insert"],
		"on_update": ["crm_cakra.utils.on_communication_update"],
	},
	"Comment": {
		"after_insert": ["crm_cakra.utils.on_comment_insert"],
		"on_update": ["crm_cakra.api.comment.on_update"],
	},
	"WhatsApp Message": {
		"validate": ["crm_cakra.api.whatsapp.validate"],
		"on_update": ["crm_cakra.api.whatsapp.on_update"],
	},
	# branch_office diisi otomatis untuk SEMUA doctype yang punya field itu (wildcard).
	# set_branch_from_user aman untuk semua doctype (guard has_field di dalamnya).
	"*": {
		"before_insert": "crm_cakra.api.permissions.set_branch_from_user",
	},
	"CRM Inquiry": {
		"on_update": [
			"crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.create_customer_in_erpnext"
		],
	},
	"User": {
		"before_validate": ["crm_cakra.api.live_demo.validate_user"],
		"validate_reset_password": ["crm_cakra.api.live_demo.validate_reset_password"],
		# (branch access = custom role-based via 'CMI Branch Access'; branch user diambil
		# dari field User.branch. Tidak ada sync ke User Permission.)
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily_long": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_daily"],
	"hourly_long": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_hourly"],
	"monthly_long": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_monthly"],
	"cron": {
		"*/5 * * * *": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_5_minutes"],
		"*/10 * * * *": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_10_minutes"],
		"*/15 * * * *": ["crm_cakra.lead_syncing.background_sync.sync_leads_from_sources_15_minutes"],
	},
}

# Testing
# -------

before_tests = "crm_cakra.tests.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# "frappe.desk.doctype.event.event.get_events": "crm_cakra.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# "Task": "crm_cakra.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

ignore_links_on_delete = ["Failed Lead Sync Log"]

# Request Events
# ----------------
# before_request = ["crm_cakra.utils.before_request"]
# after_request = ["crm_cakra.utils.after_request"]

# Job Events
# ----------
# before_job = ["crm_cakra.utils.before_job"]
# after_job = ["crm_cakra.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# {
# "doctype": "{doctype_1}",
# "filter_by": "{filter_by}",
# "redact_fields": ["{field_1}", "{field_2}"],
# "partial": 1,
# },
# {
# "doctype": "{doctype_2}",
# "filter_by": "{filter_by}",
# "partial": 1,
# },
# {
# "doctype": "{doctype_3}",
# "strict": False,
# },
# {
# "doctype": "{doctype_4}"
# }
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# "crm_cakra.auth.validate"
# ]

after_migrate = [
	"crm_cakra.fcrm.doctype.fcrm_settings.fcrm_settings.after_migrate",
	"crm_cakra.api.whatsapp.add_roles",
	# Field User.custom_branches (Additional Branches) + seed CMI Branch Access.
	# WAJIB di after_migrate, bukan cuma after_install: site yang sudah ada tidak pernah
	# menjalankan after_install lagi, jadi field-nya tak akan pernah muncul di server.
	"crm_cakra.install.after_migrate",
]

standard_dropdown_items = [
	{
		"name1": "app_selector",
		"label": "Apps",
		"type": "Route",
		"route": "#",
		"is_standard": 1,
	},
	{
		"name1": "settings",
		"label": "Settings",
		"type": "Route",
		"icon": "settings",
		"route": "#",
		"is_standard": 1,
	},
	{
		"name1": "login_to_fc",
		"label": "Login to Frappe Cloud",
		"type": "Route",
		"route": "#",
		"is_standard": 1,
	},
	{
		"name1": "about",
		"label": "About",
		"type": "Route",
		"icon": "info",
		"route": "#",
		"is_standard": 1,
	},
	{
		"name1": "separator",
		"label": "",
		"type": "Separator",
		"is_standard": 1,
	},
	{
		"name1": "logout",
		"label": "Log out",
		"type": "Route",
		"icon": "log-out",
		"route": "#",
		"is_standard": 1,
	},
]

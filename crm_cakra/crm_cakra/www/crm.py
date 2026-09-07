# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# GNU GPLv3 License. See license.txt

import frappe
import frappe.sessions
from frappe import _
from frappe.integrations.frappe_providers.frappecloud_billing import is_fc_site
from frappe.translate import get_messages_for_boot, get_translated_doctypes
from frappe.utils import cint, get_system_timezone
from frappe.utils.telemetry import capture

no_cache = 1


def get_context():
	from crm_cakra.api import check_app_permission

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Frappe CRM"), frappe.PermissionError)

	frappe.db.commit()
	context = frappe._dict()
	context.boot = get_boot()
	if frappe.session.user != "Guest":
		capture("active_site", "crm_cakra")
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	return frappe._dict(
		{
			"frappe_version": frappe.__version__,
			"default_route": get_default_route(),
			"site_name": frappe.local.site,
			"read_only_mode": frappe.flags.read_only,
			"csrf_token": frappe.sessions.get_csrf_token(),
			"setup_complete": cint(frappe.get_system_settings("setup_complete")),
			"sysdefaults": frappe.defaults.get_defaults(),
			"is_demo_site": frappe.conf.get("is_demo_site"),
			"demo_data_created": frappe.db.get_default("crm_demo_data_created") == "1",
			"is_fc_site": is_fc_site(),
			"show_sales_hierarchy_banner": frappe.db.count("CRM Lead") > 0,
			"translated_doctypes": get_translated_doctypes(),
			"cmi_item_groups": get_item_group_scopes(),
			"translated_messages": get_messages_for_boot(),
			"timezone": {
				"system": get_system_timezone(),
				"user": frappe.db.get_value("User", frappe.session.user, "time_zone")
				or get_system_timezone(),
			},
		}
	)


def get_item_group_scopes():
	"""Item Group yang membatasi kolom Item di grid Revenue/Expense (Estimation) dan tabel
	Items Cost Component. Sumbernya ERPNext Custom Setting > Expedition — satu tempat untuk
	desk maupun portal; sebelumnya sisi portal punya field sendiri (FCRM Settings.use_items_group)
	yang gampang melenceng. Kosong = semua item boleh."""
	try:
		from erpnext_custom.item_scope import item_groups
	except ImportError:
		return {}
	return {"revenue": item_groups("revenue"), "expense": item_groups("expense")}


def get_default_route():
	return "/crm"

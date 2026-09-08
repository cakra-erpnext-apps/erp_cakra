"""Cek menu desk: tiap menu depan punya file icon (bukan huruf), dan menu RESTRICTED
cuma tampil untuk pemegang rolenya. Tidak mengubah data.

    bench --site erp.localhost console
    >>> from erpnext_custom.test_desk_menu import run; run()
"""

import frappe
from frappe.boot import get_desktop_icon_urls
from frappe.desk.doctype.desktop_icon.desktop_icon import get_desktop_icons

from erpnext_custom.desk_menu import LAYOUT_FIELDS, _icon_role_gates, _labels_for
from erpnext_custom.desk_menus_spec import RESTRICTED


def _style():
	return (frappe.db.get_single_value("Desktop Settings", "icon_style") or "Solid").lower()


def how_rendered(icon, urls, style):
	"""Meniru desktop_icon.html: file SVG -> logo -> folder -> HURUF awal label."""
	app = icon.get("app")
	if app and icon.get("icon_type") != "Folder":
		url = f"assets/{app}/icons/desktop_icons/{style}/{frappe.scrub(icon['label'])}.svg"
		if url in (urls.get(app) or {}).get(style, []):
			return "SVG " + url
	if icon.get("logo_url") or icon.get("icon_image"):
		return "LOGO " + (icon.get("logo_url") or icon.get("icon_image"))
	if icon.get("icon_type") == "Folder":
		return "FOLDER"
	return "HURUF"


def _top_icons(user):
	frappe.set_user(user)
	frappe.cache.hdel("desktop_icons", user)
	boot = frappe._dict(workspace_sidebar_item=frappe.boot.get_bootinfo().workspace_sidebar_item)
	icons = get_desktop_icons(bootinfo=boot)
	return [i for i in icons if not i.get("parent_icon") and not i.get("hidden")]


def run(verbose=True):
	urls, style = get_desktop_icon_urls(), _style()
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("not in", ["Administrator", "Guest"])},
		pluck="name",
	)
	sysman = [u for u in users if "System Manager" in frappe.get_roles(u)]
	plain = [u for u in users if "System Manager" not in frappe.get_roles(u)]
	assert sysman and plain, "butuh contoh user System Manager DAN user biasa"

	try:
		for user, is_mgr in ((sysman[0], True), (plain[0], False)):
			top = _top_icons(user)
			labels = {i["label"] for i in top}
			if verbose:
				print(f"\n=== {user} ({'System Manager' if is_mgr else 'biasa'}) -> {len(top)} menu depan")
			for i in top:
				how = how_rendered(i, urls, style)
				if verbose:
					print("   ", i["label"].ljust(20), how)
				assert how != "HURUF", f"{i['label']} masih digambar sebagai huruf"
			for label in RESTRICTED:
				if is_mgr:
					assert label in labels, f"{label} hilang untuk System Manager"
				else:
					assert label not in labels, f"{label} masih terlihat user biasa"
	finally:
		frappe.set_user("Administrator")
	print("\nOK")

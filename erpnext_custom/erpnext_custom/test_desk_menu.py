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
			_check_layout_labels(user, is_mgr)
	finally:
		frappe.set_user("Administrator")
	_check_item_icons(verbose)
	print("\nOK")



def _check_layout_labels(user, is_mgr):
	"""Snapshot Desktop Layout dipakai desk apa adanya (tidak lewat is_permitted), jadi
	batas role harus ikut kena di sana -- termasuk anak folder Default yang, kalau tidak
	ikut dibuang, malah naik jadi menu depan."""
	icons = {i.label: i for i in frappe.get_all("Desktop Icon", fields=list(LAYOUT_FIELDS))}
	labels = _labels_for(user, icons, _icon_role_gates())
	for label in RESTRICTED:
		assert (label in labels) is is_mgr, f"layout {user}: {label} salah tampil/hilang"
	if not is_mgr:
		anak = [l for l, i in icons.items() if i.parent_icon in RESTRICTED]
		bocor = [l for l in anak if l in labels]
		assert not bocor, f"layout {user}: anak menu terbatas ikut bocor: {bocor}"


def _check_item_icons(verbose=True):
	"""Tiap baris menu top-level punya icon, DAN nama iconnya benar-benar ada di sprite
	lucide. Nama yang salah tidak melempar error apa pun -- cuma jadi kotak kosong."""
	import os
	import re

	# Icon desk datang dari BEBERAPA sprite, bukan lucide saja: menu bawaan masih memakai
	# nama dari sprite "timeless" (stock, buying, chart, ...). Kumpulkan semuanya.
	available = set()
	root = os.path.join(frappe.get_app_path("frappe"), "public", "icons")
	for folder, _dirs, files in os.walk(root):
		for fname in files:
			if not fname.endswith(".svg"):
				continue
			with open(os.path.join(folder, fname), encoding="utf-8") as f:
				available |= set(re.findall(r'id="(?:icon-)?([a-z0-9-]+)"', f.read()))

	icons = frappe.boot.get_bootinfo().desktop_icons
	top = sorted({i["label"] for i in icons if not i.get("parent_icon") and not i.get("hidden")})
	rows = frappe.get_all(
		"Workspace Sidebar Item",
		filters={"parenttype": "Workspace Sidebar", "type": "Link", "parent": ("in", top)},
		fields=["parent", "label", "icon"],
	)
	kosong = [(r.parent, r.label) for r in rows if not r.icon]
	salah = sorted({r.icon for r in rows if r.icon and r.icon not in available})
	assert not kosong, f"{len(kosong)} baris menu tanpa icon, mis. {kosong[:3]}"
	assert not salah, f"nama icon tidak ada di sprite manapun: {salah}"
	if verbose:
		print(f"icon baris menu: {len(rows)} baris, semua terisi & namanya valid")

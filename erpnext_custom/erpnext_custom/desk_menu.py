"""Menu desk: kumpulkan seluruh menu bawaan ERPNext ke satu folder "Default".

Desk v16 merender menu dari doctype Desktop Icon. Icon ber-`icon_type = "Folder"`
menjadi grup, anggotanya menunjuk balik lewat `parent_icon` (lihat build_folder_map
di frappe/public/js/frappe/ui/sidebar/sidebar_header.js). Nesting hanya SATU lapis:
folder di dalam folder tidak pernah dirender anaknya, jadi grup bawaan seperti
"Accounting" dibongkar dan isinya ikut pindah ke folder ini.

Idempotent, dipanggil dari after_migrate supaya tidak dikembalikan oleh migrate.
"""

import json

import frappe

from erpnext_custom.desk_menus_spec import (
	KEEP_TOP_LEVEL,
	MENUS,
	PLACEHOLDER_WORKSPACES,
	SB,
)

FOLDER = "Default"
APP = "erpnext"

# Folder bawaan yang isinya dibongkar ke FOLDER; setelah kosong ikut disembunyikan.
LEGACY_FOLDERS = ("Accounting",)


def _standard_icons():
	"""Icon menu bawaan ERPNext. Icon milik kita `standard = 0`, jadi aman terlewat,
	begitu juga icon App (ERPNext/Framework) yang dipakai app switcher."""
	return frappe.get_all(
		"Desktop Icon",
		filters={"standard": 1, "app": APP, "icon_type": ("in", ("Link", "Folder"))},
		fields=["name", "label", "icon_type", "parent_icon", "hidden"],
	)


def _ensure_folder_icon():
	name = frappe.db.exists("Desktop Icon", {"label": FOLDER, "icon_type": "Folder"})
	icon = frappe.get_doc("Desktop Icon", name) if name else frappe.new_doc("Desktop Icon")
	icon.update(
		{
			"label": FOLDER,
			"icon_type": "Folder",
			# External dibuang dari daftar menu, jadi jangan dipakai untuk folder
			"link_type": "Workspace Sidebar",
			"link_to": "",
			"app": APP,
			"icon": "folder-normal",
			"parent_icon": None,
			"hidden": 0,
			"standard": 0,
		}
	)
	icon.save(ignore_permissions=True)
	return icon.name


LAYOUT_FIELDS = (
	"label",
	"bg_color",
	"link",
	"link_type",
	"app",
	"icon_type",
	"parent_icon",
	"icon",
	"link_to",
	"idx",
	"standard",
	"logo_url",
	"hidden",
	"name",
	"restrict_removal",
	"icon_image",
)


def _layout_entry(icon):
	entry = {f: icon.get(f) for f in LAYOUT_FIELDS}
	entry["child_icons"] = []
	return entry


def _sync_desktop_layouts():
	"""Desk merender dari snapshot per-user (Desktop Layout) begitu record itu ada;
	tanpa disamakan, icon baru tidak pernah muncul dan icon yang dipindah tetap di
	tempat lama untuk user tersebut. Snapshot disamakan penuh dengan Desktop Icon:
	entry yang ada diperbarui, yang belum ada ditambahkan, yang iconnya sudah hilang
	dibuang."""
	icons = {
		i.label: i
		for i in frappe.get_all("Desktop Icon", fields=list(LAYOUT_FIELDS))
	}

	for user in frappe.get_all("Desktop Layout", pluck="name"):
		doc = frappe.get_doc("Desktop Layout", user)
		try:
			layout = json.loads(doc.layout or "[]")
		except ValueError:
			layout = []
		if not isinstance(layout, list):
			layout = []

		kept = []
		seen = set()
		for entry in layout:
			if not isinstance(entry, dict):
				continue
			icon = icons.get(entry.get("label"))
			if not icon:
				continue  # iconnya sudah tidak ada
			entry.update(_layout_entry(icon))
			kept.append(entry)
			seen.add(icon.label)

		for label, icon in icons.items():
			if label not in seen:
				kept.append(_layout_entry(icon))

		kept.sort(key=lambda e: (e.get("idx") or 0, e.get("label") or ""))
		doc.db_set("layout", json.dumps(kept), update_modified=False)


def ensure_default_folder():
	_ensure_folder_icon()

	own = {m["label"] for m in MENUS} | set(KEEP_TOP_LEVEL)
	moved, hidden = set(), set()
	for row in _standard_icons():
		if row.label == FOLDER or row.label in own:
			# menu versi kita: tetap di baris depan, bukan di dalam folder
			if row.parent_icon:
				frappe.db.set_value("Desktop Icon", row.name, "parent_icon", None)
			continue
		if row.label in LEGACY_FOLDERS:
			# folder bawaan: anaknya sudah dipindah, folder kosongnya disembunyikan
			frappe.db.set_value("Desktop Icon", row.name, "hidden", 1)
			hidden.add(row.label)
			continue
		if row.parent_icon != FOLDER:
			frappe.db.set_value("Desktop Icon", row.name, "parent_icon", FOLDER)
		moved.add(row.label)

	_sync_desktop_layouts()

	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
	return sorted(moved)


def _ensure_placeholder_workspace(title, icon):
	"""Halaman kosong supaya menunya bisa diklik sebelum isinya diputuskan."""
	if frappe.db.exists("Workspace", title):
		return
	w = frappe.new_doc("Workspace")
	w.title = title
	w.label = title
	w.update({"module": "ERPNext Custom", "app": APP, "public": 1, "icon": icon, "content": "[]"})
	w.flags.ignore_links = True
	w.insert(ignore_permissions=True)


def _ensure_sidebar(menu):
	title = menu["label"]
	if frappe.db.exists("Workspace Sidebar", title):
		sb = frappe.get_doc("Workspace Sidebar", title)
	else:
		sb = frappe.new_doc("Workspace Sidebar")
		sb.title = title
	sb.update({"module": "ERPNext Custom", "app": APP, "header_icon": menu["icon"]})
	sb.set("items", [])
	for item in menu["items"]:
		if item[0] == SB:
			sb.append("items", {"type": "Section Break", "label": item[1]})
			continue
		label, link_type, link_to, route_options = item
		row = {"type": "Link", "label": label, "link_type": link_type, "link_to": link_to}
		if route_options:
			row["route_options"] = json.dumps(route_options)
		sb.append("items", row)
	sb.flags.ignore_links = True
	sb.save(ignore_permissions=True)


def _ensure_menu_icon(menu, idx):
	"""Icon desk. Label WAJIB sama dengan nama Workspace Sidebar -- desk mencari
	sidebar lewat label icon (get_route_for_icon), bukan lewat link_to."""
	label = menu["label"]
	name = frappe.db.exists("Desktop Icon", {"label": label, "icon_type": ("!=", "App")})
	icon = frappe.get_doc("Desktop Icon", name) if name else frappe.new_doc("Desktop Icon")
	icon.update(
		{
			"label": label,
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": label,
			"app": APP,
			"icon": menu["icon"],
			"parent_icon": None,
			"hidden": 0,
			"idx": idx,
		}
	)
	icon.flags.ignore_links = True
	icon.save(ignore_permissions=True)


def ensure_menus():
	"""Bangun menu desk versi CMI, lalu sisanya dirapikan ke folder Default."""
	for title, icon in PLACEHOLDER_WORKSPACES:
		_ensure_placeholder_workspace(title, icon)

	for i, menu in enumerate(MENUS, start=1):
		_ensure_sidebar(menu)
		_ensure_menu_icon(menu, i)

	# menu lama yang dipakai apa adanya, dijaga tetap di depan dan urut di belakang
	for j, label in enumerate(KEEP_TOP_LEVEL, start=len(MENUS) + 1):
		name = frappe.db.exists("Desktop Icon", {"label": label})
		if name:
			frappe.db.set_value(
				"Desktop Icon", name, {"parent_icon": None, "hidden": 0, "idx": j}, update_modified=False
			)

	ensure_default_folder()
	return [m["label"] for m in MENUS]

"""Bikin file icon menu desk (SVG berwarna) dari sprite lucide milik frappe.

Desk v16 menggambar icon home dengan urutan: file
`assets/{app}/icons/desktop_icons/{subtle|solid}/{scrub(label)}.svg` -> `logo_url` ->
HURUF AWAL label (frappe/public/js/frappe/ui/desktop_icon.html). Field `icon` pada
Desktop Icon TIDAK dipakai di sana, jadi satu-satunya cara menghilangkan huruf itu
adalah menyediakan file SVG-nya -- dan `app` iconnya harus app yang memuat file itu
(disetel desk_menu._ensure_menu_icon ke `erpnext_custom`).

Hasilnya di-commit; jalankan lagi hanya kalau icon/warna di desk_menus_spec berubah:

    bench --site erp.localhost console
    >>> from erpnext_custom.desk_icons import build; build()
"""

import os
import re

import frappe

from erpnext_custom.desk_menus_spec import desk_icons

APP = "erpnext_custom"
VARIANTS = ("solid", "subtle")

# 54x54 = ukuran icon desk bawaan. Glyph lucide (24x24) diskalakan ke 28 lalu ditaruh
# di tengah. Solid: kotak berwarna + garis putih. Subtle: kotak transparan + garis warna.
_TPL = (
	'<svg width="54" height="54" viewBox="0 0 54 54" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
	'<rect width="54" height="54" rx="15.4286" fill="{bg}"{bg_opacity}/>\n'
	'<g transform="translate(13 13) scale(1.16667)" fill="none" stroke="{fg}" '
	'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{glyph}</g>\n'
	"</svg>\n"
)

_SYMBOL = re.compile(r'<symbol[^>]*id="icon-([a-z0-9-]+)"[^>]*>(.*?)</symbol>', re.S)


def _lucide():
	path = os.path.join(frappe.get_app_path("frappe"), "public", "icons", "lucide.svg")
	with open(path, encoding="utf-8") as f:
		return {m.group(1): " ".join(m.group(2).split()) for m in _SYMBOL.finditer(f.read())}


def build():
	"""Tulis 2 file (solid + subtle) per menu. Nama file = frappe.scrub(label), sama
	dengan yang dicari frappe.utils.get_desktop_icon."""
	glyphs = _lucide()
	base = os.path.join(frappe.get_app_path(APP), "public", "icons", "desktop_icons")
	written = []
	for label, (glyph_name, color) in desk_icons().items():
		# nama icon lucide salah -> meledak di sini, bukan diam-diam jadi kotak kosong
		glyph = glyphs[glyph_name]
		fname = frappe.scrub(label) + ".svg"
		for variant in VARIANTS:
			solid = variant == "solid"
			folder = os.path.join(base, variant)
			os.makedirs(folder, exist_ok=True)
			with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
				f.write(
					_TPL.format(
						bg=color,
						bg_opacity="" if solid else ' fill-opacity="0.19"',
						fg="#FFFFFF" if solid else color,
						glyph=glyph,
					)
				)
		written.append(fname)
	return sorted(written)

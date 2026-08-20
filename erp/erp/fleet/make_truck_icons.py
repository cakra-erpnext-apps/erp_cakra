"""Bikin pin truk berwarna dari satu artwork: erp/public/images/truck.png.

Badan pin yang hitam diwarnai, garis truk yang putih dibiarkan putih supaya tetap
terbaca di atas warna apa pun. Jalankan kalau palet warna aturan bertambah:

    bench --site erp.localhost execute erp.fleet.make_truck_icons.build

Hasilnya truck-<warna>.png, dipetakan ke status lewat COLOR_ICON di vehicle_status.py.
"""

import os

# (nama warna aturan, RGB badan pin)
COLORS = {
	"merah": (220, 38, 38),
	"oranye": (234, 88, 12),
	"kuning": (202, 138, 4),
	"biru": (29, 78, 216),
	"ungu": (124, 58, 237),
	"hijau": (22, 163, 74),
	"abu": (107, 114, 128),
}

DARK = 200  # r+g+b di bawah ini dianggap badan pin, bukan garis truk


def build():
	from PIL import Image

	folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "images")
	src = Image.open(os.path.join(folder, "truck.png")).convert("RGBA")
	px = src.load()
	w, h = src.size
	for slug, rgb in COLORS.items():
		out = src.copy()
		o = out.load()
		for y in range(h):
			for x in range(w):
				r, g, b, a = px[x, y]
				if a and (r + g + b) < DARK:
					o[x, y] = (*rgb, a)
		out.save(os.path.join(folder, f"truck-{slug}.png"))
		print("dibuat: truck-%s.png" % slug)

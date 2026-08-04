"""Saran rak (WMS ringan) — tombol "Suggest Rack" di Purchase Receipt & Delivery Note.

MASUK (PR, per baris, butuh Gudang terisi):
  1. rak segudang yang SUDAH menyimpan item sama (konsolidasi); banyak -> terdekat;
  2. kalau tidak ada: rak paling kosong (total qty semua item terkecil), tie terdekat.

KELUAR (DN, per baris): habiskan stok TERTUA dulu (FIFO antar rak — umur rak =
tanggal terima tertua yang masih tersisa di rak itu); umur sama -> rak TERDEKAT,
masih sama -> rak paling BAWAH. Satu rak tidak cukup -> alokasi dipecah ke rak
berikutnya (JS memecah barisnya).

Posisi rak dari 2 field Warehouse (kosong = dianggap paling jauh/paling atas):
  custom_rack_order = urutan jarak, 1 = paling dekat pintu keluar
  custom_rack_level = tingkat, 1 = paling bawah (rak tinggi: bawah lebih dulu)
Ini murni SARAN — field rak tetap editable, dan klik ulang tombolnya = replan
dari kondisi stok terkini.
"""

import json
import re

import frappe

_FAR = 10**9  # rak tanpa urutan/level dianggap paling jauh/paling atas

# Skema nama rak: RACK[-SEGMEN]-LEVEL. Contoh: A-AA-01 (rack A, segmen AA,
# level 1), A-AB-01, B-BA-03; bentuk pendek tanpa segmen (A1, B3) juga diterima.
# Urutan jarak = komposit rack lalu segmen (rack A sebelum B; di dalam rack,
# segmen AA sebelum AB). Level: 1 = paling bawah.
_RACK_NAME = re.compile(r"^([A-Za-z])(?:[-. ]([A-Za-z]{1,3}))?[-. ]?(\d{1,3})$")


def _letters_index(letters):
	"""AA -> 27, AB -> 28 (base-26, A=1) — urut alfabetis jadi urut angka."""
	idx = 0
	for ch in letters.upper():
		idx = idx * 26 + (ord(ch) - ord("A") + 1)
	return idx


def set_position_from_name(doc, method=None):
	"""Hook validate Warehouse: isi posisi rak dari nama ber-skema A-AA-01 / A1.
	Hanya mengisi field yang masih kosong — isian manual tidak ditimpa."""
	m = _RACK_NAME.match((doc.warehouse_name or "").strip())
	if not m:
		return
	rack, segment, level = m.groups()
	if not doc.get("custom_rack_order"):
		doc.custom_rack_order = _letters_index(rack) * 100000 + _letters_index(segment or "")
	if not doc.get("custom_rack_level"):
		doc.custom_rack_level = int(level)


@frappe.whitelist()
def suggest(direction, company, rows):
	rows = json.loads(rows) if isinstance(rows, str) else rows
	fn = _suggest_in if direction == "in" else _suggest_out
	return [fn(company, r) if r.get("item_code") else None for r in rows]


def _positions(names):
	"""{warehouse: (jarak, level)} — kunci urut 'terdekat lalu terbawah'."""
	return {
		w.name: (w.custom_rack_order or _FAR, w.custom_rack_level or _FAR)
		for w in frappe.get_all(
			"Warehouse",
			filters={"name": ["in", list(names)]},
			fields=["name", "custom_rack_order", "custom_rack_level"],
		)
	}


def _zone_for_item(item_code):
	"""Huruf rack yang diizinkan untuk item ini (Item Group.custom_rack_zone,
	naik ke parent group sampai ketemu). None = bebas."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	while group:
		zone, group = frappe.db.get_value(
			"Item Group", group, ["custom_rack_zone", "parent_item_group"]
		)
		if zone:
			return {z.strip().upper() for z in zone.split(",") if z.strip()}
	return None


def _suggest_in(company, row):
	gudang = row.get("gudang")
	if not gudang:
		return {"skip": "gudang belum dipilih"}
	racks_all = frappe.get_all(
		"Warehouse",
		filters={"parent_warehouse": gudang, "is_group": 0, "disabled": 0, "company": company},
		fields=["name", "warehouse_name"],
	)
	if not racks_all:
		return {"skip": "gudang tidak punya rak"}

	# zoning: rak ber-huruf sesuai zona item group (kosong = semua rak boleh)
	zone = _zone_for_item(row["item_code"])
	if zone:
		def letter(wn):
			m = _RACK_NAME.match((wn or "").strip())
			return m.group(1).upper() if m else None
		racks = [r.name for r in racks_all if letter(r.warehouse_name) in zone]
		if not racks:
			return {"skip": "tidak ada rak zona {0} di gudang ini".format(",".join(sorted(zone)))}
	else:
		racks = [r.name for r in racks_all]
	pos = _positions(racks)

	# 1. konsolidasi: rak yang sudah menyimpan item yang sama
	same = frappe.get_all(
		"Bin",
		filters={"item_code": row["item_code"], "warehouse": ["in", racks], "actual_qty": [">", 0]},
		pluck="warehouse",
	)
	if same:
		best = sorted(same, key=lambda w: (*pos[w], w))[0]
		return {"allocations": [{"warehouse": best, "qty": row.get("qty")}]}

	# 2. rak paling kosong
	totals = dict.fromkeys(racks, 0.0)
	for b in frappe.get_all(
		"Bin", filters={"warehouse": ["in", racks]}, fields=["warehouse", "actual_qty"]
	):
		totals[b.warehouse] += b.actual_qty or 0
	best = sorted(racks, key=lambda w: (totals[w], *pos[w], w))[0]
	return {"allocations": [{"warehouse": best, "qty": row.get("qty")}]}


def _suggest_out(company, row):
	need = float(row.get("stock_qty") or row.get("qty") or 0)
	if need <= 0:
		return {"skip": "qty kosong"}
	bins = frappe.get_all(
		"Bin",
		filters={"item_code": row["item_code"], "actual_qty": [">", 0]},
		fields=["warehouse", "actual_qty"],
	)
	whs = {
		w.name: w
		for w in frappe.get_all(
			"Warehouse",
			filters={"name": ["in", [b.warehouse for b in bins]], "company": company, "disabled": 0},
			fields=["name", "custom_rack_order", "custom_rack_level", "is_rejected_warehouse"],
		)
	}
	candidates = [b for b in bins if b.warehouse in whs and not whs[b.warehouse].is_rejected_warehouse]
	if not candidates:
		return {"skip": "tidak ada stok"}

	# FIFO antar rak: tanggal terima tertua yang masih tersisa,
	# tie -> terdekat, masih sama -> paling bawah.
	def key(b):
		age = _oldest_receipt(row["item_code"], b.warehouse, b.actual_qty)
		w = whs[b.warehouse]
		return (
			str(age or "9999-12-31"),
			w.custom_rack_order or _FAR,
			w.custom_rack_level or _FAR,
			b.warehouse,
		)

	allocations, shortage = [], need
	for b in sorted(candidates, key=key):
		take = min(shortage, b.actual_qty)
		allocations.append({"warehouse": b.warehouse, "qty": take})
		shortage -= take
		if shortage <= 0:
			break
	out = {"allocations": allocations}
	if shortage > 0:
		out["shortage"] = shortage
	return out


def _oldest_receipt(item_code, warehouse, qty_now):
	"""Tanggal masuk tertua yang stoknya masih tersisa di rak ini (aproksimasi FIFO:
	jalan mundur dari SLE penerimaan terbaru sampai menutup qty sekarang)."""
	# ponytail: O(jumlah SLE masuk) per rak; cukup untuk skala rak. Kalau lambat,
	# baca stock_queue FIFO milik valuation di SLE terakhir.
	remaining, oldest = qty_now, None
	for sle in frappe.get_all(
		"Stock Ledger Entry",
		filters={"item_code": item_code, "warehouse": warehouse, "is_cancelled": 0, "actual_qty": [">", 0]},
		fields=["posting_date", "actual_qty"],
		order_by="posting_datetime desc, creation desc",
	):
		oldest = sle.posting_date
		remaining -= sle.actual_qty
		if remaining <= 0:
			break
	return oldest

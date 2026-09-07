"""Saran rak (WMS ringan) — tombol "Suggest Rack" di Purchase Receipt & Delivery Note.

MASUK (PR, per baris, butuh Gudang terisi):
  1. rak segudang yang SUDAH menyimpan item sama (konsolidasi); banyak -> terdekat;
  2. kalau tidak ada: rak paling kosong (total qty semua item terkecil), tie terdekat.

KELUAR (DN, per baris): habiskan stok TERTUA dulu (FIFO antar rak — umur rak =
tanggal terima tertua yang masih tersisa di rak itu); umur sama -> rak TERDEKAT,
masih sama -> rak paling BAWAH. Satu rak tidak cukup -> alokasi dipecah ke rak
berikutnya (JS memecah barisnya).

Pohon Warehouse dipakai 3 tingkat, dibedakan lewat field NATIVE warehouse_type
(diisi otomatis dari posisi di pohon, lihat classify_warehouse) -- inilah yang
memisahkan menu Gudang / Rak / Bin Location di desk:

  Gudang   anak langsung akar company    Gudang Jakarta, Gudang KIM
  Rak      group di dalam gudang         AA, AB, BULKY, Staging Area
  Bin      DAUN, tempat stok betul ada   AA0101A, AB4A, AE7

Stok selalu diposting ke Bin. Gudang tanpa rak (mis. Gudang Sparepart) boleh
punya Bin yang menempel langsung ke gudangnya.

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

# Tiga nilai warehouse_type = tiga tingkat pohon. Master-nya di-seed
# install._ensure_warehouse_types.
GUDANG, RAK, BIN = "Gudang", "Rak", "Bin"

# Nama bin, dua dialek yang dipakai di lapangan:
#   AA0101A / AB4A / AE7  huruf rak + nomor bay + huruf tingkat (A = paling bawah)
#   A-AA-01               skema lama: rack A, segmen AA, tingkat 01
# Yang dipakai cuma untuk MENGURUTKAN saran; nama yang tak terbaca tetap sah,
# posisinya saja yang dianggap paling jauh (isi manual kalau perlu).
_BIN_NAME = re.compile(r"^([A-Za-z]+)[-. ]?(\d{1,4})[-. ]?([A-Za-z]?)$")
_LEGACY_NAME = re.compile(r"^([A-Za-z])[-. ]([A-Za-z]{1,3})[-. ]?(\d{1,3})$")


def _letters_index(letters):
	"""AA -> 27, AB -> 28 (base-26, A=1) — urut alfabetis jadi urut angka."""
	idx = 0
	for ch in letters.upper():
		idx = idx * 26 + (ord(ch) - ord("A") + 1)
	return idx


def classify_warehouse(doc, method=None):
	"""Hook validate Warehouse: tentukan tingkat pohon + posisi rak dari nama.

	warehouse_type di sini BUKAN pilihan user — dia turunan posisi di pohon, dan
	dipakai sebagai filter menu Gudang/Rak/Bin. Posisi rak sebaliknya hanya diisi
	kalau masih kosong, supaya isian manual tidak ditimpa.
	"""
	doc.warehouse_type = _level_of(doc.parent_warehouse, doc.is_group)
	_set_position_from_name(doc)


def _level_of(parent, is_group):
	"""Gudang / Rak / Bin dari posisi di pohon (akar company tidak diberi tipe)."""
	if not parent:
		return None  # akar company
	grandparent, parent_type = frappe.get_cached_value(
		"Warehouse", parent, ["parent_warehouse", "warehouse_type"]
	)
	if not grandparent:
		return GUDANG  # anak langsung akar company
	if parent_type == GUDANG:
		return RAK if is_group else BIN
	return BIN


def reclassify_all():
	"""Hitung ulang warehouse_type SEluruh pohon (urut lft = induk sebelum anak).

	Dibutuhkan karena memindahkan satu gudang/rak tidak menjalankan validate pada
	keturunannya. Jalankan lewat bench console sesudah menata ulang pohon / impor.
	"""
	changed = 0
	for w in frappe.get_all(
		"Warehouse", fields=["name", "parent_warehouse", "is_group", "warehouse_type"], order_by="lft"
	):
		level = _level_of(w.parent_warehouse, w.is_group)
		if level != w.warehouse_type:
			frappe.db.set_value("Warehouse", w.name, "warehouse_type", level, update_modified=False)
			changed += 1
	return changed


def _set_position_from_name(doc):
	name = (doc.warehouse_name or "").strip()
	m = _BIN_NAME.match(name)
	if m:
		letters, bay, level = m.groups()
		order = _letters_index(letters) * 10000 + int(bay)
		tingkat = _letters_index(level)  # A = 1 = paling bawah; kosong = 0
	else:
		m = _LEGACY_NAME.match(name)
		if not m:
			return
		rack, segment, level = m.groups()
		order = _letters_index(rack) * 100000 + _letters_index(segment)
		tingkat = int(level)
	if not doc.get("custom_rack_order"):
		doc.custom_rack_order = order
	if tingkat and not doc.get("custom_rack_level"):
		doc.custom_rack_level = tingkat


def _gudang_of(warehouse):
	"""Naik ke leluhur bertipe Gudang (dirinya sendiri kalau sudah Gudang)."""
	while warehouse:
		parent, wtype = frappe.get_cached_value(
			"Warehouse", warehouse, ["parent_warehouse", "warehouse_type"]
		)
		if wtype == GUDANG:
			return warehouse
		warehouse = parent
	return None


def bins_under(gudang, company):
	"""Semua BIN (daun) di bawah gudang + peta bin -> nama rak induknya.

	Pakai descendants, bukan anak langsung, karena pohonnya 3 tingkat: bin ada di
	bawah rak induk. Bin yang menempel langsung ke gudang (mis. Staging Area)
	ikut terambil, dan rak induknya dianggap namanya sendiri.
	"""
	nodes = frappe.get_all(
		"Warehouse",
		filters={"name": ["descendants of", gudang], "disabled": 0, "company": company},
		fields=["name", "warehouse_name", "is_group", "parent_warehouse"],
	)
	label = {n.name: (n.warehouse_name or "").strip().upper() for n in nodes}
	bins = [n for n in nodes if not n.is_group]
	return bins, {b.name: label.get(b.parent_warehouse) or label[b.name] for b in bins}


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
	bins, rak_of = bins_under(gudang, company)
	if not bins:
		return {"skip": "gudang tidak punya rak"}

	# zoning: nama rak induk diawali salah satu huruf zona item group
	# (zona "A" mencakup rak AA/AB; kosong = semua rak boleh)
	zone = _zone_for_item(row["item_code"])
	if zone:
		bins = [b for b in bins if any(rak_of[b.name].startswith(z) for z in zone)]
		if not bins:
			return {"skip": "tidak ada rak zona {0} di gudang ini".format(",".join(sorted(zone)))}
	racks = [b.name for b in bins]
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


def split_gudang_from_rack(doc, method=None):
	"""Jaga kolom Warehouse dan Rack di baris PR supaya tidak pernah bertentangan.

	PO memilih GUDANG, PR memilih RAK di dalam gudang itu. Dipasang di dua titik
	karena ERPNext mengisi ulang rak di antaranya:

	  before_validate  gudang yang terbawa dari PO ada di field `warehouse`
	                   (berlabel Rack) -> pindahkan ke `custom_gudang`, rak
	                   dikosongkan. Kalau lolos, submit akan kena larangan SLE
	                   'group node warehouse'.
	  validate         rak sudah terisi, entah oleh user, Suggest Rack, atau
	                   Default Warehouse milik Item -> gudangnya diturunkan dari
	                   rak itu, supaya kolom Warehouse tidak menunjuk gudang lain.

	Pohonnya 3 tingkat, jadi gudang dicari dengan NAIK sampai ketemu tipe Gudang
	(_gudang_of) — parent langsung sebuah bin biasanya rak induk, bukan gudang.
	"""
	if doc.get("set_warehouse") and frappe.get_cached_value("Warehouse", doc.set_warehouse, "is_group"):
		doc.set_warehouse = None
	for row in doc.get("items") or []:
		wh = row.get("warehouse")
		if not wh:
			continue
		row.custom_gudang = _gudang_of(wh)
		# group (gudang / rak induk) tidak bisa menampung stok -> raknya dikosongkan
		if frappe.get_cached_value("Warehouse", wh, "is_group"):
			row.warehouse = None

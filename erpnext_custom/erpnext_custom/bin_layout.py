"""Layout gudang: rak, bin, dan penempatan item di dalamnya.

Lapisan ini SENGAJA terpisah dari akuntansi. Stok dan jurnal tetap berhenti di
Warehouse (gudang) -- PI yang mengakui persediaan, neraca ikut PI. Rak/Bin bukan
Warehouse, tidak punya Stock Ledger Entry, tidak punya akun. Yang disimpan di
sini cuma peta: item ini, di gudang ini, fisiknya ditaruh di bin mana.

    Warehouse "Gudang Jakarta"   stok + GL (leaf, tidak pernah jadi group)
      Rack "AA"                  layout
        Bin Location "AA0101A"   kapasitas berat + volume
          Item Bin Qty           saldo: item X sebanyak N di bin ini

Aturan yang dijaga:
  1. total Item Bin Qty per (item, gudang) TIDAK PERNAH melebihi stok ERPNext di
     gudang itu. Kelebihan dipangkas otomatis oleh reconcile() tiap ada SLE --
     jadi saat barang keluar lewat DN/Material Issue, bin ikut berkurang tanpa
     dokumen picking tambahan.
  2. isi sebuah bin tidak boleh melewati kapasitas berat / volumenya (ditolak
     saat Goods Receive disimpan).
  3. rak cuma menerima item yang boleh: tabel Item Khusus di master Rack kalau
     diisi, kalau kosong jatuh ke zona (Rack.rack_zone vs Item Group.custom_rack_zone).
  4. barang tidak boleh lebih panjang dari slot bin. Dua bin bersebelahan bisa
     disatukan jadi satu slot panjang lewat Bin Location.merged_into.

Kapasitas (berat, volume, panjang slot) sebuah bin TIGA LAPIS, yang pertama
terisi menang: isian bin itu sendiri, baris tingkat di master Rack, lalu default
di Stock Settings > tab Warehouse. Saklar penegakan aturan 3 dan 4 juga di tab
itu, supaya gudang yang masternya belum lengkap tidak langsung terkunci.

Ukuran barang: berat dari field native Item.weight_per_unit (+ weight_uom),
volume dari custom_length/width/height yang SELALU dalam METER -- satuan yang
sama dengan Panjang Slot bin, jadi panjang barang bisa dibandingkan langsung.
"""

import json
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

_FAR = 10**9  # bin tanpa urutan/tingkat dianggap paling jauh / paling atas

# Nama bin, dua dialek yang dipakai di lapangan:
#   AA0101A / AB4A / AE7  huruf rak + nomor bay + huruf tingkat (A = paling bawah)
#   A-AA-01               skema lama: rack A, segmen AA, tingkat 01
_BIN_NAME = re.compile(r"^([A-Za-z]+)[-. ]?(\d{1,4})[-. ]?([A-Za-z]?)$")
_LEGACY_NAME = re.compile(r"^([A-Za-z])[-. ]([A-Za-z]{1,3})[-. ]?(\d{1,3})$")


# ------------------------------------------------------------------ ukuran item


def item_size(item_code):
	"""(berat kg, volume m3) untuk SATU satuan stok item. 0 = tidak diketahui."""
	it = frappe.get_cached_value(
		"Item",
		item_code,
		["weight_per_unit", "weight_uom", "custom_length", "custom_width", "custom_height"],
		as_dict=True,
	)
	if not it:
		return 0.0, 0.0
	weight = flt(it.weight_per_unit) * _kg_factor(it.weight_uom)
	# dimensi selalu meter, jadi hasil kalinya sudah m3
	volume = flt(it.custom_length) * flt(it.custom_width) * flt(it.custom_height)
	return weight, volume


def _kg_factor(uom):
	"""Faktor ke kilogram. UOM tak dikenal dianggap 1 -- kapasitas berat memang
	cuma sebaik data master beratnya."""
	if not uom or uom.strip().lower() in ("kg", "kilogram", "kgs"):
		return 1.0
	value = frappe.db.get_value("UOM Conversion Factor", {"from_uom": uom, "to_uom": "Kg"}, "value")
	return flt(value) or 1.0


def item_length(item_code):
	"""Panjang satu unit dalam METER. 0 = tidak diketahui (tidak memblokir).

	Satu satuan dengan Panjang Slot di Bin Location, jadi dibandingkan apa adanya."""
	return flt(frappe.get_cached_value("Item", item_code, "custom_length"))


# ------------------------------------------------- kapasitas efektif sebuah bin


def stock_settings():
	"""Default gudang, ada di Stock Settings > tab Warehouse (dibuat di install.py)."""
	return frappe.get_cached_doc("Stock Settings")


def _level_row(rack, level):
	"""Baris tingkat di master Rack, mis. semua bin level A muat 500 kg."""
	if not rack:
		return None
	key = (level or "").strip().upper()
	for row in frappe.get_cached_doc("Rack", rack).get("levels") or []:
		if (row.level or "").strip().upper() == key:
			return row
	return None


def _own_caps(row):
	"""(berat kg, volume m3, panjang slot m) sebuah bin SEBELUM digabung.

	Tiga lapis, yang pertama terisi menang: isian bin itu sendiri, tingkat di
	master Rack, lalu default Stock Settings. 0 di semuanya = tanpa batas.
	"""
	lvl = _level_row(row.get("rack"), row.get("level"))
	setting = stock_settings()
	return tuple(
		flt(row.get(field)) or (flt(lvl.get(field)) if lvl else 0.0) or flt(setting.get(default))
		for field, default in (
			("capacity_weight", "custom_bin_capacity_weight"),
			("capacity_volume", "custom_bin_capacity_volume"),
			("slot_length", "custom_bin_slot_length"),
		)
	)


def _cap_add(a, b):
	"""0 = tanpa batas, jadi gabungan dengan bin tanpa batas ikut tanpa batas."""
	return 0.0 if a <= 0 or b <= 0 else a + b


def bin_caps_map(gudang):
	"""{bin: (berat kg, volume m3, panjang slot m)} efektif satu gudang, sekali query.

	Bin yang digabung (merged_into) TIDAK muncul sebagai kunci: kapasitas dan
	panjang slotnya sudah pindah ke bin induknya -- itulah "2 bin jadi 1 slot"
	untuk barang yang kepanjangan.
	"""
	rows = frappe.get_all(
		"Bin Location",
		filters={"gudang": gudang},
		fields=[
			"name", "rack", "level", "merged_into",
			"capacity_weight", "capacity_volume", "slot_length",
		],
	)
	own = {r.name: _own_caps(r) for r in rows}
	caps = {r.name: own[r.name] for r in rows if not r.merged_into}
	for r in rows:
		if r.merged_into in caps:
			caps[r.merged_into] = tuple(
				_cap_add(a, b) for a, b in zip(caps[r.merged_into], own[r.name])
			)
	return caps


# ------------------------------------------------------------------ isi bin


def bin_usage(bin_names):
	"""{bin: {"qty","weight","volume"}} dari saldo Item Bin Qty yang ada sekarang."""
	usage = {b: {"qty": 0.0, "weight": 0.0, "volume": 0.0} for b in bin_names}
	if not bin_names:
		return usage
	for row in frappe.get_all(
		"Item Bin Qty",
		filters={"bin_location": ["in", list(bin_names)], "qty": ["!=", 0]},
		fields=["bin_location", "item_code", "qty"],
	):
		w, v = item_size(row.item_code)
		u = usage[row.bin_location]
		u["qty"] += flt(row.qty)
		u["weight"] += flt(row.qty) * w
		u["volume"] += flt(row.qty) * v
	return usage


def bin_free(caps, used):
	"""Sisa (berat, volume) dari kapasitas efektif bin (bin_caps_map). None = tanpa batas."""
	cap_w, cap_v = flt(caps[0]), flt(caps[1])
	free_w = None if cap_w <= 0 else cap_w - flt(used.get("weight"))
	free_v = None if cap_v <= 0 else cap_v - flt(used.get("volume"))
	return free_w, free_v


def fits(free_w, free_v, weight, volume):
	"""Berapa unit lagi yang muat, dibatasi berat DAN volume. None = tak terbatas.

	Item tanpa ukuran (berat/volume 0) dianggap tidak memakan kapasitas itu --
	kalau tidak, satu master yang belum diisi ukurannya akan memblokir bin.
	"""
	limits = []
	if free_w is not None and weight > 0:
		limits.append(free_w / weight)
	if free_v is not None and volume > 0:
		limits.append(free_v / volume)
	if not limits:
		return None
	return max(0.0, min(limits))


# ------------------------------------------------------------------ saldo


def placed_qty(item_code, gudang):
	"""Total item ini yang sudah punya tempat di gudang ini."""
	# dijumlah di python: "sum(qty)" sebagai string ditolak query builder Frappe.
	return sum(
		flt(q)
		for q in frappe.get_all(
			"Item Bin Qty", filters={"item_code": item_code, "gudang": gudang}, pluck="qty"
		)
	)


def stock_qty(item_code, gudang):
	"""Stok ERPNext yang sesungguhnya di gudang itu (sumber kebenaran)."""
	return flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": gudang}, "actual_qty")
	)


def move(item_code, bin_location, qty, allow_short=False):
	"""Tambah/kurangi saldo sebuah bin. Saldo nol dihapus supaya tabel tidak kembung.

	Mengeluarkan lebih banyak dari isi bin DITOLAK -- dulu diam-diam dipotong jadi
	nol, dan peta bin jadi bohong tanpa ada yang tahu. Pengecualiannya cuma
	pembatalan dokumen (allow_short): saldonya mungkin memang sudah dipangkas
	reconcile() karena barangnya sudah keluar lewat DN, dan pembatalan tidak boleh
	ikut terkunci gara-gara itu.
	"""
	name = frappe.db.get_value(
		"Item Bin Qty", {"item_code": item_code, "bin_location": bin_location}
	)
	if name:
		doc = frappe.get_doc("Item Bin Qty", name)
		sisa = flt(doc.qty) + flt(qty)
		if sisa < -0.0001 and not allow_short:
			frappe.throw(
				_("Bin {0} cuma berisi {1} {2}, tidak bisa dikeluarkan {3}.").format(
					bin_location, flt(doc.qty), item_code, abs(flt(qty))
				)
			)
		doc.qty = sisa
		if doc.qty <= 0:
			doc.delete(ignore_permissions=True)
			return
		doc.save(ignore_permissions=True)
		return
	if flt(qty) <= 0:
		if allow_short:
			return
		frappe.throw(
			_("Bin {0} tidak berisi {1}, tidak bisa dikurangi.").format(bin_location, item_code)
		)
	loc = frappe.get_cached_value("Bin Location", bin_location, ["gudang", "rack"], as_dict=True)
	frappe.get_doc(
		{
			"doctype": "Item Bin Qty",
			"item_code": item_code,
			"bin_location": bin_location,
			"gudang": loc.gudang,
			"rack": loc.rack,
			"qty": flt(qty),
			"stock_uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
		}
	).insert(ignore_permissions=True)


def reconcile(item_code, gudang):
	"""Pangkas saldo bin kalau sudah melebihi stok gudang.

	Dipanggil tiap Stock Ledger Entry: barang keluar lewat DN / Material Issue
	otomatis mengurangi bin, tanpa dokumen picking. Yang dipangkas duluan adalah
	bin TERDEKAT pick area dan paling gampang digapai (sort_key) -- itu memang
	yang diambil orang gudang duluan.
	Idempoten, jadi aman dipanggil ulang saat cancel atau repost.
	"""
	excess = placed_qty(item_code, gudang) - stock_qty(item_code, gudang)
	if excess <= 0:
		return
	rows = frappe.get_all(
		"Item Bin Qty",
		filters={"item_code": item_code, "gudang": gudang, "qty": [">", 0]},
		fields=["name", "bin_location", "qty"],
	)
	pos = _positions([r.bin_location for r in rows])
	for r in sorted(rows, key=lambda r: (*pos[r.bin_location], r.bin_location)):
		take = min(excess, flt(r.qty))
		sisa = flt(r.qty) - take
		if sisa <= 0:
			frappe.delete_doc("Item Bin Qty", r.name, ignore_permissions=True, force=True)
		else:
			frappe.db.set_value("Item Bin Qty", r.name, "qty", sisa, update_modified=False)
		excess -= take
		if excess <= 0:
			break


def reconcile_sle(doc, method=None):
	"""Hook Stock Ledger Entry: stok turun -> isi bin ikut turun."""
	if flt(doc.actual_qty) < 0:
		reconcile(doc.item_code, doc.warehouse)


# ------------------------------------------------------------------ saran bin


def _pick_effort(rack, level, rack_level):
	"""Seberapa susah tingkat itu digapai. Makin kecil makin didahulukan.

	Tiga lapis: kolom Urutan Ambil di tabel Tingkat master Rack, urutan global di
	Stock Settings > Warehouse (mis. "B,A,C,D,E" -- setinggi pinggang duluan),
	lalu nomor tingkat apa adanya (makin ke bawah makin gampang).
	"""
	key = (level or "").strip().upper()
	if rack:
		for row in rack.get("levels") or []:
			if (row.level or "").strip().upper() == key and row.pick_order:
				return row.pick_order
	urutan = [
		x.strip().upper()
		for x in (stock_settings().get("custom_level_pick_order") or "").split(",")
		if x.strip()
	]
	if key and key in urutan:
		return urutan.index(key) + 1
	return rack_level or _FAR


def sort_key(b):
	"""(jarak rak, susah digapai, urutan bay) -- makin kecil makin duluan dipakai.

	Jarak diambil dari Rack.distance_order (satu angka per rak, mis. rak A nempel
	pick area); kalau raknya belum diberi nomor, jatuh ke tebakan dari kode bin.
	"""
	rack = frappe.get_cached_doc("Rack", b.get("rack")) if b.get("rack") else None
	return (
		(rack.distance_order if rack else 0) or _FAR,
		_pick_effort(rack, b.get("level"), b.get("rack_level")),
		b.get("rack_order") or _FAR,
	)


def _positions(bin_names):
	"""{bin: sort_key} -- 'paling dekat dan paling gampang diambil' duluan."""
	out = {}
	if bin_names:
		for b in frappe.get_all(
			"Bin Location",
			filters={"name": ["in", list(bin_names)]},
			fields=["name", "rack", "level", "rack_order", "rack_level"],
		):
			out[b.name] = sort_key(b)
	return {b: out.get(b, (_FAR, _FAR, _FAR)) for b in bin_names}


def _zone_for_item(item_code):
	"""Zona rak yang diizinkan untuk item ini (Item Group.custom_rack_zone, naik
	ke parent group sampai ketemu). None = bebas."""
	group = frappe.db.get_value("Item", item_code, "item_group")
	while group:
		zone, group = frappe.db.get_value(
			"Item Group", group, ["custom_rack_zone", "parent_item_group"]
		)
		if zone:
			return {z.strip().upper() for z in zone.split(",") if z.strip()}
	return None


def item_allowed(rack, item_code, zone=False):
	"""Boleh atau tidak item ini masuk rak ini.

	Dua lapis dan tabel Item Khusus di master Rack yang menang: kalau tabel itu
	diisi, HANYA item di situ yang boleh. Tabel kosong = jatuh ke zona
	(Rack.rack_zone vs Item Group.custom_rack_zone). Item yang groupnya tidak
	menyebut zona = bebas masuk rak mana saja.
	"""
	doc = frappe.get_cached_doc("Rack", rack)
	if doc.get("allowed_items"):
		return item_code in {r.item_code for r in doc.allowed_items}
	zone = _zone_for_item(item_code) if zone is False else zone
	if not zone:
		return True
	return (doc.rack_zone or "").strip().upper() in zone


def candidate_bins(gudang, item_code, caps=None):
	"""Bin aktif di gudang yang boleh menerima item ini.

	Tiga saringan: bin yang sudah digabung ke bin lain tidak berdiri sendiri,
	raknya harus menerima item ini, dan slotnya harus cukup panjang untuk barangnya.
	"""
	caps = bin_caps_map(gudang) if caps is None else caps
	bins = [
		b
		for b in frappe.get_all(
			"Bin Location",
			filters={"gudang": gudang, "disabled": 0},
			fields=["name", "rack", "level", "merged_into", "rack_order", "rack_level"],
		)
		if not b.merged_into
	]
	rak = set(
		frappe.get_all(
			"Rack", filters={"gudang": gudang, "kind": "Rak", "disabled": 0}, pluck="name"
		)
	)
	bins = [b for b in bins if b.rack in rak]
	zone = _zone_for_item(item_code)
	bins = [b for b in bins if item_allowed(b.rack, item_code, zone)]
	panjang = item_length(item_code)
	if panjang:
		bins = [b for b in bins if not caps.get(b.name, (0, 0, 0))[2] or caps[b.name][2] >= panjang]
	return bins


@frappe.whitelist()
def suggest(gudang, rows):
	"""Bagi qty tiap baris ke bin-bin yang masih muat.

	Urutan pilih: bin yang SUDAH berisi item sama (konsolidasi) dulu, lalu yang
	paling dekat pick area dan paling gampang digapai (sort_key), baru bin paling
	kosong sebagai pemecah seri. Satu bin tidak cukup = sisanya lanjut ke bin
	berikutnya.
	"""
	rows = json.loads(rows) if isinstance(rows, str) else rows
	out = []
	# Usage dihitung SEKALI lalu dikurangi sendiri selama membagi, supaya dua
	# baris berbeda tidak sama-sama dijanjikan bin yang cuma muat satu.
	usage = bin_usage(frappe.get_all("Bin Location", filters={"gudang": gudang}, pluck="name"))
	caps = bin_caps_map(gudang)
	for row in rows:
		item_code = row.get("item_code")
		need = flt(row.get("qty"))
		if not item_code or need <= 0:
			out.append(None)
			continue
		bins = candidate_bins(gudang, item_code, caps)
		if not bins:
			out.append({"skip": _("tidak ada bin yang cocok: zona rak, daftar item, atau panjang slot")})
			continue
		weight, volume = item_size(item_code)
		occupied = set(
			frappe.get_all(
				"Item Bin Qty",
				filters={
					"item_code": item_code,
					"bin_location": ["in", [b.name for b in bins]],
					"qty": [">", 0],
				},
				pluck="bin_location",
			)
		)
		# konsolidasi dulu (bin yang sudah berisi item sama), lalu tempat yang
		# paling dekat pick area dan paling gampang digapai. Bin paling kosong
		# cuma pemecah seri terakhir -- tempat terdekat lebih berharga.
		ordered = sorted(
			bins,
			key=lambda b: (
				0 if b.name in occupied else 1,
				*sort_key(b),
				usage.get(b.name, {}).get("qty", 0.0),
				b.name,
			),
		)
		allocations, sisa = [], need
		for b in ordered:
			used = usage.setdefault(b.name, {"qty": 0.0, "weight": 0.0, "volume": 0.0})
			muat = fits(*bin_free(caps.get(b.name, (0.0, 0.0, 0.0)), used), weight, volume)
			take = sisa if muat is None else min(sisa, muat)
			if take <= 0:
				continue
			allocations.append({"bin_location": b.name, "qty": take})
			used["qty"] += take
			used["weight"] += take * weight
			used["volume"] += take * volume
			sisa -= take
			if sisa <= 0:
				break
		result = {"allocations": allocations}
		if sisa > 0:
			result["shortage"] = sisa
		if not allocations:
			result["skip"] = _("semua bin sudah penuh")
		out.append(result)
	return out


@frappe.whitelist()
def invoice_gudang(purchase_invoice):
	"""Gudang sebuah nota, kalau cuma satu. None = notanya memakai beberapa gudang.

	Dipakai dua tempat: form Goods Receive mengisi Gudang begitu nota dipilih, dan
	pull_purchase_invoice di bawah memakai jawaban yang sama supaya keduanya tidak
	pernah berbeda pendapat.
	"""
	gudang = {
		r.warehouse
		for r in frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": purchase_invoice, "parenttype": "Purchase Invoice", "docstatus": 1},
			fields=["warehouse"],
		)
		if r.warehouse
	}
	return gudang.pop() if len(gudang) == 1 else None


@frappe.whitelist()
def pull_purchase_invoice(purchase_invoice, gudang=None):
	"""Isi tabel Goods Receive dari baris sebuah Purchase Invoice.

	Qty dipakai stock_qty (satuan stok), sama dengan satuan saldo bin. Yang sudah
	diterima lewat Goods Receive LAIN untuk nota yang sama dipotong, supaya nota
	yang diterima bertahap tidak menempatkan barang dua kali.

	Balikan: {"gudang": ..., "rows": [...]}. Gudang diturunkan dari nota kalau
	pemanggilnya belum menentukan -- kecuali notanya memang memakai lebih dari satu.
	"""
	rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"parent": purchase_invoice, "parenttype": "Purchase Invoice", "docstatus": 1},
		fields=["item_code", "warehouse", "stock_qty", "stock_uom"],
	)
	if not rows:
		frappe.throw(_("{0} tidak punya baris barang.").format(purchase_invoice))
	if not gudang:
		gudang = invoice_gudang(purchase_invoice)
		if not gudang:
			frappe.throw(_("Nota ini memakai lebih dari satu gudang, pilih gudangnya dulu."))

	diminta, satuan = defaultdict(float), {}
	for r in rows:
		if r.warehouse != gudang:
			continue
		diminta[r.item_code] += flt(r.stock_qty)
		satuan[r.item_code] = r.stock_uom

	sudah = defaultdict(float)
	diterima = frappe.get_all(
		"Goods Receive", filters={"purchase_invoice": purchase_invoice, "docstatus": 1}, pluck="name"
	)
	if diterima:
		for d in frappe.get_all(
			"Goods Receive Item",
			filters={"parent": ["in", diterima], "parenttype": "Goods Receive"},
			fields=["item_code", "qty"],
		):
			sudah[d.item_code] += flt(d.qty)

	out = [
		{"item_code": item_code, "qty": sisa, "stock_uom": satuan[item_code]}
		for item_code, qty in diminta.items()
		if (sisa := qty - sudah[item_code]) > 0
	]
	return {"gudang": gudang, "rows": out}


@frappe.whitelist()
def rack_capacity(gudang=None):
	"""Ringkasan per rak: kapasitas, terpakai, dan sisa.

	Inilah jawaban "1 rak ini muat berapa lagi" -- kapasitas rak TIDAK disimpan,
	selalu jumlah bin-bin di bawahnya, jadi tidak bisa basi.
	"""
	filters = {"disabled": 0, "kind": ("in", ("Rak", "Staging"))}
	if gudang:
		filters["gudang"] = gudang
	out, caps_gudang = [], {}
	for rack in frappe.get_all("Rack", filters=filters, fields=["name", "gudang", "rack_code"]):
		bins = frappe.get_all(
			"Bin Location",
			filters={"rack": rack.name, "disabled": 0},
			fields=["name", "capacity_weight", "capacity_volume"],
		)
		# pakai kapasitas EFEKTIF (default tingkat / Stock Settings / gabungan bin)
		caps = caps_gudang.setdefault(rack.gudang, bin_caps_map(rack.gudang))
		for b in bins:
			b.capacity_weight, b.capacity_volume = caps.get(b.name, (0.0, 0.0, 0.0))[:2]
		usage = bin_usage([b.name for b in bins])
		cap_w = sum(flt(b.capacity_weight) for b in bins)
		cap_v = sum(flt(b.capacity_volume) for b in bins)
		used_w = sum(u["weight"] for u in usage.values())
		used_v = sum(u["volume"] for u in usage.values())
		out.append(
			{
				"rack": rack.name,
				"gudang": rack.gudang,
				"rack_code": rack.rack_code,
				"bins": len(bins),
				"capacity_weight": cap_w,
				"used_weight": used_w,
				"free_weight": cap_w - used_w if cap_w else None,
				"capacity_volume": cap_v,
				"used_volume": used_v,
				"free_volume": cap_v - used_v if cap_v else None,
				"qty": sum(u["qty"] for u in usage.values()),
			}
		)
	return out


# ------------------------------------------------------------------ denah 2D

# SEMUA angka denah dalam METER — posisi maupun ukuran. Perbesaran layar (px per meter)
# urusan halaman Layout saja, tidak pernah ikut tersimpan; itu yang membuat denah selalu
# sesuai skala dan ukuran kotak tidak pernah bisa beda dari ukuran fisik raknya.
#
# Ukuran kotak = Rack.panjang x Rack.lebar. Tidak ada map_w/map_h lagi: dua sumber ukuran
# berarti cepat atau lambat keduanya berbeda dan tidak ada cara tahu mana yang benar.
_DEF_W, _DEF_H, _GAP = 10.0, 2.5, 1.5


def rack_weight(rack):
	"""Berat yang sudah duduk di sebuah rak: jumlah isi semua binnya."""
	bins = frappe.get_all("Bin Location", filters={"rack": rack}, pluck="name")
	return sum(u["weight"] for u in bin_usage(bins).values())


@frappe.whitelist()
def layout(gudang):
	"""Denah satu gudang: kotak per rak + ringkasan isi tiap tingkat.

	Posisi kotak disimpan di Rack (map_x/y/w/h) dan digeser langsung di halaman
	Layout. Isi bin TIDAK disimpan di sini -- selalu dihitung dari Item Bin Qty.
	"""
	racks = frappe.get_all(
		"Rack",
		filters={"gudang": gudang},
		fields=[
			"name", "rack_code", "kind", "rack_zone", "disabled",
			"panjang", "lebar", "tinggi", "volume", "max_weight",
			"map_x", "map_y",
		],
		order_by="rack_code",
	)
	bins = frappe.get_all(
		"Bin Location",
		filters={"gudang": gudang},
		fields=["name", "rack", "bin_code", "level", "capacity_weight", "capacity_volume", "disabled"],
	)
	caps = bin_caps_map(gudang)
	for b in bins:
		b.capacity_weight, b.capacity_volume = caps.get(b.name, (0.0, 0.0, 0.0))[:2]
	usage = bin_usage([b.name for b in bins])

	by_rack = {}
	for b in bins:
		by_rack.setdefault(b.rack, []).append(b)

	# y default dihitung dulu: tiap rak menumpuk di bawah rak sebelumnya, jadi
	# tingginya sendiri yang menentukan jarak, bukan angka tetap.
	taruh_y, kursor = {}, _GAP
	for rack in racks:
		taruh_y[rack.name] = kursor
		kursor += (flt(rack.lebar) or _DEF_H) + _GAP

	out = []
	for i, rack in enumerate(racks):
		mine = by_rack.get(rack.name, [])
		levels = {}
		for b in mine:
			lv = levels.setdefault(
				b.level or "-", {"level": b.level or "-", "bins": 0, "capacity": 0.0, "used": 0.0, "qty": 0.0}
			)
			u = usage.get(b.name, {})
			lv["bins"] += 1
			lv["capacity"] += flt(b.capacity_weight)
			lv["used"] += flt(u.get("weight"))
			lv["qty"] += flt(u.get("qty"))
		out.append(
			{
				"name": rack.name,
				"rack_code": rack.rack_code,
				"kind": rack.kind or "Rak",
				"zone": rack.rack_zone,
				"disabled": rack.disabled,
				# rak baru belum punya posisi -> ditumpuk sebagai baris sejajar,
				# persis bentuk lorong gudang sungguhan
				"x": flt(rack.map_x) or _GAP,
				"y": flt(rack.map_y) or taruh_y[rack.name],
				# ukuran kotak = ukuran fisik rak (meter). Rak yang ukurannya belum
				# diisi dapat kotak default, tinggal ditarik gagangnya di denah.
				"w": flt(rack.panjang) or _DEF_W,
				"h": flt(rack.lebar) or _DEF_H,
				"panjang": flt(rack.panjang),
				"lebar": flt(rack.lebar),
				"tinggi": flt(rack.tinggi),
				"volume": flt(rack.volume),
				"max_weight": flt(rack.max_weight),
				"bins": len(mine),
				"capacity": sum(flt(b.capacity_weight) for b in mine),
				"used": sum(flt(usage.get(b.name, {}).get("weight")) for b in mine),
				"qty": sum(flt(usage.get(b.name, {}).get("qty")) for b in mine),
				"levels": sorted(levels.values(), key=lambda l: l["level"], reverse=True),
			}
		)
	return out


@frappe.whitelist()
def add_box(gudang, kind, code):
	"""Tambah kotak baru di denah: Rak, Staging, Pintu, atau Kantor.

	Boleh berapa pun per gudang (mis. dua staging area) -- yang membedakan cuma
	kodenya. Posisinya tidak diisi di sini: kotak baru dijejer otomatis oleh
	layout(), tinggal digeser ke tempatnya.
	"""
	doc = frappe.get_doc(
		{"doctype": "Rack", "gudang": gudang, "kind": kind, "rack_code": code}
	).insert()
	return doc.name


# Denah lorong: rak dipasangkan punggung-ke-punggung, tiap pasang dipisah gang,
# dan pindah kolom kalau satu kolom sudah penuh. METER.
_LANE_W, _LANE_H, _AISLE, _PAIRS_PER_COL = 20.0, 2.8, 3.6, 4


@frappe.whitelist()
def arrange(gudang):
	"""Tata ulang kotak jadi denah lorong. Balikan: berapa kotak yang dipindah.

	Ini TITIK AWAL, bukan denah sungguhan -- gudang asli tidak pernah serapi ini.
	Gunanya cuma supaya tidak menata belasan kotak dari tumpukan kosong; sesudah
	ini tetap digeser tangan.

	Rak dan Staging selalu ditata ulang (itu yang diminta). Pintu dan Kantor yang
	posisinya SUDAH pernah diatur tidak disentuh -- itu patokan yang digambar orang
	gudang -- dan lorongnya DIGESER TURUN supaya tidak menabraknya; yang belum
	pernah ditaruh dijejer di bawah lorong.
	"""
	frappe.has_permission("Rack", "write", throw=True)
	lorong, patokan = [], []
	for r in frappe.get_all(
		"Rack",
		filters={"gudang": gudang},
		fields=["name", "kind", "map_x", "map_y", "panjang", "lebar"],
		order_by="rack_code",
	):
		(lorong if (r.kind or "Rak") in ("Rak", "Staging") else patokan).append(r)

	# Patokan yang sudah digambar (mis. pintu di dinding atas) tidak boleh tertimpa:
	# kalau dia menghalangi jalur kolom, lorongnya mulai di bawahnya.
	kolom_total = -(-len(lorong) // (2 * _PAIRS_PER_COL)) or 1
	batas_kanan = _GAP + kolom_total * (_LANE_W + _AISLE) - _AISLE
	atas = _GAP
	for r in patokan:
		if not (r.map_x or r.map_y):
			continue
		if r.map_x < batas_kanan and r.map_x + flt(r.panjang) > _GAP:
			atas = max(atas, flt(r.map_y) + flt(r.lebar) + _AISLE)

	for i, r in enumerate(lorong):
		pasang, sisi = divmod(i, 2)  # dua rak sepasang = punggung-ke-punggung
		kolom, baris = divmod(pasang, _PAIRS_PER_COL)
		frappe.db.set_value(
			"Rack",
			r.name,
			{
				"map_x": _GAP + kolom * (_LANE_W + _AISLE),
				"map_y": atas + baris * (2 * _LANE_H + _AISLE) + sisi * _LANE_H,
				# ukuran lorong = ukuran FISIK raknya; tidak ada angka denah terpisah
				"panjang": _LANE_W,
				"lebar": _LANE_H,
			},
			update_modified=False,
		)

	# di bawah lorong, bukan di kanannya -- kanan biasanya sudah dipakai pintu
	bawah, x = atas + _PAIRS_PER_COL * (2 * _LANE_H + _AISLE), _GAP
	dipindah = len(lorong)
	for r in patokan:
		if r.map_x or r.map_y:
			continue
		frappe.db.set_value(
			"Rack", r.name, {"map_x": x, "map_y": bawah, "panjang": 8.0, "lebar": 5.0},
			update_modified=False,
		)
		x += 8.0 + _GAP
		dipindah += 1
	# tanpa commit: request whitelist sudah commit sendiri, dan commit di sini
	# bikin fixture test ikut permanen (rollback tearDown jadi tidak ada gunanya)
	return dipindah


@frappe.whitelist()
def distance_from_map(gudang):
	"""Isi Urutan Jarak tiap rak dari kotak Pintu terdekat di denah.

	Dipakai supaya "prioritaskan tempat terdekat" tidak perlu diketik satu-satu:
	gambar pintunya, tekan tombolnya. Yang disimpan PERINGKAT 1..N, bukan piksel,
	supaya satu skala dengan angka yang diisi tangan dan gampang ditimpa lagi.
	Posisi diambil dari layout(), jadi rak yang belum pernah ditata pun terhitung.
	"""
	frappe.has_permission("Rack", "write", throw=True)
	boxes = layout(gudang)
	pintu = [_center(b) for b in boxes if b["kind"] == "Pintu"]
	if not pintu:
		frappe.throw(_("Gudang ini belum punya kotak Pintu di denah."))
	jarak = []
	for b in boxes:
		if b["kind"] != "Rak":
			continue
		x, y = _center(b)
		jarak.append((min(((x - px) ** 2 + (y - py) ** 2) ** 0.5 for px, py in pintu), b["name"]))
	for urutan, (_d, name) in enumerate(sorted(jarak), start=1):
		frappe.db.set_value("Rack", name, "distance_order", urutan, update_modified=False)
		frappe.clear_document_cache("Rack", name)
	return len(jarak)


def _center(box):
	return (box["x"] + box["w"] / 2.0, box["y"] + box["h"] / 2.0)


@frappe.whitelist()
def save_layout(positions):
	"""Simpan posisi & ukuran kotak hasil geser/tarik di halaman Layout. SEMUA METER.

	Menarik gagang kotak = mengubah ukuran FISIK raknya (panjang x lebar), bukan angka
	gambar tersendiri. Karena itu volumenya ikut dihitung ulang di sini — rak disimpan
	lewat db_set (tanpa memicu validate) supaya menggeser belasan kotak tetap ringan.
	"""
	positions = json.loads(positions) if isinstance(positions, str) else positions
	frappe.has_permission("Rack", "write", throw=True)
	for p in positions:
		panjang, lebar = flt(p["w"]), flt(p["h"])
		# tinggi tidak bisa digambar di denah 2D, jadi ikut dititipkan panel samping
		# kalau memang diubah; kalau tidak, yang tersimpan sekarang dipakai apa adanya
		tinggi = flt(p["tinggi"]) if p.get("tinggi") is not None else flt(
			frappe.db.get_value("Rack", p["name"], "tinggi")
		)
		frappe.db.set_value(
			"Rack",
			p["name"],
			{
				"map_x": flt(p["x"]),
				"map_y": flt(p["y"]),
				"panjang": panjang,
				"lebar": lebar,
				"tinggi": tinggi,
				"volume": panjang * lebar * tinggi,
			},
			update_modified=False,
		)
		frappe.clear_document_cache("Rack", p["name"])
	return len(positions)


@frappe.whitelist()
def set_rack_size(rack, panjang=None, lebar=None, tinggi=None):
	"""Ukuran satu rak dari panel samping halaman Layout. METER.

	Tinggi tidak bisa digambar di denah 2D, jadi inilah satu-satunya jalannya; panjang
	dan lebar ikut di sini supaya angkanya bisa diketik persis, bukan cuma ditarik.
	"""
	frappe.has_permission("Rack", "write", throw=True)
	doc = frappe.get_doc("Rack", rack)
	for field, value in (("panjang", panjang), ("lebar", lebar), ("tinggi", tinggi)):
		if value is not None:
			doc.set(field, flt(value))
	doc.save()  # lewat validate: volume dihitung di controller Rack
	return {"panjang": doc.panjang, "lebar": doc.lebar, "tinggi": doc.tinggi, "volume": doc.volume}


@frappe.whitelist()
def bin_map(gudang):
	"""Bin tiap rak, dikelompokkan per BAY, untuk tombol Tampilkan Bin di denah.

	Denah ini tampak atas, jadi yang bisa digambar cuma bay (petak sepanjang rak) --
	tingkat A..E menumpuk ke arah kita dan tidak punya tempat di gambar 2D. Satu bay
	karena itu merangkum semua tingkatnya; rinciannya tetap di panel samping.

	Bay diambil dari angka di kode bin (AA0101A -> 0101). Kode yang tidak berpola
	(BULKY DEPAN, LORONG AA-AB) tidak punya bay, jadi tiap bin berdiri sendiri.
	Dipanggil terpisah dari layout(): payload-nya berat dan cuma dipakai saat
	tombolnya dinyalakan.
	"""
	bins = frappe.get_all(
		"Bin Location",
		filters={"gudang": gudang, "disabled": 0},
		fields=["name", "rack", "bin_code", "level", "merged_into", "rack_order"],
		order_by="rack_order, bin_code",
	)
	usage = bin_usage([b.name for b in bins])
	caps = bin_caps_map(gudang)

	per_rak = {}
	for b in bins:
		m = _BIN_NAME.match((b.bin_code or "").strip())
		bay = m.group(2) if m else (b.bin_code or b.name)
		petak = per_rak.setdefault(b.rack, {}).setdefault(
			bay, {"bay": bay, "bins": [], "qty": 0.0, "used": 0.0, "capacity": 0.0, "order": b.rack_order or _FAR}
		)
		u = usage.get(b.name, {})
		petak["bins"].append({"bin": b.name, "bin_code": b.bin_code, "level": b.level or "-", "qty": flt(u.get("qty"))})
		petak["qty"] += flt(u.get("qty"))
		petak["used"] += flt(u.get("weight"))
		# bin yang digabung tidak punya kapasitas sendiri lagi (sudah pindah ke induknya)
		petak["capacity"] += flt(caps.get(b.name, (0.0, 0.0, 0.0))[0])
		petak["order"] = min(petak["order"], b.rack_order or _FAR)

	return {
		rack: sorted(petak.values(), key=lambda s: (s["order"], s["bay"]))
		for rack, petak in per_rak.items()
	}


@frappe.whitelist()
def rack_level_contents(rack, level=None):
	"""Isi sebuah rak, dikelompokkan per tingkat lalu per bin."""
	filters = {"rack": rack}
	if level:
		filters["level"] = level
	bins = frappe.get_all(
		"Bin Location",
		filters=filters,
		fields=["name", "bin_code", "level", "capacity_weight", "disabled", "rack_order"],
		order_by="rack_order, bin_code",
	)
	caps = bin_caps_map(frappe.get_cached_value("Rack", rack, "gudang"))
	for b in bins:
		b.capacity_weight = caps.get(b.name, (0.0, 0.0, 0.0))[0]
	usage = bin_usage([b.name for b in bins])
	items = {}
	for row in frappe.get_all(
		"Item Bin Qty",
		filters={"bin_location": ["in", [b.name for b in bins]]} if bins else {"name": ""},
		fields=["bin_location", "item_code", "item_name", "qty", "stock_uom"],
	):
		items.setdefault(row.bin_location, []).append(row)
	out = []
	for b in bins:
		u = usage.get(b.name, {})
		out.append(
			{
				"bin": b.name,
				"bin_code": b.bin_code,
				"level": b.level or "-",
				"disabled": b.disabled,
				"capacity": flt(b.capacity_weight),
				"used": flt(u.get("weight")),
				"qty": flt(u.get("qty")),
				"items": items.get(b.name, []),
			}
		)
	return out


# ------------------------------------------------------------------ posisi bin


def _letters_index(letters):
	"""AA -> 27, AB -> 28 (base-26, A=1) -- urut alfabetis jadi urut angka."""
	idx = 0
	for ch in (letters or "").upper():
		idx = idx * 26 + (ord(ch) - ord("A") + 1)
	return idx


def set_position_from_name(doc):
	"""Tebak tingkat + urutan jarak dari kode bin. Isian manual tidak ditimpa.

	Huruf tingkatnya bukan hiasan: itu yang menyambungkan bin ke baris Tingkat di
	master Rack (kapasitas default per tingkat), jadi bin yang dibuat manual pun
	harus terisi, bukan cuma yang lewat importer.
	"""
	name = (doc.bin_code or "").strip()
	m = _BIN_NAME.match(name)
	if m:
		letters, bay, level = m.groups()
		order = _letters_index(letters) * 10000 + int(bay)
		tingkat = _letters_index(level)
	else:
		m = _LEGACY_NAME.match(name)
		if not m:
			return
		rack, segment, level = m.groups()
		order = _letters_index(rack) * 100000 + _letters_index(segment)
		tingkat = int(level)
	if not doc.get("rack_order"):
		doc.rack_order = order
	if tingkat and not doc.get("rack_level"):
		doc.rack_level = tingkat
	if level and not doc.get("level"):
		doc.level = level.upper()

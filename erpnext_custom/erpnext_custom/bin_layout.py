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
     gudang itu. Saldo tiap bin dipelihara oleh bin_ledger.py (buku besar bin) --
     jadi saat barang keluar lewat DN/Material Issue, bin ikut berkurang tanpa
     dokumen picking tambahan.
  2. isi sebuah bin tidak boleh melewati kapasitas berat / volumenya (ditolak
     saat Goods Receive disimpan).
  3. bin cuma menerima item yang boleh: tabel Item Khusus di master Bin Location
     kalau diisi, kalau kosong jatuh ke tabel yang sama di master Rack, lalu ke
     zona (Rack.rack_zone vs Item Group.custom_rack_zone).
  4. barang tidak boleh lebih panjang dari slot bin. Dua bin bersebelahan bisa
     disatukan jadi satu slot panjang lewat Bin Location.merged_into.
  5. barang berat tidak boleh naik: di atas ambang berat per unit (Stock Settings
     > Warehouse) cuma boleh sampai tingkat ke-N, default 3.
  6. barang yang tidak boleh bercampur tidak pernah sebin: centang Bin Khusus
     (maunya sendirian) atau Grup Campur Bin di master Item.

Kapasitas (berat, volume, panjang slot) sebuah bin TIGA LAPIS, yang pertama
terisi menang: isian bin itu sendiri, baris tingkat di master Rack, lalu default
di Stock Settings > tab Warehouse. Saklar penegakan aturan 3 dan 4 juga di tab
itu, supaya gudang yang masternya belum lengkap tidak langsung terkunci.

Ukuran barang: berat dari field native Item.weight_per_unit (+ weight_uom),
volume dari custom_length/width/height yang SELALU dalam METER -- satuan yang
sama dengan Panjang Slot bin, jadi panjang barang bisa dibandingkan langsung.
"""

import json
import math
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

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


def packing_rules():
	"""{item: (isi per kemasan, kemasan per bin)} dari Stock Settings > Warehouse.

	Ini jawaban "satu bin muat berapa" yang dinyatakan dalam KEMASAN, bukan kilogram:
	4 drum per bin, 2 pallet per bin. Sengaja tinggal di setting gudang, bukan di
	master Item -- yang menentukan muat berapa itu raknya, bukan barangnya.

	Baris yang salah satu angkanya 0 DILEWATI, sama seperti kapasitas berat/volume:
	0 berarti "tidak diatur", bukan "nol yang muat". Kalau tidak dilewati, satu baris
	master yang setengah terisi akan membagi nol di setiap simpan dokumen, setiap
	denah gudang, dan setiap submit dokumen stok -- lewat bin_usage yang dipanggil
	di semua jalur itu.
	"""
	out = {}
	for row in stock_settings().get("custom_bin_packing_rules") or []:
		qpp, ppb = flt(row.qty_per_package), cint(row.packages_per_bin)
		if qpp > 0 and ppb > 0 and row.item_code not in out:
			out[row.item_code] = (qpp, ppb)
	return out


def pack_share(qty, pack):
	"""Bagian bin yang dimakan qty ini, dihitung dalam KEMASAN UTUH (0..1 per bin).

	Kemasan itu diskret dan itulah seluruh gunanya aturan ini: drum yang tinggal
	berisi 1 Kg tetap memakan satu slot palet. Menghitungnya lurus (qty dibagi isi
	per bin) bikin bin yang drumnya sudah terbuka separuh terbaca setengah kosong,
	lalu menerima barang yang slotnya sudah habis -- persis keadaan normal sesudah
	pengambilan sebagian.
	"""
	if not pack or flt(qty) <= 0:
		return 0.0
	qpp, ppb = pack
	return math.ceil(flt(qty) / qpp) / ppb


def validate_packing_rules(doc, method=None):
	"""Penjaga tabel Aturan Kemasan, dipasang di Stock Settings.validate (hooks.py).

	Angka nol dan item kembar ditolak DI SINI, sekali, supaya mesin di bawah tidak
	perlu menebak baris mana yang benar -- dan supaya salah ketiknya ketahuan oleh
	yang mengetik, bukan oleh orang gudang yang dokumennya tiba-tiba tidak bisa
	disimpan.
	"""
	sudah = set()
	for row in doc.get("custom_bin_packing_rules") or []:
		if flt(row.qty_per_package) <= 0 or cint(row.packages_per_bin) <= 0:
			frappe.throw(
				_("Aturan kemasan baris {0}: Isi per Kemasan dan Maks per Bin harus lebih dari 0.").format(
					row.idx
				)
			)
		if row.item_code in sudah:
			frappe.throw(
				_("Aturan kemasan baris {0}: {1} sudah punya baris sendiri di atas.").format(
					row.idx, row.item_code
				)
			)
		sudah.add(row.item_code)
		row.qty_per_bin = flt(row.qty_per_package) * cint(row.packages_per_bin)


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
	"""{bin: {"qty","weight","volume","items","share"}} dari saldo Item Bin Qty sekarang.

	"items" = item yang sedang menghuni bin itu, dipakai aturan campur (mix_blocker).
	"share" = bagian bin yang sudah dimakan KEMASAN (1,0 = slotnya habis), dari
	tabel Aturan Kemasan di Stock Settings.

	Keduanya ikut di sini karena querynya memang sudah jalan DAN karena di sinilah
	qty per item masih di tangan -- satu baris Item Bin Qty = satu item di satu bin.
	Query kedua khusus untuk itu berarti dua sumber yang cepat atau lambat berbeda
	pendapat.
	"""
	usage = {
		b: {"qty": 0.0, "weight": 0.0, "volume": 0.0, "items": set(), "share": 0.0}
		for b in bin_names
	}
	if not bin_names:
		return usage
	aturan = packing_rules()
	for row in frappe.get_all(
		"Item Bin Qty",
		filters={"bin_location": ["in", list(bin_names)], "qty": ["!=", 0]},
		fields=["bin_location", "item_code", "qty"],
	):
		w, v = item_size(row.item_code)
		u = usage[row.bin_location]
		u["share"] += pack_share(row.qty, aturan.get(row.item_code))
		u["qty"] += flt(row.qty)
		u["weight"] += flt(row.qty) * w
		u["volume"] += flt(row.qty) * v
		if flt(row.qty) > 0:
			u["items"].add(row.item_code)
	return usage


def bin_free(caps, used):
	"""Sisa (berat, volume) dari kapasitas efektif bin (bin_caps_map). None = tanpa batas."""
	cap_w, cap_v = flt(caps[0]), flt(caps[1])
	free_w = None if cap_w <= 0 else cap_w - flt(used.get("weight"))
	free_v = None if cap_v <= 0 else cap_v - flt(used.get("volume"))
	return free_w, free_v


def fits(free_w, free_v, weight, volume, free_share=None, pack=None):
	"""Berapa unit lagi yang muat: dibatasi berat, volume, DAN jumlah kemasan.

	None = tak terbatas. Item tanpa ukuran (berat/volume 0) dan tanpa aturan kemasan
	dianggap tidak memakan kapasitas -- kalau tidak, satu master yang belum diisi
	ukurannya akan memblokir bin.

	Batas kemasan sengaja duduk DI SINI, bukan di pemanggilnya: suggest(),
	bin_ledger._fits_in(), dan lewat itu place() otomatis tunduk pada aturan yang
	sama. Menambalnya di suggest saja meninggalkan jalur pendaratan otomatis bebas
	melanggar.

	Dua parameter terakhir ada di BELAKANG dengan default aman karena pemanggilnya
	menulis fits(*bin_free(...), weight, volume): menambah nilai balik ke bin_free
	akan menggeser argumen posisional DIAM-DIAM, bukan melempar error.

	Sisa bin dibulatkan ke KEMASAN UTUH: sisa 0,483 bin untuk drum 4-per-bin berarti
	1 drum, bukan 1,9 drum. Yang muat di angka harus muat juga di raknya.
	"""
	limits = []
	if free_w is not None and weight > 0:
		limits.append(free_w / weight)
	if free_v is not None and volume > 0:
		limits.append(free_v / volume)
	if free_share is not None and pack:
		qpp, ppb = pack
		limits.append(math.floor(max(0.0, free_share) * ppb + 1e-9) * qpp)
	if not limits:
		return None
	return max(0.0, min(limits))


# ------------------------------------------------------------------ saldo
#
# Saldo bin PINDAH ke erpnext_custom/bin_ledger.py.
#
# Dulu di sini ada move()/reconcile()/reconcile_sle(): saldo disimpan langsung di
# Item Bin Qty, dan tiap ada stok keluar, kelebihannya dipangkas dari bin TERDEKAT
# tanpa jejak. Itu tidak bisa menjawab "barang lama keluar duluan" (tidak ada
# tanggal terima yang disimpan), tidak mengembalikan apa pun saat dokumen dibatalkan,
# dan selisihnya hilang diam-diam.
#
# Sekarang Item Bin Qty jadi CACHE saldo yang dihitung ulang dari Bin Ledger Entry,
# persis seperti hubungan Bin dengan Stock Ledger Entry. Semua fungsi di file ini
# yang membaca Item Bin Qty (bin_usage, suggest, layout, bin_map) jalan seperti biasa.


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


def bin_sort_key(bin_location):
	"""sort_key sebuah bin yang cuma diketahui NAMANYA. Bin hilang = paling belakang."""
	b = frappe.db.get_value(
		"Bin Location", bin_location, ["rack", "level", "rack_level", "rack_order"], as_dict=True
	)
	return sort_key(b) if b else (_FAR, _FAR, _FAR)


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


def _bin_allowed_map(bin_names):
	"""{bin: {item}} dari tabel Item Khusus di master Bin Location.

	Bin yang tabelnya kosong TIDAK muncul sebagai kunci, dan bedanya penting:
	"tidak diatur" (ikut aturan rak) bukan "tidak boleh apa-apa".
	"""
	out = defaultdict(set)
	if bin_names:
		for r in frappe.get_all(
			"Rack Allowed Item",
			filters={
				"parenttype": "Bin Location",
				"parentfield": "allowed_items",
				"parent": ["in", list(bin_names)],
			},
			fields=["parent", "item_code"],
		):
			out[r.parent].add(r.item_code)
	return out


def bin_allowed(bin_location, item_code, zone=False, allow=None, rack=None):
	"""Boleh atau tidak item ini masuk BIN ini.

	Daftar Item Khusus di master Bin Location menang atas daftar/zona raknya --
	aturan yang paling dekat dengan barangnya yang berlaku. Bin tanpa daftar
	jatuh ke aturan rak. `allow` dan `rack` cuma jalan pintas supaya pemanggil
	yang sudah punya datanya (candidate_bins) tidak query ulang per bin.
	"""
	allow = _bin_allowed_map([bin_location]) if allow is None else allow
	if bin_location in allow:
		return item_code in allow[bin_location]
	rack = rack or frappe.get_cached_value("Bin Location", bin_location, "rack")
	return item_allowed(rack, item_code, zone)


def heavy_max_level(item_code):
	"""Tingkat tertinggi yang boleh dipakai item ini. 0 = tidak dibatasi.

	Barang berat di tingkat atas itu bahaya angkat sekaligus rangka penyok, jadi
	batasnya KERAS, bukan sekadar urutan saran: di atas ambang berat per unit
	(Stock Settings > Warehouse) barang cuma boleh sampai tingkat ke-N. Tingkat
	yang tidak diketahui ikut dianggap tinggi -- arah salahnya sengaja ke bawah.
	"""
	setting = stock_settings()
	ambang = flt(setting.get("custom_heavy_item_weight"))
	if ambang <= 0:
		return 0
	weight, _volume = item_size(item_code)
	if weight < ambang:
		return 0
	return cint(setting.get("custom_heavy_max_level")) or 3


def mix_rule(item_code):
	"""(khusus sendiri, grup campur) satu item, dari master Item."""
	it = (
		frappe.get_cached_value(
			"Item", item_code, ["custom_bin_exclusive", "custom_mix_group"], as_dict=True
		)
		or {}
	)
	return bool(it.get("custom_bin_exclusive")), (it.get("custom_mix_group") or "").strip().upper()


def mix_ok(a, b):
	"""Boleh atau tidak dua item berbagi satu bin.

	Dua lapis: item bercentang "Bin Khusus" tidak mau ditemani apa pun (walau
	binnya masih lowong), dan sisanya cuma boleh sekamar dengan Grup Campur yang
	SAMA. Grup dibandingkan apa adanya, kosong pun dianggap grup -- itu yang bikin
	aturannya simetris: memberi grup pada satu barang otomatis memisahkannya dari
	semua yang tidak bergrup, tanpa perlu mendaftar lawannya satu per satu.
	"""
	if a == b:
		return True
	ex_a, grup_a = mix_rule(a)
	ex_b, grup_b = mix_rule(b)
	return not ex_a and not ex_b and grup_a == grup_b


def whole_number(item_code):
	"""Item bersatuan utuh: Pcs, Drum, Zak. 4,16 flexibag tidak muat di satu bin.

	Saklar "Qty Bin Tanpa Desimal" (Stock Settings > Warehouse, nyala dari sananya)
	memberlakukannya untuk SEMUA item -- isi bin memang dihitung orang, bukan
	dihitung kalkulator. Kalau dimatikan, jatuh ke satuan itemnya sendiri.
	"""
	if cint(stock_settings().get("custom_bin_whole_qty")):
		return True
	uom = frappe.get_cached_value("Item", item_code, "stock_uom")
	return bool(uom and frappe.get_cached_value("UOM", uom, "must_be_whole_number"))


def mix_blocker(item_code, items):
	"""Penghuni bin yang menolak ditemani item ini. None = boleh masuk."""
	for other in items or ():
		if not mix_ok(item_code, other):
			return other
	return None


def candidate_bins(gudang, item_code, caps=None, locked=None):
	"""Bin aktif di gudang yang boleh menerima item ini.

	Tiga saringan: bin yang sudah digabung ke bin lain tidak berdiri sendiri,
	raknya harus menerima item ini, dan slotnya harus cukup panjang untuk barangnya.

	`locked` = {bin: nomor replan} dari erpnext_custom/replan.py; bin yang sedang
	masuk replan yang belum disetujui tidak pernah disarankan, karena barangnya
	sedang dipindah orang. Pemanggil yang mengulang per item (suggest) menghitungnya
	SEKALI lalu mengoper ke sini -- bukan di-cache, supaya kuncinya tidak pernah
	basi di dalam request yang sama.
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
	if locked is None:
		from erpnext_custom import replan  # replan.py membaca modul ini; impor lokal

		locked = replan.locked_bins()
	bins = [b for b in bins if b.name not in locked]
	zone = _zone_for_item(item_code)
	allow = _bin_allowed_map([b.name for b in bins])
	bins = [b for b in bins if bin_allowed(b.name, item_code, zone, allow, b.rack)]
	panjang = item_length(item_code)
	if panjang:
		bins = [b for b in bins if not caps.get(b.name, (0, 0, 0))[2] or caps[b.name][2] >= panjang]
	batas = heavy_max_level(item_code)
	if batas:
		bins = [b for b in bins if (b.rack_level or _FAR) <= batas]
	return bins


@frappe.whitelist()
def suggest(gudang, rows, exclude=None):
	"""Bagi qty tiap baris ke bin-bin yang masih muat.

	Urutan pilih: bin yang SUDAH berisi item sama (konsolidasi) dulu, lalu yang
	paling dekat pick area dan paling gampang digapai (sort_key), baru bin paling
	kosong sebagai pemecah seri. Satu bin tidak cukup = sisanya lanjut ke bin
	berikutnya.

	Baris boleh membawa `from_bin`: barangnya sudah ADA di sebuah bin dan yang
	dicari tempat yang lebih baik (Replan). Kalau begitu, cuma bin yang jelas lebih
	dekat atau lebih gampang digapai daripada bin asal yang diterima -- memindahkan
	barang ke tempat yang sama susahnya itu kerja tanpa hasil.

	`exclude` = bin yang tidak boleh jadi tujuan apa pun alasannya (di Replan: semua
	bin asal, karena isinya sedang dibongkar).
	"""
	rows = json.loads(rows) if isinstance(rows, str) else rows
	exclude = json.loads(exclude) if isinstance(exclude, str) else exclude
	exclude = set(exclude or [])
	out = []
	# Usage dihitung SEKALI lalu dikurangi sendiri selama membagi, supaya dua
	# baris berbeda tidak sama-sama dijanjikan bin yang cuma muat satu.
	usage = bin_usage(frappe.get_all("Bin Location", filters={"gudang": gudang}, pluck="name"))
	caps = bin_caps_map(gudang)
	aturan = packing_rules()
	from erpnext_custom import replan  # impor lokal: replan.py membaca modul ini

	locked = replan.locked_bins()
	for row in rows:
		item_code = row.get("item_code")
		need = flt(row.get("qty"))
		if not item_code or need <= 0:
			out.append(None)
			continue
		bins = candidate_bins(gudang, item_code, caps, locked)
		if exclude:
			bins = [b for b in bins if b.name not in exclude]
		from_bin = row.get("from_bin")
		if from_bin:
			# Cuma dua unsur pertama sort_key yang dibandingkan (jarak rak, susah
			# digapai). Unsur ketiga cuma urutan bay -- geser satu bay di tingkat yang
			# sama bukan perbaikan, cuma memindahkan barang tanpa alasan.
			batas = bin_sort_key(from_bin)
			bins = [b for b in bins if b.name != from_bin and sort_key(b)[:2] < batas[:2]]
			if not bins:
				out.append({"skip": _("tidak ada bin yang lebih gampang digapai")})
				continue
		if not bins:
			out.append({"skip": _("tidak ada bin yang cocok: zona rak, daftar item, atau panjang slot")})
			continue
		weight, volume = item_size(item_code)
		bulat = whole_number(item_code)
		pack = aturan.get(item_code)
		occupied = {b.name for b in bins if item_code in usage.get(b.name, {}).get("items", ())}
		# Tempat terdekat staging dan tingkat terbawah DULU (sort_key); bin yang
		# sudah berisi item sama cuma pemecah seri. Konsolidasi sengaja turun:
		# jalan kaki lebih mahal daripada rapi, dan aturan campur di bawah sudah
		# menjaga isi bin tetap cocok.
		ordered = sorted(
			bins,
			key=lambda b: (
				*sort_key(b),
				0 if b.name in occupied else 1,
				usage.get(b.name, {}).get("qty", 0.0),
				b.name,
			),
		)
		allocations, sisa, ditolak = [], need, None
		for b in ordered:
			used = usage.setdefault(
				b.name,
				{"qty": 0.0, "weight": 0.0, "volume": 0.0, "items": set(), "share": 0.0},
			)
			lawan = mix_blocker(item_code, used["items"])
			if lawan:
				ditolak = lawan
				continue
			muat = fits(
				*bin_free(caps.get(b.name, (0.0, 0.0, 0.0)), used),
				weight,
				volume,
				free_share=1.0 - flt(used.get("share")),
				pack=pack,
			)
			take = sisa if muat is None else min(sisa, muat)
			# Bin penuh di tengah unit: dibulatkan ke BAWAH, sisanya lanjut ke bin
			# berikutnya. Sisa terakhir tidak dibulatkan -- itu qty aslinya.
			if bulat and take < sisa:
				take = float(int(take))
			if take <= 0:
				continue
			allocations.append(
				{"bin_location": b.name, "rack": b.rack, "qty": take, "weight": take * weight}
			)
			used["qty"] += take
			used["weight"] += take * weight
			used["volume"] += take * volume
			used["items"].add(item_code)
			# Kemasan yang baru ditaruh ikut memakan slot. Dihitung terpisah dari isi
			# lama, jadi kalau bin itu sudah berisi item yang sama hasilnya kelebihan
			# paling banyak satu kemasan -- arah salahnya sengaja ke "kurang muat".
			used["share"] += pack_share(take, pack)
			sisa -= take
			if sisa <= 0:
				break
		result = {"allocations": allocations}
		if sisa > 0:
			result["shortage"] = sisa
		if not allocations:
			result["skip"] = (
				_("tidak boleh dicampur dengan {0}").format(ditolak)
				if ditolak
				else _("semua bin sudah penuh")
			)
		out.append(result)
	return out


def staging_stock(gudang):
	"""{item: qty} yang masih menganggur di bin penampung (staging) gudang ini.

	Inilah "yang benar-benar belum ditaruh": stoknya sudah diakui di notanya dan
	buku besar bin sudah mendaratkannya di staging, tinggal dipindah ke rak.
	"""
	racks = frappe.get_all("Rack", filters={"gudang": gudang, "kind": "Staging"}, pluck="name")
	bins = (
		frappe.get_all("Bin Location", filters={"rack": ["in", racks]}, pluck="name")
		if racks
		else []
	)
	out = defaultdict(float)
	if bins:
		for row in frappe.get_all(
			"Item Bin Qty",
			filters={"bin_location": ["in", bins], "qty": [">", 0]},
			fields=["item_code", "qty"],
		):
			out[row.item_code] += flt(row.qty)
	return out


def _sudah_ditempatkan(invoices):
	"""{(nota, item): qty} yang sudah ditempatkan Goods Receive lain yang sudah submit.

	Dibaca per BARIS, bukan per dokumen: satu Goods Receive boleh memuat beberapa
	nota sekaligus, jadi nomor notanya ada di barisnya.
	"""
	out = defaultdict(float)
	for r in frappe.get_all(
		"Goods Receive Item",
		filters={"purchase_invoice": ["in", invoices], "docstatus": 1},
		fields=["purchase_invoice", "item_code", "qty"],
	):
		out[(r.purchase_invoice, r.item_code)] += flt(r.qty)
	return out


def _nota_belum_habis(invoices, gudang=None):
	"""Dari daftar nota, mana yang MASIH punya barang belum ditaruh.

	Ukurannya kertas notanya: qty nota dikurangi yang sudah ditempatkan Goods
	Receive lain. Isi bin penampung sengaja tidak ikut -- itu urusan pull_invoices
	waktu notanya benar-benar dipilih, dan gudang yang riwayat stagingnya kosong
	tidak boleh kehilangan notanya dari daftar.
	"""
	invoices = [i for i in invoices if i]
	if not invoices:
		return set()
	filters = {"parent": ["in", invoices], "parenttype": "Purchase Invoice", "docstatus": 1}
	if gudang:
		filters["warehouse"] = gudang
	diminta = defaultdict(float)
	for r in frappe.get_all(
		"Purchase Invoice Item", filters=filters, fields=["parent", "item_code", "stock_qty"]
	):
		diminta[(r.parent, r.item_code)] += flt(r.stock_qty)
	sudah = _sudah_ditempatkan(invoices)
	return {
		nota for (nota, item_code), qty in diminta.items() if qty - sudah[(nota, item_code)] > 0.0001
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def invoices_to_place(doctype, txt, searchfield, start, page_len, filters):
	"""Isi dropdown Purchase Invoice di Goods Receive: nota yang masih ada sisanya.

	Nota yang barangnya sudah naik rak semua tidak perlu ditawarkan lagi -- dulu
	masih muncul dan baru bilang "sudah ditempatkan semua" sesudah dipilih.

	ponytail: disaring di python sesudah mengambil sebatch kandidat terbaru, bukan
	di SQL. Itu berarti gulung-ke-bawah bisa meleset kalau satu gudang punya ribuan
	nota yang sudah selesai beruntun; pindahkan ke satu query EXISTS kalau daftarnya
	sudah sepanjang itu.
	"""
	start, page_len = cint(start), cint(page_len)
	cond = {"docstatus": 1, "update_stock": 1, "is_return": 0}
	if txt:
		cond["name"] = ["like", f"%{txt}%"]
	kandidat = frappe.get_all(
		"Purchase Invoice",
		filters=cond,
		fields=["name", "supplier_name"],
		order_by="posting_date desc, name desc",
		limit=start + page_len * 5,
	)
	belum = _nota_belum_habis([k.name for k in kandidat], (filters or {}).get("gudang"))
	rows = [(k.name, k.supplier_name) for k in kandidat if k.name in belum]
	return rows[start : start + page_len]


@frappe.whitelist()
def pull_invoices(invoices, gudang=None, listed=None):
	"""Baris barang beberapa Purchase Invoice sekaligus, siap ditaruh ke bin.

	Satu Goods Receive boleh memuat beberapa nota, jadi tiap baris membawa nomor
	notanya sendiri. Qty dipakai stock_qty (satuan stok, sama dengan satuan saldo
	bin), dikurangi yang sudah ditempatkan Goods Receive lain.

	Pemangkas terakhir: isi bin penampung. Yang menentukan boleh ditaruh berapa
	adalah barang yang masih menganggur di lantai, bukan angka notanya -- kalau
	tidak, Recommendation menjanjikan bin untuk barang yang sudah naik rak dan
	dokumennya baru ditolak saat disimpan. `listed` = {item: qty} yang sudah ada
	di tabel dokumen ini, supaya menambah nota kedua tidak menghitung ulang jatah
	yang sama. Item yang staging-nya kosong TIDAK dipangkas: gudang yang binnya
	baru dipasang belum punya riwayat, dan penolakan sungguhannya tetap ada saat
	simpan (Goods Receive._check_source).
	"""
	invoices = json.loads(invoices) if isinstance(invoices, str) else invoices
	listed = json.loads(listed) if isinstance(listed, str) else (listed or {})
	invoices = [i for i in invoices if i]
	if not invoices:
		frappe.throw(_("Pilih Purchase Invoice dulu."))

	rows = frappe.get_all(
		"Purchase Invoice Item",
		filters={"parent": ["in", invoices], "parenttype": "Purchase Invoice", "docstatus": 1},
		fields=["parent", "item_code", "item_name", "warehouse", "stock_qty", "stock_uom"],
		order_by="parent asc, idx asc",
	)
	if not rows:
		frappe.throw(_("{0} tidak punya baris barang.").format(", ".join(invoices)))
	if not gudang:
		semua = {r.warehouse for r in rows if r.warehouse}
		if len(semua) != 1:
			frappe.throw(_("Nota ini memakai lebih dari satu gudang, pilih gudangnya dulu."))
		gudang = semua.pop()

	diminta, info = defaultdict(float), {}
	for r in rows:
		if r.warehouse != gudang:
			continue
		diminta[(r.parent, r.item_code)] += flt(r.stock_qty)
		info[(r.parent, r.item_code)] = (r.item_name, r.stock_uom)

	sudah = _sudah_ditempatkan(invoices)
	tersedia = staging_stock(gudang)
	for item_code, qty in listed.items():
		if item_code in tersedia:
			tersedia[item_code] -= flt(qty)

	out = []
	for (nota, item_code), qty in diminta.items():
		# qty = angka notanya apa adanya; sisa = yang benar-benar masih bisa ditaruh
		# hari ini. Dua kolom yang berbeda: yang pertama untuk dicocokkan dengan
		# kertas notanya, yang kedua batas alokasi.
		sisa = qty - sudah[(nota, item_code)]
		jatah = flt(tersedia.get(item_code))
		if item_code in tersedia:
			sisa = min(sisa, jatah)
			tersedia[item_code] = jatah - max(sisa, 0.0)
		if sisa <= 0:
			continue
		nama, uom = info[(nota, item_code)]
		out.append(
			{
				"purchase_invoice": nota,
				"item_code": item_code,
				"item_name": nama,
				"qty": qty,
				"max_qty": sisa,
				# Allocated mulai dari 0: berapa yang naik ke rak hari ini keputusan
				# orang gudang, bukan angka nota.
				"allocated": 0.0,
				"outstanding": sisa,
				"stock_uom": uom,
			}
		)
	supplier = frappe.db.get_value("Purchase Invoice", invoices[-1], "supplier_name")
	return {"gudang": gudang, "supplier": supplier, "rows": out}


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
	"""Isi Urutan Jarak tiap rak dari kotak Staging terdekat di denah.

	Dipakai supaya "prioritaskan tempat terdekat" tidak perlu diketik satu-satu:
	gambar pintunya, tekan tombolnya. Yang disimpan PERINGKAT 1..N, bukan piksel,
	supaya satu skala dengan angka yang diisi tangan dan gampang ditimpa lagi.
	Posisi diambil dari layout(), jadi rak yang belum pernah ditata pun terhitung.
	"""
	frappe.has_permission("Rack", "write", throw=True)
	boxes = layout(gudang)
	# Staging duluan: di situlah barang mendarat dan dari situ orang berjalan
	# membawanya. Pintu cuma cadangan untuk gudang yang belum menggambar staging.
	acuan = [_center(b) for b in boxes if b["kind"] == "Staging"] or [
		_center(b) for b in boxes if b["kind"] == "Pintu"
	]
	if not acuan:
		frappe.throw(_("Gudang ini belum punya kotak Staging atau Pintu di denah."))
	jarak = []
	for b in boxes:
		if b["kind"] != "Rak":
			continue
		x, y = _center(b)
		jarak.append((min(((x - px) ** 2 + (y - py) ** 2) ** 0.5 for px, py in acuan), b["name"]))
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

	Kotak rak di denah digambar seperti rak TAMPAK DEPAN: kolom = bay, baris =
	tingkat (E di atas, A di bawah), jadi satu petak = satu bin dan bisa diklik.
	Isi per bin ikut di sini (qty, berat, kapasitas) supaya warnanya bisa digambar
	tanpa panggilan tambahan; rincian ITEM-nya tidak, itu lewat rack_level_contents
	saat petaknya benar-benar diklik.

	Bay diambil dari angka di kode bin (AA0101A -> 0101). Kode yang tidak berpola
	(BULKY DEPAN, LORONG AA-AB) tidak punya bay, jadi tiap bin berdiri sendiri.
	Dipanggil terpisah dari layout(): payload-nya berat dan cuma dipakai saat
	tombolnya dinyalakan.
	"""
	bins = frappe.get_all(
		"Bin Location",
		filters={"gudang": gudang, "disabled": 0},
		fields=["name", "rack", "bin_code", "level", "merged_into", "rack_order", "default_uom"],
		order_by="rack_order, bin_code",
	)
	usage = bin_usage([b.name for b in bins])
	caps = bin_caps_map(gudang)
	from erpnext_custom import replan  # impor lokal: replan.py membaca modul ini

	terkunci = replan.locked_bins()

	per_rak = {}
	for b in bins:
		m = _BIN_NAME.match((b.bin_code or "").strip())
		bay = m.group(2) if m else (b.bin_code or b.name)
		petak = per_rak.setdefault(b.rack, {}).setdefault(
			bay, {"bay": bay, "bins": [], "qty": 0.0, "used": 0.0, "capacity": 0.0, "order": b.rack_order or _FAR}
		)
		u = usage.get(b.name, {})
		petak["bins"].append(
			{
				"bin": b.name,
				"bin_code": b.bin_code,
				"level": b.level or "-",
				"qty": flt(u.get("qty")),
				"used": flt(u.get("weight")),
				"capacity": flt(caps.get(b.name, (0.0, 0.0, 0.0))[0]),
				# kemasan yang dipesan untuk bin ini (Drum, Box, Zak, ...) -- dipakai
				# halaman Layout untuk mewarnai petak menurut peruntukan, seperti Excel gudang
				"uom": b.default_uom,
				# nomor Bin Replan yang sedang mengunci bin ini (belum disetujui), supaya
				# orang gudang lihat di denah kalau bin itu sedang dibongkar
				"locked": terkunci.get(b.name),
			}
		)
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
		# berat baris ini dipakai halaman Layout untuk rasio isi bin per item; satuan
		# bisa campur (KG, PCS, Drum) jadi jumlah unit saja tidak bisa dibandingkan
		row.weight = flt(row.qty) * item_size(row.item_code)[0]
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

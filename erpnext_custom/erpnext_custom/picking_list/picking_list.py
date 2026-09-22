from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime

from erpnext_custom import bin_layout, bin_ledger, replan

_EPS = 0.0001
# Umur tak diketahui = paling BELAKANG, sama seperti di bin_ledger: lapisan tanpa
# tanggal tidak boleh menyamar jadi barang tertua dan menyerobot antrian.
_FAR = get_datetime("2999-01-01 00:00:00")


def validate_stock_availability(doc, method=None):
	"""Prevent a Pick List from allocating more than the current physical stock."""
	required = defaultdict(float)

	for row in doc.get("locations"):
		if not row.item_code or not row.warehouse:
			continue

		# ERPNext fills picked_qty from stock_qty only in before_submit. Validate
		# stock_qty too so manually edited drafts cannot bypass the stock check.
		qty = flt(row.picked_qty) if flt(row.picked_qty) > 0 else flt(row.stock_qty)
		if qty > 0:
			required[(row.item_code, row.warehouse, row.batch_no or "")] += qty

	for (item_code, warehouse, batch_no), qty in required.items():
		other_filters = {
			"parent": ["!=", doc.name],
			"parenttype": "Pick List",
			"docstatus": ["<", 2],
			"item_code": item_code,
			"warehouse": warehouse,
		}
		if batch_no:
			other_filters["batch_no"] = batch_no
		else:
			other_filters["batch_no"] = ["is", "not set"]

		allocated_elsewhere = sum(
			flt(row.picked_qty) if flt(row.picked_qty) > 0 else flt(row.stock_qty)
			for row in frappe.get_all(
				"Pick List Item",
				filters=other_filters,
				fields=["stock_qty", "picked_qty"],
			)
		)

		if batch_no:
			from erpnext.stock.doctype.batch.batch import get_batch_qty

			available = flt(get_batch_qty(batch_no, warehouse, item_code))
			scope = _("batch {0} in warehouse {1}").format(
				frappe.bold(batch_no), frappe.bold(warehouse)
			)
		else:
			available = flt(
				frappe.db.get_value(
					"Bin",
					{"item_code": item_code, "warehouse": warehouse},
					"actual_qty",
				)
			)
			scope = _("warehouse {0}").format(frappe.bold(warehouse))

		total_allocated = qty + allocated_elsewhere
		if total_allocated > available:
			frappe.throw(
				_(
					"Total Pick Qty {0} for item {1} exceeds available stock {2} in {3}. "
					"Other active Pick Lists already allocate {4}."
				).format(
					total_allocated,
					frappe.bold(item_code),
					available,
					scope,
					allocated_elsewhere,
				),
				title=_("Insufficient Stock"),
			)


# ------------------------------------------------------------------ bin asal


def validate_pick_bins(doc, method=None):
	"""Bin asal tiap baris harus segudang dengan barisnya DAN benar-benar berisi barangnya.

	Dicek di validate, bukan cuma saat submit, supaya draft yang salah ketahuan
	sejak disimpan. bin_ledger.move() mengecek ulang waktu submit -- sengaja dobel,
	karena isi bin bisa berubah di antara simpan dan submit.

	Tidak dipasang di on_update_after_submit: sesudah submit barangnya memang sudah
	pindah ke staging keluar, jadi bin asalnya wajar kosong.
	"""
	if doc.purpose != "Delivery":
		return

	butuh = defaultdict(float)
	for row in doc.get("locations"):
		asal = row.get("custom_bin_location")
		if not asal:
			continue
		gudang = frappe.get_cached_value("Bin Location", asal, "gudang")
		if gudang != row.warehouse:
			frappe.throw(
				_("Baris {0}: bin {1} ada di gudang {2}, bukan di {3}.").format(
					row.idx, asal, gudang, row.warehouse
				)
			)
		qty = flt(row.picked_qty) or flt(row.stock_qty)
		if qty > 0:
			butuh[(row.item_code, row.warehouse, asal)] += qty

	dipesan = _allocated_elsewhere(doc.name)
	for (item_code, gudang, asal), qty in butuh.items():
		ada = sum(flt(l.qty_left) for l in bin_ledger.fifo_layers(item_code, gudang, asal))
		lain = dipesan.get((item_code, asal), 0.0)
		if qty + lain > ada + _EPS:
			frappe.throw(
				_(
					"Bin {0} cuma berisi {1} {2}, tidak cukup untuk {3}. "
					"Pick List lain yang masih draft sudah memesan {4}."
				).format(asal, ada, item_code, qty, lain),
				title=_("Isi Bin Tidak Cukup"),
			)


def _allocated_elsewhere(exclude=None):
	"""{(item, bin): qty} yang sudah dipesan Pick List lain yang masih DRAFT.

	Hanya draft. Pick List yang sudah submit memindahkan barangnya ke staging
	keluar saat itu juga, jadi lapisannya sudah tidak ada lagi di rak -- dihitung
	lagi di sini berarti dipotong dua kali.
	"""
	out = defaultdict(float)
	for r in frappe.get_all(
		"Pick List Item",
		filters={
			"docstatus": 0,
			"custom_bin_location": ["is", "set"],
			"parent": ["!=", exclude or ""],
		},
		fields=["item_code", "custom_bin_location", "stock_qty", "picked_qty"],
	):
		out[(r.item_code, r.custom_bin_location)] += flt(r.picked_qty) or flt(r.stock_qty)
	return out


# ------------------------------------------------------------------ rak -> staging keluar


def move_to_pick_staging(doc, method=None):
	"""Turunkan barang yang dipetik dari raknya ke bin staging keluar.

	Cermin Goods Receive, arah sebaliknya: perpindahan bin murni, nol stok dan nol
	jurnal. Total per gudang tidak berubah, jadi invarian bin_total ==
	Bin.actual_qty tetap utuh di setiap titik.

	Barisnya boleh menunjuk rak berbeda-beda; semuanya mendarat di SATU bin staging
	keluar. Itu yang membuat Delivery Note nanti cukup punya satu bin asal walau
	pengambilannya tersebar di lima rak.
	"""
	_shift(doc, ke_staging=True)


def move_back_from_pick_staging(doc, method=None):
	"""Kembalikan barang dari staging keluar ke rak asalnya, dengan umur aslinya.

	Kalau Delivery Note-nya sudah submit, staging keluar sudah kosong dan
	bin_ledger.move() menolak -- memang begitu urutannya: batalkan DN dulu.
	"""
	_shift(doc, ke_staging=False)


def _shift(doc, ke_staging):
	if doc.purpose != "Delivery":
		return
	for row in doc.get("locations"):
		asal = row.get("custom_bin_location")
		qty = flt(row.picked_qty) or flt(row.stock_qty)
		if not asal or qty <= 0:
			continue
		keluar = bin_ledger.staging_bin(row.warehouse, bin_ledger.KELUAR)
		dari, ke = (asal, keluar) if ke_staging else (keluar, asal)
		bin_ledger.move(row.item_code, dari, ke, qty, doc)


# ------------------------------------------------------------------ pemetik rak


def _pick_order(layers, toleransi_hari):
	"""Urutan mengambil lapisan: tertua duluan, tapi tidak membabi buta.

	Di sinilah FIFO dan monkey-pick berdamai. FIFO murni menyuruh orang memanjat ke
	tingkat teratas rak terjauh cuma karena barangnya lebih tua sehari. Dengan
	toleransi N hari, lapisan yang umurnya berdekatan dianggap SEIMBANG, dan yang
	menang di antara mereka adalah yang paling dekat dan paling gampang digapai
	(bin_layout.sort_key: jarak rak, susah digapai, urutan bay).

	Toleransi 0 = FIFO keras, kemudahan cuma jadi pemecah seri antar lapisan
	seumur. Itu default-nya, karena barang berumur tidak boleh ditawar sampai
	gudangnya sendiri menyatakan berapa hari yang boleh dianggap sama tua.
	"""
	if not layers:
		return []
	pos = bin_layout._positions({l.bin_location for l in layers})

	def umur(l):
		return get_datetime(l.received_on) if l.received_on else _FAR

	if not toleransi_hari:
		return sorted(layers, key=lambda l: (umur(l), pos[l.bin_location], l.creation))

	sisa = sorted(layers, key=lambda l: (umur(l), l.creation))
	urut = []
	while sisa:
		batas = umur(sisa[0]) + timedelta(days=toleransi_hari)
		grup = [l for l in sisa if umur(l) <= batas]
		sisa = [l for l in sisa if umur(l) > batas]
		urut += sorted(grup, key=lambda l: (pos[l.bin_location], umur(l), l.creation))
	return urut


@frappe.whitelist()
def suggest_bins(rows, exclude=None):
	"""Bagi tiap baris pick ke bin yang BENAR-BENAR memegang barangnya.

	Bedanya dengan bin_layout.suggest (put-away): itu memilih bin KOSONG yang muat,
	ini memilih bin ISI yang paling tua. Skor jarak dan kemudahannya sama persis.

	Dua jenis bin dilewati. Staging keluar, karena isinya sudah dipetik untuk
	pengiriman lain dan menawarkannya lagi berarti menjanjikan barang yang sama ke
	dua orang. Dan bin yang sedang dikunci Bin Replan, karena barangnya sedang
	dipindah dan raknya akan salah begitu petugas sampai di sana.

	rows: [{item_code, warehouse, qty}]
	-> [{allocations: [{bin_location, qty}], shortage}] sejajar indeksnya.
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else (rows or [])
	locked = replan.locked_bins()
	toleransi = cint(
		frappe.db.get_single_value("Stock Settings", "custom_pick_age_tolerance_days")
	)
	dipesan = _allocated_elsewhere(exclude)
	sisa_layer = {}  # lapisan -> qty yang masih bisa dibagikan di panggilan ini
	sisa_bin = {}  # (item, bin) -> idem, sesudah dipotong pesanan Pick List draft lain
	out = []

	for row in rows:
		item_code, gudang = row.get("item_code"), row.get("warehouse")
		sisa = flt(row.get("qty"))
		bagi = defaultdict(float)

		# ponytail: baris ber-batch dilewati, bukan ditebak. Bin Ledger Entry tidak
		# punya dimensi batch sama sekali (bin dan batch dua sumbu terpisah), jadi
		# bin tertua belum tentu memegang batch yang diminta. Menyarankannya berarti
		# menyuruh petugas ke rak yang salah. Tambahkan kolom batch di buku besar bin
		# kalau gudang ini memang menjalankan batch per rak.
		if row.get("batch_no"):
			out.append(
				{
					"allocations": [],
					"shortage": 0,
					"skip": _("baris ber-batch: buku besar bin tidak menyimpan batch"),
				}
			)
			continue

		if item_code and gudang and sisa > 0 and bin_ledger.is_tracked(gudang):
			keluar = bin_ledger.staging_bin(gudang, bin_ledger.KELUAR)
			layers = [
				l
				for l in bin_ledger.fifo_layers(item_code, gudang)
				if l.bin_location != keluar and l.bin_location not in locked
			]
			per_bin = defaultdict(float)
			for l in layers:
				sisa_layer.setdefault(l.name, flt(l.qty_left))
				per_bin[l.bin_location] += flt(l.qty_left)
			for b, total in per_bin.items():
				sisa_bin.setdefault((item_code, b), total - dipesan.get((item_code, b), 0.0))

			for l in _pick_order(layers, toleransi):
				if sisa <= _EPS:
					break
				ada = min(sisa_layer[l.name], sisa_bin[(item_code, l.bin_location)])
				if ada <= _EPS:
					continue
				ambil = min(sisa, ada)
				sisa_layer[l.name] -= ambil
				sisa_bin[(item_code, l.bin_location)] -= ambil
				bagi[l.bin_location] += ambil
				sisa -= ambil

		out.append(
			{
				"allocations": [{"bin_location": b, "qty": q} for b, q in bagi.items()],
				"shortage": sisa if sisa > _EPS else 0,
			}
		)
	return out

"""Buku besar bin: mencatat barang masuk/keluar TIAP BIN, dan mengeluarkannya FIFO.

Kenapa ada lapisan ini
----------------------
ERPNext tahu ada berapa banyak sebuah item di sebuah GUDANG (tabBin), tapi tidak
tahu barang itu ada di rak mana, dan sama sekali tidak tahu unit mana yang lebih
tua. FIFO bawaan ERPNext cuma FIFO NILAI (antrian harga pokok di stock_ledger.py),
bukan FIFO BARANG -- dua float per lapisan, tanpa jejak balik ke penerimaannya.

Jadi umur barang disimpan di sini, di `received_on` tiap lapisan.

Hubungan antar tabel -- sama persis dengan pola ERPNext sendiri:

    Stock Ledger Entry  ->  Bin              (gerakan -> saldo, milik ERPNext)
    Bin Ledger Entry    ->  Item Bin Qty     (gerakan -> saldo, milik kita)

Yang bikin ini tidak bisa melenceng
-----------------------------------
`doc_hook` tidak pernah menebak berapa yang bergerak. Dia MENGUKUR selisih antara
`Bin.actual_qty` (kebenaran) dan `bin_total()` (catatan kita), lalu menutup
selisih itu. Jadi pasca-kondisinya SAMA DENGAN invariannya: sesudah apply(),
bin_total == Bin.actual_qty menurut konstruksi. Dokumen yang lupa dikaitkan,
baris yang dihapus orang, atau data lama yang telanjur miring -- semuanya lurus
lagi sendiri begitu item+gudang itu bergerak berikutnya.

Satu-satunya penulis tabel Bin Ledger Entry adalah file ini.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, nowdate, now_datetime

from erpnext_custom import bin_layout

# Umur tak diketahui = taruh paling BELAKANG. Lapisan tanpa tanggal tidak boleh
# menyamar jadi barang paling tua dan menyerobot antrian FIFO.
_FAR = get_datetime("2999-01-01 00:00:00")

_EPS = 0.0001

# Dua arah staging. Nilainya sama dengan opsi Select `kind` di master Rack.
MASUK = "Staging"
KELUAR = "Staging Keluar"
_KODE_STAGING = {MASUK: "STAGING", KELUAR: "PICKOUT"}


# ------------------------------------------------------------------ dasar


def _posting_dt(voucher):
	"""Umur lapisan = tanggal POSTING dokumen, bukan saat barisnya dibuat.

	Penerimaan yang dimundurkan tanggalnya tetap duduk di urutan yang benar.
	Ini justru yang salah di FIFO batch bawaan, yang memakai Batch.creation.
	"""
	if voucher is not None:
		d = voucher.get("posting_date")
		if d:
			jam = voucher.get("posting_time") or "00:00:00"
			return get_datetime("{0} {1}".format(d, jam))
	return now_datetime()


def is_tracked(gudang):
	"""Gudang ini dipetakan per bin atau tidak.

	Site ini punya 81 gudang non-group (transit, WIP, rejected, supplier, dst).
	Cuma yang benar-benar punya bin yang ikut buku besar ini -- sisanya tidak
	boleh ketularan rak STAGING otomatis yang lalu mengotori denah gudang.
	"""
	if not gudang:
		return False
	return bool(frappe.db.exists("Bin Location", {"gudang": gudang, "disabled": 0}))


def is_ledgered_item(item_code):
	"""Item ber-batch/serial TIDAK masuk buku besar bin.

	ERPNext sudah punya FIFO/FEFO sendiri untuk mereka lewat batch. Dua mesin FIFO
	atas barang yang sama cuma menghasilkan dua jawaban yang berbeda.
	"""
	if not item_code:
		return False
	it = frappe.get_cached_value("Item", item_code, ["has_batch_no", "has_serial_no"], as_dict=True)
	if not it:
		return False
	return not (it.has_batch_no or it.has_serial_no)


def staging_bin(gudang, kind=MASUK):
	"""Bin penampung gudang ini. Dibuat kalau belum ada -- TIDAK PERNAH melempar error.

	Penerimaan tidak boleh gagal cuma karena raknya penuh atau masternya belum
	lengkap. Barang yang tidak kebagian tempat mendarat di sini dan muncul di
	daftar kerja put-away, bukan menggantung tanpa tercatat.

	Dua arah, dua penampung. MASUK menampung barang yang belum naik rak (diisi
	`place`, dikosongkan Goods Receive). KELUAR menampung barang yang sudah
	diturunkan Pick List dan menunggu Delivery Note. Dipisah karena isi MASUK
	adalah daftar kerja put-away, dan barang yang sudah dipetik untuk pesanan
	orang lain tidak boleh muncul di situ.

	Rak yang SUDAH ada dipakai ulang -- kalau tidak, rak kedua akan muncul di
	sebelah rak yang sudah dibuat operator dan denah gudang jadi ganda.
	"""
	kode = _KODE_STAGING[kind]
	rack = frappe.db.get_value("Rack", {"gudang": gudang, "kind": kind, "disabled": 0})
	if not rack:
		rack = (
			frappe.get_doc(
				{
					"doctype": "Rack",
					"gudang": gudang,
					"rack_code": kode,
					"kind": kind,
					"description": _("Penampung sementara, dibuat otomatis oleh buku besar bin."),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	loc = frappe.db.get_value("Bin Location", {"rack": rack, "disabled": 0})
	if not loc:
		loc = (
			frappe.get_doc(
				{"doctype": "Bin Location", "rack": rack, "gudang": gudang, "bin_code": kode}
			)
			.insert(ignore_permissions=True)
			.name
		)
	return loc


def bin_total(item_code, gudang):
	"""Total item ini yang tercatat di bin-bin gudang ini.

	SUM(qty) atas SEMUA baris, bukan SUM(qty_left) -- supaya baris kurang-lapisan
	(is_short, qty negatif tanpa lapisan) ikut terhitung. Kalau tidak, selisihnya
	jadi tak terlihat dan doc_hook akan mengulang koreksi yang sama selamanya.
	"""
	rows = frappe.get_all(
		"Bin Ledger Entry", filters={"item_code": item_code, "gudang": gudang}, pluck="qty"
	)
	return sum(flt(q) for q in rows)


def bin_qty(item_code, bin_location):
	"""Isi bin ini menurut buku besar. SUM(qty) atas semua baris, alasan sama dengan
	`bin_total`: baris kurang-lapisan (is_short) harus ikut terhitung."""
	return sum(
		flt(q)
		for q in frappe.get_all(
			"Bin Ledger Entry",
			filters={"item_code": item_code, "bin_location": bin_location},
			pluck="qty",
		)
	)


def fifo_layers(item_code, gudang, bin_location=None):
	"""Lapisan yang masih bersisa, PALING TUA DULUAN.

	`creation` bukan hiasan: penerimaan mundur tanggal dan impor massal bisa
	berbagi detik yang sama, dan urutannya harus tetap pasti.
	"""
	filters = {"item_code": item_code, "gudang": gudang, "qty_left": [">", 0]}
	if bin_location:
		filters["bin_location"] = bin_location
	return frappe.get_all(
		"Bin Ledger Entry",
		filters=filters,
		fields=["name", "bin_location", "qty_left", "received_on", "voucher_no", "creation"],
		order_by="received_on asc, creation asc",
	)


def _pick_sort(layers, voucher_no=None):
	"""Urutan makan lapisan: milik dokumen ini dulu (saat batal), lalu yang tertua."""

	def key(l):
		mine = 0 if voucher_no and l.voucher_no == voucher_no else 1
		umur = get_datetime(l.received_on) if l.received_on else _FAR
		return (mine, umur, l.creation)

	return sorted(layers, key=key)


# ------------------------------------------------------------------ tulis


def _write(
	item_code, bin_location, qty, voucher, received_on, qty_left=0.0, source_ble=None, is_short=0
):
	loc = frappe.get_cached_value("Bin Location", bin_location, ["gudang", "rack"], as_dict=True)
	doc = frappe.get_doc(
		{
			"doctype": "Bin Ledger Entry",
			"item_code": item_code,
			"bin_location": bin_location,
			"gudang": loc.gudang,
			"qty": flt(qty),
			"qty_left": flt(qty_left),
			"stock_uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
			"received_on": received_on,
			"posting_date": (voucher.get("posting_date") if voucher is not None else None) or nowdate(),
			"voucher_type": voucher.doctype if voucher is not None else None,
			"voucher_no": voucher.name if voucher is not None else None,
			"source_ble": source_ble,
			"is_short": is_short,
		}
	)
	doc.insert(ignore_permissions=True)
	_refresh_balance(item_code, bin_location)
	return doc.name


def _refresh_balance(item_code, bin_location):
	"""Item Bin Qty = cache saldo, dihitung ulang dari buku besar. Bukan sumber kebenaran.

	Skemanya tidak berubah sedikit pun, cuma artinya. Semua yang membacanya --
	bin_usage, suggest, halaman Warehouse Layout, report Stock per Rak -- jalan
	terus tanpa satu pun edit.
	"""
	total = bin_qty(item_code, bin_location)
	name = frappe.db.get_value(
		"Item Bin Qty", {"item_code": item_code, "bin_location": bin_location}
	)
	if abs(total) < _EPS:
		if name:
			frappe.delete_doc("Item Bin Qty", name, ignore_permissions=True, force=True)
		return
	if name:
		frappe.db.set_value("Item Bin Qty", name, "qty", total, update_modified=False)
		return
	loc = frappe.get_cached_value("Bin Location", bin_location, ["gudang", "rack"], as_dict=True)
	frappe.get_doc(
		{
			"doctype": "Item Bin Qty",
			"item_code": item_code,
			"bin_location": bin_location,
			"gudang": loc.gudang,
			"rack": loc.rack,
			"qty": total,
			"stock_uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
		}
	).insert(ignore_permissions=True)


# ------------------------------------------------------------------ masuk / keluar


def _hint_list(hint_bin):
	"""Samakan bentuk petunjuk bin: None, satu bin, atau [(bin, qty), ...].

	Batas qty per bin bukan hiasan. Satu dokumen boleh mengambil item yang sama
	dari beberapa rak sekaligus, dan tanpa batas itu bin pertama akan menelan
	seluruh qty dokumen -- rak kedua dan ketiga tidak pernah tersentuh, padahal
	barangnya nyata diambil dari sana.
	"""
	if not hint_bin:
		return []
	if isinstance(hint_bin, str):
		return [(hint_bin, 0.0)]
	return [(h, 0.0) if isinstance(h, str) else (h[0], flt(h[1])) for h in hint_bin]


def place(item_code, gudang, qty, voucher, hint_bin=None, received_on=None):
	"""Taruh qty ke bin. Urutan: kembalikan ke asal (kalau batal) -> hint -> staging.

	Barang yang baru masuk TIDAK dibagikan sendiri ke rak. Yang menaikkannya ke
	rak adalah Goods Receive (tombol Recommendation), karena penempatan itu
	keputusan orang gudang yang sedang memegang barangnya: dia yang tahu kalau
	paletnya penyok, kalau binnya kehalang, kalau barangnya mau langsung keluar
	lagi. Membagi otomatis di sini bikin peta bin percaya diri tentang barang yang
	fisiknya masih ngumpul di lantai.
	"""
	sisa = flt(qty)
	if sisa <= 0:
		return
	umur = received_on or _posting_dt(voucher)

	# Batal dokumen keluar: kembalikan ke bin yang dulu diambil, dengan umur aslinya.
	# Tanpa ini, barang yang batal keluar akan mendarat di bin terdekat sebagai
	# barang baru -- dan FIFO-nya bohong mulai saat itu.
	if voucher is not None and voucher.get("docstatus") == 2:
		for row in _undo_rows(voucher, item_code, gudang):
			take = min(sisa, abs(flt(row.qty)))
			if take <= 0:
				continue
			_write(item_code, row.bin_location, take, voucher, row.received_on, qty_left=take)
			sisa -= take
			if sisa <= _EPS:
				return

	for bin_location, batas in _hint_list(hint_bin):
		if sisa <= _EPS:
			break
		muat = _fits_in(bin_location, item_code, min(sisa, batas) if batas else sisa)
		if muat > 0:
			_write(item_code, bin_location, muat, voucher, umur, qty_left=muat)
			sisa -= muat

	if sisa > _EPS:
		_write(item_code, staging_bin(gudang), sisa, voucher, umur, qty_left=sisa)


def consume(item_code, gudang, qty, voucher, hint_bin=None):
	"""Ambil qty dari bin, PALING TUA DULUAN.

	Inilah jawaban 'urutan keluarnya gimana, barang lama barang baru'.
	"""
	sisa = flt(qty)
	if sisa <= 0:
		return
	voucher_no = (
		voucher.name if voucher is not None and voucher.get("docstatus") == 2 else None
	)

	for bin_location, batas in _hint_list(hint_bin):
		if sisa <= _EPS:
			break
		minta = min(sisa, batas) if batas else sisa
		sisa -= minta - _eat(item_code, gudang, minta, voucher, bin_location, voucher_no)
	if sisa > _EPS:
		sisa = _eat(item_code, gudang, sisa, voucher, None, voucher_no)

	if sisa > _EPS:
		# Lapisan habis tapi stok ERPNext bilang masih ada yang keluar. Dibukukan ke
		# staging sebagai minus supaya aritmetikanya tetap utuh dan selisihnya
		# KELIHATAN di audit() -- bukan hilang diam-diam seperti reconcile() dulu.
		_write(item_code, staging_bin(gudang), -sisa, voucher, _posting_dt(voucher), is_short=1)


def _eat(item_code, gudang, sisa, voucher, bin_location, voucher_no):
	for layer in _pick_sort(fifo_layers(item_code, gudang, bin_location), voucher_no):
		take = min(sisa, flt(layer.qty_left))
		if take <= 0:
			continue
		frappe.db.set_value(
			"Bin Ledger Entry",
			layer.name,
			"qty_left",
			flt(layer.qty_left) - take,
			update_modified=False,
		)
		_write(item_code, layer.bin_location, -take, voucher, layer.received_on, source_ble=layer.name)
		sisa -= take
		if sisa <= _EPS:
			break
	return sisa


def apply(item_code, gudang, delta, voucher, hint_bin=None):
	if delta > _EPS:
		place(item_code, gudang, delta, voucher, hint_bin=hint_bin)
	elif delta < -_EPS:
		consume(item_code, gudang, -delta, voucher, hint_bin=hint_bin)


def move(item_code, from_bin, to_bin, qty, voucher):
	"""Pindah antar bin DI GUDANG YANG SAMA, umur lapisan ikut pindah.

	Ini invarian paling rapuh di seluruh rancangan: kalau put-away dari staging ke
	rak mereset umur, FIFO jadi bohong untuk hampir semua barang -- karena staging
	memang tempat mendarat defaultnya.
	"""
	gudang = frappe.get_cached_value("Bin Location", from_bin, "gudang")
	sisa = flt(qty)
	for layer in _pick_sort(fifo_layers(item_code, gudang, from_bin)):
		take = min(sisa, flt(layer.qty_left))
		if take <= 0:
			continue
		frappe.db.set_value(
			"Bin Ledger Entry",
			layer.name,
			"qty_left",
			flt(layer.qty_left) - take,
			update_modified=False,
		)
		_write(item_code, from_bin, -take, voucher, layer.received_on, source_ble=layer.name)
		_write(item_code, to_bin, take, voucher, layer.received_on, qty_left=take)
		sisa -= take
		if sisa <= _EPS:
			return
	if sisa > _EPS:
		frappe.throw(
			_("Bin {0} cuma berisi {1} {2}, tidak bisa dipindahkan {3}.").format(
				from_bin, flt(qty) - sisa, item_code, flt(qty)
			)
		)


def transfer(item_code, from_gudang, to_gudang, qty, voucher, hint_bin=None):
	"""Pindah ANTAR GUDANG dengan umur yang dipertahankan.

	Tanpa ini, transfer terbaca sebagai keluar-di-sini + masuk-baru-di-sana, dan
	umur barang tereset diam-diam tiap kali pindah gudang.
	"""
	sisa = flt(qty)
	if is_tracked(from_gudang):
		for layer in _pick_sort(fifo_layers(item_code, from_gudang)):
			take = min(sisa, flt(layer.qty_left))
			if take <= 0:
				continue
			frappe.db.set_value(
				"Bin Ledger Entry",
				layer.name,
				"qty_left",
				flt(layer.qty_left) - take,
				update_modified=False,
			)
			_write(
				item_code, layer.bin_location, -take, voucher, layer.received_on, source_ble=layer.name
			)
			if is_tracked(to_gudang):
				place(
					item_code, to_gudang, take, voucher, hint_bin=hint_bin, received_on=layer.received_on
				)
			sisa -= take
			if sisa <= _EPS:
				return
	if sisa > _EPS and is_tracked(to_gudang):
		place(item_code, to_gudang, sisa, voucher, hint_bin=hint_bin)


# ------------------------------------------------------------------ koreksi


def adjust(item_code, bin_location, qty, voucher, received_on=None):
	"""Tulis apa adanya ke bin ini. Tanpa kapasitas, tanpa tetesan ke staging.

	Jalur KOREKSI (Bin Adjustment): yang dicatat di sini adalah KENYATAAN FISIK di
	bin itu -- barangnya sudah di situ, atau sudah tidak ada. Jadi aturan penempatan
	tidak boleh menolaknya dan sisanya tidak boleh menetes ke staging seperti
	`place()`; kalau boleh, sistem jadi tidak sanggup menuliskan apa yang benar-benar
	ada di rak, dan itu justru satu-satunya gunanya dokumen adjustment.

	qty positif = tambah lapisan baru di bin itu. qty negatif = kurangi, tertua
	duluan; kalau lapisannya kurang, sisanya dibukukan sebagai `is_short` supaya
	selisihnya KELIHATAN di audit(), bukan hilang diam-diam.
	"""
	qty = flt(qty)
	if qty > _EPS:
		_write(
			item_code,
			bin_location,
			qty,
			voucher,
			received_on or _posting_dt(voucher),
			qty_left=qty,
		)
		return
	if qty < -_EPS:
		gudang = frappe.get_cached_value("Bin Location", bin_location, "gudang")
		sisa = _eat(item_code, gudang, -qty, voucher, bin_location, None)
		if sisa > _EPS:
			_write(item_code, bin_location, -sisa, voucher, _posting_dt(voucher), is_short=1)


def undo(voucher):
	"""Balik SEMUA baris buku besar milik dokumen ini, lengkap dengan umur lapisannya.

	Dibalik dari baris yang BENAR-BENAR ditulis, bukan dari isi dokumennya: umur
	lapisan yang dulu dimakan ikut pulih, dan itu satu-satunya cara FIFO tidak
	bohong sesudah pembatalan.

	Daftarnya diambil dulu sebelum satu pun baris balikan ditulis -- kalau tidak,
	baris balikannya sendiri ikut terbaca dan pembatalannya berputar.
	"""
	rows = frappe.get_all(
		"Bin Ledger Entry",
		filters={"voucher_type": voucher.doctype, "voucher_no": voucher.name},
		fields=["item_code", "bin_location", "qty", "received_on"],
		order_by="creation desc",
	)
	for r in rows:
		adjust(r.item_code, r.bin_location, -flt(r.qty), voucher, received_on=r.received_on)


# ------------------------------------------------------------------ bantu


def _fits_in(bin_location, item_code, qty):
	"""Berapa banyak yang muat di bin ini. Pilihan operator itu USULAN, bukan kontrak.

	Yang tidak muat menetes ke saran berikutnya; baris dokumennya sendiri tidak
	pernah dipecah. Lapisan bin memang satu-satunya yang tahu kapasitas.
	"""
	loc = frappe.db.get_value(
		"Bin Location", bin_location, ["gudang", "disabled", "merged_into"], as_dict=True
	)
	if not loc or loc.disabled or loc.merged_into:
		return 0
	# Bin yang sedang masuk Replan yang belum disetujui tidak menerima barang baru;
	# yang tidak muat mendarat di staging seperti biasa.
	from erpnext_custom import replan

	if bin_location in replan.locked_bins():
		return 0
	caps = bin_layout.bin_caps_map(loc.gudang)
	used = bin_layout.bin_usage([bin_location]).get(
		bin_location, {"qty": 0.0, "weight": 0.0, "volume": 0.0, "share": 0.0}
	)
	weight, volume = bin_layout.item_size(item_code)
	muat = bin_layout.fits(
		*bin_layout.bin_free(caps.get(bin_location, (0.0, 0.0, 0.0)), used),
		weight,
		volume,
		free_share=1.0 - flt(used.get("share")),
		pack=bin_layout.packing_rules().get(item_code),
	)
	return flt(qty) if muat is None else min(flt(qty), flt(muat))


def _undo_rows(voucher, item_code, gudang):
	"""Baris keluar milik dokumen ini -- dipakai saat batal untuk mengembalikan ke asal."""
	return frappe.get_all(
		"Bin Ledger Entry",
		filters={
			"voucher_type": voucher.doctype,
			"voucher_no": voucher.name,
			"item_code": item_code,
			"gudang": gudang,
			"qty": ["<", 0],
			"is_short": 0,
		},
		fields=["bin_location", "qty", "received_on"],
		order_by="creation asc",
	)


def _touched(doc):
	"""Pasangan (item, gudang) yang benar-benar bergerak -- dibaca dari SLE, bukan ditebak.

	Membaca field dokumen satu per satu (warehouse, s_warehouse, t_warehouse,
	from_warehouse, supplier_warehouse, rejected_warehouse, packed_items,
	supplied_items...) berarti arkeologi field yang harus ditinjau ulang tiap kali
	ada tipe dokumen baru. SLE sudah menyatakan kebenarannya, dan tabelnya terindeks
	pada (voucher_type, voucher_no).
	"""
	rows = frappe.get_all(
		"Stock Ledger Entry",
		filters={"voucher_type": doc.doctype, "voucher_no": doc.name},
		fields=["item_code", "warehouse"],
		distinct=True,
	)
	return {(r.item_code, r.warehouse) for r in rows}


def _hints(doc):
	"""{(item, gudang): [(bin, qty), ...]} -- dari mana tiap BARIS dokumen ini mengambil.

	Per baris, bukan per (item, gudang). Satu pengiriman lazim mengambil item yang
	sama dari beberapa rak, dan peta satu-bin-per-item membuang semua rak kecuali
	yang terakhir dibaca.

	Dua sumber. Field `custom_bin_location` di barisnya kalau diisi, dan -- untuk
	baris Delivery Note yang lahir dari Pick List -- bin staging keluar, karena
	Pick List sudah menurunkan barangnya ke sana waktu dia submit.
	"""
	out = {}
	for row in doc.get("items") or []:
		wh = next(
			(row.get(f) for f in ("warehouse", "t_warehouse", "target_warehouse") if row.get(f)),
			None,
		)
		if not wh or not is_tracked(wh):
			continue
		hint = row.get("custom_bin_location")
		if not hint and row.get("pick_list_item"):
			hint = staging_bin(wh, KELUAR)
		if hint:
			qty = flt(row.get("stock_qty")) or flt(row.get("qty"))
			out.setdefault((row.get("item_code"), wh), []).append((hint, qty))
	return out


# ------------------------------------------------------------------ hook


def doc_hook(doc, method=None):
	"""Satu-satunya pintu masuk. Mengukur selisih terhadap Bin, lalu menutupnya.

	Dipasang di on_submit DAN on_cancel. Pembatalan tidak butuh kode khusus:
	ERPNext menulis SLE pembalik, Bin bergerak, dan selisihnya terukur sendiri.

	URUTAN PENTING: di Purchase Receipt / Purchase Invoice, hook ini harus jalan
	DULUAN sebelum handler yang ikut membuat dokumen stok (sparepart.issue_on_submit
	menyubmit Stock Entry Material Issue di dalam on_submit induknya). Kalau tidak,
	Stock Entry anak itu memakan FIFO di gudang yang penerimaannya belum dibukukan
	-- jadi yang termakan adalah stok lama milik orang lain.
	"""
	if doc.doctype == "Stock Ledger Entry":
		return
	if doc.doctype in ("Sales Invoice", "Purchase Invoice") and not doc.get("update_stock"):
		return

	hints = _hints(doc)
	for item_code, gudang in _touched(doc):
		if not is_tracked(gudang) or not is_ledgered_item(item_code):
			continue
		nyata = flt(
			frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": gudang}, "actual_qty")
		)
		delta = nyata - bin_total(item_code, gudang)
		if abs(delta) <= _EPS:
			continue
		apply(item_code, gudang, delta, voucher=doc, hint_bin=hints.get((item_code, gudang)))


def sle_hook(doc, method=None):
	"""Jaring pengaman untuk SLE yang tidak lewat submit dokumen.

	Tidak menebak apa pun, cuma memanggil pengukuran yang sama. Repost dilewati
	karena ia membongkar-pasang SLE yang sama dan kuantitasnya tidak berubah.
	"""
	if frappe.flags.get("through_repost_item_valuation"):
		return
	# Bin Adjustment sudah menulis letak barangnya SENDIRI sebelum Stock
	# Reconciliation-nya disubmit. SLE disubmit sebelum tabBin ikut naik (lihat
	# erpnext/stock/stock_ledger.py: make_sl_entries), jadi pengukuran di sini akan
	# membaca saldo LAMA dan membatalkan koreksi yang baru saja ditulis. doc_hook di
	# ujung Stock Reconciliation tetap jalan -- di situ tabBin sudah benar, dan sisa
	# selisih (kalau ada) tetap tertutup seperti biasa.
	if frappe.flags.get("bin_adjustment"):
		return
	item_code, gudang = doc.item_code, doc.warehouse
	if not is_tracked(gudang) or not is_ledgered_item(item_code):
		return
	nyata = flt(
		frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": gudang}, "actual_qty")
	)
	delta = nyata - bin_total(item_code, gudang)
	if abs(delta) > _EPS:
		apply(item_code, gudang, delta, voucher=None)


# ------------------------------------------------------------------ audit


@frappe.whitelist()
def audit(gudang=None):
	"""Item yang catatan binnya tidak sama dengan stok ERPNext. Kosong = sehat.

	Ini jaring yang tidak dipunyai sistem lama: dulu selisih cuma hilang diam-diam.
	"""
	filters = {"actual_qty": ["!=", 0]}
	if gudang:
		filters["warehouse"] = gudang
	out = []
	for b in frappe.get_all("Bin", filters=filters, fields=["item_code", "warehouse", "actual_qty"]):
		if not is_tracked(b.warehouse) or not is_ledgered_item(b.item_code):
			continue
		catat = bin_total(b.item_code, b.warehouse)
		if abs(flt(b.actual_qty) - catat) > _EPS:
			out.append(
				{
					"item_code": b.item_code,
					"gudang": b.warehouse,
					"stok": flt(b.actual_qty),
					"di_bin": catat,
					"selisih": flt(b.actual_qty) - catat,
				}
			)
	return out

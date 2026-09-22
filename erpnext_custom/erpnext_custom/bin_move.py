"""Dasar dokumen pemindah bin: aturan penempatan yang dipakai BERSAMA.

Dua dokumen menaruh barang ke bin, dan keduanya wajib menuruti aturan master yang
sama (kapasitas, aturan campur, batas tingkat barang berat, daftar item, bin
terkunci):

    Goods Receive   penampung -> rak   (put-away, barisnya dari Purchase Invoice)
    Bin Replan      rak -> rak         (turunkan dari tingkat atas / barang tua)

Aturannya duduk di sini, bukan di salah satu controller, supaya tidak ada dokumen
yang tertinggal saat aturannya berubah -- satu penjaga untuk semua penulis.

Tidak ada yang menyentuh stok maupun jurnal: stoknya sudah diakui di dokumen
stoknya (PI/PR/Stock Entry), yang bergerak di sini cuma LETAK barangnya
(erpnext_custom/bin_ledger.py).
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt

from erpnext_custom import bin_layout, bin_ledger, replan


def autoname_with_warehouse(doc):
	"""<nomor seri> - <gudang>, mis. "GRC-2026-00007 - Gudang Jakarta".

	Dokumen rak/bin dibaca orang gudang, bukan akuntan: gudang mana yang dimaksud
	harus kelihatan tanpa membuka dokumennya. Dipakai bersama oleh semua dokumen
	bin (Goods Receive, Bin Replan, Bin Adjustment) supaya nomornya seragam.
	"""
	seri = make_autoname(doc.naming_series, doc=doc)
	gudang = frappe.get_cached_value("Warehouse", doc.gudang, "warehouse_name") or doc.gudang
	return f"{seri} - {gudang}"


class BinMove(Document):
	"""Satu baris = satu perpindahan: `from_bin_location` -> `bin_location`.

	Kosongkan `from_bin_location` untuk mengambil dari bin penampung (staging)
	gudang ini.

	Umur barang (`received_on`) IKUT PINDAH, tidak pernah direset. Kalau tidak,
	FIFO jadi bohong untuk hampir semua barang, karena staging memang tempat
	mendarat defaultnya.
	"""

	def autoname(self):
		self.name = autoname_with_warehouse(self)

	def validate(self):
		if frappe.get_cached_value("Warehouse", self.gudang, "is_group"):
			frappe.throw(_("{0} adalah group warehouse, pilih gudang yang menyimpan stok.").format(self.gudang))
		self._fill_rows()
		self._check_source()
		self._check_placement()
		self._check_mix()
		self._check_capacity()
		self._check_pack()
		self._check_rack_weight()

	def on_submit(self):
		for row in self.items:
			bin_ledger.move(row.item_code, self._source(row), row.bin_location, flt(row.qty), self)

	def on_cancel(self):
		for row in self.items:
			bin_ledger.move(row.item_code, row.bin_location, self._source(row), flt(row.qty), self)

	def _source(self, row):
		return row.from_bin_location or bin_ledger.staging_bin(self.gudang)

	# ---------------------------------------------------------------- internal

	def _fill_rows(self):
		for row in self.items:
			if not flt(row.qty):
				frappe.throw(_("Baris {0}: qty tidak boleh 0.").format(row.idx))
			loc = frappe.get_cached_value(
				"Bin Location", row.bin_location, ["gudang", "rack"], as_dict=True
			)
			if loc.gudang != self.gudang:
				frappe.throw(
					_("Baris {0}: bin {1} ada di {2}, bukan di {3}.").format(
						row.idx, row.bin_location, loc.gudang, self.gudang
					)
				)
			row.rack = loc.rack
			weight, volume = bin_layout.item_size(row.item_code)
			row.weight = flt(row.qty) * weight
			row.volume = flt(row.qty) * volume

	def _check_source(self):
		"""Bin asal harus benar-benar berisi barangnya.

		Dicek di validate (bukan cuma saat submit) supaya draft yang salah ketahuan
		sejak disimpan. bin_ledger.move() mengecek ulang saat submit -- ini sengaja
		dobel, karena isi bin bisa berubah di antara simpan dan submit.
		"""
		butuh = defaultdict(float)
		for row in self.items:
			if flt(row.qty) <= 0:
				continue
			butuh[(row.item_code, self._source(row))] += flt(row.qty)
		for (item_code, asal), qty in butuh.items():
			ada = sum(flt(l.qty_left) for l in bin_ledger.fifo_layers(item_code, self.gudang, asal))
			if qty > ada + 0.0001:
				frappe.throw(
					_("Bin {0} cuma berisi {1} {2}, tidak bisa dipindahkan {3}.").format(
						asal, ada, item_code, qty
					)
				)

	def _check_placement(self):
		"""Aturan master rak/bin: bin gabungan, item yang boleh, tingkat, dan panjang.

		Zona/daftar item rak dan panjang slot bisa dimatikan di Stock Settings >
		Warehouse (gudang yang masternya belum lengkap tidak langsung terkunci).
		Daftar Item Khusus PER BIN tidak ikut saklar itu: itu daftar yang diketik
		orang untuk bin tertentu, bukan warisan master yang mungkin belum diisi.
		"""
		setting = bin_layout.stock_settings()
		caps = bin_layout.bin_caps_map(self.gudang)
		# Bin yang masuk Replan yang belum disetujui: barangnya sedang dipindah orang
		# gudang, jadi tidak boleh ada yang menitipkan barang ke situ dulu. Dokumen
		# ini sendiri dikecualikan -- kalau tidak, replan tidak bisa menyetujui
		# binnya sendiri.
		terkunci = replan.locked_bins(exclude=self.name)
		for row in self.items:
			if flt(row.qty) <= 0:
				continue
			if row.bin_location in terkunci:
				frappe.throw(
					_(
						"Baris {0}: bin {1} sedang dikunci Replan {2} yang belum disetujui. "
						"Setujui atau batalkan replan itu dulu."
					).format(row.idx, row.bin_location, terkunci[row.bin_location])
				)
			loc = frappe.get_cached_doc("Bin Location", row.bin_location)
			if loc.disabled or frappe.get_cached_value("Rack", loc.rack, "disabled"):
				frappe.throw(
					_(
						"Baris {0}: bin {1} atau raknya sudah dinonaktifkan, tidak bisa diisi lagi. "
						"Mengeluarkan barang dari bin nonaktif tetap boleh."
					).format(row.idx, row.bin_location)
				)
			if loc.merged_into:
				frappe.throw(
					_("Baris {0}: bin {1} digabung ke {2}, tempatkan barangnya di bin itu.").format(
						row.idx, row.bin_location, loc.merged_into
					)
				)
			if loc.get("allowed_items"):
				if row.item_code not in {r.item_code for r in loc.allowed_items}:
					frappe.throw(
						_("Baris {0}: bin {1} cuma menerima item di daftar Item Khusus-nya.").format(
							row.idx, row.bin_location
						)
					)
			elif setting.get("custom_enforce_rack_zone") and not bin_layout.item_allowed(
				loc.rack, row.item_code
			):
				frappe.throw(
					_("Baris {0}: rak {1} tidak menerima {2} (lihat Zona / Item Khusus di master Rak).").format(
						row.idx, loc.rack, row.item_code
					)
				)
			batas = bin_layout.heavy_max_level(row.item_code)
			if batas and (loc.rack_level or 999) > batas:
				frappe.throw(
					_(
						"Baris {0}: {1} termasuk barang berat, cuma boleh sampai tingkat {2}. "
						"Bin {3} ada di tingkat {4}."
					).format(row.idx, row.item_code, batas, row.bin_location, loc.rack_level or "?")
				)
			panjang = bin_layout.item_length(row.item_code)
			slot = flt(caps.get(row.bin_location, (0.0, 0.0, 0.0))[2])
			if setting.get("custom_enforce_bin_length") and slot and panjang > slot + 0.0001:
				frappe.throw(
					_(
						"Baris {0}: {1} panjangnya {2} m, slot bin {3} cuma {4} m. "
						"Gabungkan bin sebelahnya lewat field Digabung Ke di master Bin Location."
					).format(row.idx, row.item_code, panjang, row.bin_location, slot)
				)

	def _check_mix(self):
		"""Barang yang tidak boleh sekamar: isi bin sekarang DAN baris dokumen ini.

		Dua-duanya perlu. Mengecek isi bin saja meloloskan dua baris dokumen yang
		sama-sama menunjuk bin kosong yang sama -- dan setelah submit barangnya
		sudah telanjur bercampur.
		"""
		isi = {
			b: set(u["items"])
			for b, u in bin_layout.bin_usage([r.bin_location for r in self.items]).items()
		}
		for row in self.items:
			if flt(row.qty) <= 0:
				continue
			huni = isi.setdefault(row.bin_location, set())
			lawan = bin_layout.mix_blocker(row.item_code, huni)
			if lawan:
				frappe.throw(
					_("Baris {0}: {1} tidak boleh dicampur dengan {2} di bin {3}.").format(
						row.idx, row.item_code, lawan, row.bin_location
					)
				)
			huni.add(row.item_code)

	def _check_capacity(self):
		"""Kapasitas berat/volume bin adalah batas keras -- ditolak, bukan diperingatkan.

		Yang dipakai kapasitas EFEKTIF: isian bin sendiri, kalau kosong ikut tingkat
		di master Rak lalu default Stock Settings, ditambah bin yang digabung ke sini.
		"""
		delta = defaultdict(lambda: {"weight": 0.0, "volume": 0.0})
		for row in self.items:
			delta[row.bin_location]["weight"] += flt(row.weight)
			delta[row.bin_location]["volume"] += flt(row.volume)
		usage = bin_layout.bin_usage(list(delta) + [r.from_bin_location for r in self.items if r.get("from_bin_location")])
		caps = bin_layout.bin_caps_map(self.gudang)
		# Barang yang KELUAR dari sebuah bin di dokumen ini mengurangi isi bin itu.
		# Perlu untuk Replan: memindahkan barang dari bin penuh ke bin penuh yang
		# saling bertukar isi akan selalu ditolak kalau isi bin asal dianggap tetap.
		for row in self.items:
			asal = row.get("from_bin_location")
			if not asal or asal not in usage:
				continue
			weight, volume = bin_layout.item_size(row.item_code)
			usage[asal]["weight"] -= flt(row.qty) * weight
			usage[asal]["volume"] -= flt(row.qty) * volume
		for bin_location, add in delta.items():
			used = usage.get(bin_location, {"weight": 0.0, "volume": 0.0})
			for i, (field, label, unit) in enumerate(
				(
					("weight", _("berat"), "kg"),
					("volume", _("volume"), "m3"),
				)
			):
				cap = flt(caps.get(bin_location, (0.0, 0.0, 0.0))[i])
				if cap <= 0:
					continue
				total = flt(used[field]) + add[field]
				if total > cap + 0.0001:
					frappe.throw(
						_("Bin {0} kelebihan {1}: {2} {3} dari kapasitas {4} {3}.").format(
							bin_location, label, round(total - cap, 3), unit, cap
						)
					)

	def _check_pack(self):
		"""Jumlah KEMASAN per bin: 4 drum per bin, 2 pallet per bin.

		Dihitung dari kemasan utuh (pack_share), bukan dari qty lurus -- drum yang
		tinggal separuh tetap memakan satu slot palet.

		Isi bin dibaca per (bin, item) langsung dari Item Bin Qty karena bin_usage
		cuma menyimpan totalnya, sedangkan ceil-nya harus per item. Barang yang
		KELUAR dari bin lain di dokumen ini ikut dikurangi, kalau tidak Replan yang
		menukar isi dua bin penuh akan selalu ditolak.

		Bin penampung (rak bukan jenis "Rak") dikecualikan: batas kemasan itu soal
		slot rak, bukan lantai transit -- kalau tidak, mengembalikan barang ke
		penampung bisa ditolak dan barangnya tidak punya tempat pulang.
		"""
		aturan = bin_layout.packing_rules()
		if not aturan:
			return
		tujuan = {
			row.bin_location
			for row in self.items
			if flt(row.qty) > 0
			and frappe.get_cached_value(
				"Rack", frappe.get_cached_value("Bin Location", row.bin_location, "rack"), "kind"
			)
			== "Rak"
		}
		if not tujuan:
			return
		saldo = defaultdict(float)
		for r in frappe.get_all(
			"Item Bin Qty",
			filters={"bin_location": ["in", list(tujuan)]},
			fields=["bin_location", "item_code", "qty"],
		):
			saldo[(r.bin_location, r.item_code)] += flt(r.qty)
		for row in self.items:
			if flt(row.qty) <= 0:
				continue
			if row.bin_location in tujuan:
				saldo[(row.bin_location, row.item_code)] += flt(row.qty)
			asal = row.get("from_bin_location")
			if asal and asal in tujuan:
				saldo[(asal, row.item_code)] -= flt(row.qty)

		terpakai = defaultdict(float)
		rincian = defaultdict(list)
		for (bin_location, item_code), qty in saldo.items():
			pack = aturan.get(item_code)
			bagian = bin_layout.pack_share(qty, pack)
			if not bagian:
				continue
			terpakai[bin_location] += bagian
			rincian[bin_location].append(
				_("{0} {1} kemasan (maks {2} per bin)").format(
					item_code, int(round(bagian * pack[1])), pack[1]
				)
			)
		for bin_location in tujuan:
			if terpakai[bin_location] > 1.0001:
				frappe.throw(
					_("Bin {0} kelebihan kemasan ({1}% terisi): {2}.").format(
						bin_location,
						int(round(terpakai[bin_location] * 100)),
						", ".join(rincian[bin_location]),
					)
				)

	def _check_rack_weight(self):
		"""Batas beban RANGKA rak, terpisah dari kapasitas tiap bin.

		Rangka biasanya tidak sanggup menahan semua binnya penuh sekaligus, jadi
		batas ini bisa lebih kecil dari jumlah kapasitas bin di bawahnya.
		0 di master Rak = rangka tidak jadi pembatas.
		"""
		delta = defaultdict(float)
		for row in self.items:
			rack = frappe.get_cached_value("Bin Location", row.bin_location, "rack")
			delta[rack] += flt(row.weight)
			# pindah di dalam rak yang sama tidak menambah beban rangkanya
			if row.get("from_bin_location"):
				asal = frappe.get_cached_value("Bin Location", row.from_bin_location, "rack")
				delta[asal] -= flt(row.weight)
		for rack, tambah in delta.items():
			if tambah <= 0:
				continue
			batas = flt(frappe.get_cached_value("Rack", rack, "max_weight"))
			if batas <= 0:
				continue
			total = bin_layout.rack_weight(rack) + tambah
			if total > batas + 0.0001:
				frappe.throw(
					_("Rak {0} kelebihan beban: {1} kg dari batas rangka {2} kg.").format(
						rack, round(total - batas, 2), batas
					)
				)

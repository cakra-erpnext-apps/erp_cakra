from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from erpnext_custom import bin_layout


class GoodsReceive(Document):
	"""Penerimaan barang: item dari sebuah Purchase Invoice ditaruh di bin mana.

	Tidak menyentuh stok maupun jurnal sama sekali -- stok sudah diakui di PI,
	dokumen ini cuma memetakan letak fisiknya (lihat erpnext_custom/bin_layout.py).
	Qty negatif = mengeluarkan dari bin (pindah = satu baris negatif di bin asal +
	satu baris positif di bin tujuan).
	"""

	def validate(self):
		if frappe.get_cached_value("Warehouse", self.gudang, "is_group"):
			frappe.throw(_("{0} adalah group warehouse, pilih gudang yang menyimpan stok.").format(self.gudang))
		self._fill_rows()
		self._check_stock()
		self._check_placement()
		self._check_capacity()
		self._check_rack_weight()

	def on_submit(self):
		for row in self.items:
			bin_layout.move(row.item_code, row.bin_location, flt(row.qty))

	def on_cancel(self):
		for row in self.items:
			# allow_short: barangnya bisa saja sudah keluar lewat DN dan binnya sudah
			# dipangkas reconcile() -- pembatalan tetap harus bisa jalan.
			bin_layout.move(row.item_code, row.bin_location, -flt(row.qty), allow_short=True)

	# ---------------------------------------------------------------- internal

	def _fill_rows(self):
		for row in self.items:
			if not flt(row.qty):
				frappe.throw(_("Baris {0}: qty tidak boleh 0.").format(row.idx))
			gudang = frappe.get_cached_value("Bin Location", row.bin_location, "gudang")
			if gudang != self.gudang:
				frappe.throw(
					_("Baris {0}: bin {1} ada di {2}, bukan di {3}.").format(
						row.idx, row.bin_location, gudang, self.gudang
					)
				)
			weight, volume = bin_layout.item_size(row.item_code)
			row.weight = flt(row.qty) * weight
			row.volume = flt(row.qty) * volume

	def _check_stock(self):
		"""Tidak boleh menempatkan lebih banyak dari stok yang benar-benar ada."""
		delta = defaultdict(float)
		for row in self.items:
			delta[row.item_code] += flt(row.qty)
		for item_code, qty in delta.items():
			if qty <= 0:
				continue
			sudah = bin_layout.placed_qty(item_code, self.gudang)
			stok = bin_layout.stock_qty(item_code, self.gudang)
			if sudah + qty > stok + 0.0001:
				frappe.throw(
					_(
						"{0}: stok di {1} cuma {2}, sudah ditempatkan {3}. Tidak bisa menempatkan {4} lagi."
					).format(item_code, self.gudang, stok, sudah, qty)
				)

	def _check_placement(self):
		"""Aturan master rak/bin: bin gabungan, item yang boleh, dan panjang barang.

		Zona/daftar item dan panjang slot bisa dimatikan di Stock Settings > Warehouse
		(gudang yang masternya belum lengkap tidak langsung terkunci).
		"""
		setting = bin_layout.stock_settings()
		caps = bin_layout.bin_caps_map(self.gudang)
		for row in self.items:
			if flt(row.qty) <= 0:
				continue
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
			if setting.get("custom_enforce_rack_zone") and not bin_layout.item_allowed(
				loc.rack, row.item_code
			):
				frappe.throw(
					_("Baris {0}: rak {1} tidak menerima {2} (lihat Zona / Item Khusus di master Rak).").format(
						row.idx, loc.rack, row.item_code
					)
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

	def _check_capacity(self):
		"""Kapasitas berat/volume bin adalah batas keras -- ditolak, bukan diperingatkan.

		Yang dipakai kapasitas EFEKTIF: isian bin sendiri, kalau kosong ikut tingkat
		di master Rak lalu default Stock Settings, ditambah bin yang digabung ke sini.
		"""
		delta = defaultdict(lambda: {"weight": 0.0, "volume": 0.0})
		for row in self.items:
			delta[row.bin_location]["weight"] += flt(row.weight)
			delta[row.bin_location]["volume"] += flt(row.volume)
		usage = bin_layout.bin_usage(list(delta))
		caps = bin_layout.bin_caps_map(self.gudang)
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
		for rack, tambah in delta.items():
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

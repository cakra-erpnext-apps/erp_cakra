"""Replan: menata ulang letak barang yang sudah di rak.

Dua hal yang bikin gudang melambat dan cuma bisa dibetulkan dengan MEMINDAHKAN
barang, bukan dengan aturan penempatan baru:

1. barang nangkring di tingkat atas padahal tingkat bawah sudah kosong lagi --
   tiap pengambilan jadi butuh tangga atau forklift;
2. barang tua terkubur di tempat yang susah digapai, jadi yang keluar malah
   barang baru walaupun buku besar bin sudah FIFO.

`plan()` membaca keadaan sekarang dan mengarang DAFTAR INSTRUKSI: item ini,
sebanyak ini, dari bin ini ke bin ini. Daftarnya masuk dokumen Bin Replan untuk
dicentang satu-satu orang gudang, lalu berlaku begitu disetujui (submit).

Bin yang masuk replan yang belum disetujui DIKUNCI dari barang masuk
(`locked_bins`, ditegakkan di erpnext_custom/bin_move.py): barangnya sedang
dipegang orang, jadi menitipkan barang baru ke situ cuma bikin peta bin bohong.
Mengeluarkan barang dari bin terkunci tetap boleh -- pengiriman tidak boleh
disandera pekerjaan rapi-rapi.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, nowdate

from erpnext_custom import bin_layout


def locked_bins(exclude=None):
	"""{bin: nomor replan} untuk semua Bin Replan yang masih DRAFT.

	Draft = pekerjaannya sedang jalan. Submit (disetujui) melepas kuncinya karena
	barangnya sudah sampai di tempat barunya; batal juga melepas.

	Dua query, bukan satu ke tabel anak dengan filter docstatus: docstatus baris
	anak cuma benar sejauh parent-nya ikut tersimpan, dan kunci ini tidak boleh
	bergantung pada itu.
	"""
	drafts = frappe.get_all("Bin Replan", filters={"docstatus": 0}, pluck="name")
	if exclude:
		drafts = [d for d in drafts if d != exclude]
	if not drafts:
		return {}
	out = {}
	for row in frappe.get_all(
		"Bin Replan Item",
		filters={"parent": ["in", drafts]},
		fields=["parent", "from_bin_location", "bin_location"],
	):
		for b in (row.from_bin_location, row.bin_location):
			if b:
				out.setdefault(b, row.parent)
	return out


def _saldo(gudang):
	"""{(item, bin): {"qty", "oldest"}} dari buku besar bin.

	Umur dibaca dari lapisan FIFO, bukan dari Item Bin Qty: yang menentukan
	prioritas replan itu tanggal terima lapisan tertua yang masih ada di bin itu.
	"""
	agg = {}
	for r in frappe.get_all(
		"Bin Ledger Entry",
		filters={"gudang": gudang, "qty_left": [">", 0]},
		fields=["item_code", "bin_location", "qty_left", "received_on"],
	):
		a = agg.setdefault((r.item_code, r.bin_location), {"qty": 0.0, "oldest": None})
		a["qty"] += flt(r.qty_left)
		if r.received_on and (a["oldest"] is None or r.received_on < a["oldest"]):
			a["oldest"] = r.received_on
	return agg


@frappe.whitelist()
def plan(gudang, max_level=2, min_age_days=90):
	"""Instruksi pindah: turunkan dari tingkat atas, dan majukan barang tua.

	`max_level` = tingkat tertinggi yang dianggap masih enak diambil tangan
	(1 = tingkat A). Barang di atas itu diusulkan turun. `min_age_days` = umur yang
	bikin barang dianggap harus dimajukan ke tempat paling gampang digapai; 0
	mematikan kriteria itu.

	Tujuannya dipilih oleh `bin_layout.suggest()` -- mesin yang sama dengan
	Recommendation di Goods Receive, jadi kapasitas, zona, aturan campur dan batas
	barang berat berlaku sama. Bedanya: cuma bin yang BENAR-BENAR lebih gampang
	digapai (atau lebih dekat pick area) yang diterima, supaya replan tidak
	menyuruh orang memindahkan barang ke tempat yang sama susahnya.
	"""
	max_level = cint(max_level)
	min_age_days = cint(min_age_days)
	terkunci = locked_bins()

	bins = {
		b.name: b
		for b in frappe.get_all(
			"Bin Location",
			filters={"gudang": gudang, "disabled": 0},
			fields=["name", "rack", "level", "rack_level", "merged_into"],
		)
	}
	racks = {
		r.name: r
		for r in frappe.get_all(
			"Rack", filters={"gudang": gudang}, fields=["name", "kind", "disabled"]
		)
	}

	kandidat = []
	for (item_code, bin_location), a in _saldo(gudang).items():
		b = bins.get(bin_location)
		if not b or bin_location in terkunci:
			continue
		rack = racks.get(b.rack)
		# Bin penampung tidak ikut: mengosongkan staging itu pekerjaan Goods Receive,
		# lengkap dengan nomor notanya. Rak nonaktif juga tidak -- tujuannya tidak
		# boleh diisi lagi, jadi tidak ada gunanya mengarang pindahan dari sana.
		if not rack or rack.kind != "Rak" or rack.disabled:
			continue
		umur = date_diff(nowdate(), a["oldest"]) if a["oldest"] else 0
		alasan = []
		if max_level and cint(b.rack_level) > max_level:
			alasan.append(_("Tingkat {0}").format(b.level or b.rack_level))
		if min_age_days and umur >= min_age_days:
			alasan.append(_("Umur {0} hari").format(umur))
		if not alasan:
			continue
		kandidat.append(
			{
				"item_code": item_code,
				"item_name": frappe.get_cached_value("Item", item_code, "item_name"),
				"stock_uom": frappe.get_cached_value("Item", item_code, "stock_uom"),
				"from_bin_location": bin_location,
				"from_rack": b.rack,
				"qty": a["qty"],
				"age_days": umur,
				"reason": ", ".join(alasan),
			}
		)

	# Yang paling tua dilayani duluan, lalu yang paling tinggi: tempat bagus di
	# tingkat bawah terbatas, dan yang paling pantas mendapatkannya adalah barang
	# yang paling dekat harus keluar.
	kandidat.sort(key=lambda k: (-k["age_days"], -cint(bins[k["from_bin_location"]].rack_level)))

	hasil = bin_layout.suggest(
		gudang,
		[
			{"item_code": k["item_code"], "qty": k["qty"], "from_bin": k["from_bin_location"]}
			for k in kandidat
		],
		exclude=[k["from_bin_location"] for k in kandidat],
	)

	rows, skipped = [], []
	for k, s in zip(kandidat, hasil):
		if not s or s.get("skip"):
			skipped.append("{0} @ {1}: {2}".format(k["item_code"], k["from_bin_location"], (s or {}).get("skip") or _("dilewati")))
			continue
		for a in s.get("allocations") or []:
			rows.append(
				{
					"item_code": k["item_code"],
					"item_name": k["item_name"],
					"stock_uom": k["stock_uom"],
					"from_bin_location": k["from_bin_location"],
					"from_rack": k["from_rack"],
					"bin_location": a["bin_location"],
					"rack": a["rack"],
					"qty": a["qty"],
					"age_days": k["age_days"],
					"reason": k["reason"],
				}
			)
		if s.get("shortage"):
			skipped.append(
				"{0} @ {1}: {2} {3}".format(
					k["item_code"], k["from_bin_location"], s["shortage"], _("tidak kebagian bin")
				)
			)
	return {"rows": rows, "skipped": skipped}

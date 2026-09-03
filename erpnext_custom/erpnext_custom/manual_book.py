"""Menu "Manual Book" di desk: panduan pemakaian per modul.

Bentuk: satu Desktop Icon + Workspace Sidebar "Manual Book" (menu kiri) + satu
Workspace per manual. Halaman manual = SATU blok Custom HTML Block (nama sama
dengan workspace-nya) berisi flowchart + langkah bernomor — editorjs paragraph
terlalu terbatas untuk layout begini.

Konten manual hidup DI FILE INI sebagai satu-satunya sumber; ensure_manual_book()
menimpa dokumen DB tiap migrate, jadi edit lewat UI tidak bertahan — edit di sini.

Rencana isi (permintaan user 2026-08-04): expedition, payment, selling, stock,
buying. Dimulai dari Manual Trading (SO -> Pick List -> DN -> SI).
"""

import json

import frappe

MODULE = "ERPNext Custom"
# app "erpnext" supaya menu muncul satu grup dengan Buying/Selling/Stock di desk.
APP = "erpnext"
SIDEBAR = "Manual Book"


def _h(text, level=5):
	return {"type": "header", "data": {"text": f'<span class="h{level}"><b>{text}</b></span>', "col": 12}}


def _p(text):
	return {"type": "paragraph", "data": {"text": text, "col": 12}}


# CSS bersama semua halaman manual. Pakai CSS variable desk (tembus shadow DOM)
# supaya ikut light/dark theme.
MANUAL_CSS = """
.mb { font-size: 14px; line-height: 1.6; color: var(--text-color, #1f1f1f); max-width: 980px; }
.mb h2 { font-size: 20px; font-weight: 700; margin: 0 0 4px; }
.mb .lead { opacity: .7; margin: 0 0 20px; }

.mb .flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 4px; margin: 0 0 24px; }
.mb .flow-node { flex: 1 1 140px; min-width: 140px; max-width: 260px;
  border: 1px solid var(--border-color, #dcdcdc);
  border-radius: 10px; padding: 10px 12px; background: var(--card-bg, #fff); }
.mb .flow-node .tag { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .4px;
  padding: 1px 7px; border-radius: 4px; background: var(--bg-gray, #f3f3f3);
  border: 1px solid var(--border-color, #dcdcdc); margin-bottom: 6px; }
.mb .flow-node .nm { font-weight: 600; }
.mb .flow-node .ds { font-size: 12.5px; opacity: .7; }
.mb .flow-node .fx { font-size: 12px; margin-top: 6px; padding-top: 6px;
  border-top: 1px dashed var(--border-color, #dcdcdc); }
.mb .flow-arrow { align-self: center; flex: 0 0 auto; width: 18px; height: 18px; }
.mb .flow-arrow svg { display: block; width: 100%; height: 100%; stroke: var(--text-muted, #9a9a9a); }

.mb .fh { font-weight: 700; margin: 4px 0 8px; }

.mb .box { border: 1px solid var(--border-color, #dcdcdc); border-radius: 10px;
  padding: 12px 16px; margin-bottom: 20px; background: var(--card-bg, #fff); }
.mb .box .bt { font-weight: 700; margin-bottom: 6px; }
.mb .box.warn { border-color: var(--orange-400, #e8a13c); }

.mb table.j { width: 100%; border-collapse: collapse; margin: 0 0 24px; }
.mb table.j th, .mb table.j td { border: 1px solid var(--border-color, #dcdcdc);
  padding: 7px 10px; text-align: left; vertical-align: top; font-size: 13px; }
.mb table.j th { background: var(--bg-gray, #f3f3f3); font-weight: 700; }
.mb table.j td.n { opacity: .7; }
.mb .box ul { margin: 0; padding-left: 18px; }

.mb .step { display: flex; gap: 14px; border: 1px solid var(--border-color, #dcdcdc);
  border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; background: var(--card-bg, #fff); }
.mb .step .no { flex: 0 0 30px; height: 30px; border-radius: 50%; background: var(--text-color, #1f1f1f);
  color: var(--card-bg, #fff); font-weight: 700; display: flex; align-items: center; justify-content: center; }
.mb .step .st { font-weight: 700; margin-bottom: 4px; }
.mb .step ul { margin: 0; padding-left: 18px; }
.mb .step li { margin-bottom: 3px; }
.mb .step .fx { margin-top: 8px; font-size: 13px; padding: 6px 10px; border-radius: 6px;
  background: var(--bg-gray, #f5f5f5); }
.mb b { font-weight: 600; }
"""

_ARROW = ('<div class="flow-arrow"><svg viewBox="0 0 18 18" fill="none" stroke-width="2">'
          '<path d="M3 9h11m-4-4 4 4-4 4"/></svg></div>')


def _node(tag, name, desc, effect):
	return (f'<div class="flow-node"><span class="tag">{tag}</span>'
	        f'<div class="nm">{name}</div><div class="ds">{desc}</div>'
	        f'<div class="fx">{effect}</div></div>')


def _jtable(rows):
	"""Tabel jurnal: rows = [(dokumen, debit, kredit, catatan), ...]."""
	body = "".join(
		f'<tr><td>{d}</td><td>{dr}</td><td>{cr}</td><td class="n">{note}</td></tr>'
		for d, dr, cr, note in rows)
	return ('<table class="j"><tr><th>Dokumen / kejadian</th><th>Debit</th>'
	        f'<th>Kredit</th><th>Catatan</th></tr>{body}</table>')


def _step(no, title, bullets, effect=None):
	lis = "".join(f"<li>{b}</li>" for b in bullets)
	fx = f'<div class="fx">{effect}</div>' if effect else ""
	return (f'<div class="step"><div class="no">{no}</div><div>'
	        f'<div class="st">{title}</div><ul>{lis}</ul>{fx}</div></div>')


# CSS tab (radio + :checked, tanpa JS) dan FAQ (<details> native).
MANUAL_CSS += """
.mb .tabs > input { position: absolute; opacity: 0; pointer-events: none; }
.mb .tabbar { display: flex; gap: 4px; margin: 0 0 20px;
  border-bottom: 1px solid var(--border-color, #dcdcdc); }
.mb .tabbar label { cursor: pointer; padding: 8px 16px; font-weight: 600; font-size: 13.5px;
  border: 1px solid transparent; border-bottom: none; border-radius: 8px 8px 0 0;
  margin-bottom: -1px; opacity: .6; }
.mb .tabbar label:hover { opacity: 1; }
.mb .tabpanes > section { display: none; }
.mb details.faq { border: 1px solid var(--border-color, #dcdcdc); border-radius: 10px;
  padding: 10px 14px; margin-bottom: 8px; background: var(--card-bg, #fff); }
.mb details.faq summary { cursor: pointer; font-weight: 600; }
.mb details.faq > div { margin-top: 8px; font-size: 13.5px; opacity: .85; }
.mb details.faq ul { margin: 6px 0 0; padding-left: 18px; }
"""

MANUAL_CSS += "".join(
	'.mb .tabs > input:nth-of-type(%(i)d):checked ~ .tabbar label:nth-of-type(%(i)d)'
	' { opacity: 1; background: var(--card-bg, #fff); border-color: var(--border-color, #dcdcdc); }'
	'.mb .tabs > input:nth-of-type(%(i)d):checked ~ .tabpanes > section:nth-of-type(%(i)d)'
	' { display: block; }' % {"i": i}
	for i in range(1, 6))


def _tabs(key, panes):
	"""panes = [(judul, html), ...]. Tab pertama aktif. Maks 5 (lihat CSS di atas)."""
	inputs = "".join(
		f'<input type="radio" name="{key}" id="{key}{i}"{" checked" if i == 1 else ""}>'
		for i in range(1, len(panes) + 1))
	bar = "".join(f'<label for="{key}{i}">{t}</label>' for i, (t, _) in enumerate(panes, 1))
	body = "".join(f"<section>{h}</section>" for _, h in panes)
	return (f'<div class="tabs">{inputs}<div class="tabbar">{bar}</div>'
	        f'<div class="tabpanes">{body}</div></div>')


def _page(key, head, roadmap, manual, faq):
	"""Satu halaman manual = judul + 3 tab: Roadmap, Manual Book, FAQ."""
	return ('<div class="mb">' + head
	        + _tabs(key, [("Roadmap", roadmap), ("Manual Book", manual), ("FAQ", faq)])
	        + '</div>')


def _faq(items):
	return "".join(
		f'<details class="faq"><summary>{q}</summary><div>{a}</div></details>' for q, a in items)


# ---------------------------------------------------------------- Manual Trading

TRADING_HEAD = (
	'<h2>Manual Trading — Penjualan Barang Dagang</h2>'
	'<p class="lead">Alur barang dagang keluar, dari order sampai pembayaran. '
	'Stok dan jurnal HPP terjadi di Delivery Note; pendapatan dan piutang di Sales Invoice.</p>'
)

TRADING_ROADMAP = (
	'<div class="flow">'
	+ _node("SO", "Sales Order", "Komitmen penjualan", "Tanpa efek stok / jurnal")
	+ _ARROW
	+ _node("PICK", "Pick List", "Perintah ambil barang di rak", "Tanpa efek stok / jurnal")
	+ _ARROW
	+ _node("DN", "Delivery Note", "Barang keluar gudang", "Stok berkurang. Dr HPP / Cr Persediaan")
	+ _ARROW
	+ _node("SI", "Sales Invoice", "Tagihan ke customer", "Dr Piutang / Cr Penjualan Barang Dagang")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Terima pembayaran", "Dr Bank / Cr Piutang")
	+ '</div>'

	'<div class="box"><div class="bt">Prasyarat</div><ul>'
	'<li>Item bertipe stock (<b>Maintain Stock</b> tercentang) dan stoknya sudah ada di gudang/rak '
	'(barang masuk lewat Purchase Receipt — lihat Manual Buying).</li>'
	'<li>Customer sudah punya <b>Address</b> — wajib saat membuat Sales Invoice.</li>'
	'<li>Harga jual: isi manual di baris item, atau siapkan Item Price.</li>'
	'</ul></div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li>Stok dan <b>HPP</b> terjadi di <b>Delivery Note</b>. Sales Invoice hanya menagih.</li>"
	"<li>Sales Invoice wajib <b>Invoice Type</b>, <b>Type No</b>, <b>Invoice Date</b>, dan"
	" <b>Customer Address</b> — customer tanpa Address tidak bisa ditagih.</li>"
	"<li>Pengiriman dan penagihan boleh bertahap; sisa qty SO tetap terbuka.</li>"
	'</ul></div>'
)

TRADING_MANUAL = (
	_step(1, "Sales Order (SO)", [
		"Buka <b>Selling &gt; Sales Order &gt; + Add Sales Order</b>.",
		"Isi <b>Customer</b> dan <b>Delivery Date</b>.",
		"Tabel <b>Items</b>: pilih item, isi qty dan rate.",
		"Bila kena pajak, isi bagian <b>Tax / PPh / Materai</b>. Kolom <b>Remark</b> untuk catatan.",
		"<b>Save</b>, lalu <b>Submit</b>.",
	], "SO = komitmen penjualan. Belum menyentuh stok maupun jurnal.")

	+ _step(2, "Pick List (perintah ambil barang)", [
		"Dari SO yang sudah submit: <b>Create &gt; Pick List</b>.",
		"Sistem mengisi tabel lokasi: item, <b>rak asal (warehouse)</b>, qty. Periksa raknya.",
		"Qty yang dipick divalidasi tidak boleh melebihi stok rak (alokasi Pick List lain ikut dihitung).",
		"<b>Save</b>, lalu <b>Submit</b>, serahkan ke gudang.",
	])

	+ _step(3, "Delivery Note (DN / surat jalan)", [
		"Dari Pick List yang sudah submit: <b>Create &gt; Delivery Note</b> — rak per baris ikut hasil pick.",
		"Alternatif tanpa Pick List: buat DN langsung dari SO, lalu tombol <b>Suggest Rack</b> "
		"memberi saran rak keluar secara FIFO.",
		"Akun HPP per baris terisi otomatis dari Item Default (fallback Item Group).",
		"<b>Save</b>, lalu <b>Submit</b>.",
	], "Stok berkurang di sini. Jurnal: Dr HPP / Cr Persediaan.")

	+ _step(4, "Sales Invoice (SI)", [
		"Dari DN yang sudah submit: <b>Create &gt; Sales Invoice</b> (bisa juga dari SO).",
		"Wajib isi: <b>Invoice Type = Trading</b>, <b>Invoice Type No</b>, <b>Invoice Date</b>, "
		"<b>Customer Address</b>. Nomor otomatis C/T/####/CMI/YY.",
		"<b>Update Stock</b> dibiarkan kosong — stok sudah keluar lewat DN. "
		"Centang hanya bila menjual tanpa DN.",
		"<b>Save</b>, lalu tekan tombol <b>Validate</b> (workflow CMI — bukan Submit bawaan).",
		"Koreksi: <b>Invalidate</b> kembali ke draft, <b>Void</b> membatalkan — butuh role, dan "
		"ditolak bila SI sudah dirujuk Payment Entry.",
	], "Jurnal: Dr Piutang / Cr Penjualan Barang Dagang.")

	+ _step(5, "Payment Entry (pembayaran)", [
		"Dari SI tervalidasi: <b>Create &gt; Payment</b> — Payment Entry tipe Receive.",
		"Detail lengkap di Manual Payment Entry.",
	], "Jurnal: Dr Bank / Cr Piutang.")

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Pengiriman boleh sebagian (partial): sisa qty SO tetap terbuka dan bisa dibuatkan '
	'Pick List / DN berikutnya.</li>'
	'<li>Progres terlihat dari kolom status di list SO / DN / SI.</li>'
	'</ul></div>'
)

TRADING_FAQ = _faq([
	("Stok tidak berkurang setelah Sales Invoice divalidasi",
	 "Stok dan HPP keluar di <b>Delivery Note</b>, bukan di invoice. Kalau memang menjual tanpa surat"
	 " jalan, centang <b>Update Stock</b> di Sales Invoice — tapi jangan dicentang bila DN-nya sudah"
	 " ada, stok akan terpotong dua kali."),

	("Harus lewat Pick List, atau boleh langsung Delivery Note?",
	 "Pick List opsional. Dari Sales Order bisa langsung <b>Create &gt; Delivery Note</b>, lalu tekan"
	 " <b>Suggest Rack</b> supaya rak asal diisi FIFO. Pick List dipakai bila pengambilan barang"
	 " diserahkan ke petugas gudang lebih dulu."),

	("Akun HPP di baris Delivery Note kosong",
	 "Akun HPP diambil otomatis dari <b>Item Default</b>, lalu <b>Item Group</b>. Kalau tetap kosong"
	 " berarti kedua tempat itu belum diisi untuk company tersebut — isi Default Expense Account di"
	 " Item Group-nya."),

	("Sales Invoice ditolak karena Customer Address",
	 "Customer trading wajib punya record <b>Address</b>. Buat dulu alamatnya dari form Customer"
	 " (Address &amp; Contacts), baru invoice bisa disimpan."),

	("Nomor invoice tidak berformat C/T/####/CMI/YY",
	 "Format nomor mengikuti <b>Invoice Type</b>. Pastikan tipe <b>Trading</b> yang dipilih dan"
	 " <b>Invoice Type No</b> terisi; daftar tipe beserta kode nomornya diatur di Selling Settings."),

	("Salah kirim, DN sudah terlanjur submit",
	 "Belum ada invoice: cancel DN-nya, stok kembali. Sudah ada Sales Invoice: <b>Invalidate</b>"
	 " invoice-nya dulu, baru DN. Barang sudah sampai customer lalu dikembalikan? pakai <b>Sales"
	 " Return</b>, bukan cancel."),

	("Menjual jasa, bukan barang",
	 "Lewati Pick List dan Delivery Note — buat invoice langsung dari Sales Order dengan Invoice Type"
	 " yang sesuai. Tidak ada efek stok maupun HPP."),

	("Harga tidak muncul otomatis di baris item",
	 "Harga jual bisa diisi manual, atau disiapkan sekali lewat <b>Item Price</b> (price list"
	 " penjualan) supaya terisi sendiri setiap kali item dipilih."),
])

TRADING_HTML = _page("tr", TRADING_HEAD, TRADING_ROADMAP, TRADING_MANUAL, TRADING_FAQ)

# ---------------------------------------------------------------- Manual Purchase

PURCHASE_HEAD = (
	'<h2>Manual Purchase — Pembelian</h2>'
	'<p class="lead">Alur pembelian dari order sampai tagihan supplier. '
	'Stok bertambah di Purchase Receipt; hutang supplier resmi terbentuk di Purchase Invoice.</p>'
)

PURCHASE_ROADMAP = (
	'<div class="flow">'
	+ _node("PO", "Purchase Order", "Order ke supplier", "Tanpa efek stok / jurnal")
	+ _ARROW
	+ _node("PR", "Purchase Receipt", "Barang diterima di gudang / rak",
	        "Stok bertambah. Dr Persediaan / Cr Hutang Sementara")
	+ _ARROW
	+ _node("PI", "Purchase Invoice", "Tagihan dari supplier",
	        "Hutang Sementara pindah ke Hutang Usaha supplier")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Bayar supplier", "Dr Hutang Usaha / Cr Bank")
	+ '</div>'

	'<div class="box"><div class="bt">Tipe pembelian — pembedanya SETTING ITEM, bukan tipe PO</div><ul>'
	'<li><b>Stock</b> (barang dagang): item <b>Maintain Stock</b> tercentang. Alur penuh PO - PR - PI.</li>'
	'<li><b>Jasa</b>: item non-stock, expense account Beban Jasa. PO - PI, <b>tanpa PR</b>.</li>'
	'<li><b>Langsung dipakai</b> (ATK, BBM, dll): sama dengan jasa, hanya beda akun beban. PO - PI.</li>'
	'<li><b>Asset</b>: item <b>Is Fixed Asset</b> + Asset Category. PO - PR - PI, record Asset '
	'terbentuk otomatis. (Asset Category belum di-setup di site ini.)</li>'
	'<li><b>Sparepart</b>: item stock ber-expense Beban Sparepart. Baris PR yang diisi <b>Vehicle</b> '
	'otomatis langsung dipakai (Material Issue); baris tanpa Vehicle masuk stok biasa.</li>'
	'</ul></div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li>Yang membedakan kelima tipe pembelian adalah <b>setting Item</b>, bukan tipe PO.</li>"
	"<li>Barang stock lewat <b>Purchase Receipt</b>; jasa dan barang langsung pakai lompat dari PO ke"
	" Purchase Invoice.</li>"
	"<li>Semua koreksi dikerjakan dari <b>PR</b>-nya (Invalidate / Void) — dokumen turunannya ikut"
	" mundur sendiri.</li>"
	'</ul></div>'
)

PURCHASE_MANUAL = (
	_step(1, "Purchase Order (PO)", [
		"Buka <b>Buying &gt; Purchase Order &gt; + Add Purchase Order</b>.",
		"Isi <b>Type</b> (wajib) — untuk pembelian trading pilih <b>TRD</b>.",
		"Isi <b>Supplier</b>, lalu tabel <b>Items</b>: item, qty, rate.",
		"<b>Save</b>, lalu tekan tombol <b>Validate</b>.",
	], "PO = komitmen pembelian. Belum menyentuh stok maupun jurnal.")

	+ _step(2, "Purchase Receipt (PR) — hanya barang stock", [
		"Dari PO tervalidasi: <b>Create &gt; Purchase Receipt</b>.",
		"Per baris pilih <b>Warehouse</b> (gudang) lalu <b>Rack</b> — atau pakai tombol "
		"<b>Suggest Rack</b>: sistem menyarankan rak searah zona item "
		"(konsolidasi ke rak yang sudah berisi item sama, lalu rak paling kosong).",
		"Sparepart yang langsung dipakai: isi <b>Vehicle</b> di barisnya (atau tombol "
		"<b>Set Vehicle</b> untuk semua baris sekaligus) — saat Validate, sistem otomatis membuat "
		"Material Issue sehingga stoknya langsung terpakai.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Stok bertambah per rak. Jurnal: Dr Persediaan / Cr Hutang Usaha Sementara.")

	+ _step(3, "Purchase Invoice (PI)", [
		"Dari PR tervalidasi: <b>Create &gt; Purchase Invoice</b>. "
		"Untuk jasa / non-stock: buat PI langsung dari PO.",
		"Cocokkan dengan tagihan supplier (qty, harga, pajak).",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Hutang supplier resmi terbentuk: Hutang Sementara berpindah ke Hutang Usaha. "
	   "Untuk jasa / non-stock: Dr Beban / Cr Hutang Usaha.")

	+ _step(4, "Payment Entry (pembayaran)", [
		"Dari PI tervalidasi: <b>Create &gt; Payment</b> — Payment Entry tipe Pay.",
		"Detail lengkap di Manual Payment Entry.",
	], "Jurnal: Dr Hutang Usaha / Cr Bank.")

	# ---- kasus khusus: revisi sparepart yang sudah jadi kartu Maintenance ----
	+ '<div class="fh" style="margin-top:28px">Kasus khusus — Revisi Sparepart Maintenance</div>'
	'<p class="lead">Baris PR ber-<b>Vehicle</b> memicu tiga dokumen sekaligus saat Validate. '
	'Kalau isinya salah, semuanya harus mundur bersama — dan itu terjadi otomatis, '
	'ASALKAN koreksinya dilakukan di PR, bukan di dokumen turunannya.</p>'

	'<div class="flow">'
	+ _node("PR", "Purchase Receipt", "Baris diisi Vehicle", "Stok masuk. Dr Persediaan")
	+ _ARROW
	+ _node("SE", "Stock Entry - Material Issue", "Dibuat otomatis, nomor sendiri",
	        "Stok keluar lagi. Dr Beban Kendaraan")
	+ _ARROW
	+ _node("MTC", "Maintenance", "Kartu servis kendaraan, otomatis Validated",
	        "Cermin saja — tidak punya jurnal sendiri")
	+ '</div>'

	'<div class="box warn"><div class="bt">Aturan tunggal yang harus diingat</div><ul>'
	'<li><b>Selalu koreksi dari PR-nya.</b> Jangan membatalkan Stock Entry-nya, dan jangan '
	'mengubah kartu Maintenance-nya. Keduanya sudah dikunci sistem dan akan menolak.</li>'
	'<li>Isi salah, mau diperbaiki &rarr; <b>Invalidate</b> PR.</li>'
	'<li>Memang tidak jadi sama sekali &rarr; <b>Void</b> PR.</li>'
	'</ul></div>'

	+ _step(1, "Salah isi ketahuan — Invalidate PR", [
		"Buka PR-nya, menu <b>...</b> &gt; <b>Invalidate</b>. Butuh izin <b>Validate</b> di "
		"Purchase Receipt (Role Permission Manager).",
		"Yang terjadi otomatis dan serentak: Stock Entry turunannya dibatalkan, stok kembali "
		"seperti sebelum PR dibuat, jurnal PR dihapus, dan kartu Maintenance-nya kembali "
		"<b>belum divalidasi (outstanding)</b>.",
		"PR kembali Draft dengan <b>nomor yang sama</b> dan bisa diedit.",
	], "Kartu Maintenance TIDAK hilang dan TIDAK dapat nomor baru — ia menunggu di status outstanding.")

	+ _step(2, "Perbaiki lalu Validate lagi", [
		"Betulkan yang salah: qty, item, rak, atau kolom <b>Vehicle</b>.",
		"<b>Save</b>, lalu <b>Validate</b> lagi.",
		"Stock Entry <b>baru</b> terbit (nomor baru — yang lama tinggal sebagai jejak Cancelled).",
		"Kartu Maintenance yang tadi outstanding <b>dipakai ulang</b>: isinya ditimpa dengan "
		"angka yang benar, lalu kembali Validated.",
	], "Satu PR + satu kendaraan = satu kartu, berapa kali pun direvisi. Nomor kartu tidak terbakar.")

	+ _step(3, "Kalau memang tidak jadi — Void PR", [
		"Menu <b>...</b> &gt; <b>Void</b>, isi alasannya. Butuh izin <b>Void</b> di Purchase Receipt.",
		"Stock Entry dibatalkan, stok kembali, jurnal PR dibalik (bukan dihapus — jejaknya tinggal).",
		"Kartu Maintenance ditandai <b>Void</b> beserta alasannya, bukan outstanding: "
		"dokumen ini memang batal, bukan menunggu diperbaiki.",
	], "Bedanya dengan Invalidate: PR mati di status Void, tidak bisa diedit lagi.")

	+ '<div class="box"><div class="bt">Kalau ditolak sistem</div><ul>'
	'<li><b>"Batalkan dulu Purchase Invoice terkait: PI/..."</b> &mdash; PR sudah ditagih. '
	'Invalidate PI-nya lebih dulu, baru PR-nya. Kalau PI sudah dibayar, Payment Entry-nya '
	'yang harus dibatalkan paling awal.</li>'
	'<li><b>"Stock Entry ... milik Purchase Receipt ..."</b> &mdash; Anda mencoba membatalkan '
	'Material Issue-nya langsung. Tutup, kerjakan dari PR-nya.</li>'
	'<li><b>"Status Maintenance ... mengikuti Purchase Receipt ..."</b> &mdash; Anda mencoba '
	'mengubah kartunya sendiri. Sama, kerjakan dari PR-nya.</li>'
	'<li>Periode akuntansi sudah ditutup &mdash; pembalikan ditulis di tanggal dokumen aslinya, '
	'jadi bulan itu harus dibuka dulu oleh pemegang izin, atau koreksinya dialihkan ke '
	'Purchase Return di periode berjalan.</li>'
	'</ul></div>'

	+ '<div class="box"><div class="bt">Kapan pakai Purchase Return, bukan Void</div><ul>'
	'<li><b>Salah ketik</b> (qty / item / vehicle keliru) &rarr; Invalidate, perbaiki, Validate. '
	'Bukan Return.</li>'
	'<li><b>Barang tidak pernah datang</b>, atau PR dobel &rarr; Void.</li>'
	'<li><b>Barang benar datang lalu dikembalikan ke supplier</b> &rarr; Purchase Return. '
	'Ini dokumen baru bertanggal hari ini; riwayatnya jujur bahwa barang pernah masuk lalu keluar.</li>'
	'<li>Untuk baris ber-Vehicle, Return jarang cocok: stoknya sudah nol karena langsung dipakai, '
	'jadi tidak ada yang bisa dikembalikan tanpa menerimanya balik dulu.</li>'
	'</ul></div>'

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Penerimaan boleh sebagian (partial): sisa qty PO tetap terbuka untuk PR berikutnya.</li>'
	'<li>Koreksi dokumen: <b>Invalidate</b> kembali ke draft, <b>Void</b> membatalkan — butuh role, '
	'dan ditolak bila dokumen sudah dirujuk dokumen lain (batalkan perujuknya dulu).</li>'
	'<li>Pemakaian sparepart dari stok (bukan saat pembelian) sementara lewat '
	'<b>Stock Entry - Material Issue</b> manual — lihat Manual Stock.</li>'
	'</ul></div>'
)

PURCHASE_FAQ = _faq([
	("Kapan saya perlu Purchase Receipt, kapan tidak?",
	 "Hanya barang <b>stock</b> (dan asset) yang lewat Purchase Receipt. Jasa, ATK, BBM, dan barang"
	 " langsung pakai lompat dari Purchase Order ke Purchase Invoice — PR untuk item non-stock tidak"
	 " berefek apa-apa ke persediaan."),

	("Purchase Order ditolak karena Type kosong",
	 "Field <b>Type</b> (Link ke Purchase Order Type) wajib di CMI. Untuk pembelian barang dagang"
	 " pilih <b>TRD</b>. Tipe ini hanya untuk penomoran dan pengelompokan, tidak mengubah jurnal."),

	("Sparepart dibeli untuk langsung dipasang ke kendaraan",
	 "Isi kolom <b>Vehicle</b> di baris Purchase Receipt-nya (atau tombol <b>Set Vehicle</b> untuk"
	 " semua baris). Saat Validate sistem membuat Material Issue otomatis: stok masuk lalu keluar di"
	 " dokumen yang sama, biaya langsung menempel ke kendaraan."),

	("Invalidate Purchase Receipt ditolak",
	 "Biasanya PR sudah ditagih. Invalidate <b>Purchase Invoice</b>-nya lebih dulu; kalau PI sudah"
	 " dibayar, Payment Entry-nya yang harus dibatalkan paling awal. Urutannya selalu mundur dari"
	 " dokumen terakhir."),

	("Apa itu Hutang Usaha Sementara?",
	 "Akun penampung barang yang <b>sudah diterima tapi belum ditagih</b>. Purchase Receipt"
	 " mengkreditnya, lalu Purchase Invoice memindahkannya ke Hutang Usaha supplier. Saldo yang"
	 " menggantung di akun ini berarti ada PR yang belum dibuatkan PI."),

	("Kolom harga di Purchase Receipt tidak bisa diisi",
	 "Memang disembunyikan: harga mengalir dari Purchase Order / price list supaya tidak berbeda"
	 " dengan yang dipesan. Kalau harga tagihan berbeda, betulkan di Purchase Invoice."),

	("Beda Warehouse dan Rack di baris PR",
	 "<b>Warehouse</b> memilih gudangnya, <b>Rack</b> memilih rak di dalam gudang itu — dan rak inilah"
	 " yang benar-benar dicatat sebagai lokasi stok. Tombol <b>Suggest Rack</b> mengisinya otomatis:"
	 " konsolidasi ke rak yang sudah berisi item sama, dengan menghormati zona Item Group."),

	("Barang datang lebih banyak / lebih sedikit dari PO",
	 "Terima sesuai fisik; sisa qty PO tetap terbuka untuk penerimaan berikutnya. Kelebihan di atas"
	 " toleransi akan ditolak sistem — perbaiki PO-nya dulu bila memang disepakati bertambah."),

	("Beli aset tetap (kendaraan, mesin)",
	 "Alurnya sama (PO - PR - PI) dengan item ber-<b>Is Fixed Asset</b>, tapi setup Asset Category dan"
	 " akun CWIP/Disposal di site ini belum diisi — jadi jalur asset belum bisa dipakai."),
])

PURCHASE_HTML = _page("pu", PURCHASE_HEAD, PURCHASE_ROADMAP, PURCHASE_MANUAL, PURCHASE_FAQ)

# ---------------------------------------------------------------- Manual Payment Entry

PAYMENT_HEAD = (
	'<h2>Manual Payment Entry</h2>'
	'<p class="lead">Semua uang masuk dan keluar bank dicatat lewat Payment Entry. '
	'Nomor otomatis: RV (terima) / PV (bayar) + kode bank + bulan romawi, '
	'contoh RV/MDR/CMI/2026/VII/0003.</p>'
)

PAYMENT_ROADMAP = (
	'<div class="fh">Uang masuk (Receive)</div>'
	'<div class="flow">'
	+ _node("SI", "Sales Invoice", "Tagihan customer tervalidasi", "Piutang outstanding")
	+ _ARROW
	+ _node("PE", "Payment Entry - Receive", "Terima pembayaran customer", "Dr Bank / Cr Piutang")
	+ '</div>'

	'<div class="fh">Uang keluar (Pay)</div>'
	'<div class="flow">'
	+ _node("PI / EN", "Purchase Invoice / Expense Note", "Hutang supplier / vendor",
	        "Hutang outstanding")
	+ _ARROW
	+ _node("PE", "Payment Entry - Pay", "Bayar hutang", "Dr Hutang / Cr Bank")
	+ '</div>'

	'<div class="box warn"><div class="bt">Penting — pembayaran di luar IDR (valas)</div><ul>'
	'<li>Mata uang Payment Entry mengikuti <b>rekening bank</b> yang dipilih. '
	'Mau bayar/terima dalam USD atau mata uang lain? <b>Pilih rekening bank non-IDR itu '
	'DI AWAL</b> (Account Paid From / Paid To), sebelum mengisi yang lain.</li>'
	'<li>Kalau rekeningnya baru diganti belakangan, nominal dan alokasi yang sudah terisi '
	'ikut kacau — lebih aman mulai dari Payment Entry baru.</li>'
	'<li>Langkah lengkapnya di langkah 4 di bawah.</li>'
	'</ul></div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li><b>Rekening bank yang dipilih menentukan mata uang</b> pembayaran — untuk valas, pilih"
	" rekeningnya lebih dulu, sebelum mengisi yang lain.</li>"
	"<li>Kata pertama nama akun bank jadi kode nomor dokumen (RV/MDR/...).</li>"
	"<li>Potongan (Tax, PPh, Materai, Admin, CN/DN) punya akunnya sendiri di ERPNext Custom Setting —"
	" bukan dikurangkan diam-diam dari nominal.</li>"
	'</ul></div>'
)

PAYMENT_MANUAL = (
	_step(1, "Terima pembayaran customer (Receive)", [
		"Dari Sales Invoice tervalidasi: <b>Create &gt; Payment</b> — tipe Receive terisi otomatis.",
		"Periksa <b>Account Paid To</b> (rekening bank penerima) dan alokasi per invoice "
		"di tabel References.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Jurnal: Dr Bank / Cr Piutang. Outstanding SI berkurang.")

	+ _step(2, "Bayar Purchase Invoice (Pay)", [
		"Dari Purchase Invoice tervalidasi: <b>Create &gt; Payment</b> — tipe Pay.",
		"Periksa <b>Account Paid From</b> (rekening bank sumber) dan alokasi di References.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Jurnal: Dr Hutang Usaha / Cr Bank. Outstanding PI berkurang.")

	+ _step(3, "Bayar Expense Note vendor", [
		"Buat Payment Entry baru: tipe <b>Pay</b>, Party Type <b>Supplier</b>, pilih vendornya.",
		"Tekan tombol <b>Tarik Expense Note</b> — EN outstanding vendor itu masuk sebagai "
		"baris pembayaran, alokasikan nominalnya.",
		"Potongan / tambahan (Tax, PPh, Materai, Admin, CN/DN) diisi di field-nya — otomatis "
		"dijurnalkan ke akun yang di-set di ERPNext Custom Setting.",
		"EN valas (mis. USD): lihat langkah 4.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Jurnal: Dr Hutang vendor (dari jurnal EN) / Cr Bank, plus baris potongan.")

	+ _step(4, "Pembayaran valas (di luar IDR)", [
		"Buat Payment Entry baru tipe <b>Pay</b>, pilih Party seperti biasa.",
		"<b>Sebelum mengisi yang lain</b>: pilih <b>Account Paid From</b> = rekening bank "
		"valas (mata uang bukan IDR). Mata uang pembayaran otomatis mengikuti rekening ini.",
		"Isi <b>kurs</b> (exchange rate) sesuai kurs transaksi / bank.",
		"Tarik tagihannya seperti biasa (mis. <b>Tarik Expense Note</b>) dan alokasikan — "
		"hutang tercatat dalam IDR, dibayar dalam valas memakai kurs tadi.",
		"Selisih antara kurs bayar dan kurs buku dijurnalkan otomatis ke akun "
		"<b>Selisih Kurs</b>.",
		"Potongan / tambahan (Tax, PPh, Materai, Admin, CN/DN) tetap bisa diisi seperti biasa.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Jurnal: Dr Hutang @kurs buku / Cr Bank valas @kurs bayar, selisihnya ke Selisih Kurs.")

	+ _step(5, "Bayar pakai Pending Cash (kasbon) sebagai sumber dana", [
		"Di Payment Entry tipe Pay: section <b>Pending Cash</b>, tekan <b>Add Pending Cash</b>.",
		"Pilih Pending Cash yang sudah <b>Paid</b>, isi nominal yang dipakai (allocated).",
		"Sisi kredit memakai akun uang muka dari jurnal kasbon itu; kelebihan di atas "
		"uang muka tetap keluar dari bank.",
	], "Jurnal: Dr Hutang / Cr Uang Muka (dan Cr Bank untuk sisanya).")

	+ _step(6, "Biaya / pendapatan langsung tanpa tagihan (Expense / Income)", [
		"Centang <b>Expense / Income</b> — tanpa party, tanpa tarikan dokumen.",
		"Isi tabel <b>Items</b>: catatan, akun, nominal per baris. Penerima/pengirim "
		"dicatat di field <b>Pay To</b>.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Pay: Dr tiap akun item / Cr Bank. Receive: Dr Bank / Cr tiap akun item.")

	+ _step(7, "Settlement — pelunasan tanpa lewat bank", [
		"Dipakai saat pelunasan tidak menyentuh rekening bank: lewat akun perantara, "
		"mis. offset hutang-piutang atau pelunasan antar dokumen.",
		"Buat Payment Entry (Pay / Receive) dan pilih Party seperti biasa.",
		"Tarik transaksinya seperti biasa: alokasi invoice di tabel <b>References</b>, "
		"atau tombol <b>Tarik Expense Note</b> untuk EN vendor.",
		"Pilih <b>Mode of Payment = Settlement</b>, lalu isi <b>Settlement Account</b> "
		"(akun pengganti sisi bank) — wajib, Save ditolak bila kosong.",
		"Nomor dokumen tetap RV/PV; kode banknya diambil dari nama akun settlement.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "Jurnal: Pay = Dr Hutang / Cr Settlement Account; Receive = Dr Settlement Account "
	   "/ Cr Piutang. Bank tidak tersentuh. Contoh offset: hutang vendor dan piutang "
	   "customer yang sama ditutup dengan dua PE ke akun settlement yang sama.")

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Koreksi: <b>Invalidate</b> kembali ke draft, <b>Void</b> membatalkan — butuh role.</li>'
	'</ul></div>'
)

PAYMENT_FAQ = _faq([
	("Mata uang Payment Entry salah / tidak bisa diubah",
	 "Mata uang mengikuti <b>rekening bank</b> (Account Paid From / Paid To). Pilih rekening valas"
	 " <b>di awal</b>, sebelum mengisi nominal dan alokasi. Kalau rekening baru diganti belakangan,"
	 " isian yang sudah ada ikut kacau — lebih aman mulai dari Payment Entry baru."),

	("Invoice tidak muncul saat mau dialokasikan",
	 "Syaratnya: dokumennya sudah <b>Validated</b>, party-nya sama, dan masih punya outstanding."
	 " Expense Note tidak muncul di tabel References — tariknya lewat tombol <b>Tarik Expense Note</b>."),

	("Potongan PPh / PPN / materai dicatat ke mana?",
	 "Ke akun yang di-set di <b>ERPNext Custom Setting</b>, otomatis sebagai baris jurnal tersendiri."
	 " Jadi nominal bank berkurang sesuai yang benar-benar ditransfer, sementara hutangnya tetap"
	 " tertutup penuh."),

	("Bayar vendor expedition (Expense Note)",
	 "Payment Entry tipe <b>Pay</b>, Party Type Supplier, lalu tombol <b>Tarik Expense Note</b>. EN"
	 " outstanding vendor itu masuk sebagai baris pembayaran yang tinggal dialokasikan."),

	("Pelunasan tanpa lewat bank (offset hutang-piutang)",
	 "Pakai <b>Mode of Payment = Settlement</b> lalu isi <b>Settlement Account</b> (wajib). Sisi bank"
	 " digantikan akun itu, sehingga hutang dan piutang bisa saling ditutup tanpa uang bergerak."),

	("Bayar memakai kasbon yang sudah cair",
	 "Section <b>Pending Cash</b> &gt; <b>Add Pending Cash</b>, pilih kasbon berstatus <b>Paid</b>."
	 " Sisi kredit memakai akun uang muka kasbon; kelebihan di atas uang muka tetap keluar dari bank."),

	("Dari mana nomor RV/MDR/CMI/2026/VII/0001?",
	 "RV untuk terima, PV untuk bayar; <b>MDR</b> diambil dari kata pertama nama akun banknya, lalu"
	 " company, tahun, dan bulan romawi. Jadi penamaan akun bank menentukan nomor dokumen."),

	("Satu transfer membayar beberapa invoice",
	 "Boleh: tambahkan beberapa baris di tabel References dan bagi nominalnya. Total alokasi harus"
	 " sama dengan nominal yang dibayar setelah potongan."),

	("Salah bayar, sudah tervalidasi",
	 "<b>Invalidate</b> mengembalikannya ke draft untuk diperbaiki, <b>Void</b> membatalkan. Keduanya"
	 " butuh role dan akan ditolak bila dokumen ini sudah dirujuk dokumen lain."),
])

PAYMENT_HTML = _page("pa", PAYMENT_HEAD, PAYMENT_ROADMAP, PAYMENT_MANUAL, PAYMENT_FAQ)

# ---------------------------------------------------------------- Manual Pending Cash

PENDING_CASH_HEAD = (
	'<h2>Manual Pending Cash — Kasbon</h2>'
	'<p class="lead">Uang muka tunai yang diserahkan ke penerima sebelum ada bukti biaya. '
	'Nomor otomatis PC/TIPE/COMPANY/TAHUN/####, contoh PC/JOB/CMI/26/0001.</p>'
)

PENDING_CASH_ROADMAP = (
	'<div class="flow">'
	+ _node("DRAFT", "Draft", "Input kasbon", "Tanpa efek jurnal")
	+ _ARROW
	+ _node("VAL", "Validated", "Disetujui, isi terkunci", "Tanpa efek jurnal")
	+ _ARROW
	+ _node("PAID", "Paid", "Uang diserahkan", "Dr Uang Muka / Cr Bank")
	+ _ARROW
	+ _node("PE", "Dipakai di Payment Entry", "Membayar hutang / tagihan",
	        "Hutang ditutup dengan mengkredit Uang Muka")
	+ '</div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li>Jurnal baru terbit saat status <b>Paid</b> — Draft dan Validated belum menyentuh uang.</li>"
	"<li>Akun uang muka diambil dari <b>Pending Cash Type</b>, bukan diisi per dokumen.</li>"
	"<li>Kasbon yang sudah ditarik ke Payment Entry tidak bisa di-Unpaid — lepas dulu barisnya di"
	" sana.</li>"
	'</ul></div>'
)

PENDING_CASH_MANUAL = (
	_step(1, "Buat Pending Cash", [
		"Buka <b>Payments &gt; Pending Cash &gt; + Add Pending Cash</b>.",
		"Isi <b>Type</b> (menentukan akun uang muka), <b>Pay To</b> (penerima), "
		"<b>Total</b>, <b>Bank Account</b>, dan <b>Cost Center</b>.",
		"Opsional: section <b>Connection</b> menautkan kasbon ke dokumen job "
		"(Shipping List / Packing List / SO / PO).",
		"<b>Save</b>.",
	])

	+ _step(2, "Validate (persetujuan)", [
		"Tekan <b>Validate</b> — dokumen disetujui dan isinya terkunci.",
		"Setelah Validated hanya <b>Bank Account</b> yang masih boleh direvisi.",
		"Salah isi? <b>Invalidate</b> mengembalikan ke Draft (harus Unpaid dulu bila sudah Paid).",
	], "Belum ada jurnal — uangnya belum keluar.")

	+ _step(3, "Pay (uang diserahkan)", [
		"Tekan <b>Pay</b>, isi tanggal bayar dan catatan bila perlu.",
		"Sistem membuat Journal Entry otomatis dari akun uang muka Type-nya.",
		"Salah input? <b>Unpaid</b>: jurnal dibatalkan dan dihapus, dokumen kembali "
		"Validated. Ditolak bila kasbonnya sudah ditarik ke Payment Entry — lepas dulu "
		"barisnya di sana.",
	], "Jurnal: Dr Akun Uang Muka (terurai per penerima bila akunnya Receivable) / Cr Bank.")

	+ _step(4, "Pakai untuk membayar (di Payment Entry)", [
		"Di Payment Entry tipe Pay: section <b>Pending Cash</b> &gt; <b>Add Pending Cash</b>, "
		"pilih kasbon ber-status Paid dan isi nominal yang dipakai.",
		"Lihat detail di Manual Payment Entry langkah 5.",
	], "Hutang dibayar dengan mengkredit akun uang muka kasbon; kelebihannya dari bank.")

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li><b>Void</b> membatalkan dokumen (jurnal ikut dibatalkan tapi dibiarkan sebagai jejak); '
	'<b>Unvoid</b> mengaktifkan lagi — yang sudah Paid mendapat jurnal baru.</li>'
	'<li>Semua aksi bisa massal dari list view lewat menu <b>Actions</b>.</li>'
	'<li>Realisasi / pertanggungjawaban kasbon (bukti biaya + kembalian) belum ada — '
	'sementara pemakaiannya lewat Payment Entry.</li>'
	'</ul></div>'
)

PENDING_CASH_FAQ = _faq([
	("Kapan pakai kasbon, kapan bayar langsung?",
	 "Kasbon dipakai saat uang harus diserahkan <b>sebelum</b> ada bukti biaya (uang jalan,"
	 " operasional job). Kalau tagihannya sudah ada, bayar langsung lewat Payment Entry."),

	("Sudah Validate tapi belum ada jurnal",
	 "Memang belum: jurnal baru terbit saat ditekan <b>Pay</b>, karena saat itulah uang keluar dari"
	 " bank. Draft dan Validated hanya soal persetujuan."),

	("Unpaid ditolak",
	 "Kasbonnya sudah ditarik ke Payment Entry. Lepas dulu barisnya di Payment Entry itu, baru kasbon"
	 " bisa di-Unpaid."),

	("Akun uang muka diambil dari mana?",
	 "Dari <b>Pending Cash Type</b> yang dipilih (field Advance Account), bukan diisi per dokumen."
	 " Type juga menentukan format nomor PC/TIPE/COMPANY/YY/####."),

	("Beda Invalidate dan Void",
	 "<b>Invalidate</b> mengembalikan ke Draft untuk diperbaiki (harus Unpaid dulu bila sudah cair)."
	 " <b>Void</b> membatalkan dokumen — jurnalnya ikut dibatalkan tapi dibiarkan sebagai jejak, dan"
	 " bisa diaktifkan lagi lewat <b>Unvoid</b>."),

	("Mempertanggungjawabkan kasbon (bukti biaya + kembalian)",
	 "Belum ada dokumen realisasi khusus. Sementara ini pemakaiannya lewat Payment Entry: kasbon"
	 " ditarik untuk membayar tagihan, sisanya tetap menggantung di akun uang muka."),

	("Memproses banyak kasbon sekaligus",
	 "Dari list view: centang barisnya lalu menu <b>Actions</b> — Validate, Pay, dan aksi lain bisa"
	 " dijalankan massal."),

	("Menghubungkan kasbon ke job tertentu",
	 "Section <b>Connection</b> di form kasbon: tautkan ke Shipping List, Packing List, Sales Order,"
	 " atau Purchase Order supaya biayanya bisa ditelusuri per job."),
])

PENDING_CASH_HTML = _page("pc", PENDING_CASH_HEAD, PENDING_CASH_ROADMAP, PENDING_CASH_MANUAL, PENDING_CASH_FAQ)

# ---------------------------------------------------------------- Manual Expedition

EXPEDITION_HEAD = (
	'<h2>Manual Expedition</h2>'
	'<p class="lead">Alur job expedition: dokumen job, biaya vendor, tagihan ke customer, '
	'lalu pembayaran dua arah (bayar vendor, terima customer).</p>'
)

EXPEDITION_ROADMAP = (
	'<div class="flow">'
	+ _node("JOB", "Shipping List / Packing List", "Dokumen job per shipment",
	        "Tanpa efek jurnal; status bayar per BL terpantau")
	+ _ARROW
	+ _node("EN", "Expense Note", "Biaya vendor per job",
	        "Dr Biaya (reimburse: akun Reimbursement) / Cr Hutang Vendor")
	+ _ARROW
	+ _node("SI", "Sales Invoice", "Tagihan ke customer",
	        "Dr Piutang / Cr Pendapatan Jasa atau Reimbursement")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Bayar vendor, terima customer", "Lihat Manual Payment")
	+ '</div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li><b>Expense Note</b> yang menjurnal biaya vendor (saat Validate), bukan dokumen job-nya.</li>"
	"<li>Biaya yang ditagih ulang ke customer harus dicentang <b>Reimburse to Customer</b> —"
	" jurnalnya masuk akun Reimbursement, bukan biaya perusahaan.</li>"
	"<li>Sales Invoice reimburse adalah <b>pass-through</b>, bukan pendapatan; pendapatannya hanya"
	" dari baris Markup.</li>"
	'</ul></div>'
)

EXPEDITION_MANUAL = (
	_step(1, "Dokumen job", [
		"<b>Shipping List</b>: satu dokumen per shipment — isi BL dan container. "
		"Status pembayaran tiap BL (invoice masuk maupun Expense Note keluar) "
		"terpantau otomatis di tabel BL-nya.",
		"<b>Packing List</b>: job barang dengan rincian item.",
		"Dokumen lain (EN, SI, Pending Cash) menaut ke job lewat section <b>Connection</b>.",
	])

	+ _step(2, "Expense Note (EN) — biaya vendor", [
		"Buka <b>Expedition &gt; Expense Note &gt; + Add</b>. Isi <b>Type</b> "
		"(menentukan nomor EXP/TIPE/COMPANY/YY) dan <b>Supplier</b> (vendor).",
		"Isi biaya lewat panel <b>Biaya per Expense Class</b> — per expense class dan "
		"per container; tabel Items terisi otomatis dari panel.",
		"Isi <b>PPN / PPh / Discount / Materai</b> bila ada.",
		"Biaya yang akan ditagihkan ulang ke customer: centang <b>Reimburse to Customer</b> "
		"dan pilih Customer-nya.",
		"<b>Save</b>, lalu <b>Validate</b> — Journal Entry terbentuk otomatis.",
	], "Jurnal: Dr Akun Biaya per baris (EN reimburse: akun Reimbursement) / Cr Hutang Vendor.")

	+ _step(3, "Sales Invoice — tagihan ke customer", [
		"Tipe invoice dipilih di field <b>Invoice Type</b> (daftarnya dikonfigurasi di "
		"Selling Settings, per tipe ada Behavior, Type No, dan role yang boleh memakai).",
		"Behavior <b>Normal</b> (jasa expedition): isi baris jasa di Items — income mengikuti "
		"akun tipe invoice.",
		"Behavior <b>Reimburse</b>: tombol <b>Get Expense Notes</b> menarik EN reimburse "
		"customer itu (pass-through, bukan pendapatan). Checkbox <b>Markup</b> membuka tabel "
		"Items untuk baris jasa tambahan — jurnalnya per item.",
		"Wajib: Invoice Type, Invoice Type No, Invoice Date, Customer Address.",
		"<b>Save</b>, lalu <b>Validate</b>.",
	], "EN yang sudah ditarik ke invoice reimburse terkunci — lepas dari invoice dulu untuk revisi.")

	+ _step(4, "Pembayaran", [
		"Bayar vendor: Payment Entry tipe Pay + tombol <b>Tarik Expense Note</b> "
		"(lihat Manual Payment Entry langkah 3; pembayaran valas di langkah 4).",
		"Terima dari customer: dari SI, <b>Create &gt; Payment</b> "
		"(lihat Manual Payment Entry langkah 1).",
		"Kasbon operasional job: lihat Manual Pending Cash.",
	])
)

EXPEDITION_FAQ = _faq([
	("Tabel Items di Expense Note kosong padahal biaya sudah diisi",
	 "Biaya diisi lewat panel <b>Biaya per Expense Class</b> (per class dan per container); panel"
	 " itulah yang menulis ke tabel Items. Jangan mengetik langsung di tabel."),

	("Kapan centang Reimburse to Customer?",
	 "Bila biaya itu akan <b>ditagihkan ulang</b> ke customer. Jurnalnya jadi akun Reimbursement"
	 " (titipan), bukan biaya perusahaan, dan EN-nya baru bisa ditarik ke invoice reimburse."),

	("Tombol Get Expense Notes tidak menarik apa-apa",
	 "EN yang ditarik harus: sudah <b>Validated</b>, dicentang Reimburse to Customer, customer-nya"
	 " sama dengan invoice, dan belum ditarik invoice lain."),

	("Mau merevisi Expense Note yang sudah masuk invoice",
	 "EN terkunci selama masih ditarik invoice reimburse. Lepas dulu barisnya dari Sales Invoice (atau"
	 " Invalidate invoice-nya), baru EN bisa di-Invalidate dan diperbaiki."),

	("Apa gunanya checkbox Markup?",
	 "Membuka tabel Items di invoice reimburse untuk baris jasa tambahan (keuntungan). Biaya titipan"
	 " tetap pass-through, sementara baris markup dijurnalkan per item sebagai pendapatan."),

	("Bayar vendor dalam USD",
	 "Payment Entry tipe Pay, pilih <b>rekening bank valas lebih dulu</b>, isi kurs, baru tarik"
	 " EN-nya. Hutang tercatat IDR, selisih kursnya masuk akun Selisih Kurs otomatis."),

	("Uang jalan / operasional job",
	 "Pakai <b>Pending Cash</b> dan tautkan ke job lewat section Connection; pemakaiannya nanti"
	 " ditarik di Payment Entry."),

	("Status pembayaran per BL",
	 "Terpantau otomatis di tabel BL pada Shipping List — baik tagihan masuk maupun Expense Note"
	 " keluar, tanpa perlu diperbarui manual."),

	("Nomor Expense Note berubah-ubah polanya",
	 "Nomor mengikuti field <b>Type</b>: EXP/TIPE/COMPANY/YY. Tipe yang berbeda memang menghasilkan"
	 " seri nomor yang berbeda."),
])

EXPEDITION_HTML = _page("ex", EXPEDITION_HEAD, EXPEDITION_ROADMAP, EXPEDITION_MANUAL, EXPEDITION_FAQ)

# ---------------------------------------------------------------- Manual Selling

SELLING_HEAD = (
	'<h2>Manual Selling — Penjualan</h2>'
	'<p class="lead">Alur penjualan umum. Untuk penjualan barang dagang lengkap sampai '
	'gudang, lihat Manual Trading; untuk tagihan job expedition, lihat Manual Expedition.</p>'
)

SELLING_ROADMAP = (
	'<div class="flow">'
	+ _node("QTN", "Quotation", "Penawaran harga (opsional)", "Tanpa efek jurnal")
	+ _ARROW
	+ _node("SO", "Sales Order", "Order customer", "Tanpa efek stok / jurnal")
	+ _ARROW
	+ _node("DN", "Delivery Note", "Kirim barang (khusus barang)", "Stok keluar. Dr HPP / Cr Persediaan")
	+ _ARROW
	+ _node("SI", "Sales Invoice", "Tagihan", "Dr Piutang / Cr Pendapatan")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Terima pembayaran", "Dr Bank / Cr Piutang")
	+ '</div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li><b>Invoice Type</b> menentukan akun pendapatan, format nomor, dan siapa yang boleh"
	" memakainya — bukan dipilih bebas.</li>"
	"<li>Barang stock wajib lewat Delivery Note (atau Update Stock di SI); penjualan jasa langsung"
	" dari SO ke invoice.</li>"
	"<li>Penawaran tim sales dikelola di aplikasi <b>CRM</b>, terpisah dari Quotation modul ini.</li>"
	'</ul></div>'
)

SELLING_MANUAL = (
	_step(1, "Quotation (opsional)", [
		"Buka <b>Selling &gt; Quotation &gt; + Add</b>: customer, item, harga, masa berlaku.",
		"Deal? <b>Create &gt; Sales Order</b> — isi quotation terbawa.",
		"Penawaran dari tim sales/CRM dikelola di aplikasi CRM (Inquiry - Quotation - "
		"Estimation), terpisah dari modul ini.",
	])

	+ _step(2, "Sales Order (SO)", [
		"Isi <b>Customer</b>, <b>Delivery Date</b>, tabel <b>Items</b> (item, qty, rate).",
		"Pajak diisi lewat field <b>Tax / PPh / Materai</b> — detail pajak native diisi "
		"otomatis oleh sistem dari field ini.",
		"<b>Save</b>, lalu <b>Submit</b>.",
	])

	+ _step(3, "Pengiriman (khusus barang stock)", [
		"Pick List lalu Delivery Note — langkah lengkapnya di Manual Trading langkah 2-3.",
		"Penjualan jasa: lewati langkah ini, langsung buat invoice dari SO.",
	])

	+ _step(4, "Sales Invoice (SI)", [
		"Dari DN atau SO: <b>Create &gt; Sales Invoice</b>.",
		"Pilih <b>Invoice Type</b> sesuai transaksi (Trading untuk barang dagang; daftar tipe "
		"plus nomor dan role-nya dikonfigurasi di Selling Settings tab Invoice Type).",
		"Wajib: Invoice Type, Invoice Type No, Invoice Date, Customer Address.",
		"<b>Save</b>, lalu <b>Validate</b> (bukan Submit bawaan).",
	], "Jurnal: Dr Piutang / Cr akun pendapatan sesuai tipe invoice / item.")

	+ _step(5, "Payment Entry", [
		"Dari SI tervalidasi: <b>Create &gt; Payment</b> — detail di Manual Payment.",
	], "Jurnal: Dr Bank / Cr Piutang.")

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Harga default per item bisa disiapkan lewat <b>Item Price</b>.</li>'
	'<li>Form SO / DN sengaja berhenti di Remark — metadata native setelahnya disembunyikan '
	'tapi tetap diisi sistem.</li>'
	'<li>Pengiriman dan penagihan boleh sebagian; status SO memantau sisa qty dan tagihan.</li>'
	'</ul></div>'
)

SELLING_FAQ = _faq([
	("Bedanya Manual Selling dan Manual Trading",
	 "Manual Selling menjelaskan alur umum penjualan (termasuk jasa). Manual Trading adalah versi"
	 " lengkap untuk barang dagang, sampai pengambilan barang di rak. Tagihan job expedition punya"
	 " manualnya sendiri."),

	("Quotation dari tim sales tidak kelihatan di sini",
	 "Penawaran tim sales dikelola di aplikasi <b>CRM</b> (Inquiry - Quotation - Estimation), database"
	 " dan formnya terpisah dari Quotation modul Selling ini."),

	("Pajak diisi di mana?",
	 "Cukup isi field <b>Tax / PPh / Materai</b> di dokumennya. Tabel pajak native ERPNext diisi"
	 " sistem dari field itu, jadi tidak perlu disentuh."),

	("Invoice Type yang saya butuhkan tidak muncul",
	 "Tiap tipe punya daftar <b>Roles</b> yang boleh memakainya, dan tipe yang disabled tidak"
	 " ditampilkan. Aturnya di <b>Selling Settings &gt; tab Invoice Type</b>."),

	("Sales Order tidak bisa dibuatkan invoice lagi",
	 "Berarti seluruh qty-nya sudah tertagih (status billed penuh). Cek kolom status di SO; kalau"
	 " memang ada tagihan tambahan, buat invoice tersendiri."),

	("Form berhenti di Remark, field standar ERPNext hilang",
	 "Disengaja: metadata native setelah Remark disembunyikan supaya form ringkas. Isinya tetap diisi"
	 " sistem dan tetap ikut ke laporan."),

	("Kirim dan tagih sebagian",
	 "Boleh. Satu Sales Order bisa punya beberapa Delivery Note dan beberapa Sales Invoice; sisa qty"
	 " dan sisa tagihan terpantau di status SO."),
])

SELLING_HTML = _page("se", SELLING_HEAD, SELLING_ROADMAP, SELLING_MANUAL, SELLING_FAQ)

# ---------------------------------------------------------------- Manual Stock

STOCK_ROADMAP = (
	'<div class="fh">Alur utama — barang masuk, disimpan, keluar, tertagih</div>'
	'<div class="flow">'
	+ _node("PO", "Purchase Order", "Order ke supplier (Type TRD)", "Tanpa efek stok / jurnal")
	+ _ARROW
	+ _node("PR", "Purchase Receipt", "Barang diterima, pilih gudang lalu rak",
	        "Stok bertambah. Dr Persediaan / Cr Hutang Sementara")
	+ _ARROW
	+ _node("STOK", "Stok per Rak", "Duduk di gudang, terpantau Stock Balance / Ledger",
	        "Nilainya di akun persediaan menurut Item Group")
	+ _ARROW
	+ _node("DN", "Delivery Note", "Barang keluar dijual (Suggest Rack, FIFO)",
	        "Stok berkurang. Dr HPP / Cr Persediaan")
	+ _ARROW
	+ _node("SI", "Sales Invoice", "Tagihan ke customer",
	        "Dr Piutang / Cr Penjualan Barang Dagang")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Terima pembayaran", "Dr Bank / Cr Piutang")
	+ '</div>'

	'<div class="fh">Cabang lain dari stok</div>'
	'<div class="flow">'
	+ _node("SE", "Material Issue", "Dipakai sendiri, tidak dijual",
	        "Stok berkurang. Dr Beban item / Cr Persediaan")
	+ _node("SE", "Material Transfer", "Pindah antar rak / gudang",
	        "Nilai ikut pindah, tanpa efek laba rugi")
	+ _node("SR", "Stock Reconciliation", "Opname / koreksi hasil hitung fisik",
	        "Selisih ke akun Penyesuaian Persediaan")
	+ _node("MTC", "Maintenance", "Sparepart dipasang ke kendaraan",
	        "Material Issue terbit sendiri saat Validate")
	+ '</div>'

	'<div class="fh">Jalur pintas yang sah</div>'
	+ '<div class="box"><ul>'
	'<li><b>Sparepart beli-langsung-pakai</b>: baris Purchase Receipt yang diisi <b>Vehicle</b> '
	'masuk dan keluar di dokumen yang sama — stok net nol, biaya langsung ke kendaraan.</li>'
	'<li><b>Jual tanpa Delivery Note</b>: centang <b>Update Stock</b> di Sales Invoice, '
	'stok dan HPP terjadi di SI. Dipakai hanya bila memang tidak ada surat jalan.</li>'
	'<li><b>Barang non-stock</b> (jasa, ATK, BBM): tidak lewat gudang sama sekali — '
	'PO langsung ke Purchase Invoice.</li>'
	'</ul></div>'

	+ '<div class="fh">Jurnal yang terbentuk di sepanjang jalur</div>'
	+ _jtable([
		("Purchase Receipt", "Persediaan (menurut Item Group)", "Hutang Usaha Sementara",
		 "Stok bertambah per rak"),
		("Purchase Invoice", "Hutang Usaha Sementara", "Hutang Usaha", "Hutang supplier resmi"),
		("Delivery Note", "HPP", "Persediaan", "HPP diakui di sini, bukan di Sales Invoice"),
		("Sales Invoice", "Piutang", "Penjualan Barang Dagang", ""),
		("Payment Entry", "Bank", "Piutang", ""),
		("Stock Entry — Material Issue", "Beban item", "Persediaan",
		 "Termasuk sparepart ber-Vehicle"),
		("Stock Entry — Material Transfer", "—", "—",
		 "Nilai pindah rak, tanpa jurnal laba rugi"),
		("Stock Reconciliation", "Persediaan / Penyesuaian", "Penyesuaian / Persediaan",
		 "Arah ikut selisih fisik"),
	])

	+ '<div class="box warn"><div class="bt">Tiga hal yang menentukan segalanya</div><ul>'
	'<li>Stok hanya berubah di <b>Purchase Receipt</b>, <b>Delivery Note</b>, '
	'<b>Stock Entry</b>, dan <b>Stock Reconciliation</b>. Dokumen lain (PO, SO, Pick List) '
	'cuma komitmen.</li>'
	'<li>Akun persediaan ikut <b>jenis barang (Item Group)</b>, bukan gudang tempatnya '
	'disimpan — jadi satu rak boleh dicampur.</li>'
	'<li><b>Rak = warehouse</b>. Semua laporan stok otomatis rinci sampai rak, '
	'tanpa modul tambahan.</li>'
	'</ul></div>'
)

STOCK_FAQ = _faq([
	("Kenapa stok tidak berkurang waktu saya Validate Sales Invoice?",
	 "Stok keluar di <b>Delivery Note</b>, bukan di invoice — begitu juga jurnal HPP-nya. "
	 "Invoice hanya menagih. Kalau memang menjual tanpa surat jalan, centang "
	 "<b>Update Stock</b> di Sales Invoice; jangan dicentang bila DN-nya sudah ada, "
	 "nanti stok terpotong dua kali."),

	("Muncul pesan \"Please set default inventory account for item ...\"",
	 "Item Group barang itu belum punya <b>Default Inventory Account</b>. Sistem ini "
	 "sengaja tidak punya cadangan, jadi transaksinya ditolak sampai diisi. "
	 "Buka <b>Stock &gt; Item Group</b> &gt; tabel Item Defaults &gt; baris company &gt; isi akunnya. "
	 "Ragu? isi <b>1130.003 Persediaan Umum</b>, itu perilaku lama dan aman."),

	("Stoknya jelas ada, tapi Delivery Note bilang stok kurang",
	 "Stok dihitung <b>per rak</b>, bukan per gudang. Barangnya kemungkinan di rak lain. "
	 "Pakai tombol <b>Suggest Rack</b> di DN (FIFO, otomatis memecah baris bila satu rak "
	 "tidak cukup), atau cek <b>Stock Balance</b> untuk melihat rak mana yang berisi. "
	 "Mau dikumpulkan dulu? Stock Entry <b>Material Transfer</b>."),

	("Sparepart untuk kendaraan dicatat lewat mana?",
	 "Dua jalur, jangan dicampur:<ul>"
	 "<li><b>Baru dibeli dan langsung dipasang</b>: isi kolom <b>Vehicle</b> di baris "
	 "Purchase Receipt. Material Issue terbit otomatis saat Validate.</li>"
	 "<li><b>Diambil dari stok gudang</b>: lewat <b>Fleet &gt; Maintenance</b>. "
	 "Stock Entry-nya juga terbit sendiri.</li></ul>"
	 "Material Issue manual dipakai untuk pemakaian lain, bukan untuk sparepart kendaraan."),

	("Salah input Purchase Receipt yang sudah terlanjur bikin Material Issue",
	 "Kerjakan dari <b>PR-nya</b>: menu ... &gt; <b>Invalidate</b> (mau diperbaiki) atau "
	 "<b>Void</b> (memang batal). Stock Entry dan kartu Maintenance-nya ikut mundur sendiri. "
	 "Membatalkan Stock Entry-nya langsung akan ditolak sistem."),

	("Saldo akun persediaan di GL beda dengan Stock Balance",
	 "Yang biasa jadi biang: (1) ada dokumen stok yang masih draft atau baru di-void, "
	 "(2) tanggal laporan beda, (3) item yang akun Item Group-nya baru diubah — nilai lamanya "
	 "tetap tinggal di akun lama sampai dibuatkan Journal Entry reklasifikasi. "
	 "Laporan pembanding: <b>Stock Ledger</b> dan <b>Stock Balance</b> per tanggal yang sama."),

	("Item baru perlu disetel apa saja?",
	 "Centang <b>Maintain Stock</b> dan pilih <b>Item Group</b> yang benar — akun persediaan "
	 "dan akun bebannya ikut grup itu. Isi Item Defaults di level item hanya bila "
	 "item ini harus beda dari grupnya (isian item menang atas grup)."),

	("Kenapa nama rak seperti A-AA-01?",
	 "Polanya <b>RAK-SEGMEN-LEVEL</b>: rak A, segmen AA, level 1. Dari nama itu sistem "
	 "mengisi sendiri urutan dekat pintu dan tinggi level, yang dipakai <b>Suggest Rack</b> "
	 "untuk memilih rak terdekat dan terbawah lebih dulu."),

	("Barang datang bertahap / dikirim sebagian, boleh?",
	 "Boleh. Sisa qty PO tetap terbuka untuk Purchase Receipt berikutnya, begitu juga sisa SO "
	 "untuk Delivery Note berikutnya. Statusnya terpantau di kolom status list dokumen."),

	("Barang sudah diterima lalu dikembalikan ke supplier",
	 "Itu <b>Purchase Return</b>, bukan Void — dokumen baru bertanggal hari ini, supaya "
	 "riwayatnya jujur bahwa barang pernah masuk lalu keluar. Void hanya untuk penerimaan "
	 "yang memang tidak pernah terjadi (dobel input, barang tidak pernah datang)."),
])

STOCK_MANUAL = (
	_step(1, "Melihat stok", [
		"<b>Stock &gt; Stock Balance</b>: saldo qty dan nilai per item per warehouse — "
		"karena rak = warehouse, laporan otomatis rinci per rak.",
		"<b>Stock Ledger</b>: riwayat mutasi per transaksi.",
	])

	+ _step(2, "Adjustment / stock opname — Stock Reconciliation", [
		"Buka <b>Stock &gt; Stock Reconciliation &gt; + Add</b>, purpose Stock Reconciliation.",
		"Tambah baris per item + rak, isi <b>Qty</b> dan/atau <b>Valuation Rate</b> hasil "
		"hitung fisik — sistem menghitung selisihnya.",
		"<b>Save</b>, lalu <b>Submit</b>.",
	], "Selisih dibukukan otomatis ke akun Penyesuaian Persediaan.")

	+ _step(3, "Pemakaian internal — Stock Entry: Material Issue", [
		"Buka <b>Stock &gt; Stock Entry &gt; + Add</b>, type <b>Material Issue</b>.",
		"Isi Source Warehouse (rak asal), item, qty.",
		"<b>Save</b>, lalu <b>Submit</b>.",
		"Sparepart yang langsung dipakai saat pembelian TIDAK perlu ini — otomatis dari "
		"baris ber-Vehicle di Purchase Receipt (Manual Purchase langkah 2).",
		"Sparepart untuk kendaraan yang diambil DARI GUDANG juga tidak lewat sini — "
		"pakai <b>Fleet &gt; Maintenance</b>, Stock Entry-nya terbit sendiri saat Validate.",
	], "Jurnal: Dr akun beban item (mis. Beban Sparepart) / Cr Persediaan.")

	+ _step(4, "Mutasi antar rak / gudang — Stock Entry: Material Transfer", [
		"Buka <b>Stock &gt; Stock Entry &gt; + Add</b>, type <b>Material Transfer</b>.",
		"Per baris isi Source Warehouse (rak asal) dan Target Warehouse (rak tujuan).",
		"<b>Save</b>, lalu <b>Submit</b>.",
	], "Nilai stok ikut pindah, tanpa efek laba rugi.")

	+ _step(5, "Mengatur akun persediaan — ikut JENIS BARANG, bukan gudang", [
		"Akun persediaan diambil dari <b>Item Group</b> barangnya, bukan dari gudang tempat "
		"barang disimpan. Jadi flexibag, oleo, dan sparepart boleh menumpuk di rak yang sama, "
		"jurnalnya tetap masuk ke akun masing-masing.",
		"Aturnya di <b>Stock &gt; Item Group</b> &gt; buka grupnya &gt; tabel <b>Item Defaults</b> &gt; "
		"buka baris company (ikon pensil) &gt; isi <b>Default Inventory Account</b> "
		"(akun persediaan) dan <b>Default Expense Account</b> (akun beban saat barang dipakai).",
		"Item baru tidak perlu disetel apa-apa — cukup pilih Item Group yang benar.",
		"Kalau satu item harus beda dari grupnya: <b>Item</b> &gt; tab <b>Accounting</b> &gt; "
		"tabel Item Defaults. Isian di Item menang atas Item Group.",
		"Saklarnya di <b>Company</b> &gt; section <b>Stock Settings</b> &gt; "
		"<b>Enable Item-wise Inventory Account</b> (sudah menyala, cukup sekali).",
	], "Contoh nyata: satu Purchase Receipt berisi flexibag + glycerine ke satu rak menghasilkan "
	   "Dr Persediaan Flexibag dan Dr Persediaan Oleo Chemicals terpisah, "
	   "lawan Cr Hutang Usaha Sementara.")

	+ '<div class="box"><div class="bt">Pemetaan akun persediaan (PT CMI)</div>'
	'<table class="j"><tr><th>Item Group</th><th>Akun persediaan</th><th>Akun beban</th>'
	'<th>Catatan</th></tr>'
	'<tr><td>Sparepart</td><td>1140.006 Persediaan Spareparts</td>'
	'<td>5110.042 Bi. Pemeliharaan Trado</td><td class="n">dipakai lewat Maintenance</td></tr>'
	'<tr><td>Flexibag</td><td>1130.001 Persediaan Flexibag</td><td>—</td>'
	'<td class="n">barang dagang</td></tr>'
	'<tr><td>Oleo Chemicals</td><td>1130.002 Persediaan Oleo Chemicals</td><td>—</td>'
	'<td class="n">barang dagang</td></tr>'
	'<tr><td>CRM, Products, Consumable, Raw Material, Services</td>'
	'<td>1130.003 Persediaan Umum</td><td>—</td>'
	'<td class="n">bawaan, tidak dipisah</td></tr>'
	'</table></div>'

	+ '<div class="box warn"><div class="bt">Wajib: Item Group baru harus punya akun persediaan</div>'
	'<ul>'
	'<li>Mode ini TIDAK punya cadangan. Item yang Item Group-nya belum diisi '
	'<b>Default Inventory Account</b> akan menolak transaksi dengan pesan '
	'<i>"Please set default inventory account for item ..."</i> — bukan jatuh ke akun gudang '
	'atau akun default Company.</li>'
	'<li>Kalau ragu sebuah grup perlu akun sendiri, isi saja <b>1130.003 Persediaan Umum</b>. '
	'Itu perilaku lama, aman, dan bisa diubah kapan saja.</li>'
	'<li>Akun yang dipakai sebagai akun persediaan harus ber-<b>Account Type = Stock</b>.</li>'
	'</ul></div>'

	+ '<div class="box"><div class="bt">Tentang rak (WMS)</div><ul>'
	'<li>Rak = child warehouse di bawah gudang (mis. Gudang Utama - CMI &gt; A-AA-01 - CMI).</li>'
	'<li>Nama rak berpola <b>RAK-SEGMEN-LEVEL</b>, contoh A-AA-01 = rak A, segmen AA, level 1. '
	'Urutan dekat pintu dan level otomatis terisi dari namanya.</li>'
	'<li>Zona per kelompok barang: field <b>Rack Zone</b> di Item Group (huruf rak, '
	'mis. "A,B") membatasi saran rak masuk.</li>'
	'<li>Tombol <b>Suggest Rack</b>: di Purchase Receipt menyarankan rak masuk '
	'(konsolidasi ke rak berisi item sama, hormati zona); di Delivery Note menyarankan '
	'rak keluar secara FIFO (stok tertua dulu).</li>'
	'</ul></div>'
)

STOCK_HEAD = (
	'<h2>Manual Stock — Inventory</h2>'
	'<p class="lead">Stok masuk lewat Purchase Receipt dan keluar lewat Delivery Note; '
	'di antaranya ada opname, pemakaian internal, dan mutasi antar rak. '
	'Semua stok tercatat per rak, karena rak adalah warehouse.</p>'
)

STOCK_HTML = _page("st", STOCK_HEAD, STOCK_ROADMAP, STOCK_MANUAL, STOCK_FAQ)

# ---------------------------------------------------------------- Manual Basic

BASIC_HEAD = (
	'<h2>Manual Basic — Setup Akun</h2>'
	'<p class="lead">Di mana saja akun di-setting sebelum sistem dipakai: dari Company, '
	'pembelian, penjualan, sampai kasbon. Jurnal yang dihasilkan tiap setting ada di '
	'Manual Penjurnalan.</p>'
)

BASIC_ROADMAP = (
	'<div class="fh">Urutan setup, dari daftar akun sampai kasbon</div>'
	'<div class="flow">'
	+ _node("1", "Chart of Accounts", "Daftar akun per company",
	        "Sumber semua akun di langkah berikutnya")
	+ _ARROW
	+ _node("2", "Company", "Akun default: piutang, hutang, bank, persediaan, HPP, selisih kurs",
	        "Dipakai bila dokumen tidak menyebut akun sendiri")
	+ _ARROW
	+ _node("3", "Item / Item Group", "Akun persediaan dan akun beban per jenis barang",
	        "Menentukan jurnal PR, DN, dan Material Issue")
	+ _ARROW
	+ _node("4", "Invoice Type / Expense Class", "Akun pendapatan penjualan dan akun biaya job",
	        "Menentukan jurnal Sales Invoice dan Expense Note")
	+ _ARROW
	+ _node("5", "Setting pembayaran", "ERPNext Custom Setting, Mode of Payment, rekening bank",
	        "Menentukan akun potongan dan sisi bank Payment Entry")
	+ _ARROW
	+ _node("6", "Pending Cash Type", "Akun uang muka kasbon",
	        "Menentukan jurnal saat kasbon di-Pay")
	+ '</div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li>Hampir semua setting akun bersifat <b>per company</b> — pastikan memilih company yang"
	" benar.</li>"
	"<li>Akun persediaan dan beban barang mengikuti <b>Item Group</b> (item menang bila diisi); grup"
	" tanpa akun akan menolak transaksi.</li>"
	"<li>Akun di Company adalah <b>jaring pengaman terakhir</b>: dipakai hanya saat dokumen tidak"
	" menyebut akunnya sendiri.</li>"
	'</ul></div>'
)

BASIC_MANUAL = (
	_step(1, "Chart of Accounts — daftar akun", [
		"Semua akun hidup di <b>Accounting &gt; Chart of Accounts</b>, per company.",
		"Tambah / ubah akun dari halaman itu; nomor dan pengelompokan mengikuti "
		"struktur CoA perusahaan.",
	])

	+ _step(2, "Company — akun default", [
		"Buka <b>Company</b>, section Accounts. Akun di sini dipakai sistem setiap kali "
		"dokumen tidak menyebut akun sendiri:",
		"<b>Default Receivable</b> (Piutang) — sisi debit semua Sales Invoice.",
		"<b>Default Payable</b> (Hutang Usaha) — sisi kredit Purchase Invoice.",
		"<b>Default Bank / Cash Account</b> — sisi bank Payment Entry bila tidak dipilih.",
		"Stock: <b>Default Inventory</b> (Persediaan), <b>Stock Received But Not Billed</b> "
		"(Hutang Sementara), <b>Default COGS</b> (HPP), <b>Stock Adjustment</b> "
		"(Penyesuaian Persediaan).",
		"<b>Exchange Gain / Loss</b> (Selisih Kurs) — dipakai pembayaran valas.",
		"Asset: <b>Accumulated Depreciation</b>, <b>Depreciation Expense</b> "
		"(CWIP dan Disposal belum diisi — lihat Manual Penjurnalan bagian Asset).",
		"<b>Default Cost Center</b> — dipakai semua jurnal tanpa cost center eksplisit.",
	])

	+ _step(3, "Purchase — akun beban per item", [
		"Akun beban pembelian ditentukan di <b>Item &gt; Item Default</b> per company "
		"(field Default Expense Account); kosong = fallback ke <b>Item Group</b>-nya.",
		"Akun inilah yang jadi: Dr Beban di PI jasa / non-stock, dan Dr HPP di "
		"Delivery Note untuk barang stock.",
		"Tipe pembelian (stock / jasa / langsung pakai / asset / sparepart) dibedakan "
		"oleh setting Item — lihat box di Manual Purchase.",
	])

	+ _step(4, "Selling — akun pendapatan per Invoice Type", [
		"Daftar tipe invoice dikelola di <b>Selling Settings &gt; tab Invoice Type</b>.",
		"Per tipe diisi: <b>Behavior</b> (Normal / Reimburse / Trading), "
		"<b>Income Account</b> (sisi kredit SI tipe itu), <b>Discount Account</b>, "
		"<b>Type No</b> (kode nomor), dan <b>Roles</b> yang boleh memakai.",
	])

	+ _step(5, "Expedition — akun per Expense Class", [
		"Tiap <b>Expense Class</b> (jenis biaya job) menyimpan akunnya sendiri: "
		"<b>Account</b> (akun biaya, Dr saat EN Validate), <b>Account Reimbursement</b> "
		"(dipakai bila EN dicentang Reimburse to Customer), dan <b>Account Suspend</b>.",
		"Panel Biaya di Expense Note mengisi akun per baris dari sini.",
	])

	+ _step(6, "Payment — potongan dan Mode of Payment", [
		"<b>ERPNext Custom Setting</b>: akun PPN / PPh / Materai untuk penjualan (SI) "
		"dan pembelian (PI), plus akun potongan Payment Entry "
		"(Tax, PPh, Discount, Materai, Admin / Adjustment, CN-DN).",
		"<b>Mode of Payment &gt; Accounts</b>: akun default per company — dipakai "
		"mengisi otomatis sisi bank Payment Entry.",
		"Mode of Payment <b>Settlement</b> tidak butuh akun default — akunnya dipilih "
		"per dokumen di field Settlement Account.",
	])

	+ _step(7, "Rekening bank", [
		"Tiap rekening = satu akun tipe <b>Bank</b> di Chart of Accounts.",
		"<b>Kata pertama nama akun</b> jadi kode bank di nomor dokumen RV / PV "
		"(mis. akun \"MDR 167-xxx\" menghasilkan RV/MDR/...).",
		"<b>Currency akun</b> menentukan mata uang pembayaran — rekening non-IDR "
		"untuk pembayaran valas (lihat Manual Payment Entry langkah 4).",
	])

	+ _step(8, "Pending Cash — akun uang muka per Type", [
		"Tiap <b>Pending Cash Type</b> menyimpan <b>Advance Account</b> (akun uang muka) "
		"— sisi debit saat kasbon di-Pay, dan sisi kredit saat kasbon dipakai "
		"membayar di Payment Entry.",
	])

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Semua jurnal yang dihasilkan setting di atas terangkum di <b>Manual Penjurnalan</b>.</li>'
	'<li>Setting akun umumnya per company — pastikan memilih company yang benar '
	'saat mengisi.</li>'
	'</ul></div>'
)

BASIC_FAQ = _faq([
	("Akun mana yang dipakai kalau dokumen tidak menyebut akun?",
	 "Akun default di <b>Company</b>: Receivable, Payable, Bank, Inventory, Stock Received But Not"
	 " Billed, COGS, Stock Adjustment, Exchange Gain/Loss, dan Default Cost Center. Anggap ini jaring"
	 " pengaman terakhir, bukan tempat mengatur kebijakan akun."),

	("Menambah tipe invoice baru",
	 "<b>Selling Settings &gt; tab Invoice Type</b>: isi Behavior (Normal / Reimburse / Trading),"
	 " Income Account, Discount Account, Type No untuk nomor, dan Roles yang boleh memakainya."),

	("Akun beban / persediaan diisi di Item atau Item Group?",
	 "Isi di <b>Item Group</b> supaya berlaku untuk semua item di dalamnya. Isian di level <b>Item</b>"
	 " hanya untuk pengecualian — dan ia menang atas grup."),

	("Akun baru tidak muncul di pilihan dokumen",
	 "Cek tiga hal: company-nya benar, akunnya bukan <b>group</b>, dan <b>Account Type</b>-nya sesuai"
	 " (akun persediaan harus bertipe Stock, akun bank bertipe Bank)."),

	("Mengatur akun potongan PPN / PPh / materai",
	 "Di <b>ERPNext Custom Setting</b>: akun pajak untuk penjualan dan pembelian, plus akun potongan"
	 " Payment Entry (Tax, PPh, Discount, Materai, Admin/Adjustment, CN-DN)."),

	("Menambah rekening bank baru",
	 "Buat akun bertipe <b>Bank</b> di Chart of Accounts. Perhatikan dua hal: <b>kata pertama"
	 " namanya</b> menjadi kode nomor RV/PV, dan <b>currency</b>-nya menentukan mata uang pembayaran."),

	("Kenapa Mode of Payment Settlement tidak punya akun default?",
	 "Karena akunnya berbeda tiap kasus — dipilih per dokumen di field <b>Settlement Account</b>, dan"
	 " Save ditolak bila dikosongkan."),

	("Menyiapkan company baru",
	 "Urutannya: Chart of Accounts, akun default Company, Item Group Defaults (persediaan dan beban),"
	 " Invoice Type, Expense Class, setting pembayaran, rekening bank, lalu Pending Cash Type. Semuanya"
	 " per company."),
])

BASIC_HTML = _page("ba", BASIC_HEAD, BASIC_ROADMAP, BASIC_MANUAL, BASIC_FAQ)

# ---------------------------------------------------------------- Manual Penjurnalan

JOURNAL_HEAD = (
	'<h2>Manual Penjurnalan</h2>'
	'<p class="lead">Rekap semua jurnal yang dibuat sistem secara otomatis: dokumen apa '
	'memicu jurnal apa. Detail cara input tiap dokumen ada di manual modulnya.</p>'
)

JOURNAL_ROADMAP = (
	'<div class="fh">Rantai pembelian</div>'
	'<div class="flow">'
	+ _node("PR", "Purchase Receipt", "Barang diterima", "Dr Persediaan / Cr Hutang Sementara")
	+ _ARROW
	+ _node("PI", "Purchase Invoice", "Tagihan supplier", "Dr Hutang Sementara / Cr Hutang Usaha")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Bayar supplier", "Dr Hutang Usaha / Cr Bank")
	+ '</div>'

	'<div class="fh">Rantai penjualan</div>'
	'<div class="flow">'
	+ _node("DN", "Delivery Note", "Barang keluar", "Dr HPP / Cr Persediaan")
	+ _ARROW
	+ _node("SI", "Sales Invoice", "Tagihan customer", "Dr Piutang / Cr Pendapatan")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Terima pembayaran", "Dr Bank / Cr Piutang")
	+ '</div>'

	'<div class="fh">Rantai biaya job</div>'
	'<div class="flow">'
	+ _node("EN", "Expense Note", "Biaya vendor", "Dr Biaya / Cr Hutang Vendor")
	+ _ARROW
	+ _node("SI", "Sales Invoice reimburse", "Ditagihkan ulang", "Dr Piutang / Cr Reimbursement")
	+ _ARROW
	+ _node("PE", "Payment Entry", "Bayar vendor, terima customer", "Dua arah")
	+ '</div>'
	+ '<div class="box warn"><div class="bt">Yang menentukan benar-salahnya</div><ul>'
	"<li>Jurnal selalu lahir dari <b>dokumen</b>, bukan diinput manual — koreksi jurnal berarti"
	" koreksi dokumennya.</li>"
	"<li><b>Invalidate</b> menghapus jurnal (dokumen kembali draft); <b>Void</b> membalik jurnal dan"
	" meninggalkan jejak.</li>"
	"<li>Barang yang diterima tapi belum ditagih duduk di <b>Hutang Usaha Sementara</b> sampai"
	" Purchase Invoice terbit.</li>"
	'</ul></div>'
)

JOURNAL_MANUAL = (
	'<div class="fh">Pembelian (Manual Purchase)</div>'
	+ _jtable([
		("Purchase Receipt — barang stock", "Persediaan", "Hutang Usaha Sementara",
		 "Stok bertambah per rak"),
		("Purchase Receipt — baris sparepart ber-Vehicle", "Beban Sparepart", "Persediaan",
		 "Material Issue otomatis, menyusul jurnal PR di atas"),
		("Purchase Invoice — barang stock", "Hutang Usaha Sementara", "Hutang Usaha",
		 "Hutang supplier resmi terbentuk"),
		("Purchase Invoice — jasa / non-stock / langsung pakai", "Beban (akun item)",
		 "Hutang Usaha", "Tanpa PR"),
	])

	+ '<div class="fh">Penjualan (Manual Trading / Selling)</div>'
	+ _jtable([
		("Delivery Note", "HPP", "Persediaan",
		 "Stok keluar; akun HPP dari Item Default (fallback Item Group)"),
		("Sales Invoice — Trading", "Piutang", "Penjualan Barang Dagang", ""),
		("Sales Invoice — Normal (jasa)", "Piutang", "Pendapatan sesuai Invoice Type",
		 "Akun income dikonfigurasi per tipe di Selling Settings"),
		("Sales Invoice — Reimburse", "Piutang", "Reimbursement",
		 "Pass-through, bukan pendapatan; baris Markup dijurnalkan per item"),
	])

	+ '<div class="fh">Expedition (Manual Expedition)</div>'
	+ _jtable([
		("Expense Note — Validate", "Akun biaya per expense class", "Hutang Vendor",
		 "Journal Entry otomatis; EN reimburse: debit ke akun Reimbursement"),
	])

	+ '<div class="fh">Pembayaran (Manual Payment Entry)</div>'
	+ _jtable([
		("Payment Entry — Receive", "Bank", "Piutang", "Outstanding SI berkurang"),
		("Payment Entry — Pay (Purchase Invoice)", "Hutang Usaha", "Bank", ""),
		("Payment Entry — Pay (Tarik Expense Note)", "Hutang Vendor (dari jurnal EN)", "Bank",
		 "Potongan Tax / PPh / Materai / Admin / CN-DN ke akun di ERPNext Custom Setting"),
		("Payment Entry — valas", "Hutang @kurs buku", "Bank valas @kurs bayar",
		 "Selisihnya otomatis ke akun Selisih Kurs"),
		("Payment Entry — Expense / Income", "Akun tiap baris item (Pay)", "Bank",
		 "Receive kebalikannya: Dr Bank / Cr akun item"),
		("Payment Entry — Settlement", "Hutang", "Settlement Account",
		 "Bank tidak tersentuh; Receive kebalikannya"),
		("Payment Entry — pakai Pending Cash", "Hutang", "Uang Muka (+ Bank untuk sisanya)",
		 "Kredit memakai akun uang muka kasbonnya"),
	])

	+ '<div class="fh">Kasbon (Manual Pending Cash)</div>'
	+ _jtable([
		("Pending Cash — Pay", "Uang Muka (akun dari Type)", "Bank",
		 "Terurai per penerima bila akunnya Receivable; Unpaid menghapus jurnalnya"),
		("Pending Cash — Void", "-", "-",
		 "Jurnal dibatalkan tapi dibiarkan sebagai jejak; Unvoid membuat jurnal baru"),
	])

	+ '<div class="fh">Stock (Manual Stock)</div>'
	+ _jtable([
		("Stock Reconciliation", "Persediaan / Penyesuaian Persediaan",
		 "Penyesuaian Persediaan / Persediaan",
		 "Arah tergantung selisih fisik plus atau minus"),
		("Stock Entry — Material Issue", "Beban item (mis. Beban Sparepart)", "Persediaan", ""),
		("Stock Entry — Material Transfer", "-", "-",
		 "Nilai stok pindah antar rak, tanpa efek laba rugi"),
	])

	+ '<div class="fh">Asset (BELUM AKTIF di site ini)</div>'
	+ _jtable([
		("Purchase Receipt / Invoice — item fixed asset", "Asset (atau CWIP)", "Hutang Usaha",
		 "Record Asset terbentuk otomatis dari pembelian"),
		("Depreciation Entry — otomatis per jadwal", "Beban Penyusutan", "Akumulasi Penyusutan",
		 "Journal Entry berkala mengikuti jadwal penyusutan asset"),
		("Penjualan / pelepasan asset", "Akumulasi Penyusutan + Bank/Piutang", "Asset",
		 "Selisihnya ke akun laba/rugi pelepasan asset"),
		("Scrap asset", "Akumulasi Penyusutan + Kerugian", "Asset", ""),
	])
	+ '<div class="box warn"><div class="bt">Setup asset belum lengkap</div><ul>'
	'<li>Belum ada <b>Asset Category</b>, item ber-<b>Is Fixed Asset</b>, maupun akun '
	'<b>CWIP</b> dan <b>Disposal</b> di Company — jurnal di atas belum bisa terjadi '
	'sampai setup ini diisi.</li>'
	'</ul></div>'

	+ '<div class="box"><div class="bt">Dokumen TANPA jurnal</div><ul>'
	'<li>Sales Order, Purchase Order, Quotation, Pick List — komitmen saja.</li>'
	'<li>Shipping List / Packing List — dokumen job.</li>'
	'<li>Pending Cash sebelum Paid (Draft / Validated).</li>'
	'</ul></div>'
)

JOURNAL_FAQ = _faq([
	("Kenapa Purchase Receipt sudah menjurnal padahal belum ada tagihan?",
	 "Karena barangnya sudah menjadi milik dan risiko perusahaan. Lawannya ditampung di <b>Hutang"
	 " Usaha Sementara</b>, lalu dipindahkan ke Hutang Usaha supplier saat Purchase Invoice terbit."),

	("Kenapa HPP muncul di Delivery Note, bukan di Sales Invoice?",
	 "HPP mengikuti <b>barangnya keluar</b>, bukan tagihannya terbit. Kalau menjual tanpa DN (Update"
	 " Stock dicentang di invoice), HPP-nya baru ikut di invoice itu."),

	("Di mana jurnal Expense Note?",
	 "Expense Note membuat <b>Journal Entry</b> tersendiri saat Validate — bukan GL langsung. Nomornya"
	 " tertaut di dokumen EN dan itulah yang dirujuk Payment Entry saat vendor dibayar."),

	("Melihat jurnal sebuah dokumen",
	 "Buka laporan <b>General Ledger</b> lalu filter Voucher No dengan nomor dokumennya, atau pakai"
	 " menu Ledger / dashboard di dokumen yang bersangkutan."),

	("Beda efek Invalidate dan Void ke jurnal",
	 "<b>Invalidate</b>: jurnal dihapus, dokumen kembali draft dengan nomor yang sama. <b>Void</b>:"
	 " jurnal dibalik dan dibiarkan sebagai jejak, dokumen mati di status Void."),

	("Selisih kurs muncul dari mana?",
	 "Dari pembayaran valas: hutang dicatat memakai kurs buku, bank keluar memakai kurs bayar,"
	 " selisihnya otomatis ke akun <b>Selisih Kurs</b> di Company."),

	("Kenapa invoice reimburse tidak menambah pendapatan?",
	 "Karena isinya biaya titipan yang ditagihkan ulang (pass-through) — kreditnya ke akun"
	 " Reimbursement. Pendapatan hanya lahir dari baris <b>Markup</b>."),

	("Jurnal asset dan penyusutan belum pernah muncul",
	 "Setup asset di site ini belum lengkap (belum ada Asset Category, item Is Fixed Asset, dan akun"
	 " CWIP / Disposal di Company), jadi jurnal asset memang belum bisa terjadi."),

	("Dokumen apa saja yang sama sekali tidak menjurnal?",
	 "Sales Order, Purchase Order, Quotation, Pick List, dokumen job (Shipping List / Packing List),"
	 " dan Pending Cash sebelum status Paid."),
])

JOURNAL_HTML = _page("jn", JOURNAL_HEAD, JOURNAL_ROADMAP, JOURNAL_MANUAL, JOURNAL_FAQ)

LANDING_BLOCKS = [
	_h("Manual Book", 4),
	_p("Panduan pemakaian ERP per modul. Pilih manual dari menu di kiri."),
	_p("Isi: Basic (setup akun), Expedition, Trading, Selling, Purchase, Stock, Payment Entry, Pending Cash, Penjurnalan."),
]

# (nama workspace, ikon sidebar, html manual). Tambah manual baru = tambah baris.
MANUALS = [
	("Manual Basic", "book-open", BASIC_HTML),
	("Manual Expedition", "book-open", EXPEDITION_HTML),
	("Manual Trading", "book-open", TRADING_HTML),
	("Manual Selling", "book-open", SELLING_HTML),
	("Manual Purchase", "book-open", PURCHASE_HTML),
	("Manual Stock", "book-open", STOCK_HTML),
	("Manual Payment Entry", "book-open", PAYMENT_HTML),
	("Manual Pending Cash", "book-open", PENDING_CASH_HTML),
	("Manual Penjurnalan", "book-open", JOURNAL_HTML),
]


def _ensure_workspace(title, blocks, parent=None, custom_block=None):
	# Menu top-level desk = daftar Workspace public (get_workspace_sidebar_items);
	# Workspace Sidebar hanya menu kiri saat workspace dibuka (match by title).
	if frappe.db.exists("Workspace", title):
		w = frappe.get_doc("Workspace", title)
	else:
		w = frappe.new_doc("Workspace")
		w.title = title
		w.label = title  # autoname = field:label
	w.update({"module": MODULE, "app": APP, "public": 1, "icon": "book-open",
	          "parent_page": parent or "",
	          "content": json.dumps([dict(b, id=f"b{i}") for i, b in enumerate(blocks)])})
	w.set("links", [])
	w.set("shortcuts", [])
	w.set("charts", [])
	w.set("number_cards", [])
	# blok content type custom_block hanya dirender bila juga terdaftar di child
	# table custom_blocks (get_desktop_page membacanya dari sana).
	w.set("custom_blocks", [])
	if custom_block:
		w.append("custom_blocks", {"custom_block_name": custom_block, "label": custom_block})
	w.flags.ignore_links = True
	w.save(ignore_permissions=True)


def _ensure_html_block(name, html):
	if frappe.db.exists("Custom HTML Block", name):
		blk = frappe.get_doc("Custom HTML Block", name)
	else:
		blk = frappe.new_doc("Custom HTML Block")
		blk.name = name  # autoname = prompt
	blk.update({"html": html, "style": MANUAL_CSS, "script": "", "private": 0})
	blk.save(ignore_permissions=True)


def ensure_manual_book():
	_ensure_workspace(SIDEBAR, LANDING_BLOCKS)
	for title, _icon, html in MANUALS:
		_ensure_html_block(title, html)
		_ensure_workspace(title, [{"type": "custom_block",
		                           "data": {"custom_block_name": title, "col": 12}}],
		                  parent=SIDEBAR, custom_block=title)

	if frappe.db.exists("Workspace Sidebar", SIDEBAR):
		sb = frappe.get_doc("Workspace Sidebar", SIDEBAR)
	else:
		sb = frappe.new_doc("Workspace Sidebar")
		sb.title = SIDEBAR
	sb.update({"module": MODULE, "app": APP, "header_icon": "book-open"})
	sb.set("items", [])
	sb.append("items", {"type": "Link", "label": "Home", "icon": "home",
	                    "link_type": "Workspace", "link_to": SIDEBAR})
	for title, icon, _html in MANUALS:
		sb.append("items", {"type": "Link", "label": title, "icon": icon,
		                    "link_type": "Workspace", "link_to": title})
	sb.save(ignore_permissions=True)

	# Menu kiri desk (daftar modul) dirender dari Desktop Icon, bukan dari
	# Workspace/Sidebar — tanpa icon ini Manual Book tidak muncul di menu.
	# app WAJIB diisi: dropdown switcher memfilter icon.app == current_app.
	di_name = frappe.db.exists("Desktop Icon", {"label": SIDEBAR, "link_type": "Workspace Sidebar"})
	di = frappe.get_doc("Desktop Icon", di_name) if di_name else frappe.new_doc("Desktop Icon")
	di.update({"label": SIDEBAR, "link_type": "Workspace Sidebar", "link_to": SIDEBAR, "app": APP})
	di.save(ignore_permissions=True)

	# cache icon & bootinfo per-user (redis hash) — buang seluruhnya, bukan cuma
	# user session ini, supaya menu langsung muncul untuk semua user.
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")

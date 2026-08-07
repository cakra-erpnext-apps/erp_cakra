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


# ---------------------------------------------------------------- Manual Trading

TRADING_HTML = (
	'<div class="mb">'
	'<h2>Manual Trading — Penjualan Barang Dagang</h2>'
	'<p class="lead">Alur barang dagang keluar, dari order sampai pembayaran. '
	'Stok dan jurnal HPP terjadi di Delivery Note; pendapatan dan piutang di Sales Invoice.</p>'

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

	+ _step(1, "Sales Order (SO)", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Purchase

PURCHASE_HTML = (
	'<div class="mb">'
	'<h2>Manual Purchase — Pembelian</h2>'
	'<p class="lead">Alur pembelian dari order sampai tagihan supplier. '
	'Stok bertambah di Purchase Receipt; hutang supplier resmi terbentuk di Purchase Invoice.</p>'

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

	+ _step(1, "Purchase Order (PO)", [
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

	+ '<div class="box"><div class="bt">Catatan</div><ul>'
	'<li>Penerimaan boleh sebagian (partial): sisa qty PO tetap terbuka untuk PR berikutnya.</li>'
	'<li>Koreksi dokumen: <b>Invalidate</b> kembali ke draft, <b>Void</b> membatalkan — butuh role, '
	'dan ditolak bila dokumen sudah dirujuk dokumen lain (batalkan perujuknya dulu).</li>'
	'<li>Pemakaian sparepart dari stok (bukan saat pembelian) sementara lewat '
	'<b>Stock Entry - Material Issue</b> manual — lihat Manual Stock.</li>'
	'</ul></div>'
	'</div>'
)

# ---------------------------------------------------------------- Manual Payment Entry

PAYMENT_HTML = (
	'<div class="mb">'
	'<h2>Manual Payment Entry</h2>'
	'<p class="lead">Semua uang masuk dan keluar bank dicatat lewat Payment Entry. '
	'Nomor otomatis: RV (terima) / PV (bayar) + kode bank + bulan romawi, '
	'contoh RV/MDR/CMI/2026/VII/0003.</p>'

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

	+ _step(1, "Terima pembayaran customer (Receive)", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Pending Cash

PENDING_CASH_HTML = (
	'<div class="mb">'
	'<h2>Manual Pending Cash — Kasbon</h2>'
	'<p class="lead">Uang muka tunai yang diserahkan ke penerima sebelum ada bukti biaya. '
	'Nomor otomatis PC/TIPE/COMPANY/TAHUN/####, contoh PC/JOB/CMI/26/0001.</p>'

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

	+ _step(1, "Buat Pending Cash", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Expedition

EXPEDITION_HTML = (
	'<div class="mb">'
	'<h2>Manual Expedition</h2>'
	'<p class="lead">Alur job expedition: dokumen job, biaya vendor, tagihan ke customer, '
	'lalu pembayaran dua arah (bayar vendor, terima customer).</p>'

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

	+ _step(1, "Dokumen job", [
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
	+ '</div>'
)

# ---------------------------------------------------------------- Manual Selling

SELLING_HTML = (
	'<div class="mb">'
	'<h2>Manual Selling — Penjualan</h2>'
	'<p class="lead">Alur penjualan umum. Untuk penjualan barang dagang lengkap sampai '
	'gudang, lihat Manual Trading; untuk tagihan job expedition, lihat Manual Expedition.</p>'

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

	+ _step(1, "Quotation (opsional)", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Stock

STOCK_HTML = (
	'<div class="mb">'
	'<h2>Manual Stock — Gudang dan Rak</h2>'
	'<p class="lead">Stok masuk lewat Purchase Receipt dan keluar lewat Delivery Note; '
	'di antaranya ada opname, pemakaian internal, dan mutasi antar rak. '
	'Semua stok tercatat per rak, karena rak adalah warehouse.</p>'

	'<div class="flow">'
	+ _node("IN", "Purchase Receipt", "Barang masuk (Manual Purchase)",
	        "Stok bertambah per rak")
	+ _ARROW
	+ _node("RAK", "Stok per Rak", "Tersimpan, terpantau per rak",
	        "Stock Balance / Stock Ledger")
	+ _ARROW
	+ _node("OUT", "Delivery Note / Material Issue", "Barang keluar: dijual atau dipakai",
	        "Stok berkurang")
	+ '</div>'

	+ _step(1, "Melihat stok", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Basic

BASIC_HTML = (
	'<div class="mb">'
	'<h2>Manual Basic — Setup Akun</h2>'
	'<p class="lead">Di mana saja akun di-setting sebelum sistem dipakai: dari Company, '
	'pembelian, penjualan, sampai kasbon. Jurnal yang dihasilkan tiap setting ada di '
	'Manual Penjurnalan.</p>'

	+ _step(1, "Chart of Accounts — daftar akun", [
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
	'</div>'
)

# ---------------------------------------------------------------- Manual Penjurnalan

JOURNAL_HTML = (
	'<div class="mb">'
	'<h2>Manual Penjurnalan</h2>'
	'<p class="lead">Rekap semua jurnal yang dibuat sistem secara otomatis: dokumen apa '
	'memicu jurnal apa. Detail cara input tiap dokumen ada di manual modulnya.</p>'

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
	'</div>'
)

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

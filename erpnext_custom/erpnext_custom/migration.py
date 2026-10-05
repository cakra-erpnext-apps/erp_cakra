"""Menu "Migration" di desk: tata cara pindah dari Ascend ke ERPNext + daftar modul
yang wajib diisi, berurutan. SATU workspace saja (permintaan user), isinya satu Custom
HTML Block dengan tab Tata Cara / Modul / Cek / FAQ. Modul yang sama juga dipasang di
sidebar kiri (sidebar_items), jadi user mengecek semuanya tanpa pindah menu. Doctype
itu juga ada di menu lain; sidebar_fallback.js menjaga Migration tidak "merebut"
halaman itu saat refresh kecuali Migration memang menu terakhir yang dibuka.

Konten hidup DI FILE INI; ensure_migration() menimpa DB tiap migrate.
"""

import frappe

from erpnext_custom.desk_menu import _ensure_sidebar
from erpnext_custom.desk_menus_spec import SB, L
from erpnext_custom.manual_book import _ARROW, _faq, _node, _table, _tabs, ensure_book

SIDEBAR = "Migration"
ICON = "database-zap"


def _a(doctype, label=None, new=False):
	"""Link ke list (atau form baru) doctype."""
	href = "/app/" + frappe.scrub(doctype).replace("_", "-") + ("/new" if new else "")
	return f'<a href="{href}">{label or doctype}</a>'


def _r(report):
	return f'<a href="/app/query-report/{report}">{report}</a>'


def _box(title, items, warn=False):
	lis = "".join(f"<li>{i}</li>" for i in items)
	return f'<div class="box{" warn" if warn else ""}"><div class="bt">{title}</div><ul>{lis}</ul></div>'


IMPORT = "Data Import"
MANUAL = "Manual di form"


# ---------------------------------------------------------------- Tab Tata Cara

GUIDE = (
	'<div class="flow">' + _ARROW.join([
		_node("1", "Fondasi", "Company, tahun buku, CoA, cost center", "Kerangka akun"),
		_node("2", "Setting", "Akun default, tipe dokumen, bank, pajak", "Jurnal otomatis benar"),
		_node("3", "Master", "Item, gudang, customer, supplier", "Siap dipakai transaksi"),
		_node("4", "Saldo awal", "Piutang, hutang, stok, aset, neraca", "Per tanggal cut-off"),
		_node("5", "Dokumen berjalan", "PO, SO, job yang belum selesai", "Opsional"),
		_node("6", "Cek", "Bandingkan laporan dengan Ascend", "Baru go-live"),
	]) + "</div>"
	+ _box("Aturan umum", [
		"Tentukan <b>tanggal cut-off</b> lebih dulu, biasanya akhir bulan. Semua saldo awal memakai "
		"posting date tanggal itu; transaksi baru di ERPNext dimulai tanggal sesudahnya.",
		"Ikuti urutan fase. Data yang dirujuk harus ada dulu: akun sebelum item dan customer, "
		"Item Group sebelum Item, Customer dan Supplier sebelum saldo piutang dan hutang.",
		"Pertahankan kode dari Ascend (nomor akun, kode customer, supplier, item) supaya hasilnya "
		"bisa dicocokkan baris per baris.",
		"Kerjakan di site uji dulu sampai Fase 6 cocok, lalu ulangi di produksi dengan file import yang sama.",
	])
	+ _box("Cara isi massal: Data Import", [
		f"Buka {_a('Data Import', 'Data Import', new=True)}, pilih Document Type, Import Type "
		"<b>Insert New Records</b>.",
		"Klik <b>Download Template</b>, pilih kolom yang perlu, isi di Excel, lalu upload dan "
		"<b>Start Import</b>.",
		"Baris gagal tampil di bagian log beserta alasannya; perbaiki di file lalu import ulang baris "
		"itu saja.",
		"Koreksi data yang sudah masuk: Import Type <b>Update Existing Records</b> (kolom ID wajib).",
	])
	+ _box("Yang menentukan benar salahnya", [
		"Akun default di Fase 2. Salah di sini berarti semua jurnal otomatis salah sejak transaksi pertama.",
		"Akun <b>Temporary Opening</b> harus bersaldo 0 setelah Fase 4 selesai. Kalau tidak nol, ada "
		"saldo awal yang belum masuk atau masuk dua kali.",
		"Nilai yang sudah masuk lewat saldo awal tidak boleh dicatat lagi lewat dokumen (Fase 5).",
	], warn=True)
)


# ---------------------------------------------------------------- Tab Modul

# Satu sumber untuk tabel tab Modul DAN sidebar kiri. Baris = (doctype, isi, sumber
# Ascend, cara isi); doctype boleh list, item-nya str atau (doctype, label).
PHASES = [
	(1, "Fondasi", "Kerangka yang dirujuk semua data lain.", [
		("Company", "Nama, singkatan (abbr), mata uang IDR, negara", "", MANUAL),
		("Fiscal Year", "Tahun buku tanggal cut-off dan tahun berjalan", "", MANUAL),
		(("Account", "Chart of Accounts"), "Nomor, nama, induk, tipe akun (Bank, Cash, Receivable, "
		 "Payable, Stock, Fixed Asset, Tax), mata uang untuk akun valas",
		 "GL Account", "Chart of Accounts Importer atau " + IMPORT),
		("Cost Center", "Pohon cost center, centang yang dipakai transaksi", "Manage Cost Centers", IMPORT),
		(["Department", "Branch", "CMI Office"], "Struktur organisasi dan kantor cabang (CMI Office "
		 "menentukan data CRM yang terlihat per user)", "", MANUAL),
		("Currency Exchange", "Kurs per tanggal cut-off untuk saldo valas", "", MANUAL),
		(["User", "Role Profile"], "Akun login, role, cabang", "", IMPORT),
	]),
	(2, "Setting akun dan tipe dokumen", "Rinciannya ada di Manual Book &gt; Manual Basic.", [
		(("Company", "Company (akun default)"), "Section Accounts: Default Receivable, Payable, Bank, "
		 "Inventory, COGS, Stock Adjustment, Exchange Gain/Loss, Depreciation, Default Cost Center",
		 "GL Interfaces", MANUAL),
		("ERPNext Custom Setting", "Grid Invoice Type (behavior, income account), akun PPN, PPh, "
		 "Materai, potongan Payment Entry, grup Expense Items", "GL Interfaces, Revenue Types", MANUAL),
		(["Purchase Order Type", "Expense Note Type", "Packing List Type", ("APNote Type", "AP Note Type"),
		  ("ARNote Type", "AR Note Type")], "Tipe dokumen dan kode nomornya", "Packing List Types", MANUAL),
		("Mode of Payment", "Akun default per company", "", MANUAL),
		(["Bank", "Bank Account"], "Rekening = akun tipe Bank; kata pertama nama akun jadi kode RV/PV; "
		 "mata uang akun untuk rekening valas", "Bank Account (PV/RV Type)", MANUAL),
		("Pending Cash Type", "Advance Account (akun uang muka kasbon)", "Receivable.PendingCash", MANUAL),
		(["Sales Taxes and Charges Template", "Purchase Taxes and Charges Template", "Item Tax Template",
		  "Tax Withholding Category"], "Template PPN dan PPh", "SalesTax, PurchaseTax, DeductedPPh", MANUAL),
		("Asset Category", "Akun aset, akumulasi, beban penyusutan, metode dan umur; centang Is Vehicle "
		 "untuk kendaraan (otomatis membuat Vehicle)", "", MANUAL),
		("Document Naming Settings", "Seri nomor per dokumen; set counter melanjutkan nomor terakhir "
		 "Ascend bila nomor harus bersambung", "Document Numbering", MANUAL),
	]),
	(3, "Master data", "Isi massal lewat Data Import, urut dari atas.", [
		("UOM", "Satuan yang belum ada", "UOM item", IMPORT),
		("Item Group", "Grup item, akun default per grup, zona rak", "Item Category / Family", IMPORT),
		("Item", "Kode, nama, grup, UOM, Maintain Stock, Is Fixed Asset; tab Item Default: akun beban "
		 "dan Default Reimbursement untuk item biaya", "Inventory Item, Expense Class", IMPORT),
		(["Price List", "Item Price"], "Harga jual / beli bila dipakai", "", IMPORT),
		(["Warehouse", "Rack", "Bin Location"], "Gudang, lalu rak dan bin (rak dan bin tidak punya stok "
		 "atau jurnal)", "Warehouse", IMPORT),
		(["Customer Group", "Customer"], "Kode, nama, NPWP, term, mata uang, akun piutang khusus di tab "
		 "Accounting", "Customer (tab GL Interface)", IMPORT),
		(["Supplier Group", "Supplier"], "Kode, nama, NPWP, PPh, term, rekening bank",
		 "Supplier (tab Accounts, GL Interface)", IMPORT),
		(["Address", "Contact"], "Alamat dan kontak, kolom Links diisi Customer / Supplier",
		 "Customer, Supplier", IMPORT),
		(["Fleet Location", "Shipping Line", "Vessel", "Voyage", "Cargo", "Container Size", "Shipment Type",
		  "Sandaran", "Jenis Karantina"], "Master expedition", "Master Expedition", IMPORT),
		(["Vehicle", "Driver"], "Kendaraan (bila belum terbentuk dari Asset) dan sopir", "", IMPORT),
	]),
	(4, "Saldo awal per tanggal cut-off",
	 "Semua posting date = tanggal cut-off. Lawan setiap saldo awal adalah akun Temporary Opening.", [
		("Opening Invoice Creation Tool", "Piutang dan hutang yang belum lunas, satu baris per invoice: "
		 "party, nomor invoice Ascend, tanggal jatuh tempo, sisa tagihan", "Aging AR / AP", "Tool"),
		("Stock Reconciliation", "Purpose <b>Opening Stock</b>: qty dan valuation rate per item per gudang, "
		 "Difference Account = Temporary Opening", "Saldo inventory per gudang", IMPORT + " (tabel item)"),
		("Asset", "Asset Type <b>Existing Asset</b>: purchase amount, Opening Accumulated Depreciation, "
		 "Opening Number of Booked Depreciations. Tidak membuat jurnal", "Daftar aset tetap", IMPORT),
		(("Journal Entry", "Journal Entry (opening)"), "Is Opening = Yes: saldo neraca sisanya (kas, bank "
		 "per rekening, aset tetap dan akumulasi, pajak, uang muka, hutang lain, modal, laba ditahan). Akun "
		 "piutang, hutang usaha dan persediaan JANGAN diisi lagi di sini", "Trial Balance per cut-off",
		 MANUAL + " / " + IMPORT),
	]),
	(5, "Dokumen berjalan (opsional)", "Hanya yang belum selesai di Ascend per tanggal cut-off.", [
		("Purchase Order", "Sisa qty yang belum diterima / ditagih", "PO outstanding", MANUAL),
		("Sales Order", "Sisa order trading yang belum dikirim", "SO outstanding", MANUAL),
		(["Shipping List", "Packing List"], "Job expedition yang masih berjalan", "Shipping / Packing List", MANUAL),
		("Expense Note", "Biaya job yang belum ditagih ke customer, supaya bisa ditarik ke Sales Invoice",
		 "Expense Note", MANUAL),
		("Pending Cash", "Kasbon yang belum diselesaikan", "Pending Cash", MANUAL),
	]),
]

# (report, dibandingkan dengan di Ascend, harus)
CHECK_ROWS = [
	("Trial Balance", "Trial Balance", "Sama per akun"),
	("Accounts Receivable", "Aging piutang", "Sama per customer dan per invoice"),
	("Accounts Payable", "Aging hutang", "Sama per supplier dan per invoice"),
	("Stock Balance", "Saldo inventory", "Qty dan nilai sama per item per gudang"),
	("Fixed Asset Register", "Daftar aset tetap", "Nilai buku sama per aset"),
	("General Ledger", "", "Akun Temporary Opening bersaldo 0"),
	("Account Mapping", "GL Interfaces", "Tidak ada customer, supplier, item tanpa akun efektif"),
]


def _docs(cell):
	"""Isi kolom modul -> [(doctype, label), ...]."""
	items = cell if isinstance(cell, list) else [cell]
	return [i if isinstance(i, tuple) else (i, i) for i in items]


def _phase(no, title, lead, rows):
	numbered = [(f"{no}.{i}", ", ".join(_a(d, lb) for d, lb in _docs(r[0])), *r[1:])
	            for i, r in enumerate(rows, 1)]
	return (f"<h3>Fase {no}. {title}</h3><p>{lead}</p>"
	        + _table(["No", "Modul", "Yang diisi", "Sumber di Ascend", "Cara isi"], numbered))


MODULES = (
	"".join(_phase(*p) for p in PHASES)
	+ _box("Hati hati di Fase 5", [
		"Dokumen yang di-Validate atau di-Pay membuat jurnal. Kalau nilainya sudah masuk saldo awal "
		"(Fase 4), jangan validasi lagi atau keluarkan dari saldo awal; pilih salah satu.",
		"Contoh: kasbon yang di-Pay di ERPNext membuat Dr uang muka Cr bank, jadi saldo uang muka "
		"kasbon itu tidak boleh ikut di Journal Entry opening.",
		"Data CRM (Lead, Inquiry, Quotation) diisi di aplikasi CRM, di luar menu ini.",
	], warn=True)
)


# ---------------------------------------------------------------- Tab Cek

CHECKS = (
	"<p>Jalankan semua laporan per tanggal cut-off dan bandingkan dengan Ascend. Go-live hanya bila semua cocok.</p>"
	+ _table(["Laporan ERPNext", "Bandingkan dengan Ascend", "Harus"],
	         [(_r(rep), asc, must) for rep, asc, must in CHECK_ROWS])
	+ _box("Sebelum user mulai", [
		"Uji satu transaksi per modul mengikuti Manual Book, cek jurnalnya di General Ledger.",
		"Pastikan nomor dokumen pertama sesuai seri yang diharapkan.",
		"Hentikan input di Ascend mulai tanggal sesudah cut-off supaya tidak ada transaksi ganda.",
	])
)


FAQ = _faq([
	("Kenapa piutang dan hutang lewat Opening Invoice, bukan Journal Entry?",
	 "Supaya tiap invoice Ascend jadi dokumen yang bisa dilunasi satu per satu di Payment Entry dan "
	 "muncul di aging. Journal Entry hanya memberi saldo total per akun."),
	("Akun Temporary Opening tidak nol, apa artinya?",
	 "Ada saldo awal yang belum masuk atau masuk dua kali. Bandingkan Trial Balance dengan Ascend per akun "
	 "untuk menemukan selisihnya."),
	("Apakah transaksi historis Ascend ikut dipindah?",
	 "Tidak wajib. Cara baku: saldo per cut-off saja. Riwayat tetap dibaca di Ascend."),
	("Existing Asset kok tidak membuat jurnal?",
	 "Memang begitu. Nilai aset dan akumulasi penyusutannya masuk lewat Journal Entry opening; dokumen "
	 "Asset hanya untuk menjalankan penyusutan berikutnya."),
	("Import gagal karena link tidak ditemukan?",
	 "Data yang dirujuk belum ada atau namanya beda. Ikuti urutan fase dan pakai nama persis seperti di "
	 "ERPNext (termasuk singkatan company di nama akun dan cost center)."),
	("Salah import, bagaimana menghapus?",
	 "Draft bisa dihapus dari list view (pilih semua, Delete). Dokumen yang sudah submit harus Cancel dulu."),
])


HTML = ('<div class="mb"><h2>Migration: Ascend ke ERPNext</h2>'
        '<p class="lead">Tata cara pindah ke ERPNext dan modul yang harus diisi, berurutan dari fondasi '
        'sampai saldo awal. Klik nama modul untuk membuka daftarnya.</p>'
        + _tabs("mg", [("Tata Cara", GUIDE), ("Modul", MODULES), ("Cek", CHECKS), ("FAQ", FAQ)])
        + "</div>")


# Filter list view untuk item sidebar Fase 4: yang dicek cuma dokumen saldo awal.
ROUTE_OPTIONS = {
	"Journal Entry": {"is_opening": "Yes"},
	"Stock Reconciliation": {"purpose": "Opening Stock"},
	"Asset": {"asset_type": "Existing Asset"},
}


def sidebar_items():
	"""Sidebar kiri = semua modul di tab Modul + laporan tab Cek, per fase, supaya user
	tidak perlu mencari ke menu lain. Doctype yang sudah muncul di fase sebelumnya
	tidak diulang (Company di Fase 1 dan 2)."""
	items, seen = [L("Panduan", "Workspace", SIDEBAR), L("Data Import", "DocType", "Data Import")], set()
	for no, title, _lead, rows in PHASES:
		items.append((SB, f"Fase {no} {title}"))
		for row in rows:
			for doctype, label in _docs(row[0]):
				if doctype not in seen:
					seen.add(doctype)
					items.append(L(label, "DocType", doctype, ROUTE_OPTIONS.get(doctype)))
	items.append((SB, "Fase 6 Cek"))
	items += [L(rep, "Report", rep) for rep, *_ in CHECK_ROWS]
	return items


def ensure_migration():
	ensure_book(SIDEBAR, [{"type": "custom_block", "data": {"custom_block_name": SIDEBAR, "col": 12}}],
	            [], ICON, landing_html=HTML)
	_ensure_sidebar({"label": SIDEBAR, "icon": ICON, "items": sidebar_items()})

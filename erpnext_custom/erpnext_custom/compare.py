"""Menu "Compare" di desk: cara input Ascend dibanding ERPNext, per modul.

Bentuk dan mekanismenya sama dengan Manual Book (manual_book.ensure_book): satu
Workspace per modul berisi satu Custom HTML Block, tiga tab Ascend / ERPNext /
Perbedaan. Konten hidup DI FILE INI; ensure_compare() menimpa DB tiap migrate.

Sumber sisi Ascend: hasil decompile D:\\System_Ascend\\Decompiled (FrontEnd.BS.*,
procs DB_AS_CIMI) dan jumlah baris tabel CIMI untuk menandai fitur yang tidak
dipakai. Sisi ERPNext mengikuti Manual Book dan kode erpnext_custom / erp.
"""

from erpnext_custom.manual_book import _ARROW, _node, _step, _table, _tabs, ensure_book

SIDEBAR = "Compare"
ICON = "git-compare"


def _flow(*nodes):
	return '<div class="flow">' + _ARROW.join(_node(*n) for n in nodes) + "</div>"


def _box(title, items, warn=False):
	lis = "".join(f"<li>{i}</li>" for i in items)
	return f'<div class="box{" warn" if warn else ""}"><div class="bt">{title}</div><ul>{lis}</ul></div>'


def _compare(key, title, lead, ascend, erpnext, rows, notes):
	diff = _table(["Hal", "Ascend", "ERPNext"], rows) + _box("Yang perlu diingat saat pindah", notes, warn=True)
	return ('<div class="mb">' + f"<h2>{title}</h2>" + f'<p class="lead">{lead}</p>'
	        + _tabs(key, [("Ascend", ascend), ("ERPNext", erpnext), ("Perbedaan", diff)]) + "</div>")


# Pola umum yang berlaku di hampir semua modul; dipakai di baris tabel Perbedaan.
ASCEND_POSTING = ("Tidak saat Save. Jurnal dibuat lewat GL &gt; Posting/Unposting Transactions "
                  "(pilih jenis dokumen + rentang tanggal, Post to GL)")
ERP_POSTING = "Langsung saat Validate, per dokumen, tanpa langkah posting terpisah"


# ---------------------------------------------------------------- Basic / Setup

BASIC_ASCEND = (
	_flow(("1", "GL Account", "Chart of Accounts", "Kode, induk, tipe, kategori"),
	      ("2", "GL Interfaces", "InterfaceCode ke akun", "Akun default semua dokumen"),
	      ("3", "Master", "Customer, Supplier, Bank, Item", "Tab GL Interface menimpa default"),
	      ("4", "Numbering", "SH_DocumentNumbering", "Format nomor per jenis dokumen"))
	+ _step(1, "GL Account (Chart of Accounts)", [
		"Isi Account code, Account name, Parent account.",
		"Type: header neraca / header laba rugi / account / retained earning. Hanya tipe account yang bisa dijurnal.",
		"Category (Cash, Bank, Receivable, dll), Normal balance, Require cost center, Cash Flow Code.",
	])
	+ _step(2, "GL Interfaces", [
		"Satu tabel pusat: InterfaceCode dipetakan ke akun + department. Contoh: Receivable, Payable, "
		"AdvanceReceivable, AdvancePayable, BankCharges, DeductedPPh, PurchaseTax, SalesTax, "
		"ExchangeRateGainLoss, BiayaMeterai, Receivable.PendingCash, RetainedEarning.",
		"Dokumen mencari akun berurutan: baris, item, kategori stok, lalu GL Interface.",
	], "Ini sumber akun default seluruh jurnal otomatis Ascend.")
	+ _step(3, "Cost Center", ["Manage Cost Centers: pohon kode segmen, centang Can be used in transactions."])
	+ _step(4, "Customer dan Supplier", [
		"Customer: kode, nama, alamat, NPWP, term, credit limit, currency, collector. Tab GL Interface: "
		"Receivable, ReceivableCheck, AdvanceReceivable.",
		"Supplier: kode, nama, grup, NPWP, PPh, term. Tab Accounts = rekening bank supplier. Tab GL: "
		"Payable, PayableCheck, AdvancePayable.",
	])
	+ _step(5, "Bank Account", [
		"Master tersendiri: kode, nama bank, no rekening, pemilik, currency, akun GL.",
		"PV Type / RV Type menentukan seri nomor voucher bank itu.",
	])
	+ _step(6, "Inventory Item dan kategori", [
		"Type (Stock, NonStock, Service, Assembly, Bundle), Category, Family, UOM 1 sampai 4.",
		"Tab GL Interface per item: Inventory, Purchase, PurchaseReturn, Usage, Adjustment, COG, Sales.",
		"Akun per kategori x pemakai di Stock Categories Mapping.",
	])
	+ _step(7, "Master Expedition", [
		"Expense Class (akun biaya + akun suspend), Revenue Types (akun pendapatan), Packing List Types, "
		"Expense Rules (harga otomatis per class).",
	])
	+ _step(8, "Document Numbering", [
		"Per jenis dokumen: Format, NextCounter, ResetBy. Token $YYYY, $YY, $MM, $MR (bulan romawi), "
		"$VT (tipe voucher), $BAC (kode bank).",
	])
)

BASIC_ERP = (
	_flow(("1", "Chart of Accounts", "Daftar akun per company", "Sumber semua akun"),
	      ("2", "Company", "Akun default", "Jaring pengaman terakhir"),
	      ("3", "Item / Item Group", "Akun persediaan dan beban", "Item menang atas grup"),
	      ("4", "Invoice Type / Setting", "Pendapatan, potongan, kasbon", "Per company"))
	+ _step(1, "Chart of Accounts", [
		"Accounting &gt; Chart of Accounts, per company. Akun group tidak bisa dijurnal.",
		"Account Type menentukan pemakaian: Bank, Stock, Receivable, Payable, dll.",
	])
	+ _step(2, "Company: akun default", [
		"Default Receivable, Payable, Bank/Cash, Inventory, COGS, Stock Adjustment, Exchange Gain/Loss, "
		"Default Cost Center.",
	], "Padanan GL Interfaces Ascend, tetapi hanya untuk akun yang tidak disebut dokumennya.")
	+ _step(3, "Item dan Item Group", [
		"Item Defaults per company: Default Inventory Account dan Default Expense Account. Isi di Item Group, "
		"Item hanya untuk pengecualian.",
		"Biaya expedition juga Item (grup Expense) dengan Default Expense Account dan Default Reimbursement.",
	])
	+ _step(4, "Invoice Type", [
		"Selling Settings &gt; Invoice Type: Behavior (Normal / Reimburse / Trading), Income Account, "
		"Discount Account, Type No (kode nomor), Roles.",
	], "Padanan Revenue Types + Receivable.&lt;InvoiceType&gt; di Ascend.")
	+ _step(5, "ERPNext Custom Setting dan Mode of Payment", [
		"Akun PPN, PPh, Materai penjualan dan pembelian, plus akun potongan Payment Entry.",
		"Mode of Payment &gt; Accounts: akun bank default per company.",
	])
	+ _step(6, "Rekening bank", [
		"Bukan master terpisah: satu akun bertipe Bank di Chart of Accounts.",
		"Kata pertama nama akun jadi kode bank di nomor RV/PV; currency akun = mata uang pembayaran.",
	])
	+ _step(7, "Customer, Supplier, Pending Cash Type", [
		"Customer / Supplier: tabel Accounts per company bila akun piutang/hutang beda dari default Company.",
		"Pending Cash Type: Advance Account (akun uang muka kasbon).",
	])
	+ _step(8, "Penomoran", [
		"Naming series per doctype, diatur di Document Naming Settings. Contoh EXP/TIPE/CMI/YY, "
		"RV/MDR/CMI/2026/VII/0001.",
	])
)

BASIC_HTML = _compare(
	"cba", "Compare Basic: Setup Akun dan Master",
	"Di mana akun dan master disiapkan sebelum transaksi. Ascend memusatkan akun default di GL "
	"Interfaces; ERPNext menyebarnya ke Company, Item Group, Invoice Type, dan setting.",
	BASIC_ASCEND, BASIC_ERP,
	[
		("Akun default", "GL Interfaces (satu tabel InterfaceCode)", "Company + ERPNext Custom Setting + Mode of Payment"),
		("Urutan cari akun", "Baris, item, kategori stok, GL Interface", "Item, Item Group, Company"),
		("Akun pendapatan jasa", "Revenue Types / ServiceInvoice.Revenue.&lt;Type&gt;", "Invoice Type (Selling Settings) atau akun Item"),
		("Akun biaya job", "Expense Class", "Item grup Expense (dulu Expense Class)"),
		("Rekening bank", "Master Bank Account + akun GL", "Akun bertipe Bank di Chart of Accounts"),
		("Akun per customer/supplier", "Tab GL Interface di master", "Tabel Accounts di master"),
		("Penomoran", "SH_DocumentNumbering, token $YY/$MR/$BAC", "Naming series per doctype"),
	],
	[
		"Akun di Company hanya dipakai bila dokumen tidak menyebut akunnya; jangan dianggap sama persis dengan GL Interfaces.",
		"Item Group baru wajib diisi Default Inventory Account, tidak ada cadangan seperti interface Inventory.Value di Ascend.",
		"Rekening bank baru cukup dibuat sebagai akun Bank, tapi nama akunnya menentukan kode nomor RV/PV.",
	])


# ---------------------------------------------------------------- Expedition

EXP_ASCEND = (
	_flow(("EST", "Estimation", "Rate per customer", "Approve, tanpa jurnal"),
	      ("PL", "Packing List", "Job per shipment / container", "Tanpa jurnal"),
	      ("EN", "Expense Note", "Biaya vendor per container", "Post to GL: Dr Biaya / Cr Hutang"),
	      ("INV", "Service Invoice", "Tagihan customer / agent", "Post to GL: Dr Piutang / Cr Pendapatan"),
	      ("RV/PV", "Voucher", "Terima / bayar", "Lihat Compare Payment"))
	+ _step(1, "Estimation", [
		"Isi Customer, Type, Quotation No/date, masa berlaku, Tax included (%), Est. Profit, Sales Person.",
		"Tab Revenue / Expense / Reimburse: Type, Amount, Per Doc / By Qty, Jalur, Area, Lokasi Sandar, "
		"Shipping Line, Destination, Cont. Size, Supplier, Karantina.",
		"Save lalu Approve (role Exp.Estimation.Approve).",
	])
	+ _step(2, "Packing List", [
		"Header: Packing List Type, Expedition Comp., Customer + Est ID, Agent + Agent Est ID, Vessel, "
		"Voyage, Shipping line, Origin, Destination, ETD/ETA/ETB.",
		"Tab Basic Info: Shipment Type, SalesPerson, Jenis Karantina, BL No/Date, No AJU, Include Agency Fee.",
		"Tab Details: satu baris per container (Container No, Seal No, Size, Est. ID, tagih ke Agent/Customer). "
		"Bisa Paste from Excel.",
		"Dari Packing List: Create Expense Note, Create Pending Cash V2, Create Receipt/Payment Voucher, Create AR Note.",
	], "Tidak menjurnal. Tutup job dengan Close.")
	+ _step(3, "Expense Note", [
		"Header: Type, Supplier, Class (THC, STORAGE, BONGKAR, dll), Currency + kurs, PPN, PPh, Not Crd.",
		"Biaya ditagih ulang: tab Remarks centang Reimburse to Customer + pilih customer.",
		"Add: muncul container yang belum punya biaya untuk Class itu. Harga terisi dari Expense Rules; "
		"Distribute Cost membagi total ke baris.",
		"Save, Check, Validate, lalu Post to GL. No faktur vendor lewat Edit Tax Invoice Number.",
		"Refund / koreksi minus: Expense Note (Minus).",
	], "Dr akun Expense Class (atau akun suspend) + PPN / Cr Hutang supplier. Reimburse: Dr Piutang "
	   "Reimburse Belum Ditagih.")
	+ _step(4, "Service Invoice (Customer / Expedition / Agent)", [
		"Header: Invoice Type, Customer, Currency, Tax %, Voyage No, Tax Invoice No.",
		"Add: pilih container outstanding customer itu. Baris pendapatan terbentuk otomatis dari baris "
		"Revenue di Estimation (disaring jalur, area, size, karantina).",
		"Validate, lalu Post to GL.",
		"Penagihan reimburse ditempuh lewat Invoice Receipt (AR); tab Reimbursement di invoice tidak dipakai di CIMI.",
	], "Dr Piutang / Cr pendapatan per Revenue Type + PPN Keluaran.")
	+ _step(5, "Pembayaran", [
		"Receipt Voucher dari customer, Payment Voucher ke vendor: Add Items, pilih invoice / Expense Note (tipe EX).",
	])
)

EXP_ERP = (
	_flow(("EST", "Estimation (CRM)", "Rate per customer", "Tanpa jurnal"),
	      ("SL/PL", "Shipping List / Packing List", "Job per shipment", "Tanpa jurnal"),
	      ("EN", "Expense Note", "Biaya vendor", "Validate: Dr Biaya / Cr Hutang"),
	      ("SI", "Sales Invoice", "Tagihan customer", "Validate: Dr Piutang / Cr Pendapatan"),
	      ("PE", "Payment Entry", "Terima / bayar", "Lihat Compare Payment"))
	+ _step(1, "Estimation", [
		"Dibuat di aplikasi CRM (Inquiry, Quotation, Estimation), baris revenue dan expense per rute.",
		"Packing List menyimpan Estimation-nya; dipakai sebagai plafon biaya di Expense Note.",
	])
	+ _step(2, "Shipping List / Packing List", [
		"Shipping List: satu dokumen per shipment, berisi BL dan container; status bayar per BL terpantau otomatis.",
		"Packing List: job barang dengan rincian container dan Estimation.",
		"EN, SI, dan Pending Cash menaut ke job lewat section Connection.",
	], "Tidak menjurnal.")
	+ _step(3, "Expense Note", [
		"Expedition &gt; Expense Note &gt; + Add. Isi Type (menentukan nomor EXP/TIPE/CMI/YY) dan Supplier.",
		"Isi biaya lewat panel Biaya: per item biaya dan per container. Label Sesuai / Melebihi / Di luar "
		"Estimation muncul dari Estimation job-nya.",
		"PPN / PPh / Discount / Materai bila ada. Biaya ditagih ulang: centang Reimburse to Customer + customer.",
		"Save lalu Validate. Journal Entry terbentuk saat itu juga.",
		"Refund dari vendor: dokumen Expense Refund (Add Transaction, Validate).",
	], "Dr akun beban item (reimburse: akun Default Reimbursement) / Cr Hutang vendor.")
	+ _step(4, "Proforma Invoice (opsional)", [
		"Nomor PR-INV/, form sama dengan Sales Invoice, tidak menjurnal. Tombol Import di Sales Invoice menyalinnya.",
	])
	+ _step(5, "Sales Invoice", [
		"Invoice Type menentukan akun, nomor, dan behavior.",
		"Behavior Normal: baris jasa diisi di Items.",
		"Behavior Reimburse: tombol Get Expense Notes menarik EN reimburse customer itu. Centang Markup untuk "
		"baris jasa tambahan.",
		"Wajib Invoice Type, Invoice Type No, Invoice Date, Customer Address. Save lalu Validate.",
	], "Dr Piutang / Cr pendapatan Invoice Type; reimburse Cr akun Reimbursement (pass-through).")
	+ _step(6, "Pembayaran", [
		"Bayar vendor: Payment Entry Pay + tombol Tarik Expense Note.",
		"Terima customer: dari Sales Invoice, Create &gt; Payment.",
	])
)

EXP_HTML = _compare(
	"cex", "Compare Expedition",
	"Job expedition dari estimasi sampai tagihan. Urutan dokumennya sama; bedanya di kapan jurnal "
	"terbentuk, cara menagih reimburse, dan dari mana harga tagihan diambil.",
	EXP_ASCEND, EXP_ERP,
	[
		("Estimation", "Modul Expedition, Approve", "Aplikasi CRM (sinkron ke EXP_Estimation)"),
		("Dokumen job", "Packing List", "Shipping List / Packing List"),
		("Baris biaya", "Add container per Expense Class, harga dari Expense Rules", "Panel Biaya per item x container, dicek ke plafon Estimation"),
		("Status Expense Note", "Save, Check, Validate, Post to GL", "Save, Validate (jurnal langsung)"),
		("Refund vendor", "Expense Note (Minus)", "Expense Refund"),
		("Tagihan jasa", "Service Invoice, baris revenue otomatis dari Estimation", "Sales Invoice behavior Normal, baris diisi di Items"),
		("Tagihan reimburse", "Invoice Receipt (AR)", "Sales Invoice behavior Reimburse + Get Expense Notes"),
		("Proforma", "Field No. PI di Sales Order", "Doctype Proforma Invoice (PR-INV/)"),
		("Kapan jurnal terbentuk", ASCEND_POSTING, ERP_POSTING),
	],
	[
		"Tidak ada langkah Post to GL di ERPNext: begitu Expense Note di-Validate, hutang vendor sudah ada dan bisa dibayar.",
		"Reimburse tidak lagi lewat dokumen terpisah: Sales Invoice dengan Invoice Type behavior Reimburse menarik EN-nya.",
		"EN yang sudah ditarik ke invoice terkunci; lepas dari invoice dulu sebelum direvisi.",
	])


# ---------------------------------------------------------------- Selling / Trading

SELL_ASCEND = (
	_flow(("SO", "Sales Order", "Order customer", "Approve, tanpa jurnal"),
	      ("SI", "Sales Invoice", "Tagihan", "Post to GL: Dr Piutang / Cr Penjualan"),
	      ("RV", "Receipt Voucher", "Terima pembayaran", "Dr Bank / Cr Piutang"))
	+ _step(1, "Sales Order", [
		"Header: Customer, SO Type (harus cocok dengan tipe customer), Currency, Terms, Inclusive, Cust. PO, Sales person.",
		"Items: item, qty, UOM, price, disc. Tombol Quotation menarik baris dari penawaran.",
		"Tab Advanced: delivery terms, destination, container, ETD/ETA, down payment. Tab Proforma Invoice: Generate nomor.",
		"Save, Approve, Mark as Checked / Verify, lalu Transfer to Invoice. Close / Reopen.",
	])
	+ _step(2, "Pengiriman", [
		"Layar Goods Delivery Note dan SPB / Picking List tersedia, tetapi tabelnya kosong di CIMI: tidak dipakai.",
	])
	+ _step(3, "Sales Invoice", [
		"Import from Sales Order, atau isi item manual. Header: Customer, Invoice Type, Currency, Terms, Tax Inv. #.",
		"Validate, lalu Post to GL. Input Bukti Potong PPh dari menu dokumen.",
	], "Dr Piutang / Cr Sales + PPN Keluaran. HPP hanya bila setting PostCOGS menyala.")
	+ _step(4, "Retur", [
		"Sales Return: editor yang sama, baris dipilih dari invoice, Return Reason wajib.",
		"Dalam praktik pengurang tagihan lebih sering lewat AR Note / AR Discount Note.",
	], "Dr Sales Return / Cr Piutang.")
)

SELL_ERP = (
	_flow(("SO", "Sales Order", "Order customer", "Submit, tanpa jurnal"),
	      ("PICK", "Pick List", "Perintah ambil barang (opsional)", "Tanpa jurnal"),
	      ("DN", "Delivery Note", "Surat jalan", "Stok keluar: Dr HPP / Cr Persediaan"),
	      ("SI", "Sales Invoice", "Tagihan", "Validate: Dr Piutang / Cr Penjualan"),
	      ("PE", "Payment Entry", "Terima pembayaran", "Dr Bank / Cr Piutang"))
	+ _step(1, "Sales Order", [
		"Trading &gt; Sales Order: Customer, Delivery Date, Items (item, qty, rate), Tax / PPh / Materai.",
		"Save lalu Submit. Penawaran tim sales dibuat di CRM.",
	])
	+ _step(2, "Pick List (opsional)", [
		"Dari SO: Create &gt; Pick List. Rak asal per baris, qty tidak boleh melebihi stok rak. Submit.",
	])
	+ _step(3, "Delivery Note", [
		"Dari Pick List atau langsung dari SO. Tombol Suggest Rack mengisi rak keluar FIFO. Submit.",
	], "Stok berkurang dan HPP dibukukan di sini.")
	+ _step(4, "Sales Invoice", [
		"Dari DN (atau SO untuk jasa): Create &gt; Sales Invoice. Invoice Type = Trading, nomor C/T/####/CMI/YY.",
		"Update Stock dibiarkan kosong bila sudah ada DN. Save lalu Validate.",
	], "Dr Piutang / Cr Penjualan Barang Dagang.")
	+ _step(5, "Retur", [
		"Barang kembali: Sales Return (Delivery Note retur). Pengurang tagihan: Credit Note (Sales Invoice retur).",
	])
)

SELL_HTML = _compare(
	"cse", "Compare Selling dan Trading",
	"Penjualan barang dan jasa non-expedition. Ascend di CIMI langsung SO ke invoice; ERPNext memisah "
	"surat jalan supaya stok dan HPP keluar saat barang keluar.",
	SELL_ASCEND, SELL_ERP,
	[
		("Order", "Sales Order: Approve, Verify, Transfer to Invoice", "Sales Order: Submit"),
		("Surat jalan", "Ada layarnya, tidak dipakai di CIMI", "Pick List (opsional) dan Delivery Note"),
		("Stok dan HPP", "Di invoice, hanya bila PostCOGS menyala", "Di Delivery Note"),
		("Invoice", "Import from Sales Order", "Create &gt; Sales Invoice dari DN / SO, Invoice Type wajib"),
		("Retur barang", "Sales Return (AR_Invoices IsInvoice=0)", "Delivery Note retur (Sales Return)"),
		("Pengurang tagihan", "AR Note / AR Discount Note", "Credit Note (Sales Invoice retur) atau AR Note"),
		("Kapan jurnal terbentuk", ASCEND_POSTING, ERP_POSTING),
	],
	[
		"Barang stock wajib lewat Delivery Note (atau centang Update Stock di invoice bila tanpa DN), kalau tidak stok tidak berkurang.",
		"Jangan centang Update Stock bila DN sudah ada: stok terpotong dua kali.",
		"Customer trading wajib punya Address sebelum invoice bisa disimpan.",
	])


# ---------------------------------------------------------------- Purchase

PUR_ASCEND = (
	_flow(("PO", "Purchase Order", "Pesanan ke supplier", "Approve, tanpa jurnal"),
	      ("PI", "Purchase Invoice", "Barang diterima (AP_Purchases)", "Stok naik. Dr Persediaan / Cr Hutang Belum Ditagih"),
	      ("IR", "Invoice Receipt (AP)", "Faktur supplier diterima", "Dr Hutang Belum Ditagih + PPN / Cr Hutang Usaha"),
	      ("PV", "Payment Voucher", "Bayar supplier", "Dr Hutang / Cr Bank"))
	+ _step(1, "Purchase Order", [
		"Header: Supplier, PO Type, Deliver to (gudang), Currency + kurs, Pym. term, Allow partial shp.",
		"Baris: Add (item, qty, UOM, price, discount, cost center), Import from Purchase Request, atau Query by Min/Max.",
		"Tab Extra Charges: freight, bea masuk, clearance, masing-masing dengan supplier sendiri.",
		"Post to Fixed Asset as: None / CIP / Asset untuk pembelian aset.",
		"Check, Approve (Manager), Approve (Director) sesuai limit, lalu Transfer to Inventory Receipt. Close PO.",
	], "Terkunci setelah approve atau dipakai.")
	+ _step(2, "Purchase Invoice (penerimaan barang)", [
		"Add from Purchase Order: baris PO outstanding. Isi Reference no., Purchase Type, gudang.",
		"Extra Charges dan Distr. Shp. Cost membagi biaya tambahan ke baris.",
		"Check lalu Validate. Convert to Assets untuk baris aset.",
		"Goods Receiving sebagai dokumen terpisah ada, tetapi kosong di CIMI.",
	], "Stok naik saat disimpan. Dr Persediaan per item / Cr Hutang Belum Ditagih (Payable.UninvoicedGoods).")
	+ _step(3, "Invoice Receipt (AP)", [
		"Pilih supplier, Add: centang PI-PI supplier itu. Isi Tax Invoice No/Date, Rounding.",
		"Validate.",
	], "Dr Hutang Belum Ditagih + PPN Masukan / Cr Hutang Usaha supplier.")
	+ _step(4, "Purchase Return", [
		"Editor yang sama dengan PI: Add from Purchase Invoice. Stok turun saat disimpan.",
	], "Dr Hutang / Cr akun Purchase Return; selisih harga ke PurchaseReturn.Variance.")
)

PUR_ERP = (
	_flow(("PO", "Purchase Order", "Pesanan ke supplier", "Validate, tanpa jurnal"),
	      ("PI", "Purchase Invoice", "Barang + faktur sekaligus", "Stok naik. Dr Persediaan + PPN / Cr Hutang Usaha"),
	      ("GR", "Goods Receive", "Taruh barang di bin (WMS)", "Tanpa jurnal"),
	      ("PE", "Payment Entry", "Bayar supplier", "Dr Hutang / Cr Bank"))
	+ _step(1, "Purchase Order", [
		"Purchase &gt; Purchase Order: Type (wajib, mis. TRD), Supplier, Items (item, qty, rate, warehouse).",
		"Save lalu Validate.",
	])
	+ _step(2, "Purchase Invoice", [
		"Dari PO: Create &gt; Purchase Invoice. Isi nomor dan tanggal faktur supplier, PPN / PPh.",
		"Stok diakui di PI: Update Stock dinyalakan otomatis untuk baris bergudang, tidak perlu dicentang.",
		"Baris sparepart: isi Vehicle = langsung biaya kendaraan + kartu Maintenance; isi Warehouse = persediaan.",
		"Item aset (Is Fixed Asset): isi Asset Location, record Asset terbentuk otomatis.",
		"Save lalu Validate.",
	], "Dr Persediaan / Beban + PPN Masukan / Cr Hutang Usaha. Tidak ada Hutang Belum Ditagih.")
	+ _step(3, "Goods Receive (gudang)", [
		"Warehouse &gt; Goods Receive: Tarik dari Purchase Invoice, Suggest Bin, simpan.",
	], "Hanya peta letak barang di rak/bin, tidak mengubah stok maupun jurnal.")
	+ _step(4, "Retur", [
		"Purchase &gt; Debit Note (Purchase Invoice retur): stok dan hutang sama-sama berkurang.",
	])
)

PUR_HTML = _compare(
	"cpu", "Compare Purchase",
	"Ascend CIMI memakai tiga dokumen (PO, PI, Invoice Receipt AP) dengan akun perantara Hutang Belum "
	"Ditagih. ERPNext cukup dua (PO, PI): barang dan faktur diakui di dokumen yang sama.",
	PUR_ASCEND, PUR_ERP,
	[
		("Pesanan", "PO: Check, Approve Manager, Approve Director", "PO: Validate"),
		("Barang masuk", "Purchase Invoice (AP_Purchases)", "Purchase Invoice (Update Stock otomatis)"),
		("Faktur supplier", "Invoice Receipt (AP), dokumen terpisah", "Di Purchase Invoice yang sama"),
		("Akun perantara", "Payable.UninvoicedGoods", "Tidak ada"),
		("Sparepart langsung pakai", "Inventory Usage terpisah", "Baris PI ber-Vehicle langsung jadi biaya + kartu Maintenance"),
		("Letak barang di rak", "Tidak ada", "Goods Receive (bin), tanpa jurnal"),
		("Retur", "Purchase Return (editor PI)", "Debit Note (PI retur)"),
		("Kapan jurnal terbentuk", ASCEND_POSTING, ERP_POSTING),
	],
	[
		"Jangan mencari dokumen Invoice Receipt (AP) di ERPNext: nomor dan tanggal faktur supplier diisi langsung di Purchase Invoice.",
		"Huruf PI di kedua sistem sama-sama Purchase Invoice dan sama-sama menaikkan stok.",
		"Koreksi PI: Invalidate (balik draft) atau Void, ditolak bila sudah dibayar Payment Entry.",
	])


# ---------------------------------------------------------------- Stock

STOCK_ASCEND = (
	_flow(("ADJ", "Inventory Adjustment", "Koreksi qty / nilai", "Approve: Persediaan vs AdjustmentVariance"),
	      ("TRF", "Goods Transfer", "Pindah gudang", "Stok pindah saat Receive"),
	      ("USE", "Inventory Usage", "Pemakaian internal", "Dr Beban pemakaian / Cr Persediaan"))
	+ _step(1, "Inventory Adjustment", [
		"Header: Adjustment date, Type, Currency.",
		"Baris: Item, Warehouse, Adjust quantity (Before / Adjust by / After), nilai otomatis atau manual.",
		"Approve: stok baru bergerak. Calculate COG, Void.",
	], "Persediaan lawan akun Adjustment (baris, item, kategori, AdjustmentVariance).")
	+ _step(2, "Stock opname", [
		"Utilities &gt; Stock Take: scan barcode / Browse, gudang, qty hasil hitung.",
		"Hasilnya tidak otomatis jadi koreksi: selisih dibukukan lewat Inventory Adjustment.",
	])
	+ _step(3, "Goods Transfer", [
		"Diawali Goods Transfer Request. Header: From warehouse, To warehouse, Vehicle No, Driver, Expected Delivery.",
		"Baris: Item, Qty, Used by. Validate, lalu Receive di gudang tujuan.",
	], "Tanpa jurnal kecuali antar grup akun atau gudang transit.")
	+ _step(4, "Inventory Usage", [
		"Header: Used by (department), Warehouse, Purpose, Project, Employee.",
		"Baris: Item, Qty, Cost Center, Asset / kendaraan.",
		"Approve (HoD), Approve (Warehouse), Validate. Kembalian lewat Inventory Usage Return.",
	], "Dr akun pemakaian (kategori x pemakai) / Cr Persediaan.")
	+ _step(5, "Melihat stok", [
		"Tab Balance dan History and Statistics di Inventory Item (kartu stok), Warehouse balance.",
		"Saldo dihitung dari dokumen saat dibuka, tidak ada buku besar stok tersendiri.",
	])
)

STOCK_ERP = (
	_flow(("SR", "Stock Reconciliation", "Opname / koreksi", "Selisih ke Penyesuaian Persediaan"),
	      ("SE-T", "Material Transfer", "Pindah gudang / rak", "Tanpa efek laba rugi"),
	      ("SE-I", "Material Issue", "Pemakaian internal", "Dr Beban item / Cr Persediaan"))
	+ _step(1, "Stock Reconciliation (opname dan adjustment)", [
		"Warehouse &gt; Stock Opname &gt; + Add: per baris item + gudang, isi Qty dan / atau Valuation Rate hasil hitung.",
		"Sistem menghitung selisihnya. Save lalu Submit.",
		"Koreksi isi bin (kurangi, kosongkan, ganti item): Warehouse &gt; Adjustment, Stock Reconciliation-nya dibuat otomatis.",
	], "Selisih otomatis ke akun Penyesuaian Persediaan.")
	+ _step(2, "Material Transfer", [
		"Inventory &gt; Stock Entry type Material Transfer (atau Warehouse &gt; Rack Transfer): Source dan Target Warehouse. Submit.",
	])
	+ _step(3, "Material Issue", [
		"Stock Entry type Material Issue: Source Warehouse, item, qty. Submit.",
		"Sparepart kendaraan dari gudang: lewat Fleet &gt; Maintenance, Stock Entry-nya terbit sendiri.",
	], "Dr akun beban Item Group / Cr Persediaan.")
	+ _step(4, "Melihat stok", [
		"Stock Balance, Stock Ledger, Stock per Rak, Stock Ageing. Isi bin di Warehouse &gt; Isi Bin.",
	], "Setiap mutasi tercatat di Stock Ledger saat Submit.")
)

STOCK_HTML = _compare(
	"cst", "Compare Stock",
	"Koreksi, pindah, dan pemakaian barang. Ascend memakai approval berlapis dan hitung saldo dari "
	"dokumen; ERPNext mencatat setiap mutasi di Stock Ledger saat Submit.",
	STOCK_ASCEND, STOCK_ERP,
	[
		("Opname", "Stock Take lalu Inventory Adjustment manual", "Stock Reconciliation: isi qty fisik, selisih otomatis"),
		("Koreksi qty", "Inventory Adjustment (Adjust by)", "Stock Reconciliation / Warehouse Adjustment"),
		("Pindah gudang", "Goods Transfer Request, Transfer, Receive", "Stock Entry Material Transfer / Rack Transfer"),
		("Pemakaian", "Inventory Usage, Approve HoD + Warehouse", "Stock Entry Material Issue / Fleet Maintenance"),
		("Akun persediaan", "Item, kategori, Stock Categories Mapping", "Item Group (Item menang bila diisi)"),
		("Rak dan bin", "Tidak ada", "Master Rak / Bin, Goods Receive, Replan"),
		("Saldo stok", "Dihitung dari dokumen saat dibuka", "Stock Ledger"),
	],
	[
		"Stock Reconciliation diisi qty AKHIR hasil hitung, bukan selisihnya seperti Adjust by di Ascend.",
		"Rak/bin di ERPNext bukan gudang: pindah bin tidak mengubah stok maupun jurnal.",
		"Item Group tanpa Default Inventory Account membuat transaksi ditolak.",
	])


# ---------------------------------------------------------------- Payment

PAY_ASCEND = (
	_flow(("RV", "Receipt Voucher", "Terima dari customer", "Dr Bank / Cr Piutang"),
	      ("PV", "Payment Voucher", "Bayar supplier / vendor", "Dr Hutang / Cr Bank"),
	      ("EXP", "Expense/Other", "Biaya / pendapatan langsung", "Tanpa invoice"))
	+ _step(1, "Header voucher", [
		"Customer / Supplier, tanggal, Method: Cash / Transfer / Check (giro) / Card / WriteOff.",
		"Cash/Bank account, Currency + kurs, Amount paid, detail transfer atau cek.",
		"Potongan di header: Bank charges 1 dan 2, PPh + jenis, Tax, Meterai.",
	])
	+ _step(2, "Pilih dokumen yang dilunasi", [
		"Add Items: daftar outstanding party itu (SI, PI, Expense Note tipe EX, AR/AP Note), centang lalu Total selected.",
		"Tiap baris: Payment Details (Amount paid, Debit / Credit note, Allocation date, PPh, Disc %, Less / Over paid).",
	])
	+ _step(3, "Biaya langsung dan kasbon", [
		"Centang Expense/Other (PV) atau Income/Other (RV): isi baris Expense / Revenue type, qty, harga, akun, department.",
		"Tab Other/Pnd. Cash: tarik Pending Cash V2 sebagai pengurang bank.",
	])
	+ _step(4, "Status", [
		"PV: Save, Approve, Checked, Pay Out. RV: Validate.",
		"Jurnal dibuat otomatis saat Save (setting ARAP.AutoPosting), kecuali harus diverifikasi dulu.",
		"Nomor per bank lewat PV Type / RV Type rekeningnya.",
	], "Satu jurnal: Dr Hutang per dokumen / Cr Bank (mis. PV/CAB/1487). PV uang muka: Dr Uang Muka / Cr Bank, lalu saat dialokasikan Dr Hutang / Cr Uang Muka. "
	   "Selisih kurs ke ExchangeRateGainLoss.")
)

PAY_ERP = (
	_flow(("RV", "Payment Entry Receive", "Terima dari customer", "Dr Bank / Cr Piutang"),
	      ("PV", "Payment Entry Pay", "Bayar supplier / vendor", "Dr Hutang / Cr Bank"),
	      ("EI", "Expense / Income", "Biaya / pendapatan langsung", "Tanpa party"))
	+ _step(1, "Terima / bayar invoice", [
		"Dari SI / PI tervalidasi: Create &gt; Payment, tipe terisi otomatis.",
		"Periksa Account Paid To / From dan alokasi di tabel References.",
	])
	+ _step(2, "Bayar Expense Note, AP / AR Note", [
		"Payment Entry Pay, Supplier, tombol Tarik Expense Note. AP / AR Note lewat Add Items.",
		"Potongan Tax, PPh, Materai, Admin, CN-DN diisi di field-nya, akunnya dari ERPNext Custom Setting.",
	])
	+ _step(3, "Valas", [
		"Pilih Account Paid From = rekening valas LEBIH DULU, isi kurs, baru tarik tagihannya.",
	], "Selisih kurs otomatis ke akun Selisih Kurs.")
	+ _step(4, "Kasbon, biaya langsung, settlement", [
		"Add Pending Cash: kasbon Paid jadi sumber dana.",
		"Centang Expense / Income: baris akun + nominal, penerima di Pay To.",
		"Mode of Payment = Settlement + Settlement Account: pelunasan tanpa bank (offset).",
	])
	+ _step(5, "Status", [
		"Save lalu Validate; Invalidate / Void untuk koreksi.",
		"Nomor RV/PV + kode bank (kata pertama nama akun) + CMI + tahun + bulan romawi.",
	], "Satu jurnal: Dr Hutang / Cr Bank, sama dengan Ascend.")
)

PAY_HTML = _compare(
	"cpa", "Compare Payment Entry",
	"Receipt Voucher dan Payment Voucher Ascend menjadi satu dokumen Payment Entry (Receive / Pay). "
	"Fiturnya hampir sejajar: tarik dokumen, potongan, valas, kasbon, biaya langsung.",
	PAY_ASCEND, PAY_ERP,
	[
		("Dokumen", "Receipt Voucher / Payment Voucher", "Payment Entry Receive / Pay"),
		("Pilih dokumen", "Add Items, centang outstanding", "References (SI/PI), Tarik Expense Note, Add Items (AP/AR Note)"),
		("Potongan", "Bank charges, PPh, Tax, Meterai di header", "Tax, PPh, Materai, Admin, CN-DN"),
		("Kasbon", "Tab Other/Pnd. Cash", "Section Pending Cash, Add Pending Cash"),
		("Biaya langsung", "Expense/Other / Income/Other", "Centang Expense / Income"),
		("Tanpa bank", "Method WriteOff", "Mode of Payment Settlement"),
		("Approval PV", "Approve, Checked, Pay Out", "Validate"),
		("Jurnal", "Otomatis saat Save; Dr Hutang / Cr Bank, uang muka lewat akun Uang Muka lalu dialokasikan", "Saat Validate; sama, uang muka dialokasikan lewat Payment Reconciliation"),
		("Nomor", "Seri per PV / RV Type rekening", "RV/PV/kode bank/CMI/YYYY/bulan/####"),
	],
	[
		"Pembayaran valas: rekening valas harus dipilih sebelum mengisi apa pun, mata uang mengikuti rekening.",
		"Expense Note tidak muncul di References; tariknya lewat tombol Tarik Expense Note.",
		"Nama akun bank menentukan kode di nomor RV/PV.",
	])


# ---------------------------------------------------------------- Pending Cash

PC_ASCEND = (
	_flow(("SAVE", "Pending Cash V2", "Input kasbon", "Tanpa jurnal"),
	      ("CHK", "Check-1 / Check-2 / Approve", "Persetujuan berlapis", "Tanpa jurnal"),
	      ("PAID", "Paid", "Uang diserahkan", "Post to GL: Dr Kasbon / Cr Bank"),
	      ("PV", "Pertanggungjawaban", "Lewat Payment Voucher", "Cr akun kasbon"))
	+ _step(1, "Input", [
		"Type, Memo number, Date, Pay to (pemakai kasbon, punya limit dan akun), Post as, Total, PPN, PPh, bank.",
		"Bisa juga dari Packing List: Create Pending Cash V2.",
	])
	+ _step(2, "Persetujuan dan bayar", [
		"Save, Check-1, Check-2 (bila diwajibkan), Approve, lalu Paid (tanggal bayar).",
		"Refund (seri nomor sendiri), Split (membuat salinan -SPLIT), Void.",
	], "Saat Paid dan diposting: Dr akun pemakai / Receivable.PendingCash / Cr Bank.")
	+ _step(3, "Pertanggungjawaban", [
		"Payment Voucher tab Other/Pnd. Cash: kasbon dikredit, biaya didebit, selisihnya saja lewat bank.",
	])
)

PC_ERP = (
	_flow(("DRAFT", "Pending Cash", "Input kasbon", "Tanpa jurnal"),
	      ("VAL", "Validated", "Disetujui", "Tanpa jurnal"),
	      ("PAID", "Paid", "Uang diserahkan", "Dr Uang Muka / Cr Bank"),
	      ("PE/RF", "Payment Entry / Refund", "Dipakai atau dikembalikan", "Cr Uang Muka"))
	+ _step(1, "Input", [
		"Finance &gt; Pending Cash &gt; + Add: Type (menentukan akun uang muka), Pay To, Total, Bank Account, Cost Center.",
		"Section Connection: tautkan ke Shipping List / Packing List / SO / PO. Save.",
	])
	+ _step(2, "Validate lalu Pay", [
		"Validate: disetujui, isi terkunci (kecuali Bank Account).",
		"Pay: isi tanggal bayar, Journal Entry terbit. Unpaid membatalkannya selama belum dipakai.",
	], "Dr Uang Muka (akun Type) / Cr Bank. Nomor PC/TIPE/CMI/YY/####.")
	+ _step(3, "Pakai atau kembalikan", [
		"Pakai: Payment Entry Pay, Add Pending Cash.",
		"Sisa: Pending Cash Refund (tombol Refund, atau satu refund untuk beberapa kasbon), Validate.",
		"Void / Unvoid; semua aksi bisa massal dari list view.",
	])
)

PC_HTML = _compare(
	"cpc", "Compare Pending Cash",
	"Kasbon dari input sampai dipertanggungjawabkan. Alurnya sama; ERPNext memadatkan approval "
	"jadi satu Validate dan menjurnal langsung saat Pay.",
	PC_ASCEND, PC_ERP,
	[
		("Approval", "Check-1, Check-2, Approve", "Validate"),
		("Akun uang muka", "Akun pemakai kasbon / Receivable.PendingCash", "Advance Account di Pending Cash Type"),
		("Jurnal", "Saat Paid, lewat posting batch", "Saat Pay, langsung"),
		("Pertanggungjawaban", "Payment Voucher tab Other/Pnd. Cash", "Payment Entry Add Pending Cash"),
		("Refund", "Refund di dokumen kasbon", "Dokumen Pending Cash Refund (bisa banyak kasbon)"),
		("Tautan job", "Create dari Packing List", "Section Connection"),
		("Batalkan bayar", "Unposting / Void", "Unpaid (hapus jurnal) atau Void (jurnal dibalik)"),
	],
	[
		"Refund menerbitkan jurnal baru bertanggal refund; jurnal Paid tidak disentuh.",
		"Kasbon yang sudah ditarik Payment Entry tidak bisa di-Unpaid, lepas dulu barisnya.",
	])


# ---------------------------------------------------------------- AP / AR Note

NOTE_ASCEND = (
	_flow(("AR", "A/R Note", "Tagihan tambahan ke customer", "Dr Piutang / Cr akun baris"),
	      ("AP", "A/P Note", "Tagihan tambahan dari supplier", "Dr akun baris / Cr Hutang"),
	      ("DISC", "Discount Note", "Pengurang (AR / AP)", "Kebalikan tanda"))
	+ _step(1, "Header", [
		"Note number, Date, Customer / Supplier, Currency + kurs, Terms / due, Type (34 tipe AP Note), "
		"Tax Inv. No, PPN, PPh, Retention, Rounding, Reference.",
		"Bisa dibuat dari Packing List atau Service Invoice: Create AR Note / AR Discount Note.",
	])
	+ _step(2, "Baris", ["Description, Qty, Unit price, Amount, akun atau expense / revenue type, Cost Center."])
	+ _step(3, "Status", [
		"Save, Validate, Approve (Check-1 sampai 4 bila diaktifkan), lalu Post to GL. Void, Duplicate.",
		"Dilunasi lewat Receipt / Payment Voucher (Add Items).",
	], "AR: Dr Piutang / Cr akun baris + PPN Keluaran. AP: Dr akun baris + PPN Masukan / Cr Hutang.")
)

NOTE_ERP = (
	_flow(("AR", "AR Note", "Tagihan tambahan ke customer", "Dr Piutang / Cr akun baris"),
	      ("AP", "AP Note", "Tagihan tambahan dari supplier", "Dr akun baris / Cr Hutang"),
	      ("PE", "Payment Entry", "Pelunasan", "Add Items"))
	+ _step(1, "Header", [
		"Finance &gt; AP Note / AR Note: Type, Date, Supplier / Customer, Currency, Rate, Due Date, Cost Center, "
		"External Ref, Tax No.",
		"Opsi: Don't Post to GL, Confidential (hanya pembuat dan yang berhak), Skip Payable.",
	])
	+ _step(2, "Baris dan pajak", [
		"Items: deskripsi, akun, nominal. PPN dan PPh diisi di Summary (persen atau nominal).",
	])
	+ _step(3, "Status", [
		"Save lalu Validate: Journal Entry terbentuk. Void untuk membatalkan.",
		"Pelunasan: Payment Entry (AP Note: Pay, AR Note: Receive), Add Items.",
	], "AP: Dr biaya + PPN / Cr PPh + Hutang. AR: Dr Piutang + PPh 23 / Cr pendapatan + PPN.")
)

NOTE_HTML = _compare(
	"cno", "Compare AP Note dan AR Note",
	"Tagihan tambahan di luar invoice / expense note. Ascend punya empat varian (Note dan Discount Note "
	"untuk AR dan AP); ERPNext punya AP Note dan AR Note.",
	NOTE_ASCEND, NOTE_ERP,
	[
		("Dokumen", "A/R Note, A/R Discount Note, A/P Note, A/P Discount Note", "AR Note, AP Note"),
		("Pengurang tagihan", "Discount Note", "Credit Note (SI retur) / Debit Note (PI retur)"),
		("Approval", "Validate + Check-1 sampai 4", "Validate"),
		("Rahasia", "Tidak ada", "Confidential"),
		("Jurnal", "Post to GL batch", "Saat Validate"),
		("Pelunasan", "Receipt / Payment Voucher", "Payment Entry Add Items"),
	],
	[
		"Note yang dicentang Don't Post to GL atau Skip Payable tidak muncul di pilihan Payment Entry.",
		"No faktur pajak Note diisi lewat menu Tax &gt; Tax ARAP Note.",
	])


# ---------------------------------------------------------------- Tax

TAX_ASCEND = (
	_flow(("SI", "Sales / Service Invoice", "Edit Tax Invoice Number", "No faktur keluaran"),
	      ("EN", "Expense Note / IR AP", "Edit Tax Invoice Number", "No faktur masukan"),
	      ("SYNC", "Database pajak", "Disalin otomatis", "Untuk laporan pajak"))
	+ _step(1, "Faktur keluaran", [
		"Di Sales Invoice / Service Invoice: field Tax Invoice No, atau menu Edit Tax Invoice Number (Ctrl+F2): "
		"Type, No, Tanggal, Bukti Potong PPh.",
		"Auto Tax Invoice Number mengambil dari stok nomor, tetapi stok nomornya kosong di CIMI: diketik manual.",
	])
	+ _step(2, "Faktur masukan", [
		"Expense Note: Edit Tax Invoice Number (tipe, no, tanggal, no bupot) dan Edit Tax Report Date (masa lapor PPN).",
		"Invoice Receipt (AP) dan AR/AP Note juga punya Tax Invoice No / Date.",
	])
	+ _step(3, "Pelaporan", ["Data pajak disinkronkan ke database pajak terpisah."])
)

TAX_ERP = (
	_flow(("DOC", "Dokumen jadi", "SI / PI / EN / AP-AR Note divalidasi", "Baris Tax dibuat otomatis"),
	      ("TAX", "Menu Tax", "User isi No Tax", "Ditulis balik ke dokumen"),
	      ("CT", "Core Tax", "Laporan / ekspor", "Untuk Coretax"))
	+ _step(1, "Daftar per jenis", [
		"Tax &gt; Tax Invoice (Sales Invoice), Tax Expense (Expense Note), Tax ARAP Note, Tax Purchase (Purchase Invoice).",
		"Satu baris per dokumen yang sudah jadi, dibuat otomatis. Dokumen batal: baris dihapus, atau berstatus Batal bila No Tax sudah terisi.",
	])
	+ _step(2, "Isi nomor", [
		"Buka barisnya, isi No Tax, Save. Field lain terkunci. Nomor ikut tersimpan di dokumen sumbernya.",
	])
	+ _step(3, "Pelaporan dan setup", [
		"Report Core Tax. Setup: Tax Category, Tax Rule, Tax Withholding Category.",
	])
)

TAX_HTML = _compare(
	"ctx", "Compare Tax",
	"Pencatatan nomor faktur pajak. Ascend mengisinya per dokumen lewat menu Edit Tax Invoice Number; "
	"ERPNext mengumpulkan semua dokumen jadi di menu Tax supaya nomor diisi dari satu tempat.",
	TAX_ASCEND, TAX_ERP,
	[
		("Faktur keluaran", "Edit Tax Invoice Number di invoice", "Tax &gt; Tax Invoice"),
		("Faktur masukan", "Edit Tax Invoice Number di Expense Note / IR AP", "Tax &gt; Tax Expense / Tax Purchase"),
		("Note", "Tax Inv. No di AR/AP Note", "Tax &gt; Tax ARAP Note"),
		("Daftar yang belum bernomor", "Per dokumen", "Satu list per jenis, filter No Tax kosong"),
		("Pelaporan", "Sinkron ke database pajak", "Report Core Tax"),
	],
	[
		"Baris Tax baru muncul setelah dokumennya Validated; dokumen draft belum ada di daftar.",
		"No Tax diisi di menu Tax, bukan di form dokumennya.",
	])


# ---------------------------------------------------------------- Asset

ASSET_ASCEND = (
	_flow(("CAT", "Asset Category", "Akun + umur standar", "Master"),
	      ("FA", "Asset", "Register aset", "Dari PI / langsung"),
	      ("DEP", "Calculate Depreciation", "Jalankan per bulan", "Dr Bi. Penyusutan / Cr Akumulasi"),
	      ("SALE", "Asset Sales", "Jual aset", "Laba / rugi penjualan"))
	+ _step(1, "Asset Category dan Sub-Category", [
		"Akun AcquisitionCost, AccumDepreciation, DepreciationCost, CIP, Sales, Disposal; StdAgeMonths. Sub-category menimpa category.",
	])
	+ _step(2, "Daftarkan aset", [
		"Langsung di Asset editor (aset lama, isi Beg. depreciation), dari baris PO/PI Post to FA as Asset/CIP, "
		"PI Convert to Assets, atau dokumen Asset Purchase.",
		"Isi kode, kategori, lokasi, department, Acquisition date, Usage date, Acquisition cost, metode, Duration (bulan).",
	])
	+ _step(3, "Penyusutan", [
		"Calculate Fixed Asset Depreciation: pilih periode, wajib berurutan per bulan (nomor FA-DEP-periode).",
		"Bisa dibatalkan dengan Cancel Fixed Asset Depreciation Calculation, lalu diposting.",
	], "Dr DepreciationCost / Cr AccumDepreciation.")
	+ _step(4, "Jual", [
		"Asset Sales: Customer, Currency, Cash / Terms, baris aset + harga.",
		"Tidak ada dokumen penghapusan tersendiri.",
	], "Dr Kas / Piutang + Akumulasi / Cr Harga Perolehan + PPN, selisih ke AssetSales.ProfitLoss.")
)

ASSET_ERP = (
	_flow(("CAT", "Asset Category", "Akun + finance book", "Master"),
	      ("PI", "Purchase Invoice", "Beli item aset", "Asset Draft terbentuk"),
	      ("DEP", "Penyusutan otomatis", "Scheduler bulanan", "Dr Bi. Penyusutan / Cr Akumulasi"),
	      ("SELL", "Sell / Scrap Asset", "Lepas aset", "Sales Invoice / Journal Entry"))
	+ _step(1, "Asset Category dan Item aset", [
		"Asset Category: akun aktiva, akumulasi, beban penyusutan per company; Finance Books Straight Line, umur dalam bulan.",
		"Item: Is Fixed Asset, Asset Category, Auto Create Assets.",
	])
	+ _step(2, "Beli dan aktifkan", [
		"PO lalu Purchase Invoice, isi Asset Location. Record Asset Draft lahir otomatis.",
		"Buka Asset: nama nyata, Available for Use Date, Location, Cost Center, Submit.",
		"Aset lama: Asset Type = Existing Asset + Opening Accumulated Depreciation, tanpa jurnal.",
		"Barang stok jadi aset: Asset Capitalization.",
	])
	+ _step(3, "Penyusutan", [
		"Tidak perlu dijalankan: scheduler membuat Journal Entry tiap tanggal jadwal, prorata bulan pertama.",
	])
	+ _step(4, "Jual atau hapus", [
		"Actions &gt; Sell Asset: Sales Invoice draft, isi customer dan harga, Validate.",
		"Actions &gt; Scrap Asset: jurnal penghapusan dibuat sendiri. Restore Asset untuk membatalkan.",
	])
)

ASSET_HTML = _compare(
	"cas", "Compare Asset",
	"Aset tetap dari pembelian sampai pelepasan. Perbedaan terbesar: Ascend menyusutkan lewat proses "
	"bulanan yang dijalankan user, ERPNext menyusutkan sendiri sesuai jadwal.",
	ASSET_ASCEND, ASSET_ERP,
	[
		("Master", "Category + Sub-Category", "Asset Category + Item Is Fixed Asset"),
		("Dari pembelian", "Post to FA as / Convert to Assets / Asset Purchase", "PI item aset, Asset Draft otomatis"),
		("Aset lama", "Asset editor + Beg. depreciation", "Existing Asset + Opening Accumulated Depreciation"),
		("Penyusutan", "Calculate Depreciation per bulan, manual", "Scheduler otomatis"),
		("Jual", "Asset Sales", "Sell Asset, lewat Sales Invoice"),
		("Hapus buku", "Tidak ada dokumen khusus", "Scrap Asset (Journal Entry otomatis)"),
	],
	[
		"Available for Use Date menentukan mulai disusutkan, bukan tanggal beli.",
		"Batal jual dari Sales Invoice-nya (Invalidate / Void), bukan dari record aset.",
	])


# ---------------------------------------------------------------- Penjurnalan

GL_ASCEND = (
	_flow(("DOC", "Dokumen", "Save / Validate", "Belum menjurnal"),
	      ("POST", "Posting/Unposting", "Batch per jenis dokumen", "Jurnal terbentuk"),
	      ("JV", "GL Journal Voucher", "Jurnal manual", "Validate"))
	+ _step(1, "Jurnal otomatis lewat posting batch", [
		"GL &gt; Posting/Unposting Transactions: pilih jenis dokumen, rentang tanggal atau nomor, Post to GL / Post All to GL.",
		"Unposting boleh selama jurnalnya belum Protected. Pengecualian: Receipt / Payment Voucher terposting saat Save.",
	])
	+ _step(2, "GL Journal Voucher (manual)", [
		"Nomor otomatis, Voucher date, Reference, Remarks.",
		"Baris lewat dialog Journal Item: Account, Description, Department, Debit, Credit.",
		"Validate, Toggle Posted, Duplicate (Reverse) untuk jurnal balik.",
		"Massal: Post/Unpost Manual GL Journal Voucher, Delete GL Journal Voucher (per filter), Renumber.",
	], "Di CIMI sekitar 120 dari 7.900 jurnal diketik manual; sisanya lahir dari dokumen.")
)

GL_ERP = (
	_flow(("DOC", "Dokumen", "Validate / Submit", "Jurnal langsung terbentuk"),
	      ("JE", "Journal Entry", "Jurnal manual", "Submit"))
	+ _step(1, "Jurnal otomatis", [
		"Lahir saat dokumen di-Validate (SI, PI, EN, PE, Pending Cash Pay, Notes) atau di-Submit (DN, Stock Entry).",
		"Invalidate: jurnal dihapus, dokumen kembali draft. Void: jurnal dibalik dan disimpan sebagai jejak.",
		"Repost Accounting Ledger membangun ulang jurnal dokumen bila setting akunnya diubah.",
	])
	+ _step(2, "Journal Entry (manual)", [
		"Accounting &gt; Journal Entry: tanggal, baris akun, debit, kredit, cost center, party bila akun piutang / hutang. Submit.",
		"List Journal Entry hanya menampilkan jurnal ketikan user; jurnal otomatis ditandai system generated dan disaring.",
		"Jurnal balik: Create &gt; Reverse Journal Entry. Salah input: Cancel lalu Amend, nomor tidak bisa dihapus atau diurut ulang.",
	])
)

GL_HTML = _compare(
	"cgl", "Compare Penjurnalan",
	"Kapan dan bagaimana jurnal terbentuk. Ini perbedaan paling mendasar: Ascend mengumpulkan dokumen "
	"lalu mempostingnya ke GL, ERPNext menjurnal setiap dokumen saat divalidasi. Tutup periode dan "
	"laporan ada di Compare Accounting.",
	GL_ASCEND, GL_ERP,
	[
		("Jurnal otomatis", ASCEND_POSTING, ERP_POSTING),
		("Batal posting", "Unposting (jurnal belum Protected)", "Invalidate (hapus) atau Void (balik)"),
		("Jurnal manual", "GL Journal Voucher", "Journal Entry"),
		("Jurnal balik", "Duplicate (Reverse)", "Reverse Journal Entry, atau Void dokumen sumber"),
		("Hapus / nomor ulang", "Delete GL Journal Voucher, Renumber", "Tidak ada: Cancel lalu Amend"),
		("Cek jurnal dokumen", "Link GL Journal di editor", "General Ledger filter Voucher No"),
	],
	[
		"Tidak ada antrean dokumen belum terposting di ERPNext: laporan keuangan selalu berisi semua dokumen yang sudah Validated.",
		"Koreksi jurnal berarti koreksi dokumennya, bukan mengedit jurnal.",
		"Jurnal otomatis tidak tampil di list Journal Entry; cari lewat General Ledger.",
	])


# ---------------------------------------------------------------- Accounting

ACC_ASCEND = (
	_flow(("COA", "Chart of Accounts", "Akun + cost center", "Master"),
	      ("FX", "Kurs dan revaluasi", "AR/AP Exchange Rate G/L", "Jurnal selisih kurs"),
	      ("REC", "Bank Reconciliation", "Cocokkan mutasi bank", "Tanpa jurnal"),
	      ("CLOSE", "Close Period", "Kunci per bulan", "Tolak transaksi"),
	      ("RPT", "Laporan", "TB, Ledger, Neraca, Laba Rugi", "Baca GL"))
	+ _step(1, "Chart of Accounts dan Cost Center", [
		"GL &gt; Chart of Accounts: pohon akun, Type header neraca / header laba rugi / account, Category, "
		"Normal balance, Require cost center, Cash Flow Code. Sekitar 400 akun di CIMI.",
		"Manage Cost Centers (141 di CIMI), Cost Center Sets, CostCenter Status (aktif / nonaktif sejak tanggal).",
		"GL Account Security Codes dan Report Schema Security Codes membatasi akun dan laporan per user.",
		"Akun default jurnal otomatis: GL Interfaces (lihat Compare Basic).",
	])
	+ _step(2, "Kurs dan revaluasi valas", [
		"Currency (7 mata uang di CIMI). Tabel Manage Exchange Rates kosong: kurs diketik di tiap dokumen.",
		"Selisih kurs pelunasan otomatis ke interface ExchangeRateGainLoss.",
		"Revaluasi: Create Journal for AR/AP Exchange Rate G/L, isi tanggal, currency, kurs baru, AR / AP / keduanya.",
	], "Jurnal selisih kurs saldo piutang / hutang valas yang masih terbuka.")
	+ _step(3, "Rekonsiliasi bank", [
		"Bank Account Reconciliation per rekening + Reconciliation Types.",
		"Hanya 2 data di CIMI: praktis tidak dipakai.",
	])
	+ _step(4, "Tutup periode", [
		"Tools &gt; Close Period: per bulan, Reactivate, Mark read-only, Close, Accounting Check.",
		"Dua lapis: tutup operasional dan tutup accounting. 27 periode sudah ditutup di CIMI.",
	], "Transaksi bertanggal di periode tertutup ditolak (Please select an active date).")
	+ _step(5, "Budget dan rasio", [
		"Manage GL Account Budgets per akun / per cost center, Paste Annual Budget, Budget Analysis, Financial Ratio.",
		"Tabelnya kosong di CIMI: tidak dipakai.",
	])
	+ _step(6, "Laporan", [
		"Standard General Ledger Reports: Trial Balance dan Worksheet, Ledger, Subsidiary Ledger, "
		"Journal Report by Voucher, Balance Sheet, Income Statement.",
		"Financial Report dengan layout sendiri lewat Financial Report Schema (composer COGM / COGS / IS / CashFlow).",
	])
)

ACC_ERP = (
	_flow(("COA", "Chart of Accounts", "Akun + cost center", "Per company"),
	      ("FX", "Exchange Rate Revaluation", "Revaluasi akhir bulan", "Journal Entry otomatis"),
	      ("REC", "Bank Reconciliation Tool", "Cocokkan mutasi bank", "Tanpa jurnal"),
	      ("CLOSE", "Frozen Till / Period Closing", "Kunci dan tutup buku", "Tolak transaksi"),
	      ("RPT", "Laporan Keuangan", "Menu Accounting", "Baca GL"))
	+ _step(1, "Chart of Accounts dan Cost Center", [
		"Accounting &gt; Chart of Accounts, per company: Group (induk) atau ledger, Root Type, Account Type.",
		"Cost Center: pohon per company, centang Disabled untuk menonaktifkan. Segmen tambahan lewat Accounting Dimension.",
		"Pembatasan per user lewat User Permission, tidak ada security code per akun.",
		"Akun efektif per customer, supplier, item: Accounting &gt; Account Mapping (report, read-only).",
	])
	+ _step(2, "Kurs dan revaluasi valas", [
		"Currency Exchange: kurs per tanggal, jadi isian awal kurs di dokumen. Bisa ditarik otomatis lewat Currency Exchange Settings.",
		"Selisih kurs pelunasan otomatis ke Exchange Gain / Loss Account di Company.",
		"Revaluasi: Exchange Rate Revaluation (cari lewat kotak search), Posting Date, Get Entries, isi kurs baru, "
		"Submit lalu Create Journal Entry.",
	], "Jurnalnya bertipe Exchange Rate Revaluation, tidak tampil di list Journal Entry; lihat di General Ledger.")
	+ _step(3, "Rekonsiliasi bank", [
		"Bank Reconciliation Tool: pilih Bank Account, impor mutasi (Bank Statement Import jadi Bank Transaction), "
		"cocokkan dengan Payment Entry / Journal Entry.",
		"Butuh master Bank Account yang ditautkan ke akun bank di Chart of Accounts.",
	])
	+ _step(4, "Kunci dan tutup periode", [
		"Kunci bulanan: Company &gt; Accounts Frozen Till Date + Roles Allowed to Set and Edit Frozen Account Entries. "
		"Semua jurnal sampai tanggal itu ditolak kecuali role tersebut.",
		"Kunci per jenis dokumen: Accounting Period (rentang tanggal, Closed Documents, Exempted Role).",
		"Tutup buku: Accounting &gt; Closing Periode (Period Closing Voucher) memindahkan laba rugi ke laba ditahan.",
	])
	+ _step(5, "Budget", [
		"Budget per Cost Center / Project + akun, tahunan, sebaran bulanan lewat Monthly Distribution.",
		"Aksi bila terlampaui di PO / Material Request / jurnal: Stop, Warn, atau Ignore. Report Budget Variance.",
	])
	+ _step(6, "Laporan", [
		"Accounting &gt; Laporan Keuangan: Income Statement, Neraca, Cash Flow, Trial Balance, General Ledger, Payment Ledger.",
		"Layout laporan sendiri: Financial Report Template.",
	])
)

ACC_HTML = _compare(
	"cac", "Compare Accounting",
	"Setup akun, kurs, rekonsiliasi bank, tutup periode, budget, dan laporan. Cara jurnal terbentuk "
	"ada di Compare Penjurnalan.",
	ACC_ASCEND, ACC_ERP,
	[
		("Chart of Accounts", "Header neraca / laba rugi + account, Category, Normal balance", "Group / ledger, Root Type + Account Type, per company"),
		("Cost Center", "Kode segmen, CostCenter Status, Cost Center Sets", "Pohon per company, Disabled, Accounting Dimension"),
		("Akses akun per user", "GL Account Security Codes", "User Permission"),
		("Akun default", "GL Interfaces", "Company, Item Group, Invoice Type, setting; dicek di Account Mapping"),
		("Kurs harian", "Manage Exchange Rates (kosong di CIMI)", "Currency Exchange"),
		("Revaluasi valas", "Create Journal for AR/AP Exchange Rate G/L", "Exchange Rate Revaluation"),
		("Rekonsiliasi bank", "Bank Account Reconciliation (nyaris tak dipakai)", "Bank Reconciliation Tool + Bank Transaction"),
		("Kunci periode", "Close Period per bulan, operasional dan accounting", "Accounts Frozen Till Date / Accounting Period"),
		("Tutup buku", "Jurnal laba rugi otomatis ke interface ProfitLoss / RetainedEarning", "Period Closing Voucher"),
		("Budget", "Per akun / cost center (kosong di CIMI)", "Budget per cost center / project, Budget Variance"),
		("Layout laporan", "Financial Report Schema", "Financial Report Template"),
	],
	[
		"Close Period tidak punya padanan satu tombol: tiap tutup bulan majukan Accounts Frozen Till Date di Company. Sekarang masih kosong.",
		"Period Closing Voucher bukan kunci bulanan; ia menutup akun laba rugi ke laba ditahan, lazimnya akhir tahun.",
		"Revaluasi valas tidak berjalan sendiri: jalankan Exchange Rate Revaluation di akhir bulan bila ada saldo valas.",
	])


# ---------------------------------------------------------------- Jurnal
# Sisi Ascend = jurnal NYATA dari database AS_CAKRA (SQL Server lokal user): pola akun
# terbanyak 12 bulan terakhir per modul, satu voucher terbaru per pola. Sisi ERPNext =
# jurnal untuk transaksi yang sama menurut setting PT CMI di erp.localhost. Baris =
# (kode akun, nama akun, debit, kredit). Cek: test_compare_jurnal.py.

def _n(x):
	if not x:
		return ""
	s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	return s[:-3] if s.endswith(",00") else s


def _jt(lines):
	if not lines:
		return '<p class="lead">Tidak ada jurnal.</p>'
	r = 'style="text-align:right"'
	body = "".join(f"<tr><td>{c}</td><td>{nm}</td><td {r}>{_n(d)}</td><td {r}>{_n(k)}</td></tr>"
	               for c, nm, d, k in lines)
	total = (f'<tr><td></td><td><b>Total</b></td><td {r}><b>{_n(sum(l[2] for l in lines))}</b></td>'
	         f'<td {r}><b>{_n(sum(l[3] for l in lines))}</b></td></tr>')
	return (f'<table class="j"><tr><th>Account Code</th><th>Account Name</th><th {r}>Debit</th>'
	        f"<th {r}>Credit</th></tr>{body}{total}</table>")


def _jside(system, modul, blocks):
	"""Satu sisi kasus: {Sistem} / {Modul} / {Transaksi} - {Review} / {Tabel}."""
	inner = ""
	for trx, review, status, lines in blocks:
		pill = f' <b>[{status}]</b>' if status else ""
		inner += (f'<div class="ds" style="margin:8px 0 6px"><b>{trx}</b> - {review}{pill}</div>'
		          + _jt(lines))
	return (f'<div style="flex:1 1 360px;min-width:0"><div class="tag" style="display:inline-block;'
	        f'font-weight:700;margin-bottom:2px">{system}</div><div class="bt">{modul}</div>{inner}</div>')


# Status blok ERPNext dibanding Ascend.
SAMA, BEDA, SETTING = "Sama", "Beda", "Setting"

# (modul, [blok Ascend], [blok ERPNext]); blok = (transaksi, review, status, [(kode, nama, debit, kredit)]).
# Status: Sama = jurnal setara Ascend; Beda = akun/alur berbeda, perlu keputusan; Setting = sama
# asalkan setting master diisi.
JOURNAL_CASES = [
	("Expense Note",
	 [("EXP/EXP/27503/CMI/26 (TANK FEE, 28-09-2026)",
	   "Biaya diparkir di Suspend Biaya EMKL, baru dipindah ke akun biaya saat Service Invoice terbit.", "", [
		("2110.004", "Suspend Biaya EMKL", 22372500, 0),
		("2110.001", "Hutang Usaha", 0, 22372500)])],
	 [("Expense Note TANK FEE, saat Validate",
	   "Langsung ke akun biaya item, tanpa Suspend; tidak perlu reklas di invoice. Pola terbukti di "
	   "EN/EXP/CMI/2026/0001.", BEDA, [
		("5110.001", "Bi. Freight", 22372500, 0),
		("2110.001", "Hutang Usaha", 0, 22372500)])]),
	("Expense Note",
	 [("EXP/EXP/27412/CMI/26 (BIAYA TOL, 28-09-2026)",
	   "Vendor supir, hutang dicatat ke Hutang Supir.", "", [
		("2110.004", "Suspend Biaya EMKL", 225000, 0),
		("2170.003", "Hutang Supir", 0, 225000)])],
	 [("Expense Note BIAYA TOL, saat Validate",
	   "Hutang Supir hanya bila Supplier atau Supplier Group diisi akun 2170.003; kalau kosong jatuh ke "
	   "2110.001 Hutang Usaha.", SETTING, [
		("5110.052", "Bi. Parkir & Tol (Operasional)", 225000, 0),
		("2170.003", "Hutang Supir", 0, 225000)])]),
	("Expense Note",
	 [("EXP/EXP/27497/CMI/26 (Reimburse to Customer, 28-09-2026)",
	   "Biaya titipan customer ke akun Reimbursement.", "", [
		("1510.001", "Reimbursement", 641445, 0),
		("2110.001", "Hutang Usaha", 0, 641445)])],
	 [("Expense Note reimburse, saat Validate",
	   "Pola terbukti di EN/NJ/CMI/2026/0004.", SAMA, [
		("1510.001", "Reimbursement", 641445, 0),
		("2110.001", "Hutang Usaha", 0, 641445)])]),

	("Service Invoice",
	 [("C/E/09368/CMI/26 (28-09-2026)",
	   "Invoice sekaligus memindahkan biaya job dari Suspend ke akun biaya (Handling, Uang Jalan, Pelabuhan).",
	   "", [
		("1150.001", "Piutang Dagang IDR", 2680095, 0),
		("5110.006", "Bi. Handling Export", 25000, 0),
		("5110.009", "Bi. Uang Jalan Trucking", 590000, 0),
		("5110.075", "Bi. Pelabuhan", 658500, 0),
		("2110.004", "Suspend Biaya EMKL", 0, 1273500),
		("2120.006", "PPN Keluaran", 0, 265595),
		("4120.001", "Pendapatan Jasa Trucking", 0, 2414500)])],
	 [("Sales Invoice tipe Expedition, saat Validate",
	   "Hanya piutang, PPN, pendapatan: biaya sudah dibukukan di Expense Note. Pola terbukti di "
	   "C/E/0001/CMI/26. Service Invoice Agent sama polanya.", BEDA, [
		("1150.001", "Piutang Dagang IDR", 2680095, 0),
		("2120.006", "PPN Keluaran", 0, 265595),
		("4120.001", "Pendapatan Jasa Trucking", 0, 2414500)])]),

	("Sales Invoice",
	 [("SJ/1720/CMI/26 (Surat Jalan, 28-09-2026)",
	   "Barang keluar: nilai barang dipindah ke Persediaan In Transit.", "", [
		("1130.006", "Persediaan In Transit", 521273.17, 0),
		("1130.002", "Persediaan Oleo Chemicals", 0, 521273.17)]),
	  ("C/T/1617/CMI/26 (invoice, 28-09-2026)",
	   "HPP diakui saat invoice, mengosongkan Persediaan In Transit.", "", [
		("1150.001", "Piutang Dagang IDR", 943500, 0),
		("4140.002", "HPP Oleo Chemicals", 521273.17, 0),
		("1130.006", "Persediaan In Transit", 0, 521273.17),
		("2120.006", "PPN Keluaran", 0, 93500),
		("4110.001", "Penjualan Barang Dagang", 0, 850000)])],
	 [("Delivery Note, saat Submit",
	   "Mode In Transit (Company > Persediaan In Transit). Diuji test_in_transit.", SAMA, [
		("1130.006", "Persediaan In Transit", 521273.17, 0),
		("1130.002", "Persediaan Oleo Chemicals", 0, 521273.17)]),
	  ("Sales Invoice tipe Trading, saat Validate",
	   "HPP diakui saat invoice, proporsional qty yang ditagih. Syarat: Item Group punya Default COGS "
	   "Account. Invoice barang stok tanpa Delivery Note ditolak.", SAMA, [
		("1150.001", "Piutang Dagang IDR", 943500, 0),
		("4140.002", "HPP Oleo Chemicals", 521273.17, 0),
		("1130.006", "Persediaan In Transit", 0, 521273.17),
		("2120.006", "PPN Keluaran", 0, 93500),
		("4110.001", "Penjualan Barang Dagang", 0, 850000)])]),

	("Invoice Reimburse",
	 [("IR/4928/CMI/26 (Invoice Receipt AR, 28-09-2026)",
	   "Menagih biaya titipan, menutup akun Reimbursement.", "", [
		("1150.001", "Piutang Dagang IDR", 3415958, 0),
		("1510.001", "Reimbursement", 0, 3415958)])],
	 [("Sales Invoice behavior Reimburse, saat Validate",
	   "Pola terbukti di IR/0002/CMI/26. PPN vendor yang ikut ditagihkan Cr 1200.005, baris Markup Cr 4120.001.",
	   SAMA, [
		("1150.001", "Piutang Dagang IDR", 3415958, 0),
		("1510.001", "Reimbursement", 0, 3415958)])]),

	("Payment Voucher",
	 [("PV/CAB/1487/CMI/IX/26 (28-09-2026)",
	   "Satu jurnal: Dr Hutang per dokumen yang dilunasi (8 dokumen, dirangkum) / Cr Bank.", "", [
		("2110.001", "Hutang Usaha", 2640000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 2640000)])],
	 [("Payment Entry Pay, saat Validate",
	   "Pola terbukti di PE/MDR/CMI/2026/IX/0017. Potongan: PPN Dr 1200.005, Materai Dr 5110.069, Admin Dr "
	   "6210.001, PPh Cr 2120.002.", SAMA, [
		("2110.001", "Hutang Usaha", 2640000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 2640000)])]),

	("Payment Voucher",
	 [("PV/MDRA/0797/CMI/IX/26 (bayar Expense Note valas, 28-09-2026)",
	   "Transfer biasa (27.618 PV setahun). Contoh ini ada selisih kurs: rugi kurs ke Selisih Kurs.", "", [
		("2110.001", "Hutang Usaha", 52608000, 0),
		("6110.002", "Selisih Kurs", 1131000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 53739000)])],
	 [("Payment Entry Pay, Tarik Expense Note, bank valas",
	   "Selisih kurs masuk Exchange Gain/Loss Account Company, sekarang 6210.003 Bi. Rounded (tertukar dengan "
	   "akun pembulatan). Tukar di Company: Exchange Gain/Loss = 6110.002, Round Off = 6210.003.", SETTING, [
		("2110.001", "Hutang Usaha", 52608000, 0),
		("6110.002", "Selisih Kurs", 1131000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 53739000)])]),
	("Payment Voucher",
	 [("PV/MDRA/0791/CMI/IX/26 (bank charges / pembulatan, 28-09-2026)",
	   "Field Bank charges dipakai untuk pembulatan sen ke Bi. Rounded (4.437 PV setahun).", "", [
		("6210.003", "Bi. Rounded", 0.4, 0),
		("2110.001", "Hutang Usaha", 550000, 0),
		("2110.001", "Hutang Usaha", 550000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 1100000.4)])],
	 [("Payment Entry Pay, pembulatan otomatis",
	   "Selisih sen otomatis ke Round Off Account Company, sekarang 6110.002 Selisih Kurs (tertukar). Setelah "
	   "ditukar jadi 6210.003 seperti Ascend.", SETTING, [
		("6210.003", "Bi. Rounded", 0.4, 0),
		("2110.001", "Hutang Usaha", 550000, 0),
		("2110.001", "Hutang Usaha", 550000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 1100000.4)])]),
	("Payment Voucher",
	 [("PV/CAM/0272/CMI/IX/26 (dibayar dari kasbon, 28-09-2026)",
	   "Tagihan supir dibayar penuh dari kasbon: bank tidak keluar (2.979 PV setahun).", "", [
		("2170.003", "Hutang Supir", 196500, 0),
		("2170.003", "Hutang Supir", 1500000, 0),
		("2170.003", "Hutang Supir", 100000, 0),
		("1160.004", "Kas Bon Operasional", 0, 1796500)])],
	 [("Payment Entry Pay, Tarik Expense Note + Add Pending Cash",
	   "Sama, asalkan 2170.003 Hutang Supir ber-account type Payable (sekarang kosong) dan dipakai sebagai akun "
	   "hutang supplier supir.", SETTING, [
		("2170.003", "Hutang Supir", 196500, 0),
		("2170.003", "Hutang Supir", 1500000, 0),
		("2170.003", "Hutang Supir", 100000, 0),
		("1160.004", "Kas Bon Operasional", 0, 1796500)])]),
	("Payment Voucher",
	 [("PV/KK-JKT/0163/CMI/IX/26 (kas kecil + kasbon, 28-09-2026)",
	   "Kasbon lebih besar dari tagihan: sisanya kembali ke kas kecil (1.524 PV kas setahun).", "", [
		("1110.001", "Kas Kecil IDR Jakarta", 66000, 0),
		("2110.001", "Hutang Usaha", 234000, 0),
		("1160.004", "Kas Bon Operasional", 0, 300000)])],
	 [("Payment Entry Pay, Paid From kas kecil, Add Pending Cash",
	   "Kelebihan kasbon didebit ke akun Paid From (kas kecil).", SAMA, [
		("1110.001", "Kas Kecil IDR Jakarta", 66000, 0),
		("2110.001", "Hutang Usaha", 234000, 0),
		("1160.004", "Kas Bon Operasional", 0, 300000)])]),
	("Payment Voucher",
	 [("PV/CAB/1485/CMI/IX/26 (PPh dipotong, 28-09-2026)",
	   "PPh 23 dipotong saat bayar vendor (110 PV setahun).", "", [
		("2110.001", "Hutang Usaha", 133200, 0),
		("2120.002", "PPh Ps 23 yang dipotong", 0, 2400),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 130800)])],
	 [("Payment Entry Pay, field PPh", "Akun PPh dari ERPNext Custom Setting.", SAMA, [
		("2110.001", "Hutang Usaha", 133200, 0),
		("2120.002", "PPh Ps 23 yang Dipotong", 0, 2400),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 130800)])]),
	("Payment Voucher",
	 [("PV/CAB/1502/CMI/IX/26 (Debit Note per baris, 28-09-2026)",
	   "Potongan per dokumen (di sini PPh) lewat Debit Note baris (4.435 PV setahun).", "", [
		("2110.001", "Hutang Usaha", 18557815, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 18432255),
		("2120.002", "PPh Ps 23 yang dipotong", 0, 125560)])],
	 [("Payment Entry Pay, Debit Note per baris", "Debit Note baris dikredit ke akun yang dipilih di baris itu.",
	   SAMA, [
		("2110.001", "Hutang Usaha", 18557815, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 18432255),
		("2120.002", "PPh Ps 23 yang Dipotong", 0, 125560)])]),
	("Payment Voucher",
	 [("PV/CAB/1510/CMI/IX/26 (bayar Invoice Receipt AP, 28-09-2026)",
	   "Hutang karyawan dari IRP (1.593 PV setahun).", "", [
		("2170.004", "Hutang Karyawan", 175000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 175000)])],
	 [("Payment Entry Pay, tarik Purchase Invoice",
	   "Sama, asalkan 2170.004 Hutang Karyawan ber-account type Payable (sekarang kosong).", SETTING, [
		("2170.004", "Hutang Karyawan", 175000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 175000)])]),
	("Payment Voucher",
	 [("PV//0017/CMI/IX/26 (Settlement / WriteOff, 28-09-2026)",
	   "Tanpa bank: hutang dealer dipindah ke Hutang Leasing (326 PV setahun).", "", [
		("2110.001", "Hutang Usaha", 843536000, 0),
		("2130.002", "Hutang Leasing", 0, 843536000)])],
	 [("Payment Entry Pay, Mode of Payment Settlement",
	   "Settlement Account = 2130.002 menggantikan sisi bank.", SAMA, [
		("2110.001", "Hutang Usaha", 843536000, 0),
		("2130.002", "Hutang Leasing", 0, 843536000)])]),
	("Payment Voucher",
	 [("PV//0015/CMI/IX/26 (Settlement Expense Note Minus, 25-09-2026)",
	   "Expense Note (Minus) yang tidak jadi dikembalikan vendor ditutup balik ke biaya (118 PV setahun).", "", [
		("5110.003", "Bi. LOLO", 315315, 0),
		("1200.005", "PPN Masukan", 34685, 0),
		("2170.001", "Hutang Pengurus", 0, 350000)])],
	 [("Journal Entry, atau Void Expense Refund-nya",
	   "Belum ada padanan di Payment Entry: refund vendor (Expense Refund) yang batal cukup di-Void; kalau sudah "
	   "tervalidasi lama, balik dengan Journal Entry baris yang sama.", BEDA, [
		("5110.003", "Bi. LOLO", 315315, 0),
		("1200.005", "PPN Masukan", 34685, 0),
		("2170.001", "Hutang Pengurus", 0, 350000)])]),
	("Payment Voucher",
	 [("PV/CAB/1289/CMI/IX/26 (Expense, Transfer, 24-09-2026)",
	   "Is Expense: tanpa tagihan, baris akun langsung (419 PV setahun).", "", [
		("1110.008", "Cash Temporary", 120000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 120000)])],
	 [("Payment Entry Pay, centang Expense / Income", "Baris akun bebas, Pay To diisi.", SAMA, [
		("1110.008", "Cash Temporary", 120000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 120000)])]),
	("Payment Voucher",
	 [("PV/KK-JKT/0147/CMI/IX/26 (Expense, Cash, 24-09-2026)",
	   "Is Expense dari kas kecil; contoh ini memindah Lebih/Kurang Bayar ke kas (113 PV setahun).", "", [
		("1110.001", "Kas Kecil IDR Jakarta", 77700, 0),
		("1110.001", "Kas Kecil IDR Jakarta", 233100, 0),
		("1160.002", "Lebih/Kurang Bayar", 0, 77700),
		("1160.002", "Lebih/Kurang Bayar", 0, 233100)])],
	 [("Payment Entry, centang Expense / Income, akun kas kecil", "Jurnal sama.", SAMA, [
		("1110.001", "Kas Kecil IDR Jakarta", 77700, 0),
		("1110.001", "Kas Kecil IDR Jakarta", 233100, 0),
		("1160.002", "Lebih/Kurang Bayar", 0, 77700),
		("1160.002", "Lebih/Kurang Bayar", 0, 233100)])]),
	("Payment Voucher",
	 [("PV//0010/CMI/IX/26 (Expense, Settlement / WriteOff, 01-09-2026)",
	   "Is Expense tanpa bank = reklas antar akun biaya (58 PV setahun).", "", [
		("5210.050", "Bi. Gaji Mitra", 41715240, 0),
		("5110.045", "Bi. Operasional Supir Mitra", 104000000, 0),
		("5110.009", "Bi. Uang Jalan Trucking", 0, 145715240)])],
	 [("Journal Entry, atau Payment Entry Expense + Mode Settlement",
	   "Reklas biaya lazimnya Journal Entry; lewat Payment Entry: Settlement Account = akun yang dikredit.", SAMA, [
		("5210.050", "Bi. Gaji Mitra", 41715240, 0),
		("5110.045", "Bi. Operasional Supir Mitra", 104000000, 0),
		("5110.009", "Bi. Uang Jalan Trucking", 0, 145715240)])]),
	("APN",
	 [("APN/F.J/0750/CMI/26 (A/P Note, 28-09-2026)",
	   "Biaya operasional karyawan, hutang ke Hutang Karyawan.", "", [
		("5110.051", "Bi. BBM kendaraan", 300000, 0),
		("5110.052", "Bi. Parkir/Tol", 257000, 0),
		("2170.004", "Hutang Karyawan", 0, 557000)])],
	 [("AP Note, saat Validate (Journal Entry otomatis)",
	   "Akun kredit = hutang Supplier; 2170.004 hanya bila Supplier / Supplier Group diisi. Dari kode, belum "
	   "ada dokumen di DB.", SETTING, [
		("5110.051", "Bi. BBM Kendaraan (Operasional)", 300000, 0),
		("5110.052", "Bi. Parkir & Tol (Operasional)", 257000, 0),
		("2170.004", "Hutang Karyawan", 0, 557000)])]),

	("APN",
	 [("APN/OLEO.M/0607/CMI/26 (dengan PPN, 28-09-2026)",
	   "A/P Note biasa ber-PPN (860 note setahun).", "", [
		("4130.001", "Bi. Pembelian", 4190000, 0),
		("4130.001", "Bi. Pembelian", 3200000, 0),
		("4130.001", "Bi. Pembelian", 135135.12, 0),
		("1200.005", "PPN Masukan", 14864.86, 0),
		("2110.001", "Hutang Usaha", 0, 7539999.98)])],
	 [("AP Note, field PPN", "Jurnal sama. Akun 4130.001 di ERPNext ber-root Income, perlu dicek.", SAMA, [
		("4130.001", "Bi. Pembelian", 4190000, 0),
		("4130.001", "Bi. Pembelian", 3200000, 0),
		("4130.001", "Bi. Pembelian", 135135.12, 0),
		("1200.005", "PPN Masukan", 14864.86, 0),
		("2110.001", "Hutang Usaha", 0, 7539999.98)])]),
	("APN",
	 [("APN/EMKL.J/0240/CMI/26 (PPN tidak dapat dikreditkan, 28-09-2026)",
	   "Tax Not Credited: tidak ada baris PPN Masukan, PPN ikut jadi biaya (82 note setahun).", "", [
		("5110.051", "Bi. BBM kendaraan", 200000, 0),
		("5110.052", "Bi. Parkir/Tol", 45000, 0),
		("2170.001", "Hutang Pengurus", 0, 245000)])],
	 [("AP Note tanpa field PPN, nilai baris sudah termasuk PPN",
	   "AP Note tidak punya opsi PPN tidak dikreditkan: kosongkan PPN, masukkan PPN ke nilai baris. 2170.001 perlu "
	   "account type Payable.", SETTING, [
		("5110.051", "Bi. BBM Kendaraan (Operasional)", 200000, 0),
		("5110.052", "Bi. Parkir & Tol (Operasional)", 45000, 0),
		("2170.001", "Hutang Pengurus", 0, 245000)])]),
	("APN",
	 [("APN/GA.J/0749/CMI/26 (Prepaid, 18-08-2026)",
	   "Post As Prepaid: dicatat sebagai dibayar dimuka, lalu diamortisasi tiap bulan di jurnal FA-DEP (14 note "
	   "setahun).", "", [
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 38521800, 0),
		("2110.001", "Hutang Usaha", 0, 38521800)])],
	 [("AP Note dengan akun baris Dibayar Dimuka",
	   "Jurnal awal sama, tapi amortisasi bulanannya belum ada di ERPNext (di Ascend ikut FA-DEP otomatis). "
	   "Sementara: Journal Entry bulanan Dr biaya / Cr 1220.002.", BEDA, [
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 38521800, 0),
		("2110.001", "Hutang Usaha", 0, 38521800)])]),
	("APN",
	 [("APN/GA.M/0621/CMI/26 (akun sama di Debit dan Kredit, 28-09-2026)",
	   "Bayar PPN ke Kas Negara: baris dan hutangnya sama-sama 2120.010, jadi jurnal note-nya nol; gunanya "
	   "supaya bisa dibayar lewat PV (40 note setahun).", "", [
		("2120.010", "Hutang Pajak PPN", 1758349683, 0),
		("2120.010", "Hutang Pajak PPN", 0, 1758349683)])],
	 [("Payment Entry Pay, centang Expense / Income, tanpa AP Note",
	   "AP Note menolak akun Payable di baris, dan Payment Entry hanya melacak sisa hutang di akun Payable. Jadi "
	   "setoran PPN langsung lewat Payment Entry mode Expense ke 2120.010.", BEDA, [
		("2120.010", "Hutang Pajak PPN", 1758349683, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 1758349683)])]),
	("ARN",
	 [("ARN/0025/CMI/26 (A/R Note, 28-09-2026)",
	   "Biaya ditagihkan ke customer, mengurangi akun biaya.", "", [
		("1150.001", "Piutang Dagang IDR", 4308000, 0),
		("5110.020", "Bi. keperluan Isotank", 0, 4308000)])],
	 [("AR Note, saat Validate (Journal Entry otomatis)",
	   "Dari kode, belum ada dokumen di DB.", SAMA, [
		("1150.001", "Piutang Dagang IDR", 4308000, 0),
		("5110.020", "Bi. Keperluan Isotank", 0, 4308000)])]),
	("ARN",
	 [("ARD/0006/CMI/26 (A/R Discount Note, 06-02-2026)",
	   "Pengurang tagihan: membalik pendapatan dan PPN.", "", [
		("2120.006", "PPN Keluaran", 858000, 0),
		("4120.001", "Pendapatan Jasa Trucking", 7800000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 8658000)])],
	 [("Credit Note (Sales Invoice retur), saat Validate",
	   "Padanan A/R Discount Note. Dari kode.", SAMA, [
		("2120.006", "PPN Keluaran", 858000, 0),
		("4120.001", "Pendapatan Jasa Trucking", 7800000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 8658000)])]),

	("ARN",
	 [("ARD/0008/CMI/26 (A/R Discount Note ke akun beban, 25-02-2026)",
	   "Potongan tagihan dibebankan ke akun beban, bukan pendapatan.", "", [
		("5110.056", "Bi. Kerusakan Flexibag / Tank", 13078700, 0),
		("1150.001", "Piutang Dagang IDR", 0, 13078700)])],
	 [("Journal Entry ber-party customer, lalu Payment Reconciliation",
	   "Credit Note memakai akun pendapatan item; potongan ke akun beban pakai Journal Entry.", BEDA, [
		("5110.056", "Bi. Kerusakan Flexibag / Tank", 13078700, 0),
		("1150.001", "Piutang Dagang IDR", 0, 13078700)])]),
	("ARN",
	 [("ARN/0024/CMI/26 (Prepaid, cashback asuransi, 21-09-2026)",
	   "Cashback mengurangi asuransi dibayar dimuka.", "", [
		("1150.001", "Piutang Dagang IDR", 79200220, 0),
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 0, 49267488),
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 0, 29932732)])],
	 [("AR Note dengan akun baris Dibayar Dimuka", "Jurnal sama.", SAMA, [
		("1150.001", "Piutang Dagang IDR", 79200220, 0),
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 0, 49267488),
		("1220.002", "Asuransi Dibayar Dimuka - Kendaraan", 0, 29932732)])]),
	("Receipt Voucher",
	 [("RV/CAA/0317/CMI/IX/26 (24-09-2026)",
	   "PPh 23 yang dipotong customer ke 1200.003 (kredit pajak), admin bank ke biaya.", "", [
		("1120.016", "BCA - 806-0303810 (IDR)", 299748000, 0),
		("1200.003", "PPh Ps 23 (kredit pajak)", 5500000, 0),
		("6210.001", "Bi. Provisi dan Adm bank", 2000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 305250000)])],
	 [("Payment Entry Receive, saat Validate",
	   "PPh dipotong customer ke 1200.003 (pph23_account, sama dengan Sales Invoice); PPh di Pay tetap "
	   "2120.002. Diperbaiki 07-10-2026.", SAMA, [
		("1120.016", "BCA - 806-0303810 (IDR)", 299748000, 0),
		("1200.003", "PPh Ps 23 ( Kredit Pajak )", 5500000, 0),
		("6210.001", "Bi. Provisi dan Adm Bank", 2000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 305250000)])]),

	("Receipt Voucher",
	 [("RV/CAB/0029/CMI/IX/26 (terima Service Invoice, 25-09-2026)", "Transfer biasa.", "", [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 18525900, 0),
		("1150.001", "Piutang Dagang IDR", 0, 18525900)])],
	 [("Payment Entry Receive", "Jurnal sama.", SAMA, [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 18525900, 0),
		("1150.001", "Piutang Dagang IDR", 0, 18525900)])]),
	("Receipt Voucher",
	 [("RV/CAA/0341/CMI/IX/26 (pembulatan, 25-09-2026)",
	   "Selisih sen ke Bi. Rounded (243 RV setahun).", "", [
		("1120.016", "BCA - 806-0303810 (IDR)", 160552221, 0),
		("6210.003", "Bi. Rounded", 0, 0.6),
		("1150.001", "Piutang Dagang IDR", 0, 107034813.6),
		("1150.001", "Piutang Dagang IDR", 0, 53517406.8)])],
	 [("Payment Entry Receive, pembulatan otomatis",
	   "Ke Round Off Account Company, sekarang 6110.002 Selisih Kurs (tertukar). Setelah ditukar jadi 6210.003.",
	   SETTING, [
		("1120.016", "BCA - 806-0303810 (IDR)", 160552221, 0),
		("6210.003", "Bi. Rounded", 0, 0.6),
		("1150.001", "Piutang Dagang IDR", 0, 107034813.6),
		("1150.001", "Piutang Dagang IDR", 0, 53517406.8)])]),
	("Receipt Voucher",
	 [("RV/CAA/0359/CMI/IX/26 (terima Invoice Receipt AR, 15-09-2026)", "Dua invoice reimburse sekaligus.", "", [
		("1120.016", "BCA - 806-0303810 (IDR)", 10164915, 0),
		("1150.001", "Piutang Dagang IDR", 0, 4227885),
		("1150.001", "Piutang Dagang IDR", 0, 5937030)])],
	 [("Payment Entry Receive, dua Sales Invoice IR", "Jurnal sama.", SAMA, [
		("1120.016", "BCA - 806-0303810 (IDR)", 10164915, 0),
		("1150.001", "Piutang Dagang IDR", 0, 4227885),
		("1150.001", "Piutang Dagang IDR", 0, 5937030)])]),
	("Receipt Voucher",
	 [("RV//0001/CMI/IX/26 (Settlement / WriteOff, 07-09-2026)",
	   "Tanpa bank: piutang ditutup ke Pendapatan Komisi, beda kurs ke Selisih Kurs (25 RV setahun).", "", [
		("4120.013", "Pendapatan Komisi Lainnya", 77726000, 0),
		("6110.002", "Selisih Kurs", 1196800, 0),
		("1150.001", "Piutang Dagang IDR", 0, 78922800)])],
	 [("Payment Entry Receive, Mode of Payment Settlement",
	   "Settlement Account = 4120.013; selisih kurs ke Exchange Gain/Loss Company (perlu ditukar ke 6110.002).",
	   SETTING, [
		("4120.013", "Pendapatan Komisi Lainnya", 77726000, 0),
		("6110.002", "Selisih Kurs", 1196800, 0),
		("1150.001", "Piutang Dagang IDR", 0, 78922800)])]),
	("Receipt Voucher",
	 [("RV/CAA/0365/CMI/IX/26 (Revenue, Transfer, 28-09-2026)",
	   "Is Revenue: tanpa invoice, baris akun langsung (462 RV setahun).", "", [
		("1120.016", "BCA - 806-0303810 (IDR)", 1166666, 0),
		("1120.016", "BCA - 806-0303810 (IDR)", 1570269, 0),
		("1120.016", "BCA - 806-0303810 (IDR)", 920720, 0),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 1166666),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 1570269),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 920720)])],
	 [("Payment Entry Receive, centang Expense / Income", "Jurnal sama, satu baris bank per baris akun.", SAMA, [
		("1120.016", "BCA - 806-0303810 (IDR)", 3657655, 0),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 1166666),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 1570269),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 920720)])]),
	("Receipt Voucher",
	 [("RV/KK-SBY/0001/CMI/IX/26 (Revenue, Cash, 24-09-2026)",
	   "Is Revenue ke kas kecil, termasuk pembulatan (160 RV setahun).", "", [
		("1110.003", "Kas Kecil Surabaya", 4955, 0),
		("1110.003", "Kas Kecil Surabaya", 4955, 0),
		("1110.003", "Kas Kecil Surabaya", 4955, 0),
		("1110.003", "Kas Kecil Surabaya", 135, 0),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("6210.003", "Bi. Rounded", 0, 135)])],
	 [("Payment Entry Receive, Expense / Income, akun kas kecil", "Jurnal sama.", SAMA, [
		("1110.003", "Kas Kecil Surabaya", 15000, 0),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("1150.005", "Piutang Atas PPh 23 Supplier", 0, 4955),
		("6210.003", "Bi. Rounded", 0, 135)])]),
	("Receipt Voucher",
	 [("RV//0003/CMI/V/26 (Revenue, Settlement / WriteOff, 31-05-2026)",
	   "Is Revenue tanpa bank = revaluasi saldo bank USD ke Selisih Kurs (7 RV setahun).", "", [
		("1120.009", "BCA - 0222426888 (USD)", 59801613.45, 0),
		("6110.002", "Selisih Kurs", 0, 59801613.45)])],
	 [("Exchange Rate Revaluation (akhir bulan)",
	   "Dokumen khusus revaluasi; akunnya Exchange Gain/Loss Company (perlu ditukar ke 6110.002).", BEDA, [
		("1120.009", "BCA - 0222426888 (USD)", 59801613.45, 0),
		("6110.002", "Selisih Kurs", 0, 59801613.45)])]),
	("Purchase Invoice",
	 [("PI/2266/CMI/26 (28-09-2026)",
	   "Sparepart masuk stok + biaya langsung; kredit ke Hutang Usaha Sementara sampai Invoice Receipt AP.",
	   "", [
		("1140.006", "Persediaan Spareparts", 300000, 0),
		("5110.038", "Bi. Pemeliharaan Gandengan/Chasis", 75000, 0),
		("2110.002", "Hutang Usaha Sementara", 0, 375000)])],
	 [("Purchase Invoice, saat Validate",
	   "Langsung Hutang Usaha (akun Supplier), tanpa Invoice Receipt AP. Pola terbukti di PI/00001/CMI/26.",
	   BEDA, [
		("1140.006", "Persediaan Spareparts", 300000, 0),
		("5110.038", "Bi. Pemeliharaan Gandengan/Chasis", 75000, 0),
		("2110.001", "Hutang Usaha", 0, 375000)])]),
	("Purchase Invoice",
	 [("PI/2267/CMI/26 (28-09-2026)",
	   "Jasa dengan PPN Masukan diakui di PI.", "", [
		("1200.005", "PPN Masukan", 52800, 0),
		("5110.033", "Bi. Sewa/Aktivasi GPS Trado", 480000, 0),
		("2110.002", "Hutang Usaha Sementara", 0, 532800)])],
	 [("Purchase Invoice, saat Validate",
	   "Sama, kecuali akun hutang langsung Hutang Usaha.", BEDA, [
		("1200.005", "PPN Masukan", 52800, 0),
		("5110.033", "Bi. Sewa/Aktivasi GPS Trado", 480000, 0),
		("2110.001", "Hutang Usaha", 0, 532800)])]),

	("Invoice Receipt AP",
	 [("IRP/2205/CMI/26 (28-09-2026)",
	   "Faktur supplier diterima: Hutang Usaha Sementara dipindah ke Hutang Usaha.", "", [
		("2110.002", "Hutang Usaha Sementara", 4215000, 0),
		("2110.001", "Hutang Usaha", 0, 4215000)]),
	  ("IRP/2217/CMI/26 (28-09-2026)",
	   "Jenis hutang (di sini Hutang Supir) baru ditentukan di IRP.", "", [
		("2110.002", "Hutang Usaha Sementara", 100000, 0),
		("2170.003", "Hutang Supir", 0, 100000)])],
	 [("Tidak ada dokumennya",
	   "Purchase Invoice sudah langsung mengkredit hutang supplier (Usaha / Supir / Karyawan dari akun "
	   "Supplier).", BEDA, [])]),

	("Usage",
	 [("IU-F/0600/CMI/26 (15-09-2026)",
	   "Sparepart truk dipakai, beban ke Bi. Pemeliharaan Trado.", "", [
		("5110.042", "Bi. Pemeliharaan Trado", 613928.57, 0),
		("1140.006", "Persediaan Spareparts", 0, 613928.57)])],
	 [("Fleet Maintenance / Stock Entry Material Issue",
	   "Item Group Sparepart - Trado (dan item di dalamnya) = 5110.042, disamakan 07-10-2026. Dari kode.",
	   SAMA, [
		("5110.042", "Bi. Pemeliharaan Trado", 613928.57, 0),
		("1140.006", "Persediaan Spareparts", 0, 613928.57)])]),
	("Usage",
	 [("IU-SH/0129/CMI/26 (28-09-2026)",
	   "Flexibag dipakai, beban ke HPP Packaging.", "", [
		("4140.001", "HPP Packaging", 2142364.30, 0),
		("1130.001", "Persediaan Flexibag", 0, 2142364.30)])],
	 [("Stock Entry Material Issue",
	   "Item Group Flexibag belum punya akun pemakaian, jatuh ke 4130.001 Bi. Pembelian (root Income). Isi "
	   "Default Expense Account Item Group. Dari kode.", SETTING, [
		("4130.001", "Bi. Pembelian", 2142364.30, 0),
		("1130.001", "Persediaan Flexibag", 0, 2142364.30)])]),

	("Asset",
	 [("ASP/00001/CMI/VI/21 (Asset Purchase, 09-06-2021)",
	   "Pembelian aset langsung ke akun aktiva.", "", [
		("1410.004", "Peralatan Kantor", 40000000, 0),
		("2110.001", "Hutang Usaha", 0, 40000000)])],
	 [("Purchase Invoice item aset, saat Validate",
	   "Pola terbukti di PI/00006/CMI/26.", SAMA, [
		("1410.004", "Peralatan Kantor", 40000000, 0),
		("2110.001", "Hutang Usaha", 0, 40000000)])]),
	("Asset",
	 [("FA-DEP-JUL-2026 (penyusutan bulanan)",
	   "Hanya baris kendaraan; jurnal yang sama juga mengamortisasi biaya dibayar dimuka.", "", [
		("5210.011", "Bi. Penyusutan - Kendaraan", 2939069896.15, 0),
		("1420.002", "Ak Peny Kendaraan", 0, 2939069896.15)])],
	 [("Depreciation Entry otomatis (scheduler)",
	   "Asset Category kendaraan belum punya akun beban penyusutan, jatuh ke 5210.010. Isi 5210.011. Pola "
	   "terbukti di ACC-JV-2026-00173.", SETTING, [
		("5210.010", "Bi. Penyusutan - Gedung/Bangunan", 2939069896.15, 0),
		("1420.002", "Ak Peny Kendaraan", 0, 2939069896.15)])]),
	("Asset",
	 [("FA-SALES/0007/CMI/26 (Asset Sales, 03-06-2026)",
	   "Laba penjualan aset ke Pendapatan Lain-Lain.", "", [
		("1150.001", "Piutang Dagang IDR", 120000000, 0),
		("1420.002", "Ak Peny Kendaraan", 262536364, 0),
		("1410.003", "Kendaraan", 0, 262536364),
		("6110.003", "Pendapatan Lain-Lain", 0, 120000000)])],
	 [("Sell Asset (Sales Invoice), saat Validate",
	   "Laba ke 6110.008 Laba/Rugi Penjualan Asset, bukan Pendapatan Lain-Lain. Dari kode.", BEDA, [
		("1150.001", "Piutang Dagang IDR", 120000000, 0),
		("1420.002", "Ak Peny Kendaraan", 262536364, 0),
		("1410.003", "Kendaraan", 0, 262536364),
		("6110.008", "Laba/Rugi Penjualan Asset", 0, 120000000)])]),
	("Asset",
	 [("FA-SALES/0006/CMI/25 (Asset Sales tanpa harga, 31-07-2025)",
	   "Penghapusan aset; sisa nilai buku ke Bi. Kerugian Penghapusan Asset.", "", [
		("1420.002", "Ak Peny Kendaraan", 575520833.32, 0),
		("6210.008", "Bi. Kerugian Penghapusan Asset", 74479166.68, 0),
		("1410.003", "Kendaraan", 0, 650000000)])],
	 [("Scrap Asset (Journal Entry otomatis)",
	   "Rugi ke 6110.008, satu akun untuk laba maupun rugi pelepasan. Dari kode.", BEDA, [
		("1420.002", "Ak Peny Kendaraan", 575520833.32, 0),
		("6110.008", "Laba/Rugi Penjualan Asset", 74479166.68, 0),
		("1410.003", "Kendaraan", 0, 650000000)])]),

	("Adjustment",
	 [("IA/0199/CMI/26 (22-09-2026)",
	   "Stok naik; lawan akun ikut tipe adjustment (di sini HPP Packaging).", "", [
		("1130.001", "Persediaan Flexibag", 20693062.90, 0),
		("4140.001", "HPP Packaging", 0, 20693062.90)])],
	 [("Stock Reconciliation, saat Submit",
	   "Lawan akun default 1130.007 Penyesuaian Persediaan; bisa diganti per dokumen di Difference Account. "
	   "Dari kode.", BEDA, [
		("1130.001", "Persediaan Flexibag", 20693062.90, 0),
		("1130.007", "Penyesuaian Persediaan", 0, 20693062.90)])]),

	("Goods Transfer",
	 [("IC_Mutations", "1.450 dokumen di AS_CAKRA, tidak satu pun berjurnal.", "", [])],
	 [("Stock Entry Material Transfer",
	   "Akun persediaan item sama di kedua gudang, jadi tanpa efek GL.", SAMA, [])]),

	("Sales Return",
	 [("SN/0003/CMI/25 (21-11-2025)",
	   "Pengurang penjualan ke akun Retur Penjualan.", "", [
		("2120.006", "PPN Keluaran", 588516.5, 0),
		("4110.002", "Retur Penjualan", 5350150, 0),
		("1150.001", "Piutang Dagang IDR", 0, 5938666.5)])],
	 [("Credit Note (Sales Invoice retur), saat Validate",
	   "Membalik akun Penjualan 4110.001; 4110.002 Retur Penjualan tidak dipakai kecuali di-set di Item. "
	   "Barang kembali: DN retur Dr Persediaan / Cr In Transit, Credit Note Dr In Transit / Cr HPP.", BEDA, [
		("4110.001", "Penjualan Barang Dagang", 5350150, 0),
		("2120.006", "PPN Keluaran", 588516.5, 0),
		("1150.001", "Piutang Dagang IDR", 0, 5938666.5)])]),

	("Pending Cash",
	 [("PC/04399/CMI/26 (Pending Cash V2, 28-09-2026)",
	   "Kasbon diserahkan: Kas Bon Operasional didebit, bank keluar.", "", [
		("1160.004", "Kas Bon Operasional", 5400000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 5400000)])],
	 [("Pending Cash tipe KBO, saat Pay (Journal Entry otomatis)",
	   "Akun dari Pending Cash Type KBO = 1160.004 Kas Bon Operasional (diganti 06-10-2026, diuji), terurai "
	   "per penerima. Kasbon lama yang sudah Paid tetap di 1230.001.", SAMA, [
		("1160.004", "Kas Bon Operasional", 5400000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 5400000)])]),
	("Pending Cash Refund",
	 [("PC/04249/CMI/26-REFUND (Pending Cash Refund, 11-09-2026)",
	   "Sisa kasbon dikembalikan ke bank.", "", [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 250000, 0),
		("1160.004", "Kas Bon Operasional", 0, 250000)])],
	 [("Pending Cash Refund, saat Validate (Journal Entry otomatis)",
	   "Kredit ke akun uang muka dari jurnal kasbonnya sendiri, jadi kasbon KBO baru kembali ke 1160.004. "
	   "Pola terbukti di ACC-JV-2026-00159.", SAMA, [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 250000, 0),
		("1160.004", "Kas Bon Operasional", 0, 250000)])]),

	("Jaminan",
	 [("JAMN/0212/CMI/26 (Nota Jaminan, 25-09-2026)",
	   "Jaminan container ke pelayaran untuk job SO/OLEO.S/0014; dokumen ini sendiri tidak berjurnal.", "", []),
	  ("PV/MDRA/0764/CMI/IX/26 (bayar jaminan, 25-09-2026)",
	   "PV menarik JAMN/0212 sebagai baris tipe EJ; jaminan jadi piutang ke pelayaran. Semua 317 Nota Jaminan setahun dibayar lewat PV.", "", [
		("1150.003", "Piutang atas Jaminan", 500000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 500000)])],
	 [("Pending Cash tipe JMK (Jaminan Keluar), saat Pay",
	   "Pay To = pelayaran, job ditautkan lewat section Connection. Tipe JMK belum ada: buat dulu (langkah "
	   "di bawah).", SETTING, [
		("1150.003", "Piutang atas Jaminan", 500000, 0),
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 0, 500000)])]),
	("Jaminan",
	 [("RV/CAB/0026/CMI/IX/26 (jaminan kembali, 24-09-2026)",
	   "RV menarik JAMN/0172 dan JAMN/0173 sebagai baris tipe EJC: jaminan selesai = uang kembali lewat RV (271 dari 317 setahun).", "", [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 45000000, 0),
		("1150.003", "Piutang atas Jaminan", 0, 24000000),
		("1150.003", "Piutang atas Jaminan", 0, 21000000)])],
	 [("Pending Cash Refund untuk dua kasbon JMK, saat Validate",
	   "Satu refund boleh menutup beberapa jaminan: sebaris per jaminan + satu baris bank. Sisa jaminan yang "
	   "belum kembali terlihat per dokumen.", SETTING, [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 45000000, 0),
		("1150.003", "Piutang atas Jaminan", 0, 24000000),
		("1150.003", "Piutang atas Jaminan", 0, 21000000)])]),
	("Jaminan",
	 [("APN/OLEO.J/0579/CMI/26 (jaminan dipotong pelayaran)",
	   "Sebagian jaminan dipakai menutup tagihan pelayaran (mis. demurrage); sisanya kembali lewat RV. "
	   "Terjadi pada 10 jaminan setahun.", "", [
		("2110.002", "Hutang Usaha Sementara", 800000, 0),
		("1150.003", "Piutang atas Jaminan", 0, 800000)])],
	 [("Payment Entry Pay ke pelayaran + Add Pending Cash JMK",
	   "Tarik Expense Note tagihan pelayaran, lalu Add Pending Cash kasbon JMK-nya: jaminan dipakai membayar, "
	   "bank tidak keluar. Sisa jaminan tetap bisa di-Refund.", SETTING, [
		("2110.001", "Hutang Usaha", 800000, 0),
		("1150.003", "Piutang atas Jaminan", 0, 800000)])]),
	("Jaminan",
	 [("RV/CAB/0012/CMI/IV/26 (terima jaminan customer, 21-04-2026)",
	   "Jaminan dari customer dicatat sebagai kewajiban Jaminan.", "", [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 2000000, 0),
		("2150.001", "Jaminan", 0, 2000000)])],
	 [("Pending Cash tipe JMN (Cash Inflow), saat Pay",
	   "Tipe JMN sekarang memakai 2150.003 Nota Jaminan; ganti ke 2150.001 Jaminan agar sama. Pola terbukti di "
	   "ACC-JV-2026-00158.", SETTING, [
		("1120.029", "BCA - 806-0303801 PT (IDR)", 2000000, 0),
		("2150.001", "Jaminan", 0, 2000000)])]),
	("Jaminan",
	 [("PV/CAB/0496/CMI/IX/26 (kembalikan jaminan customer, 09-09-2026)",
	   "Jaminan customer dikembalikan.", "", [
		("2150.001", "Jaminan", 2000000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 2000000)])],
	 [("Pending Cash Refund untuk kasbon JMN, saat Validate",
	   "Kasbon Cash Inflow dibalik: Dr akun jaminan / Cr Bank. Ikut setting JMN di atas.", SETTING, [
		("2150.001", "Jaminan", 2000000, 0),
		("1120.029", "BCA - 806-0303801 PT (IDR)", 0, 2000000)])]),

	("Bank Deposit",
	 [("BD/1014/CMI/26 (28-09-2026)",
	   "Pindah dana antar rekening, biaya transfer ke biaya bank.", "", [
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 500000000, 0),
		("6210.001", "Bi. Provisi dan Adm bank", 2900, 0),
		("1120.016", "BCA - 806-0303810 (IDR)", 0, 500002900)])],
	 [("Journal Entry (Bank Entry) atau Payment Entry Internal Transfer",
	   "Jurnal sama; ERPNext tidak punya dokumen khusus bernomor BD/. Native.", SAMA, [
		("1120.020", "MDR - 1680001650850 (IDR) (Master)", 500000000, 0),
		("6210.001", "Bi. Provisi dan Adm Bank", 2900, 0),
		("1120.016", "BCA - 806-0303810 (IDR)", 0, 500002900)])]),

	("Uang Muka",
	 [("PV/MDRA/0533/CMI/IX/26/001 (alokasi PV, 28-09-2026)",
	   "PV uang muka dialokasikan ke tagihan: Uang Muka Pembelian ditutup ke Hutang.", "", [
		("2110.001", "Hutang Usaha", 9100000, 0),
		("1230.001", "Uang Muka Pembelian", 0, 9100000)])],
	 [("Alokasi uang muka (Payment Reconciliation / Get Advances di Purchase Invoice)",
	   "Company memakai akun uang muka terpisah, jadi saat dialokasikan ERPNext menulis Dr Hutang / Cr Uang "
	   "Muka. Native, belum ada contoh di DB.", SAMA, [
		("2110.001", "Hutang Usaha", 9100000, 0),
		("1230.001", "Uang Muka Pembelian", 0, 9100000)])]),
	("Uang Muka",
	 [("RV/CAA/0280/CMI/IX/26/001 (alokasi RV, 25-09-2026)",
	   "DP customer dialokasikan ke invoice: Uang Muka Penjualan ditutup ke Piutang.", "", [
		("2140.001", "Uang Muka /DP Penjualan", 184260000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 184260000)])],
	 [("Alokasi DP customer (Payment Reconciliation / Get Advances di Sales Invoice)",
	   "Sama polanya dengan sisi pembelian. Native, belum ada contoh di DB.", SAMA, [
		("2140.001", "Uang Muka /DP Penjualan", 184260000, 0),
		("1150.001", "Piutang Dagang IDR", 0, 184260000)])]),

	("AP Note HPP",
	 [("APN/PKG.J/0486/CMI/26 (A/P Note trading, 22-09-2026)",
	   "Biaya kirim container ekspor (freight, stuffing, pelabuhan) ditampung di Hutang Usaha Sementara.", "", [
		("2110.002", "Hutang Usaha Sementara", 25734639.38, 0),
		("1200.005", "PPN Masukan", 334360.34, 0),
		("5210.019", "Bi. Benda Benda Pos & Materai", 20000, 0),
		("2110.001", "Hutang Usaha", 0, 26088999.72)]),
	  ("APN/PKG.J/0486/CMI/26-HPP (jurnal HPP-nya)",
	   "Biaya dipindah ke Persediaan In Transit, bertanggal Purchase yang ditautkan.", "", [
		("1130.006", "Persediaan In Transit", 25734639.38, 0),
		("2110.002", "Hutang Usaha Sementara", 0, 25734639.38)]),
	  ("PI/2198/CMI/26 (Purchase yang ditautkan, 22-09-2026)",
	   "AP Note itu menunjuk PI ini (ExSource AP_Purchases). Jurnal PI mengosongkan In Transit ke persediaan "
	   "barangnya (landed cost); bagian AP Note ini saja, total In Transit di PI 29.395.409,38.", "", [
		("1130.001", "Persediaan Flexibag", 25734639.38, 0),
		("1130.006", "Persediaan In Transit", 0, 25734639.38)])],
	 [("AP Note isi Purchase Invoice (HPP), saat Validate",
	   "Baris otomatis ke Persediaan In Transit (akun di Company); langkah Hutang Usaha Sementara tidak "
	   "perlu. Materai yang bukan HPP dibuat AP Note terpisah. Diuji test_notes._check_landed_cost.", SAMA, [
		("1130.006", "Persediaan In Transit", 25734639.38, 0),
		("1200.005", "PPN Masukan", 334360.34, 0),
		("2110.001", "Hutang Usaha", 0, 26068999.72)]),
	  ("Landed Cost Voucher otomatis ke Purchase Invoice yang ditautkan",
	   "GL Purchase Invoice ditulis ulang bertanggal PI (seperti Ascend): nilai barang naik, In Transit "
	   "kosong lagi, biaya ikut jadi HPP saat barangnya dijual. Batal validasi = LCV dibatalkan.", SAMA, [
		("1130.001", "Persediaan Flexibag", 25734639.38, 0),
		("1130.006", "Persediaan In Transit", 0, 25734639.38)])]),

	("Assembly",
	 [("ASM/0086/CMI/26 (22-09-2026)",
	   "Barang dirakit / diganti jenis: persediaan pindah antar akun item.", "", [
		("1130.002", "Persediaan Oleo Chemicals", 9038642.44, 0),
		("1130.001", "Persediaan Flexibag", 0, 9038642.44)])],
	 [("Stock Entry Repack (menu Change Items), saat Submit",
	   "Akun persediaan ikut Item Group masing-masing item, jadi jurnalnya sama. Native.", SAMA, [
		("1130.002", "Persediaan Oleo Chemicals", 9038642.44, 0),
		("1130.001", "Persediaan Flexibag", 0, 9038642.44)])]),

	("Jurnal Manual",
	 [("ADJ/0013/CMI/26 (GL Journal Voucher, 31-07-2026)",
	   "Kompensasi PPN bulanan: PPN Keluaran dikurangi PPN Masukan, sisanya Hutang Pajak PPN.", "", [
		("2120.006", "PPN Keluaran", 3735707483.37, 0),
		("1200.005", "PPN Masukan", 0, 1814064583.0),
		("1200.006", "PPN Masukan Import", 0, 674379176.0),
		("2120.010", "Hutang Pajak PPN", 0, 1247263724.37)])],
	 [("Journal Entry manual, saat Submit",
	   "Jurnal sama, diketik di Accounting > Journal Entry. Native.", SAMA, [
		("2120.006", "PPN Keluaran", 3735707483.37, 0),
		("1200.005", "PPN Masukan", 0, 1814064583.0),
		("1200.006", "PPN Masukan Import", 0, 674379176.0),
		("2120.010", "Hutang Pajak PPN", 0, 1247263724.37)])]),

	("Tutup Laba Rugi",
	 [("PL/2026.07.31 (tutup bulan)",
	   "Laba bulan berjalan dipindah dari Ikhtisar L/R.", "", [
		("9", "IKTHISAR L/R", 3630236591.9, 0),
		("3210.002", "Laba Rugi Bulan Berjalan", 0, 3630236591.9)]),
	  ("PL-ANNUAL/2026.08.01 (awal bulan berikutnya)",
	   "Laba bulan berjalan digulung ke Laba Rugi Tahun Berjalan.", "", [
		("3210.002", "Laba Rugi Bulan Berjalan", 3630236591.9, 0),
		("3210.001", "Laba Rugi Tahun Berjalan", 0, 3630236591.9)])],
	 [("Period Closing Voucher Juli 2026, Closing Account 3210.002",
	   "Menolkan semua akun laba rugi periode itu ke Laba Rugi Bulan Berjalan; laporan Laba Rugi tetap utuh. "
	   "Akun Ikhtisar L/R tidak diperlukan. PCV juga mengunci bulan itu.", SAMA, [
		("", "Akun-akun laba rugi Juli (dinolkan, dibalik dari saldonya)", 3630236591.9, 0),
		("3210.002", "Laba Rugi Bulan Berjalan", 0, 3630236591.9)]),
	  ("Journal Entry otomatis 01-08-2026",
	   "Dibuat sendiri saat PCV di-submit, ikut batal kalau PCV dibatalkan. Diuji test_period_close.", SAMA, [
		("3210.002", "Laba Rugi Bulan Berjalan", 3630236591.9, 0),
		("3210.001", "Laba Rugi Tahun Berjalan", 0, 3630236591.9)])]),
	("Tutup Laba Rugi",
	 [("ADJ/0128/CMI/22 (GL Journal Voucher manual, 31-12-2022)",
	   "Ganti tahun: laba setahun dipindah manual oleh accounting, \"LABA RUGI TAHUN 2022\". Tidak konsisten: "
	   "2024-2025 hanya bagian Desember (ADJ/0001/CMI/26), laba Jan-Nov 2025 tertinggal di 3210.001.", "", [
		("3210.001", "Laba Rugi Tahun Berjalan", 41687810842.58, 0),
		("3210.003", "Laba Rugi Tahun Lalu", 0, 41687810842.58)])],
	 [("Journal Entry otomatis 01-01 saat PCV Desember di-submit",
	   "Seluruh saldo Tahun Berjalan (sudah termasuk gulungan Desember) pindah ke Tahun Lalu, jadi Tahun "
	   "Berjalan selalu mulai nol. Tanggal 1 Januari, bukan 31 Desember, karena 31 Desember dikunci PCV. "
	   "Diuji test_period_close.", SAMA, [
		("3210.001", "Laba Rugi Tahun Berjalan", 41687810842.58, 0),
		("3210.003", "Laba Rugi Tahun Lalu", 0, 41687810842.58)])]),
]


# Alur jurnal: lane dari artifact "Peta Alur ERP CMI" (58Y8byQHoCN2o3zwwGVs7J) diubah jadi diagram
# dokumen ke dokumen, tiap kotak berisi akun Debit / Kredit. Akun diambil dari JOURNAL_CASES (tidak ditulis
# ulang). Node = (dokumen, keterangan, baris); baris None = dokumen tanpa jurnal.

def _jl(modul, case=0, side="A", blk=0):
	"""Baris jurnal kasus ke-`case` modul itu; side A = Ascend, E = ERPNext."""
	m = [c for c in JOURNAL_CASES if c[0] == modul][case]
	return (m[1] if side == "A" else m[2])[blk][3]


_PV_A = ("Payment Voucher", "bayar vendor", _jl("Payment Voucher"))
_PV_E = ("Payment Entry Pay", "bayar vendor", _jl("Payment Voucher", side="E"))
_RV_A = ("Receipt Voucher", "terima customer", _jl("Receipt Voucher"))
_RV_E = ("Payment Entry Receive", "terima customer", _jl("Receipt Voucher", side="E"))

# (area, lane, status ERPNext vs Ascend, catatan, [node Ascend], [node ERPNext])
JOURNAL_FLOWS = [
	("Ekspedisi", "Biaya vendor", BEDA,
	 "Ascend memarkir biaya di Suspend Biaya EMKL sampai Service Invoice; ERPNext langsung ke akun biaya.",
	 [("Packing List", "job", None), ("Expense Note", "TANK FEE", _jl("Expense Note")), _PV_A],
	 [("Packing List", "job", None), ("Expense Note", "TANK FEE", _jl("Expense Note", side="E")), _PV_E]),
	("Ekspedisi", "Tagihan jasa", BEDA,
	 "Service Invoice Ascend sekalian memindahkan biaya dari Suspend; di ERPNext biaya sudah dibukukan di "
	 "Expense Note.",
	 [("Packing List", "container", None), ("Service Invoice", "C/E", _jl("Service Invoice")), _RV_A],
	 [("Packing List / Proforma", "", None),
	  ("Sales Invoice C/E", "Expedition", _jl("Service Invoice", side="E")), _RV_E]),
	("Ekspedisi", "Tagihan reimburse", SAMA, "",
	 [("Expense Note reimburse", "", _jl("Expense Note", 2)),
	  ("Invoice Receipt AR", "IR", _jl("Invoice Reimburse")), _RV_A],
	 [("Expense Note reimburse", "", _jl("Expense Note", 2, "E")),
	  ("Sales Invoice IR", "Reimburse", _jl("Invoice Reimburse", side="E")), _RV_E]),
	("Ekspedisi", "Jaminan container", SETTING, "Butuh Pending Cash Type JMK (lihat panduan Jaminan).",
	 [("Nota Jaminan", "JAMN", None), ("Payment Voucher", "bayar jaminan", _jl("Jaminan", 0, "A", 1)),
	  ("Receipt Voucher", "jaminan kembali", _jl("Jaminan", 1))],
	 [("Pending Cash JMK", "Pay", _jl("Jaminan", 0, "E")),
	  ("Pending Cash Refund", "jaminan kembali", _jl("Jaminan", 1, "E"))]),
	("Trading", "Jual barang", SAMA, "HPP diakui saat invoice di kedua sistem (mode In Transit).",
	 [("Sales Order", "", None), ("Surat Jalan", "SPB", _jl("Sales Invoice")),
	  ("Sales Invoice", "C/T", _jl("Sales Invoice", 0, "A", 1)), _RV_A],
	 [("Sales Order", "", None), ("Delivery Note", "", _jl("Sales Invoice", side="E")),
	  ("Sales Invoice C/T", "", _jl("Sales Invoice", 0, "E", 1)), _RV_E]),
	("Trading", "Retur penjualan", BEDA, "ERPNext membalik akun Penjualan, bukan Retur Penjualan.",
	 [("Sales Return", "", _jl("Sales Return"))],
	 [("Credit Note", "Sales Invoice retur", _jl("Sales Return", side="E"))]),
	("Pembelian", "Purchase Invoice", BEDA,
	 "Ascend lewat Hutang Usaha Sementara lalu Invoice Receipt AP; ERPNext langsung Hutang Usaha.",
	 [("Purchase Order", "", None), ("Purchase Invoice", "", _jl("Purchase Invoice")),
	  ("Invoice Receipt AP", "IRP", _jl("Invoice Receipt AP")), _PV_A],
	 [("Purchase Order", "", None), ("Purchase Invoice", "", _jl("Purchase Invoice", side="E")), _PV_E]),
	("Pembelian", "Pemakaian sparepart", BEDA,
	 "Akun beban sama (5110.042). Bedanya dokumen: Inventory Usage di Ascend, Maintenance / Material Issue "
	 "di ERPNext; sparepart ber-Vehicle di PI langsung jadi beban.",
	 [("Inventory Usage", "", _jl("Usage"))],
	 [("Maintenance / Material Issue", "", _jl("Usage", side="E"))]),
	("Finance", "Kasbon", SAMA, "",
	 [("Pending Cash V2", "Paid", _jl("Pending Cash")), ("Refund", "sisa kembali", _jl("Pending Cash Refund"))],
	 [("Pending Cash", "Pay", _jl("Pending Cash", side="E")),
	  ("Pending Cash Refund", "", _jl("Pending Cash Refund", side="E"))]),
	("Finance", "Hutang lain", SETTING, "Hutang Karyawan hanya bila Supplier / Supplier Group diisi.",
	 [("A/P Note", "", _jl("APN")), _PV_A],
	 [("AP Note", "", _jl("APN", side="E")), _PV_E]),
	("Finance", "Piutang lain", SAMA, "",
	 [("A/R Note", "", _jl("ARN")), _RV_A],
	 [("AR Note", "", _jl("ARN", side="E")), _RV_E]),
	("Finance", "Tutup bulan dan tahun", SAMA,
	 "ERPNext otomatis tiap bulan dan tiap tahun (setting di Custom Setting tab Journal Entry); di Ascend yang "
	 "tahunan manual. ERPNext tanpa akun Ikhtisar L/R.",
	 [("PL", "akhir bulan", _jl("Tutup Laba Rugi")), ("PL-ANNUAL", "tanggal 1", _jl("Tutup Laba Rugi", 0, "A", 1)),
	  ("ADJ manual", "ganti tahun", _jl("Tutup Laba Rugi", 1))],
	 [("Period Closing Voucher", "akhir bulan", _jl("Tutup Laba Rugi", side="E")),
	  ("Journal Entry otomatis", "tanggal 1", _jl("Tutup Laba Rugi", 0, "E", 1)),
	  ("Journal Entry otomatis", "1 Januari", _jl("Tutup Laba Rugi", 1, "E"))]),
	("Gudang", "Koreksi stok", BEDA, "Lawan akun ERPNext satu Difference Account per dokumen.",
	 [("Inventory Adjustment", "", _jl("Adjustment"))],
	 [("Stock Reconciliation", "", _jl("Adjustment", side="E"))]),
	("Gudang", "Pindah dan rakit", SAMA, "",
	 [("Goods Transfer", "", None), ("Assembly", "", _jl("Assembly"))],
	 [("Material Transfer", "", None), ("Stock Entry Repack", "", _jl("Assembly", side="E"))]),
	# ---- varian Payment Voucher / Receipt Voucher / Note (kasus di JOURNAL_CASES modul yang sama)
	("Payment Voucher", "Bayar tagihan valas, selisih kurs", SETTING,
	 "ERPNext: selisih kurs ke Exchange Gain/Loss Company, sekarang tertukar dengan akun pembulatan.",
	 [("Expense Note", "USD", _jl("Expense Note")), ("Payment Voucher", "Transfer", _jl("Payment Voucher", 1))],
	 [("Expense Note", "USD", _jl("Expense Note", side="E")),
	  ("Payment Entry Pay", "bank valas", _jl("Payment Voucher", 1, "E"))]),
	("Payment Voucher", "Dibayar dari kasbon", SETTING,
	 "Bank tidak keluar. ERPNext: akun hutang supir perlu account type Payable.",
	 [("Pending Cash V2", "Paid", _jl("Pending Cash")), ("Payment Voucher", "tab Pnd. Cash", _jl("Payment Voucher", 3))],
	 [("Pending Cash", "Pay", _jl("Pending Cash", side="E")),
	  ("Payment Entry Pay", "Add Pending Cash", _jl("Payment Voucher", 3, "E"))]),
	("Payment Voucher", "Kas kecil, sisa kasbon kembali ke kas", SAMA, "",
	 [("Pending Cash V2", "Paid", _jl("Pending Cash")), ("Payment Voucher", "Cash", _jl("Payment Voucher", 4))],
	 [("Pending Cash", "Pay", _jl("Pending Cash", side="E")),
	  ("Payment Entry Pay", "Paid From kas kecil", _jl("Payment Voucher", 4, "E"))]),
	("Payment Voucher", "PPh dipotong saat bayar", SAMA, "",
	 [("Invoice Receipt AP", "IRP", _jl("Invoice Receipt AP")), ("Payment Voucher", "PPh", _jl("Payment Voucher", 5))],
	 [("Purchase Invoice", "", _jl("Purchase Invoice", side="E")),
	  ("Payment Entry Pay", "field PPh", _jl("Payment Voucher", 5, "E"))]),
	("Payment Voucher", "Debit Note per baris", SAMA, "",
	 [("A/P Note", "", _jl("APN")), ("Payment Voucher", "Debit Note baris", _jl("Payment Voucher", 6))],
	 [("AP Note", "", _jl("APN", side="E")), ("Payment Entry Pay", "Debit Note baris", _jl("Payment Voucher", 6, "E"))]),
	("Payment Voucher", "Settlement: hutang dipindah ke leasing", SAMA, "Tanpa bank.",
	 [("Invoice Receipt AP", "IRP", _jl("Invoice Receipt AP")),
	  ("Payment Voucher", "Method WriteOff", _jl("Payment Voucher", 8))],
	 [("Purchase Invoice", "", _jl("Purchase Invoice", side="E")),
	  ("Payment Entry Pay", "Mode Settlement", _jl("Payment Voucher", 8, "E"))]),
	("Payment Voucher", "Settlement Expense Note Minus", BEDA, "Belum ada padanan di Payment Entry.",
	 [("Expense Note (Minus)", "refund vendor", "Dr Hutang / Cr Biaya, kebalikan Expense Note"),
	  ("Payment Voucher", "Method WriteOff", _jl("Payment Voucher", 9))],
	 [("Expense Refund", "refund vendor", "Dr Hutang / Cr Biaya"),
	  ("Void, atau Journal Entry", "", _jl("Payment Voucher", 9, "E"))]),
	("Payment Voucher", "Is Expense (tanpa tagihan)", SAMA, "",
	 [("Payment Voucher", "Is Expense, Transfer", _jl("Payment Voucher", 10))],
	 [("Payment Entry Pay", "Expense / Income", _jl("Payment Voucher", 10, "E"))]),
	("Payment Voucher", "Is Expense + Settlement (reklas biaya)", SAMA, "",
	 [("Payment Voucher", "Is Expense, WriteOff", _jl("Payment Voucher", 12))],
	 [("Journal Entry", "atau PE Expense + Settlement", _jl("Payment Voucher", 12, "E"))]),
	("Payment Voucher", "Uang muka supplier lalu dialokasikan", SAMA, "",
	 [("Payment Voucher", "uang muka", "Dr Uang Muka Pembelian / Cr Bank"),
	  ("Jurnal baris PV", ".../001", _jl("Uang Muka"))],
	 [("Payment Entry Pay", "tanpa alokasi", "Dr Uang Muka Pembelian / Cr Bank"),
	  ("Payment Reconciliation", "", _jl("Uang Muka", side="E"))]),

	("Receipt Voucher", "Pembulatan sen", SETTING, "ERPNext: Round Off Account Company perlu ditukar ke 6210.003.",
	 [("Sales Invoice", "C/T", _jl("Sales Invoice", 0, "A", 1)), ("Receipt Voucher", "", _jl("Receipt Voucher", 2))],
	 [("Sales Invoice C/T", "", _jl("Sales Invoice", 0, "E", 1)),
	  ("Payment Entry Receive", "pembulatan", _jl("Receipt Voucher", 2, "E"))]),
	("Receipt Voucher", "Settlement: piutang ke pendapatan komisi", SETTING, "Tanpa bank.",
	 [("Sales Invoice", "C/T", _jl("Sales Invoice", 0, "A", 1)),
	  ("Receipt Voucher", "Method WriteOff", _jl("Receipt Voucher", 4))],
	 [("Sales Invoice C/T", "", _jl("Sales Invoice", 0, "E", 1)),
	  ("Payment Entry Receive", "Mode Settlement", _jl("Receipt Voucher", 4, "E"))]),
	("Receipt Voucher", "Is Revenue (tanpa invoice)", SAMA, "",
	 [("Receipt Voucher", "Is Revenue, Transfer", _jl("Receipt Voucher", 5))],
	 [("Payment Entry Receive", "Expense / Income", _jl("Receipt Voucher", 5, "E"))]),
	("Receipt Voucher", "Revaluasi saldo bank USD", BEDA, "",
	 [("Receipt Voucher", "Is Revenue, WriteOff", _jl("Receipt Voucher", 7))],
	 [("Exchange Rate Revaluation", "akhir bulan", _jl("Receipt Voucher", 7, "E"))]),
	("Receipt Voucher", "DP customer lalu dialokasikan", SAMA, "",
	 [("Receipt Voucher", "DP", "Dr Bank / Cr Uang Muka DP Penjualan"),
	  ("Jurnal baris RV", ".../001", _jl("Uang Muka", 1))],
	 [("Payment Entry Receive", "tanpa alokasi", "Dr Bank / Cr Uang Muka DP Penjualan"),
	  ("Payment Reconciliation", "", _jl("Uang Muka", 1, "E"))]),

	("A/P Note dan A/R Note", "A/P Note dengan PPN", SAMA, "",
	 [("A/P Note", "PPN", _jl("APN", 1)), _PV_A],
	 [("AP Note", "PPN", _jl("APN", 1, "E")), _PV_E]),
	("A/P Note dan A/R Note", "A/P Note PPN tidak dapat dikreditkan", SETTING,
	 "ERPNext: kosongkan PPN, masukkan ke nilai baris.",
	 [("A/P Note", "Tax Not Credited", _jl("APN", 2)), _PV_A],
	 [("AP Note", "tanpa PPN", _jl("APN", 2, "E")), _PV_E]),
	("A/P Note dan A/R Note", "A/P Note Prepaid lalu amortisasi", BEDA,
	 "Amortisasi bulanan belum ada di ERPNext.",
	 [("A/P Note", "Post As Prepaid", _jl("APN", 3)),
	  ("FA-DEP bulanan", "amortisasi", "Dr Biaya Asuransi / Cr Asuransi Dibayar Dimuka")],
	 [("AP Note", "akun Dibayar Dimuka", _jl("APN", 3, "E")),
	  ("Journal Entry manual", "tiap bulan", "Dr Biaya Asuransi / Cr Asuransi Dibayar Dimuka")]),
	("A/P Note dan A/R Note", "Setoran PPN ke Kas Negara (akun sama Debit dan Kredit)", BEDA,
	 "Ascend: note bernilai nol supaya bisa dibayar PV. ERPNext: langsung Payment Entry mode Expense.",
	 [("A/P Note", "akun sama dua sisi", _jl("APN", 4)),
	  ("Payment Voucher", "", "Dr Hutang Pajak PPN / Cr Bank")],
	 [("Payment Entry Pay", "Expense / Income", _jl("APN", 4, "E"))]),
	("A/P Note dan A/R Note", "A/R Discount Note ke akun beban", BEDA, "",
	 [("A/R Discount Note", "", _jl("ARN", 2))],
	 [("Journal Entry", "ber-party customer", _jl("ARN", 2, "E"))]),
	("A/P Note dan A/R Note", "A/R Note Prepaid (cashback)", SAMA, "",
	 [("A/R Note", "Prepaid", _jl("ARN", 3)), _RV_A],
	 [("AR Note", "akun Dibayar Dimuka", _jl("ARN", 3, "E")), _RV_E]),
]

# Lane Peta Alur yang tidak menyentuh jurnal sama sekali.
FLOWS_NO_JOURNAL = ("CRM (Lead sampai Estimation, Tender, Meeting), Email dan Assistant, Fleet order angkutan "
                    "(Dispatch Order, apps Mandor dan Sopir), put-away gudang (Goods Receive, Replan), Proforma "
                    "Invoice, Menu Tax.")


def _t_columns(lines):
	"""Baris jurnal -> pasangan (debit, kredit) untuk tabel T, tanpa nominal."""
	dr = [f"{c} {n}".strip() for c, n, d, k in lines if d]
	cr = [f"{c} {n}".strip() for c, n, d, k in lines if k]
	width = max(len(dr), len(cr))
	return list(zip(dr + [""] * (width - len(dr)), cr + [""] * (width - len(cr))))


def _tnode(title, desc, lines):
	"""Kotak dokumen + tabel T Debit | Kredit (alur akunnya yang dibandingkan, bukan nominal)."""
	if isinstance(lines, str):  # dokumen tanpa contoh nyata: ringkasan jurnalnya saja
		body = f'<div class="ds" style="margin-top:6px">{lines}</div>'
	elif not lines:
		body = '<div class="ds">Tanpa jurnal</div>'
	else:
		rows = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in _t_columns(lines))
		body = (f'<table class="j" style="margin:6px 0 0;font-size:12px"><tr><th>Debit</th><th>Kredit</th></tr>'
		        f"{rows}</table>")
	sub = f'<div class="ds">{desc}</div>' if desc else ""
	return (f'<div class="flow-node" style="max-width:320px;flex-basis:240px"><div class="nm">{title}</div>'
	        f"{sub}{body}</div>")


def _flow_row(label, nodes):
	return (f'<div class="ds" style="margin:6px 0 4px"><b>{label}</b></div><div class="flow" style="margin-bottom:8px">'
	        + _ARROW.join(_tnode(*n) for n in nodes) + "</div>")


def _journal_flow_html():
	parts, last = [], None
	for area, lane, status, note, asc, erp in JOURNAL_FLOWS:
		if area != last:
			parts.append(f'<div class="fh" style="font-size:15px;margin-top:18px">{area}</div>')
			last = area
		nt = f'<div class="fx">{note}</div>' if note else ""
		parts.append(f'<div class="box{" warn" if status != SAMA else ""}"><div class="bt">{lane} [{status}]</div>'
		             + _flow_row("Ascend", asc) + _flow_row("ERPNext", erp) + nt + "</div>")
	return ('<h2 style="font-size:17px;margin:20px 0 8px">Alur jurnal</h2>'
	        '<p class="lead">Alur dari Peta Alur ERP CMI, tiap dokumen dengan akun Debit dan Kreditnya. Baris atas '
	        "Ascend, baris bawah ERPNext. Status: Sama, Beda, atau Setting.</p>" + "".join(parts)
	        + f'<div class="box"><div class="bt">Alur tanpa jurnal</div>{FLOWS_NO_JOURNAL}</div>')


# Peta semua sumber jurnal Ascend (AC_JournalHeaderLinks.LinkType + jurnal tanpa link) di AS_CAKRA,
# dicocokkan ke dokumen ERPNext. Kolom: modul Ascend, sumber jurnal, jurnal 12 bulan (Okt 2025 - Sep 2026),
# dokumen ERPNext, kapan/bagaimana ERPNext menjurnal, ada di Compare Jurnal.
JOURNAL_SOURCES = [
	("Expense Note", "EXP.Expense", "86.847", "Expense Note", "Ya, Journal Entry otomatis saat Validate", "Ya"),
	("Payment Voucher / Receipt Voucher", "ARAP", "53.819", "Payment Entry Pay / Receive",
	 "Ya, GL di Payment Entry saat Validate", "Ya"),
	("Service Invoice (Customer)", "EXP.ServiceInvoiceCustomer", "12.177", "Sales Invoice tipe Expedition",
	 "Ya, GL di Sales Invoice saat Validate", "Ya"),
	("A/P Note, A/R Note, Discount Note", "ARAPNote", "10.483", "AP Note, AR Note, Credit Note",
	 "Ya, Journal Entry otomatis saat Validate (Credit Note: GL di invoice)", "Ya"),
	("Invoice Receipt (AR) reimburse", "InvoiceReceipt", "6.657", "Sales Invoice behavior Reimburse",
	 "Ya, GL di Sales Invoice saat Validate", "Ya"),
	("Pending Cash V2", "PendingCashV2", "6.196", "Pending Cash", "Ya, Journal Entry otomatis saat Pay", "Ya"),
	("Alokasi uang muka PV / RV", "ARAPItem", "3.540", "Payment Reconciliation / Get Advances",
	 "Ya, native saat dialokasikan", "Ya"),
	("Purchase Invoice", "Purchase", "2.971", "Purchase Invoice", "Ya, GL di Purchase Invoice saat Validate", "Ya"),
	("Invoice Receipt (AP)", "APReceipt", "2.885", "Tidak ada",
	 "Tidak perlu: Purchase Invoice langsung membentuk hutang", "Ya"),
	("Surat Jalan", "SPB", "2.148", "Delivery Note", "Ya, saat Submit (mode In Transit)", "Ya"),
	("Sales Invoice trading + Sales Return", "Sales", "2.061", "Sales Invoice Trading / Credit Note",
	 "Ya, GL di Sales Invoice saat Validate", "Ya"),
	("Service Invoice (Agent)", "EXP.ServiceInvoiceAgent", "1.554", "Sales Invoice tipe Expedition Agent",
	 "Ya, GL di Sales Invoice saat Validate", "Ya"),
	("Bank Deposit", "BankDeposit", "1.393", "Journal Entry / Payment Entry Internal Transfer",
	 "Ya, saat Submit", "Ya"),
	("A/P Note bagian HPP", "ARAPNote.HPP", "1.219", "AP Note isi Purchase Invoice (HPP)",
	 "Ya, Journal Entry + Landed Cost Voucher otomatis saat Validate", "Ya"),
	("Inventory Usage", "UsageReport", "885", "Stock Entry Material Issue / Fleet Maintenance",
	 "Ya, saat Submit / Validate", "Ya"),
	("Inventory Adjustment", "Adjustment", "289", "Stock Reconciliation / WMS Adjustment", "Ya, saat Submit", "Ya"),
	("Pending Cash Refund", "PendingCashV2Refund", "218", "Pending Cash Refund",
	 "Ya, Journal Entry otomatis saat Validate", "Ya"),
	("Assembly", "Assembly", "115", "Stock Entry Repack (Change Items)", "Ya, saat Submit", "Ya"),
	("GL Journal Voucher (manual)", "tanpa link, manual", "24", "Journal Entry", "Ya, saat Submit", "Ya"),
	("Tutup laba rugi bulanan + tahunan", "PL / PL-ANNUAL", "23", "Period Closing Voucher bulanan",
	 "Ya: PCV ke 3210.002 saat tutup buku, gulung ke 3210.001 otomatis tanggal 1; ganti tahun otomatis ke 3210.003 "
	 "(di Ascend ADJ manual)", "Ya"),
	("Fixed Asset Depreciation", "FA-Depreciation", "11", "Depreciation Entry (scheduler)",
	 "Ya, otomatis per jadwal", "Ya"),
	("Asset Sales", "FA.Sales", "8", "Sell Asset (Sales Invoice) / Scrap Asset", "Ya, saat Validate / Submit", "Ya"),
	("Asset Purchase", "FA.Purchase", "0 (terakhir 2021)", "Purchase Invoice item aset",
	 "Ya, GL di Purchase Invoice", "Ya"),
	("Asset Expense Note", "FA.ExpenseNote", "0 (terakhir Sep 2025)", "Journal Entry",
	 "Tidak dipakai lagi di Ascend", "Tidak"),
	("Bank Reconciliation", "BankReconciliation", "0 (terakhir 2022)", "Bank Reconciliation Tool",
	 "Tidak dipakai lagi di Ascend; di ERPNext hanya tanggal kliring, tanpa jurnal", "Tidak"),
]

# Modul Ascend yang dipakai tapi TIDAK membentuk jurnal (dokumen 12 bulan terakhir).
NON_JOURNAL = [
	("Packing List", "14.390", "Shipping List / Packing List", "Tidak berjurnal, sama"),
	("Purchase Order", "2.835", "Purchase Order", "Tidak berjurnal, sama (kecuali uang muka PO lewat Payment Entry)"),
	("Sales Order", "1.345", "Sales Order", "Tidak berjurnal, sama"),
	("Estimation", "1.076", "CRM Estimation", "Tidak berjurnal, sama"),
	("Nota Jaminan", "317", "Pending Cash tipe JMK (usulan)",
	 "Beda: di Ascend jurnalnya lewat PV/RV; di ERPNext dokumen jaminannya sendiri yang menjurnal saat Pay"),
	("Goods Transfer", "269", "Stock Entry Material Transfer", "Tanpa efek GL di keduanya"),
]


# Dokumen ERPNext yang menjurnal tanpa sumber jurnal tersendiri di Ascend.
ERP_ONLY = [
	("Expense Refund", "Journal Entry otomatis saat Validate",
	 "Di Ascend: Expense Note (Minus), ikut sumber EXP.Expense"),
	("Payment Entry mode Settlement", "GL di Payment Entry",
	 "Di Ascend: PV/RV method WriteOff, ikut sumber ARAP"),
	("Asset Capitalization", "GL saat Submit", "Tidak ada padanan; barang stok dijadikan aset"),
	("Exchange Rate Revaluation", "Journal Entry saat Submit", "Tidak ditemukan sumber jurnal revaluasi di AS_CAKRA"),
]


# Pilihan penyelesaian untuk modul yang statusnya Beda dan butuh keputusan; tampil setelah
# kasus modulnya (desk dan artifact). (judul, header, baris, saran).
JOURNAL_OPTIONS = {
	"Payment Voucher": (
		"Peta varian Payment Voucher dan Receipt Voucher Ascend (12 bulan, AS_CAKRA)",
		["Varian Ascend", "PV", "RV", "ERPNext", "Catatan"],
		[
			["Transfer menarik tagihan", "41.061", "5.489", "Payment Entry Pay / Receive", "Sama"],
			["Cash (kas kecil)", "5.563", "18", "Payment Entry, Paid From akun kas", "Sama"],
			["Settlement (Method WriteOff)", "444", "25", "Payment Entry, Mode of Payment Settlement",
			 "Settlement Account menggantikan bank"],
			["Is Expense / Is Revenue + Transfer", "419", "462", "Payment Entry, centang Expense / Income",
			 "Baris akun bebas tanpa tagihan"],
			["Is Expense / Is Revenue + Cash", "113", "160", "Sama, Paid From akun kas", ""],
			["Is Expense / Is Revenue + Settlement", "58", "7",
			 "Journal Entry (reklas) / Exchange Rate Revaluation", "RV revenue settlement dipakai untuk revaluasi bank USD"],
			["Dibayar dari kasbon (Pending Cash)", "4.503", "0", "Add Pending Cash", "Kelebihan kasbon masuk ke akun Paid From"],
			["PPh dipotong", "110", "3.355", "Field PPh", "Sama: RV ke 1200.003, PV ke 2120.002"],
			["Bank charges / pembulatan", "4.452", "1.072", "Pembulatan otomatis",
			 "Round Off dan Exchange Gain/Loss di Company tertukar"],
			["Debit / Credit Note per baris", "4.435", "580", "Debit / Credit Note per baris", "Sama"],
		],
		"Setting yang perlu dibereskan supaya varian di atas sama: (1) Company: Round Off Account = 6210.003 "
		"Bi. Rounded, Exchange Gain/Loss Account = 6110.002 Selisih Kurs; (2) account type 2170.001 Hutang "
		"Pengurus, 2170.003 Hutang Supir, 2170.004 Hutang Karyawan = Payable.",
	),
	"APN": (
		"Peta varian A/P Note dan A/R Note Ascend (12 bulan, AS_CAKRA)",
		["Varian Ascend", "Jumlah", "ERPNext", "Catatan"],
		[
			["A/P Note biasa (856 dengan PPN)", "10.344", "AP Note", "Sama"],
			["A/P Note PPN tidak dapat dikreditkan", "82", "AP Note tanpa PPN, PPN masuk nilai baris",
			 "Belum ada opsi khusus"],
			["A/P Note Prepaid", "14", "AP Note ke akun Dibayar Dimuka",
			 "Amortisasi bulanan belum ada (Ascend ikut FA-DEP)"],
			["A/P Note akun sama Debit dan Kredit", "40", "Payment Entry mode Expense",
			 "Setoran pajak ke Kas Negara; AP Note ERPNext menolak akun Payable di baris"],
			["A/P Note bagian HPP", "1.219", "AP Note isi Purchase Invoice (HPP)", "Sama, lewat Landed Cost Voucher"],
			["A/R Note biasa", "29", "AR Note", "Sama"],
			["A/R Discount Note", "9", "Credit Note / Journal Entry", "Ke akun beban: Journal Entry"],
			["A/R Note Prepaid", "5", "AR Note ke akun Dibayar Dimuka", "Sama"],
		],
		"Note di Ascend dibuat per divisi dan cabang (NoteType GA, PKG, OLEO, EMKL, F x J/M/S); di ERPNext "
		"padanannya AP Note Type.",
	),
	"Tutup Laba Rugi": (
		"Cara tutup laba rugi bulanan dan tahunan di ERPNext (sama dengan PL / PL-ANNUAL + ADJ tahunan Ascend)",
		["Langkah", "Di mana", "Isi"],
		[
			["1. Setting sekali per company", "ERPNext Custom Setting > tab Journal Entry > Tutup Laba Rugi Bulanan",
			 "Tambah baris: Company, Bulan Berjalan 3210.002, Tahun Berjalan 3210.001, Tahun Lalu 3210.003, "
			 "centang Bulanan Otomatis dan Tahunan Otomatis"],
			["2. Sebelum PCV pertama", "Migrasi saldo awal",
			 "Opening Entry harus selesai dulu: setelah ada PCV, ERPNext menolak Opening Entry"],
			["3. Tahun sebelumnya", "Accounting > Closing Periode",
			 "Kalau tahun lalu punya GL, tutup dulu dengan satu PCV tahunan"],
			["4. Tiap tutup buku bulanan", "Accounting > Closing Periode > + Add",
			 "Period End Date = akhir bulan, Closing Account = 3210.002, Submit. Jurnal gulung tanggal 1 "
			 "terbentuk sendiri (field Jurnal Gulung ke Tahun Berjalan)"],
			["5. Ganti tahun", "Accounting > Fiscal Year",
			 "Buat Fiscal Year tahun depan SEBELUM tutup buku Desember. PCV Desember otomatis membuat dua jurnal "
			 "tanggal 1 Januari: gulung Desember, lalu seluruh Tahun Berjalan ke Tahun Lalu"],
			["6. Koreksi bulan yang sudah ditutup", "Period Closing Voucher",
			 "Batalkan PCV mulai dari bulan terakhir mundur sampai bulan itu, koreksi, lalu tutup ulang berurutan"],
		],
		"Bedanya dengan Ascend: PCV sekaligus mengunci bulan (Ascend memisahkan PL dan Close Period), dan "
		"tidak ada akun Ikhtisar L/R karena akun laba rugi langsung dinolkan.",
	),
	"Jaminan": (
		"Cara membuat jaminan di ERPNext (Ascend setahun: 317 Nota Jaminan, semua dibayar PV, 271 kembali "
		"lewat RV, 10 dipotong pelayaran, 46 belum kembali)",
		["Langkah", "Di mana", "Isi"],
		[
			["1. Buat tipe Jaminan Keluar", "Finance > Pending Cash > Pending Cash Type > + Add",
			 "Code JMK, Title Jaminan Keluar, Direction Cash Outflow, Advance Account 1150.003 Piutang atas "
			 "Jaminan, Enabled dicentang"],
			["2. Samakan akun jaminan masuk", "Pending Cash Type JMN",
			 "Advance Account diganti dari 2150.003 Nota Jaminan ke 2150.001 Jaminan"],
			["3. Opsional: sisa per pelayaran", "Chart of Accounts > 1150.003 Piutang atas Jaminan",
			 "Account Type = Receivable supaya saldo jaminan terurai per pelayaran"],
			["4. Bayar jaminan", "Pending Cash > + Add",
			 "Type JMK, Pay To = pelayaran, Total, Bank Account, Connection = Packing List / Shipping List job, "
			 "isi rincian di Remark (BL, container, periode extend DO); Save, Validate, Pay"],
			["5. Jaminan kembali", "Tombol Refund di kasbonnya, atau Pending Cash Refund > + Add",
			 "Pilih kasbon JMK pelayaran itu (boleh beberapa sekaligus), Refund To Bank, Refund Date; Save, "
			 "Validate"],
			["6. Jaminan dipotong pelayaran", "Payment Entry Pay ke pelayaran",
			 "Tarik Expense Note tagihannya (mis. demurrage), Add Pending Cash pilih kasbon JMK-nya; sisanya "
			 "lewat langkah 5"],
		],
		"Kasbon lama yang sudah Paid tidak ikut berubah; setting hanya berlaku untuk kasbon baru.",
	),
}


def _journal_html():
	parts, last = [], None

	def flush(modul):
		if modul in JOURNAL_OPTIONS:
			title, head, rows, saran = JOURNAL_OPTIONS[modul]
			parts.append(f'<div class="box warn"><div class="bt">{title}</div>{_table(head, rows)}'
			             f'<div class="fx">{saran}</div></div>')

	for modul, asc, erp in JOURNAL_CASES:
		if modul != last:
			flush(last)
			parts.append(f'<h2 style="font-size:17px;margin:28px 0 8px">{modul}</h2>')
			last = modul
		warn = any(b[2] in (BEDA, SETTING) for b in erp)
		parts.append(f'<div class="box{" warn" if warn else ""}"><div style="display:flex;flex-wrap:wrap;gap:16px">'
		             + _jside("Ascend", modul, asc) + _jside("ERPNext", modul, erp) + "</div></div>")
	flush(last)
	peta = ('<h2 style="font-size:17px;margin:20px 0 8px">Peta sumber jurnal</h2>'
	        '<p class="lead">Semua sumber jurnal di AS_CAKRA dan padanannya di ERPNext.</p>'
	        + _table(["Modul Ascend", "Sumber jurnal", "Jurnal 12 bulan", "Dokumen ERPNext",
	                  "Terjurnal di ERPNext", "Ada di Compare Jurnal"], JOURNAL_SOURCES)
	        + '<div class="fh">Modul Ascend yang dipakai tapi tidak berjurnal</div>'
	        + _table(["Modul Ascend", "Dokumen 12 bulan", "Dokumen ERPNext", "Jurnal"], NON_JOURNAL)
	        + '<div class="fh">Dokumen ERPNext yang menjurnal tanpa sumber Ascend tersendiri</div>'
	        + _table(["Dokumen ERPNext", "Jurnal", "Keterangan"], ERP_ONLY))
	parts.insert(0, peta + _journal_flow_html())
	return ('<div class="mb"><h2>Compare Jurnal</h2><p class="lead">Ascend: jurnal nyata dari database '
	        "AS_CAKRA, pola akun yang paling sering muncul 12 bulan terakhir. ERPNext: jurnal untuk transaksi "
	        "yang sama menurut setting PT CMI. Status ERPNext: Sama = setara Ascend; Beda = akun atau alur "
	        "berbeda; Setting = sama asalkan master diisi. Kotak oranye = ada Beda atau Setting.</p>"
	        + "".join(parts) + "</div>")


JRN_HTML = _journal_html()


# ---------------------------------------------------------------- Landing + daftar

LANDING_BLOCKS = [
	{"type": "header", "data": {"text": '<span class="h4"><b>Compare: Ascend dan ERPNext</b></span>', "col": 12}},
	{"type": "paragraph", "data": {"col": 12, "text":
		"Cara input di Ascend dibanding ERPNext untuk tiap modul. Setiap halaman punya tiga tab: Ascend, "
		"ERPNext, dan Perbedaan."}},
	{"type": "paragraph", "data": {"col": 12, "text":
		"Pola umum: di Ascend dokumen disimpan, dicek, divalidasi, lalu diposting ke GL secara batch. "
		"Di ERPNext jurnal terbentuk saat dokumen di-Validate, tanpa langkah posting."}},
	{"type": "paragraph", "data": {"col": 12, "text":
		"Tanpa padanan di Ascend CIMI: Warehouse (rak dan bin), Fleet (modul Transport Ascend ada tetapi "
		"datanya kosong), Mail, Assistant, dan CRM."}},
]

# (nama workspace, ikon sidebar, html). Tambah modul = tambah baris.
COMPARES = [
	("Compare Basic", ICON, BASIC_HTML),
	("Compare Expedition", ICON, EXP_HTML),
	("Compare Selling", ICON, SELL_HTML),
	("Compare Purchase", ICON, PUR_HTML),
	("Compare Stock", ICON, STOCK_HTML),
	("Compare Payment Entry", ICON, PAY_HTML),
	("Compare Pending Cash", ICON, PC_HTML),
	("Compare AP AR Note", ICON, NOTE_HTML),
	("Compare Tax", ICON, TAX_HTML),
	("Compare Asset", ICON, ASSET_HTML),
	("Compare Accounting", ICON, ACC_HTML),
	("Compare Penjurnalan", ICON, GL_HTML),
	("Compare Jurnal", ICON, JRN_HTML),
]


def ensure_compare():
	ensure_book(SIDEBAR, LANDING_BLOCKS, COMPARES, ICON)

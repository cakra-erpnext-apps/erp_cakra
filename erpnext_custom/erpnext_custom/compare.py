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
	], "Dua tahap lewat akun Advance: Dr Advance / Cr Bank, lalu per dokumen Dr Hutang / Cr Advance. "
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
	], "Satu jurnal langsung Dr Hutang / Cr Bank, tanpa akun Advance perantara.")
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
		("Jurnal", "Otomatis saat Save, dua tahap lewat akun Advance", "Saat Validate, satu jurnal"),
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
]


def ensure_compare():
	ensure_book(SIDEBAR, LANDING_BLOCKS, COMPARES, ICON)

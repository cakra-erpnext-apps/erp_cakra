"""Definisi menu desk CMI. Data saja -- pembangunnya ada di desk_menu.py.

Bentuk satu item: (label, link_type, link_to, route_options|None)
  link_type: DocType / Page / Report / Workspace / Dashboard / URL
  route_options: filter list view, mis. {"is_return": 1}
Section break: (SB, judul)

`icon` = nama icon lucide (sprite frappe/public/icons/lucide.svg), `color` = warna
kotak iconnya di home desk. Keduanya dipakai desk_icons.build() untuk membuat file SVG
di public/icons/desktop_icons/ -- TANPA file itu desk cuma menggambar huruf awal label.
Ganti icon/warna? ubah di sini lalu jalankan build() lagi.
"""

SB = "--"


def L(label, link_type, link_to, route_options=None):
	return (label, link_type, link_to, route_options)


MENUS = [
	{
		"label": "Mail",
		"icon": "mail",
		"color": "#0EA5E9",
		"items": [
			L("Inbox", "DocType", "Communication", {"sent_or_received": "Received"}),
			L("Sent", "DocType", "Communication", {"sent_or_received": "Sent"}),
			L("Delete", "DocType", "Communication", {"status": "Closed"}),
			L("User Group Email", "DocType", "Email Group"),
			(SB, "Setting"),
			L("Email Account", "DocType", "Email Account"),
			L("Email Domain", "DocType", "Email Domain"),
			L("Email Queue", "DocType", "Email Queue"),
			L("Notification Settings", "DocType", "Notification Settings"),
		],
	},
	{
		"label": "Expedition",
		"icon": "ship",
		"color": "#0D9488",
		"items": [
			L("Dashboard", "Workspace", "Expedition"),
			L("Assistant Center", "Page", "assistant-center"),
			L("Estimation", "DocType", "CRM Estimation"),
			L("Packing List", "DocType", "Packing List"),
			L("Shipping List", "DocType", "Shipping List"),
			L("Expense Note", "DocType", "Expense Note"),
			L("Invoice", "DocType", "Sales Invoice"),
			(SB, "Report"),
			L("Expense Note Report", "Report", "Expense Note Report"),
		],
	},
	{
		"label": "Trading",
		"icon": "store",
		"color": "#F97316",
		"items": [
			L("Dashboard", "Workspace", "Selling"),
			L("Sales Order", "DocType", "Sales Order"),
			L("Delivery Note", "DocType", "Delivery Note"),
			L("Pick List", "DocType", "Pick List"),
			L("Sales Invoice", "DocType", "Sales Invoice"),
			L("Sales Return", "DocType", "Delivery Note", {"is_return": 1}),
			(SB, "Reports"),
			L("Sales Register", "Report", "Sales Register"),
			L("Sales Analytics", "Report", "Sales Analytics"),
			L("Item-wise Sales History", "Report", "Item-wise Sales History"),
			L("Sales Order Analysis", "Report", "Sales Order Analysis"),
			L("Sales Invoice Trends", "Report", "Sales Invoice Trends"),
		],
	},
	{
		"label": "Finance",
		"icon": "wallet",
		"color": "#16A34A",
		"items": [
			L("Dashboard Payment", "Dashboard", "Payments"),
			L("AR Note (Debit Piutang)", "DocType", "Sales Invoice", {"custom_invoice_type": "Debit Note"}),
			L("AP Note (Debit Hutang)", "Workspace", "AP Note"),
			L("Pending Cash", "DocType", "Pending Cash"),
			L("Payment Entry", "DocType", "Payment Entry"),
			L("Payment Reconciliation", "DocType", "Payment Reconciliation"),
			(SB, "Report"),
			L("Accounts Receivable", "Report", "Accounts Receivable"),
			L("Accounts Payable", "Report", "Accounts Payable"),
			L("General Ledger", "Report", "General Ledger"),
		],
	},
	{
		"label": "Banking",
		"icon": "landmark",
		"color": "#0891B2",
		"items": [
			L("Dashboard Banking", "Dashboard", "Accounts"),
			L("Bank Clearance", "DocType", "Bank Clearance"),
			L("Bank Reconciliation", "DocType", "Bank Reconciliation Tool"),
			L("Reconciliation Statement", "Report", "Bank Reconciliation Statement"),
			L("Unreconcile Payment", "DocType", "Unreconcile Payment"),
			L("Process Payment Reconciliation", "DocType", "Process Payment Reconciliation"),
			(SB, "Master"),
			L("Bank", "DocType", "Bank"),
			L("Bank Account", "DocType", "Bank Account"),
		],
	},
	{
		"label": "Invoicing",
		"icon": "file-text",
		"color": "#6366F1",
		"items": [
			L("Dashboard", "Workspace", "Invoicing"),
			L("Sales Invoice", "DocType", "Sales Invoice"),
			# "Asset Sales" versi ERPNext sendiri (workspace_sidebar/assets.json): tidak ada
			# doctype/field penjualan aset, yang ada report pelepasan aset difilter Sold.
			L("Asset Sales", "Report", "Asset Disposal", {"disposal_type": "Sold"}),
			L("Credit Note", "DocType", "Sales Invoice", {"is_return": 1}),
			L("Accounts Receivable", "Report", "Accounts Receivable"),
		],
	},
	{
		"label": "Accounting",
		"icon": "calculator",
		"color": "#7C3AED",
		"items": [
			L("Journal Entry", "DocType", "Journal Entry"),
			(SB, "Sumber Jurnal"),
			L("Expense Note", "DocType", "Expense Note"),
			L("Sales Invoice", "DocType", "Sales Invoice"),
			L("Purchase Invoice", "DocType", "Purchase Invoice"),
			L("Payment Entry", "DocType", "Payment Entry"),
			L("Pending Cash", "DocType", "Pending Cash"),
			L("Delivery Note", "DocType", "Delivery Note"),
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Stock Entry", "DocType", "Stock Entry"),
			(SB, "Laporan Keuangan"),
			L("Income Statement (Laba Rugi)", "Report", "Profit and Loss Statement"),
			L("Neraca (Balance Sheet)", "Report", "Balance Sheet"),
			L("Cash Flow", "Report", "Cash Flow"),
			L("Trial Balance", "Report", "Trial Balance"),
			L("General Ledger", "Report", "General Ledger"),
			L("Payment Ledger", "Report", "Payment Ledger"),
			(SB, "Setup"),
			L("Chart of Accounts", "DocType", "Account"),
			L("GL Entry", "DocType", "GL Entry"),
			L("Repost Accounting Ledger", "DocType", "Repost Accounting Ledger"),
			L("Closing Periode", "DocType", "Period Closing Voucher"),
		],
	},
	{
		"label": "Purchase",
		"icon": "shopping-cart",
		"color": "#D97706",
		"items": [
			L("Debit Note", "DocType", "Purchase Invoice", {"is_return": 1}),
			L("Purchase Order", "DocType", "Purchase Order"),
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Purchase Invoice", "DocType", "Purchase Invoice"),
		],
	},
	{
		"label": "Inventory",
		"icon": "boxes",
		"color": "#B45309",
		"items": [
			L("Dashboard", "Workspace", "Stock"),
			L("Stock Entry", "DocType", "Stock Entry"),
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Pick List", "DocType", "Pick List"),
			L("Change Items", "DocType", "Stock Entry", {"stock_entry_type": "Repack"}),
			L("Quality Inspection", "DocType", "Quality Inspection"),
			L("Quality Inspection Template", "DocType", "Quality Inspection Template"),
			(SB, "Reports"),
			L("Stock Balance", "Report", "Stock Balance"),
			L("Stock Ledger", "Report", "Stock Ledger"),
			L("Stock Projected Qty", "Report", "Stock Projected Qty"),
		],
	},
	{
		"label": "Warehouse",
		"icon": "warehouse",
		"color": "#64748B",
		"items": [
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Delivery Note", "DocType", "Delivery Note"),
			L("Pick List", "DocType", "Pick List"),
			L("Rack Transfer", "DocType", "Stock Entry", {"stock_entry_type": "Material Transfer"}),
			L("Stock Opname", "DocType", "Stock Reconciliation"),
			(SB, "Master"),
			# Satu doctype Warehouse, tiga tingkat pohon — dipisah lewat filter
			# warehouse_type (diisi otomatis, lihat rack_suggest.classify_warehouse).
			# Bentuk pohonnya sendiri dilihat lewat tombol Tree di list Rak.
			L("Gudang", "DocType", "Warehouse", {"warehouse_type": "Gudang"}),
			L("Rak", "DocType", "Warehouse", {"warehouse_type": "Rak"}),
			L("Bin Location", "DocType", "Warehouse", {"warehouse_type": "Bin"}),
			L("Rack Zone (Item Group)", "DocType", "Item Group"),
			L("Stock Settings", "DocType", "Stock Settings"),
			(SB, "Report"),
			L("Stock Balance", "Report", "Stock Balance"),
			L("Stock per Warehouse", "Report", "Warehouse wise Item Balance Age and Value"),
			L("Stock Ageing", "Report", "Stock Ageing"),
			L("Stock Ledger", "Report", "Stock Ledger"),
		],
	},
	{
		"label": "Organization",
		"icon": "building-2",
		"color": "#8B5CF6",
		"items": [
			L("Company", "DocType", "Company"),
			L("Departement", "DocType", "Department"),
			L("Branch", "DocType", "Branch"),
			L("User", "DocType", "User"),
			L("Role Permission", "Page", "permission-manager"),
			L("Role Profile", "DocType", "Role Profile"),
		],
	},
	{
		"label": "Items",
		"icon": "package",
		"color": "#DB2777",
		"items": [
			(SB, "Setup"),
			L("Stock Settings", "DocType", "Stock Settings"),
			L("Warehouse", "DocType", "Warehouse"),
			L("Unit of Measure (UOM)", "DocType", "UOM"),
			L("Item Variant Settings", "DocType", "Item Variant Settings"),
			L("Brand", "DocType", "Brand"),
			L("Item Attribute", "DocType", "Item Attribute"),
			L("UOM Conversion Factor", "DocType", "UOM Conversion Factor"),
			(SB, "Items & Pricing"),
			L("Item", "DocType", "Item"),
			L("Item Group", "DocType", "Item Group"),
			L("Price List", "DocType", "Price List"),
			L("Item Price", "DocType", "Item Price"),
			L("Pricing Rule", "DocType", "Pricing Rule"),
			L("Promotional Scheme", "DocType", "Promotional Scheme"),
			L("Coupon Code", "DocType", "Coupon Code"),
			L("Blanket Order", "DocType", "Blanket Order"),
		],
	},
	{
		"label": "Supplier",
		"icon": "factory",
		"color": "#65A30D",
		"items": [
			L("Supplier", "DocType", "Supplier"),
			L("Supplier Group", "DocType", "Supplier Group"),
			L("Item", "DocType", "Item"),
			L("Price List", "DocType", "Price List"),
			L("Address", "DocType", "Address"),
			L("Contacts", "DocType", "Contact"),
			(SB, "Scorecard"),
			L("Supplier Scorecard", "DocType", "Supplier Scorecard"),
			L("Scorecard Criteria", "DocType", "Supplier Scorecard Criteria"),
			L("Scorecard Variable", "DocType", "Supplier Scorecard Variable"),
			L("Scorecard Standing", "DocType", "Supplier Scorecard Standing"),
		],
	},
	{
		"label": "Customer",
		"icon": "users",
		"color": "#2563EB",
		"items": [
			L("Customer", "DocType", "Customer"),
			L("Customer Group", "DocType", "Customer Group"),
			L("Address", "DocType", "Address"),
			L("Contact", "DocType", "Contact"),
			L("Territory", "DocType", "Territory"),
			L("Campaign", "DocType", "Campaign"),
			L("Sales Person", "DocType", "Sales Person"),
			L("Sales Partner", "DocType", "Sales Partner"),
			L("Monthly Distribution", "DocType", "Monthly Distribution"),
			L("Terms Template", "DocType", "Terms and Conditions"),
			L("Tax Template", "DocType", "Sales Taxes and Charges Template"),
			L("Product Bundle", "DocType", "Product Bundle"),
			L("UTM Source", "DocType", "UTM Source"),
			L("Shipping Rule", "DocType", "Shipping Rule"),
		],
	},
	{
		"label": "Master",
		"icon": "database",
		"color": "#475569",
		"items": [
			(SB, "ERP"),
			L("Invoice Type", "DocType", "Invoice Type"),
			L("Purchase Order Type", "DocType", "Purchase Order Type"),
			L("Expense Note Type", "DocType", "Expense Note Type"),
			L("Packing List Type", "DocType", "Packing List Type"),
			(SB, "Expedition"),
			L("Location", "DocType", "Fleet Location"),
			L("Sandaran", "DocType", "Sandaran"),
			L("Shipping Line", "DocType", "Shipping Line"),
			L("Cargo", "DocType", "Cargo"),
			L("Container Size", "DocType", "Container Size"),
			L("Shipment Type", "DocType", "Shipment Type"),
			L("Jenis Karantina", "DocType", "Jenis Karantina"),
			L("Vessel", "DocType", "Vessel"),
			L("Voyage", "DocType", "Voyage"),
			(SB, "Fleet"),
			L("Vehicle", "DocType", "Vehicle"),
			L("Driver", "DocType", "Driver"),
			L("Fleet Location", "DocType", "Fleet Location"),
		],
	},
]

# Menu yang sudah ada dan dibiarkan apa adanya, cuma dipastikan tetap di baris depan.
KEEP_TOP_LEVEL = ["Assistant", "Manual Book", "Fleet", "Assets", "ERPNext Settings", "Frappe CRM"]

# Workspace kosong yang perlu ada supaya menunya bisa diklik (belum ada isinya).
PLACEHOLDER_WORKSPACES = [("AP Note", "dollar-sign")]


# Icon+warna untuk menu yang tidak dibangun dari MENUS (lihat KEEP_TOP_LEVEL) dan menu
# bawaan yang tetap tampil di home. Bentuk sama: label -> (icon lucide, warna).
EXTRA_ICONS = {
	"Assistant": ("bot", "#9333EA"),
	"Manual Book": ("book-open", "#0F766E"),
	"Fleet": ("truck", "#DC2626"),
	"Assets": ("briefcase", "#A16207"),
	"ERPNext Settings": ("settings", "#52525B"),
	"My Workspaces": ("grid-2x2", "#78716C"),
}

# Menu yang HANYA boleh dilihat pemegang role ini. Digarap lewat tabel `roles` milik
# Desktop Icon (Desktop Icon.is_permitted) -- termasuk anak-anak folder Default dan
# entri app switcher Framework, yang ikut hilang begitu induknya tidak diizinkan.
RESTRICTED = {
	"Default": "System Manager",
	"Framework": "System Manager",
	"ERPNext Settings": "System Manager",
}


def desk_icons():
	"""label -> (icon lucide, warna) untuk SEMUA menu yang punya icon sendiri."""
	icons = {m["label"]: (m["icon"], m["color"]) for m in MENUS}
	icons.update(EXTRA_ICONS)
	return icons

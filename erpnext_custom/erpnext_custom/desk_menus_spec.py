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
			L("Proforma Invoice", "DocType", "Proforma Invoice"),
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
			L("Payment Entry", "DocType", "Payment Entry"),
			L("Pending Cash", "DocType", "Pending Cash"),
			L("Pending Cash Refund", "DocType", "Pending Cash Refund"),
			L("AP Note (Debit Hutang)", "Workspace", "AP Note"),
			L("AR Note (Debit Piutang)", "DocType", "Sales Invoice", {"custom_invoice_type": "Debit Note"}),
			L("Expense Note", "DocType", "Expense Note"),
			L("Purchase Invoice", "DocType", "Purchase Invoice"),
			L("Sales Invoice", "DocType", "Sales Invoice"),
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
			L("Proforma Invoice", "DocType", "Proforma Invoice"),
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
			L("Pending Cash Refund", "DocType", "Pending Cash Refund"),
			L("Delivery Note", "DocType", "Delivery Note"),
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
		"label": "Tax",
		"icon": "percent",
		"color": "#E11D48",
		# Cerminan sidebar bawaan ERPNext "Taxes" (erpnext/workspace_sidebar/taxes.json).
		"items": [
			L("Core Tax", "Report", "Core Tax"),
			(SB, "Template"),
			L("Sales Tax Template", "DocType", "Sales Taxes and Charges Template"),
			L("Purchase Tax Template", "DocType", "Purchase Taxes and Charges Template"),
			L("Item Tax Template", "DocType", "Item Tax Template"),
			(SB, "Setup"),
			L("Tax Category", "DocType", "Tax Category"),
			L("Tax Rule", "DocType", "Tax Rule"),
			L("Tax Withholding Category", "DocType", "Tax Withholding Category"),
			L("Tax Withholding Group", "DocType", "Tax Withholding Group"),
			L("Deduction Certificate", "DocType", "Lower Deduction Certificate"),
			(SB, "Report"),
			L("Tax Withholding Details", "Report", "Tax Withholding Details"),
			L("TDS Computation Summary", "Report", "TDS Computation Summary"),
		],
	},
	{
		"label": "Audit",
		"icon": "search-check",
		"color": "#A21CAF",
		# Isinya menyusul; sementara cuma workspace kosong supaya menunya bisa diklik.
		"items": [
			L("Dashboard", "Workspace", "Audit"),
		],
	},
	{
		"label": "Purchase",
		"icon": "shopping-cart",
		"color": "#D97706",
		# Item PERTAMA = halaman yang dibuka saat icon menu diklik (get_route_for_icon),
		# jadi urutannya mengikuti alur beli: PO -> PI, retur di paling bawah.
		"items": [
			L("Purchase Order", "DocType", "Purchase Order"),
			L("Purchase Invoice", "DocType", "Purchase Invoice"),
			# Retur pembelian: stok DAN uang sama-sama lewat Debit Note (PI retur), karena
			# stok memang diakui di PI. Purchase Receipt tidak dipakai lagi.
			L("Debit Note", "DocType", "Purchase Invoice", {"is_return": 1}),
		],
	},
	{
		"label": "Inventory",
		"icon": "boxes",
		"color": "#B45309",
		"items": [
			L("Dashboard", "Workspace", "Stock"),
			L("Stock Entry", "DocType", "Stock Entry"),
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
			# Denah 2D rak per gudang: geser kotaknya, klik untuk lihat isi tiap tingkat.
			L("Layout", "Page", "warehouse-layout"),
			# Penerimaan barang: tarik baris Purchase Invoice, taruh di bin.
			# Rak & bin BUKAN warehouse -- tidak punya stok/jurnal, cuma peta item
			# mana ditaruh di mana; lihat erpnext_custom/bin_layout.py.
			L("Goods Receive", "DocType", "Goods Receive"),
			L("Pick List", "DocType", "Pick List"),
			L("Rack Transfer", "DocType", "Stock Entry", {"stock_entry_type": "Material Transfer"}),
			L("Stock Opname", "DocType", "Stock Reconciliation"),
			L("Isi Bin", "DocType", "Item Bin Qty"),
			(SB, "Master"),
			L("Gudang", "DocType", "Warehouse"),
			L("Rak", "DocType", "Rack"),
			L("Bin Location", "DocType", "Bin Location"),
			L("Rack Zone (Item Group)", "DocType", "Item Group"),
			L("Stock Settings", "DocType", "Stock Settings"),
			(SB, "Report"),
			L("Stock Balance", "Report", "Stock Balance"),
			L("Stock per Warehouse", "Report", "Warehouse wise Item Balance Age and Value"),
			# laporan yang sama, ditambah kolom Rak dan Bin (report/stock_per_rak)
			L("Stock per Rak", "Report", "Stock per Rak"),
			L("Stock Ageing", "Report", "Stock Ageing"),
			L("Stock Ledger", "Report", "Stock Ledger"),
		],
	},
	{
		# BUKAN "Organization": ada Translation en Organization -> Account (rename CRM) dan
		# desk merender label icon lewat __(), jadi menunya terbaca "Account" di home.
		"label": "Organisasi",
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
PLACEHOLDER_WORKSPACES = [("AP Note", "dollar-sign"), ("Audit", "search-check")]


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


# ---------------------------------------------------------------------------
# Icon per ITEM di dalam sidebar (bukan icon menu di home desk -- itu di
# desk_icons.py). Workspace Sidebar Item punya field `icon`, dirender lewat
# frappe.utils.icon() dari sprite lucide, jadi nilainya nama icon lucide.
# NAMA SALAH = kotak kosong tanpa error, karena itu divalidasi test_desk_menu.
#
# Urutan pencarian: label dulu (satu doctype bisa dipakai beberapa menu dengan arti
# beda -- "Credit Note" vs "Sales Invoice"), lalu link_to, lalu jenis linknya.
ITEM_ICON_BY_LABEL = {
	"Inbox": "inbox",
	"Sent": "send",
	"Delete": "trash-2",
	"User Group Email": "users",
	"Dashboard": "layout-dashboard",
	"Dashboard Payment": "gauge",
	"Dashboard Banking": "gauge",
	"Invoice": "file-text",
	"Proforma Invoice": "file-clock",
	"Credit Note": "undo-2",
	"Debit Note": "undo-2",
	"Sales Return": "undo-2",
	"Purchase Return": "package-x",
	"AR Note (Debit Piutang)": "file-plus",
	"AP Note (Debit Hutang)": "file-minus",
	"Chart of Accounts": "list-tree",
	"Closing Periode": "lock",
	"Income Statement (Laba Rugi)": "trending-up",
	"Neraca (Balance Sheet)": "scale",
	"Trial Balance": "scale",
	"Cash Flow": "arrow-left-right",
	"Reconciliation Statement": "file-check",
	"Rack Transfer": "arrow-left-right",
	"Change Items": "repeat",
	"Stock Opname": "clipboard-check",
	"Gudang": "warehouse",
	"Rak": "columns-3",
	"Bin Location": "box",
	"Layout": "layout-grid",
	"Goods Receive": "package-plus",
	"Isi Bin": "boxes",
	"Rack Zone (Item Group)": "grid-2x2",
	"Stock per Warehouse": "warehouse",
	"Stock per Rak": "columns-3",
	"Location": "map-pin",
	"Unit of Measure (UOM)": "ruler",
	"Role Permission": "shield-check",
	"Assistant Center": "bot",
	"Core Tax": "stamp",
	"Departement": "building",
	"Tax Template": "percent",
	"Terms Template": "scroll-text",
	"Asset Sales": "briefcase",
	"Expense Note Report": "receipt",
}

ITEM_ICON_BY_LINK = {
	# --- master & umum
	"Account": "list-tree",
	"Address": "map-pin",
	"Bank": "landmark",
	"Bank Account": "credit-card",
	"Bank Clearance": "check-check",
	"Bank Reconciliation Tool": "arrow-left-right",
	"Blanket Order": "file-stack",
	"Branch": "git-branch",
	"Brand": "tag",
	"CRM Estimation": "calculator",
	"Campaign": "megaphone",
	"Cargo": "package",
	"Communication": "mail",
	"Company": "building-2",
	"Contact": "contact",
	"Container Size": "container",
	"Coupon Code": "ticket",
	"Customer": "user-round",
	"Customer Group": "users-round",
	"Delivery Note": "truck",
	"Department": "building",
	"Driver": "user-round-check",
	"Email Account": "at-sign",
	"Email Domain": "globe",
	"Email Group": "users",
	"Email Queue": "send",
	"Expense Note": "receipt",
	"Expense Note Type": "tags",
	"Fleet Location": "map-pin",
	"GL Entry": "book-open",
	"Invoice Type": "tags",
	"Item": "package",
	"Item Attribute": "sliders-horizontal",
	"Item Group": "folder-tree",
	"Item Price": "tag",
	"Item Tax Template": "percent",
	"Item Variant Settings": "settings-2",
	"Jenis Karantina": "shield-alert",
	"Journal Entry": "book-text",
	"Lower Deduction Certificate": "file-badge",
	"Monthly Distribution": "calendar-range",
	"Notification Settings": "bell",
	"Packing List": "clipboard-list",
	"Packing List Type": "tags",
	"Payment Entry": "banknote",
	"Payment Reconciliation": "arrow-left-right",
	"Pending Cash": "wallet",
	"Pending Cash Refund": "hand-coins",
	"Period Closing Voucher": "lock",
	"Pick List": "list-checks",
	"Price List": "list",
	"Pricing Rule": "percent",
	"Process Payment Reconciliation": "refresh-cw",
	"Product Bundle": "boxes",
	"Promotional Scheme": "gift",
	"Purchase Invoice": "receipt-text",
	"Purchase Order": "shopping-cart",
	"Purchase Order Type": "tags",
	"Purchase Receipt": "package-check",
	"Purchase Taxes and Charges Template": "percent",
	"Quality Inspection": "badge-check",
	"Quality Inspection Template": "clipboard-check",
	"Repost Accounting Ledger": "refresh-cw",
	"Role Profile": "shield",
	"Sales Invoice": "file-text",
	"Sales Order": "file-check",
	"Sales Partner": "handshake",
	"Sales Person": "briefcase",
	"Sales Taxes and Charges Template": "percent",
	"Sandaran": "anchor",
	"Shipment Type": "tags",
	"Shipping Line": "ship",
	"Shipping List": "ship",
	"Shipping Rule": "truck",
	"Stock Entry": "arrow-left-right",
	"Stock Reconciliation": "clipboard-check",
	"Stock Settings": "settings",
	"Supplier": "factory",
	"Supplier Group": "building-2",
	"Supplier Scorecard": "star",
	"Supplier Scorecard Criteria": "list-checks",
	"Supplier Scorecard Standing": "award",
	"Supplier Scorecard Variable": "variable",
	"Tax Category": "tags",
	"Tax Rule": "gavel",
	"Tax Withholding Category": "badge-percent",
	"Tax Withholding Group": "users",
	"Terms and Conditions": "scroll-text",
	"Territory": "map",
	"UOM": "ruler",
	"UOM Conversion Factor": "arrow-left-right",
	"UTM Source": "link",
	"Unreconcile Payment": "unlink",
	"User": "user",
	"Vehicle": "truck",
	"Vessel": "ship",
	"Voyage": "route",
	"Warehouse": "warehouse",
	"assistant-center": "bot",
	"permission-manager": "shield-check",
	# --- report
	"Accounts Receivable": "arrow-down-left",
	"Accounts Payable": "arrow-up-right",
	"General Ledger": "book-open",
	"Payment Ledger": "book-open",
	"Profit and Loss Statement": "trending-up",
	"Balance Sheet": "scale",
	"Stock Balance": "boxes",
	"Stock Ledger": "book-open",
	"Stock Ageing": "hourglass",
	"Stock Projected Qty": "trending-up",
	"Asset Disposal": "briefcase",
	"Tax Withholding Details": "book-open",
	# --- Fleet (sidebar milik app erp, bukan dari MENUS)
	"Tire": "circle-dot",
	"Tire On Off": "wrench",
	"Vulkanisir Request": "flame",
	"Storing": "archive",
	"Tire Type": "tags",
	"Tire Size": "ruler",
	"Tire Manufacturer": "factory",
	"Vehicle Joint": "layout-grid",
	"Vehicle Tire": "target",
	"Tire KM Setting": "gauge",
	"Tire Numbering": "hash",
	"Vehicle Variant": "car-front",
	"Driver Skill": "award",
	"GPS Vendor": "satellite",
	# --- Assets (sidebar bawaan ERPNext)
	"Asset": "briefcase",
	"Asset Category": "tags",
	"Asset Maintenance": "wrench",
	"Asset Maintenance Team": "users",
	"Asset Maintenance Log": "clipboard-list",
	"Asset Value Adjustment": "sliders-horizontal",
	"Asset Repair": "hammer",
	"Location": "map-pin",
	"Fixed Asset Register": "book-open",
	"Asset Depreciation Ledger": "trending-down",
	"Asset Depreciations and Balances": "trending-down",
	"Asset Activity": "activity",
	# --- Frappe CRM
	"CRM Lead": "user-plus",
	"CRM Lead Status": "flag",
	"CRM Lead Source": "radio",
	"CRM Deal Status": "flag",
	"CRM Inquiry": "handshake",
	"CRM Organization": "building-2",
	"CRM Industry": "factory",
	"CRM Territory": "map",
	"CRM Communication Status": "message-circle",
	"CRM Service Level Agreement": "clock",
	"Assignment Rule": "user-check",
	"Frappe CRM": "house",
}

# Cadangan kalau tidak ada di dua peta di atas.
ITEM_ICON_BY_TYPE = {
	"Report": "chart-column",
	"Workspace": "layout-dashboard",
	"Dashboard": "gauge",
	"Page": "app-window",
	"URL": "external-link",
	"DocType": "file-text",
}


def item_icon(label, link_type, link_to):
	icon = ITEM_ICON_BY_LABEL.get(label) or ITEM_ICON_BY_LINK.get(link_to)
	# Semua doctype "* Settings" (belasan, isinya sama saja) pakai satu icon -- tak ada
	# gunanya didaftar satu per satu.
	if not icon and str(link_to or "").endswith("Settings"):
		icon = "settings"
	return icon or ITEM_ICON_BY_TYPE.get(link_type, "file-text")

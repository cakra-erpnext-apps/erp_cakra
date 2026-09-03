"""Definisi menu desk CMI. Data saja -- pembangunnya ada di desk_menu.py.

Bentuk satu item: (label, link_type, link_to, route_options|None)
  link_type: DocType / Page / Report / Workspace / Dashboard / URL
  route_options: filter list view, mis. {"is_return": 1}
Section break: (SB, judul)
"""

SB = "--"


def L(label, link_type, link_to, route_options=None):
	return (label, link_type, link_to, route_options)


MENUS = [
	{
		"label": "Mail",
		"icon": "mail",
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
		"icon": "truck",
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
		"icon": "sell",
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
		"icon": "dollar-sign",
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
		"icon": "receipt-text",
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
		"icon": "file",
		"items": [
			L("Dashboard", "Workspace", "Invoicing"),
			L("Credit Note", "DocType", "Sales Invoice", {"is_return": 1}),
			L("Accounts Receivable", "Report", "Accounts Receivable"),
			(SB, "Reports"),
			L("Sales Register", "Report", "Sales Register"),
			L("Item-wise Sales Register", "Report", "Item-wise Sales Register"),
			L("Accounts Receivable Summary", "Report", "Accounts Receivable Summary"),
		],
	},
	{
		"label": "Accounting",
		"icon": "accounting",
		"items": [
			L("Repost Accounting Ledger", "DocType", "Repost Accounting Ledger"),
			L("GL Entry", "DocType", "GL Entry"),
			L("General Ledger", "Report", "General Ledger"),
			L("Closing Periode", "DocType", "Period Closing Voucher"),
		],
	},
	{
		"label": "Purchase",
		"icon": "buying",
		"items": [
			L("Debit Note", "DocType", "Purchase Invoice", {"is_return": 1}),
			L("Purchase Order", "DocType", "Purchase Order"),
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Purchase Invoice", "DocType", "Purchase Invoice"),
		],
	},
	{
		"label": "Inventory",
		"icon": "stock",
		"items": [
			L("Dashboard", "Workspace", "Stock"),
			L("Stock Entry", "DocType", "Stock Entry"),
			L("Purchase Receipt", "DocType", "Purchase Receipt"),
			L("Pick List", "DocType", "Pick List"),
			L("Change Items", "DocType", "Stock Entry", {"stock_entry_type": "Repack"}),
			(SB, "Reports"),
			L("Stock Balance", "Report", "Stock Balance"),
			L("Stock Ledger", "Report", "Stock Ledger"),
			L("Stock Projected Qty", "Report", "Stock Projected Qty"),
		],
	},
	{
		"label": "Asset",
		"icon": "assets",
		"items": [
			L("Asset", "DocType", "Asset"),
			L("Depreciation Schedule", "DocType", "Asset Depreciation Schedule"),
			L("Asset Movement", "DocType", "Asset Movement"),
			L("Asset Value Adjustment", "DocType", "Asset Value Adjustment"),
			L("Asset Repair", "DocType", "Asset Repair"),
			(SB, "Reports"),
			L("Fixed Asset Register", "Report", "Fixed Asset Register"),
			L("Asset Depreciation Ledger", "Report", "Asset Depreciation Ledger"),
			L("Asset Depreciations and Balances", "Report", "Asset Depreciations and Balances"),
			(SB, "Master"),
			L("Asset Category", "DocType", "Asset Category"),
			L("Asset Item", "DocType", "Item", {"is_fixed_asset": 1}),
			L("Location", "DocType", "Location"),
		],
	},
	{
		"label": "Organization",
		"icon": "organization",
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
		"icon": "table",
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
		"icon": "buying",
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
		"icon": "folder-normal",
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
KEEP_TOP_LEVEL = ["Assistant", "Manual Book", "Fleet", "ERPNext Settings", "Frappe CRM"]

# Workspace kosong yang perlu ada supaya menunya bisa diklik (belum ada isinya).
PLACEHOLDER_WORKSPACES = [("AP Note", "dollar-sign")]

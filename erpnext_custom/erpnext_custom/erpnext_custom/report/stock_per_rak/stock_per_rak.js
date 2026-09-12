// Filter sama persis dengan laporan bawaan yang dibungkus, supaya hasilnya
// bisa diadu langsung. Lihat stock_per_rak.py.
frappe.query_reports["Stock per Rak"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
			reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1,
			default: frappe.datetime.get_today() },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "warehouse", label: __("Gudang"), fieldtype: "Link", options: "Warehouse",
			get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company") } }) },
		{ fieldname: "filter_total_zero_qty", label: __("Filter Total Zero Qty"), fieldtype: "Check", default: 1 },
	],
};

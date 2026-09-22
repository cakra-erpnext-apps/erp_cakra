frappe.query_reports["Bin Adjustment History"] = {
	filters: [
		{ fieldname: "gudang", label: __("Gudang"), fieldtype: "Link", options: "Warehouse",
			get_query: () => ({ filters: { is_group: 0 } }) },
		{ fieldname: "bin_location", label: __("Bin"), fieldtype: "Link", options: "Bin Location",
			get_query: () => ({ filters: { gudang: frappe.query_report.get_filter_value("gudang") || undefined } }) },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
			default: frappe.datetime.get_today() },
	],
};

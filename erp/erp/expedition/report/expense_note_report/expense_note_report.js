// Copyright (c) 2026, Cakra Mandiri Indonesia

frappe.query_reports["Expense Note Report"] = {
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Detail", "Summary", "Outstanding", "Per Job"],
			default: "Detail",
			reqd: 1,
			on_change: () => {
				erp_en_report_toggle();
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: [
				"Supplier",
				"Expense Class",
				"Expense Note Type",
				"Expense Account",
				"Cost Center",
				"Branch Office",
				"Month",
			],
			default: "Supplier",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "vendor",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "expense_note_type",
			label: __("Type"),
			fieldtype: "Link",
			options: "Expense Note Type",
		},
		{
			fieldname: "expense_class",
			label: __("Expense Class"),
			fieldtype: "Link",
			options: "Expense Class",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "branch_office",
			label: __("Branch"),
			fieldtype: "Link",
			options: "CMI Office",
		},
		{
			fieldname: "shipping_list",
			label: __("Shipping List"),
			fieldtype: "Link",
			options: "Shipping List",
		},
		{
			fieldname: "packing_list",
			label: __("Packing List"),
			fieldtype: "Link",
			options: "Packing List",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Validated", "Half Paid", "Paid", "Closed", "Void"],
		},
		{
			fieldname: "include_void",
			label: __("Include Void"),
			fieldtype: "Check",
		},
	],

	onload: () => erp_en_report_toggle(),

	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "outstanding" && data && data.age > 90) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		return value;
	},
};

// Filter yang tidak berlaku untuk view aktif disembunyikan, bukan diabaikan diam-diam.
function erp_en_report_toggle() {
	const report = frappe.query_report;
	if (!report || !report.get_filter_value) return;
	const view = report.get_filter_value("view") || "Detail";
	const hide = {
		group_by: view !== "Summary",
		expense_class: view === "Outstanding",
		status: view === "Outstanding",
		include_void: view === "Outstanding",
	};
	for (const [fieldname, hidden] of Object.entries(hide)) {
		report.toggle_filter_display(fieldname, hidden);
	}
}

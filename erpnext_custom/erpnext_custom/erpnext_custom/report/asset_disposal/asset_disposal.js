// Filter laporan Asset Disposal. Rentang tanggal sengaja LEBAR secara default
// (awal tahun s/d hari ini) -- aset lama tanggal pelepasannya bisa jauh ke belakang.
frappe.query_reports["Asset Disposal"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "disposal_type",
			label: __("Type"),
			fieldtype: "Select",
			options: ["", "Sold", "Scrapped"].join("\n"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "gain_loss" && data && data.gain_loss) {
			const color = data.gain_loss > 0 ? "green" : "red";
			value = `<span style="color:${color}">${value}</span>`;
		}
		return value;
	},
};

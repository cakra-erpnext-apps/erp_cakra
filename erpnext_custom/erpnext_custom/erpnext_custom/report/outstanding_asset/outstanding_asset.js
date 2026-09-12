// Default filter sengaja "Outstanding": yang dicari orang di laporan ini adalah
// pembelian aset yang kartunya BELUM dibuat, bukan daftar lengkapnya.
frappe.query_reports["Outstanding Asset"] = {
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
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Outstanding", "Belum", "Sebagian", "Sudah"].join("\n"),
			default: "Outstanding",
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
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({ filters: { is_fixed_asset: 1 } }),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "outstanding_qty" && data.outstanding_qty > 0) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		if (column.fieldname === "status") {
			const color = { Belum: "red", Sebagian: "orange", Sudah: "green" }[data.status];
			if (color) value = `<span style="color:var(--${color}-500)">${value}</span>`;
		}
		return value;
	},
};

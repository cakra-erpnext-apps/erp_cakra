// Akun yang BENAR-BENAR dipakai saat transaksi per Customer / Supplier / Item, beserta
// asalnya (master sendiri, grup, atau default Company). Lihat account_mapping.py.
frappe.query_reports["Account Mapping"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
			reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "jenis", label: __("Jenis"), fieldtype: "Select",
			options: ["", "Customer", "Supplier", "Item"] },
		{ fieldname: "akun_untuk", label: __("Akun Untuk"), fieldtype: "Select",
			options: ["", "Piutang", "Hutang", "Uang Muka", "Persediaan", "HPP", "Pemakaian", "Penjualan", "Reimburse"] },
		{ fieldname: "grup", label: __("Grup"), fieldtype: "Data" },
		{ fieldname: "kode", label: __("Kode / Nama"), fieldtype: "Data" },
		{ fieldname: "hanya_masalah", label: __("Hanya yang bermasalah"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status !== "OK") {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};

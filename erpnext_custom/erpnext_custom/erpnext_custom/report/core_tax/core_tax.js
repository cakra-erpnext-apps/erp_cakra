// Filter + tombol unduh XML. File XML-nya dibangun di server (erpnext_custom.coretax),
// di sini cuma disimpan jadi file lewat Blob -- tidak lewat File doctype supaya file
// pajak tidak nyangkut di lampiran situs.
frappe.query_reports["Core Tax"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Perusahaan"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("Dari Tanggal"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("Sampai Tanggal"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "vat_rate",
			label: __("Tarif PPN Dilaporkan"),
			fieldtype: "Select",
			options: "12\n11",
			default: "12",
		},
	],

	onload(report) {
		report.page.add_inner_button(__("Download XML"), () => {
			frappe.call({
				method: "erpnext_custom.coretax.export_xml",
				args: { filters: report.get_filter_values(true) },
				freeze: true,
				freeze_message: __("Menyusun XML Coretax..."),
				callback(r) {
					if (!r.message) return;
					const link = document.createElement("a");
					link.href = URL.createObjectURL(
						new Blob([r.message.xml], { type: "application/xml" })
					);
					link.download = r.message.filename;
					link.click();
					URL.revokeObjectURL(link.href);
					frappe.show_alert({
						message: __("{0} faktur diexport, {1} dilewati", [
							r.message.ok,
							r.message.skipped,
						]),
						indicator: r.message.skipped ? "orange" : "green",
					});
				},
			});
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const color = data.status === "Siap" ? "green" : "red";
			value = `<span style="color: var(--text-on-${color}); background: var(--bg-${color}); padding: 0 6px; border-radius: 4px">${value}</span>`;
		}
		return value;
	},
};

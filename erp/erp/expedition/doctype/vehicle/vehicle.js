// Pilihan Device ID di tabel GPS Source dibatasi ke unit milik vendor pada baris itu.
frappe.ui.form.on('Vehicle', {
	setup(frm) {
		frm.set_query('device_id', 'gps_sources', (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return { filters: { vendor: row.vendor || '' } };
		});
	},
});

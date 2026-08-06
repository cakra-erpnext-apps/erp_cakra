frappe.listview_settings['Driver Monitor'] = {
	hide_name_column: true,
	get_indicator(doc) {
		const color = { 'On Job': 'blue', Ready: 'green', Absensi: 'orange', 'Belum Absen': 'gray' };
		return [__(doc.status), color[doc.status] || 'gray', `status,=,${doc.status}`];
	},
};

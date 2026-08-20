// Tombol uji koneksi & tarik unit — keduanya memanggil server, key tidak pernah ke browser.
frappe.ui.form.on('GPS Vendor', {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__('Test Connection'), () =>
			frappe.call({
				method: 'erp.fleet.gps_sync.test_connection',
				args: { vendor: frm.doc.name },
				freeze: true,
				callback: (r) => {
					frappe.msgprint({
						title: __('Test Connection'),
						message: r.message,
						indicator: (r.message || '').startsWith('OK') ? 'green' : 'red',
					});
					frm.reload_doc();
				},
			})
		);
		frm.add_custom_button(__('Tarik Unit dari Vendor'), () =>
			frappe.call({
				method: 'erp.fleet.gps_sync.pull_devices',
				args: { vendor: frm.doc.name },
				freeze: true,
				callback: (r) => frappe.msgprint({ title: __('Tarik Unit'), message: r.message, indicator: 'blue' }),
			})
		);
		frm.add_custom_button(__('Daftar Unit Vendor'), () =>
			frappe.set_route('List', 'GPS Device', { vendor: frm.doc.name })
		);
		frm.add_custom_button(__('Sync Now'), () =>
			frappe.call({
				method: 'erp.fleet.gps_sync.sync_vendor',
				args: { vendor: frm.doc.name },
				freeze: true,
				callback: (r) => {
					frappe.show_alert({ message: r.message, indicator: 'green' });
					frm.reload_doc();
				},
			})
		);
	},
});

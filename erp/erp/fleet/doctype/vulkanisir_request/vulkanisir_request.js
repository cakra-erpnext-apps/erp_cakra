frappe.ui.form.on('Vulkanisir Request', {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !frm.doc.received) {
			frm.add_custom_button(__('Terima dari Vendor'), () => {
				frappe.confirm(
					__('Terima {0} ban? Emboss tetap, hitungan vulkanisir +1, KM di-reset.', [frm.doc.items.length]),
					() =>
						frm.call('receive').then((r) => {
							frappe.show_alert({ message: __('{0} ban diterima', [r.message.count]), indicator: 'green' });
							frm.reload_doc();
						})
				);
			}).addClass('btn-primary');
		}
	},
	setup(frm) {
		// ban yang boleh divulkanisir: tidak sedang terpasang
		frm.set_query('tire', 'items', () => ({ filters: { tire_status: ['in', ['Available', 'Apkir']] } }));
	},
});

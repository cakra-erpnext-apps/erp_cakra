frappe.ui.form.on('Vehicle Joint', {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__('Generate Slot Ban'), () => {
			frappe.prompt(
				[{ fieldname: 'vehicle', fieldtype: 'Link', options: 'Vehicle', label: __('Vehicle (kosong = semua)') }],
				(v) =>
					frappe.call({
						method: 'erp.fleet.doctype.vehicle_joint.vehicle_joint.generate_vehicle_tires',
						args: { vehicle: v.vehicle || null },
						freeze: true,
						callback: (r) =>
							frappe.show_alert({ message: __('{0} slot dibuat', [r.message.created]), indicator: 'green' }),
					}),
				__('Generate posisi ban dari layout'),
				__('Generate')
			);
		});
	},
});

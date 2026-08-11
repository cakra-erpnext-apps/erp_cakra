frappe.ui.form.on('Tire On Off', {
	setup(frm) {
		// posisi hanya slot milik vehicle di baris itu
		frm.set_query('vehicle_tire', 'items', (doc, cdt, cdn) => ({
			query: 'erp.fleet.doctype.tire_on_off.tire_on_off.slot_query',
			filters: { vehicle: locals[cdt][cdn].vehicle },
		}));
		frm.set_query('vehicle_tire_to', 'items', (doc, cdt, cdn) => ({
			query: 'erp.fleet.doctype.tire_on_off.tire_on_off.slot_query',
			filters: { vehicle: locals[cdt][cdn].vehicle_to || locals[cdt][cdn].vehicle },
		}));
		// hanya ban siap pakai (bukan yang sedang terpasang/vulkanisir/scrap)
		for (const f of ['ban_luar', 'ban_dalam', 'marset']) {
			frm.set_query(f, 'items', () => ({ filters: { tire_status: 'Available' } }));
		}
	},
});

frappe.ui.form.on('Tire On Off Detail', {
	vehicle(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, { vehicle_tire: '', position: '' });
	},
	vehicle_tire(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.vehicle_tire) return;
		// tampilkan ban yang sedang menempel (diisi ulang oleh server saat save)
		frappe.db.get_doc('Vehicle Tire', row.vehicle_tire).then((slot) => {
			frappe.model.set_value(cdt, cdn, {
				position: slot.position,
				ban_luar_lama: slot.ban_luar,
				ban_dalam_lama: slot.ban_dalam,
				marset_lama: slot.marset,
			});
		});
	},
});

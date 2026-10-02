// Aksi task ada di halaman Orchestrator (satu tempat); form ini cukup mengarah ke sana.
frappe.ui.form.on('Agent Task', {
	refresh(frm) {
		frm.add_custom_button(__('Buka di Orchestrator'), () => { frappe.route_options = { task: frm.doc.name }; frappe.set_route('orchestrator'); });
	},
});

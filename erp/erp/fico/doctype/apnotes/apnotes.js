// AP Note: form bersama, lihat erp/public/js/note_form.js.
cmi_note_form('APNotes', 'APNote Details', { label: 'AP Note', what: 'hutang' });

// Biaya HPP: hanya PI tervalidasi yang menambah stok (syarat Landed Cost Voucher).
frappe.ui.form.on('APNotes', {
	setup(frm) {
		frm.set_query('purchase_invoice', () => ({
			filters: { docstatus: 1, update_stock: 1, company: frm.doc.company || undefined },
		}));
	},
});

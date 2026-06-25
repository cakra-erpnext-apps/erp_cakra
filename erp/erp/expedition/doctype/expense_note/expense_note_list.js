// List View settings untuk Expense Note.
// - Indikator status berwarna (Draft / Validated / Closed / Void) + klik untuk filter.
// - add_fields memuat field flag yang dipakai indikator (tidak ditampilkan sebagai kolom).
frappe.listview_settings['Expense Note'] = {
	add_fields: ['validated', 'closed', 'void', 'is_reimburse'],

	get_indicator(doc) {
		if (doc.void) return [__('Void'), 'red', 'void,=,1'];
		if (doc.closed) return [__('Closed'), 'gray', 'closed,=,1'];
		if (doc.validated) return [__('Validated'), 'green', 'validated,=,1'];
		return [__('Draft'), 'orange', 'validated,=,0'];
	},
};

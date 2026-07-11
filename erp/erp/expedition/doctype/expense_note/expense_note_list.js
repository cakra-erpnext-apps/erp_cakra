// List View settings untuk Expense Note.
// - Indikator status berwarna (Void / Paid / Validated) + klik untuk filter.
//   Dokumen yang belum divalidasi TIDAK diberi badge (tidak ada status "Draft").
// - add_fields memuat field flag yang dipakai indikator (tidak ditampilkan sebagai kolom).
// Lebarkan kolom ID (subject) agar nomor panjang (EXP/IMP/0008/OGM/26) tidak terpotong.
// Scoped ke .erp-fin-list (halaman ini) supaya tak memengaruhi list doctype lain.
function erp_en_widen(listview) {
	if (!document.getElementById('erp-en-style')) {
		const s = document.createElement('style');
		s.id = 'erp-en-style';
		s.textContent = `
		.erp-fin-list .list-row-head .list-subject, .erp-fin-list .list-row .list-subject { flex: 0 0 220px !important; max-width: 220px !important; padding-right: 5px !important; }
		.erp-fin-list .list-subject .ellipsis, .erp-fin-list .list-subject a, .erp-fin-list .list-subject .level-item, .erp-fin-list .list-subject span {
			max-width: none !important; overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; }`;
		document.head.appendChild(s);
	}
	if (listview && listview.page && listview.page.wrapper) $(listview.page.wrapper).addClass('erp-fin-list');
}

frappe.listview_settings['Expense Note'] = {
	add_fields: ['validated', 'paid', 'void', 'is_reimburse', 'owner', '_assign'],

	// Kolom display: created_by / assigned_to adalah field kosong (hidden di form) —
	// isinya dirender dari owner & _assign standar Frappe lewat formatter ini.
	formatters: {
		created_by(value, df, doc) {
			return frappe.utils.escape_html(frappe.user.full_name(doc.owner) || doc.owner || '');
		},
		assigned_to(value, df, doc) {
			let users = [];
			try { users = JSON.parse(doc._assign || '[]'); } catch (e) { /* bukan JSON -> kosong */ }
			return frappe.utils.escape_html(users.map((u) => frappe.user.full_name(u) || u).join(', '));
		},
		validated_by(value) {
			return frappe.utils.escape_html(value ? (frappe.user.full_name(value) || value) : '');
		},
	},

	get_indicator(doc) {
		if (doc.void) return [__('Void'), 'red', 'void,=,1'];
		if (doc.paid) return [__('Paid'), 'blue', 'paid,=,1'];
		if (doc.validated) return [__('Validated'), 'green', 'validated,=,1'];
		return; // belum validate: tanpa badge
	},

	onload(listview) { erp_en_widen(listview); },
	refresh(listview) { erp_en_widen(listview); },
};

// List View Sales Invoice (extend bawaan erpnext, JANGAN timpa get_indicator dll).
// - Kolom display Created By / Assign To: field kosong (hidden di form) yang dirender
//   dari owner & _assign standar lewat formatter.
// - Kolom ID (subject) disamakan lebarnya dengan kolom lain (default subject flex 2 ->
//   kolom customer tampak sempit). Scoped ke halaman ini saja.
// PENTING: formatter WAJIB mengembalikan HTML (diawali "<") — list_view.js melakukan
// $(column_html); string polos seperti email dianggap CSS selector oleh jQuery -> throw
// -> list mati (kejadian di Expense Note, lihat expense_note_list.js).
function cmi_si_txt(s) {
	return '<span>' + frappe.utils.escape_html(s == null ? '' : String(s)) + '</span>';
}

function cmi_si_style(listview) {
	if (!document.getElementById('cmi-si-style')) {
		const s = document.createElement('style');
		s.id = 'cmi-si-style';
		// Subject (ID) default flex:2 — samakan dengan kolom biasa (flex:1) supaya
		// kolom Customer dkk kebagian lebar yang sama.
		s.textContent = `
		.cmi-si-list .list-row-head .list-subject, .cmi-si-list .list-row .list-subject { flex: 1 1 0 !important; min-width: 170px; }`;
		document.head.appendChild(s);
	}
	if (listview && listview.page && listview.page.wrapper) $(listview.page.wrapper).addClass('cmi-si-list');
}

(function () {
	const base = frappe.listview_settings['Sales Invoice'] || {};
	const base_onload = base.onload; // bulk action Delivery Note/Payment bawaan erpnext

	base.add_fields = [...(base.add_fields || []), 'owner', '_assign'];
	base.formatters = Object.assign(base.formatters || {}, {
		custom_created_by(value, df, doc) {
			return cmi_si_txt(frappe.user.full_name(doc.owner) || doc.owner);
		},
		custom_assigned_to(value, df, doc) {
			let users = [];
			try { users = JSON.parse(doc._assign || '[]'); } catch (e) { /* bukan JSON -> kosong */ }
			if (!Array.isArray(users)) users = [];
			return cmi_si_txt(users.map((u) => frappe.user.full_name(u) || u).join(', '));
		},
	});
	base.onload = function (listview) {
		if (typeof base_onload === 'function') {
			try { base_onload(listview); } catch (e) { console.error('si list base onload', e); }
		}
		cmi_si_style(listview);
	};
	base.refresh = function (listview) { cmi_si_style(listview); };
	frappe.listview_settings['Sales Invoice'] = base;
})();

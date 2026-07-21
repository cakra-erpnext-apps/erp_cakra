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
		// Subject (ID) default flex:2 — samakan dengan kolom biasa (flex:1) supaya kolom
		// Customer dkk kebagian lebar yang sama. min-width WAJIB !important: .list-row-col
		// bawaan memasang min-width sendiri (150px, dan `auto` di layar kecil), dan dengan
		// belasan kolom yang semuanya flex:1 tidak ada yang kebagian lebih dari min-width-nya
		// — jadi angka inilah lebar sebenarnya. Nomor terpanjang di data 17 karakter
		// ("C/E/0001/OGM/25-1") ditambah checkbox + padding.
		s.textContent = `
		.cmi-si-list .list-row-head .list-subject, .cmi-si-list .list-row .list-subject { flex: 1 1 0 !important; min-width: 180px !important; }
		.cmi-si-list .list-subject .level-item.bold, .cmi-si-list .list-subject a { max-width: none !important; }`;
		document.head.appendChild(s);
	}
	if (listview && listview.page && listview.page.wrapper) $(listview.page.wrapper).addClass('cmi-si-list');
}

(function () {
	const base = frappe.listview_settings['Sales Invoice'] || {};
	const base_onload = base.onload; // bulk action Delivery Note/Payment bawaan erpnext

	base.add_fields = [...(base.add_fields || []), 'owner', '_assign', 'custom_customer_paid'];
	base.formatters = Object.assign(base.formatters || {}, {
		// Kolom "Paid": Check 0/1 -> pill hijau/abu. custom_customer_paid diturunkan dari
		// Paid Date di server (before_validate), jadi cukup baca nilainya.
		custom_customer_paid(value, df, doc) {
			const paid = cint(doc.custom_customer_paid);
			return `<span class="indicator-pill ${paid ? 'green' : 'gray'} filterable ellipsis">
				<span>${paid ? __('Paid') : __('Unpaid')}</span></span>`;
		},
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
	// Badge & aksi bulk Validate/Invalidate/Void/Unvoid: logika di public/js/workflow_list.js
	// (dipakai bareng Payment Entry). Istilah CMI: Draft / Validated / Void.
	base.add_fields = [...base.add_fields, 'docstatus'];
	base.get_indicator = cmi_workflow_indicator;
	base.onload = function (listview) {
		if (typeof base_onload === 'function') {
			try { base_onload(listview); } catch (e) { console.error('si list base onload', e); }
		}
		cmi_si_style(listview);
		cmi_workflow_list_actions(listview, 'Sales Invoice', __('Invoice'));
	};
	base.refresh = function (listview) {
		cmi_si_style(listview);
		cmi_workflow_list_actions(listview, 'Sales Invoice', __('Invoice'));
	};
	frappe.listview_settings['Sales Invoice'] = base;
})();

// List View settings untuk Expense Note.
// - Indikator status berwarna (Void / Paid / Validated) + klik untuk filter.
//   Dokumen yang belum divalidasi TIDAK diberi badge (tidak ada status "Draft").
// - add_fields memuat field flag yang dipakai indikator (tidak ditampilkan sebagai kolom).
// Lebarkan kolom ID (subject) agar nomor panjang (EXP/IMP/0008/OGM/26) tidak terpotong.
// Scoped ke .erp-fin-list (halaman ini) supaya tak memengaruhi list doctype lain.
// Bungkus teks jadi HTML aman untuk formatter list view (lihat catatan di `formatters`).
function erp_en_txt(s) {
	return '<span>' + frappe.utils.escape_html(s == null ? '' : String(s)) + '</span>';
}

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
	// PENTING: formatter WAJIB mengembalikan HTML (diawali "<"), bukan teks polos.
	// list_view.js melakukan `$(column_html)` — string yang tidak diawali "<" dianggap
	// CSS SELECTOR oleh jQuery. Nilai seperti email ("a@b.com") bukan selector valid ->
	// jQuery throw -> render list MATI (list kosong, padahal datanya ada). Ini terjadi
	// saat user tak punya Full Name, karena frappe.user.full_name() jatuh ke email.
	formatters: {
		created_by(value, df, doc) {
			return erp_en_txt(frappe.user.full_name(doc.owner) || doc.owner);
		},
		assigned_to(value, df, doc) {
			let users = [];
			try { users = JSON.parse(doc._assign || '[]'); } catch (e) { /* bukan JSON -> kosong */ }
			if (!Array.isArray(users)) users = [];
			return erp_en_txt(users.map((u) => frappe.user.full_name(u) || u).join(', '));
		},
		validated_by(value) {
			return erp_en_txt(value ? (frappe.user.full_name(value) || value) : '');
		},
	},

	get_indicator(doc) {
		if (doc.void) return [__('Void'), 'red', 'void,=,1'];
		if (doc.paid) return [__('Paid'), 'blue', 'paid,=,1'];
		if (doc.validated) return [__('Validated'), 'green', 'validated,=,1'];
		return; // belum validate: tanpa badge
	},

	onload(listview) { erp_en_widen(listview); erp_en_actions(listview); },
	refresh(listview) { erp_en_widen(listview); erp_en_actions(listview); },
};

// Pasang bulk actions (Validate / Void) di menu Actions. DIGUARD: saat `onload`,
// `listview.page` bisa BELUM siap — kalau langsung dipanggil, throw -> list view gagal
// init -> daftar tampak KOSONG. Karena itu dicek dulu, dan dipasang sekali saja
// (dipanggil ulang dari refresh saat page sudah ada).
function erp_en_actions(listview) {
	if (!listview || !listview.page || typeof listview.page.add_actions_menu_item !== 'function') return;
	if (listview._erp_en_actions) return;
	listview._erp_en_actions = true;
	try {
		listview.page.add_actions_menu_item(__('Validate'), () => erp_en_bulk(listview, 'validate'), true);
		listview.page.add_actions_menu_item(__('Void'), () => erp_en_bulk(listview, 'void'), true);
	} catch (e) {
		console.error('expense note bulk actions', e);
	}
}

// Bulk Validate / Void dari list view. Lewat server bulk_set_state -> save() tiap doc,
// jadi cek Expense Account tetap jalan (yang akunnya kosong GAGAL, tidak tervalidasi).
function erp_en_bulk(listview, action) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__('Centang Expense Note dulu.'));
		return;
	}
	const run = (reason) => {
		frappe.call({
			method: 'erp.expedition.doctype.expense_note.expense_note.bulk_set_state',
			args: { names, action, reason },
			freeze: true,
			freeze_message: action === 'void' ? __('Mem-void…') : __('Memvalidasi…'),
			callback(r) {
				const res = (r && r.message) || {};
				const okN = (res.ok || []).length;
				const failed = res.failed || [];
				let msg = __('Berhasil: {0}', [okN]);
				if (failed.length) {
					msg += '<br><br>' + __('Gagal: {0}', [failed.length]) + '<br>' +
						failed.map((f) => `<b>${frappe.utils.escape_html(f.name)}</b>: ${frappe.utils.escape_html(f.error)}`).join('<br>');
				}
				frappe.msgprint({
					title: action === 'void' ? __('Void') : __('Validate'),
					message: msg,
					indicator: failed.length ? 'orange' : 'green',
				});
				listview.clear_checked_items && listview.clear_checked_items();
				listview.refresh();
			},
		});
	};
	if (action === 'void') {
		frappe.prompt(
			[{ fieldname: 'reason', fieldtype: 'Small Text', label: __('Alasan Void'), reqd: 1 }],
			(v) => run(v.reason),
			__('Void {0} Expense Note', [names.length]),
			__('Void')
		);
	} else {
		frappe.confirm(__('Validasi {0} Expense Note terpilih?', [names.length]), () => run());
	}
}

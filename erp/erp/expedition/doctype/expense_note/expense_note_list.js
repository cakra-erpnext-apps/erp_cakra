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
		.erp-fin-list .list-row-head .list-subject, .erp-fin-list .list-row .list-subject { flex: 0 0 250px !important; max-width: 250px !important; padding-right: 5px !important; }
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
		// Dua tombol TOGGLE: aksinya ditentukan dari state tiap dokumen terpilih.
		listview.page.add_actions_menu_item(__('Validate / Invalidate'), () => erp_en_toggle(listview, 'validate'), true);
		listview.page.add_actions_menu_item(__('Void / Unvoid'), () => erp_en_toggle(listview, 'void'), true);
	} catch (e) {
		console.error('expense note bulk actions', e);
	}
}

// Toggle Validate/Invalidate atau Void/Unvoid dari list view.
//   kind='validate' -> yang belum validated di-Validate, yang sudah di-Invalidate.
//   kind='void'     -> yang belum void di-Void, yang sudah di-Unvoid.
// Modal menampilkan SEMUA dokumen terpilih, dikelompokkan per aksi, supaya user tahu
// persis apa yang akan terjadi ke masing-masing (penting saat bulk campuran).
function erp_en_toggle(listview, kind) {
	const docs = listview.get_checked_items(); // full row (add_fields memuat validated/void/paid)
	if (!docs.length) {
		frappe.msgprint(__('Centang Expense Note dulu.'));
		return;
	}

	const field = kind === 'void' ? 'void' : 'validated';
	const onAction = kind === 'void' ? 'void' : 'validate';   // set flag = 1
	const offAction = kind === 'void' ? 'unvoid' : 'invalidate'; // set flag = 0
	const onLabel = kind === 'void' ? __('Void') : __('Validate');
	const offLabel = kind === 'void' ? __('Unvoid') : __('Invalidate');

	const toOn = docs.filter((d) => !d[field]).map((d) => d.name);
	const toOff = docs.filter((d) => d[field]).map((d) => d.name);

	const esc = frappe.utils.escape_html;
	const listHtml = (title, arr, color) =>
		arr.length
			? `<div style="margin-bottom:8px"><b style="color:var(--${color})">${title} (${arr.length})</b><br>` +
			  arr.map((n) => esc(n)).join('<br>') + '</div>'
			: '';

	// Kalimat konfirmasi & label tombol mengikuti aksinya. Kalau seleksi seragam
	// (semua Validate, atau semua Invalidate) -> pakai kata aksinya. Kalau campuran
	// -> sebut keduanya, tombolnya generik.
	let actionWord, btnLabel;
	if (toOn.length && !toOff.length) {
		actionWord = onLabel;
		btnLabel = onLabel;
	} else if (toOff.length && !toOn.length) {
		actionWord = offLabel;
		btnLabel = offLabel;
	} else {
		actionWord = `${onLabel} / ${offLabel}`;
		btnLabel = __('Proses');
	}
	const question =
		`<p style="margin-bottom:10px">${__('Apakah anda yakin ingin {0} Expense Note di bawah ini?', [actionWord])}</p>`;

	let body = question;
	body += listHtml(onLabel, toOn, kind === 'void' ? 'red-600' : 'green-600');
	body += listHtml(offLabel, toOff, kind === 'void' ? 'blue-600' : 'orange-600');

	// Void butuh alasan (hanya untuk yang akan di-Void).
	const needReason = kind === 'void' && toOn.length;

	const d = new frappe.ui.Dialog({
		title: kind === 'void' ? __('Void / Unvoid') : __('Validate / Invalidate'),
		fields: [
			{ fieldtype: 'HTML', fieldname: 'info', options: body },
			...(needReason
				? [{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Alasan Void'), reqd: 1 }]
				: []),
		],
		primary_action_label: btnLabel,
		primary_action(v) {
			d.hide();
			erp_en_run(listview, [
				{ names: toOn, action: onAction, reason: v.reason },
				{ names: toOff, action: offAction },
			]);
		},
	});
	d.show();
}

// Jalankan beberapa grup aksi (validate+invalidate atau void+unvoid) berurutan,
// lalu tampilkan ringkasan gabungan berhasil/gagal.
function erp_en_run(listview, groups) {
	groups = groups.filter((g) => g.names && g.names.length);
	const okAll = [];
	const failAll = [];
	const step = (i) => {
		if (i >= groups.length) {
			let msg = __('Berhasil: {0}', [okAll.length]);
			if (failAll.length) {
				msg += '<br><br>' + __('Gagal: {0}', [failAll.length]) + '<br>' +
					failAll.map((f) => `<b>${frappe.utils.escape_html(f.name)}</b>: ${frappe.utils.escape_html(f.error)}`).join('<br>');
			}
			frappe.msgprint({ title: __('Selesai'), message: msg, indicator: failAll.length ? 'orange' : 'green' });
			listview.clear_checked_items && listview.clear_checked_items();
			listview.refresh();
			return;
		}
		const g = groups[i];
		frappe.call({
			method: 'erp.expedition.doctype.expense_note.expense_note.bulk_set_state',
			args: { names: g.names, action: g.action, reason: g.reason },
			freeze: true,
			freeze_message: __('Memproses…'),
			callback(r) {
				const res = (r && r.message) || {};
				(res.ok || []).forEach((n) => okAll.push(n));
				(res.failed || []).forEach((f) => failAll.push(f));
				step(i + 1);
			},
		});
	};
	step(0);
}

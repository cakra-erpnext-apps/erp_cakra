// Form bersama AP Note (APNotes) dan AR Note (ARNotes). Dimuat app-wide (hooks
// app_include_js); tiap doctype JS cukup memanggil cmi_note_form(...) dengan konfigurasinya.
// Baris diisi lewat modal Add Item (grid cuma tampilan), jumlah dihitung live; server
// (erp.fico.notes._calculate_totals) tetap sumber kebenarannya saat save.
//
// cfg: { label: 'AP Note', what: 'hutang' }
function cmi_note_form(doctype, child_doctype, cfg) {
	frappe.ui.form.on(doctype, {
		setup(frm) {
			const company = () => frm.doc.company || frappe.defaults.get_default('company');
			frm.set_query('cost_center', () => ({ filters: { company: company(), is_group: 0 } }));
			frm.set_query('account', 'items', () => ({ filters: { company: company(), is_group: 0 } }));
			frm.set_query('note_type', () => ({ filters: { disabled: 0 } }));
		},
		onload(frm) {
			if (frm.is_new() && !frm.doc.currency) {
				const company = frm.doc.company || frappe.defaults.get_default('company');
				frappe.db.get_value('Company', company, 'default_currency').then((r) => {
					if (!frm.doc.currency) frm.set_value('currency', r.message?.default_currency);
				});
			}
		},
		refresh(frm) {
			cmi_note_wide_associate(frm);
			cmi_note_items_grid(frm);
			cmi_note_buttons(frm, cfg);
			cmi_note_totals(frm);
			if (frm.doc.journal_entry) {
				frm.add_custom_button(__('Accounting Ledger'), () => {
					frappe.route_options = {
						voucher_no: frm.doc.journal_entry, from_date: frm.doc.date, to_date: frm.doc.date,
						company: frm.doc.company, categorize_by: '',
					};
					frappe.set_route('query-report', 'General Ledger');
				}, __('View'));
			}
		},
		tax_input(frm) { cmi_note_apply_input(frm, 'tax'); },
		pph_input(frm) { cmi_note_apply_input(frm, 'pph'); },
	});

	frappe.ui.form.on(child_doctype, {
		items_remove: cmi_note_totals,
		// Tabel Items read-only: baris tidak diedit di grid. Klik baris -> dialog.
		form_render(frm, cdt, cdn) {
			frm.fields_dict.items.grid.grid_rows_by_docname[cdn]?.toggle_view(false);
			if (!(frm.doc.validated || frm.doc.void)) cmi_note_item_dialog(frm, cdn);
		},
	});
}

// Tombol Add Item di bawah tabel (tabelnya read-only, Add Row bawaan tidak tampil).
function cmi_note_items_grid(frm, cfg) {
	// Baris baru hanya lewat modal: Add Row bawaan dimatikan (property ini tidak bisa
	// disimpan di JSON DocField versi Frappe ini, jadi dipasang dari sini). Centang + Delete
	// bawaan tetap ada untuk menghapus baris.
	frm.set_df_property('items', 'cannot_add_rows', 1);
	const grid = frm.fields_dict.items.grid;
	grid.wrapper.find('.cmi-note-add-item').remove();
	if (frm.doc.validated || frm.doc.void) return;
	grid.add_custom_button(__('Add Item'), () => cmi_note_item_dialog(frm), 'bottom')
		.addClass('cmi-note-add-item btn-primary');
}

// Modal isi / edit satu baris. cdn kosong = baris baru.
//   Price | Qty | Amount
//   Account Code | Cost Center
//   Notes
function cmi_note_item_dialog(frm, cdn) {
	const row = cdn ? locals[frm.fields_dict.items.grid.doctype][cdn] : null;
	const company = frm.doc.company || frappe.defaults.get_default('company');
	const amount = () => d.set_value('amount', flt(d.get_value('qty')) * flt(d.get_value('price')));
	const d = new frappe.ui.Dialog({
		title: row ? __('Edit Item #{0}', [row.idx]) : __('Add Item'),
		size: 'large',
		fields: [
			{ fieldname: 'price', fieldtype: 'Currency', label: __('Price'), default: 0, onchange: amount },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'qty', fieldtype: 'Float', label: __('Qty'), default: 1, onchange: amount },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'amount', fieldtype: 'Currency', label: __('Amount'), default: 0, read_only: 1 },
			{ fieldtype: 'Section Break' },
			{
				fieldname: 'account', fieldtype: 'Link', options: 'Account', label: __('Account Code'), reqd: 1,
				get_query: () => ({ filters: { company, is_group: 0 } }),
			},
			{ fieldtype: 'Column Break' },
			{
				fieldname: 'cost_center', fieldtype: 'Link', options: 'Cost Center', label: __('Cost Center'),
				default: frm.doc.cost_center,
				get_query: () => ({ filters: { company, is_group: 0 } }),
			},
			{ fieldtype: 'Section Break' },
			{ fieldname: 'description', fieldtype: 'Small Text', label: __('Notes') },
		],
		primary_action_label: __('Save'),
		primary_action(v) {
			const target = row || frm.add_child('items');
			Object.assign(target, {
				account: v.account, cost_center: v.cost_center || '', description: v.description || '',
				qty: flt(v.qty), price: flt(v.price), amount: flt(v.qty) * flt(v.price),
			});
			frm.refresh_field('items');
			cmi_note_totals(frm);
			frm.dirty();
			d.hide();
		},
	});
	if (row) {
		d.set_values({
			price: row.price, qty: row.qty, amount: row.amount,
			account: row.account, cost_center: row.cost_center, description: row.description,
		});
		d.set_secondary_action_label(__('Delete'));
		d.set_secondary_action(() => {
			frappe.model.clear_doc(row.doctype, row.name);
			frm.refresh_field('items');
			cmi_note_totals(frm);
			frm.dirty();
			d.hide();
		});
	}
	d.show();
}

// Indikator status list (dipakai kedua list view).
function cmi_note_listview() {
	return {
		add_fields: ['status'],
		get_indicator(doc) {
			const color = { Draft: 'gray', Validated: 'blue', Paid: 'green', Void: 'red' }[doc.status] || 'gray';
			return [__(doc.status || 'Draft'), color, 'status,=,' + (doc.status || 'Draft')];
		},
	};
}

// Baris pertama: Type | Date | Supplier/Customer, yang terakhir selebar 2 kolom (3 + 3 + 6 dari 12).
function cmi_note_wide_associate(frm) {
	const col = frm.fields_dict.associate.$wrapper.closest('.form-column');
	col.removeClass('col-sm-4').addClass('col-sm-6');
	col.siblings('.form-column').removeClass('col-sm-4').addClass('col-sm-3');
}

// ---- Smart input PPN / PPh (pola Expense Note) -------------------------------------
// Satu field teks per komponen: "11%" = persen dari Amount Total, "150.000" = nominal.
// Disimpan di tax_pct/tax_amount & pph_pct/pph_amount (hidden); server menghitung ulang
// persen saat save. Helper angka = salinan en_* di expense_note.js (tesnya membaca source
// file itu, jadi tidak dipindah); ubah di dua tempat kalau aturannya berubah.
function cmi_note_prec() {
	const p = cint(frappe.boot?.sysdefaults?.currency_precision);
	return p > 0 ? p : 2;
}
function cmi_note_num_format() {
	const nf = frappe.boot?.sysdefaults?.number_format || '';
	return /[.,]\S*[.,]/.test(nf) ? nf : '#.###,##';
}
function cmi_note_fmt_pct(n) {
	n = flt(n);
	const parts = String(Math.abs(n)).split('.');
	return (n < 0 ? '-' : '') + parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.') + (parts[1] ? ',' + parts[1] : '');
}
// String angka bebas locale -> Number: kalau ada titik DAN koma, yang TERAKHIR = desimal;
// satu jenis saja + pola kelompok-3 = ribuan ("2.000.000"), selain itu desimal ("11,5").
function cmi_note_to_number(s) {
	s = s.replace(/[^\d.,-]/g, '');
	if (!s) return 0;
	const lastDot = s.lastIndexOf('.'), lastComma = s.lastIndexOf(',');
	let dec = null;
	if (lastDot !== -1 && lastComma !== -1) dec = lastDot > lastComma ? '.' : ',';
	else if (lastComma !== -1) dec = /^-?\d{1,3}(,\d{3})+$/.test(s) ? null : ',';
	else if (lastDot !== -1) dec = /^-?\d{1,3}(\.\d{3})+$/.test(s) ? null : '.';
	let intp = s, frac = '';
	if (dec) {
		const i = s.lastIndexOf(dec);
		intp = s.slice(0, i);
		frac = s.slice(i + 1);
	}
	return parseFloat(intp.replace(/[.,]/g, '') + (frac ? '.' + frac.replace(/[.,]/g, '') : '')) || 0;
}
function cmi_note_apply_input(frm, k) {
	const raw = (frm.doc[k + '_input'] || '').trim();
	if (!raw) {
		frm.doc[k + '_pct'] = 0;
		frm.doc[k + '_amount'] = 0;
	} else if (raw.includes('%')) {
		frm.doc[k + '_pct'] = cmi_note_to_number(raw);
	} else {
		frm.doc[k + '_pct'] = 0;
		frm.doc[k + '_amount'] = flt(cmi_note_to_number(raw), cmi_note_prec());
	}
	cmi_note_totals(frm);
	frm.dirty();
}

// Hitung live (mirror erp.fico.notes._calculate_totals) + rapikan tampilan smart input.
function cmi_note_totals(frm) {
	const d = frm.doc;
	const total = (d.items || []).reduce((s, r) => s + flt(r.amount), 0);
	const amt = {};
	['tax', 'pph'].forEach((k) => {
		amt[k] = flt(d[k + '_pct']) ? flt(total * flt(d[k + '_pct']) / 100, 2) : flt(d[k + '_amount']);
	});
	const vals = { total_amount: total, tax_amount: amt.tax, pph_amount: amt.pph, net_total: flt(total + amt.tax - amt.pph, 2) };
	Object.keys(vals).forEach((f) => {
		if (flt(d[f]) !== flt(vals[f])) { d[f] = vals[f]; frm.refresh_field(f); }
	});
	['tax', 'pph'].forEach((k) => {
		const pct = flt(d[k + '_pct']), a = flt(d[k + '_amount']);
		const text = pct > 0 ? cmi_note_fmt_pct(pct) + '%'
			: a ? format_number(a, cmi_note_num_format(), cmi_note_prec()) : '';
		// Selama masih diketik, penulisan teks ditunda sampai kursor keluar (smart_input_typing.js).
		if ((d[k + '_input'] || '') !== text) { d[k + '_input'] = text; frm.refresh_field(k + '_input'); }
		frm.set_df_property(k + '_input', 'description',
			pct > 0 || a ? __('= {0}', [format_currency(a, d.currency || 'IDR')]) : __('Ketik persen (11%) atau nominal (150.000).'));
	});
}

function cmi_note_buttons(frm, cfg) {
	if (frm.is_new()) return;
	const isMgr = (frappe.user_roles || []).some((r) => r === 'Accounts Manager' || r === 'System Manager');
	const reopen = (btn, field) => {
		if (isMgr) frm.add_custom_button(__(btn), () => frappe.confirm(__(btn + '?'), () => {
			frm.set_value(field, 0).then(() => frm.save());
		}));
	};
	if (frm.doc.void) {
		frm.set_read_only();
		frm.page.set_indicator(__('Void'), 'red');
		frm.dashboard.set_headline(__('VOID oleh {0}. Alasan: {1}', [frm.doc.void_by || '-', frm.doc.void_reason || '-']));
		reopen('Batalkan Void', 'void');
		return;
	}
	if (frm.doc.validated) {
		frm.set_read_only();
		frm.page.set_indicator(__('Validated'), 'green');
		reopen('Batalkan Validasi', 'validated');
		return;
	}
	frm.add_custom_button(__('Validate'), () => {
		frappe.confirm(__('Validasi {0} ini? Jurnal {1} dibuat dan dokumen terkunci.', [cfg.label, cfg.what]), () => {
			frm.set_value('validated', 1).then(() => frm.save());
		});
	}).addClass('btn-primary');
	frm.add_custom_button(__('Void'), () => {
		frappe.prompt(
			[{ fieldname: 'reason', fieldtype: 'Small Text', label: __('Alasan Void'), reqd: 1 }],
			(v) => { frm.set_value({ void_reason: v.reason, void: 1 }).then(() => frm.save()); },
			__('Void {0}', [cfg.label]), __('Void')
		);
	});
}

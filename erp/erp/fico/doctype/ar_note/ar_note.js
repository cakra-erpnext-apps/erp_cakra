// AR Note: grid diisi langsung (pola AP Note / Expense Note Tanpa Job), jumlah dihitung
// live; server (_calculate_totals) tetap sumber kebenarannya saat save.
frappe.ui.form.on('AR Note', {
	setup(frm) {
		const company = () => frm.doc.company || frappe.defaults.get_default('company');
		frm.set_query('cost_center', () => ({ filters: { company: company(), is_group: 0 } }));
		frm.set_query('account', 'items', () => ({ filters: { company: company(), is_group: 0 } }));
		const groups = frappe.boot.cmi_revenue_item_groups || [];
		if (groups.length) frm.set_query('item', 'items', () => ({ filters: { item_group: ['in', groups], disabled: 0 } }));
	},
	refresh(frm) {
		ar_note_buttons(frm);
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
	tax_pct: ar_note_totals,
	pph_pct: ar_note_totals,
	materai_amount: ar_note_totals,
});

frappe.ui.form.on('AR Note Item', {
	qty: ar_note_row,
	price: ar_note_row,
	items_remove: ar_note_totals,
});

function ar_note_row(frm, cdt, cdn) {
	const r = locals[cdt][cdn];
	r.amount = flt(r.qty) * flt(r.price);
	frm.refresh_field('items');
	ar_note_totals(frm);
}

function ar_note_totals(frm) {
	const d = frm.doc;
	const total = (d.items || []).reduce((s, r) => s + flt(r.amount), 0);
	const tax = flt(total * flt(d.tax_pct) / 100, 2);
	const pph = flt(total * flt(d.pph_pct) / 100, 2);
	frm.set_value({
		total_amount: total, tax_amount: tax, pph_amount: pph,
		net_total: flt(total + tax - pph + flt(d.materai_amount), 2),
	});
}

function ar_note_buttons(frm) {
	if (frm.is_new()) return;
	const isMgr = (frappe.user_roles || []).some((r) => r === 'Accounts Manager' || r === 'System Manager');
	const reopen = (label, field) => {
		if (isMgr) frm.add_custom_button(__(label), () => frappe.confirm(__(label + '?'), () => {
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
		frappe.confirm(__('Validasi AR Note ini? Jurnal piutang dibuat dan dokumen terkunci.'), () => {
			frm.set_value('validated', 1).then(() => frm.save());
		});
	}).addClass('btn-primary');
	frm.add_custom_button(__('Void'), () => {
		frappe.prompt(
			[{ fieldname: 'reason', fieldtype: 'Small Text', label: __('Alasan Void'), reqd: 1 }],
			(v) => { frm.set_value({ void_reason: v.reason, void: 1 }).then(() => frm.save()); },
			__('Void AR Note'), __('Void')
		);
	});
}

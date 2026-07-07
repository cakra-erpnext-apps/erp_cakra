frappe.ui.form.on('Expense Note Type', {
	refresh(frm) {
		if (frm.is_new()) return;
		if (!frappe.user.has_role('System Manager')) return;

		frm.add_custom_button(__('Set Counter'), () => show_counter_dialog(frm));
	},
});

function show_counter_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __('Expense Note Counter'),
		fields: [
			{
				fieldname: 'company',
				fieldtype: 'Link',
				options: 'Company',
				label: __('Company'),
				default: frappe.defaults.get_default('company'),
				reqd: 1,
				change: () => load_counter(frm, d),
			},
			{
				fieldname: 'date',
				fieldtype: 'Date',
				label: __('Year Date'),
				default: frappe.datetime.get_today(),
				reqd: 1,
				change: () => load_counter(frm, d),
			},
			{ fieldname: 'series_key', fieldtype: 'Data', label: __('Series Key'), read_only: 1 },
			{ fieldname: 'current', fieldtype: 'Int', label: __('Current / Last Used'), read_only: 1 },
			{ fieldname: 'next', fieldtype: 'Int', label: __('Next Counter'), read_only: 1 },
			{ fieldname: 'preview', fieldtype: 'Data', label: __('Next Number Preview'), read_only: 1 },
			{
				fieldname: 'new_current',
				fieldtype: 'Int',
				label: __('Set Current / Last Used'),
				description: __('If set to 25, the next Expense Note number will use 00026.'),
			},
		],
		primary_action_label: __('Set Counter'),
		primary_action(values) {
			frappe.call({
				method: 'erp.expedition.doctype.expense_note_type.expense_note_type.set_expense_note_counter',
				args: {
					expense_note_type: frm.doc.name,
					company: values.company,
					date: values.date,
					current: values.new_current,
				},
				freeze: true,
				freeze_message: __('Updating counter...'),
				callback(r) {
					if (!r.message) return;
					set_counter_values(d, r.message);
					frappe.show_alert({
						message: __('Counter updated. Next number: {0}', [r.message.preview]),
						indicator: 'green',
					});
				},
			});
		},
	});

	d.show();
	load_counter(frm, d);
}

function load_counter(frm, d) {
	const values = d.get_values();
	if (!values || !values.company || !values.date) return;

	frappe.call({
		method: 'erp.expedition.doctype.expense_note_type.expense_note_type.get_expense_note_counter',
		args: {
			expense_note_type: frm.doc.name,
			company: values.company,
			date: values.date,
		},
		callback(r) {
			if (!r.message) return;
			set_counter_values(d, r.message);
		},
	});
}

function set_counter_values(d, info) {
	d.set_value('series_key', info.series_key);
	d.set_value('current', info.current);
	d.set_value('next', info.next);
	d.set_value('preview', info.preview);
	d.set_value('new_current', info.current);
}

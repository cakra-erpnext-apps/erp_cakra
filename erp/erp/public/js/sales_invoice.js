frappe.ui.form.on('Sales Invoice', {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return; // only draft / new
		const grp = __('Get Items');
		frm.add_custom_button(__('Packing List'), () => pick_expedition(frm, 'Packing List'), grp);
		frm.add_custom_button(__('Shipping List'), () => pick_expedition(frm, 'Shipping List'), grp);
		frm.add_custom_button(__('Sales Order'), () => get_from_sales_order(frm), grp);
	},
});

// Pick a Packing List / Shipping List, pull its containers as one item row each.
function pick_expedition(frm, doctype) {
	const d = new frappe.ui.Dialog({
		title: __('Get Items dari {0}', [doctype]),
		fields: [
			{ fieldname: 'source', fieldtype: 'Link', label: doctype, options: doctype, reqd: 1 },
			{ fieldname: 'item_code', fieldtype: 'Link', label: __('Bill as Item (opsional)'), options: 'Item' },
			{
				fieldname: 'help',
				fieldtype: 'HTML',
				options: `<p class="text-muted small">${__('Tiap container jadi 1 baris item. Rate diisi manual. Kosongkan Item kalau mau isi item per baris sendiri.')}</p>`,
			},
		],
		primary_action_label: __('Get Items'),
		primary_action(values) {
			frappe.call({
				method: 'erp.expedition.get_items.get_container_invoice_items',
				args: { source_doctype: doctype, source_name: values.source, item_code: values.item_code },
				freeze: true,
				freeze_message: __('Menarik container…'),
				callback: (r) => {
					const rows = r.message || [];
					if (!rows.length) {
						frappe.msgprint(__('Tidak ada container di {0} ini.', [values.source]));
						return;
					}
					rows.forEach((row) => frm.add_child('items', row));
					frm.refresh_field('items');
					d.hide();
					frappe.show_alert(
						{ message: __('{0} container ditambahkan sebagai item.', [rows.length]), indicator: 'green' },
						5
					);
				},
			});
		},
	});
	d.show();
}

// Native ERPNext Sales Order -> Sales Invoice item mapping.
function get_from_sales_order(frm) {
	if (!erpnext || !erpnext.utils || !erpnext.utils.map_current_doc) {
		frappe.msgprint(__('Fitur Sales Order tidak tersedia.'));
		return;
	}
	erpnext.utils.map_current_doc({
		method: 'erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice',
		source_doctype: 'Sales Order',
		target: frm,
		setters: { customer: frm.doc.customer || undefined },
		get_query_filters: {
			docstatus: 1,
			status: ['not in', ['Closed', 'On Hold']],
			per_billed: ['<', 99.99],
			company: frm.doc.company,
		},
	});
}

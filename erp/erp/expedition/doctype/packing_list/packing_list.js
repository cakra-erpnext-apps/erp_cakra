// ---- Penomoran tertangguh (draft agent: nomor diberikan saat Save / Confirm) ----
// Draft yang dibuat agent bernama sementara "DRAFT-...". Nomor asli baru diminta
// ke server saat user menyimpan / klik Confirm, lalu form pindah ke nomor barunya.
frappe.provide('erp.draft');

erp.draft.is_draft = (frm) => !frm.is_new() && (frm.doc.name || '').startsWith('DRAFT-');

erp.draft.assign = (frm) => {
	frappe.call({
		method: 'erp.expedition.numbering.assign_number',
		args: { doctype: frm.doctype, docname: frm.doc.name },
		freeze: true,
		freeze_message: __('Memberi nomor…'),
		callback(r) {
			const m = r && r.message;
			if (m && m.changed) {
				frappe.show_alert({ message: __('Nomor diberikan: {0}', [m.name]), indicator: 'green' });
				frappe.set_route('Form', frm.doctype, m.name);
			}
		},
	});
};

erp.draft.setup = (frm) => {
	if (!erp.draft.is_draft(frm)) return;
	frm.dashboard.set_headline(__('📝 Draft belum bernomor — nomor diberikan saat Save / klik Confirm.'));
	frm.add_custom_button(__('Confirm & Beri Nomor'), () => {
		if (frm.is_dirty()) frm.save();
		else erp.draft.assign(frm);
	}).addClass('btn-primary');
};

frappe.ui.form.on('Packing List', {
	refresh: erp.draft.setup,
	after_save(frm) { if (erp.draft.is_draft(frm)) erp.draft.assign(frm); },
});

// ---- Tab Agent + Email (shared) — JS diambil dari backend lalu di-eval (lihat expense_note.js). ----
window.cmi_load_assistant = window.cmi_load_assistant || function (frm) {
	if (window.cmi_asst_render) { window.cmi_asst_render(frm); return; }
	frappe.call({ method: 'assistant.assistant.api.assistant_js' }).then((r) => {
		if (r && r.message && !window.cmi_asst_render) {
			try { eval(r.message); } catch (e) { console.error('assistant_tabs eval', e); }
		}
		if (window.cmi_asst_render) window.cmi_asst_render(frm);
	});
};
// Cost Center: hanya milik organisasi sistem (default company) & bukan group node.
window.cmi_cost_center_query = window.cmi_cost_center_query || function (frm, fieldname, table) {
	fieldname = fieldname || 'cost_center';
	const q = () => {
		const company = frappe.defaults.get_default('company');
		return { filters: company ? { company, is_group: 0 } : { is_group: 0 } };
	};
	if (table) frm.set_query(fieldname, table, q);
	else frm.set_query(fieldname, q);
};

// Create Invoice / Expense Note dari BL (shared dgn Shipping List). Guard: definisi
// pertama yang dipakai runtime — HARUS identik dengan yang di shipping_list.js.
window.cmi_create_from_bl = window.cmi_create_from_bl || function (frm, cfg) {
	frappe.call({
		method: 'erpnext_custom.connection.get_bls',
		args: { source_doctype: frm.doctype, source_name: frm.doc.name },
	}).then((r) => {
		const bls = (r.message || []).map((b) => b.bl_no).filter(Boolean);
		if (!bls.length) { frappe.msgprint(__('Belum ada BL di dokumen ini.')); return; }
		const d = new frappe.ui.Dialog({
			title: cfg.title,
			fields: [{
				fieldname: 'bl_no', fieldtype: 'Select', label: __('Pilih BL'),
				options: bls.join('\n'), reqd: 1, default: bls[0], description: cfg.desc,
			}],
			primary_action_label: cfg.label,
			primary_action(v) {
				if (!v.bl_no) { frappe.msgprint(__('Pilih BL dulu.')); return; }
				d.hide();
				frappe.call({
					method: cfg.method,
					args: { source_doctype: frm.doctype, source_name: frm.doc.name, bl_no: v.bl_no },
					freeze: true, freeze_message: cfg.freeze,
					callback(res) {
						if (res && res.message) {
							frappe.model.sync(res.message);
							frappe.set_route('Form', cfg.target, res.message.name);
						}
					},
				});
			},
		});
		d.show();
	});
};
window.CMI_MAKE_INVOICE = window.CMI_MAKE_INVOICE || {
	method: 'erpnext_custom.connection.make_invoice_from_bl', target: 'Sales Invoice',
	title: __('Create Invoice dari BL'), label: __('Create Invoice'), freeze: __('Menyiapkan Sales Invoice...'),
	desc: __('Customer, alamat & containers BL ini dibawa ke Sales Invoice baru (tanggal hari ini).'),
};
window.CMI_MAKE_EXPENSE = window.CMI_MAKE_EXPENSE || {
	method: 'erpnext_custom.connection.make_expense_from_bl', target: 'Expense Note',
	title: __('Create Expense Note dari BL'), label: __('Create Expense Note'), freeze: __('Menyiapkan Expense Note...'),
	desc: __('Supplier dikosongkan; BL & containers dibawa (tanggal hari ini).'),
};

frappe.ui.form.on('Packing List', {
	refresh(frm) {
		window.cmi_load_assistant(frm);
		window.cmi_cost_center_query(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Invoice'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_INVOICE)).addClass('btn-primary');
			frm.add_custom_button(__('Create Expense Note'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_EXPENSE));
		}
	},
});

frappe.ui.form.on('Shipping List', {
	refresh(frm) {
		frm.add_custom_button(__('➕ Tambah BL + Containers'), () => open_bl_dialog(frm));
		// Entry is via the modal only — disable inline add on both grids.
		['bls', 'containers'].forEach((f) => {
			const g = frm.fields_dict[f] && frm.fields_dict[f].grid;
			if (g) {
				g.cannot_add_rows = true;
				g.refresh();
			}
		});
	},
});

// Edit buttons on each row open the same modal, pre-filled for that BL.
frappe.ui.form.on('Shipping List BL', {
	edit_row(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		open_bl_dialog(frm, row.bl_no);
	},
});

frappe.ui.form.on('Shipping List Container', {
	edit_row(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.bl) {
			open_bl_dialog(frm, row.bl);
		} else {
			frappe.msgprint(__('Container ini belum punya BL.'));
		}
	},
});

const BL_KEYS = ['bl_no', 'bl_date', 'shipper', 'consignee', 'cargo', 'goods_description', 'weight', 'freight_terms', 'remarks'];
const C_KEYS = ['bl', 'container_no', 'seal_no', 'container_size', 'cargo', 'goods_description', 'customer', 'vehicle', 'driver', 'remarks'];

function plain(row, keys) {
	const o = {};
	keys.forEach((k) => {
		o[k] = row[k];
	});
	return o;
}

// Rebuild both tables from scratch, dropping the edited BL group — avoids stale
// grid state from in-place array mutation.
function rebuild_excluding(frm, bl_no) {
	const keepBls = (frm.doc.bls || []).filter((b) => b.bl_no !== bl_no).map((b) => plain(b, BL_KEYS));
	const keepC = (frm.doc.containers || []).filter((c) => c.bl !== bl_no).map((c) => plain(c, C_KEYS));
	frm.clear_table('bls');
	frm.clear_table('containers');
	keepBls.forEach((b) => frm.add_child('bls', b));
	keepC.forEach((c) => frm.add_child('containers', c));
}

// Remove any modal backdrop that got left behind after a dialog closed.
function clear_stray_backdrop() {
	if (!$('.modal.show, .modal.in, .modal:visible').length) {
		$('.modal-backdrop').remove();
		$('body').removeClass('modal-open').css({ overflow: '', 'padding-right': '' });
	}
}

// Apply one BL + its containers to the form (runs AFTER the dialog has closed).
function apply_bl(frm, originalBlNo, blData, containers) {
	if (originalBlNo) {
		rebuild_excluding(frm, originalBlNo);
	}
	frm.add_child('bls', blData);
	let n = 0;
	containers.forEach((c) => {
		frm.add_child('containers', {
			bl: blData.bl_no,
			container_no: c.container_no,
			seal_no: c.seal_no,
			container_size: c.container_size,
			customer: c.customer,
			cargo: blData.cargo,
			goods_description: blData.goods_description,
		});
		n++;
	});
	frm.refresh_field('bls');
	frm.refresh_field('containers');
	clear_stray_backdrop();
	frappe.show_alert(
		{
			message: originalBlNo
				? __('BL {0} diperbarui ({1} container). Jangan lupa Save.', [blData.bl_no, n])
				: __('BL {0} + {1} container ditambahkan. Jangan lupa Save.', [blData.bl_no, n]),
			indicator: 'green',
		},
		5
	);
}

// Add (no arg) or Edit (originalBlNo) one BL together with its containers.
function open_bl_dialog(frm, originalBlNo) {
	let bl = {};
	let containerData = [];
	if (originalBlNo) {
		bl = (frm.doc.bls || []).find((b) => b.bl_no === originalBlNo) || {};
		containerData = (frm.doc.containers || [])
			.filter((c) => c.bl === originalBlNo)
			.map((c) => ({
				container_no: c.container_no,
				seal_no: c.seal_no,
				container_size: c.container_size,
				customer: c.customer,
			}));
	}

	const d = new frappe.ui.Dialog({
		title: originalBlNo ? __('Edit BL {0}', [originalBlNo]) : __('Tambah BL beserta Containers'),
		size: 'extra-large',
		fields: [
			{ fieldname: 'bl_no', fieldtype: 'Data', label: __('BL No'), reqd: 1, default: bl.bl_no },
			{ fieldname: 'bl_date', fieldtype: 'Date', label: __('BL Date'), default: bl.bl_date },
			{ fieldname: 'cb1', fieldtype: 'Column Break' },
			{ fieldname: 'consignee', fieldtype: 'Link', label: __('Consignee'), options: 'CRM Organization', default: bl.consignee },
			{ fieldname: 'cargo', fieldtype: 'Link', label: __('Cargo'), options: 'Cargo', default: bl.cargo },
			{ fieldname: 'cb2', fieldtype: 'Column Break' },
			{ fieldname: 'goods_description', fieldtype: 'Small Text', label: __('Goods Description'), default: bl.goods_description },
			{ fieldname: 'sb', fieldtype: 'Section Break', label: __('Containers untuk BL ini') },
			{
				fieldname: 'containers',
				fieldtype: 'Table',
				label: __('Containers'),
				cannot_add_rows: false,
				in_place_edit: true,
				data: containerData,
				fields: [
					{ fieldname: 'container_no', fieldtype: 'Data', label: __('Container No'), in_list_view: 1, reqd: 1, columns: 3 },
					{ fieldname: 'seal_no', fieldtype: 'Data', label: __('Seal No'), in_list_view: 1, columns: 2 },
					{ fieldname: 'container_size', fieldtype: 'Link', label: __('Size'), options: 'Container Size', in_list_view: 1, columns: 2 },
					{ fieldname: 'customer', fieldtype: 'Link', label: __('Customer'), options: 'CRM Organization', in_list_view: 1, columns: 3 },
				],
			},
		],
		primary_action_label: originalBlNo ? __('Simpan') : __('Tambahkan'),
		primary_action(values) {
			const bl_no = (values.bl_no || '').trim();
			if (!bl_no) {
				frappe.msgprint(__('BL No wajib diisi.'));
				return;
			}
			const blData = {
				bl_no: bl_no,
				bl_date: values.bl_date,
				consignee: values.consignee,
				cargo: values.cargo,
				goods_description: values.goods_description,
			};
			const containers = (values.containers || []).filter((c) => c.container_no);

			// Close the dialog FIRST, then mutate the form once the modal (and its
			// backdrop) has fully gone — doing heavy grid work mid-hide leaves a
			// stuck dark overlay.
			d.hide();
			setTimeout(() => apply_bl(frm, originalBlNo, blData, containers), 200);
		},
	});
	d.show();
}

// ---- Penomoran tertangguh (draft agent: nomor diberikan saat Save / Confirm) ----
// Draft yang dibuat agent bernama sementara "DRAFT-...". Nomor asli baru diminta
// ke server saat user menyimpan / klik Confirm, lalu form pindah ke nomor barunya.
frappe.provide('erp_cmi.draft');

erp_cmi.draft.is_draft = (frm) => !frm.is_new() && (frm.doc.name || '').startsWith('DRAFT-');

erp_cmi.draft.assign = (frm) => {
	frappe.call({
		method: 'erp_cmi.expedition.numbering.assign_number',
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

erp_cmi.draft.setup = (frm) => {
	if (!erp_cmi.draft.is_draft(frm)) return;
	frm.dashboard.set_headline(__('📝 Draft belum bernomor — nomor diberikan saat Save / klik Confirm.'));
	frm.add_custom_button(__('Confirm & Beri Nomor'), () => {
		if (frm.is_dirty()) frm.save();
		else erp_cmi.draft.assign(frm);
	}).addClass('btn-primary');
};

frappe.ui.form.on('Shipping List', {
	refresh: erp_cmi.draft.setup,
	after_save(frm) { if (erp_cmi.draft.is_draft(frm)) erp_cmi.draft.assign(frm); },
});

// ---- Tab Agent + Email (shared) — JS diambil dari backend lalu di-eval (lihat expense_note.js). ----
window.cmi_load_assistant = window.cmi_load_assistant || function (frm) {
	if (window.cmi_asst_render) { window.cmi_asst_render(frm); return; }
	frappe.call({ method: 'agents.agent.api.assistant_js' }).then((r) => {
		if (r && r.message && !window.cmi_asst_render) {
			try { eval(r.message); } catch (e) { console.error('assistant_tabs eval', e); }
		}
		if (window.cmi_asst_render) window.cmi_asst_render(frm);
	});
};
frappe.ui.form.on('Shipping List', {
	refresh(frm) { window.cmi_load_assistant(frm); },
});

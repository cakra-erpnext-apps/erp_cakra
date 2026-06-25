frappe.ui.form.on('Shipping List', {
	refresh(frm) {
		frm.add_custom_button(__('➕ Tambah BL + Containers'), () => open_bl_dialog(frm));
		// "Show" must be visible on every row without clicking the row first.
		bind_show_buttons(frm);
		// Cost Center: hanya milik organisasi sistem (default company) & bukan group node.
		window.cmi_cost_center_query(frm);
		load_bl_invoices(frm);
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

// A Button fieldtype only renders its control when the row enters edit mode
// (i.e. after the row is clicked). To make "Show" visible on every row up front,
// inject our own button into the static cell on each row render instead.
function bind_show_buttons(frm) {
	$(frm.wrapper)
		.off('grid-row-render.slshow')
		.on('grid-row-render.slshow', (e, grid_row) => {
			const doc = grid_row && grid_row.doc;
			if (!doc) return;
			// "Show" hanya di tabel Bills of Lading (BL), tidak di Containers.
			if (doc.doctype !== 'Shipping List BL') return;
			const col = grid_row.columns && grid_row.columns.edit_row;
			if (!col || !col.static_area) return;
			const bl_no = doc.bl_no || doc.bl;
			col.static_area.empty();
			$(`<button type="button" class="btn btn-xs btn-default">${__('Show')}</button>`)
				.appendTo(col.static_area)
				.on('click', (ev) => {
					ev.stopPropagation();
					ev.preventDefault();
					if (bl_no) {
						open_bl_dialog(frm, bl_no);
					} else {
						frappe.msgprint(__('Row ini belum punya BL.'));
					}
				});
		});
}

// Cost Center field filter: tampilkan HANYA cost center milik organisasi sistem
// (default company) dan bukan group node. "1 system = 1 organisasi" — dinamis ikut
// default company, jadi otomatis benar walau nanti ada company kedua. Dipakai bersama
// oleh form expedition lain (Packing List / Expense Note) via window guard.
window.cmi_cost_center_query = window.cmi_cost_center_query || function (frm, fieldname, table) {
	fieldname = fieldname || 'cost_center';
	const q = () => {
		const company = frappe.defaults.get_default('company');
		return { filters: company ? { company, is_group: 0 } : { is_group: 0 } };
	};
	if (table) frm.set_query(fieldname, table, q);
	else frm.set_query(fieldname, q);
};

// Edit buttons on each row open the same modal, pre-filled for that BL.
frappe.ui.form.on('Shipping List BL', {
	edit_row(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		open_bl_dialog(frm, row.bl_no);
	},
});

// Containers: tidak ada tombol "Show" / edit langsung — semua diedit lewat tombol
// "Show" di tabel Bills of Lading saja.

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
			customer: c.customer || blData.consignee,
			cargo: c.cargo,
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
				cargo: c.cargo,
				customer: c.customer,
			}));
	}

	const d = new frappe.ui.Dialog({
		title: originalBlNo ? __('Edit BL {0}', [originalBlNo]) : __('Tambah BL beserta Containers'),
		size: 'extra-large',
		fields: [
			{ fieldname: 'bl_no', fieldtype: 'Data', label: __('BL No'), reqd: 1, default: bl.bl_no },
			{ fieldname: 'bl_date', fieldtype: 'Date', label: __('BL Date'), reqd: 1, default: bl.bl_date },
			{ fieldname: 'cb1', fieldtype: 'Column Break' },
			{
				fieldname: 'consignee', fieldtype: 'Link', label: __('Consignee/Shipper'), reqd: 1, options: 'Customer', default: bl.consignee,
				onchange() {
					// Consignee = customer untuk seluruh BL → segarkan kolom Customer di tiap container.
					const cons = d.get_value('consignee');
					const grid = d.fields_dict.containers && d.fields_dict.containers.grid;
					if (cons && grid) {
						(grid.data || []).forEach((row) => { row.customer = cons; });
						grid.refresh();
					}
				},
			},
			{ fieldname: 'cb2', fieldtype: 'Column Break' },
			{ fieldname: 'goods_description', fieldtype: 'Small Text', label: __('Goods Description'), default: bl.goods_description },
			{ fieldname: 'sb', fieldtype: 'Section Break'},
			{
				fieldname: 'containers',
				fieldtype: 'Table',
				label: __('Containers'),
				cannot_add_rows: false,
				in_place_edit: true,
				data: containerData,
				fields: [
					{ fieldname: 'container_no', fieldtype: 'Data', label: __('Container No'), in_list_view: 1, reqd: 1, columns: 2 },
					{ fieldname: 'seal_no', fieldtype: 'Data', label: __('Seal No'), in_list_view: 1, columns: 2 },
					{ fieldname: 'container_size', fieldtype: 'Link', label: __('Size'), options: 'Container Size', in_list_view: 1, columns: 2 },
					{ fieldname: 'cargo', fieldtype: 'Link', label: __('Cargo'), options: 'Cargo', in_list_view: 1, columns: 2 },
					{ fieldname: 'customer', fieldtype: 'Link', label: __('Customer'), options: 'Customer', in_list_view: 1, columns: 2 },
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

frappe.ui.form.on('Shipping List', {
	refresh: erp.draft.setup,
	after_save(frm) { if (erp.draft.is_draft(frm)) erp.draft.assign(frm); },
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

// ---- Tab Summary — view-only: Expense Note, Invoice (Revenue), dan Margin. ----
// Data diambil dari server (Expense Note + Sales Invoice yang terhubung), bukan dari
// frm.doc, jadi async. Tidak ada elemen yang bisa diedit di sini.
function render_summary(frm) {
	const f = frm.fields_dict.summary_html;
	if (!f || !f.$wrapper) return;
	if (frm.is_new() || !frm.doc.name) {
		f.$wrapper.html(`<div class="text-muted" style="padding:12px">${__('Simpan dokumen dulu untuk melihat summary.')}</div>`);
		return;
	}
	f.$wrapper.html(`<div class="text-muted" style="padding:12px">${__('Memuat summary…')}</div>`);
	frappe.call({
		method: 'erp.expedition.doctype.shipping_list.shipping_list.summary_data',
		args: { shipping_list: frm.doc.name },
	}).then((r) => paint_summary(f.$wrapper, (r && r.message) || {}))
		.catch(() => f.$wrapper.html(`<div class="text-danger" style="padding:12px">${__('Gagal memuat summary.')}</div>`));
}

// Style tabel Summary: angka (kolom kanan) tidak turun baris; kolom teks (Expense
// Class / No / Item / Invoice) dibatasi lebar + ellipsis kalau kepanjangan.
function cmi_summary_inject_style() {
	if (document.getElementById('cmi-summary-style')) return;
	const s = document.createElement('style');
	s.id = 'cmi-summary-style';
	s.textContent = `
	.cmi-summary .frappe-card { overflow-x: auto; }
	.cmi-summary td, .cmi-summary th { padding: 5px 8px; vertical-align: top; }
	.cmi-summary td.text-right, .cmi-summary th.text-right { white-space: nowrap; }
	.cmi-summary .cmi-ell { display: inline-block; max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
	`;
	document.head.appendChild(s);
}

function paint_summary($w, data) {
	const esc = frappe.utils.escape_html;
	const cur = data.currency || 'IDR';
	const money = (v) => format_currency(v || 0, cur);
	const exp = data.expenses || [];
	const rev = data.revenues || [];
	const t = data.totals || {};
	cmi_summary_inject_style();
	$w.addClass('cmi-summary');

	// Tiap dokumen = baris header (tebal) + baris detail (indent).
	const docBlock = (head, detailLines) => `
		<tr class="summary-head" style="font-weight:600;background:var(--bg-light-gray,#f4f5f6)">
		  <td>${head.title}</td>
		  <td class="text-right">${money(head.amount)}</td>
		  <td class="text-right">${money(head.tax)}</td>
		  <td class="text-right">${money(head.net)}</td>
		</tr>
		${detailLines.join('')}`;

	const titleOf = (parts) => parts.filter(Boolean).join(', ');

	// EXPENSE — 1 baris per Expense Class (digabung di server) + baris Total (Amount/Tax/Net).
	const expBody = !exp.length
		? `<tr><td colspan="5" class="text-muted text-center">${__('Belum ada Expense')}</td></tr>`
		: exp.map((e) => `<tr>
			<td><span class="cmi-ell" title="${esc(e.expense_class || '-')}">${esc(e.expense_class || '-')}</span></td>
			<td><span class="cmi-ell" title="${esc(e.expense_no || '-')}">${esc(e.expense_no || '-')}</span></td>
			<td class="text-right">${money(e.amount)}</td>
			<td class="text-right">${money(e.tax)}</td>
			<td class="text-right">${money(e.net)}</td>
		  </tr>`).join('')
		  + `<tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)">
			<td>${__('Total')}</td><td></td>
			<td class="text-right">${money(t.expense)}</td>
			<td class="text-right">${money(t.expense_tax)}</td>
			<td class="text-right">${money(t.expense_net)}</td>
		  </tr>`;

	// REVENUE — 1 baris per item invoice + baris Total (Amount/Tax/Line Total).
	const revBody = !rev.length
		? `<tr><td colspan="5" class="text-muted text-center">${__('Belum ada Invoice')}</td></tr>`
		: rev.map((r) => `<tr>
			<td><span class="cmi-ell" title="${esc(r.item || '-')}">${esc(r.item || '-')}</span></td>
			<td><span class="cmi-ell" title="${esc(r.invoice || '-')}">${esc(r.invoice || '-')}</span></td>
			<td class="text-right">${money(r.amount)}</td>
			<td class="text-right">${money(r.tax)}</td>
			<td class="text-right">${money(r.net)}</td>
		  </tr>`).join('')
		  + `<tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)">
			<td>${__('Total')}</td><td></td>
			<td class="text-right">${money(t.revenue)}</td>
			<td class="text-right">${money(t.revenue_tax)}</td>
			<td class="text-right">${money(t.revenue_net)}</td>
		  </tr>`;

	const mColor = (t.margin || 0) >= 0 ? 'green' : 'red';

	// Reimbursement (pass-through — tidak masuk margin): EN reimburse (Paid) + Invoice Reimburse (Billed).
	const reimb = data.reimbursements || {};
	const rexp = reimb.expenses || [];
	const rinv = reimb.invoices || [];
	const reimbBody = `
		<div style="border-top:2px dashed var(--gray-500,#8d96a5);margin:40px 0 28px;"></div>
		<div class="frappe-card" style="padding:12px;margin-top:0">
		  <h5 style="margin-top:0">${__('Reimbursement')} <span class="text-muted" style="font-size:.8em">(${__('tidak masuk margin')})</span></h5>
		  <table class="table table-sm" style="margin:0 0 10px">
		    <thead><tr><th>${__('Expense Note (Reimburse)')}</th><th class="text-right" style="width:28%">${__('Paid')}</th></tr></thead>
		    <tbody>
		      ${rexp.length ? rexp.map((e) => `<tr><td><span class="cmi-ell" title="${esc(titleOf([e.name, e.vendor, e.customer]))}">${esc(titleOf([e.name, e.vendor, e.customer]))}</span></td><td class="text-right">${money(e.amount)}</td></tr>`).join('') : `<tr><td colspan="2" class="text-muted text-center">${__('Belum ada EN reimburse')}</td></tr>`}
		      <tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)"><td>${__('Total Paid')}</td><td class="text-right">${money(reimb.paid)}</td></tr>
		    </tbody>
		  </table>
		  <table class="table table-sm" style="margin:0">
		    <thead><tr><th>${__('Invoice (Reimburse)')}</th><th class="text-right" style="width:28%">${__('Billed')}</th></tr></thead>
		    <tbody>
		      ${rinv.length ? rinv.map((iv) => `<tr><td><span class="cmi-ell" title="${esc(titleOf([iv.name, iv.customer, iv.date ? frappe.datetime.str_to_user(iv.date) : '']))}">${esc(titleOf([iv.name, iv.customer, iv.date ? frappe.datetime.str_to_user(iv.date) : '']))}${iv.draft ? ` <span class="text-muted">(${__('draft')})</span>` : ''}</span></td><td class="text-right">${money(iv.amount)}</td></tr>`).join('') : `<tr><td colspan="2" class="text-muted text-center">${__('Belum ada invoice reimburse')}</td></tr>`}
		      <tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)"><td>${__('Total Billed')}</td><td class="text-right">${money(reimb.billed)}</td></tr>
		      <tr style="font-size:1.1em;border-top:1px solid var(--border-color,#d1d8dd)"><td>${__('Net Reimburse')} <span class="text-muted" style="font-size:.85em">(billed − paid)</span></td><td class="text-right"><b>${money(reimb.net)}</b></td></tr>
		    </tbody>
		  </table>
		</div>`;

	$w.html(`
		<div class="frappe-card" style="padding:12px;margin-bottom:12px">
		  <h5 style="margin-top:0">${__('Expense')}</h5>
		  <table class="table table-sm" style="margin:0">
		    <thead><tr>
		      <th>${__('Expense Class')}</th>
		      <th>${__('Expense No')}</th>
		      <th class="text-right" style="width:14%">${__('Amount')}</th>
		      <th class="text-right" style="width:14%">${__('Tax')}</th>
		      <th class="text-right" style="width:14%">${__('Net Total')}</th>
		    </tr></thead>
		    <tbody>${expBody}</tbody>
		  </table>
		</div>

		<div class="frappe-card" style="padding:12px;margin-bottom:12px">
		  <h5 style="margin-top:0">${__('Revenue')}</h5>
		  <table class="table table-sm" style="margin:0">
		    <thead><tr>
		      <th>${__('Item Name')}</th>
		      <th>${__('Invoice')}</th>
		      <th class="text-right" style="width:14%">${__('Amount')}</th>
		      <th class="text-right" style="width:14%">${__('Tax')}</th>
		      <th class="text-right" style="width:14%">${__('Line Total')}</th>
		    </tr></thead>
		    <tbody>${revBody}</tbody>
		  </table>
		</div>

		<div class="frappe-card" style="padding:12px">
		  <table class="table table-sm table-borderless" style="margin:0">
		    <tr><th style="width:60%">${__('Total Revenue')} <span class="text-muted">(DPP)</span></th><td class="text-right">${money(t.revenue)}</td></tr>
		    <tr><th>${__('Total Expense')} <span class="text-muted">(DPP)</span></th><td class="text-right">${money(t.expense)}</td></tr>
		    <tr style="font-size:1.15em;border-top:2px solid var(--border-color,#d1d8dd)">
		      <th>${__('Margin')}</th>
		      <td class="text-right"><b class="text-${mColor}">${money(t.margin)}</b>${t.margin_pct != null ? ` <span class="text-muted" style="font-size:.85em">(${t.margin_pct}%)</span>` : ''}</td>
		    </tr>
		  </table>
		</div>
	`);
	if (reimbBody) $w.append(reimbBody);
}

frappe.ui.form.on('Shipping List', {
	refresh(frm) { render_summary(frm); },
});

// Kolom "Invoice" di tabel BL: nomor Sales Invoice yang menarik tiap BL (1 BL bisa banyak invoice).
function load_bl_invoices(frm) {
	if (frm.is_new() || !(frm.doc.bls || []).length) return;
	frappe.call({ method: 'erpnext_custom.connection.bl_invoices', args: { shipping_list: frm.doc.name } }).then((r) => {
		const map = (r && r.message) || {};
		(frm.doc.bls || []).forEach((row) => { row.invoice = (map[row.bl_no] || []).join(', '); });
		frm.refresh_field('bls');
	});
}

// Ringkasan jumlah BL per customer/consignee (field HTML "customer_summary").
// Dihitung live dari tabel BL: tiap BL = 1, dikelompokkan per consignee. Contoh
// (Total BL 6): 4 BL customer A, 2 BL customer B →
//   Total BL: 6
//   4  PT. A
//   2  PT. B
function render_customer_summary(frm) {
	const fd = frm.fields_dict.customer_summary;
	if (!fd || !fd.$wrapper) return;
	const esc = frappe.utils.escape_html;
	// Jumlah BL per consignee/customer (berdasarkan Total BL, bukan per container).
	const counts = {};
	(frm.doc.bls || []).forEach((b) => {
		const k = (b.consignee || '').trim();
		if (k) counts[k] = (counts[k] || 0) + 1;
	});
	const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
	if (!entries.length) {
		fd.$wrapper.html('<div class="text-muted" style="font-size:12px">Belum ada BL/consignee.</div>');
		return;
	}
	const total = entries.reduce((s, [, n]) => s + n, 0);
	let html = `<div style="font-size:12px;line-height:1.7">`
		+ `<div style="font-weight:600;margin-bottom:2px">Total BL: ${total}</div>`;
	entries.forEach(([name, n]) => {
		html += `<div><span style="display:inline-block;min-width:26px;font-weight:600">${n}</span> ${esc(name)}</div>`;
	});
	html += '</div>';
	fd.$wrapper.html(html);
}

// ---- Create Invoice / Expense Note dari BL (shared Shipping List & Packing List) ----
// Klik tombol -> pilih BL -> redirect ke dokumen baru dengan data BL terbawa.
// cfg: { method, target, title, label, freeze, desc }. Server: erpnext_custom.connection.*
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

frappe.ui.form.on('Shipping List', {
	refresh(frm) {
		render_customer_summary(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Invoice'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_INVOICE)).addClass('btn-primary');
			frm.add_custom_button(__('Create Expense Note'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_EXPENSE));
		}
		frm.add_custom_button(__('➕ Tambah BL + Containers'), () => open_bl_dialog(frm));
		// Cost Center: hanya milik organisasi sistem (default company) & bukan group node.
		window.cmi_cost_center_query(frm);
		load_bl_financials(frm);
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

// Dialog kecil untuk melihat attachment sebuah BL (klik nama file = buka di tab baru).
function show_bl_attachments(frm, bl_no) {
	const bl = (frm.doc.bls || []).find((b) => b.bl_no === bl_no);
	let files = [];
	try {
		files = JSON.parse((bl && bl.attachments) || '[]') || [];
	} catch (err) {
		files = [];
	}
	if (!files.length) {
		frappe.msgprint(__('Belum ada attachment untuk BL {0}.', [bl_no || '-']));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: __('Attachments BL {0}', [bl_no]),
		fields: [{ fieldname: 'files_html', fieldtype: 'HTML' }],
	});
	const w = d.fields_dict.files_html.$wrapper;
	files.forEach((f) => {
		const row = $('<div style="margin-bottom:6px"></div>').appendTo(w);
		$('<a target="_blank" rel="noopener noreferrer"></a>')
			.attr('href', f.file_url)
			.text(f.file_name || f.file_url)
			.appendTo(row);
	});
	d.show();
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

// Containers: baris bisa diedit langsung di tab Containers (pencil / inline),
// kecuali kolom BL (kunci grup — dikelola lewat modal "Show" di tabel BL).
// Tambah/hapus container tetap lewat modal BL.

const BL_KEYS = ['bl_no', 'bl_date', 'shipper', 'consignee', 'cargo', 'goods_description', 'weight', 'freight_terms', 'remarks', 'attachments'];
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
	// Field per-container yang TIDAK dikelola modal (vehicle/driver/remarks) diedit
	// langsung di tab Containers — simpan dulu supaya tidak hilang saat baris
	// container BL ini dibangun ulang dari data modal.
	const preserved = {};
	if (originalBlNo) {
		(frm.doc.containers || [])
			.filter((c) => c.bl === originalBlNo)
			.forEach((c) => {
				if (c.container_no) {
					preserved[c.container_no] = { vehicle: c.vehicle, driver: c.driver, remarks: c.remarks };
				}
			});
		rebuild_excluding(frm, originalBlNo);
	}
	frm.add_child('bls', blData);
	let n = 0;
	containers.forEach((c) => {
		const keep = preserved[c.container_no] || {};
		frm.add_child('containers', {
			bl: blData.bl_no,
			container_no: c.container_no,
			seal_no: c.seal_no,
			container_size: c.container_size,
			customer: c.customer || blData.consignee,
			cargo: c.cargo,
			goods_description: blData.goods_description,
			vehicle: keep.vehicle,
			driver: keep.driver,
			remarks: keep.remarks,
		});
		n++;
	});
	frm.refresh_field('bls');
	frm.refresh_field('containers');
	// Baris BL dibangun ulang — isi lagi kolom Invoice / Expense / Margin
	// (display-only, datanya dari server) supaya tidak tampak kosong.
	load_bl_financials(frm);
	// BL berubah → segarkan ringkasan jumlah BL per customer/consignee.
	render_customer_summary(frm);
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
	let attachments = [];
	if (originalBlNo) {
		bl = (frm.doc.bls || []).find((b) => b.bl_no === originalBlNo) || {};
		try {
			attachments = JSON.parse(bl.attachments || '[]') || [];
		} catch (e) {
			attachments = [];
		}
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
			{ fieldname: 'sb_att', fieldtype: 'Section Break', label: __('Attachments') },
			{ fieldname: 'att_html', fieldtype: 'HTML' },
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
				attachments: JSON.stringify(attachments),
			};
			const containers = (values.containers || []).filter((c) => c.container_no);

			// Close the dialog FIRST, then mutate the form once the modal (and its
			// backdrop) has fully gone — doing heavy grid work mid-hide leaves a
			// stuck dark overlay.
			d.hide();
			setTimeout(() => apply_bl(frm, originalBlNo, blData, containers), 200);
		},
	});

	// ---- Attachments per BL ----
	// File di-upload sebagai attachment Shipping List (muncul juga di sidebar);
	// daftar per-BL disimpan sebagai JSON di field tersembunyi baris BL.
	// Catatan: file yang di-upload lalu dialognya di-Cancel tetap ter-attach di
	// Shipping List (tinggal hapus dari sidebar bila tidak dipakai).
	function render_attachments() {
		const f = d.fields_dict.att_html;
		if (!f || !f.$wrapper) return;
		const w = f.$wrapper.empty();
		if (!attachments.length) {
			$(`<div class="text-muted" style="margin-bottom:6px">${__('Belum ada attachment.')}</div>`).appendTo(w);
		}
		attachments.forEach((file, i) => {
			const row = $('<div style="margin-bottom:4px"></div>').appendTo(w);
			$('<a target="_blank" rel="noopener noreferrer"></a>')
				.attr('href', file.file_url)
				.text(file.file_name || file.file_url)
				.appendTo(row);
			$(`<button type="button" class="btn btn-xs btn-default" style="margin-left:8px">${__('Hapus')}</button>`)
				.appendTo(row)
				.on('click', () => {
					attachments.splice(i, 1);
					if (file.name) {
						// Hapus juga dokumen File-nya (best-effort).
						frappe.call({ method: 'frappe.client.delete', args: { doctype: 'File', name: file.name } }).catch(() => {});
					}
					render_attachments();
				});
		});
		$(`<button type="button" class="btn btn-xs btn-default" style="margin-top:4px">${__('Add Attachment')}</button>`)
			.appendTo(w)
			.on('click', () => {
				if (frm.is_new()) {
					frappe.msgprint(__('Simpan Shipping List dulu sebelum menambah attachment.'));
					return;
				}
				new frappe.ui.FileUploader({
					doctype: frm.doctype,
					docname: frm.doc.name,
					folder: 'Home/Attachments',
					on_success(file) {
						attachments.push({ name: file.name, file_url: file.file_url, file_name: file.file_name });
						render_attachments();
					},
				});
			});
	}

	d.show();
	render_attachments();
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
	frappe.call({ method: 'assistant.assistant.api.assistant_js' }).then((r) => {
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
	// Akses tab Summary dibatasi role (data expense & margin sensitif).
	const allowed = (frappe.user_roles || []).some((r) =>
		['Shipping List Summary', 'System Manager'].includes(r));
	if (!allowed) {
		frm.set_df_property('tab_summary', 'hidden', 1);
		return;
	}
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
	}).then((r) => {
		const data = (r && r.message) || {};
		if (data.forbidden) {
			frm.set_df_property('tab_summary', 'hidden', 1);
			return;
		}
		paint_summary(f.$wrapper, data);
	}).catch(() => f.$wrapper.html(`<div class="text-danger" style="padding:12px">${__('Gagal memuat summary.')}</div>`));
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

	const titleOf = (parts) => parts.filter(Boolean).join(', ');
	const fdate = (d) => (d ? frappe.datetime.str_to_user(d) : '');

	// Link dokumen: buka di tab baru.
	const docLink = (route, name) =>
		`<a href="/app/${route}/${encodeURIComponent(name)}" target="_blank" rel="noopener" title="${esc(name)}">${esc(name)}</a>`;

	// Badge status (dipakai Expense Note & Invoice, warna selaras list view).
	const statusPill = (s) => {
		const color = {
			Draft: 'gray',
			Validated: 'green',
			Unpaid: 'orange',
			Overdue: 'red',
			'Partly Paid': 'yellow',
			Paid: 'green',
			Submitted: 'blue',
			Return: 'gray',
			'Credit Note Issued': 'gray',
		}[s] || 'gray';
		return `<span class="indicator-pill ${color}" style="margin-left:8px;font-weight:400">${esc(s)}</span>`;
	};

	// Baris info di bawah nomor dokumen: pihak, tanggal, pembuat.
	const metaLine = (parts) =>
		`<div class="text-muted" style="font-weight:400;font-size:.85em">${esc(titleOf(parts))}</div>`;

	// EXPENSE — dikelompokkan per Expense Note: header (nomor EN + status + info) lalu
	// baris Expense Class di bawahnya, diakhiri baris Total (Amount/Tax/Net).
	const expGroup = (e) => `
		<tr class="summary-head" style="font-weight:600;background:var(--bg-light-gray,#f4f5f6)">
		  <td>${docLink('expense-note', e.name)}${statusPill(e.status || 'Draft')}
		    ${metaLine([e.vendor, fdate(e.date), e.owner_name ? __('oleh {0}', [e.owner_name]) : ''])}</td>
		  <td class="text-right">${money(e.amount)}</td>
		  <td class="text-right">${money(e.tax)}</td>
		  <td class="text-right">${money(e.net)}</td>
		</tr>
		${(e.classes || []).map((c) => `<tr>
		  <td style="padding-left:22px"><span class="cmi-ell" title="${esc(c.expense_class || '-')}">${esc(c.expense_class || '-')}</span></td>
		  <td class="text-right">${money(c.amount)}</td>
		  <td class="text-right">${money(c.tax)}</td>
		  <td class="text-right">${money(c.net)}</td>
		</tr>`).join('')}`;
	const expBody = !exp.length
		? `<tr><td colspan="4" class="text-muted text-center">${__('Belum ada Expense')}</td></tr>`
		: exp.map(expGroup).join('')
		  + `<tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)">
			<td>${__('Total')}</td>
			<td class="text-right">${money(t.expense)}</td>
			<td class="text-right">${money(t.expense_tax)}</td>
			<td class="text-right">${money(t.expense_net)}</td>
		  </tr>`;

	// REVENUE — dikelompokkan per invoice: header (nomor + status + info) lalu item-item
	// di bawahnya (indent), diakhiri baris Total (Amount/Tax/Line Total).
	const revGroup = (rv) => `
		<tr class="summary-head" style="font-weight:600;background:var(--bg-light-gray,#f4f5f6)">
		  <td>${docLink('sales-invoice', rv.invoice)}${statusPill(rv.status || (rv.draft ? 'Draft' : 'Submitted'))}
		    ${metaLine([rv.customer, fdate(rv.date), rv.owner_name ? __('oleh {0}', [rv.owner_name]) : ''])}</td>
		  <td class="text-right">${money(rv.amount)}</td>
		  <td class="text-right">${money(rv.tax)}</td>
		  <td class="text-right">${money(rv.net)}</td>
		</tr>
		${(rv.items || []).map((it) => `<tr>
		  <td style="padding-left:22px"><span class="cmi-ell" title="${esc(it.item || '-')}">${esc(it.item || '-')}</span></td>
		  <td class="text-right">${money(it.amount)}</td>
		  <td class="text-right">${money(it.tax)}</td>
		  <td class="text-right">${money(it.net)}</td>
		</tr>`).join('')}`;
	const revBody = !rev.length
		? `<tr><td colspan="4" class="text-muted text-center">${__('Belum ada Invoice')}</td></tr>`
		: rev.map(revGroup).join('')
		  + `<tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)">
			<td>${__('Total')}</td>
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
		      ${rexp.length ? rexp.map((e) => `<tr><td>${docLink('expense-note', e.name)} <span class="text-muted">${esc(titleOf([e.vendor, e.customer, fdate(e.date)]))}</span></td><td class="text-right">${money(e.amount)}</td></tr>`).join('') : `<tr><td colspan="2" class="text-muted text-center">${__('Belum ada EN reimburse')}</td></tr>`}
		      <tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)"><td>${__('Total Paid')}</td><td class="text-right">${money(reimb.paid)}</td></tr>
		    </tbody>
		  </table>
		  <table class="table table-sm" style="margin:0">
		    <thead><tr><th>${__('Invoice (Reimburse)')}</th><th class="text-right" style="width:28%">${__('Billed')}</th></tr></thead>
		    <tbody>
		      ${rinv.length ? rinv.map((iv) => `<tr><td>${docLink('sales-invoice', iv.name)}${iv.draft ? ` <span class="text-muted">(${__('draft')})</span>` : ''} <span class="text-muted">${esc(titleOf([iv.customer, fdate(iv.date)]))}</span></td><td class="text-right">${money(iv.amount)}</td></tr>`).join('') : `<tr><td colspan="2" class="text-muted text-center">${__('Belum ada invoice reimburse')}</td></tr>`}
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
		      <th>${__('Expense Note / Class')}</th>
		      <th class="text-right" style="width:16%">${__('Amount')}</th>
		      <th class="text-right" style="width:16%">${__('Tax')}</th>
		      <th class="text-right" style="width:16%">${__('Net Total')}</th>
		    </tr></thead>
		    <tbody>${expBody}</tbody>
		  </table>
		</div>

		<div class="frappe-card" style="padding:12px;margin-bottom:12px">
		  <h5 style="margin-top:0">${__('Revenue')}</h5>
		  <table class="table table-sm" style="margin:0">
		    <thead><tr>
		      <th>${__('Invoice / Item')}</th>
		      <th class="text-right" style="width:16%">${__('Amount')}</th>
		      <th class="text-right" style="width:16%">${__('Tax')}</th>
		      <th class="text-right" style="width:16%">${__('Line Total')}</th>
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

// Tabel "Bills of Lading" (menggantikan grid BLs yang disembunyikan): finansial
// per BL — invoice yang menarik BL itu, Expense Note ber-BL No, dan marginnya.
function load_bl_financials(frm) {
	if (frm.is_new() || !(frm.doc.bls || []).length) { render_bl_finance_table(frm, {}); return; }
	frappe.call({ method: 'erp.expedition.financials.bl_financials', args: { shipping_list: frm.doc.name } }).then((r) => {
		render_bl_finance_table(frm, (r && r.message) || {});
	});
}

// Tabel Bills of Lading: No, BL No (klik = Show BL), Containers, Consignee, Attachment,
// Invoice (+date/net), Expense (+date/net), Margin. Tiap BL memakan max(#invoice,
// #expense) baris — kolom BL info & Margin di-rowspan. Fitur: zebra per BL (selang-
// seling redup/terang), search per kolom, sort per kolom, scroll ke samping.
function render_bl_finance_table(frm, map) {
	const fd = frm.fields_dict.bl_finance_table;
	if (!fd || !fd.$wrapper) return;
	const esc = frappe.utils.escape_html;
	const cur = frm.doc.currency || frappe.defaults.get_default('currency') || 'IDR';
	const money = (v) => format_currency(flt(v), cur);
	const fdate = (d) => (d ? frappe.datetime.str_to_user(d) : '');
	const bls = frm.doc.bls || [];
	if (!bls.length) { fd.$wrapper.html(`<div class="text-muted" style="padding:8px;font-size:12px">${__('Belum ada BL.')}</div>`); return; }

	// Satu group per BL, dengan nilai sort/search per kolom yang sudah dihitung.
	const groups = bls.map((bl) => {
		const f = map[bl.bl_no] || {};
		const invs = f.invoices || [];
		const exps = f.expenses || [];
		let att = 0;
		try { att = (JSON.parse(bl.attachments || '[]') || []).length; } catch (err) { att = 0; }
		return {
			bl, f, invs, exps, att,
			key: {
				bl_no: (bl.bl_no || '').toLowerCase(),
				containers: cint(bl.no_containers),
				consignee: (bl.consignee || '').toLowerCase(),
				att: att,
				invoice: invs.map((v) => v.name).join(' ').toLowerCase(),
				inv_date: invs.map((v) => fdate(v.date)).join(' ') + ' ' + invs.map((v) => v.date || '').join(' '),
				net_inv: flt(f.revenue),
				expense: exps.map((v) => v.name).join(' ').toLowerCase(),
				supplier: exps.map((v) => v.vendor || '').join(' ').toLowerCase(),
				exp_class: exps.map((v) => v.classes || '').join(' ').toLowerCase(),
				exp_date: exps.map((v) => fdate(v.date)).join(' ') + ' ' + exps.map((v) => v.date || '').join(' '),
				net_exp: flt(f.expense),
				margin: flt(f.margin),
			},
		};
	});

	const COLS = [
		{ key: 'no', label: __('No') },
		{ key: 'bl_no', label: __('BL No'), search: 1, sort: 1 },
		{ key: 'containers', label: __('Containers'), right: 1, sort: 1, num: 1 },
		{ key: 'consignee', label: __('Consignee/Shipper'), search: 1, sort: 1 },
		{ key: 'att', label: __('Attachment'), right: 1, sort: 1, num: 1 },
		{ key: 'invoice', label: __('Invoice'), search: 1, sort: 1 },
		{ key: 'inv_date', label: __('Invoice Date'), sort: 1 },
		{ key: 'net_inv', label: __('Net Total Inv'), right: 1, sort: 1, num: 1 },
		{ key: 'expense', label: __('Expense'), search: 1, sort: 1 },
		{ key: 'supplier', label: __('Supplier'), search: 1, sort: 1 },
		{ key: 'exp_class', label: __('Class'), search: 1, sort: 1 },
		{ key: 'exp_date', label: __('Expense Date'), sort: 1 },
		{ key: 'net_exp', label: __('Net Total Exp'), right: 1, sort: 1, num: 1 },
		{ key: 'margin', label: __('Margin'), right: 1, sort: 1, num: 1 },
	];

	// State search/sort bertahan selama form terbuka (per dokumen).
	const st = (frm.__bl_table_state = frm.__bl_table_state || { sort_key: null, sort_dir: 1, filters: {} });

	const th = (c) => {
		const arrow = st.sort_key === c.key ? (st.sort_dir > 0 ? ' &#9650;' : ' &#9660;') : '';
		return `<th class="${c.right ? 'text-right' : ''}" data-key="${c.key}"${c.sort ? ' style="cursor:pointer"' : ''}>${c.label}${arrow}</th>`;
	};
	const filter_cell = (c) => (c.search
		? `<td><input type="text" class="form-control cmi-blf" data-key="${c.key}"
			value="${esc(st.filters[c.key] || '')}" placeholder="${__('Cari…')}"></td>`
		: '<td></td>');

	// Styling meniru grid bawaan Frappe: border luar + garis kolom, header abu-abu.
	fd.$wrapper.html(`
		<style>
			.cmi-bl-grid { overflow-x:auto; border:1px solid var(--border-color,#d1d8dd); border-radius:var(--border-radius-md,8px); }
			.cmi-bl-grid table { border-collapse:collapse; font-size:12px; margin:0; width:max-content; min-width:100%; }
			.cmi-bl-grid th, .cmi-bl-grid td { padding:6px 8px; white-space:nowrap; border-bottom:1px solid var(--border-color,#eaecef); }
			.cmi-bl-grid th:not(:last-child), .cmi-bl-grid td:not(:last-child) { border-right:1px solid var(--border-color,#eaecef); }
			.cmi-bl-grid thead th { background:var(--control-bg,#f4f5f6); color:var(--text-muted,#6c7680); font-weight:500; border-bottom-color:var(--border-color,#d1d8dd); }
			.cmi-bl-grid thead td { background:var(--control-bg,#f4f5f6); padding:3px 4px; }
			.cmi-bl-grid tbody td { vertical-align:top; }
			.cmi-bl-grid tfoot td { background:var(--control-bg,#f4f5f6); font-weight:600; border-top:1px solid var(--border-color,#d1d8dd); }
			.cmi-bl-grid .cmi-blf { height:24px; font-size:11px; padding:2px 6px; min-width:90px; }
		</style>
		<div class="cmi-bl-grid">
		<table>
			<thead>
				<tr>${COLS.map(th).join('')}</tr>
				<tr>${COLS.map(filter_cell).join('')}</tr>
			</thead>
			<tbody></tbody>
			<tfoot></tfoot>
		</table></div>`);

	const td = (inner, cls, span, bg) =>
		`<td${span ? ` rowspan="${span}"` : ''} class="${cls || ''}"${bg ? ` style="background:${bg}"` : ''}>${inner}</td>`;

	const render_body = () => {
		// Filter: group tampil bila SEMUA kolom ber-filter cocok (substring, case-insensitive).
		let visible = groups.filter((g) => COLS.every((c) => {
			const q = (st.filters[c.key] || '').trim().toLowerCase();
			return !q || String(g.key[c.key] ?? '').toLowerCase().includes(q);
		}));
		// Sort per group (kolom teks: abjad; kolom angka: numerik).
		if (st.sort_key) {
			const col = COLS.find((c) => c.key === st.sort_key);
			visible = visible.slice().sort((a, b) => {
				const va = a.key[st.sort_key], vb = b.key[st.sort_key];
				const cmpv = col && col.num ? flt(va) - flt(vb) : String(va).localeCompare(String(vb));
				return cmpv * st.sort_dir;
			});
		}

		let html = '';
		let totInv = 0, totExp = 0, totMargin = 0, totCont = 0;
		visible.forEach((g, vi) => {
			const { bl, f, invs, exps } = g;
			const nrows = Math.max(invs.length, exps.length, 1);
			totInv += flt(f.revenue); totExp += flt(f.expense); totMargin += flt(f.margin);
			totCont += cint(bl.no_containers);
			const mColor = (f.margin || 0) >= 0 ? 'green' : 'red';
			// Zebra per BL: group ganjil redup, group berikutnya terang (bukan per baris).
			const bg = vi % 2 === 0 ? 'rgba(127,127,127,0.08)' : '';

			for (let r = 0; r < nrows; r++) {
				html += '<tr>';
				if (r === 0) {
					html += td(vi + 1, '', nrows, bg);
					// Nomor BL = link "Show BL" (modal yang sama dgn tombol file dulu).
					html += td(bl.bl_no
						? `<a href="#" class="cmi-bl-open" data-bl="${esc(bl.bl_no)}" title="${__('Show BL')}"><b>${esc(bl.bl_no)}</b></a>`
						: '-', '', nrows, bg);
					html += td(cint(bl.no_containers), 'text-right', nrows, bg);
					html += td(esc(bl.consignee || '-'), '', nrows, bg);
					html += td(g.att
						? `<a href="#" class="cmi-bl-att" data-bl="${esc(bl.bl_no)}">${g.att} file</a>`
						: '<span class="text-muted">0</span>', 'text-right', nrows, bg);
				}
				const iv = invs[r];
				html += td(iv ? esc(iv.name) + (iv.draft ? ' <span class="text-muted">(draft)</span>' : '') : '', '', 0, bg);
				html += td(iv ? fdate(iv.date) : '', '', 0, bg);
				html += td(iv ? money(iv.net) : '', 'text-right', 0, bg);
				const ex = exps[r];
				html += td(ex ? esc(ex.name) + (ex.reimburse ? ' <span class="text-muted">(reimburse)</span>' : '') : '', '', 0, bg);
				html += td(ex ? esc(ex.vendor || '') : '', '', 0, bg);
				html += td(ex ? esc(ex.classes || '') : '', '', 0, bg);
				html += td(ex ? fdate(ex.date) : '', '', 0, bg);
				html += td(ex ? money(ex.net) : '', 'text-right', 0, bg);
				if (r === 0) html += td(`<b class="text-${mColor}">${money(f.margin)}</b>`, 'text-right', nrows, bg);
				html += '</tr>';
			}
		});
		if (!visible.length) {
			html = `<tr><td colspan="${COLS.length}" class="text-muted text-center" style="padding:10px">${__('Tidak ada BL yang cocok dengan pencarian.')}</td></tr>`;
		}
		fd.$wrapper.find('tbody').html(html);

		// Total mengikuti hasil filter (biar gambarannya sesuai yang tampil).
		fd.$wrapper.find('tfoot').html(`<tr style="font-weight:600;border-top:2px solid var(--border-color,#d1d8dd)">
			<td colspan="2" style="padding:6px 8px;text-align:right">${__('Total')}</td>
			<td class="text-right" style="padding:6px 8px">${totCont}</td>
			<td colspan="4"></td>
			<td class="text-right" style="padding:6px 8px;white-space:nowrap">${money(totInv)}</td>
			<td colspan="4"></td>
			<td class="text-right" style="padding:6px 8px;white-space:nowrap">${money(totExp)}</td>
			<td class="text-right" style="padding:6px 8px;white-space:nowrap"><b class="text-${totMargin >= 0 ? 'green' : 'red'}">${money(totMargin)}</b></td>
		</tr>`);
	};

	// Handler (delegated — tetap hidup saat tbody dirender ulang).
	fd.$wrapper
		.off('click.cmiblf input.cmiblf keydown.cmiblf')
		.on('click.cmiblf', '.cmi-bl-open', function (ev) {
			ev.preventDefault();
			open_bl_dialog(frm, $(this).attr('data-bl'));
		})
		.on('click.cmiblf', '.cmi-bl-att', function (ev) {
			ev.preventDefault();
			show_bl_attachments(frm, $(this).attr('data-bl'));
		})
		.on('click.cmiblf', 'th[data-key]', function () {
			const key = $(this).attr('data-key');
			const col = COLS.find((c) => c.key === key);
			if (!col || !col.sort) return;
			if (st.sort_key === key) {
				st.sort_dir = -st.sort_dir;
			} else {
				st.sort_key = key;
				st.sort_dir = 1;
			}
			render_bl_finance_table(frm, map); // render ulang header (panah sort) + body
		})
		.on('input.cmiblf', '.cmi-blf', function () {
			st.filters[$(this).attr('data-key')] = $(this).val();
			render_body();
		})
		.on('keydown.cmiblf', '.cmi-blf', function (ev) {
			if (ev.key === 'Escape') {
				$(this).val('');
				st.filters[$(this).attr('data-key')] = '';
				render_body();
			}
		});

	render_body();
}

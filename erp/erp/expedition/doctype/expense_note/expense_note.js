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

frappe.ui.form.on('Expense Note', {
	refresh(frm) {
		load_sl_bls(frm);
		window.cmi_cost_center_query(frm);
	},
	shipping_list(frm) {
		frm.set_value('bl_no', null);
		frm.clear_table('bl_containers');
		frm.refresh_field('bl_containers');
		load_sl_bls(frm);
		if (typeof cmi_charges_render === 'function') cmi_charges_render(frm);
	},
	bl_no(frm) {
		load_bl_containers(frm);
	},
	packing_list(frm) {
		load_pl_containers(frm);
	},
});

// Container dari Packing List (distinct container_no di Packing List Item).
function load_pl_containers(frm) {
	if (!frm.doc.packing_list) {
		if (typeof cmi_charges_render === 'function') cmi_charges_render(frm);
		return;
	}
	frappe.call({
		method: 'erp.expedition.doctype.expense_note.expense_note.get_packing_containers',
		args: { packing_list: frm.doc.packing_list },
		callback: (r) => {
			const rows = r.message || [];
			frm.clear_table('bl_containers');
			rows.forEach((c) => {
				const row = frm.add_child('bl_containers');
				row.container_no = c.container_no;
				row.seal_no = c.seal_no;
				row.container_size = c.container_size;
				row.customer = c.customer;
			});
			frm.refresh_field('bl_containers');
			if (typeof cmi_charges_render === 'function') cmi_charges_render(frm);
		},
	});
}

// Populate the BL select from the chosen Shipping List's BLs.
function load_sl_bls(frm) {
	if (!frm.doc.shipping_list) {
		frm._sl_bls = [];
		frm.set_df_property('bl_no', 'options', ['']);
		frm.refresh_field('bl_no');
		return;
	}
	frappe.call({
		method: 'erp.expedition.doctype.expense_note.expense_note.get_shipping_list_bls',
		args: { shipping_list: frm.doc.shipping_list },
		callback: (r) => {
			const rows = r.message || [];
			frm._sl_bls = rows;
			const opts = [''].concat(rows.map((b) => b.bl_no));
			frm.set_df_property('bl_no', 'options', opts.join('\n'));
			frm.refresh_field('bl_no');
		},
	});
}

// When a BL is picked, auto-fill the Containers table with that BL's containers.
// The grid is editable, so the user can delete any rows they don't need.
function load_bl_containers(frm) {
	if (!frm.doc.shipping_list || !frm.doc.bl_no) {
		frm.clear_table('bl_containers');
		frm.refresh_field('bl_containers');
		return;
	}
	frappe.call({
		method: 'erp.expedition.doctype.expense_note.expense_note.get_bl_containers',
		args: { shipping_list: frm.doc.shipping_list, bl_no: frm.doc.bl_no },
		callback: (r) => {
			const rows = r.message || [];
			frm.clear_table('bl_containers');
			rows.forEach((c) => {
				const row = frm.add_child('bl_containers');
				row.container_no = c.container_no;
				row.seal_no = c.seal_no;
				row.container_size = c.container_size;
				row.customer = c.customer;
			});
			frm.refresh_field('bl_containers');
			if (typeof cmi_charges_render === 'function') cmi_charges_render(frm);
		},
	});
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

frappe.ui.form.on('Expense Note', {
	refresh: erp.draft.setup,
	after_save(frm) { if (erp.draft.is_draft(frm)) erp.draft.assign(frm); },
});

// ---- Tab Agent + Email (shared) — JS diambil dari backend lalu di-eval, karena
// /assets/erp tidak tersaji (symlink rusak di nginx frontend, tanpa bench build). ----
window.cmi_load_assistant = window.cmi_load_assistant || function (frm) {
	if (window.cmi_asst_render) { window.cmi_asst_render(frm); return; }
	frappe.call({ method: 'assistant.assistant.api.assistant_js' }).then((r) => {
		if (r && r.message && !window.cmi_asst_render) {
			try { eval(r.message); } catch (e) { console.error('assistant_tabs eval', e); }
		}
		if (window.cmi_asst_render) window.cmi_asst_render(frm);
	});
};
frappe.ui.form.on('Expense Note', {
	refresh(frm) { window.cmi_load_assistant(frm); },
});

// ============================================================================
// Validasi & kunci — Validate => validated=1, semua field read-only (UI) dan
// server menolak perubahan. Hanya Accounts Manager / System Manager yang boleh
// "Batalkan Validasi" (validated 1->0) agar dokumen bisa diedit lagi.
// ============================================================================
frappe.ui.form.on('Expense Note', {
	refresh(frm) { cmi_validate_setup(frm); },
});

function cmi_validate_setup(frm) {
	if (frm.is_new()) return;
	const isMgr = (frappe.user_roles || []).some((r) => r === 'Accounts Manager' || r === 'System Manager');

	if (frm.doc.void) {
		frm.set_read_only();
		frm.page.set_indicator(__('Void'), 'red');
		frm.dashboard.set_headline(
			__('🚫 <b>VOID</b> oleh {0} pada {1} — dibatalkan & terkunci.{2}',
				[frm.doc.void_by || '-', frappe.datetime.str_to_user(frm.doc.void_datetime) || '-',
					frm.doc.void_reason ? (' Alasan: ' + frm.doc.void_reason) : '']));
		if (isMgr) {
			frm.add_custom_button(__('Batalkan Void'), () => {
				frappe.confirm(__('Buka Void agar dokumen bisa diedit lagi?'), () => {
					frm.set_value('void', 0); frm.save();
				});
			});
		}
		return;
	}

	if (frm.doc.validated) {
		frm.set_read_only();
		frm.page.set_indicator(__('Validated'), 'green');
		frm.dashboard.set_headline(
			__('✅ <b>Tervalidasi</b> oleh {0} pada {1} — dokumen terkunci.',
				[frm.doc.validated_by || '-', frappe.datetime.str_to_user(frm.doc.validated_date) || '-']));
		if (isMgr) {
			frm.add_custom_button(__('Batalkan Validasi'), () => {
				frappe.confirm(__('Batalkan validasi agar dokumen bisa diedit lagi?'), () => {
					frm.set_value('validated', 0); frm.save();
				});
			});
		}
		return;
	}

	// draft — bisa Validate atau Void
	frm.add_custom_button(__('Validate'), () => {
		frappe.confirm(__('Validasi Expense Note ini? Setelah divalidasi <b>semua field terkunci</b> dan tidak bisa diedit (kecuali dibatalkan oleh Manager).'), () => {
			frm.set_value('validated', 1); frm.save();
		});
	}).addClass('btn-primary');

	frm.add_custom_button(__('Void'), () => {
		frappe.prompt(
			[{ fieldname: 'reason', fieldtype: 'Small Text', label: __('Alasan Void'), reqd: 1 }],
			(v) => { frm.set_value('void_reason', v.reason); frm.set_value('void', 1); frm.save(); },
			__('Void Expense Note'), __('Void')
		);
	});
}

// ============================================================================
// "Biaya per Expense Class" — alur MODAL. Panel (tab Details) menampilkan
// ringkasan read-only tiap Expense Class + container + harga. Tambah/Edit HANYA
// lewat modal (pilih class + checklist container: pilih semua / sebagian + harga
// tiap container + set harga massal). Tombol "+ Tambah Container" menambah
// container manual ke Connection bila kurang. Semua ditulis ke tabel `items`
// (Expense Note Item): tiap container terpilih = 1 baris (expense_class +
// container_no + qty/price/amount) → total (validate) & alur Sales Invoice tetap.
// ============================================================================
frappe.ui.form.on('Expense Note', {
	refresh(frm) { cmi_charges_init(frm); },
	cost_center(frm) { if (frm._charges && frm._charges.length) cmi_charges_sync(frm); },
});

function cmi_charges_init(frm) {
	if (frm._expense_classes) { cmi_charges_render(frm); return; }
	frappe.db.get_list('Expense Class', {
		filters: { disabled: 0 }, fields: ['name', 'account'], limit: 0, order_by: 'class_name asc',
	}).then((rows) => {
		frm._expense_classes = rows || [];
		frm._class_map = {};
		(rows || []).forEach((r) => { frm._class_map[r.name] = r; });
		cmi_charges_render(frm);
	});
}

function cmi_fmt(n) { return flt(n).toLocaleString('id-ID', { maximumFractionDigits: 2 }); }

// Ada Expense Class yang dipakai? (panel berisi / ada baris items class+container)
function cmi_has_charges(frm) {
	return !!((frm._charges && frm._charges.length)
		|| (frm.doc.items || []).some((r) => r.expense_class && r.container_no));
}

// Kunci BL / Shipping List / Packing List selama masih ada Expense Class.
// User harus hapus semua Expense Class dulu sebelum bisa menggantinya.
function cmi_lock_connection(frm) {
	const lock = cmi_has_charges(frm) ? 1 : 0;
	['shipping_list', 'packing_list', 'bl_no'].forEach((f) => {
		if (frm.fields_dict[f]) frm.set_df_property(f, 'read_only', lock);
	});
}

// Bangun model panel dari baris items yang punya expense_class + container_no.
function cmi_charges_model_from_items(frm) {
	const CMI_COMPS = ['tax', 'pph', 'pph22', 'discount', 'materai'];
	const map = {}, agg = {};
	(frm.doc.items || []).forEach((r) => {
		if (r.expense_class && r.container_no) {
			if (!map[r.expense_class]) { map[r.expense_class] = {}; agg[r.expense_class] = {}; }
			map[r.expense_class][r.container_no] = flt(r.price || r.amount);
			CMI_COMPS.forEach((k) => { agg[r.expense_class][k] = flt(agg[r.expense_class][k]) + flt(r[k]); });
		}
	});
	frm._charges = Object.keys(map).map((c) => Object.assign({ cls: c, cont: map[c] }, agg[c]));
}

// Daftar container yang tersedia = dari BL (bl_containers) + yang sudah dipakai.
function cmi_charges_containers(frm) {
	const seen = {}, list = [];
	(frm.doc.bl_containers || []).forEach((c) => {
		if (c.container_no && !seen[c.container_no]) {
			seen[c.container_no] = 1;
			list.push({ no: c.container_no, size: c.container_size || '', cust: c.customer || '' });
		}
	});
	(frm._charges || []).forEach((p) => Object.keys(p.cont).forEach((cno) => {
		if (!seen[cno]) { seen[cno] = 1; list.push({ no: cno, size: '', cust: '' }); }
	}));
	return list;
}

function cmi_charges_inject_style() {
	if (document.getElementById('cmi-charges-style')) return;
	const s = document.createElement('style');
	s.id = 'cmi-charges-style';
	s.textContent = `
	.cmi-charges{font-size:12px}
	.cmi-ch-top{display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
	.cmi-ch-top .cmi-ch-grand{margin-left:auto;font-weight:600}
	.cmi-ch-hint{padding:10px;border:1px dashed var(--border-color);border-radius:6px;color:var(--text-muted)}
	.cmi-ch-note{padding:6px 10px;margin-bottom:8px;border:1px solid var(--border-color);border-left:3px solid #e09b00;border-radius:6px;background:var(--control-bg,#fff8e6);color:var(--text-muted)}
	.cmi-ch-class{border:1px solid var(--border-color);border-radius:8px;margin-bottom:10px;overflow:hidden}
	.cmi-ch-head{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--control-bg,#f4f5f6)}
	.cmi-ch-head .cmi-ch-sub{margin-left:auto;color:var(--text-muted);font-weight:600}
	.cmi-ch-del{border:none;background:transparent;color:#c0392b;cursor:pointer;font-size:14px;line-height:1}
	.cmi-ch-table{width:100%;border-collapse:collapse}
	.cmi-ch-table td{padding:3px 10px;border-top:1px solid var(--border-color)}
	.cmi-ch-table td.r{text-align:right}
	.cmi-ch-empty{padding:6px 10px;color:var(--text-muted)}
	.cmi-pick-bulk{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
	.cmi-pick-wrap{max-height:46vh;overflow:auto;border:1px solid var(--border-color);border-radius:6px}
	.cmi-pick-table{width:100%;border-collapse:collapse;font-size:12px}
	.cmi-pick-table th,.cmi-pick-table td{padding:4px 8px;border-top:1px solid var(--border-color);vertical-align:middle}
	.cmi-pick-table thead th{border-top:none;text-align:left;color:var(--text-muted);position:sticky;top:0;background:var(--card-bg,#fff)}
	.cmi-pick-table th.r,.cmi-pick-table td.r{text-align:right}
	.cmi-pick-price{text-align:right}
	.cmi-pick-foot{display:flex;justify-content:flex-end;padding:8px 2px 0;font-weight:600}
	`;
	document.head.appendChild(s);
}

function cmi_charges_render(frm) {
	const fd = frm.fields_dict.charges_panel;
	const wrap = fd && fd.$wrapper;
	if (!wrap || !wrap.length) return;
	if (!frm._charges) cmi_charges_model_from_items(frm);
	cmi_charges_inject_style();

	const esc = frappe.utils.escape_html;
	const conts = cmi_charges_containers(frm);
	const hasConn = !!(frm.doc.shipping_list || frm.doc.packing_list);
	const locked = !!(frm.doc.validated || frm.doc.void);

	let grand = 0;
	let html = '<div class="cmi-charges">';
	html += '<div class="cmi-ch-top">'
		+ `<button class="btn btn-xs btn-primary cmi-ch-add"${(hasConn && !locked) ? '' : (' disabled' + (locked ? ' title="Tervalidasi — terkunci"' : ' title="Pilih Shipping List / Packing List dulu"'))}>+ Tambah Expense Class</button>`
		+ '<span class="cmi-ch-grand">Subtotal: Rp <span class="cmi-ch-sub2">0</span> &nbsp;·&nbsp; <b>Net Total: Rp <span class="cmi-ch-net">0</span></b></span></div>';

	if (!hasConn) {
		html += '<div class="cmi-ch-hint">Pilih <b>Shipping List</b> atau <b>Packing List</b> dulu di section <b>Connection</b> untuk mulai menambah Expense Class.</div>';
	} else if (!conts.length) {
		html += '<div class="cmi-ch-hint">Belum ada container. Pilih <b>BL</b> di Connection, atau klik <b>+ Tambah Container</b>.</div>';
	}
	if (cmi_has_charges(frm)) {
		html += '<div class="cmi-ch-note">🔒 Ganti <b>BL / Shipping List / Packing List</b> terkunci selama ada Expense Class. (Menambah container tetap boleh.)</div>';
	}

	(frm._charges || []).forEach((p, pi) => {
		const keys = Object.keys(p.cont);
		let sub = 0; keys.forEach((cno) => { sub += flt(p.cont[cno]); });
		grand += sub;
		html += '<div class="cmi-ch-class">';
		html += `<div class="cmi-ch-head"><b>${esc(p.cls)}</b>`
			+ `<span class="cmi-ch-sub">Subtotal: Rp ${cmi_fmt(sub)}</span>`
			+ (flt(p.tax) ? `<span class="cmi-ch-sub">PPN: Rp ${cmi_fmt(p.tax)}</span>` : '')
			+ (flt(p.pph) ? `<span class="cmi-ch-sub">PPh: Rp ${cmi_fmt(p.pph)}</span>` : '')
			+ (flt(p.pph22) ? `<span class="cmi-ch-sub">PPh22: Rp ${cmi_fmt(p.pph22)}</span>` : '')
			+ (flt(p.discount) ? `<span class="cmi-ch-sub">Disc: Rp ${cmi_fmt(p.discount)}</span>` : '')
			+ (flt(p.materai) ? `<span class="cmi-ch-sub">Materai: Rp ${cmi_fmt(p.materai)}</span>` : '')
			+ (locked ? '' : (`<button class="btn btn-xs btn-default cmi-ch-edit" data-pi="${pi}">✎ Edit</button>`
				+ `<button class="cmi-ch-del" data-pi="${pi}" title="Hapus class">✕</button>`))
			+ '</div>';
		if (!keys.length) {
			html += '<div class="cmi-ch-empty">Belum ada container — klik <b>Edit</b> untuk memilih.</div>';
		} else {
			html += '<table class="cmi-ch-table"><tbody>';
			keys.forEach((cno) => {
				html += `<tr><td>${esc(cno)}</td><td class="r">Rp ${cmi_fmt(p.cont[cno])}</td></tr>`;
			});
			html += '</tbody></table>';
		}
		html += '</div>';
	});
	html += '</div>';
	wrap.html(html);
	wrap.find('.cmi-ch-sub2').text(cmi_fmt(grand));
	wrap.find('.cmi-ch-net').text(cmi_fmt(flt(frm.doc.net_total)));
	cmi_lock_connection(frm);

	wrap.find('.cmi-ch-add').on('click', () => cmi_charges_class_modal(frm, null));
	wrap.find('.cmi-ch-edit').on('click', function () { cmi_charges_class_modal(frm, +$(this).data('pi')); });
	wrap.find('.cmi-ch-del').on('click', function () {
		const pi = +$(this).data('pi'), p = frm._charges[pi];
		frappe.confirm(__('Hapus class "{0}" beserta semua nominalnya?', [p.cls]), () => {
			frm._charges.splice(pi, 1); cmi_charges_sync(frm); cmi_charges_render(frm);
		});
	});
}

// Modal pilih/edit Expense Class: pilih class + checklist container (pilih semua /
// sebagian) + harga tiap container (+ set harga massal). Edit HANYA lewat modal ini.
function cmi_charges_class_modal(frm, editIndex) {
	const esc = frappe.utils.escape_html;
	const conts = cmi_charges_containers(frm);
	if (!conts.length) {
		frappe.msgprint(__('Belum ada container. Pilih Shipping List + BL / Packing List di section Connection, atau klik <b>+ Tambah Container</b> dulu.'));
		return;
	}
	const isEdit = editIndex != null;
	const existing = isEdit ? frm._charges[editIndex] : null;
	const sizeOf = {};
	(frm.doc.bl_containers || []).forEach((c) => { if (c.container_no) sizeOf[c.container_no] = c.container_size || ''; });

	const d = new frappe.ui.Dialog({
		title: isEdit ? __('Edit Expense Class') : __('Tambah Expense Class'),
		size: 'large',
		fields: [
			{
				fieldname: 'cls', fieldtype: 'Link', options: 'Expense Class', label: __('Expense Class'),
				reqd: 1, read_only: isEdit ? 1 : 0, default: isEdit ? existing.cls : '',
				get_query: () => ({ filters: { disabled: 0 } }),
			},
			{ fieldname: 'picker', fieldtype: 'HTML' },
			{ fieldname: 'sb_extra', fieldtype: 'Section Break', label: __('Biaya Tambahan Per Expense Class — boleh % atau nominal') },
			// 3 kolom: [PPN, PPh] | [Discount, PPh22] | [Materai]
			{ fieldname: 'tax', fieldtype: 'Data', label: __('PPN'), default: isEdit ? (existing.tax ? String(existing.tax) : '') : '', description: __('mis. 11% atau 150000') },
			{ fieldname: 'pph', fieldtype: 'Data', label: __('PPh'), default: isEdit ? (existing.pph ? String(existing.pph) : '') : '', description: __('mis. 2% atau 50000') },
			{ fieldname: 'cb_extra', fieldtype: 'Column Break' },
			{ fieldname: 'discount', fieldtype: 'Data', label: __('Discount'), default: isEdit ? (existing.discount ? String(existing.discount) : '') : '', description: __('mis. 5% atau 100000') },
			{ fieldname: 'pph22', fieldtype: 'Data', label: __('PPh 22'), default: isEdit ? (existing.pph22 ? String(existing.pph22) : '') : '', description: __('mis. 1.5% atau 25000') },
			{ fieldname: 'cb_extra2', fieldtype: 'Column Break' },
			{ fieldname: 'materai', fieldtype: 'Currency', label: __('Materai'), default: isEdit ? (existing.materai || 0) : 0, description: __('nominal') },
		],
		primary_action_label: isEdit ? __('Simpan') : __('Tambah'),
		primary_action() {
			const cls = d.get_value('cls');
			if (!cls) { frappe.msgprint(__('Pilih Expense Class dulu.')); return; }
			const cont = {};
			d.$wrapper.find('.cmi-pick-row').each(function () {
				const $r = $(this);
				if ($r.find('.cmi-pick-chk').prop('checked')) {
					cont[String($r.attr('data-cno'))] = flt($r.find('.cmi-pick-price').val());
				}
			});
			if (!Object.keys(cont).length) { frappe.msgprint(__('Pilih minimal 1 container.')); return; }
			let sub = 0; Object.keys(cont).forEach((c) => { sub += flt(cont[c]); });
			const comp = {
				tax: cmi_parse_val(d.get_value('tax'), sub),
				pph: cmi_parse_val(d.get_value('pph'), sub),
				pph22: cmi_parse_val(d.get_value('pph22'), sub),
				discount: cmi_parse_val(d.get_value('discount'), sub),
				materai: flt(d.get_value('materai')),
			};
			if (frm._class_map && !frm._class_map[cls]) frm._class_map[cls] = { name: cls };
			if (isEdit) { existing.cls = cls; existing.cont = cont; Object.assign(existing, comp); }
			else { frm._charges.push(Object.assign({ cls: cls, cont: cont }, comp)); }
			d.hide();
			cmi_charges_sync(frm);
			cmi_charges_render(frm);
		},
	});

	let h = '<div class="cmi-pick-bulk">'
		+ '<label class="cmi-pick-all-l"><input type="checkbox" class="cmi-pick-all"> <b>Pilih semua</b></label>'
		+ '<span style="flex:1"></span>'
		+ '<span>Set harga tercentang:</span>'
		+ '<input type="number" min="0" step="any" class="cmi-pick-bulkval form-control input-xs" style="width:140px">'
		+ '<button class="btn btn-xs btn-default cmi-pick-apply" type="button">Terapkan</button>'
		+ '</div>';
	h += '<div class="cmi-pick-wrap"><table class="cmi-pick-table"><thead><tr><th style="width:34px"></th><th>Container</th><th>Size</th><th class="r">Harga</th></tr></thead><tbody>';
	conts.forEach((c) => {
		const has = existing && Object.prototype.hasOwnProperty.call(existing.cont, c.no);
		const val = has ? (existing.cont[c.no] || '') : '';
		h += `<tr class="cmi-pick-row" data-cno="${esc(c.no)}">`
			+ `<td><input type="checkbox" class="cmi-pick-chk" ${has ? 'checked' : ''}></td>`
			+ `<td>${esc(c.no)}</td><td class="text-muted">${esc(c.size || sizeOf[c.no] || '')}</td>`
			+ `<td class="r"><input type="number" min="0" step="any" class="cmi-pick-price form-control input-xs" value="${val}"></td></tr>`;
	});
	h += '</tbody></table></div><div class="cmi-pick-foot"><span class="cmi-pick-sub">Subtotal: Rp 0</span></div>';
	const $p = d.fields_dict.picker.$wrapper;
	$p.html(h);

	const recalc = () => {
		let s = 0;
		$p.find('.cmi-pick-row').each(function () {
			if ($(this).find('.cmi-pick-chk').prop('checked')) s += flt($(this).find('.cmi-pick-price').val());
		});
		$p.find('.cmi-pick-sub').text('Subtotal: Rp ' + cmi_fmt(s));
	};
	$p.on('change', '.cmi-pick-all', function () { $p.find('.cmi-pick-chk').prop('checked', this.checked); recalc(); });
	$p.on('change', '.cmi-pick-chk', recalc);
	$p.on('input', '.cmi-pick-price', recalc);
	$p.find('.cmi-pick-apply').on('click', () => {
		const v = $p.find('.cmi-pick-bulkval').val();
		$p.find('.cmi-pick-row').each(function () {
			if ($(this).find('.cmi-pick-chk').prop('checked')) $(this).find('.cmi-pick-price').val(v);
		});
		recalc();
	});
	recalc();
	if (isEdit) d.set_value('cls', existing.cls);
	d.show();
}

// ============================================================================
// Amounts — PPN / PPh / PPh 22 / Discount bisa diisi PERSEN atau NOMINAL.
// Basis persen = total_amount (subtotal items). net_total = total + PPN
// - PPh - PPh22 - Discount, dihitung live. Tiap baris mengingat mode terakhir
// (pct/amt) agar nominal fixed tak berubah saat subtotal berubah.
// ============================================================================
frappe.ui.form.on('Expense Note', {
	refresh(frm) { cmi_backfill_inputs(frm); cmi_recalc_amounts(frm); },
	tax_input(frm) { cmi_adj_changed(frm, 'tax'); },
	pph_input(frm) { cmi_adj_changed(frm, 'pph'); },
	pph22_input(frm) { cmi_adj_changed(frm, 'pph22'); },
	discount_input(frm) { cmi_adj_changed(frm, 'discount'); },
});

function cmi_base(frm) { return flt(frm.doc.total_amount); }
function cmi_setf(frm, f, v) { frm.doc[f] = flt(v); frm.refresh_field(f); }

function cmi_adj_changed(frm, k) { cmi_parse_adj(frm, k); cmi_recalc_net(frm); frm.dirty(); }

// Parse satu field "*_input" (nominal / "x%") -> set *_amount & *_pct (hidden) +
// feedback hasil di description. Basis persen = total_amount (subtotal items).
function cmi_parse_adj(frm, k) {
	const raw = String(frm.doc[k + '_input'] || '').trim();
	const b = cmi_base(frm);
	let amount = 0, pct = 0, isPct = false;
	if (raw) {
		isPct = raw.indexOf('%') !== -1;
		const num = flt(raw.replace(/[^0-9.\-]/g, ''));
		if (isPct) { pct = num; amount = b * num / 100; }
		else { amount = num; pct = b ? num / b * 100 : 0; }
	}
	cmi_setf(frm, k + '_amount', amount);
	const fd = frm.fields_dict[k + '_input'];
	if (fd) {
		fd.df.description = raw
			? ('= Rp ' + cmi_fmt(amount) + (isPct ? '' : '  (' + cmi_fmt(pct) + '%)'))
			: 'Ketik nominal atau persen — mis. 11% atau 150000';
		frm.refresh_field(k + '_input');
	}
}
function cmi_recalc_net(frm) {
	const net = flt(frm.doc.total_amount) + flt(frm.doc.tax_amount)
		- flt(frm.doc.pph_amount) - flt(frm.doc.pph22_amount) - flt(frm.doc.discount_amount)
		+ flt(frm.doc.materai_amount);
	cmi_setf(frm, 'net_total', net);
	const fd = frm.fields_dict.charges_panel;
	if (fd && fd.$wrapper) fd.$wrapper.find('.cmi-ch-net').text(cmi_fmt(net));
}
// Parse "% atau nominal" terhadap sebuah base (dipakai modal Expense Class).
function cmi_parse_val(raw, base) {
	raw = String(raw == null ? '' : raw).trim();
	if (!raw) return 0;
	const isPct = raw.indexOf('%') !== -1;
	const num = flt(raw.replace(/[^0-9.\-]/g, ''));
	return flt(isPct ? base * num / 100 : num);
}
// Total komponen k (tax/pph/pph22/discount/materai) dari semua Expense Class (panel).
function cmi_class_sum(frm, k) {
	if (!frm._charges) cmi_charges_model_from_items(frm);
	let s = 0; (frm._charges || []).forEach((p) => { s += flt(p[k]); }); return s;
}
// Akumulasi komponen per Expense Class ke header. Kalau ada Expense Class yang mengisi
// komponen → field header dikunci (read-only) & = akumulasi. Kalau tidak ada → header
// bisa diedit (parse dari input header, bisa "%" atau nominal). Subtotal berubah → re-parse.
function cmi_recalc_amounts(frm) {
	const docLocked = !!(frm.doc.validated || frm.doc.void);
	['tax', 'pph', 'pph22', 'discount'].forEach((k) => {
		const cs = cmi_class_sum(frm, k);
		const fd = frm.fields_dict[k + '_input'];
		if (cs > 0) {
			cmi_setf(frm, k + '_amount', cs);
			frm.doc[k + '_input'] = String(cs);  // nominal mentah agar tetap bisa di-parse
			frm.set_df_property(k + '_input', 'read_only', 1);
			if (fd) fd.df.description = 'Akumulasi dari Expense Class (read-only). Kosongkan di class untuk isi di sini.';
		} else {
			frm.set_df_property(k + '_input', 'read_only', docLocked ? 1 : 0);
			cmi_parse_adj(frm, k);
		}
		frm.refresh_field(k + '_input');
	});
	cmi_setf(frm, 'materai_amount', cmi_class_sum(frm, 'materai'));
	cmi_recalc_net(frm);
}
// Record lama (punya *_amount tapi *_input kosong): isi *_input dari nominal lama.
function cmi_backfill_inputs(frm) {
	['tax', 'pph', 'pph22', 'discount'].forEach((k) => {
		if (String(frm.doc[k + '_input'] || '').trim()) return;
		const amt = flt(frm.doc[k + '_amount']);
		if (amt) frm.doc[k + '_input'] = String(amt);
	});
}

// Tulis model panel -> tabel items. Baris items tanpa (class+container) dibiarkan.
function cmi_charges_sync(frm) {
	const keep = (frm.doc.items || []).filter((r) => !(r.expense_class && r.container_no));
	frm.doc.items = keep;
	(frm._charges || []).forEach((p) => {
		let firstRow = true;
		Object.keys(p.cont).forEach((cno) => {
			const cls = (frm._class_map && frm._class_map[p.cls]) || {};
			const row = frm.add_child('items');
			row.expense_class = p.cls;
			row.container_no = cno;
			row.qty = 1;
			row.price = flt(p.cont[cno]);
			row.amount = flt(p.cont[cno]);
			row.description = p.cls;
			// Komponen per Expense Class (PPN/PPh/PPh22/Discount/Materai) disimpan di baris
			// pertama class (sisanya 0); diakumulasi ke header oleh cmi_apply_class_locks.
			['tax', 'pph', 'pph22', 'discount', 'materai'].forEach((k) => { row[k] = firstRow ? flt(p[k]) : 0; });
			firstRow = false;
			if (cls.account) row.expense_account = cls.account;
			if (frm.doc.cost_center) row.cost_center = frm.doc.cost_center;
		});
	});
	frm.refresh_field('items');
	// total tampilan (server hitung ulang saat save)
	let total = 0; (frm.doc.items || []).forEach((r) => { total += flt(r.amount); });
	frm.doc.subtotal = total; frm.doc.total_amount = total;
	frm.refresh_field('subtotal'); frm.refresh_field('total_amount');
	cmi_recalc_amounts(frm);
	frm.dirty();
}

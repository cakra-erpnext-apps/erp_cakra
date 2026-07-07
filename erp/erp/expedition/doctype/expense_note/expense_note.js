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
	// frm dipakai ulang antar dokumen se-doctype — buang model panel milik
	// dokumen sebelumnya supaya dibangun ulang dari items dokumen ini.
	onload(frm) {
		frm._charges = null;
	},
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
// Komponen per class (PPN/PPh/Discount) disimpan di BARIS PERTAMA tiap class → diakumulasi.
function cmi_charges_model_from_items(frm) {
	const map = {}, comp = {};
	(frm.doc.items || []).forEach((r) => {
		if (r.expense_class && r.container_no) {
			if (!map[r.expense_class]) { map[r.expense_class] = {}; comp[r.expense_class] = { tax: 0, pph: 0, discount: 0, materai: 0 }; }
			map[r.expense_class][r.container_no] = flt(r.price || r.amount);
			['tax', 'pph', 'discount', 'materai'].forEach((k) => { comp[r.expense_class][k] += flt(r[k]); });
		}
	});
	frm._charges = Object.keys(map).map((c) => {
		const p = Object.assign({ cls: c, cont: map[c] }, comp[c]);
		// Raw untuk modal Edit = nominal (tanpa %), supaya nilai lama tak hilang saat disimpan ulang.
		p.tax_raw = flt(p.tax) ? String(flt(p.tax)) : '';
		p.pph_raw = flt(p.pph) ? String(flt(p.pph)) : '';
		p.disc_raw = flt(p.discount) ? String(flt(p.discount)) : '';
		return p;
	});
}

// Format sebuah raw jadi tampilan rapi: nominal -> "50.000,00" (ribuan + desimal sesuai
// presisi default sistem), persen -> "10%", kosong -> "".
function en_fmt_raw(raw) {
	const p = en_parse_input(raw);
	return p.empty ? '' : (p.pct !== null ? en_fmt_pct(p.pct) + '%' : en_fmt_nominal(p.amt));
}
// Auto-format field smart-input di modal saat diketik (onchange). Guard set_value agar
// tidak memicu onchange berulang (loop).
function en_modal_reformat(d, field) {
	const raw = d.get_value(field);
	const fmt = en_fmt_raw(raw);
	if (fmt !== (raw || '')) d.set_value(field, fmt);
}
// Parse "10%" atau nominal terhadap sebuah base -> AMOUNT (dipakai modal komponen per class).
function en_parse_val(raw, base) {
	const p = en_parse_input(raw);
	if (p.empty) return 0;
	if (p.pct !== null) return flt(base) * p.pct / 100;
	return flt(p.amt);
}
// Subtotal komponen k dari semua Expense Class (panel).
function en_class_sum(frm, k) {
	if (!frm._charges) cmi_charges_model_from_items(frm);
	return (frm._charges || []).reduce((s, p) => s + flt(p[k]), 0);
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
			{ fieldname: 'tax_in', fieldtype: 'Data', label: __('PPN'), default: isEdit ? en_fmt_raw(existing.tax_raw) : '', description: __('mis. 11% atau 150000'), onchange() { en_modal_reformat(d, 'tax_in'); } },
			{ fieldname: 'cb_extra', fieldtype: 'Column Break' },
			{ fieldname: 'pph_in', fieldtype: 'Data', label: __('PPh'), default: isEdit ? en_fmt_raw(existing.pph_raw) : '', description: __('mis. 2% atau 50000'), onchange() { en_modal_reformat(d, 'pph_in'); } },
			{ fieldname: 'cb_extra2', fieldtype: 'Column Break' },
			{ fieldname: 'disc_in', fieldtype: 'Data', label: __('Discount'), default: isEdit ? en_fmt_raw(existing.disc_raw) : '', description: __('mis. 5% atau 100000'), onchange() { en_modal_reformat(d, 'disc_in'); } },
			{ fieldname: 'materai_in', fieldtype: 'Currency', options: 'Currency', label: __('Materai'), default: isEdit ? (existing.materai || 0) : 0, description: __('nominal (bea meterai)') },
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
			// Komponen per class: parse "% atau nominal" terhadap subtotal class (dipatok saat entri).
			let sub = 0; Object.keys(cont).forEach((c) => { sub += flt(cont[c]); });
			const tax_raw = d.get_value('tax_in') || '', pph_raw = d.get_value('pph_in') || '', disc_raw = d.get_value('disc_in') || '';
			const comp = {
				tax: en_parse_val(tax_raw, sub), pph: en_parse_val(pph_raw, sub), discount: en_parse_val(disc_raw, sub),
				materai: flt(d.get_value('materai_in')),
				tax_raw: tax_raw, pph_raw: pph_raw, disc_raw: disc_raw,
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
// Amounts — PPN / PPh / Discount: SATU field gabungan "dinamis" per komponen
// (mirror Sales Invoice). Ketik "10%" (persen) ATAU nominal ("50000"); storage
// tersembunyi *_pct / *_amount dikonsumsi server + jurnal. Materai = nominal biasa.
// Discount dihitung dari DPP; PPN & PPh dari DPP setelah discount.
// net_total = total - discount + PPN - PPh + Materai (dihitung live).
// ============================================================================
const EN_SMART = [
	{ input: 'tax_input', pct: 'tax_pct', amt: 'tax_amount' },
	{ input: 'pph_input', pct: 'pph_pct', amt: 'pph_amount' },
	{ input: 'discount_input', pct: 'discount_pct', amt: 'discount_amount' },
];
const EN_SMART_HELP = __('Ketik mis. "10%" atau "50000"');

function en_prec() {
	const p = cint(frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency_precision);
	return p > 0 ? p : 2;
}
// Format persen ringkas: 10 -> "10"; 1.5 -> "1,5" (titik ribuan, koma desimal).
function en_fmt_pct(n) {
	n = flt(n);
	const neg = n < 0;
	const parts = String(Math.abs(n)).split('.');
	const intp = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
	return (neg ? '-' : '') + intp + (parts[1] ? ',' + parts[1] : '');
}
// Format nominal: pakai number_format sistem kalau punya pemisah desimal; kalau tidak
// (mis. "#.###"), paksa gaya Indonesia "#.###,##" supaya desimal tetap tampil (tidak
// bergantung frappe.boot yang bisa basi sebelum reload penuh).
function en_num_format() {
	const nf = (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.number_format) || '';
	return /[.,]\S*[.,]/.test(nf) ? nf : '#.###,##';
}
function en_fmt_nominal(n) { return format_number(flt(n, en_prec()), en_num_format(), en_prec()); }
// "10%" -> {pct:10}; "50.000" -> {amt}; "" -> {empty}. parseFloat (bukan flt) supaya
// teks terformat "1000.00" tidak salah dibaca 100000 saat ter-parse ulang.
function en_parse_input(raw) {
	const s = (raw == null ? '' : String(raw)).trim();
	if (!s) return { pct: null, amt: null, empty: true };
	const is_pct = s.indexOf('%') !== -1;
	const cleaned = s.replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(/,/g, '.');
	const num = parseFloat(cleaned) || 0;
	return is_pct ? { pct: num, amt: null } : { pct: null, amt: flt(num, en_prec()) };
}
function en_set(frm, field, val) {
	if (flt(frm.doc[field]) === flt(val)) return;
	frm.doc[field] = val;
	frm.refresh_field(field);
}
function en_set_text(frm, field, val) {
	if ((frm.doc[field] || '') === (val || '')) return;
	frm.doc[field] = val || '';
	frm.refresh_field(field);
}
// User mengetik -> isi pct/amount tersembunyi, hitung ulang, rapikan tampilan.
function en_apply_input(frm, cfg) {
	const p = en_parse_input(frm.doc[cfg.input]);
	if (p.empty) { en_set(frm, cfg.pct, 0); en_set(frm, cfg.amt, 0); }
	else if (p.pct !== null) { en_set(frm, cfg.pct, p.pct); }
	else { en_set(frm, cfg.pct, 0); en_set(frm, cfg.amt, p.amt); }
	en_compute_amounts(frm);
	en_render_input(frm, cfg);
	frm.dirty();
}
// Tampilan field gabungan dari storage: "10%" (persen) atau nominal terformat.
function en_render_input(frm, cfg) {
	const p = flt(frm.doc[cfg.pct]);
	const a = flt(frm.doc[cfg.amt]);
	en_set_text(frm, cfg.input, p > 0 ? en_fmt_pct(p) + '%' : a ? en_fmt_nominal(a) : '');
}
function en_hydrate_inputs(frm) { EN_SMART.forEach((cfg) => en_render_input(frm, cfg)); }
// Hint "= Rp X" di bawah tiap field gabungan.
function en_update_hints(frm) {
	const cur = frm.doc.currency || 'IDR';
	EN_SMART.forEach((cfg) => {
		let hint = EN_SMART_HELP;
		if (flt(frm.doc[cfg.pct]) > 0 || flt(frm.doc[cfg.amt])) {
			hint = __('= {0}', [format_currency(flt(frm.doc[cfg.amt]), cur)]);
		}
		frm.set_df_property(cfg.input, 'description', hint);
	});
}
// Hitung amounts live (mirror server). Prioritas per komponen: akumulasi Expense Class
// (kalau ada) > persen header > nominal header. Header dikunci saat class mengisinya.
function en_compute_amounts(frm) {
	const total = flt(frm.doc.total_amount);
	const cs = { discount: en_class_sum(frm, 'discount'), tax: en_class_sum(frm, 'tax'), pph: en_class_sum(frm, 'pph') };
	const docLocked = !!(frm.doc.validated || frm.doc.void);

	let discount;
	if (cs.discount > 0) { discount = cs.discount; en_set(frm, 'discount_amount', discount); }
	else if (flt(frm.doc.discount_pct) > 0) { discount = total * flt(frm.doc.discount_pct) / 100; en_set(frm, 'discount_amount', discount); }
	else { discount = flt(frm.doc.discount_amount); }
	const dpp = total - discount;
	let tax;
	if (cs.tax > 0) { tax = cs.tax; en_set(frm, 'tax_amount', tax); }
	else if (flt(frm.doc.tax_pct) > 0) { tax = dpp * flt(frm.doc.tax_pct) / 100; en_set(frm, 'tax_amount', tax); }
	else { tax = flt(frm.doc.tax_amount); }
	let pph;
	if (cs.pph > 0) { pph = cs.pph; en_set(frm, 'pph_amount', pph); }
	else if (flt(frm.doc.pph_pct) > 0) { pph = dpp * flt(frm.doc.pph_pct) / 100; en_set(frm, 'pph_amount', pph); }
	else { pph = flt(frm.doc.pph_amount); }
	// Materai: akumulasi dari Expense Class (kalau ada) menang atas nominal header.
	const materaiCs = en_class_sum(frm, 'materai');
	if (materaiCs > 0) en_set(frm, 'materai_amount', materaiCs);
	const materai = flt(frm.doc.materai_amount);
	const net = total - discount + tax - pph + materai;
	en_set(frm, 'net_total', net);

	// Kunci / buka field input header sesuai apakah komponennya diisi dari Expense Class.
	[['discount', cs.discount], ['tax', cs.tax], ['pph', cs.pph]].forEach(([k, sum]) => {
		if (sum > 0) {
			frm.doc[k + '_pct'] = 0;
			en_set_text(frm, k + '_input', en_fmt_nominal(flt(frm.doc[k + '_amount'])));
			frm.set_df_property(k + '_input', 'read_only', 1);
		} else {
			frm.set_df_property(k + '_input', 'read_only', docLocked ? 1 : 0);
		}
	});
	if (frm.fields_dict.materai_amount) frm.set_df_property('materai_amount', 'read_only', (materaiCs > 0 || docLocked) ? 1 : 0);

	const fd = frm.fields_dict.charges_panel;
	if (fd && fd.$wrapper) fd.$wrapper.find('.cmi-ch-net').text(cmi_fmt(net));
	en_update_hints(frm);
}

frappe.ui.form.on('Expense Note', {
	refresh(frm) { en_hydrate_inputs(frm); en_compute_amounts(frm); },
	tax_input(frm) { en_apply_input(frm, EN_SMART[0]); },
	pph_input(frm) { en_apply_input(frm, EN_SMART[1]); },
	discount_input(frm) { en_apply_input(frm, EN_SMART[2]); },
	materai_amount(frm) { en_compute_amounts(frm); },
});

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
			// Komponen per class (PPN/PPh/Discount) di baris PERTAMA class saja (sisanya 0);
			// server & header mengakumulasi dari sini.
			['tax', 'pph', 'discount', 'materai'].forEach((k) => { row[k] = firstRow ? flt(p[k]) : 0; });
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
	en_compute_amounts(frm);
	frm.dirty();
}

// ============================================================================
// Tabel Cost — tipe JOB / NO-JOB (menggantikan Connection + Biaya per Expense
// Class; lihat depends_on di expense_note.json). Amount = Qty x Price; Account
// dipilih user (akun leaf milik company). Server membangun ulang items dari
// baris cost saat save (_sync_cost_items).
// ============================================================================
frappe.ui.form.on('Expense Note', {
	refresh(frm) {
		frm.set_query('account', 'costs', () => {
			const company = frm.doc.company || frappe.defaults.get_default('company');
			return { filters: company ? { company: company, is_group: 0 } : { is_group: 0 } };
		});
	},
});

function cmi_cost_amount(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, 'amount', (flt(row.qty) || 1) * flt(row.price));
}

frappe.ui.form.on('Expense Note Cost', {
	qty(frm, cdt, cdn) { cmi_cost_amount(cdt, cdn); },
	price(frm, cdt, cdn) { cmi_cost_amount(cdt, cdn); },
});

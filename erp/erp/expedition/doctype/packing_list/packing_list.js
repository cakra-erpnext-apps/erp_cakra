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

// ---- Route: milik Packing List, disemai dari estimation ----
// Barisnya tersimpan di child table `routes` supaya bisa dipilih ulang atau ditambah.
// Koordinatnya ikut lewat fetch_from di doctype anaknya, jadi peta tidak perlu
// bolak-balik ke server tiap kali barisnya diubah.
function cmi_pl_route_wrappers(frm) {
	const map = frm.get_field('route_map_html');
	const chain = frm.get_field('route_chain_html');
	return map && chain ? { map: map.$wrapper, chain: chain.$wrapper } : null;
}

// Grid sengaja menyimpan 8 slot, sebagiannya boleh kosong. Peta & rantai route
// hanya memakai yang terisi, dan menomorinya berurutan supaya ringkas.
function cmi_pl_points(frm) {
	return (frm.doc.routes || []).filter((row) => row.location).map((row, i) => ({
		text: String(i + 1),
		label: row.location,
		jenis: row.jenis,
		lat: row.latitude,
		lon: row.longitude,
	}));
}

function cmi_pl_route_render(frm) {
	const w = cmi_pl_route_wrappers(frm);
	if (!w) return;
	const points = cmi_pl_points(frm);
	cmi_pl_route_chain(w.chain, points);
	cmi_pl_route_map(frm, w.map, points);
}

// Ganti estimation = salin ulang seluruh route dari estimation itu. Perubahan
// manual di grid memang sengaja dibuang; itu yang diminta.
function cmi_pl_route_seed(frm) {
	const w = cmi_pl_route_wrappers(frm);
	const estimation = frm.doc.estimation || frm.doc.agent_estimation;
	frm.clear_table('routes');
	if (!estimation) {
		frm.refresh_field('routes');
		cmi_pl_route_render(frm);
		return;
	}
	if (w) w.chain.html(`<div class="text-muted"><i class="fa fa-spinner fa-spin"></i> ${__('Memuat route…')}</div>`);
	frappe.call({
		method: 'erp.expedition.doctype.packing_list.packing_list.estimation_route',
		args: { estimation },
	}).then((r) => {
		// Slot kosong ikut dibuat: grid selalu 8 baris, sejajar dengan estimation-nya.
		((r && r.message && r.message.points) || []).forEach((p) => {
			frm.add_child('routes', { location: p.name, latitude: p.lat, longitude: p.lon });
		});
		// Loading/Unloading estimation = Origin/Destination PL. Hanya diisi kalau
		// estimation-nya punya; yang sudah diketik manual tidak dikosongkan.
		const m = (r && r.message) || {};
		if (m.loading) frm.set_value('origin_location', m.loading);
		if (m.unloading) frm.set_value('destination_location', m.unloading);
		frm.refresh_field('routes');
		cmi_pl_route_render(frm);
	}).catch(() => {
		if (w) w.chain.html(`<div class="text-danger">${__('Gagal memuat route.')}</div>`);
	});
}

function cmi_pl_route_chain($wrapper, points) {
	if (!points.length) {
		$wrapper.empty();
		return;
	}
	const chips = points.map((p) => {
		// Titik tanpa koordinat tetap ditampilkan supaya urutannya utuh, tapi diredupkan.
		const mapped = p.lat && p.lon;
		const hint = mapped ? '' : ` title="${__('Titik ini belum punya koordinat')}"`;
		const langsir = p.jenis === 'Langsir' ? 'color:#b45309;border-color:#b45309;' : '';
		return `<span class="border rounded ${mapped ? '' : 'text-muted'}" style="padding:2px 8px;${langsir}"${hint}>${p.text}. ${frappe.utils.escape_html(p.label)}</span>`;
	}).join('<span class="text-muted mx-1">&rarr;</span>');
	$wrapper.html(`<div class="d-flex flex-wrap align-items-center mb-3" style="gap:4px">${chips}</div>`);
}

// Pin digambar sama seperti MiniMap.vue di CRM: bulatan biru bernomor.
// Route Langsir dibedakan oranye gelap (warna badge Langsir di Dispatch Order).
function cmi_pl_pin(text, jenis) {
	const bg = jenis === 'Langsir' ? '#b45309' : '#2563eb';
	return L.divIcon({
		className: '',
		html: '<div style="background:' + bg + ';color:#fff;border:2px solid #fff;border-radius:9999px;' +
			'width:24px;height:24px;display:flex;align-items:center;justify-content:center;' +
			'font-size:11px;font-weight:600">' + text + '</div>',
		iconSize: [24, 24],
		iconAnchor: [12, 12],
	});
}

function cmi_pl_route_map(frm, $wrapper, points) {
	// Titik tanpa koordinat dilewati diam-diam: masternya boleh belum di-pin, dan itu
	// bukan alasan mengosongkan peta.
	const ok = points.filter((p) => p.lat && p.lon);
	if (!ok.length) {
		$wrapper.html(`<div class="text-muted">${__('Belum ada route berkoordinat untuk dipetakan.')}</div>`);
		frm._pl_map = null;
		return;
	}
	// Wrapper dibuat ulang tiap form di-render ulang; peta lama ikut hilang dari DOM.
	if (!frm._pl_map || !document.body.contains(frm._pl_map.getContainer())) {
		// position+z-index: tanpa ini pane Leaflet (z-index 400-700) memanjat di atas
		// page-head Frappe yang sticky. Wadahnya dibuat stacking context sendiri.
		$wrapper.html('<div class="pl-route-map border rounded" style="height:320px;position:relative;z-index:0"></div>');
		// Leaflet bundel frappe crash kalau layer ditambah sebelum view di-set.
		frm._pl_map = L.map($wrapper.find('.pl-route-map')[0], { attributionControl: false }).setView([-2.5, 118], 5);
		L.tileLayer('/tiles/{z}/{x}/{y}.png', {
			attribution: '&copy; OpenStreetMap', subdomains: 'abcd', maxZoom: 19,
		}).addTo(frm._pl_map);
		frm._pl_layer = L.layerGroup().addTo(frm._pl_map);
	}
	frm._pl_layer.clearLayers();
	const latlngs = ok.map((p) => [p.lat, p.lon]);
	L.polyline(latlngs, { color: '#2563eb', weight: 3 }).addTo(frm._pl_layer);
	ok.forEach((p, i) => {
		L.marker(latlngs[i], { icon: cmi_pl_pin(p.text, p.jenis) }).bindTooltip(p.label).addTo(frm._pl_layer);
	});
	frm._pl_map.fitBounds(L.latLngBounds(latlngs).pad(0.2), { maxZoom: 13 });
	// Peta yang digambar saat wadahnya belum punya tinggi akan tampil abu-abu.
	setTimeout(() => frm._pl_map && frm._pl_map.invalidateSize(), 100);
}

// Grid route diubah tangan -> rantai & peta ikut, tanpa menyentuh server.
// CATATAN: event grid (*_add/*_remove/*_move/field) DIKIRIM dengan doctype CHILD
// (grid.js men-trigger pakai d.doctype) — daftarkan di doctype child, bukan parent;
// di parent handler-nya tidak pernah terpanggil.
frappe.ui.form.on('Packing List Route', {
	jenis: cmi_pl_route_render,
	location: cmi_pl_route_render,
	routes_add: cmi_pl_route_render,
	routes_remove: cmi_pl_route_render,
	routes_move: cmi_pl_route_render,
});

// Baris item baru mewarisi isian header section Estimation (hanya field yang terisi).
frappe.ui.form.on('Packing List Item', {
	items_add(frm, cdt, cdn) {
		CMI_PL_SPREAD.forEach((f) => {
			if (frm.doc[f]) frappe.model.set_value(cdt, cdn, f, frm.doc[f]);
		});
	},
});

// Header section Estimation and Customer -> kolom senama di tiap baris Items.
// Nilai ditulis langsung ke objek barisnya lalu grid di-refresh SEKALI: lewat
// frappe.model.set_value, 100 baris x 4 kolom = 400 kali render ulang grid.
const CMI_PL_SPREAD = ['customer', 'estimation', 'agent', 'agent_estimation'];

// Flag "Packing List Party Read Only" (ERPNext Custom Setting, tab Flag): kolom
// party di Items dikunci — hanya terisi lewat header. Dinilai tiap refresh supaya
// berlaku untuk dokumen baru maupun lama tanpa reload.
function cmi_pl_party_lock(frm) {
	frappe.db.get_single_value('ERPNext Custom Setting', 'packing_list_party_readonly').then((locked) => {
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!grid) return;
		CMI_PL_SPREAD.forEach((f) => grid.update_docfield_property(f, 'read_only', locked ? 1 : 0));
	});
}

// ---- Kolom Trip di grid Items ----
// Jumlah trip per container dari Dispatch Order milik PL ini (1 PL = 1 DPO). Nilainya
// TIDAK disimpan di baris (field virtual): tiap refresh diambil ulang dari server,
// dirender formatter jadi "{n} trip"; klik = modal rincian Dispatch Order Route.
function cmi_pl_load_trips(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: 'erp.expedition.doctype.packing_list.packing_list.container_trips',
		args: { packing_list: frm.doc.name },
	}).then((r) => {
		frm._pl_trips = (r && r.message) || {};
		// Tulis langsung ke row (BUKAN set_value): field-nya virtual, tidak ikut
		// tersimpan dan tidak menandai form dirty — murni untuk tampilan grid.
		// frappe.format di grid mengabaikan df.formatter, makanya bukan formatter.
		(frm.doc.items || []).forEach((row) => {
			const info = frm._pl_trips[row.name];
			row.trips = `${info ? info.trips : 0} trip`;
		});
		frm.refresh_field('items');
	});
}

function cmi_pl_setup_trip_column(frm) {
	// Klik sel Trip = buka modal, BUKAN masuk mode edit baris. Handler grid terpasang
	// lebih dalam dan menang lewat bubbling, jadi kita pakai capture phase (jalan
	// duluan) lalu menghentikan propagasinya. Cukup dipasang sekali per halaman.
	if (!window._cmi_pl_trip_capture) {
		window._cmi_pl_trip_capture = true;
		document.addEventListener('click', (ev) => {
			if (!ev.target.closest || !window.cur_frm || cur_frm.doctype !== 'Packing List') return;
			const cell = ev.target.closest('.grid-static-col[data-fieldname="trips"]');
			const ctl = cell && cell.closest('.frappe-control[data-fieldname="items"]');
			if (!ctl) return;
			const rows = Array.from(ctl.querySelectorAll('.grid-body .grid-row'));
			const i = rows.indexOf(cell.closest('.grid-row'));
			if (i < 0) return; // header
			ev.stopPropagation();
			ev.preventDefault();
			const row = (cur_frm.doc.items || [])[i];
			if (row) cmi_pl_show_trips(cur_frm, row.name);
		}, true);
	}
	if (!document.getElementById('pl-trip-style')) {
		const s = document.createElement('style');
		s.id = 'pl-trip-style';
		s.textContent = '.frappe-control[data-fieldname="items"] .grid-static-col[data-fieldname="trips"] .static-area { cursor: pointer; color: var(--primary-color, #2563eb); }';
		document.head.appendChild(s);
	}
}

function cmi_pl_show_trips(frm, rowname) {
	const info = (frm._pl_trips || {})[rowname];
	if (!info) return;
	const dt = (v) => (v ? frappe.datetime.str_to_user(v) : '-');
	const esc = frappe.utils.escape_html;
	const body = info.rows.map((r) => `<tr>
		<td>${r.trip || 1}</td><td>${r.step || ''}</td><td>${esc(r.step_type || '')}</td>
		<td>${esc(r.point || r.point_type || '')}</td>
		<td>${dt(r.start)}</td><td>${dt(r.end)}</td>
		<td>${esc(r.driver || '')}</td><td>${esc(r.vehicle || '')}</td>
	</tr>`).join('');
	const html = `<div class="table-responsive"><table class="table table-bordered table-sm">
		<thead><tr><th>Trip</th><th>Step</th><th>Step Type</th><th>Point</th>
		<th>Start</th><th>End</th><th>Driver</th><th>Vehicle</th></tr></thead>
		<tbody>${body}</tbody></table></div>`;
	new frappe.ui.Dialog({
		title: __('Container {0} — {1} trip', [info.container_no || '', info.trips]),
		size: 'extra-large',
		fields: [{ fieldtype: 'HTML', fieldname: 'body', options: html }],
	}).show();
}

function cmi_pl_spread(frm, fieldname) {
	const rows = frm.doc.items || [];
	if (!rows.length) return;
	const value = frm.doc[fieldname] || null;
	rows.forEach((row) => { row[fieldname] = value; });
	frm.refresh_field('items');
	frm.dirty();
}

frappe.ui.form.on('Packing List', {
	setup(frm) {
		// Filter link di grid Items: Est Cust/Est Agent = CRM Estimation per purpose,
		// Customer aktif saja, Agent Customer = Customer bergrup "Agent" (di-seed erp.install).
		// Estimation yang ditawarkan hanya yang SUDAH divalidasi, BELUM expired, dan BELUM
		// dipakai Packing List lain. Yang tanpa Expired Date ikut tersaring — anggap belum
		// lengkap, isi dulu masa berlakunya.
		//
		// "Belum dipakai" tidak bisa jadi filter link biasa, jadi dipakai link query di
		// server (unused_estimation_query); syarat lainnya tetap dikirim sebagai `filters`
		// supaya cuma ada satu tempat kalau berubah. exclude_packing_list = dokumen ini
		// sendiri, agar estimation miliknya tetap boleh dipilih ulang.
		const not_expired = () => ['>=', frappe.datetime.get_today()];
		const EST_QUERY = 'erp.expedition.doctype.packing_list.packing_list.unused_estimation_query';
		const est_query = (purpose, party) => () => ({
			query: EST_QUERY,
			filters: {
				purpose,
				disabled: 0,
				validated: 1,
				expired_date: not_expired(),
				exclude_packing_list: frm.doc.name,
				...(party ? { customer_id: party() } : {}),
			},
		});
		frm.set_query('estimation', 'items', est_query('Customer'));
		frm.set_query('agent_estimation', 'items', est_query('Agent'));
		frm.set_query('customer', 'items', () => ({ filters: { disabled: 0 } }));
		frm.set_query('agent', 'items', () => ({ filters: { customer_group: 'Agent', disabled: 0 } }));

		// Header (section Estimation and Customer): sama, ditambah batasan pihak yang sudah
		// dipilih (customer_id sama). Est-nya read_only sampai pihaknya diisi
		// (read_only_depends_on di doctype).
		frm.set_query('customer', () => ({ filters: { disabled: 0 } }));
		frm.set_query('agent', () => ({ filters: { disabled: 0 } }));
		frm.set_query('estimation', est_query('Customer', () => frm.doc.customer));
		frm.set_query('agent_estimation', est_query('Agent', () => frm.doc.agent));
	},
	// Ganti pihaknya = estimation lama tidak lagi cocok, jangan ditinggal nyangkut.
	// set_value di sini memicu handler estimation/agent_estimation di bawah, jadi
	// baris-barisnya ikut dikosongkan tanpa perlu disebut dua kali.
	customer(frm) { frm.set_value('estimation', null); cmi_pl_spread(frm, 'customer'); },
	agent(frm) { frm.set_value('agent_estimation', null); cmi_pl_spread(frm, 'agent'); },
	estimation(frm) { cmi_pl_spread(frm, 'estimation'); cmi_pl_route_seed(frm); },
	agent_estimation(frm) { cmi_pl_spread(frm, 'agent_estimation'); cmi_pl_route_seed(frm); },
	refresh(frm) {
		window.cmi_load_assistant(frm);
		window.cmi_cost_center_query(frm);
		cmi_pl_party_lock(frm);
		cmi_pl_setup_trip_column(frm);
		cmi_pl_load_trips(frm);
		// Type dikunci begitu dokumen tersimpan: branch_office (read_only, fetch dari
		// type.branch) & nomor dokumen ikut type, jadi type tidak boleh diubah belakangan.
		frm.set_df_property('type', 'read_only', frm.is_new() ? 0 : 1);
		cmi_pl_route_render(frm);
		cmi_pl_summary(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Invoice'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_INVOICE)).addClass('btn-primary');
			frm.add_custom_button(__('Create Expense Note'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_EXPENSE));
		}
	},
});

// ---- Tab Summary -------------------------------------------------------------------
// Empat section (Expense / Reimburse / Invoice / Margin) dari satu panggilan server —
// lihat packing_list.summary. Angka baris pakai mata uang dokumennya, rekap Margin
// pakai mata uang perusahaan.
function cmi_pl_summary_style() {
	if (document.getElementById('pl-summary-style')) return;
	const s = document.createElement('style');
	s.id = 'pl-summary-style';
	s.textContent = `
	.pl-sum h5 { margin: 0 0 8px; font-weight: 600; }
	.pl-sum table { font-size: 12px; }
	/* Satu baris = satu record: isi sel jangan dipatah ke bawah (tabelnya sudah
	   dibungkus .table-responsive, jadi melebar = scroll ke samping). */
	.pl-sum th, .pl-sum td { white-space: nowrap; }
	.pl-sum td.num, .pl-sum th.num { text-align: right; white-space: nowrap; }
	.pl-sum .pl-grp-head td { background: var(--fg-color, #f8f9fa); font-weight: 600; cursor: pointer; }
	.pl-sum tbody.collapsed tr.pl-item { display: none; }
	.pl-sum .pl-caret::before { content: '▾ '; }
	.pl-sum tbody.collapsed .pl-caret::before { content: '▸ '; }
	.pl-sum .pl-ok { color: var(--green-600, #2e7d32); }
	.pl-sum .pl-no { color: var(--red-600, #c62828); }
	.pl-sum .pl-margin-pos { color: var(--green-600, #2e7d32); }
	.pl-sum .pl-margin-neg { color: var(--red-600, #c62828); }
	.pl-sum .pl-totals td:nth-child(odd) { color: var(--text-muted); }
	`;
	document.head.appendChild(s);
}

function cmi_pl_summary(frm) {
	const field = frm.get_field('summary_html');
	if (!field) return;
	if (frm.is_new()) { field.$wrapper.empty(); return; }
	cmi_pl_summary_style();
	field.$wrapper.html(`<div class="text-muted"><i class="fa fa-spinner fa-spin"></i> ${__('Memuat summary…')}</div>`);
	frappe.call({
		method: 'erp.expedition.doctype.packing_list.packing_list.summary',
		args: { packing_list: frm.doc.name },
	}).then((r) => {
		const d = (r && r.message) || {};
		field.$wrapper.html(`<div class="pl-sum">
			${cmi_pl_sum_expense(d.expenses || [])}
			${cmi_pl_sum_reimburse(d.reimburse || [])}
			${cmi_pl_sum_invoice(d.invoices || [])}
			${cmi_pl_sum_margin(d.totals || {})}
		</div>`);
		// Klik baris invoice = lipat/buka item-itemnya (default terbuka).
		field.$wrapper.off('click.plsum').on('click.plsum', '.pl-grp-head', function () {
			$(this).closest('tbody').toggleClass('collapsed');
		});
	}).catch(() => field.$wrapper.html(`<div class="text-danger">${__('Gagal memuat summary.')}</div>`));
}

const _pls_esc = (v) => frappe.utils.escape_html(String(v == null ? '' : v));
const _pls_cur = (v, c) => format_currency(v || 0, c || 'IDR');
const _pls_date = (v) => (v ? frappe.datetime.str_to_user(String(v).split(' ')[0]) : '');
const _pls_link = (dt, name) =>
	name ? `<a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${_pls_esc(name)}</a>` : '';

// Section + tabel; head = array label ('num ' di depan = rata kanan).
function cmi_pl_sum_table(title, head, body, empty) {
	if (!body) return `<h5>${title}</h5><p class="text-muted mb-4">${empty}</p>`;
	const th = head.map((h) => {
		const num = h.startsWith('num ');
		return `<th class="${num ? 'num' : ''}">${num ? h.slice(4) : h}</th>`;
	}).join('');
	return `<h5>${title}</h5><div class="table-responsive mb-4">
		<table class="table table-bordered table-sm"><thead><tr>${th}</tr></thead>${body}</table></div>`;
}

function cmi_pl_sum_expense(rows) {
	const body = rows.map((r) => `<tr>
		<td>${_pls_esc(r.container)}</td>
		<td>${_pls_link('Expense Note', r.en)}</td>
		<td>${_pls_date(r.date)}</td>
		<td>${_pls_esc(r.expense_class)}</td>
		<td>${_pls_esc(r.currency)}</td>
		<td class="num">${format_number(r.rate)}</td>
		<td class="num">${_pls_cur(r.amount, r.currency)}</td>
		<td class="num">${_pls_cur(r.discount, r.currency)}</td>
		<td class="num">${_pls_cur(r.tax, r.currency)}</td>
		<td class="num">${_pls_cur(r.net, r.currency)}</td>
		<td class="${r.sesuai === 'Ya' ? 'pl-ok' : r.sesuai ? 'pl-no' : ''}">${_pls_esc(r.sesuai)}</td>
		<td>${r.validated ? __('Yes') : __('No')}</td>
		<td class="num">${_pls_cur(r.paid, r.currency)}</td>
	</tr>`).join('');
	return cmi_pl_sum_table(__('Expense'),
		['Container', 'Expense No', 'Expense Date', 'Expense Class', 'Currency', 'num Rate',
			'num Amount', 'num Discount', 'num Tax', 'num Net Total', 'Sesuai Estimation',
			'Validate', 'num Paid Amount'],
		body && `<tbody>${body}</tbody>`, __('Belum ada Expense Note.'));
}

function cmi_pl_sum_reimburse(rows) {
	const body = rows.map((r) => `<tr>
		<td>${_pls_esc(r.container)}</td>
		<td>${_pls_link('Expense Note', r.en)}</td>
		<td>${_pls_date(r.date)}</td>
		<td>${_pls_esc(r.expense_class)}</td>
		<td>${_pls_esc(r.currency)}</td>
		<td class="num">${format_number(r.rate)}</td>
		<td class="num">${_pls_cur(r.amount, r.currency)}</td>
		<td class="num">${_pls_cur(r.discount, r.currency)}</td>
		<td class="num">${_pls_cur(r.tax, r.currency)}</td>
		<td class="num">${_pls_cur(r.net, r.currency)}</td>
		<td class="num">${_pls_cur(r.paid, r.currency)}</td>
		<td>${_pls_esc(r.customer)}</td>
		<td>${_pls_link('Sales Invoice', r.invoice)}</td>
		<td>${_pls_date(r.invoice_date)}</td>
		<td>${r.markup ? __('Yes') : __('No')}</td>
		<td class="num">${_pls_cur(r.invoice_paid)}</td>
	</tr>`).join('');
	return cmi_pl_sum_table(__('Reimburse'),
		['Container', 'Expense No', 'Expense Date', 'Expense Class', 'Currency', 'num Rate',
			'num Amount', 'num Discount', 'num Tax', 'num Net Total', 'num Amount Paid',
			'Customer', 'Invoice No', 'Invoice Date', 'Mark Up', 'num Invoice Paid Amount'],
		body && `<tbody>${body}</tbody>`, __('Belum ada expense reimburse.'));
}

// 1 invoice = 1 tbody: baris kepala (kolom level invoice) + baris item, bisa dilipat.
function cmi_pl_sum_invoice(groups) {
	const body = groups.map((g) => {
		const items = (g.items || []).map((it) => `<tr class="pl-item">
			<td colspan="7"></td>
			<td>${_pls_esc(it.item_name)}</td>
			<td class="num">${_pls_cur(it.net, g.currency)}</td>
			<td colspan="2"></td>
		</tr>`).join('');
		return `<tbody>
			<tr class="pl-grp-head">
				<td>${_pls_esc(g.estimation)}</td>
				<td>${_pls_esc((g.containers || []).join(', '))}</td>
				<td><span class="pl-caret"></span>${_pls_link('Sales Invoice', g.invoice)}${g.draft ? ' (draft)' : ''}</td>
				<td>${_pls_date(g.date)}</td>
				<td>${_pls_esc(g.customer)}</td>
				<td>${_pls_esc(g.currency)}</td>
				<td class="num">${format_number(g.rate)}</td>
				<td colspan="2"></td>
				<td class="num">${_pls_cur(g.tax, g.currency)}</td>
				<td class="num">${_pls_cur(g.net)}</td>
			</tr>${items}</tbody>`;
	}).join('');
	return cmi_pl_sum_table(__('Invoice'),
		['Estimation', 'Container', 'Invoice No', 'Invoice Date', 'Customer', 'Currency', 'num Rate',
			'Item Name', 'num Item Net Total', 'num Invoice Tax', 'num Invoice Net Total'],
		body, __('Belum ada Sales Invoice.'));
}

function cmi_pl_sum_margin(t) {
	const c = t.currency || 'IDR';
	const amt = (v) => `<td class="num">${_pls_cur(v, c)}</td>`;
	const pct = t.margin_pct != null ? ` (${t.margin_pct}%)` : '';
	return `<h5>${__('Margin')}</h5><div class="table-responsive">
		<table class="table table-bordered table-sm pl-totals" style="max-width:640px">
			<tbody>
				<tr><td>${__('Expense')}</td>${amt(t.expense)}<td>${__('Expense Tax')}</td>${amt(t.tax_expense)}</tr>
				<tr><td>${__('Invoice')}</td>${amt(t.invoice)}<td>${__('Invoice Tax')}</td>${amt(t.tax_invoice)}</tr>
				<tr><td>${__('Reimburse')}</td>${amt(t.reimburse)}<td colspan="2"></td></tr>
				<tr><td><b>${__('Margin')}</b></td>
					<td class="num ${(t.margin || 0) >= 0 ? 'pl-margin-pos' : 'pl-margin-neg'}">
						<b>${_pls_cur(t.margin, c)}${pct}</b></td>
					<td colspan="2"></td></tr>
			</tbody></table></div>`;
}

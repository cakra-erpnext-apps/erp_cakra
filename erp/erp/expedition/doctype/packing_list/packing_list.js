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
		frm.refresh_field('routes');
		cmi_pl_route_render(frm);
	}).catch(() => {
		if (w) w.chain.html(`<div class="text-danger">${__('Gagal memuat route.')}</div>`);
	});
}

function cmi_pl_route_chain($wrapper, points) {
	if (!points.length) {
		$wrapper.html(`<div class="text-muted">${__('Belum ada route terisi. Pilih Est Customer, atau isi sendiri di bawah.')}</div>`);
		return;
	}
	const chips = points.map((p) => {
		// Titik tanpa koordinat tetap ditampilkan supaya urutannya utuh, tapi diredupkan.
		const mapped = p.lat && p.lon;
		const hint = mapped ? '' : ` title="${__('Titik ini belum punya koordinat')}"`;
		return `<span class="border rounded ${mapped ? '' : 'text-muted'}" style="padding:2px 8px"${hint}>${p.text}. ${frappe.utils.escape_html(p.label)}</span>`;
	}).join('<span class="text-muted mx-1">&rarr;</span>');
	$wrapper.html(`<div class="d-flex flex-wrap align-items-center mb-3" style="gap:4px">${chips}</div>`);
}

// Pin digambar sama seperti MiniMap.vue di CRM: bulatan biru bernomor.
function cmi_pl_pin(text) {
	return L.divIcon({
		className: '',
		html: '<div style="background:#2563eb;color:#fff;border:2px solid #fff;border-radius:9999px;' +
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
		L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
			attribution: '&copy; OpenStreetMap, &copy; CARTO', subdomains: 'abcd', maxZoom: 20,
		}).addTo(frm._pl_map);
		frm._pl_layer = L.layerGroup().addTo(frm._pl_map);
	}
	frm._pl_layer.clearLayers();
	const latlngs = ok.map((p) => [p.lat, p.lon]);
	L.polyline(latlngs, { color: '#2563eb', weight: 3 }).addTo(frm._pl_layer);
	ok.forEach((p, i) => {
		L.marker(latlngs[i], { icon: cmi_pl_pin(p.text) }).bindTooltip(p.label).addTo(frm._pl_layer);
	});
	frm._pl_map.fitBounds(L.latLngBounds(latlngs).pad(0.2), { maxZoom: 13 });
	// Peta yang digambar saat wadahnya belum punya tinggi akan tampil abu-abu.
	setTimeout(() => frm._pl_map && frm._pl_map.invalidateSize(), 100);
}

// Grid route diubah tangan -> rantai & peta ikut, tanpa menyentuh server.
frappe.ui.form.on('Packing List Route', {
	location: cmi_pl_route_render,
	routes_move: cmi_pl_route_render,
});

// Header section Estimation and Customer -> kolom senama di tiap baris Items.
// Nilai ditulis langsung ke objek barisnya lalu grid di-refresh SEKALI: lewat
// frappe.model.set_value, 100 baris x 4 kolom = 400 kali render ulang grid.
const CMI_PL_SPREAD = ['customer', 'estimation', 'agent', 'agent_estimation'];

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
		frm.set_query('estimation', 'items', () => ({ filters: { purpose: 'Customer', disabled: 0 } }));
		frm.set_query('agent_estimation', 'items', () => ({ filters: { purpose: 'Agent', disabled: 0 } }));
		frm.set_query('customer', 'items', () => ({ filters: { disabled: 0 } }));
		frm.set_query('agent', 'items', () => ({ filters: { customer_group: 'Agent', disabled: 0 } }));

		// Header (section Estimation and Customer): estimation dibatasi ke pihak yang
		// sudah dipilih -- purpose yang cocok, sudah di-approve, dan customer_id-nya sama.
		// Est-nya read_only sampai pihaknya diisi (read_only_depends_on di doctype).
		// SEMENTARA: saringan "sudah di-approve" dilepas. Field req_approval/approved_by
		// dihapus dari doctype CRM Estimation (rombakan yang belum di-commit), jadi
		// saringan itu membuat daftarnya selalu kosong. Pasang lagi begitu penanda
		// approve yang baru diputuskan.
		const est_query = (purpose, party) => () => ({
			filters: { purpose, disabled: 0, customer_id: party() },
		});
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
	// refresh HANYA menggambar ulang, tidak menyemai: dokumen lama yang route-nya
	// sudah disunting tangan tidak boleh ditimpa hanya karena formnya dibuka.
	routes_add: cmi_pl_route_render,
	routes_remove: cmi_pl_route_render,
	// Baris yang ditambah belakangan ikut mewarisi isian header.
	items_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		CMI_PL_SPREAD.forEach((f) => { row[f] = frm.doc[f] || null; });
		frm.refresh_field('items');
	},
	refresh(frm) {
		window.cmi_load_assistant(frm);
		window.cmi_cost_center_query(frm);
		cmi_pl_route_render(frm);
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Invoice'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_INVOICE)).addClass('btn-primary');
			frm.add_custom_button(__('Create Expense Note'), () => window.cmi_create_from_bl(frm, window.CMI_MAKE_EXPENSE));
		}
	},
});

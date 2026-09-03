const DO_ROUTE_FIELDS = ['route_1', 'route_2', 'route_3', 'route_4', 'route_5', 'route_6', 'route_7', 'route_8'];

frappe.ui.form.on('Dispatch Order', {
	refresh(frm) {
		// Baris item mengikuti Packing List — tidak boleh tambah/hapus manual.
		frm.set_df_property('items', 'cannot_add_rows', true);
		frm.set_df_property('items', 'cannot_delete_rows', true);
		// semua isian pindah ke modal ritase; grid Items murni tampilan hasil turunannya
		frm.set_df_property('items', 'read_only', 1);
		if (!frm.is_new()) {
			// Share: link tracking publik untuk customer (tanpa login, hanya lewat link)
			const share_dialog = (url, judul) => {
				const d = new frappe.ui.Dialog({
					title: judul || __('Link Tracking Customer'),
					fields: [
						{ fieldtype: 'HTML', options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">Bisa dibuka tanpa login. Link tertutup sendiri saat semua ATA terisi, atau saat kamu tekan Stop Sharing.</div>` },
						{ fieldtype: 'Small Text', fieldname: 'url', label: __('Share URL'), default: url, read_only: 1 },
					],
					primary_action_label: __('Salin'),
					primary_action: () => {
						navigator.clipboard.writeText(url);
						frappe.show_alert({ message: __('Link tersalin'), indicator: 'green' });
						d.hide();
					},
				});
				d.show();
			};

			frm.add_custom_button(__('Share To Customer'), () =>
				frappe.call({
					method: 'erp.fleet.customer_track.share',
					args: { dispatch_order: frm.doc.name },
					freeze: true,
					callback: (r) => {
						share_dialog(r.message.url);
						frm.refresh();
					},
				})
			);

			// tombol Stop Sharing hanya muncul kalau link-nya memang sedang aktif
			frappe.call({
				method: 'erp.fleet.customer_track.share_status',
				args: { dispatch_order: frm.doc.name },
				callback: (r) => {
					const st = r.message || {};
					if (!st.name || !st.enabled) return;
					frm.add_custom_button(__('Stop Sharing'), () =>
						frappe.confirm(
							__('Hentikan sharing? Link yang sudah dikirim ke customer langsung tidak bisa dibuka.'),
							() =>
								frappe.call({
									method: 'erp.fleet.customer_track.stop_share',
									args: { dispatch_order: frm.doc.name },
									freeze: true,
									callback: (res) => {
										frappe.show_alert({ message: res.message.message, indicator: 'orange' });
										frm.refresh();
									},
								})
						)
					);
				},
			});

			frm.add_custom_button(__('Assign'), () => {
				const run = () =>
					frm.call('assign').then((r) => {
						const m = r.message || {};
						let msg = __('{0} item di-assign', [m.assigned]);
						if (m.missing && m.missing.length) msg += '. ' + __('Belum lengkap: {0}', [m.missing.join(', ')]);
						frappe.show_alert({ message: msg, indicator: 'green' });
						frm.reload_doc();
					});
				frm.is_dirty() ? frm.save().then(run) : run();
			});
		}
		render_route_map(frm);
		render_trip_matrix(frm);
		render_trip_list(frm);
	},
	onload(frm) {
		load_absen(frm);
		frm.set_query('driver', 'items', () => absen_filter(frm));
	},
	// isi/ganti salah satu titik -> matriks & pin di map langsung ikut
	...Object.fromEntries(
		DO_ROUTE_FIELDS.map((f) => [
			f,
			(frm) => {
				render_route_map(frm);
				render_trip_matrix(frm);
			},
		])
	),
});

frappe.ui.form.on('Dispatch Order Item', {
	vehicle(frm) {
		render_route_map(frm);
	},
	// nopol menyusul driver-nya (nilai dari absen/check-in hari ini) — tetap boleh diganti manual
	driver(frm, cdt, cdn) {
		const v = (frm._absen || {})[locals[cdt][cdn].driver];
		if (v) frappe.model.set_value(cdt, cdn, 'vehicle', v);
	},
});

// Driver yang boleh dipilih (aturan lengkapnya di available_drivers, sisi server):
// sudah check in hari ini, branch-nya sama dengan DPO, dan job sebelumnya sudah selesai.
// Peta driver -> nopol check-in hari ini dipakai juga untuk mengisi Vehicle otomatis.
function load_absen(frm) {
	const ambil = (busy) =>
		frappe.call('erp.fleet.doctype.dispatch_order.dispatch_order.available_drivers', {
			branch: frm.doc.branch,
			include_busy: busy,
		});
	// _absen = yang benar-benar siap; _absen_combo = ditambah yang sedang menarik container
	// lain, dipakai saat centang Combo dinyalakan
	return Promise.all([ambil(0), ambil(1)]).then(([a, b]) => {
		frm._absen = a.message || {};
		frm._absen_combo = b.message || {};
	});
}

// peta yang dipakai mengikuti centang Combo di dialog yang sedang terbuka
const peta_absen = (frm) =>
	(cur_dialog && cur_dialog.get_value && cur_dialog.get_value('combo') ? frm._absen_combo : frm._absen) || {};

const absen_filter = (frm) => ({ filters: { name: ['in', Object.keys(peta_absen(frm))] } });

// Nopol yang boleh dipilih = nopol yang DIPILIH SENDIRI oleh driver saat check-in hari ini,
// dan hanya dari driver yang berstatus siap (lolos available_drivers). Nopol lain tidak
// muncul walau ada di master Vehicle.
const nopol_filter = (frm) => ({
	filters: { name: ['in', [...new Set(Object.values(peta_absen(frm)).filter(Boolean))]] },
});

function fill_vehicle(frm, d) {
	const v = d && peta_absen(frm)[d.get_value('driver')];
	if (v) d.set_value('vehicle', v);
}

// Ikon truk driver (statis, tanpa rotasi arah). Label melayang di atas ikon, posisinya
// absolute supaya titik jangkar truk tidak bergeser sama sekali.
function truck_icon(label) {
	const tag = label
		? `<div style="position:absolute;bottom:48px;left:50%;transform:translateX(-50%);white-space:nowrap;
			font-size:11px;font-weight:600;color:#111;background:rgba(255,255,255,.92);border:1px solid rgba(0,0,0,.18);
			border-radius:4px;padding:1px 6px;box-shadow:0 1px 3px rgba(0,0,0,.3);">${frappe.utils.escape_html(label)}</div>`
		: '';
	return L.divIcon({
		className: '',
		html: `${tag}<img src="/assets/erp/images/truck.png" style="width:50px;height:50px;filter:drop-shadow(0 1px 3px rgba(0,0,0,.4));">`,
		iconSize: [50, 50],
		iconAnchor: [25, 25],
	});
}

// Tile peta bergaya Google Maps (roadmap). lyrs: m = jalan, s = satelit, y = hybrid.
function do_tiles() {
	return L.tileLayer('https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
		subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
		maxZoom: 20,
		attribution: 'Google Maps',
	});
}

// peta code -> title utk label matriks (Herman Su.. - Truck Test 01)
function get_titles(frm) {
	if (!frm._do_titles) {
		const m = (dt) => frappe.db.get_list(dt, { fields: ['name', 'title'], limit: 0 });
		frm._do_titles = Promise.all([m('Driver'), m('Vehicle')]).then(([d, v]) => ({
			driver: Object.fromEntries(d.map((x) => [x.name, x.title || x.name])),
			vehicle: Object.fromEntries(v.map((x) => [x.name, x.title || x.name])),
		}));
	}
	return frm._do_titles;
}

function get_masters(frm) {
	if (!frm._do_masters) {
		const master = (flag) =>
			frappe.db.get_list('Fleet Location', {
				fields: ['name'],
				filters: { disabled: 0, [flag]: 1 },
				limit: 0,
				order_by: 'name',
			});
		frm._do_masters = Promise.all([master('is_route'), master('is_depo')]);
	}
	return frm._do_masters;
}

// Matriks trip log (section Route): kolom = step (Assign, Accept, 8 slot titik, Lanjut Job,
// Menuju Garasi), baris = driver per item. Jenis (None/Route/Depo) dan titiknya DIPILIH DI
// HEADER; jenis None = kolom kosong (input waktu disembunyikan). Sel = IN/OUT + durasi.
// Data slot di route_type_n/route_n, waktu di child trip_log (tabDispatch Order Route).
function render_trip_matrix(frm) {
	const field = frm.get_field('trip_html');
	if (!field) return;
	const items = frm.doc.items || [];
	if (!items.length) {
		field.$wrapper.html(`<div class="text-muted">${__('Belum ada item.')}</div>`);
		return;
	}
	Promise.all([get_masters(frm), get_titles(frm)]).then(([[routes, depos], titles]) => {
		const esc = frappe.utils.escape_html;
		const rows = frm.doc.trip_log || [];
		// grup per (item, trip): 1 baris matriks = 1 ritase
		const by_key = {};
		rows.forEach((r) => {
			const k = `${r.dpo_item}|${r.trip || 1}`;
			(by_key[k] = by_key[k] || []).push(r);
		});
		const trips_of = (it) =>
			[...new Set(rows.filter((r) => r.dpo_item === it.name).map((r) => r.trip || 1))].sort((a, b) => a - b);
		const find = (it, trip, pred) => (by_key[`${it.name}|${trip}`] || []).find(pred);
		const dtVal = (v) => (v ? String(v).slice(0, 16).replace(' ', 'T') : '');
		// ATD/ATA ritase: tanggal saja, ditampilkan dd-MM-yyyy
		const tgl = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : '-');
		const durasi = (start, end) => {
			if (!start || !end) return '';
			const m = Math.round((new Date(String(end).replace(' ', 'T')) - new Date(String(start).replace(' ', 'T'))) / 60000);
			if (isNaN(m) || m < 0) return '';
			return (m >= 60 ? Math.floor(m / 60) + 'j ' : '') + (m % 60) + 'm';
		};
		// Halaman matriks dipotong per CONTAINER, bukan per baris ritase — sel Container
		// di-merge lintas ritase, jadi memotong di tengahnya akan merusak rowspan-nya.
		const mstate = (frm._mtx = frm._mtx || { q: '', page: 0, key: 'container', dir: 1 });
		const kandidat = items.map((it) => {
			const trips = trips_of(it);
			const teks = trips
				.map((tr) => {
					const g = by_key[`${it.name}|${tr}`] || [];
					const d0 = (g[0] && g[0].driver) || it.driver || '';
					const v0 = (g[0] && g[0].vehicle) || it.vehicle || '';
					return [tr, titles.driver[d0] || d0, titles.vehicle[v0] || v0].join(' ');
				})
				.join(' ');
			const drv0 = it.driver || '';
			return {
				it,
				cari: [it.container_no, it.dpo_no, teks].join(' ').toLowerCase(),
				urut: { container: it.container_no || '', driver: titles.driver[drv0] || drv0 },
			};
		});
		const { total: mtotal, page: mpage } = slice_rows(kandidat, mstate);
		const dl = (dt, list) =>
			`<datalist id="do-dl-${dt}">${list.map((r) => `<option value="${esc(r.name)}">`).join('')}</datalist>`;

		const time_cell = (c, has_end) => {
			if (!c) return '<td><span class="text-muted">-</span></td>';
			const dur = has_end ? durasi(c.start, c.end) : '';
			return `<td><div class="do-cell">
				<span class="do-trip-lbl">IN</span><input type="datetime-local" class="form-control do-trip-t" data-cdn="${c.name}" data-f="start" value="${dtVal(c.start)}">
				${has_end ? `<span class="do-trip-lbl">OUT</span><input type="datetime-local" class="form-control do-trip-t" data-cdn="${c.name}" data-f="end" value="${dtVal(c.end)}">` : ''}
			</div>${dur ? `<div class="do-trip-dur">${dur}</div>` : ''}</td>`;
		};

		const slot = (n) => ({
			jenis: frm.doc[`route_type_${n}`] || '',
			point: frm.doc[`route_${n}`] || '',
			langsir: !!frm.doc[`route_langsir_${n}`],
			origin: !!frm.doc[`route_origin_${n}`],
			dest: !!frm.doc[`route_dest_${n}`],
		});

		let html = `
		<style>
			.do-trip { overflow-x: auto; }
			.do-trip table { width: max-content; min-width: 100%; margin-bottom: 0; }
			.do-trip th, .do-trip td { white-space: nowrap; vertical-align: middle; padding: 4px 8px; text-align: center; }
			.do-trip th.do-trip-cont, .do-trip td.do-trip-cont { position: sticky; left: 0; width: 130px; min-width: 130px; background: var(--card-bg); z-index: 2; text-align: left; }
			.do-trip th.do-trip-driver, .do-trip td.do-trip-driver { position: sticky; left: 130px; background: var(--card-bg); z-index: 1; text-align: left; }
			.do-trip .do-cell { display: grid; grid-template-columns: 26px 168px; gap: 2px 4px; align-items: center; }
			.do-trip .do-trip-lbl { font-size: 10px; color: var(--text-muted); text-align: right; }
			.do-trip input.do-trip-t { width: 168px; height: 26px; font-size: 12px; padding: 2px 6px; }
			.do-trip .do-trip-dur { font-size: 11px; font-weight: 600; color: var(--text-muted); margin-top: 2px; }
			.do-trip select.do-head-jenis, .do-trip input.do-head-point { height: 26px; font-size: 12px; padding: 2px 6px; width: 130px; display: inline-block; }
			/* OR / DS / LG: satu baris di bawah input titik, singkatannya dijelaskan di legenda atas tabel */
			.do-trip .do-head-flags { display: flex; gap: 10px; justify-content: center; margin-top: 3px; }
			.do-trip .do-head-flags label { display: flex; align-items: center; gap: 3px; font-size: 10px;
				font-weight: 600; margin: 0; cursor: pointer; }
			.do-trip .do-head-flags input { margin: 0; }
			${toolbar_css()}
			.do-legend { font-size: 11px; color: var(--text-muted); margin: 0 0 6px; }
			.do-legend b { font-weight: 600; color: var(--text-color); }
			/* tombol menu baris: dikasih kotak sendiri supaya tidak tenggelam di warna baris */
			.do-trip .do-row-menu { width: 22px; height: 22px; padding: 0; flex: 0 0 22px;
				border: none; border-radius: 50%; background: #1d4ed8; color: #fff;
				--icon-stroke: #fff; --icon-fill: #fff;
				display: inline-flex; align-items: center; justify-content: center; line-height: 0; }
			.do-trip .do-row-menu svg, .do-trip .do-row-menu svg * { fill: #fff; stroke: #fff; }
			.do-trip .do-row-menu:hover { background: #1e40af; }
			.do-trip .do-trip-name { display: block; max-width: 185px; overflow: hidden; text-overflow: ellipsis; }
			.do-trip tr.do-row-alt td { background: rgba(128,128,128,.14); }
			/* kolom sticky wajib OPAQUE: dasar solid + lapisan abu, biar isi di belakang tak tembus saat scroll */
			.do-trip td.do-trip-driver, .do-trip th.do-trip-driver,
			.do-trip td.do-trip-cont, .do-trip th.do-trip-cont { background: var(--card-bg); }
			.do-trip tr.do-row-alt td.do-trip-driver, .do-trip tr.do-row-alt td.do-trip-cont {
				background: linear-gradient(rgba(128,128,128,.14), rgba(128,128,128,.14)), var(--card-bg);
			}
		</style>
		${dl('Route', routes)}${dl('Depo', depos)}
		<div class="do-legend"><b>OR</b> = Origin &nbsp; <b>DS</b> = Destination &nbsp; <b>LG</b> = Langsir</div>
		${toolbar_html(mstate, mtotal, '')}
		<div class="do-trip"><table class="table table-bordered table-sm">`;

		// header baris 1: label event + pilihan jenis per slot
		const mpanah = (k) => (mstate.key === k ? (mstate.dir > 0 ? ' ▲' : ' ▼') : '');
		html += `<thead><tr><th class="do-trip-cont do-sort" data-key="container">Container${mpanah('container')}</th>
			<th class="do-trip-driver do-sort" data-key="driver">Driver${mpanah('driver')}</th><th>Trip</th><th>Vehicle</th><th>ATD</th><th>ATA</th><th>Assign</th><th>Accept Job</th>`;
		for (let n = 1; n <= 8; n++) {
			const s = slot(n);
			const sel = s.jenis || (s.point ? 'Route' : 'None');
			html += `<th><select class="form-control do-head-jenis" data-n="${n}">
				${['None', 'Route', 'Depo'].map((o) => `<option value="${o}"${o === sel ? ' selected' : ''}>${o}</option>`).join('')}
			</select></th>`;
		}
		html += `<th>Lanjut Job</th><th>Menuju Garasi</th></tr>`;

		// header baris 2: input titik per slot
		html += `<tr><th class="do-trip-cont"></th><th class="do-trip-driver"></th><th></th><th></th><th></th><th></th><th></th><th></th>`;
		for (let n = 1; n <= 8; n++) {
			const s = slot(n);
			const none = !s.jenis && !s.point;
			// centang Langsir = titik ini masuk segmen yang diulang ritase langsir (trip 2+)
			html += `<th>${
				none
					? ''
					: `<input type="text" class="form-control do-head-point" data-n="${n}" list="do-dl-${s.jenis || 'Route'}" value="${esc(s.point)}" placeholder="${__('Titik')} ${n}" autocomplete="off">
						<div class="do-head-flags">
							<label title="${__('Origin')}">
								<input type="checkbox" class="do-head-origin" data-n="${n}"${s.origin ? ' checked' : ''}> OR
							</label>
							<label title="${__('Destination')}">
								<input type="checkbox" class="do-head-dest" data-n="${n}"${s.dest ? ' checked' : ''}> DS
							</label>
							<label title="${__('Langsir')}">
								<input type="checkbox" class="do-head-langsir" data-n="${n}"${s.langsir ? ' checked' : ''}> LG
							</label>
						</div>`
			}</th>`;
		}
		html += `<th></th><th></th></tr></thead><tbody>`;

		let item_i = 0;
		for (const { it } of mpage) {
			// selang-seling warna PER CONTAINER: semua trip container yang sama, warnanya sama
			const alt = item_i++ % 2 === 1 ? ' class="do-row-alt"' : '';
			const trips = trips_of(it);
			// item belum assigned -> 1 baris kosong; sudah -> 1 baris per trip
			const row_list = trips.length ? trips : [null];
			let first_row = true;
			for (const trip of row_list) {
				const g = trip ? by_key[`${it.name}|${trip}`] : null;
				const drv = (g && g[0].driver) || it.driver || '';
				const is_last = trip && trip === trips[trips.length - 1];
				const drv_t = drv ? titles.driver[drv] || drv : '-'; // belum ada driver -> "-"
				const veh = (g && g[0].vehicle) || it.vehicle || '';
				const veh_t = veh ? titles.vehicle[veh] || veh : '-'; // nopol trip ini, bukan nopol item terakhir
				const can_add = is_last || (!trips.length && it.assigned);
				// container di-merge: satu sel untuk semua trip milik container itu
				const cont_cell = first_row
					? `<td class="do-trip-cont" rowspan="${row_list.length}">${esc(it.container_no || '')}</td>`
					: '';
				first_row = false;
				// satu tombol titik-tiga -> menu teks (Tambah Trip / Edit / Delete / Playback)
				const menu_btn = ''; // aksi trip pindah ke tombol grid Items
				html += `<tr${alt}>${cont_cell}<td class="do-trip-driver">
					<div style="display:flex;gap:3px;align-items:center;">
						${menu_btn}
						<span class="do-trip-name" title="${esc(drv_t)}"><b>${esc(drv_t)}</b></span>
					</div></td>
					<td><b>${trip || ''}</b></td>
					<td><span class="do-trip-name" title="${esc(veh_t)}">${esc(veh_t)}</span></td>
					<td>${esc(tgl(g && g[0].atd))}</td>
					<td>${esc(tgl(g && g[0].ata))}</td>`;
				html += time_cell(trip && find(it, trip, (r) => r.step_type === 'Assign'), false);
				html += time_cell(trip && find(it, trip, (r) => r.step_type === 'Accept Job'), false);
				for (let n = 1; n <= 8; n++) {
					const s = slot(n);
					if (!s.jenis && !s.point) {
						html += '<td></td>'; // None -> clean
					} else {
						html += time_cell(
							trip && s.point ? find(it, trip, (r) => r.step_type === 'Route' && r.point === s.point) : null,
							true
						);
					}
				}
				html += time_cell(trip && find(it, trip, (r) => r.step_type === 'Lanjut Job'), false);
				html += time_cell(trip && find(it, trip, (r) => r.step_type === 'Menuju Garasi'), true);
				html += '</tr>';
			}
		}
		html += '</tbody></table></div>';
		field.$wrapper.html(html);

		field.$wrapper.find('.do-head-jenis').on('change', function () {
			const n = $(this).data('n');
			const v = this.value;
			frm.set_value(`route_type_${n}`, v === 'None' ? '' : v);
			frm.set_value(`route_${n}`, '');
			render_route_map(frm);
			render_trip_matrix(frm);
		});
		field.$wrapper.find('.do-head-point').on('change', function () {
			frm.set_value(`route_${$(this).data('n')}`, this.value || '');
			render_route_map(frm);
			render_trip_matrix(frm);
		});
		// satu slot hanya boleh salah satu (Origin ATAU Destination), dan masing-masing hanya
		// boleh dipakai satu slot di seluruh rute
		field.$wrapper.find('.do-head-origin, .do-head-dest').on('change', function () {
			const is_dest = $(this).hasClass('do-head-dest');
			const fld = is_dest ? 'route_dest' : 'route_origin';
			const lawan = is_dest ? 'route_origin' : 'route_dest';
			const n = $(this).data('n');
			if (this.checked && frm.doc[`${lawan}_${n}`]) {
				this.checked = false;
				frappe.show_alert({
					message: __('Titik {0} sudah ditandai {1}. Lepas dulu centangnya.', [
						n,
						is_dest ? __('Origin') : __('Destination'),
					]),
					indicator: 'orange',
				});
				return;
			}
			for (let i = 1; i <= 8; i++) {
				if (frm.doc[`${fld}_${i}`] && i !== n) frm.set_value(`${fld}_${i}`, 0);
			}
			frm.set_value(`${fld}_${n}`, this.checked ? 1 : 0);
			render_trip_matrix(frm);
		});

		field.$wrapper.find('.do-head-langsir').on('change', function () {
			frm.set_value(`route_langsir_${$(this).data('n')}`, this.checked ? 1 : 0);
			render_route_map(frm);
		});
		wire_toolbar(field.$wrapper, mstate, () => render_trip_matrix(frm));
		field.$wrapper.find('.do-trip-t').on('change', function () {
			let v = this.value || null;
			if (v) v = v.replace('T', ' ') + (v.length === 16 ? ':00' : '');
			frappe.model.set_value('Dispatch Order Route', $(this).data('cdn'), $(this).data('f'), v);
			render_trip_matrix(frm); // refresh durasi
		});
	});
}

// ---- Aksi ritase: dipanggil dari tabel Ritase di section Trip ----
// nilai bawaan dialog diambil dari baris trip-nya, bukan baris Items — nopol/driver
// tiap ritase bisa berbeda
function trip_row(frm, it, trip) {
	return (frm.doc.trip_log || []).find((t) => t.dpo_item === it.name && (t.trip || 1) === trip) || it;
}

function act_edit(frm, it, trip) {
	const g = trip_row(frm, it, trip);
	frappe.prompt(
		[
			{ fieldname: 'driver', fieldtype: 'Link', options: 'Driver', label: __('Driver'), default: g.driver || '',
				get_query: () => absen_filter(frm), change: () => fill_vehicle(frm, cur_dialog) },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'vehicle', fieldtype: 'Link', options: 'Vehicle', label: __('Vehicle'), default: g.vehicle || '',
				get_query: () => nopol_filter(frm) },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'chasis', fieldtype: 'Data', label: __('Chasis'), read_only: 1, default: g.chasis || '' },
			{ fieldtype: 'Section Break' },
			{ fieldname: 'atd', fieldtype: 'Date', label: __('ATD'), default: g.atd || '' },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'ata', fieldtype: 'Date', label: __('ATA'), default: g.ata || '' },
			{ fieldtype: 'Section Break' },
			// Combo: truk yang sedang menarik container lain boleh dipilih lagi, ASAL ATD-nya sama.
			// Sekali saja per driver — satu truk maksimal dua container.
			{ fieldname: 'combo', fieldtype: 'Check', label: __('Combo'), default: g.combo ? 1 : 0,
				read_only: g.combo ? 1 : 0,
				description: __('Satu truk membawa dua container. Driver yang sedang jalan ikut muncul, asalkan ATD-nya sama.'),
				change: () => {
					cur_dialog.set_value('driver', '');
					cur_dialog.set_value('vehicle', '');
				} },
		],
		(v) => {
			frm.call('edit_trip', { dpo_item: it.name, trip, driver: v.driver, vehicle: v.vehicle,
				chasis: v.chasis, atd: v.atd, ata: v.ata, combo_join: v.combo ? 1 : 0 }).then(() => {
				frappe.show_alert({ message: __('Trip {0} diubah', [trip]), indicator: 'green' });
				frm.reload_doc();
			});
		},
		__('Edit Trip {0} - {1}', [trip, it.container_no || '']),
		__('Simpan')
	);
}

function act_del(frm, it, trip) {
	frappe.confirm(__('Hapus Trip {0} ({1}) beserta semua catatan waktunya?', [trip, it.container_no || '']), () => {
		frm.call('delete_trip', { dpo_item: it.name, trip }).then(() => {
			frappe.show_alert({ message: __('Trip {0} dihapus', [trip]), indicator: 'orange' });
			frm.reload_doc();
		});
	});
}

function act_add(frm) {
	const pilihan = (frm.doc.items || []).filter((r) => r.container_no);
	if (!pilihan.length) return frappe.msgprint(__('Belum ada container di Items.'));
	const today = frappe.datetime.get_today();
	frappe.prompt(
		[
			// Satu container saja: Tambah Trip untuk langsir / kasus khusus. Combo dibuat
			// lewat centang Combo di Edit Trip, bukan di sini.
			// Autocomplete, bukan Select: containernya bisa puluhan jadi harus bisa diketik
			{ fieldname: 'dpo_item', fieldtype: 'Autocomplete', label: __('Container'), reqd: 1,
				options: pilihan.map((r) => ({ value: r.name, label: r.container_no })) },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'driver', fieldtype: 'Link', options: 'Driver', label: __('Driver'),
				get_query: () => absen_filter(frm), change: () => fill_vehicle(frm, cur_dialog) },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'vehicle', fieldtype: 'Link', options: 'Vehicle', label: __('Vehicle'),
				get_query: () => nopol_filter(frm) },
			{ fieldtype: 'Section Break' },
			{ fieldname: 'atd', fieldtype: 'Date', label: __('ATD'), reqd: 1, default: today },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'ata', fieldtype: 'Date', label: __('ATA') },
		],
		(v) => {
			const run = () =>
				frm
					.call('add_trip', {
						dpo_item: v.dpo_item,
						driver: v.driver, vehicle: v.vehicle, atd: v.atd, ata: v.ata,
					})
					.then((r) => {
						frappe.show_alert({ message: __('Trip {0} dibuat', [(r.message || {}).trip]), indicator: 'green' });
						frm.reload_doc();
					});
			frm.is_dirty() ? frm.save().then(run) : run();
		},
		__('Tambah Trip'),
		__('Buat')
	);
}


// ---- Toolbar bersama tabel Trip & matriks Route: 1 kotak cari + halaman 10 baris ----
const PER_PAGE = 10;

function toolbar_html(state, total, extra) {
	const dari = total ? state.page * PER_PAGE + 1 : 0;
	const sampai = Math.min((state.page + 1) * PER_PAGE, total);
	return `<div class="do-tb">
		${extra || ''}
		<input type="text" class="form-control input-xs do-tb-q" style="width:230px"
			placeholder="${__('Cari semua kolom')}" value="${frappe.utils.escape_html(state.q || '')}">
		<span class="do-tb-info">${dari}-${sampai} ${__('dari')} ${total}</span>
		<button class="btn btn-default btn-xs do-tb-prev"${state.page ? '' : ' disabled'}>&#8249;</button>
		<button class="btn btn-default btn-xs do-tb-next"${sampai >= total ? ' disabled' : ''}>&#8250;</button>
	</div>`;
}

function toolbar_css() {
	return `.do-tb { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
		.do-tb-info { font-size: 11px; color: var(--text-muted); margin-left: auto; }
		th.do-sort { cursor: pointer; user-select: none; }
		th.do-sort:hover { text-decoration: underline; }`;
}

// Dipasang SETELAH html digambar. `repaint` menggambar ulang dengan state terbaru.
function wire_toolbar($wrapper, state, repaint) {
	$wrapper.find('.do-tb-q').on('change keydown', function (e) {
		if (e.type === 'keydown' && e.key !== 'Enter') return;
		state.q = String(this.value || '').trim().toLowerCase();
		state.page = 0;
		repaint();
	});
	$wrapper.find('.do-tb-prev').on('click', () => {
		state.page = Math.max(0, state.page - 1);
		repaint();
	});
	$wrapper.find('.do-tb-next').on('click', () => {
		state.page += 1;
		repaint();
	});
	$wrapper.find('th.do-sort').on('click', function () {
		const k = $(this).data('key');
		state.dir = state.key === k ? -state.dir : 1;
		state.key = k;
		state.page = 0;
		repaint();
	});
}

// urut + saring + potong per halaman; `baris` = objek yang punya .cari dan .urut
function slice_rows(baris, state) {
	let out = state.q ? baris.filter((r) => r.cari.includes(state.q)) : baris.slice();
	out.sort((a, b) => {
		const x = a.urut[state.key],
			y = b.urut[state.key];
		if (x === y) return 0;
		return (x > y ? 1 : -1) * (state.dir || 1);
	});
	const total = out.length;
	if (state.page * PER_PAGE >= total) state.page = Math.max(0, Math.ceil(total / PER_PAGE) - 1);
	return { total, page: out.slice(state.page * PER_PAGE, (state.page + 1) * PER_PAGE) };
}

// Tabel Ritase di section Trip. TAMPILAN saja yang dibaca dari trip_log — Dispatch Order
// Item tetap 1:1 dengan Packing List Item, tidak ada baris yang ditambah.
function render_trip_list(frm) {
	const field = frm.get_field('trip_list_html');
	if (!field) return;
	// Digambar DULU dengan kode apa adanya supaya tombol Tambah Trip dan pesan kosong selalu
	// muncul, baru dicat ulang begitu peta nama datang. Kalau permintaan nama gagal, tabelnya
	// tetap ada — sebelumnya seluruh tabel ikut hilang tanpa jejak.
	const kosong = { driver: {}, vehicle: {} };
	paint_trip_list(frm, field, kosong);
	get_titles(frm)
		.then((titles) => paint_trip_list(frm, field, titles))
		.catch(() => {});
}

function paint_trip_list(frm, field, titles) {
	const esc = frappe.utils.escape_html;
	const state = (frm._rit = frm._rit || { q: '', page: 0, key: 'container', dir: 1 });
	const nama = (dt, v) => (v ? titles[dt][v] || v : '-');
	const item = (n) => (frm.doc.items || []).find((r) => r.name === n);
	const tgl = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : '-');
	// "Assign Date" = waktu step Assign diberi stempel, yaitu saat ritase ini benar-benar
	// diserahkan (driver + nopol terisi), bukan saat barisnya dibuat
	const jam = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 16)) : '-');

	const semua = (frm.doc.trip_log || []).filter((t) => t.step === 1);
	const anggota = (c) =>
		semua.filter((t) => t.combo === c).map((t) => (item(t.dpo_item) || {}).container_no).filter(Boolean);
	const baris = semua.map((t) => {
		const it = item(t.dpo_item) || {};
		const b = {
			t,
			it,
			container: it.container_no || '',
			tms: it.container_tms || '',
			trip: t.trip || 1,
			job: t.start || '',
			driver: nama('driver', t.driver),
			vehicle: nama('vehicle', t.vehicle),
			atd: t.atd || '',
			ata: t.ata || '',
		};
		b.urut = { container: b.container, tms: b.tms, trip: b.trip, job: b.job, driver: b.driver,
			vehicle: b.vehicle, atd: b.atd, ata: b.ata };
		b.cari = [b.container, b.tms, b.trip, b.job, b.driver, b.vehicle, b.atd, b.ata, t.combo || '']
			.join(' ').toLowerCase();
		return b;
	});
	const { total, page } = slice_rows(baris, state);

	// Nomor kontainer hasil konfirmasi sopir; merah kalau beda dengan nomor di Packing List
	const tms_sel = (b) => {
		if (!b.tms) return '';
		const beda = String(b.tms).toUpperCase() !== String(b.container).toUpperCase();
		const ket = b.it.container_tms_at ? jam(b.it.container_tms_at) : '';
		return beda
			? `<span style="color:#dc2626;font-weight:600" title="${__('Berbeda dari nomor di Packing List')} ${esc(ket)}">${esc(b.tms)}</span>`
			: `<span title="${esc(ket)}">${esc(b.tms)}</span>`;
	};
	const kombo = (c) =>
		`<span class="do-rit-combo" title="${__('Satu truk membawa')}: ${esc(anggota(c).join(', '))}">${__('Combo')}</span>`;
	const panah = (k) => (state.key === k ? (state.dir > 0 ? ' ▲' : ' ▼') : '');
	const th = (k, label) => `<th class="do-sort" data-key="${k}">${label}${panah(k)}</th>`;

	let html = `<style>
		${toolbar_css()}
		.do-rit { overflow-x: auto; }
		.do-rit table { width: 100%; border-collapse: collapse; }
		.do-rit th, .do-rit td { border: 1px solid var(--border-color); padding: 6px 10px; font-size: 13.5px; white-space: nowrap; }
		.do-rit th { background: var(--bg-light-gray, #f3f4f6); font-weight: 600; text-align: left; }
		.do-rit tbody tr { cursor: pointer; }
		.do-rit tbody tr:hover { background: var(--highlight-color, #eef2ff); }
		.do-rit td.do-rit-act { text-align: right; white-space: nowrap; }
		/* ikon aksi: bulat kecil, kliknya tidak ikut memicu modal ubah ritase */
		.do-rit .do-rit-btn { width: 26px; height: 26px; padding: 0; margin-left: 4px; border: 1px solid var(--border-color);
			border-radius: 50%; background: var(--bg-color); display: inline-flex; align-items: center; justify-content: center; }
		.do-rit .do-rit-btn:hover { border-color: #1d4ed8; }
		.do-rit .do-rit-empty { color: var(--text-muted); font-size: 13.5px; }
		.do-rit .do-rit-combo { margin-left: 6px; padding: 1px 7px; border-radius: 9px; font-size: 11px;
			font-weight: 600; background: #dbeafe; color: #1e40af; }
	</style>
	<div class="do-rit">
		${toolbar_html(state, total, `<button class="btn btn-default btn-xs do-rit-add">${frappe.utils.icon('add', 'sm')} ${__('Tambah Trip')}</button>`)}`;

	if (!page.length) {
		html += `<div class="do-rit-empty">${state.q ? __('Tidak ada ritase yang cocok.') : __('Belum ada ritase.')}</div></div>`;
	} else {
		html += `<table><thead><tr>${th('container', __('Container'))}${th('tms', __('TMS Container'))}${th('trip', __('Trip'))}
			${th('driver', __('Driver'))}${th('vehicle', __('Vehicle'))}${th('atd', __('ATD'))}
			${th('job', __('Assign Date'))}${th('ata', __('ATA'))}<th></th></tr></thead><tbody>`;
		for (const b of page) {
			html += `<tr data-item="${esc(b.t.dpo_item)}" data-trip="${b.trip}" title="${__('Klik baris untuk mengubah ritase')}">
				<td>${esc(b.container || '-')}${b.t.combo ? kombo(b.t.combo) : ''}</td>
				<td>${tms_sel(b)}</td>
				<td><b>${b.trip}</b></td>
				<td>${esc(b.driver)}</td>
				<td>${esc(b.vehicle)}</td>
				<td>${esc(tgl(b.atd))}</td>
				<td>${esc(jam(b.job))}</td>
				<td>${esc(tgl(b.ata))}</td>
				<td class="do-rit-act">
					<button class="btn do-rit-btn do-rit-play" title="${__('Playback')}">${frappe.utils.icon('play', 'sm')}</button>
					<button class="btn do-rit-btn do-rit-del" title="${__('Hapus')}">${frappe.utils.icon('delete', 'sm')}</button>
				</td></tr>`;
		}
		html += '</tbody></table></div>';
	}
	field.$wrapper.html(html);

	const ulang = () => paint_trip_list(frm, field, titles);
	wire_toolbar(field.$wrapper, state, ulang);
	const sasaran = (el) => {
		const $r = $(el).closest('tr');
		return { it: item($r.data('item')), trip: Number($r.data('trip')) || 1 };
	};
	field.$wrapper.find('.do-rit-add').on('click', () => act_add(frm));
	field.$wrapper.find('.do-rit-play').on('click', function (e) {
		e.stopPropagation(); // jangan ikut membuka modal ubah ritase
		const t = sasaran(this);
		t.it && show_playback(t.it, t.trip);
	});
	field.$wrapper.find('.do-rit-del').on('click', function (e) {
		e.stopPropagation();
		const t = sasaran(this);
		t.it && act_del(frm, t.it, t.trip);
	});
	// klik baris = ubah ritase (Driver | Vehicle / ATD | ATA), modal yang sama dengan Tambah Trip
	field.$wrapper.find('tbody tr').on('click', function () {
		const t = sasaran(this);
		t.it && act_edit(frm, t.it, t.trip);
	});
}

// Playback jejak GPS satu job dari history.route_history: garis rute + marker jalan
// mengikuti urutan waktu rekaman (start hijau S, end merah E).
function show_playback(it, trip) {
	trip = trip || 1;
	frappe
		.call('erp.fleet.doctype.dispatch_order.dispatch_order.get_route_history', { dpo_item: it.name, trip })
		.then((r) => {
			const pts = r.message || [];
			if (!pts.length) {
				frappe.msgprint(__('Belum ada history perjalanan trip {0} untuk {1}.', [trip, it.driver || it.container_no]));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __('Playback {0} ({1}) Trip {2}', [it.driver || '', it.container_no || '', trip]),
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'map' }],
			});
			d.show();
			setTimeout(() => {
				const wrap = d.get_field('map').$wrapper;
				wrap.html(`
					<div class="do-play-map border rounded" style="height:480px"></div>
					<div style="margin-top:8px;display:flex;gap:10px;align-items:center;">
						<button class="btn btn-sm btn-primary do-play">${__('Play')}</button>
						<input type="range" class="do-play-slider" min="0" max="${pts.length - 1}" value="0" style="flex:1">
						<span class="do-play-info text-muted" style="min-width:220px"></span>
					</div>`);
				const map = L.map(wrap.find('.do-play-map')[0], { attributionControl: false }).setView([-2.5, 118], 5);
				do_tiles().addTo(map);
				const latlngs = pts.map((p) => [p.latitude, p.longitude]);
				const line = L.polyline(latlngs, { color: '#1d4ed8', weight: 3, opacity: 0.6 }).addTo(map);
				const badge = (txt, bg) =>
					L.divIcon({
						className: '',
						html: `<div style="width:22px;height:22px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;">${txt}</div>`,
						iconSize: [22, 22],
						iconAnchor: [11, 11],
					});
				L.marker(latlngs[0], { icon: badge('S', '#16a34a') }).addTo(map).bindTooltip(__('Start: {0}', [pts[0].recorded_at]));
				L.marker(latlngs[latlngs.length - 1], { icon: badge('E', '#dc2626') })
					.addTo(map)
					.bindTooltip(__('End: {0}', [pts[pts.length - 1].recorded_at]));
				const mover = L.marker(latlngs[0], {
					zIndexOffset: 1000,
					icon: truck_icon(),
				}).addTo(map);
				map.fitBounds(line.getBounds().pad(0.2));
				setTimeout(() => map.invalidateSize(), 300);

				const $info = wrap.find('.do-play-info');
				const $slider = wrap.find('.do-play-slider');
				const $btn = wrap.find('.do-play');
				let idx = 0,
					timer = null;
				const show = (i) => {
					idx = i;
					mover.setLatLng(latlngs[i]);
					$slider.val(i);
					$info.text(`${i + 1}/${pts.length}  ${pts[i].recorded_at}`);
				};
				const stop = () => {
					if (timer) clearInterval(timer);
					timer = null;
					$btn.text(__('Play'));
				};
				$btn.on('click', () => {
					if (timer) return stop();
					if (idx >= pts.length - 1) idx = 0;
					$btn.text(__('Pause'));
					timer = setInterval(() => {
						if (idx >= pts.length - 1) return stop();
						show(idx + 1);
					}, 150);
				});
				$slider.on('input', function () {
					stop();
					show(Number(this.value));
				});
				show(0);
				d.$wrapper.on('hidden.bs.modal', () => {
					stop();
					map.remove();
				});
			}, 300);
		});
}

// Peta (section Map): pin bernomor sesuai urutan slot (1 = start hijau; Route biru, Depo ungu),
// garis putus-putus + panah arah antar titik, pin oranye = posisi vehicle dari GPS Vehicle.
function render_route_map(frm) {
	const field = frm.get_field('map_html');
	if (!field) return;

	const stops = DO_ROUTE_FIELDS.map((f, i) => ({
		dt: frm.doc[`route_type_${i + 1}`] || 'Route',
		name: frm.doc[f],
		langsir: !!frm.doc[`route_langsir_${i + 1}`],
	})).filter((s) => s.name);
	const vehicles = [...new Set((frm.doc.items || []).map((r) => r.vehicle).filter(Boolean))];

	const stop_names = [...new Set(stops.map((s) => s.name))];
	Promise.all([
		stop_names.length
			? frappe.db.get_list('Fleet Location', {
					filters: { name: ['in', stop_names] },
					fields: ['name', 'latitude', 'longitude'],
					limit: 0,
			  })
			: [],
		vehicles.length
			? frappe.db.get_list('GPS Vehicle', {
					filters: { vehicle: ['in', vehicles] },
					fields: ['vehicle', 'latitude', 'longitude'],
					limit: 0,
			  })
			: [],
		get_titles(frm),
	]).then(([loc_pts, veh_pts, titles]) => {
		// nopol -> driver yang memakainya di DPO ini (untuk label di atas ikon truk)
		const drv_of = Object.fromEntries(
			(frm.doc.items || []).filter((r) => r.vehicle && r.driver).map((r) => [r.vehicle, r.driver])
		);
		if (frm._do_map) {
			frm._do_map.remove();
			frm._do_map = null;
		}
		// flowchart read-only urutan route di atas map (data = slot yang di-set di header matriks)
		const esc = frappe.utils.escape_html;
		const chip = (s, i) => {
			const bg = i === 0 ? '#16a34a' : s.dt === 'Depo' ? '#7c3aed' : '#1d4ed8';
			return `<span style="display:inline-flex;align-items:center;gap:7px;padding:4px 12px 4px 6px;border:1px solid var(--border-color);border-radius:16px;background:var(--card-bg);">
				<span style="width:20px;height:20px;border-radius:50%;background:${bg};color:#fff;display:inline-flex;align-items:center;justify-content:center;font-weight:700;font-size:11px;">${i + 1}</span>
				<b style="font-size:12px;">${esc(s.name)}</b>
				<span class="text-muted" style="font-size:10px;">${s.dt}${i === 0 ? ' (Start)' : ''}</span>
				${s.langsir ? '<span style="font-size:10px;font-weight:600;color:#b45309;background:rgba(245,158,11,.15);padding:1px 7px;border-radius:8px;">Langsir</span>' : ''}
			</span>`;
		};
		const flow = stops.length
			? `<div class="do-flow" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
				${stops.map((s, i) => chip(s, i)).join(`<span style="color:var(--text-muted);font-size:14px;">&#10148;</span>`)}
			</div>`
			: '';
		// Daftar driver: panel melayang di kiri ATAS peta, tingginya dibatasi tinggi peta —
		// lebih dari itu tinggal di-scroll. Sengaja sibling .do-map (bukan anaknya) supaya
		// scroll di panel tidak ikut men-zoom peta.
		const drv_rows = (frm.doc.items || []).filter((r) => r.driver);
		const drv_panel = drv_rows.length
			? `<div class="do-drv-list">
					<div class="do-drv-head">${__('Driver')} (${drv_rows.length})</div>
					${drv_rows
						.map((r) => {
							// nama driver dipangkas 6 huruf; lebih dari itu diberi elipsis
							const n = titles.driver[r.driver] || r.driver;
							const pendek = n.length > 6 ? n.slice(0, 6) + '...' : n;
							return `<div class="do-drv-row">
								<b>${esc(pendek)} - ${esc(r.vehicle || '-')}</b>
								<span class="text-muted">${esc(r.container_no || '')}</span>
							</div>`;
						})
						.join('')}
				</div>`
			: '';
		field.$wrapper.html(`<style>
			/* z-index:0 bikin stacking context sendiri -- tanpa ini, pane Leaflet (400) dan panel
			   driver (500) ikut bersaing dengan header halaman dan menimpanya saat di-scroll */
			.do-map-wrap { position: relative; z-index: 0; }
			/* mulai di bawah kontrol zoom Leaflet (top 10px + dua tombol 30px + border) */
			.do-drv-list { position: absolute; top: 84px; left: 10px; z-index: 500; width: 210px;
				max-height: calc(100% - 94px); overflow-y: auto; font-size: 11px;
				background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 6px;
				box-shadow: 0 2px 8px rgba(0,0,0,.25); }
			.do-drv-head { position: sticky; top: 0; background: var(--card-bg); font-weight: 600;
				padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
			.do-drv-row { padding: 5px 8px; border-bottom: 1px solid var(--border-color); }
			.do-drv-row:last-child { border-bottom: none; }
			.do-drv-row b, .do-drv-row span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
		</style>
		${flow}<div class="do-map-wrap"><div class="do-map border rounded" style="height:520px"></div>${drv_panel}</div>`);
		// Leaflet 1.2 (bundel frappe) crash kalau layer ditambahkan sebelum view di-set
		const map = L.map(field.$wrapper.find('.do-map')[0], { attributionControl: false }).setView([-2.5, 118], 5);
		frm._do_map = map;
		do_tiles().addTo(map);

		const pins = [];
		const by_name = Object.fromEntries(loc_pts.map((p) => [p.name, p]));
		const points = stops
			.map((s) => {
				const p = by_name[s.name];
				return p && (p.latitude || p.longitude) ? { ...p, dt: s.dt, langsir: s.langsir } : null;
			})
			.filter(Boolean);
		points.forEach((p, i) => {
			// start hijau, Langsir biru terang, Depo ungu, Route biru tua
			const bg = i === 0 ? '#16a34a' : p.langsir ? '#0ea5e9' : p.dt === 'Depo' ? '#7c3aed' : '#1d4ed8';
			pins.push(
				L.marker([p.latitude, p.longitude], {
					icon: L.divIcon({
						className: '',
						html: `<div style="width:24px;height:24px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">${i + 1}</div>`,
						iconSize: [24, 24],
						iconAnchor: [12, 12],
					}),
				}).bindTooltip(`${i + 1}. ${p.dt === 'Depo' ? 'Depo ' : ''}${p.name}${i === 0 ? ' (Start)' : ''}${p.langsir ? ' [Langsir]' : ''}`)
			);
		});
		if (points.length > 1) {
			const latlngs = points.map((p) => [p.latitude, p.longitude]);
			pins.push(L.polyline(latlngs, { color: '#1d4ed8', weight: 3, opacity: 0.7, dashArray: '6 8' }));
			for (let i = 0; i < latlngs.length - 1; i++) {
				const [a, b] = [latlngs[i], latlngs[i + 1]];
				const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
				const dx = (b[1] - a[1]) * Math.cos((mid[0] * Math.PI) / 180);
				const dy = b[0] - a[0];
				const deg = (Math.atan2(dx, dy) * 180) / Math.PI - 90;
				pins.push(
					L.marker(mid, {
						interactive: false,
						icon: L.divIcon({
							className: '',
							html: `<div style="transform:rotate(${deg.toFixed(0)}deg);color:#1d4ed8;font-size:16px;line-height:16px;">&#10148;</div>`,
							iconSize: [16, 16],
							iconAnchor: [8, 8],
						}),
					})
				);
			}
		}
		for (const p of veh_pts) {
			if (!p.latitude && !p.longitude) continue;
			// zIndexOffset tinggi = ikon driver/vehicle selalu di atas pin titik
			const drv = drv_of[p.vehicle];
			const label = p.vehicle + (drv ? ' - ' + (titles.driver[drv] || drv) : '');
			pins.push(
				L.marker([p.latitude, p.longitude], {
					zIndexOffset: 1000,
					icon: truck_icon(label),
				}).bindTooltip(label)
			);
		}
		pins.forEach((m) => m.addTo(map));
		if (pins.length) {
			map.fitBounds(L.featureGroup(pins).getBounds().pad(0.3));
		}
		// kontainer bisa masih 0px saat load pertama -> tile abu-abu; hitung ulang begitu berukuran
		if (frm._do_map_ro) frm._do_map_ro.disconnect();
		const el = map.getContainer();
		let fitted = false;
		frm._do_map_ro = new ResizeObserver(() => {
			if (!el.offsetWidth || frm._do_map !== map) return;
			map.invalidateSize();
			if (pins.length && !fitted) {
				map.fitBounds(L.featureGroup(pins).getBounds().pad(0.3));
				fitted = true;
			}
		});
		frm._do_map_ro.observe(el);
	});
}

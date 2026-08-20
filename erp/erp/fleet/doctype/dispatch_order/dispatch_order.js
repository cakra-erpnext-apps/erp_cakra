const DO_ROUTE_FIELDS = ['route_1', 'route_2', 'route_3', 'route_4', 'route_5', 'route_6', 'route_7', 'route_8'];

frappe.ui.form.on('Dispatch Order', {
	refresh(frm) {
		// Baris item mengikuti Packing List — tidak boleh tambah/hapus manual.
		frm.set_df_property('items', 'cannot_add_rows', true);
		frm.set_df_property('items', 'cannot_delete_rows', true);
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
});

// Ikon truk driver (statis, tanpa rotasi arah).
function truck_icon() {
	return L.divIcon({
		className: '',
		html: '<img src="/assets/erp/images/truck.png" style="width:50px;height:50px;filter:drop-shadow(0 1px 3px rgba(0,0,0,.4));">',
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
		const durasi = (start, end) => {
			if (!start || !end) return '';
			const m = Math.round((new Date(String(end).replace(' ', 'T')) - new Date(String(start).replace(' ', 'T'))) / 60000);
			if (isNaN(m) || m < 0) return '';
			return (m >= 60 ? Math.floor(m / 60) + 'j ' : '') + (m % 60) + 'm';
		};
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
			.do-legend { font-size: 11px; color: var(--text-muted); margin: 0 0 6px; }
			.do-legend b { font-weight: 600; color: var(--text-color); }
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
		<div class="do-trip"><table class="table table-bordered table-sm">`;

		// header baris 1: label event + pilihan jenis per slot
		html += `<thead><tr><th class="do-trip-cont">Container</th><th class="do-trip-driver">Driver</th><th>Trip</th><th>Assign</th><th>Accept Job</th>`;
		for (let n = 1; n <= 8; n++) {
			const s = slot(n);
			const sel = s.jenis || (s.point ? 'Route' : 'None');
			html += `<th><select class="form-control do-head-jenis" data-n="${n}">
				${['None', 'Route', 'Depo'].map((o) => `<option value="${o}"${o === sel ? ' selected' : ''}>${o}</option>`).join('')}
			</select></th>`;
		}
		html += `<th>Lanjut Job</th><th>Menuju Garasi</th></tr>`;

		// header baris 2: input titik per slot
		html += `<tr><th class="do-trip-cont"></th><th class="do-trip-driver"></th><th></th><th></th><th></th>`;
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
		for (const it of items) {
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
				const can_add = is_last || (!trips.length && it.assigned);
				// container di-merge: satu sel untuk semua trip milik container itu
				const cont_cell = first_row
					? `<td class="do-trip-cont" rowspan="${row_list.length}">${esc(it.container_no || '')}</td>`
					: '';
				first_row = false;
				// satu tombol titik-tiga -> menu teks (Tambah Trip / Edit / Delete / Playback)
				const menu_btn =
					trip || can_add
						? `<button type="button" class="btn btn-xs do-row-menu" data-item="${it.name}" data-trip="${trip || ''}" data-canadd="${can_add ? 1 : 0}"
							style="padding:2px;border:none;background:transparent;">${frappe.utils.icon('dot-vertical', 'sm')}</button>`
						: '';
				html += `<tr${alt}>${cont_cell}<td class="do-trip-driver">
					<div style="display:flex;gap:3px;align-items:center;">
						${menu_btn}
						<span class="do-trip-name" title="${esc(drv_t)}"><b>${esc(drv_t)}</b></span>
					</div></td>
					<td><b>${trip || ''}</b></td>`;
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
		field.$wrapper.find('.do-trip-t').on('change', function () {
			let v = this.value || null;
			if (v) v = v.replace('T', ' ') + (v.length === 16 ? ':00' : '');
			frappe.model.set_value('Dispatch Order Route', $(this).data('cdn'), $(this).data('f'), v);
			render_trip_matrix(frm); // refresh durasi
		});
		const act_edit = (it, trip) => {
			const g = by_key[`${it.name}|${trip}`];
			frappe.prompt(
				[
					{ fieldname: 'driver', fieldtype: 'Link', options: 'Driver', label: __('Driver'), reqd: 1, default: (g && g[0].driver) || '' },
					{ fieldname: 'vehicle', fieldtype: 'Link', options: 'Vehicle', label: __('Vehicle'), reqd: 1, default: (g && g[0].vehicle) || '' },
					{ fieldname: 'chasis', fieldtype: 'Data', label: __('Chasis'), default: (g && g[0].chasis) || '' },
				],
				(v) => {
					frm.call('edit_trip', { dpo_item: it.name, trip, driver: v.driver, vehicle: v.vehicle, chasis: v.chasis }).then(() => {
						frappe.show_alert({ message: __('Trip {0} diubah', [trip]), indicator: 'green' });
						frm.reload_doc();
					});
				},
				__('Edit Trip {0}', [trip]),
				__('Simpan')
			);
		};
		const act_del = (it, trip) => {
			frappe.confirm(__('Hapus Trip {0} ({1}) beserta semua catatan waktunya?', [trip, it.container_no || '']), () => {
				frm.call('delete_trip', { dpo_item: it.name, trip }).then(() => {
					frappe.show_alert({ message: __('Trip {0} dihapus', [trip]), indicator: 'orange' });
					frm.reload_doc();
				});
			});
		};
		const act_add = (it) => {
			const trips = trips_of(it);
			const g = by_key[`${it.name}|${trips[trips.length - 1]}`];
			frappe.prompt(
				[
					{ fieldname: 'driver', fieldtype: 'Link', options: 'Driver', label: __('Driver'), reqd: 1, default: (g && g[0].driver) || it.driver },
					{ fieldname: 'vehicle', fieldtype: 'Link', options: 'Vehicle', label: __('Vehicle'), reqd: 1, default: (g && g[0].vehicle) || it.vehicle },
					{ fieldname: 'chasis', fieldtype: 'Data', label: __('Chasis'), default: (g && g[0].chasis) || it.chasis || '' },
				],
				(v) => {
					const run = () =>
						frm.call('add_trip', { dpo_item: it.name, driver: v.driver, vehicle: v.vehicle, chasis: v.chasis }).then((r) => {
							frappe.show_alert({ message: __('Trip {0} dibuat', [r.message.trip]), indicator: 'green' });
							frm.reload_doc();
						});
					frm.is_dirty() ? frm.save().then(run) : run();
				},
				__('Tambah Trip untuk {0}', [it.container_no || it.driver]),
				__('Buat')
			);
		};

		field.$wrapper.find('.do-row-menu').on('click', function (e) {
			e.preventDefault();
			e.stopPropagation();
			$('.do-row-actions').remove();
			const it = items.find((x) => x.name === $(this).data('item'));
			if (!it) return;
			const trip = Number($(this).data('trip')) || null;
			const can_add = Number($(this).data('canadd')) === 1;
			const li = (act, label) => `<a class="dropdown-item" data-act="${act}" href="#">${label}</a>`;
			let m = '';
			if (can_add) m += li('add', __('Tambah Trip'));
			if (trip) m += li('edit', __('Edit')) + li('del', __('Delete')) + li('play', __('Playback'));
			// tempel ke body (position fixed) — kalau di dalam td, kepotong overflow scroll tabel
			const r = this.getBoundingClientRect();
			const $menu = $(
				`<div class="dropdown-menu show do-row-actions" style="position:fixed;top:${(r.bottom + 2).toFixed(0)}px;left:${r.left.toFixed(0)}px;z-index:1050;">${m}</div>`
			).appendTo('body');
			$menu.find('.dropdown-item').on('click', function (ev) {
				ev.preventDefault();
				$('.do-row-actions').remove();
				const act = $(this).data('act');
				if (act === 'add') act_add(it);
				else if (act === 'edit') act_edit(it, trip);
				else if (act === 'del') act_del(it, trip);
				else show_playback(it, trip);
			});
		});
		$(document).off('click.do-row-actions').on('click.do-row-actions', () => $('.do-row-actions').remove());
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
	]).then(([loc_pts, veh_pts]) => {
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
		field.$wrapper.html(`${flow}<div class="do-map border rounded" style="height:520px"></div>`);
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
			// titik bercentang Langsir = hijau; selain itu: start hijau, Depo ungu, Route biru
			const bg = p.langsir || i === 0 ? '#16a34a' : p.dt === 'Depo' ? '#7c3aed' : '#1d4ed8';
			pins.push(
				L.marker([p.latitude, p.longitude], {
					icon: L.divIcon({
						className: '',
						html: `<div style="width:24px;height:24px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;">${i + 1}</div>`,
						iconSize: [24, 24],
						iconAnchor: [12, 12],
					}),
				}).bindTooltip(`${i + 1}. ${p.dt === 'Depo' ? 'Depo ' : ''}${p.name}${i === 0 ? ' (Start)' : ''}`)
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
			pins.push(
				L.marker([p.latitude, p.longitude], {
					zIndexOffset: 1000,
					icon: truck_icon(),
				}).bindTooltip(__('Vehicle {0}', [p.vehicle]))
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

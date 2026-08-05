const DO_ROUTE_FIELDS = ['route_1', 'route_2', 'route_3', 'route_4', 'route_5', 'route_6', 'route_7', 'route_8'];

frappe.ui.form.on('Delivery Order', {
	refresh(frm) {
		// Baris item mengikuti Packing List — tidak boleh tambah/hapus manual.
		frm.set_df_property('items', 'cannot_add_rows', true);
		frm.set_df_property('items', 'cannot_delete_rows', true);
		if (!frm.is_new()) {
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

frappe.ui.form.on('Delivery Order Item', {
	vehicle(frm) {
		render_route_map(frm);
	},
});

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
// Data slot di route_type_n/route_n, waktu di child trip_log (tabDelivery Order Route).
function render_trip_matrix(frm) {
	const field = frm.get_field('trip_html');
	if (!field) return;
	const items = frm.doc.items || [];
	if (!items.length) {
		field.$wrapper.html(`<div class="text-muted">${__('Belum ada item.')}</div>`);
		return;
	}
	get_masters(frm).then(([routes, depos]) => {
		const esc = frappe.utils.escape_html;
		const rows = frm.doc.trip_log || [];
		const by_item = {};
		rows.forEach((r) => ((by_item[r.do_item] = by_item[r.do_item] || []).push(r)));
		const find = (it, pred) => (by_item[it.name] || []).find(pred);
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

		const slot = (n) => ({ jenis: frm.doc[`route_type_${n}`] || '', point: frm.doc[`route_${n}`] || '' });

		let html = `
		<style>
			.do-trip { overflow-x: auto; }
			.do-trip table { width: max-content; min-width: 100%; margin-bottom: 0; }
			.do-trip th, .do-trip td { white-space: nowrap; vertical-align: middle; padding: 4px 8px; text-align: center; }
			.do-trip th.do-trip-driver, .do-trip td.do-trip-driver { position: sticky; left: 0; background: var(--card-bg); z-index: 1; text-align: left; }
			.do-trip .do-cell { display: grid; grid-template-columns: 26px 168px; gap: 2px 4px; align-items: center; }
			.do-trip .do-trip-lbl { font-size: 10px; color: var(--text-muted); text-align: right; }
			.do-trip input.do-trip-t { width: 168px; height: 26px; font-size: 12px; padding: 2px 6px; }
			.do-trip .do-trip-dur { font-size: 11px; font-weight: 600; color: var(--text-muted); margin-top: 2px; }
			.do-trip select.do-head-jenis, .do-trip input.do-head-point { height: 26px; font-size: 12px; padding: 2px 6px; width: 130px; display: inline-block; }
		</style>
		${dl('Route', routes)}${dl('Depo', depos)}
		<div class="do-trip"><table class="table table-bordered table-sm">`;

		// header baris 1: label event + pilihan jenis per slot
		html += `<thead><tr><th class="do-trip-driver"></th><th>Assign</th><th>Accept Job</th>`;
		for (let n = 1; n <= 8; n++) {
			const s = slot(n);
			const sel = s.jenis || (s.point ? 'Route' : 'None');
			html += `<th><select class="form-control do-head-jenis" data-n="${n}">
				${['None', 'Route', 'Depo'].map((o) => `<option value="${o}"${o === sel ? ' selected' : ''}>${o}</option>`).join('')}
			</select></th>`;
		}
		html += `<th>Lanjut Job</th><th>Menuju Garasi</th></tr>`;

		// header baris 2: input titik per slot
		html += `<tr><th class="do-trip-driver">Driver</th><th></th><th></th>`;
		for (let n = 1; n <= 8; n++) {
			const s = slot(n);
			const none = !s.jenis && !s.point;
			html += `<th>${none ? '' : `<input type="text" class="form-control do-head-point" data-n="${n}" list="do-dl-${s.jenis || 'Route'}" value="${esc(s.point)}" placeholder="${__('Titik')} ${n}" autocomplete="off">`}</th>`;
		}
		html += `<th></th><th></th></tr></thead><tbody>`;

		for (const it of items) {
			html += `<tr><td class="do-trip-driver"><b>${esc(it.driver || it.container_no || '')}</b><br>
				<button type="button" class="btn btn-xs btn-default do-playback" data-item="${it.name}"
					style="margin-top:4px;border:1px solid var(--border-color);">${__('Playback')}</button></td>`;
			html += time_cell(find(it, (r) => r.step_type === 'Assign'), false);
			html += time_cell(find(it, (r) => r.step_type === 'Accept Job'), false);
			for (let n = 1; n <= 8; n++) {
				const s = slot(n);
				if (!s.jenis && !s.point) {
					html += '<td></td>'; // None -> clean
				} else {
					html += time_cell(s.point ? find(it, (r) => r.step_type === 'Route' && r.point === s.point) : null, true);
				}
			}
			html += time_cell(find(it, (r) => r.step_type === 'Lanjut Job'), false);
			html += time_cell(find(it, (r) => r.step_type === 'Menuju Garasi'), true);
			html += '</tr>';
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
		field.$wrapper.find('.do-trip-t').on('change', function () {
			let v = this.value || null;
			if (v) v = v.replace('T', ' ') + (v.length === 16 ? ':00' : '');
			frappe.model.set_value('Delivery Order Route', $(this).data('cdn'), $(this).data('f'), v);
			render_trip_matrix(frm); // refresh durasi
		});
		field.$wrapper.find('.do-playback').on('click', function (e) {
			e.preventDefault();
			const it = items.find((x) => x.name === $(this).data('item'));
			if (it) show_playback(it);
		});
	});
}

// Playback jejak GPS satu job dari history.route_history: garis rute + marker jalan
// mengikuti urutan waktu rekaman (start hijau S, end merah E).
function show_playback(it) {
	frappe
		.call('erp.fleet.doctype.delivery_order.delivery_order.get_route_history', { do_item: it.name })
		.then((r) => {
			const pts = r.message || [];
			if (!pts.length) {
				frappe.msgprint(__('Belum ada history perjalanan untuk {0}.', [it.driver || it.container_no]));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __('Playback {0} ({1})', [it.driver || '', it.container_no || '']),
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
				const map = L.map(wrap.find('.do-play-map')[0]).setView([-2.5, 118], 5);
				L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
					attribution: '&copy; OpenStreetMap contributors',
					maxZoom: 19,
				}).addTo(map);
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
				const mover = L.circleMarker(latlngs[0], {
					radius: 9,
					color: '#c2410c',
					fillColor: '#f97316',
					fillOpacity: 1,
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
			</span>`;
		};
		const flow = stops.length
			? `<div class="do-flow" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;">
				${stops.map((s, i) => chip(s, i)).join(`<span style="color:var(--text-muted);font-size:14px;">&#10148;</span>`)}
			</div>`
			: '';
		field.$wrapper.html(`${flow}<div class="do-map border rounded" style="height:520px"></div>`);
		// Leaflet 1.2 (bundel frappe) crash kalau layer ditambahkan sebelum view di-set
		const map = L.map(field.$wrapper.find('.do-map')[0]).setView([-2.5, 118], 5);
		frm._do_map = map;
		L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
			attribution: '&copy; OpenStreetMap contributors',
			maxZoom: 19,
		}).addTo(map);

		const pins = [];
		const by_name = Object.fromEntries(loc_pts.map((p) => [p.name, p]));
		const points = stops
			.map((s) => {
				const p = by_name[s.name];
				return p && (p.latitude || p.longitude) ? { ...p, dt: s.dt } : null;
			})
			.filter(Boolean);
		points.forEach((p, i) => {
			const bg = i === 0 ? '#16a34a' : p.dt === 'Depo' ? '#7c3aed' : '#1d4ed8';
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
			pins.push(
				L.circleMarker([p.latitude, p.longitude], {
					radius: 8,
					color: '#c2410c',
					fillColor: '#f97316',
					fillOpacity: 0.9,
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

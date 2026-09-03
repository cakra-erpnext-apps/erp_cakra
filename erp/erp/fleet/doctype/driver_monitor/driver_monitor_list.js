frappe.listview_settings['Driver Monitor'] = {
	hide_name_column: true,
	// Palet sama dengan badge status di Monitoring Board supaya satu status tidak
	// pernah beda warna antar halaman.
	status_style: {
		'On Job': 'background:#dbeafe;color:#1e40af;',
		Ready: 'background:#dcfce7;color:#166534;',
		Absensi: 'background:#ffedd5;color:#9a3412;',
		Izin: 'background:#ede9fe;color:#5b21b6;',
		Sakit: 'background:#fee2e2;color:#991b1b;',
		'Belum Absen': 'background:var(--bg-light-gray,#f3f4f6);color:var(--text-muted);',
	},
	get_indicator(doc) {
		const color = {
			'On Job': 'blue',
			Ready: 'green',
			Absensi: 'orange',
			Izin: 'purple',
			Sakit: 'red',
			'Belum Absen': 'gray',
		};
		return [__(doc.status), color[doc.status] || 'gray', `status,=,${doc.status}`];
	},
	// Badge kotak seperti di Monitoring Board, bukan pill bulat + titik bawaan Frappe.
	formatters: {
		status(value) {
			const gaya = frappe.listview_settings['Driver Monitor'].status_style[value] || '';
			return `<span class="filterable" data-filter="status,=,${frappe.utils.escape_html(
				value
			)}" style="${gaya}padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;white-space:nowrap">${frappe.utils.escape_html(
				__(value)
			)}</span>`;
		},
	},

	onload(listview) {
		// klik nama driver: tampilkan absensi hari ini sebagai modal, bukan buka form virtual.
		// listener capture di document supaya jalan sebelum router frappe menangani klik link,
		// dan tidak bergantung pada elemen list yang di-render ulang tiap refresh.
		if (!window.__driver_monitor_modal_bound) {
			window.__driver_monitor_modal_bound = true;
			document.addEventListener(
				'click',
				(e) => {
					const a = e.target.closest && e.target.closest('a[href*="driver-monitor/"]');
					if (!a) return;
					e.preventDefault();
					e.stopPropagation();
					const name = decodeURIComponent(
						a.dataset.name || a.getAttribute('href').split('/').pop()
					);
					const row = (cur_list && cur_list.data ? cur_list.data : []).find((d) => d.name === name);
					show_absensi_dialog(name, row ? row.driver_name : name);
				},
				true
			);
		}

		// jalan cadangan sekaligus penanda file ini termuat
		listview.page.add_inner_button(__('Absensi Hari Ini'), () => {
			const picked = listview.get_checked_items(true);
			if (!picked.length) return frappe.msgprint(__('Centang satu driver dulu'));
			const row = (listview.data || []).find((d) => d.name === picked[0]);
			show_absensi_dialog(picked[0], row ? row.driver_name : picked[0]);
		});

		listview.page.add_actions_menu_item(__('Set Keterangan'), () => {
			const drivers = listview.get_checked_items(true);
			if (!drivers.length) return frappe.msgprint(__('Pilih driver dulu'));
			const d = new frappe.ui.Dialog({
				title: __('Set Keterangan'),
				fields: [
					{
						fieldname: 'type',
						fieldtype: 'Select',
						label: __('Type'),
						options: 'Izin\nSakit',
						reqd: 1,
					},
					{ fieldname: 'remark', fieldtype: 'Small Text', label: __('Keterangan'), reqd: 1 },
				],
				primary_action_label: __('Simpan'),
				primary_action(values) {
					frappe
						.call('erp.fleet.doctype.driver_monitor.driver_monitor.set_remark', {
							drivers,
							...values,
						})
						.then(() => {
							d.hide();
							listview.refresh();
						});
				},
			});
			d.show();
		});
	},
};

const LEAFLET = [
	'/assets/frappe/js/lib/leaflet/leaflet.css',
	'/assets/frappe/js/lib/leaflet/leaflet.js',
];

const WARNA = { absensi: '#2490ef', checkin: '#28a745', trado: '#ff8c00' };

function show_absensi_dialog(driver, driver_name) {
	frappe
		.call('erp.fleet.doctype.driver_monitor.driver_monitor.get_today_attendance', { driver })
		.then((r) => {
			const data = r.message || { photo: null, points: [] };
			const d = new frappe.ui.Dialog({
				title: `${driver_name} ${__('- Absensi Hari Ini')}`,
				size: 'extra-large',
				fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			});
			d.fields_dict.body.$wrapper.html(body_html(data));
			d.show();
			if (data.points.length) {
				frappe.require(LEAFLET, () => render_peta(d.$wrapper.find('.absensi-peta')[0], data.points));
			}
		});
}

function body_html(data) {
	const esc = frappe.utils.escape_html;
	const p = data.photo;
	const foto = p
		? `<a href="${encodeURI(p.image)}" target="_blank" rel="noopener">
				<img src="${encodeURI(p.image)}" alt="${esc(p.label)}"
					style="width:100%;border:1px solid var(--border-color);border-radius:var(--border-radius)">
			</a>
			<div class="small text-muted mt-1">${esc(p.label)} ${frappe.datetime.str_to_user(p.timestamp)}</div>`
		: `<div class="text-muted">${__('Belum ada foto absensi hari ini')}</div>`;

	const peta = data.points.length
		? `<div class="absensi-peta" style="height:460px;border:1px solid var(--border-color);border-radius:var(--border-radius)"></div>
			<div class="small text-muted mt-2">
				<span style="color:${WARNA.absensi}">&#9679;</span> ${__('Absensi')}
				<span style="color:${WARNA.checkin};margin-left:12px">&#9679;</span> ${__('Check In')}
				<span style="color:${WARNA.trado};margin-left:12px">&#9679;</span> ${__('Posisi Trado')}
			</div>`
		: `<div class="text-muted">${__('Belum ada titik lokasi hari ini')}</div>`;

	const checkin = data.points.filter((t) => t.kind === 'checkin');
	const daftar = checkin.length
		? checkin
				.map(
					(t) => `<div class="absensi-ci" data-lat="${t.lat}" data-lon="${t.lon}"
						style="padding:6px 2px;border-bottom:1px solid var(--border-color);cursor:pointer">
						<div><b>${esc(t.label)}</b> ${jam(t.timestamp)}</div>
						<div class="small text-muted">${t.vehicle ? esc(t.vehicle) : '-'}${
						t.distance_m == null ? '' : `, ${t.distance_m} m`
					}</div>
					</div>`
				)
				.join('')
		: `<div class="text-muted small">${__('Belum ada check in hari ini')}</div>`;

	return `<div class="row">
		<div class="col-sm-3 d-flex flex-column" style="height:460px">
			<div>${foto}</div>
			<div class="text-muted small mt-3 mb-1">${__('Check In')} (${checkin.length})</div>
			<div style="flex:1;overflow-y:auto">${daftar}</div>
		</div>
		<div class="col-sm-9">${peta}</div>
	</div>`;
}

function jam(timestamp) {
	return String(timestamp).split(' ')[1].slice(0, 5);
}

function render_peta(el, points) {
	const map = L.map(el);
	L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
		maxZoom: 19,
		attribution: '&copy; OpenStreetMap',
	}).addTo(map);

	const bounds = [];
	points.forEach((p) => {
		bounds.push([p.lat, p.lon]);
		L.circleMarker([p.lat, p.lon], {
			radius: 8,
			color: '#fff',
			weight: 2,
			fillColor: WARNA[p.kind],
			fillOpacity: 1,
		})
			.addTo(map)
			.bindTooltip(
				`${p.label}<br>${frappe.datetime.str_to_user(p.timestamp)}` +
					(p.distance_m == null ? '' : `<br>${__('Jarak driver ke trado')}: ${p.distance_m} m`),
				{ direction: 'top' }
			);

		// garis dari titik check in ke posisi trado saat check in itu
		if (p.kind === 'trado' && p.driver_lat) {
			L.polyline(
				[
					[p.driver_lat, p.driver_lon],
					[p.lat, p.lon],
				],
				{ color: WARNA.trado, weight: 2, dashArray: '4,4' }
			).addTo(map);
		}
	});

	$(el)
		.closest('.modal')
		.find('.absensi-ci')
		.on('click', function () {
			map.setView([$(this).data('lat'), $(this).data('lon')], 17);
		});

	map.fitBounds(bounds, { padding: [40, 40], maxZoom: 17 });
	// dialog baru dapat ukuran final setelah show
	setTimeout(() => map.invalidateSize(), 200);
}

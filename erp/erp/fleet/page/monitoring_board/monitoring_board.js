// Monitoring: satu tabel semua kendaraan aktif (job, notifikasi, note terakhir).
// Auto-refresh 60 detik.
frappe.pages['monitoring-board'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Monitoring'),
		single_column: true,
	});

	const $body = $(`
		<div class="mb">
			<style>
				.mb { padding: 8px 0; }
				.mb-scroll { overflow: auto; border: 1px solid var(--border-color); border-radius: 8px; }
				.mb table { width: 100%; margin: 0; font-size: 12px; border-collapse: separate; border-spacing: 0; }
				.mb th { position: sticky; top: 0; z-index: 1; background: var(--bg-light-gray, #f3f4f6);
					font-size: 11px; font-weight: 700; white-space: nowrap; padding: 6px 8px;
					border-bottom: 1px solid var(--border-color); }
				.mb td { padding: 3px 8px; white-space: nowrap; max-width: 260px; overflow: hidden;
					text-overflow: ellipsis; border-bottom: 1px solid var(--border-color); }
				.mb tbody tr:hover { background: var(--highlight-color, #eef2ff); }
				.mb .mb-pill { padding: 0 7px; border-radius: 9px; font-size: 11px; font-weight: 600; }
				.mb .btn-xs { padding: 1px 6px; font-size: 11px; }
				.mb-act { white-space: nowrap; }
				.mb-act .btn { padding: 2px 5px; line-height: 1; }
				.mb-act .icon { width: 14px; height: 14px; vertical-align: middle; }
				.mb-empty { padding: 14px; color: var(--text-muted); font-size: 13px; }
				.leaflet-tooltip.mb-plate { background: #000; color: #fff; border: none; box-shadow: none;
					font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
				.leaflet-tooltip.mb-plate:before { display: none; }
				/* modal peta dibuat selebar layar supaya petanya lega */
				.modal.mb-wide .modal-dialog { max-width: 96vw; width: 96vw; }
				.mb-dlg { display: flex; gap: 14px; align-items: stretch; }
				.mb-dlg-left { flex: 1 1 0; min-width: 420px; }
				.mb-dlg-col { border-left: 1px solid var(--border-color); padding-left: 12px;
					display: flex; flex-direction: column; min-width: 0; }
				.mb-dlg-route { flex: 0 0 175px; }
				.mb-dlg-notif { flex: 0 0 195px; }
				.mb-dlg-hist { flex: 0 0 205px; }
				.mb-tag { display: inline-block; font-size: 10px; font-weight: 700; padding: 0 6px; border-radius: 8px; }
				.mb-tag-job { background: #dbeafe; color: #1e40af; }
				.mb-tag-idle { background: var(--bg-light-gray, #f3f4f6); color: var(--text-muted); }
				.mb-done { color: #16a34a; font-weight: 600; }
				.mb-cur { background: #1d4ed8; color: #fff; font-weight: 700; padding: 1px 6px; border-radius: 9px; }
				.mb-dlg-info { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px 12px; margin: 10px 0 0; }
				.mb-dlg-info > div { min-width: 0; }
				.mb-dlg-info dt { font-size: 10px; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: .03em; }
				.mb-dlg-info dd { margin: 0; font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			</style>
			<div class="mb-scroll"><table class="table">
				<thead><tr>
					<th>No</th><th>Brc</th><th>Nopol</th><th>Status</th><th>Job No</th>
					<th>Customer</th><th>ATD</th><th>ATA</th><th>Notifikasi</th><th>Notification Date</th>
					<th>Note</th><th>Note Date</th>
				</tr></thead>
				<tbody></tbody>
			</table></div>
		</div>
	`).appendTo(page.body);

	page.set_secondary_action(__('Refresh'), load);

	const esc = frappe.utils.escape_html;
	// Palet datang dari server (erp/fleet/vehicle_status.py) supaya status baru tidak perlu
	// didaftarkan ulang di tiap halaman.
	let STATUS_STYLE = {};
	const dt = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 19)) : '-');
	const tgl = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : '-');
	let rows = [];

	// tabel mengisi sisa layar
	function fit() {
		const top = $body.find('.mb-scroll').offset().top - $(window).scrollTop();
		$body.find('.mb-scroll').css('max-height', Math.max(window.innerHeight - top - 40, 160) + 'px');
	}

	function paint() {
		const $tb = $body.find('tbody').empty();
		if (!rows.length) {
			$tb.append(`<tr><td colspan="12" class="mb-empty">${__('Belum ada kendaraan aktif.')}</td></tr>`);
			return;
		}
		rows.forEach((r, i) => {
			$tb.append(`<tr data-i="${i}">
				<td>${i + 1}</td>
				<td>${esc(r.branch || '-')}</td>
				<td><a href="#" class="mb-open"><b>${esc(r.nopol)}</b></a></td>
				<td><span class="mb-pill" style="${STATUS_STYLE[r.status] || ''}">${esc(r.status)}</span></td>
				<td>${esc(r.job_no || '-')}</td>
				<td title="${esc(r.customer || '')}">${esc(r.customer || '-')}</td>
				<td>${tgl(r.atd)}</td>
				<td>${tgl(r.ata)}</td>
				<td title="${esc(r.notifikasi || '')}">${esc(r.notifikasi || '-')}</td>
				<td>${dt(r.notification_date)}</td>
				<td title="${esc(r.note || '')}">${esc(r.note || '-')}</td>
				<td>${dt(r.note_date)}</td>
			</tr>`);
		});
		$tb.find('.mb-open').on('click', function (e) {
			e.preventDefault();
			map_dialog(rows[$(this).closest('tr').data('i')]);
		});
		fit();
	}

	// "05 Agu 26 18:00 - 23:59" / "... - On Going" / "-"
	const BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
	const tg = (s) => `${s.slice(8, 10)} ${BULAN[Number(s.slice(5, 7)) - 1]} ${s.slice(2, 4)}`;
	const jm = (s) => s.slice(11, 16);
	function in_out(a, b) {
		if (!a && !b) return '-';
		if (a && !b) return `${tg(a)} ${jm(a)} - ${__('On Going')}`;
		if (!a && b) return `? - ${tg(b)} ${jm(b)}`;
		return a.slice(0, 10) === b.slice(0, 10) ? `${tg(a)} ${jm(a)} - ${jm(b)}` : `${tg(a)} ${jm(a)} - ${tg(b)} ${jm(b)}`;
	}

	// titik rute job aktif unit ini (diambil saat modal dibuka)
	function load_route(r, $box) {
		const head = `<div style="font-weight:700;margin-bottom:6px">${__('Route Assigned')}</div>`;
		$box.html(`${head}<div class="text-muted" style="font-size:12px">${__('Memuat...')}</div>`);
		frappe
			.call('erp.fleet.page.gps_monitor.gps_monitor.get_detail', { vehicle: r.vehicle })
			.then((res) => {
				const pts = (res.message && res.message.route_points) || [];
				const cur = pts.findIndex((p) => !p.end);
				const isi = pts.length
					? pts
							.map(
								(p, i) => `<div style="padding:4px 0;border-bottom:1px solid var(--border-color)">
									<div style="font-size:12px" class="${p.end ? 'mb-done' : ''}">
										<b>${i + 1}.</b> ${i === cur ? `<span class="mb-cur">${esc(p.point)}</span>` : esc(p.point)}</div>
									<div style="font-size:10.5px;color:#374151;padding-left:15px">${in_out(p.start, p.end)}</div>
								</div>`
							)
							.join('')
					: `<div class="text-muted" style="font-size:12px">${
							r.dpo ? __('Belum ada titik rute.') : __('Tidak ada job aktif.')
					  }</div>`;
				$box.html(`${head}<div style="flex:1 1 auto;min-height:0;overflow-y:auto">${isi}</div>`);
			});
	}

	// feed notifikasi unit ini
	function load_notifications(r, $box) {
		const head = `<div style="font-weight:700;margin-bottom:6px">${__('Notifikasi')}</div>`;
		$box.html(`${head}<div class="text-muted" style="font-size:12px">${__('Memuat...')}</div>`);
		frappe
			.call('erp.fleet.page.monitoring_board.monitoring_board.get_notifications', {
				vehicle: r.vehicle,
				dpo_no: r.job_no || '',
			})
			.then((res) => {
				const list = res.message || [];
				const isi = list.length
					? list
							.map(
								(n) => `<div style="border-bottom:1px solid var(--border-color);padding:5px 0">
									<div style="font-size:12.5px">${esc(n.message)}</div>
									<div style="font-size:10.5px;color:var(--text-muted)">${dt(n.notification_date)}</div>
								</div>`
							)
							.join('')
					: `<div style="border-bottom:1px solid var(--border-color);padding:5px 0">
							<div style="font-size:12.5px">${esc(r.notifikasi || '-')}</div>
							<div style="font-size:10.5px;color:var(--text-muted)">${dt(r.notification_date)}</div>
						</div>`;
				$box.html(`${head}<div style="flex:1 1 auto;min-height:0;overflow-y:auto">${isi}</div>`);
			});
	}

	// penanda tiap note: dibuat saat unit punya job (tampilkan No DPO-nya) atau tidak
	const job_tag = (n) =>
		n.dpo_no
			? `<span class="mb-tag mb-tag-job" title="${__('Dibuat saat ada job')}">${esc(n.dpo_no)}</span>`
			: `<span class="mb-tag mb-tag-idle">${__('Tanpa job')}</span>`;

	// semua note unit itu (dengan atau tanpa job) — dipakai dialog peta & dialog note
	function load_history(r, $box) {
		const head = `<div style="font-weight:700;margin-bottom:6px">${__('Notes')}</div>`;
		$box.html(`${head}<div class="text-muted" style="font-size:12px">${__('Memuat...')}</div>`);
		frappe
			.call('erp.fleet.page.gps_monitor.gps_monitor.get_notes', {
				dpo_no: r.job_no || '',
				vehicle: r.vehicle,
			})
			.then((res) => {
				const list = res.message || [];
				const isi = list.length
					? list
							.map(
								(n) => `<div style="border-bottom:1px solid var(--border-color);padding:5px 0">
									<div style="font-size:11px;font-weight:700;color:#374151">${dt(n.note_date)} &middot; ${esc(n.owner)}</div>
									<div style="font-size:12.5px">${esc(n.note)}</div>
									<div>${job_tag(n)}</div>
								</div>`
							)
							.join('')
					: `<div class="text-muted" style="font-size:12px">${__('Belum ada note.')}</div>`;
				$box.html(`${head}<div style="flex:1 1 auto;min-height:0;overflow-y:auto">${isi}</div>`);
			});
	}

	// peta posisi 1 unit, plus tombol pindah ke halaman GPS Vehicle
	function map_dialog(r) {
		if (!r.latitude || !r.longitude) {
			frappe.msgprint(__('Unit {0} belum punya koordinat GPS.', [r.nopol]));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __('Posisi {0}', [r.nopol]),
			size: 'extra-large',
			fields: [{ fieldtype: 'HTML', fieldname: 'map' }],
			primary_action_label: __('Go to Map'),
			primary_action: () => {
				d.hide();
				frappe.route_options = { vehicle: r.vehicle };
				frappe.set_route('gps-monitor');
			},
			secondary_action_label: __('Add Note'),
			secondary_action: () => note_dialog(r),
		});
		d.$wrapper.addClass('mb-wide');
		d.show();
		setTimeout(() => {
			const $w = d.get_field('map').$wrapper;
			const pair = (label, val) =>
				`<div><dt>${label}</dt><dd title="${esc(val || '')}">${val || '-'}</dd></div>`;
			$w.html(`<div class="mb-dlg">
					<div class="mb-dlg-left">
						<div class="mb-dlg-map border rounded" style="height:560px"></div>
						<dl class="mb-dlg-info">
							${pair(__('Nopol'), `<b>${esc(r.nopol)}</b>`)}
							${pair(__('Branch'), esc(r.branch))}
							${pair(__('Status'), `<span class="mb-pill" style="${STATUS_STYLE[r.status] || ''}">${esc(r.status)}</span>`)}
							${pair(
								__('Job No'),
								r.dpo ? `<a href="#" class="mb-job">${esc(r.job_no)}</a>` : esc(r.job_no)
							)}
							${pair(__('Customer'), esc(r.customer))}
							${pair(__('ATD'), tgl(r.atd))}
							${pair(__('ATA'), tgl(r.ata))}
						</dl>
					</div>
					<div class="mb-dlg-col mb-dlg-route"></div>
					<div class="mb-dlg-col mb-dlg-notif"></div>
					<div class="mb-dlg-col mb-dlg-hist"></div>
				</div>`);
			$w.find('.mb-job').on('click', (ev) => {
				ev.preventDefault();
				d.hide();
				frappe.set_route('Form', 'Dispatch Order', r.dpo);
			});
			load_route(r, $w.find('.mb-dlg-route'));
			load_notifications(r, $w.find('.mb-dlg-notif'));
			load_history(r, $w.find('.mb-dlg-hist'));
			const m = L.map($w.find('.mb-dlg-map')[0]).setView([r.latitude, r.longitude], 14);
			L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
				attribution: '&copy; OpenStreetMap, &copy; CARTO',
				subdomains: 'abcd',
				maxZoom: 20,
			}).addTo(m);
			L.marker([r.latitude, r.longitude], {
				icon: L.icon({
					iconUrl: '/assets/erp/images/truck.png',
					iconSize: [50, 50],
					iconAnchor: [25, 25],
					popupAnchor: [0, -20],
				}),
			})
				.addTo(m)
				.bindTooltip(esc(r.nopol), { permanent: true, direction: 'top', offset: [0, -22], className: 'mb-plate' });
			setTimeout(() => m.invalidateSize(), 300);
			d.$wrapper.on('hidden.bs.modal', () => m.remove());
		}, 300);
	}

	// note + history-nya, sama seperti di halaman GPS Vehicle
	function note_dialog(r) {
		const d = new frappe.ui.Dialog({
			title: __('Note {0}', [r.nopol]),
			size: 'large',
			fields: [
				{ fieldtype: 'HTML', options: `<div style="font-weight:700;margin-bottom:6px">${__('Note Anda')}</div>` },
				{ fieldname: 'note_date', fieldtype: 'Datetime', label: __('Note Date'), default: frappe.datetime.now_datetime(), reqd: 1 },
				{ fieldname: 'note', fieldtype: 'Small Text', label: __('Note Anda'), reqd: 1 },
				{ fieldtype: 'Column Break' },
				{ fieldtype: 'HTML', fieldname: 'history' },
			],
			primary_action_label: __('Submit'),
			secondary_action_label: __('Cancel'),
			secondary_action: () => d.hide(),
			primary_action: (v) => {
				frappe
					.call('erp.fleet.page.gps_monitor.gps_monitor.add_note', {
						vehicle: r.vehicle,
						nopol: r.nopol,
						dpo_no: r.job_no,
						status: r.status,
						note_date: v.note_date,
						note: v.note,
					})
					.then((res) => {
						d.hide();
						frappe.show_alert({ message: __('Note tersimpan: {0}', [res.message]), indicator: 'green' });
						load();
					});
			},
		});
		d.show();

		const $h = d.get_field('history').$wrapper;
		const head = `<div style="font-weight:700;margin-bottom:6px">${__('History Note')}</div>`;
		$h.html(`${head}<div class="text-muted" style="font-size:12px">${__('Memuat...')}</div>`);
		frappe
			.call('erp.fleet.page.gps_monitor.gps_monitor.get_notes', { dpo_no: r.job_no || '', vehicle: r.vehicle })
			.then((res) => {
				const list = res.message || [];
				const isi = list.length
					? list
							.map(
								(n) => `<div style="border-bottom:1px solid var(--border-color);padding:6px 0">
									<div style="font-size:11px;font-weight:700;color:#374151">${dt(n.note_date)}</div>
									<div style="font-size:12.5px">${esc(n.note)}</div>
									<div style="font-size:10.5px;color:var(--text-muted)">${esc(n.owner)}</div>
								</div>`
							)
							.join('')
					: `<div class="text-muted" style="font-size:12px">${__('Belum ada note.')}</div>`;
				$h.html(`${head}<div style="max-height:260px;overflow-y:auto">${isi}</div>`);
			});
	}

	function load() {
		frappe.call('erp.fleet.page.monitoring_board.monitoring_board.get_rows').then((r) => {
			const res = r.message || {};
			rows = res.rows || [];
			STATUS_STYLE = res.status_colors || STATUS_STYLE;
			paint();
		});
	}

	load();
	const timer = setInterval(load, 60000);
	$(window).on('resize.mb', fit);
	$(wrapper).on('remove', () => {
		clearInterval(timer);
		$(window).off('resize.mb');
	});
};

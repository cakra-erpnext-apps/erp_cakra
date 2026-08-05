// Absensi Driver: monitoring read-only 1 baris per driver (status, absen pertama,
// check-in terakhir, job aktif). Auto-refresh tiap 60 detik.
frappe.pages['driver-monitor'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Absensi Driver'),
		single_column: true,
	});
	const $body = $(`
		<div class="dm-wrap">
			<style>
				.dm-wrap { padding: 8px 0; }
				.dm-wrap .dm-scroll { overflow-x: auto; }
				.dm-wrap td, .dm-wrap th { white-space: nowrap; }
				.dm-wrap .dm-status { font-weight: 600; padding: 2px 10px; border-radius: 10px; font-size: 12px; display: inline-block; }
			</style>
			<div class="dm-scroll"><table class="table table-bordered table-sm">
				<thead><tr>
					<th>Branch</th><th>Driver</th><th>Status</th><th>Nopol</th>
					<th>Absensi</th><th>Check In</th>
					<th>No Packing List</th><th>No DO</th><th>Checkpoint Terakhir</th>
				</tr></thead>
				<tbody></tbody>
			</table></div>
		</div>
	`).appendTo(page.body);
	page.set_secondary_action(__('Refresh'), load);

	const STATUS_STYLE = {
		'On Job': 'background:#dbeafe;color:#1e40af;',
		Ready: 'background:#dcfce7;color:#166534;',
		Absensi: 'background:#fef9c3;color:#854d0e;',
		'Belum Absen': 'background:var(--bg-light-gray, #f3f4f6);color:var(--text-muted);',
	};
	const dt = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 19)) : '');

	function load() {
		frappe.call('erp.fleet.page.driver_monitor.driver_monitor.get_rows').then((r) => {
			const esc = frappe.utils.escape_html;
			const $tb = $body.find('tbody').empty();
			for (const row of r.message || []) {
				$tb.append(`<tr>
					<td>${esc(row.branch)}</td>
					<td><b>${esc(row.driver)}</b> ${esc(row.driver_name || '')}</td>
					<td><span class="dm-status" style="${STATUS_STYLE[row.status] || ''}">${esc(row.status)}</span></td>
					<td>${esc(row.nopol)}</td>
					<td>${dt(row.absensi)}</td>
					<td>${dt(row.checkin)}</td>
					<td>${row.packing_list ? `<a href="/app/packing-list/${encodeURIComponent(row.packing_list)}">${esc(row.packing_list)}</a>` : ''}</td>
					<td>${esc(row.do_no)}</td>
					<td>${esc(row.checkpoint)}</td>
				</tr>`);
			}
		});
	}

	load();
	const timer = setInterval(load, 60000);
	$(wrapper).on('remove', () => clearInterval(timer));
};

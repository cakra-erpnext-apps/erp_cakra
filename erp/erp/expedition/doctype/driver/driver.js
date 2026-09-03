frappe.ui.form.on('Driver', {
	refresh(frm) {
		render_history(frm);
	},
});

function render_history(frm) {
	const $w = frm.get_field('job_history').$wrapper.empty();
	if (frm.is_new()) {
		return $w.html(`<div class="text-muted">${__('Simpan dulu driver ini.')}</div>`);
	}
	const esc = frappe.utils.escape_html;
	const tgl = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 10)) : '-');

	frappe
		.call('erp.expedition.doctype.driver.driver.get_job_history', { driver: frm.doc.name })
		.then(({ message: rows }) => {
			if (!rows || !rows.length) {
				return $w.html(`<div class="text-muted">${__('Belum ada job.')}</div>`);
			}
			$w.html(`
				<style>
					/* 1 baris per job: kolom tidak melipat, yang panjang dipotong ellipsis
					   (teks penuh tetap ada di tooltip), tabel geser mendatar kalau sempit. */
					/* max-content: tabel boleh lebih lebar dari panel supaya bisa digeser mendatar */
					.drv-hist { width: max-content; min-width: 100%; }
					.drv-hist td, .drv-hist th { white-space: nowrap; vertical-align: middle; }
					.drv-hist td { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
				</style>
				<div style="overflow:auto"><table class="table table-sm drv-hist">
					<thead><tr>
						<th>No</th><th>Job No</th><th>Packing List</th><th>Customer</th>
						<th>Nopol</th><th>Container</th><th>ATD</th><th>ATA</th>
						<th>Checkpoint</th><th>Durasi</th><th>Status</th>
					</tr></thead>
					<tbody>${rows
						.map(
							(r, i) => `<tr>
						<td>${i + 1}</td>
						<td><a href="/app/dispatch-order/${encodeURIComponent(r.dpo)}">${esc(r.dpo_no || r.dpo)}</a></td>
						<td title="${esc(r.packing_list || '')}">${esc(r.packing_list || '-')}</td>
						<td title="${esc(r.customer || '')}">${esc(r.customer || '-')}</td>
						<td title="${esc(r.vehicle || '')}">${esc(r.vehicle || '-')}</td>
						<td>${esc([r.container_no, r.container_size].filter(Boolean).join(' ') || '-')}</td>
						<td>${tgl(r.atd)}</td>
						<td>${tgl(r.ata)}</td>
						<td title="${esc(r.checkpoint || '')}">${esc(r.checkpoint || '-')}</td>
						<td>${esc(r.durasi || '-')}</td>
						<td><span class="indicator-pill ${r.selesai ? 'green' : 'blue'}">${
							r.selesai ? __('Selesai') : __('On Job')
						}</span></td>
					</tr>`
						)
						.join('')}</tbody>
				</table></div>`);
		});
}

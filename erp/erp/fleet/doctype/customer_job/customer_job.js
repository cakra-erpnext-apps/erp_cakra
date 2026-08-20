frappe.ui.form.on('Customer Job', {
	refresh(frm) {
		if (frm.is_new()) return;
		// hidupkan / hentikan sharing langsung dari sini
		if (frm.doc.enabled) {
			frm.add_custom_button(__('Stop Sharing'), () =>
				frappe.confirm(__('Hentikan sharing? Link yang sudah dikirim langsung tidak bisa dibuka.'), () =>
					frm.set_value('enabled', 0).then(() => frm.save())
				)
			);
		} else {
			frm.add_custom_button(__('Aktifkan Sharing'), () => frm.set_value('enabled', 1).then(() => frm.save()));
		}
		frm.add_custom_button(__('Buka Halaman'), () => window.open(frm.doc.share_url, '_blank'));
		frm.add_custom_button(__('Salin Link'), () => {
			navigator.clipboard.writeText(frm.doc.share_url || '');
			frappe.show_alert({ message: __('Link tersalin'), indicator: 'green' });
		});
		// IP yang kena rate limit bisa dibuka lagi tanpa menunggu 1 jam
		frm.add_custom_button(__('Buka Blokir IP'), () => {
			const d = new frappe.ui.Dialog({
				title: __('Buka Blokir IP'),
				fields: [
					{ fieldtype: 'HTML', options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">
						Blokir hilang sendiri setelah 1 jam. Isi IP untuk membuka satu alamat saja,
						atau kosongkan untuk membersihkan semua catatan blokir.</div>` },
					{ fieldtype: 'Data', fieldname: 'ip', label: __('IP'), default: frm.doc.last_ip || '' },
				],
				primary_action_label: __('Buka Blokir'),
				primary_action: ({ ip }) =>
					frappe.call({ method: 'erp.fleet.customer_track.clear_block', args: { ip: ip || '' } }).then((r) => {
						d.hide();
						frappe.msgprint(r.message);
					}),
			});
			d.show();
		});
	},
});

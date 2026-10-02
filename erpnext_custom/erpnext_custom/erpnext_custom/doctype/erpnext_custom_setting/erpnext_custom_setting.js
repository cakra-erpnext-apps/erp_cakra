// Kolom Item Groups di tabel Invoice Type disimpan sebagai CSV (Small Text) karena child
// doctype tidak bisa punya Table MultiSelect — tabel bersarang tak didukung Frappe. Supaya
// bisa DIPILIH, bukan diketik, docfield-nya ditukar ke MultiSelect (kontrol Data +
// awesomplete, hasilnya CSV yang sama). Ditukar di ONLOAD dan SINKRON (daftar Item Group
// ikut boot): grid menyalin docfield saat render, jadi fieldtype + options harus sudah
// terpasang sebelum itu.
frappe.ui.form.on("ERPNext Custom Setting", {
	onload() {
		const df = frappe.meta.get_docfield("CMI Invoice Type", "item_groups");
		if (!df) return;
		df.fieldtype = "MultiSelect";
		df.options = (frappe.boot.cmi_item_groups || []).join("\n");
		// buang salinan per-baris dari kunjungan sebelumnya yang masih Small Text
		frappe.meta.docfield_copy["CMI Invoice Type"] = {};
	},

	// Tab Mailbox: pembuat signature perusahaan (drag and drop), lihat public/js/signature_builder.js.
	// Dipasang ulang sesudah Save/muat ulang supaya menampilkan susunan yang tersimpan.
	refresh(frm) {
		const field = frm.fields_dict.mailbox_signature_builder;
		if (!field) return;
		frappe.require("/assets/erpnext_custom/js/signature_builder.js", () => {
			if (frm.signature_builder && frm.signature_builder.$wrapper[0] === field.$wrapper[0]) {
				frm.signature_builder.load();
			} else {
				frm.signature_builder = new SignatureBuilder(frm, field.$wrapper);
			}
		});
	},

	mailbox_signature_company(frm) {
		if (frm.signature_builder && frm.doc.mailbox_signature_company) {
			frm.signature_builder.set_company(frm.doc.mailbox_signature_company);
		}
	},
});

// Tab Attachment: lokasi fisik lampiran (erpnext_custom/attachment_storage.py). Migrasi memakai
// folder yang SUDAH tersimpan, jadi simpan dulu kalau ada perubahan.
frappe.ui.form.on("ERPNext Custom Setting", {
	refresh(frm) {
		const field = frm.fields_dict.attachment_status_html;
		if (!field) return;
		frappe.call("erpnext_custom.attachment_storage.status").then(({ message: s }) => {
			const rows = Object.entries(s.parts)
				.map(([part, p]) => `<tr><td>${part}</td><td>${p.count}</td><td>${p.size}</td><td>${frappe.utils.escape_html(p.path)}</td></tr>`)
				.join("");
			const saved = (frm.doc.attachment_folder || "").trim();
			const notes = [];
			if (s.running) notes.push(__("An attachment job is running."));
			if (saved !== s.active)
				notes.push(__("Saved folder is not active yet. Click Copy & Migrate to move attachments there."));
			if (!s.root_mounted) notes.push(__("{0} is not mounted; only the default location is available.", [s.root]));
			field.$wrapper.html(`
				<p><b>${__("Active Location")}:</b> ${frappe.utils.escape_html(s.active || __("Default (site folder) {0}", [s.site_folder]))}</p>
				<table class="table table-bordered table-sm">
					<thead><tr><th></th><th>${__("Files")}</th><th>${__("Size")}</th><th>${__("Path")}</th></tr></thead>
					<tbody>${rows}</tbody>
				</table>
				<p>${__("Disk free")}: ${s.disk_free} / ${s.disk_total}</p>
				${notes.map((n) => `<p class="text-warning">${n}</p>`).join("")}
			`);
		});
	},

	async attachment_migrate(frm) {
		if (frm.is_dirty()) await frm.save();
		frappe.confirm(
			__("Copy all attachments to {0} and switch to it? The current files are kept.", [
				frm.doc.attachment_folder || __("the default site folder"),
			]),
			() =>
				frappe.call("erpnext_custom.attachment_storage.migrate").then((r) => {
					frappe.show_alert({ message: r.message, indicator: "blue" }, 7);
					frm.refresh();
				})
		);
	},

	attachment_delete_old(frm) {
		frappe.confirm(__("Permanently delete the old folders listed in Old Folders?"), () =>
			frappe.call("erpnext_custom.attachment_storage.delete_old").then((r) => {
				frappe.show_alert({ message: r.message, indicator: "blue" }, 7);
				frm.refresh();
			})
		);
	},
});

// Tab Ascend: sinkron CRM Estimation dengan SQL Server Ascend (crm_cakra/integrations/ascend.py).
// Keduanya memakai setting yang SUDAH tersimpan, jadi simpan dulu kalau ada perubahan.
frappe.ui.form.on("ERPNext Custom Setting", {
	async ascend_test_connection(frm) {
		if (frm.is_dirty()) await frm.save();
		frappe.call({
			method: "crm_cakra.integrations.ascend.test_connection",
			freeze: true,
			freeze_message: __("Menghubungi server Ascend..."),
			callback: (r) => r.message && frappe.msgprint({ title: __("Test Connection"), message: r.message, indicator: "green" }),
		});
	},

	async ascend_sync_now(frm) {
		if (frm.is_dirty()) await frm.save();
		frappe.call({
			method: "crm_cakra.integrations.ascend.sync_now",
			callback: (r) => r.message && frappe.show_alert({ message: r.message, indicator: "blue" }, 7),
		});
	},
});

// Kolom Item Groups di tabel Invoice Type disimpan sebagai CSV (Small Text) karena child
// doctype tidak bisa punya Table MultiSelect — tabel bersarang tak didukung Frappe. Supaya
// bisa DIPILIH, bukan diketik, docfield-nya ditukar ke MultiSelect (kontrol Data +
// awesomplete, hasilnya CSV yang sama). Ditukar di ONLOAD dan SINKRON (daftar Item Group
// ikut boot): grid menyalin docfield saat render, jadi fieldtype + options harus sudah
// terpasang sebelum itu.
frappe.ui.form.on("ERPNext Custom Setting", {
	onload() {
		// Item Category dan Roles: pilih + cari dari daftar (ikut boot, lihat item_scope.boot).
		const lists = { item_groups: frappe.boot.cmi_item_groups, roles: frappe.boot.cmi_roles };
		Object.entries(lists).forEach(([fieldname, options]) => {
			const df = frappe.meta.get_docfield("CMI Invoice Type", fieldname);
			if (!df) return;
			df.fieldtype = "MultiSelect";
			df.options = (options || []).join("\n");
		});
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

// Tab Ascend: koneksi SQL Server Ascend; list Estimation CRM membaca EXP_Estimation langsung
// (crm_cakra/integrations/ascend.py). Test memakai setting yang SUDAH tersimpan, jadi simpan dulu.
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
});

// Tab Desktop App: unggah installer aplikasi desktop (erpnext_custom/desktop_app.py). Tiga berkas
// dari desktop/dist dikirim per potongan 4 MB (installer ~110 MB melebihi batas request), lalu
// server mengecek sha512-nya terhadap latest.yml dan menyimpan 3 versi terakhir.
const DESKTOP_FILES = ["erp-desktop-setup.exe", "erp-desktop-setup.exe.blockmap", "latest.yml"];
const DESKTOP_CHUNK = 4 * 1024 * 1024;

frappe.ui.form.on("ERPNext Custom Setting", {
	refresh(frm) {
		const field = frm.fields_dict.desktop_app_html;
		if (!field) return;
		frappe.call("erpnext_custom.desktop_app.status").then(({ message: s }) => render_desktop_app(field.$wrapper, s));
	},
});

function render_desktop_app($w, s) {
	const esc = frappe.utils.escape_html;
	const mb = (n) => `${(n / 1024 / 1024).toFixed(1)} MB`;
	const rows = (s.versions || [])
		.map(
			(v) => `<tr><td>${esc(v.version)}${v.version === s.latest ? ` <span class="indicator-pill green">${__("Latest")}</span>` : ""}</td>
				<td>${mb(v.size)}</td><td>${esc(v.uploaded)}</td></tr>`
		)
		.join("");
	$w.html(`
		<div style="max-width: 720px">
			<table class="table table-bordered" style="margin-bottom: 12px">
				<thead><tr><th>${__("Version")}</th><th>${__("Size")}</th><th>${__("Uploaded")}</th></tr></thead>
				<tbody>${rows || `<tr><td colspan="3" class="text-muted">${__("No installer uploaded yet.")}</td></tr>`}</tbody>
			</table>
			<input type="file" multiple class="dsk-files" accept=".exe,.blockmap,.yml" style="display: none">
			<button class="btn btn-primary btn-sm dsk-upload">${__("Upload Installer")}</button>
			<span class="dsk-progress text-muted" style="margin-left: 10px"></span>
		</div>`);

	const $input = $w.find(".dsk-files");
	const $btn = $w.find(".dsk-upload");
	const $progress = $w.find(".dsk-progress");
	$btn.on("click", () => $input.val("").trigger("click"));
	$input.on("change", async () => {
		// Dikenali dari jenisnya, bukan namanya: installer sering diganti nama sebelum dibagikan
		// (mis. mail-v1.0.9.exe). Server menyimpannya dengan nama baku dan mencocokkan isinya
		// dengan sha512 di latest.yml, jadi berkas dari build lain tetap ditolak.
		const picked = Array.from($input[0].files);
		const pick = (test) => picked.filter((f) => test(f.name.toLowerCase()));
		const groups = [
			pick((n) => n.endsWith(".exe")),
			pick((n) => n.endsWith(".blockmap")),
			pick((n) => n.endsWith(".yml")),
		];
		if (groups.some((g) => g.length !== 1)) {
			return frappe.msgprint(
				__("Select exactly three files from desktop/dist: the installer (.exe), its .blockmap, and latest.yml.")
			);
		}
		const by_name = Object.fromEntries(DESKTOP_FILES.map((name, i) => [name, groups[i][0]]));
		const total = DESKTOP_FILES.reduce((n, name) => n + by_name[name].size, 0);
		const id = (Math.random().toString(36).slice(2) + Date.now().toString(36)).slice(0, 30);
		let sent = 0;
		$btn.prop("disabled", true);
		try {
			for (const name of DESKTOP_FILES) {
				const file = by_name[name];
				for (let offset = 0; offset < file.size || (offset === 0 && !file.size); offset += DESKTOP_CHUNK) {
					const body = new FormData();
					body.append("upload_id", id);
					body.append("name", name);
					body.append("offset", offset);
					body.append("chunk", file.slice(offset, offset + DESKTOP_CHUNK), name);
					const r = await fetch("/api/method/erpnext_custom.desktop_app.upload_chunk", {
						method: "POST",
						headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
						body,
					});
					if (!r.ok) throw new Error(await server_error(r));
					sent += Math.min(DESKTOP_CHUNK, file.size - offset);
					$progress.text(__("Uploading {0}%", [Math.floor((sent / total) * 100)]));
					if (!file.size) break;
				}
			}
			$progress.text(__("Checking and publishing..."));
			const { message: s } = await frappe.call({
				method: "erpnext_custom.desktop_app.publish",
				args: { upload_id: id },
				freeze: true,
			});
			render_desktop_app($w, s);
			frappe.show_alert(
				{
					message: s.removed && s.removed.length
						? __("Version {0} published. Removed: {1}", [s.published, s.removed.join(", ")])
						: __("Version {0} published", [s.published]),
					indicator: "green",
				},
				8
			);
		} catch (e) {
			$progress.text("");
			// Galat publish sudah ditampilkan frappe.call sendiri; yang sampai di sini sebagai Error
			// = galat unggah potongan.
			if (e instanceof Error) frappe.msgprint({ title: __("Upload failed"), message: esc(e.message), indicator: "red" });
		} finally {
			$btn.prop("disabled", false);
		}
	});
}

async function server_error(r) {
	try {
		const j = await r.json();
		const msgs = j._server_messages ? JSON.parse(j._server_messages).map((m) => JSON.parse(m).message) : [];
		return msgs.join(" ") || j.exception || r.statusText;
	} catch {
		return r.statusText;
	}
}

// Tab Workflow Access: Document Type hanya doctype yang memakai alur Validate/Void/Close
// (workflow.SUPPORTED, ikut boot). Server tetap menolak yang lain (validate_access_rows).
frappe.ui.form.on("ERPNext Custom Setting", {
	refresh(frm) {
		frm.set_query("document_type", "workflow_access", () => ({
			filters: { name: ["in", (frappe.boot.cmi_workflow || {}).supported || []] },
		}));
	},
});

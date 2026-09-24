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

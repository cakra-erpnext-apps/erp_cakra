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
});

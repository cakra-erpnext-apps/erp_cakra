// Bin Replan: instruksi menata ulang letak barang. Tidak menyentuh stok/jurnal —
// yang bergerak cuma LETAK barangnya, dan baru saat disetujui (submit).

// Nama rak dan bin panjang ("AA01A - Gudang Jakarta - CMI") karena harus unik
// lintas gudang. Yang dibaca orang cuma kodenya, dan gudangnya sudah tertulis di
// kepala dokumen — jadi di tabel mana pun tampilkan potongan pertamanya saja.
["Rack", "Bin Location"].forEach((doctype) => {
	frappe.form.link_formatters[doctype] = (value) => (value || "").split(" - ")[0];
});

// Kunci bin itu efek samping yang tidak kelihatan di form; katakan terus terang
// selama masih draft, supaya orang gudang tahu kenapa bin itu menolak barang.
const intro = (frm) =>
	frm.set_intro(
		frm.doc.docstatus === 0 && (frm.doc.items || []).some((r) => r.bin_location)
			? __("Bin asal dan bin tujuan di daftar ini TERKUNCI dari barang masuk sampai replan disetujui.")
			: "",
		"orange"
	);

frappe.ui.form.on("Bin Replan", {
	onload(frm) {
		frm.set_query("gudang", () => ({ filters: { is_group: 0 } }));
		["bin_location", "from_bin_location"].forEach((field) =>
			frm.set_query(field, "items", () => ({
				filters: { gudang: frm.doc.gudang || "", disabled: 0 },
			}))
		);
	},

	refresh: intro,

	gudang(frm) {
		// Ganti gudang = instruksi yang sudah ada tidak berlaku lagi.
		frm.clear_table("items");
		frm.refresh_field("items");
		intro(frm);
	},

	// Baca keadaan gudang sekarang lalu karang instruksinya: barang di tingkat atas
	// diturunkan, barang tua dimajukan ke tempat yang paling gampang digapai.
	// Tujuannya dipilih mesin yang sama dengan Recommendation di Goods Receive.
	plan_button(frm) {
		if (!frm.doc.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		if (!frm.doc.max_level && !frm.doc.min_age_days)
			return frappe.msgprint(__("Isi Tingkat Maksimal atau Umur Minimal — salah satu harus jadi alasan."));
		frappe.call({
			method: "erpnext_custom.replan.plan",
			args: {
				gudang: frm.doc.gudang,
				max_level: frm.doc.max_level || 0,
				min_age_days: frm.doc.min_age_days || 0,
			},
			freeze: true,
			freeze_message: __("Menyusun instruksi replan..."),
			callback(res) {
				const out = res.message || {};
				const rows = out.rows || [];
				const skipped = out.skipped || [];
				if (!rows.length)
					return frappe.msgprint({
						title: __("Tidak ada yang perlu dipindah"),
						message: skipped.length
							? skipped.join("<br>")
							: __(
									"Semua barang sudah di tingkat yang gampang digapai dan belum ada yang melewati batas umur."
							  ),
						indicator: skipped.length ? "orange" : "green",
					});
				frm.clear_table("items");
				rows.forEach((r) => Object.assign(frm.add_child("items"), r));
				frm.refresh_field("items");
				intro(frm);
				frappe.show_alert(
					__("{0} instruksi pindah dibuat. Centang kolom OK setelah barangnya dipindah.", [
						rows.length,
					])
				);
				if (skipped.length)
					frappe.msgprint({
						title: __("Sebagian dilewati"),
						message: skipped.join("<br>"),
						indicator: "orange",
					});
			},
		});
	},
});

// Bin Adjustment: koreksi isi bin. Beda dengan Goods Receive/Replan yang cuma
// memindahkan — yang ini betul-betul mengubah stok, lewat Stock Reconciliation
// yang dibuat otomatis saat divalidasi. Lihat erpnext_custom/bin_adjust.py.

// Nama rak dan bin panjang ("AA01A - Gudang Jakarta - CMI") karena harus unik
// lintas gudang. Yang dibaca orang cuma kodenya, dan gudangnya sudah tertulis di
// kepala dokumen.
["Rack", "Bin Location"].forEach((doctype) => {
	frappe.form.link_formatters[doctype] = (value) => (value || "").split(" - ")[0];
});

const intro = (frm) =>
	frm.set_intro(
		frm.doc.docstatus === 0 && (frm.doc.items || []).length
			? __(
					"Belum ada yang berubah. Letak bin dan stoknya baru bergerak saat dokumen ini DIVALIDASI."
			  )
			: "",
		"orange"
	);

frappe.ui.form.on("Bin Adjustment", {
	onload(frm) {
		frm.set_query("gudang", () => ({ filters: { is_group: 0 } }));
		const bin_di_gudang = () => ({
			filters: { gudang: frm.doc.gudang || "", disabled: 0 },
		});
		frm.set_query("load_bin", bin_di_gudang);
		frm.set_query("bin_location", "items", bin_di_gudang);
	},

	refresh: intro,

	gudang(frm) {
		frm.clear_table("items");
		frm.set_value("load_bin", null);
		frm.refresh_field("items");
		intro(frm);
	},

	// Tarik isi bin apa adanya, lalu orang gudang mengubah baris yang tidak cocok
	// dengan kenyataan dan menghapus sisanya. Menambah, bukan mengganti: satu
	// dokumen boleh mengoreksi beberapa bin sekaligus.
	load_button(frm) {
		if (!frm.doc.load_bin) return frappe.msgprint(__("Pilih bin dulu."));
		const sudah = new Set(
			(frm.doc.items || []).map((r) => `${r.item_code}|${r.bin_location}`)
		);
		frappe.call({
			method: "erpnext_custom.bin_adjust.bin_contents",
			args: { bin_location: frm.doc.load_bin },
			freeze: true,
			callback(res) {
				const rows = (res.message || []).filter(
					(r) => !sudah.has(`${r.item_code}|${r.bin_location}`)
				);
				if (!rows.length)
					return frappe.msgprint(
						__("Bin itu kosong, atau isinya sudah ada di tabel.")
					);
				rows.forEach((r) => Object.assign(frm.add_child("items"), r));
				frm.refresh_field("items");
				frm.set_value("load_bin", null);
				intro(frm);
				frappe.show_alert(
					__("{0} baris ditarik. Ubah Qty Sesudah / Ganti Item Ke, hapus baris yang sudah benar.", [
						rows.length,
					])
				);
			},
		});
	},
});

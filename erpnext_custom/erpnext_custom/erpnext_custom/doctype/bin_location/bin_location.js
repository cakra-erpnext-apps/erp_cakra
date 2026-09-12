// Bin Location: "Digabung Ke" dibatasi ke bin yang memang boleh jadi induk, supaya
// pilihannya tidak memuat seluruh bin semua gudang lalu ditolak waktu simpan.
frappe.ui.form.on("Bin Location", {
	onload(frm) {
		frm.set_query("merged_into", () => ({
			filters: {
				// validate menolak gabung beda rak, jadi difilter sampai rak -- bukan
				// cuma segudang (lihat _check_merge di bin_location.py).
				rack: frm.doc.rack || "",
				name: ["!=", frm.doc.name || ""],
				// bin yang sendirinya sudah digabung tidak boleh jadi induk
				merged_into: ["is", "not set"],
				disabled: 0,
			},
		}));
	},
});

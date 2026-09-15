// List Journal Entry defaultnya menampilkan SEMUA jurnal, termasuk yang dibuat otomatis
// oleh Expense Note, Pending Cash, depresiasi aset, dan seterusnya -- padahal yang
// dicari orang di menu ini cuma jurnal adjust yang mereka ketik sendiri. Penandanya
// `is_system_generated` (lihat erpnext_custom/journal_entry.py), saklarnya di ERPNext
// Custom Setting > tab Journal Entry.
//
// Filternya dipasang lewat onload, BUKAN lewat `listview_settings.filters`. Sebabnya
// list_view.js mendahulukan setelan list per user (__UserSettings), dan siapa pun yang
// pernah membuka list ini punya `"filters": []` tersimpan di sana -- array kosong tetap
// dihitung array, jadi cabang `listview_settings.filters` tidak pernah dijalankan dan
// filternya diam-diam tidak terpasang.
//
// Konsekuensinya setelan di atas yang berkuasa: chipnya boleh dibuang untuk melihat
// semua jurnal, tapi balik lagi saat halaman dibuka berikutnya.
(function () {
	const settings = (frappe.listview_settings["Journal Entry"] =
		frappe.listview_settings["Journal Entry"] || {});
	const previous_onload = settings.onload;

	settings.onload = function (listview) {
		previous_onload && previous_onload(listview);
		if (!frappe.boot.cmi_je_hide_system_generated) return;
		// Sudah dipasang manual oleh user? jangan ditimpa -- termasuk kalau dia sengaja
		// mencari yang otomatis (is_system_generated = 1).
		const sudah_ada = listview.filter_area
			.get()
			.some((f) => f[1] === "is_system_generated");
		if (sudah_ada) return;
		// refresh = false: onload jalan SEBELUM refresh pertama (list_view.js setup_view),
		// jadi filternya ikut di query pertama tanpa menembak server dua kali.
		listview.filter_area.add([["Journal Entry", "is_system_generated", "=", 0]], false);
	};
})();

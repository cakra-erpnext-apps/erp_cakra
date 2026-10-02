// Dokumen yang sudah dipakai dokumen lanjutan (erp/downstream_lock.py) = read-only.
// Server tetap menolak simpan; ini supaya user tidak mengetik dulu baru ditolak.
$(document).on("form-refresh", (e, frm) => {
	const refs = frm.doc.__onload && frm.doc.__onload.downstream_refs;
	if (!refs || !refs.length) return;
	frm.set_read_only();
	frm.disable_save();
	// Cukup nama modulnya; daftar nomor transaksi lanjutan terlalu panjang untuk banner.
	const modules = [...new Set(refs.map(([dt]) => __(dt)))].join(", ");
	frm.set_intro(
		__("{0} ini sudah digunakan pada modul {1}.", [frappe.utils.escape_html(frm.doc.name), modules]),
		"orange"
	);
});

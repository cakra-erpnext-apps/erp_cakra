// Dokumen yang sudah dipakai dokumen lanjutan (erp/downstream_lock.py) = read-only.
// Server tetap menolak simpan; ini supaya user tidak mengetik dulu baru ditolak.
$(document).on("form-refresh", (e, frm) => {
	const refs = frm.doc.__onload && frm.doc.__onload.downstream_refs;
	if (!refs || !refs.length) return;
	frm.set_read_only();
	frm.disable_save();
	const links = refs
		.slice(0, 10)
		.map(([dt, name]) => `<a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${__(dt)} ${name}</a>`)
		.join(", ");
	frm.set_intro(
		__("Terkunci: sudah dipakai di {0}. Lepas/batalkan dulu dari dokumen tersebut untuk merevisi.", [links]),
		"orange"
	);
});

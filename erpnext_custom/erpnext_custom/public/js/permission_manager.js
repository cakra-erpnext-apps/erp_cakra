// Role Permissions Manager: kolom "Cancel" ditampilkan sebagai "Void".
//
// Di CMI, izin Cancel pada Purchase Order / Purchase Receipt / Purchase Invoice
// dipakai sebagai izin Void & Unvoid (lihat erpnext_custom.workflow.PERM_GATED).
// Kolom Submit sudah tampil sebagai "Validate" lewat record Translation, tetapi
// cara yang sama TIDAK bisa dipakai untuk Cancel: kata itu juga dipakai tombol
// batal di setiap dialog Frappe, jadi menerjemahkannya akan mengubah seluruh
// aplikasi. Karena itu penggantian namanya dibatasi ke halaman ini saja.
//
// Yang diubah hanya LABEL. Nama field, nilai tersimpan, dan pengecekan izin tetap
// `cancel` — jadi tidak ada yang berubah selain kata yang terbaca admin.
//
// Di-inject lewat hook page_js["permission-manager"], yang jalan setelah script
// halaman mendefinisikan frappe.PermissionEngine tetapi sebelum instance-nya
// dibuat, jadi patch prototype ini selalu kepakai.
(function () {
	const PE = frappe.PermissionEngine;
	if (!PE || PE.prototype._cmi_cancel_label_patched) return;
	PE.prototype._cmi_cancel_label_patched = true;

	const original = PE.prototype.add_check;
	PE.prototype.add_check = function (cell, d, fieldname, label, description) {
		// label kosong = core menurunkannya dari fieldname; hanya kasus itu yang diganti.
		if (fieldname === "cancel" && !label) label = "Void";
		return original.call(this, cell, d, fieldname, label, description);
	};
})();

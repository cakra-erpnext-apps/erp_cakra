// Login gagal beruntun mengunci user selama "Allow Login After Fail" detik (System
// Settings). Tombol ini membukanya lebih awal, untuk karyawan yang memang salah ketik
// lalu lapor ke admin. Lihat erpnext_custom/login_lock.py.
frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role("System Manager")) return;
		frm.add_custom_button(
			__("Reset Kunci Login"),
			() =>
				frappe
					.call({
						method: "erpnext_custom.login_lock.unlock",
						args: { user: frm.doc.name },
						freeze: true,
					})
					.then((r) => {
						const cleared = r.message || [];
						frappe.msgprint({
							title: __("Reset Kunci Login"),
							indicator: cleared.length ? "green" : "blue",
							message: cleared.length
								? __("Kunci dibuka untuk: {0}", [cleared.join(", ")])
								: __("Tidak ada kunci aktif untuk user ini."),
						});
					}),
			__("Password")
		);
	},
});

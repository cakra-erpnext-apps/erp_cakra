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

		// Kunci salinan email Mailbox Local Mode di laptop user ini, untuk membukanya tanpa ERP
		// (mailbox_decrypt.html). Setiap ekspor tercatat di timeline user (outlook_addin).
		frm.add_custom_button(
			__("Export Mailbox Key"),
			() =>
				frappe.confirm(
					__("Export the Mailbox key of {0}? Whoever holds it can read this user's email copies on the laptop. The export is logged.", [
						frm.doc.name,
					]),
					() =>
						frappe
							.xcall("erpnext_custom.outlook_addin.export_mailbox_key", { user: frm.doc.name })
							.then((key) => {
								show_mailbox_key(frm.doc.name, key);
								frm.reload_doc();
							})
				),
			__("Password")
		);
	},
});

function show_mailbox_key(user, key) {
	const d = new frappe.ui.Dialog({
		title: __("Mailbox Key: {0}", [user]),
		fields: [
			{ fieldtype: "Code", fieldname: "key", label: __("Key"), read_only: 1, default: key },
			{ fieldtype: "HTML", fieldname: "help" },
		],
		primary_action_label: __("Copy Key"),
		primary_action: () => frappe.utils.copy_to_clipboard(key),
	});
	d.fields_dict.help.$wrapper.html(`
		<p>${__("Store this key somewhere safe, such as the company password manager.")}</p>
		<p>${__("To read the email copies without ERP: open the decrypt tool, choose the user's email folder and an output folder, then paste this key. The result is plain .eml files that open in Outlook.")}</p>
		<p><a href="/assets/erpnext_custom/mailbox_decrypt.html" download="mailbox_decrypt.html">${__(
			"Download decrypt tool (mailbox_decrypt.html)"
		)}</a></p>`);
	d.show();
}

// Daftar User > Menu > Export Mailbox Keys: kunci Mailbox Local Mode user yang dicentang (atau
// semua user yang punya kunci) jadi satu berkas CSV, yang bisa langsung dimuat alat
// mailbox_decrypt.html. Hanya System Manager; tiap user tercatat di timeline-nya
// (outlook_addin.export_mailbox_keys). onload bawaan Frappe dibungkus, tidak ditimpa.
(() => {
	const settings = (frappe.listview_settings["User"] = frappe.listview_settings["User"] || {});
	const onload = settings.onload;

	settings.onload = function (listview) {
		if (onload) onload.apply(this, arguments);
		if (!frappe.user.has_role("System Manager")) return;
		listview.page.add_menu_item(__("Export Mailbox Keys"), () =>
			export_keys(listview.get_checked_items(true))
		);
	};

	function export_keys(users) {
		const who = users.length
			? __("the {0} selected users", [users.length])
			: __("all users who have one");
		frappe.confirm(
			__("Export the Mailbox keys of {0}? Whoever holds the file can read those users' email copies. Every export is logged on each user.", [who]),
			() =>
				frappe
					.xcall("erpnext_custom.outlook_addin.export_mailbox_keys", { users: users.length ? users : null })
					.then(({ keys, missing }) => {
						if (keys.length) download(keys);
						frappe.msgprint({
							title: __("Export Mailbox Keys"),
							indicator: keys.length ? "green" : "orange",
							message:
								(keys.length === 1 ? __("1 key exported.") : __("{0} keys exported.", [keys.length])) +
								" " +
								__("Keep the file somewhere safe, such as the company password manager.") +
								(missing.length
									? "<br>" + __("No key yet (Local Mode never used): {0}", [frappe.utils.escape_html(missing.join(", "))])
									: ""),
						});
					})
		);
	}

	function download(keys) {
		const csv = ["user,email,key", ...keys.map((k) => [k.user, k.email || "", k.key].join(","))].join("\r\n");
		const a = document.createElement("a");
		a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
		a.download = `mailbox_keys_${frappe.datetime.get_today()}.csv`;
		a.click();
		setTimeout(() => URL.revokeObjectURL(a.href), 10000);
	}
})();

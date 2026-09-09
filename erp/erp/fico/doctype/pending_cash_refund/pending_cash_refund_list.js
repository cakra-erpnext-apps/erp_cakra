frappe.listview_settings["Pending Cash Refund"] = {
	add_fields: ["validated", "void", "journal_entry"],

	// Status: Draft (belum divalidasi) -> Refunded (jurnal terbit, uangnya kembali) ->
	// Void (dibatalkan, jurnal cancel-nya disimpan sebagai jejak).
	get_indicator(doc) {
		if (doc.void) return [__("Void"), "gray", "void,=,1"];
		if (doc.validated) return [__("Refunded"), "green", "validated,=,1"];
		return [__("Draft"), "orange", "validated,=,0"];
	},

	// Kolom PC memuat nomor kasbon yang dipotong refund ini — satu refund boleh menutup
	// beberapa kasbon sekaligus, jadi dirender "{no} +N" (helper di pending_cash_actions.js).
	formatters: {
		pending_cash_no(value) {
			return pc_doc_links(value, "Pending Cash");
		},
	},

	onload(listview) {
		pc_link_style();
		listview.page.add_actions_menu_item(
			__("Void"),
			() => {
				const docs = listview.get_checked_items();
				if (!docs.length) {
					frappe.msgprint(__("Pilih dulu refund yang mau di-void."));
					return;
				}
				frappe.confirm(
					__("Void {0} refund? Jurnalnya di-cancel (tetap disimpan sebagai jejak).", [docs.length]),
					() =>
						frappe
							.call({
								method: "erp.fico.doctype.pending_cash_refund.pending_cash_refund.bulk_void",
								args: { names: docs.map((d) => d.name) },
								freeze: true,
								freeze_message: __("Void..."),
							})
							.then((r) => {
								pc_report(r.message);
								listview.refresh();
							})
				);
			},
			true
		);
	},
};

// Pending Cash — list view: indikator status + aksi bulk.
// Tiap menu adalah SATU pasangan bolak-balik (Validate/Invalidate, Pay/Unpaid,
// Void/Unvoid); arahnya ditentukan per dokumen dari statusnya, lalu dikonfirmasi lewat
// dialog berisi daftar nomornya. Logikanya di pending_cash_actions.js (dipakai bareng
// form script), jadi dialog & pesannya persis sama dari mana pun aksinya dijalankan.

frappe.listview_settings["Pending Cash"] = {
	// Status ikut ditarik: pc_run_toggle memakainya untuk menentukan arah tiap dokumen.
	add_fields: ["validated", "paid", "void", "refunded_amount", "modul"],

	// Nomor sumber (Connection) & PV pemakainya. Formatter WAJIB mengembalikan HTML
	// (diawali "<"): list_view.js melakukan `$(html)`, dan string biasa dianggap selector.
	formatters: {
		// Source No = Dynamic Link: doctype-nya menyusul field `modul` di baris itu.
		number(value, df, doc) {
			return doc.modul ? pc_doc_links(value, doc.modul) : "<span></span>";
		},
		payment_no(value) {
			return pc_doc_links(value, "Payment Entry");
		},
	},

	get_indicator(doc) {
		if (doc.void) return [__("Void"), "gray", "void,=,1"];
		if (doc.paid) return [__("Paid"), "green", "paid,=,1"];
		if (doc.validated) return [__("Validated"), "blue", "validated,=,1"];
		return [__("Draft"), "orange", "validated,=,0"];
	},

	onload(listview) {
		pc_link_style();
		const action = (kind) => () => pc_list_action(listview, kind);
		listview.page.add_actions_menu_item(__("Validate / Invalidate"), action("validate"), true);
		listview.page.add_actions_menu_item(__("Pay / Unpaid"), action("pay"), true);
		listview.page.add_actions_menu_item(__("Void / Unvoid"), action("void"), true);
		// Refund berdiri sendiri (bisa berulang, tiap kali jadi dokumen Pending Cash Refund):
		// dari list selalu SELURUH SISA — nominal per dokumen berbeda, jadi refund sebagian
		// dilakukan dari formnya.
		listview.page.add_actions_menu_item(
			__("Refund"),
			() => pc_run_action("refund", listview.get_checked_items(), () => listview.refresh()),
			true
		);
	},
};

function pc_list_action(listview, kind) {
	const docs = listview.get_checked_items();
	if (!docs.length) {
		frappe.msgprint(__("Pilih dulu Pending Cash yang mau diproses."));
		return;
	}
	pc_run_toggle(kind, docs, () => listview.refresh());
}

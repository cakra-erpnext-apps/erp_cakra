// Pending Cash — list view: indikator status + aksi bulk.
// Tiap menu adalah SATU pasangan bolak-balik (Validate/Invalidate, Pay/Unpaid,
// Void/Unvoid); arahnya ditentukan per dokumen dari statusnya, lalu dikonfirmasi lewat
// dialog berisi daftar nomornya. Logikanya di pending_cash_actions.js (dipakai bareng
// form script), jadi dialog & pesannya persis sama dari mana pun aksinya dijalankan.
frappe.listview_settings["Pending Cash"] = {
	// Status ikut ditarik: pc_run_toggle memakainya untuk menentukan arah tiap dokumen.
	add_fields: ["validated", "paid", "void"],

	get_indicator(doc) {
		if (doc.void) return [__("Void"), "gray", "void,=,1"];
		if (doc.paid) return [__("Paid"), "green", "paid,=,1"];
		if (doc.validated) return [__("Validated"), "blue", "validated,=,1"];
		return [__("Draft"), "orange", "validated,=,0"];
	},

	onload(listview) {
		const action = (kind) => () => pc_list_action(listview, kind);
		listview.page.add_actions_menu_item(__("Validate / Invalidate"), action("validate"), true);
		listview.page.add_actions_menu_item(__("Pay / Unpaid"), action("pay"), true);
		listview.page.add_actions_menu_item(__("Void / Unvoid"), action("void"), true);
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

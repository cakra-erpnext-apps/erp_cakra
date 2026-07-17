// Pending Cash — list view: indikator status + aksi bulk Validate / Pay.
// pc_confirm_validate / pc_prompt_pay / pc_report dipakai bareng dengan form script
// (pending_cash.js), jadi dialog & pesannya persis sama dari mana pun aksinya dijalankan.
frappe.listview_settings["Pending Cash"] = {
	add_fields: ["validated", "paid", "void"],

	get_indicator(doc) {
		if (doc.void) return [__("Void"), "gray", "void,=,1"];
		if (doc.paid) return [__("Paid"), "green", "paid,=,1"];
		if (doc.validated) return [__("Validated"), "blue", "validated,=,1"];
		return [__("Draft"), "orange", "validated,=,0"];
	},

	onload(listview) {
		listview.page.add_actions_menu_item(__("Validate"), () => pc_list_action(listview, "validate"), true);
		listview.page.add_actions_menu_item(__("Pay"), () => pc_list_action(listview, "pay"), true);
	},
};

function pc_list_action(listview, action) {
	const names = listview.get_checked_items(true);
	if (!names.length) {
		frappe.msgprint(__("Pilih dulu Pending Cash yang mau diproses."));
		return;
	}
	const done = () => listview.refresh();
	if (action === "validate") pc_confirm_validate(names, done);
	else pc_prompt_pay(names, done);
}

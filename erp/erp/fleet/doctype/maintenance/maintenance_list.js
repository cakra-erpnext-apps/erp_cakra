frappe.listview_settings["Maintenance"] = {
	add_fields: ["validated", "void", "finish_date"],
	get_indicator(doc) {
		if (doc.void) return [__("Void"), "red", "void,=,1"];
		if (doc.validated) return [__("Validated"), "green", "validated,=,1"];
		return [__("Draft"), "gray", "validated,=,0"];
	},
};

// List view Pending Cash Type: aktif/tidaknya tampil sebagai badge Status (klik = filter),
// bukan sebagai kolom centang tersendiri.
frappe.listview_settings["Pending Cash Type"] = {
	add_fields: ["enabled"],

	get_indicator(doc) {
		return doc.enabled
			? [__("Enabled"), "green", "enabled,=,1"]
			: [__("Disabled"), "gray", "enabled,=,0"];
	},
};

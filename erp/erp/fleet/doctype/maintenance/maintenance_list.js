frappe.listview_settings["Maintenance"] = {
	get_indicator: (doc) =>
		doc.finish_date
			? [__("Selesai"), "green", "finish_date,is,set"]
			: [__("Di Bengkel"), "orange", "finish_date,is,not set"],
};

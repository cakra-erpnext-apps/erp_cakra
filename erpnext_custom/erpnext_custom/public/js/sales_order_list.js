// Sales Order list: kolom diatur List View Settings (install.SO_LIST_COLUMNS);
// file ini hanya merender kolom placeholder, pola yang sama dengan purchase_order_list.js.
(function () {
	const settings = frappe.listview_settings["Sales Order"] || {};

	// owner/creation/modified_by/modified bukan meta.fields -> ditarik lewat add_fields
	// lalu dirender ke placeholder custom_created_* / custom_modified_*.
	settings.add_fields = [...new Set([
		...(settings.add_fields || []),
		"owner", "creation", "modified_by", "modified",
	])];
	// Formatter WAJIB mengembalikan HTML (lihat catatan di purchase_order_list.js).
	const cmi_txt = (s) => `<span>${frappe.utils.escape_html(s == null ? "" : String(s))}</span>`;
	const user_txt = (u) => cmi_txt(frappe.user.full_name(u) || u || "");
	const date_txt = (v) => cmi_txt(v ? frappe.datetime.str_to_user(v) : "");
	// Kolom daftar dokumen: "NOMOR +sisa", tooltip memuat semuanya, diklik -> list tujuan
	// terfilter ke SO baris ini (handler di bawah). Pola docs_txt di purchase_order_list.js.
	const docs_txt = (raw, so, cls) => {
		const names = (raw || "").split(",").map((v) => v.trim()).filter(Boolean);
		if (!names.length) return cmi_txt("");
		const esc = frappe.utils.escape_html;
		const label = names.length > 1 ? `${esc(names[0])} +${names.length - 1}` : esc(names[0]);
		return `<a href="#" class="${cls}" data-so="${esc(so)}"
			title="${esc(names.join(", "))}">${label}</a>`;
	};
	settings.formatters = Object.assign(settings.formatters || {}, {
		custom_dn_nos: (value, df, doc) => docs_txt(doc.custom_dn_nos, doc.name, "cmi-so-dn"),
		custom_si_nos: (value, df, doc) => docs_txt(doc.custom_si_nos, doc.name, "cmi-so-si"),
		custom_created_by: (value, df, doc) => user_txt(doc.owner),
		custom_created_date: (value, df, doc) => date_txt(doc.creation),
		custom_modified_by: (value, df, doc) => user_txt(doc.modified_by),
		custom_modified_date: (value, df, doc) => date_txt(doc.modified),
	});

	// route_options "Child DocType.fieldname" = filter ke tabel anak (list_view.parse_filters_from_route_options).
	const open_list = (doctype, filter) => (e) => {
		e.preventDefault();
		e.stopPropagation();
		frappe.route_options = { [filter]: $(e.currentTarget).attr("data-so") };
		frappe.set_route("List", doctype);
	};
	$(document)
		.off("click.cmi_so_dn")
		.on("click.cmi_so_dn", "a.cmi-so-dn", open_list("Delivery Note", "Delivery Note Item.against_sales_order"))
		.off("click.cmi_so_si")
		.on("click.cmi_so_si", "a.cmi-so-si", open_list("Sales Invoice", "Sales Invoice Item.sales_order"));

	frappe.listview_settings["Sales Order"] = settings;
})();

// Purchase Invoice list: CMI Validate/Invalidate and Void/Unvoid actions.
(function () {
	const settings = frappe.listview_settings["Purchase Invoice"] || {};
	const previous_onload = settings.onload;
	const previous_refresh = settings.refresh;

	if (!frappe.views.ListView.prototype._cmi_pi_actions_patched) {
		const native_get_actions = frappe.views.ListView.prototype.get_actions_menu_items;
		frappe.views.ListView.prototype.get_actions_menu_items = function () {
			const items = native_get_actions.call(this);
			if (this.doctype !== "Purchase Invoice") return items;
			const native_labels = new Set([__("Submit"), __("Validate"), __("Cancel")]);
			return items.filter((item) => !native_labels.has(item.label));
		};
		frappe.views.ListView.prototype._cmi_pi_actions_patched = true;
	}

	// owner/creation/modified_by/modified bukan bagian dari meta.fields sehingga tidak bisa
	// jadi kolom list; ditarik lewat add_fields lalu dirender ke placeholder custom_*
	// (pola yang sama dipakai Purchase Order). grand_total/outstanding_amount dipakai Paid %.
	settings.add_fields = [...new Set([
		...(settings.add_fields || []),
		"docstatus", "owner", "creation", "modified_by", "modified",
		"grand_total", "outstanding_amount",
	])];
	// Formatter WAJIB mengembalikan HTML (diawali "<"): list_view.js menjalankan
	// $(column_html), dan string polos ("01-09-2026", "35%") dibaca jQuery sebagai CSS
	// selector -> throw -> SELURUH baris list tidak dirender (lihat sales_invoice_list.js).
	const cmi_txt = (s) => `<span>${frappe.utils.escape_html(s == null ? "" : String(s))}</span>`;
	const user_txt = (u) => cmi_txt(frappe.user.full_name(u) || u || "");
	const date_txt = (v) => cmi_txt(v ? frappe.datetime.str_to_user(v) : "");
	settings.formatters = Object.assign(settings.formatters || {}, {
		custom_created_by: (value, df, doc) => user_txt(doc.owner),
		custom_created_date: (value, df, doc) => date_txt(doc.creation),
		custom_modified_by: (value, df, doc) => user_txt(doc.modified_by),
		custom_modified_date: (value, df, doc) => date_txt(doc.modified),
		// Paid % dihitung di sini (bukan disimpan) supaya ikut berubah begitu PE dibayar
		// atau dibatalkan. Draft tanpa nilai -> kosong, bukan "0%" yang menyesatkan.
		custom_paid_percent(value, df, doc) {
			const total = flt(doc.grand_total);
			if (!total) return cmi_txt("");
			const pct = ((total - flt(doc.outstanding_amount)) / total) * 100;
			return cmi_txt(`${flt(pct, 0)}%`);
		},
		// Klik nomor pembayaran -> list Payment Entry yang difilter ke PI ini. Filternya
		// lewat child table (Payment Entry Reference), jadi tetap benar walau kolom
		// custom_payment_no belum sempat tersinkron.
		custom_payment_no(value, df, doc) {
			if (!value) return cmi_txt("");
			return `<a href="#" class="cmi-pi-payments" data-pi="${frappe.utils.escape_html(doc.name)}"
				>${frappe.utils.escape_html(value)}</a>`;
		},
	});
	settings.hide_name_column = true;
	// Kotak ID bawaan diganti kotak Search (satu kata kunci untuk semua kolom).
	settings.hide_name_filter = true;

	if (!window._cmi_pi_payment_click) {
		window._cmi_pi_payment_click = true;
		$(document).on("click", "a.cmi-pi-payments", function (e) {
			e.preventDefault();
			e.stopPropagation();
			frappe.set_route("List", "Payment Entry", {
				"Payment Entry Reference.reference_name": $(this).data("pi"),
			});
		});
	}
	settings.get_indicator = function (doc) {
		if (cint(doc.docstatus) === 2) return [__("Void"), "red", "docstatus,=,2"];
		if (cint(doc.docstatus) === 1) return [__("Validate"), "blue", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	};
	// --- Kotak Search: satu kata kunci, dicocokkan ke SEMUA kolom sekaligus ---
	// Filter bawaan Frappe selalu AND per field, jadi dipakai `or_filters` yang disuntik ke
	// get_args milik instance list ini (pola yang sama dipakai Purchase Order).
	const SEARCH_FIELDS = [
		"name", "title", "supplier", "supplier_name", "custom_type", "posting_date",
		"currency", "conversion_rate", "custom_amount_total", "custom_tax_amount",
		"custom_net_total", "custom_payment_no", "custom_validated_by",
	];

	function cmi_pi_search(listview) {
		if (listview._cmi_search_ready) return;
		listview._cmi_search_ready = true;

		const field = listview.page.add_field({
			fieldname: "cmi_pi_search",
			fieldtype: "Data",
			label: __("Search"),
			placeholder: __("Cari di semua kolom"),
			change() {
				const q = (field.get_value() || "").trim();
				if (q === (listview._cmi_q || "")) return;
				listview._cmi_q = q;
				listview.start = 0;
				listview.refresh();
			},
		});

		const native_get_args = listview.get_args.bind(listview);
		listview.get_args = function () {
			const args = native_get_args();
			const q = listview._cmi_q;
			if (q) {
				args.or_filters = SEARCH_FIELDS.map((f) => [listview.doctype, f, "like", `%${q}%`]);
			}
			return args;
		};
	}

	settings.onload = function (listview) {
		if (typeof previous_onload === "function") previous_onload(listview);
		window.cmi_workflow_list_actions(listview, "Purchase Invoice", __("Purchase Invoice"));
		cmi_pi_search(listview);
	};
	settings.refresh = function (listview) {
		if (typeof previous_refresh === "function") previous_refresh(listview);
		window.cmi_workflow_list_actions(listview, "Purchase Invoice", __("Purchase Invoice"));
	};
	frappe.listview_settings["Purchase Invoice"] = settings;
})();

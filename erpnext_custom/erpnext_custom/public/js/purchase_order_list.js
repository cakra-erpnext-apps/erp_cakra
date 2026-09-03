// Purchase Order list actions use the shared CMI workflow endpoints.
(function () {
	const settings = frappe.listview_settings["Purchase Order"] || {};
	const previous_onload = settings.onload;
	const previous_refresh = settings.refresh;

	// Filter menu pada sumber datanya, sebelum DOM dibuat. Ini aman untuk render
	// List View dan hanya berlaku saat instance-nya adalah Purchase Order.
	if (!frappe.views.ListView.prototype._cmi_po_actions_patched) {
		const native_get_actions = frappe.views.ListView.prototype.get_actions_menu_items;
		frappe.views.ListView.prototype.get_actions_menu_items = function () {
			const items = native_get_actions.call(this);
			if (this.doctype !== "Purchase Order") return items;
			const native_labels = new Set([__("Submit"), __("Validate"), __("Cancel")]);
			return items.filter((item) => !native_labels.has(item.label));
		};
		frappe.views.ListView.prototype._cmi_po_actions_patched = true;
	}

	// owner/creation/modified_by/modified bukan bagian dari meta.fields, jadi tidak bisa
	// jadi kolom list. Nilainya ditarik lewat add_fields lalu dirender ke placeholder
	// custom_created_by / custom_created_date / custom_modified_by / custom_modified_date
	// (pola yang sama dipakai Sales Invoice).
	settings.add_fields = [...new Set([
		...(settings.add_fields || []),
		"docstatus", "owner", "creation", "modified_by", "modified",
	])];
	// Formatter WAJIB mengembalikan HTML (diawali "<"): list_view.js menjalankan
	// $(column_html), dan string polos ("01-09-2026", "35%") dibaca jQuery sebagai CSS
	// selector -> throw -> SELURUH baris list tidak dirender (lihat sales_invoice_list.js).
	const cmi_txt = (s) => `<span>${frappe.utils.escape_html(s == null ? "" : String(s))}</span>`;
	const user_txt = (u) => cmi_txt(frappe.user.full_name(u) || u || "");
	const date_txt = (v) => cmi_txt(v ? frappe.datetime.str_to_user(v) : "");
	settings.hide_name_column = true;
	// Quick filter "ID" bawaan tidak dipakai — pencarian nomor sudah tercakup kotak Search.
	settings.hide_name_filter = true;
	settings.formatters = Object.assign(settings.formatters || {}, {
		// Kolom "Purchases": daftar PI milik PO ini. Diklik -> list Purchase Invoice
		// yang sudah terfilter ke PO tersebut (lihat handler cmi-po-invoices di bawah).
		custom_purchases: (value, df, doc) => {
			const names = (doc.custom_purchases || "").split(",").map((v) => v.trim()).filter(Boolean);
			if (!names.length) return "";
			const esc = frappe.utils.escape_html;
			const label = names.length > 1 ? `${esc(names[0])} +${names.length - 1}` : esc(names[0]);
			return `<a href="#" class="cmi-po-invoices" data-po="${esc(doc.name)}"
				title="${esc(names.join(", "))}">${label}</a>`;
		},
		custom_created_by: (value, df, doc) => user_txt(doc.owner),
		custom_created_date: (value, df, doc) => date_txt(doc.creation),
		custom_modified_by: (value, df, doc) => user_txt(doc.modified_by),
		custom_modified_date: (value, df, doc) => date_txt(doc.modified),
	});
	settings.get_indicator = function (doc) {
		if (cint(doc.docstatus) === 2) return [__("Void"), "red", "docstatus,=,2"];
		if (cint(doc.docstatus) === 1) return [__("Validate"), "blue", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	};

	// --- Kotak Search: satu kata kunci, dicocokkan ke SEMUA kolom sekaligus ---
	// Filter bawaan Frappe selalu AND per field. Untuk "cari di mana saja" dipakai
	// `or_filters` (didukung frappe.desk.reportview) yang disuntik ke get_args milik
	// instance list ini — bukan menambal ListView global.
	const SEARCH_FIELDS = [
		"name", "supplier", "supplier_name", "transaction_date", "currency",
		"conversion_rate", "custom_amount_total", "custom_tax_amount", "custom_net_total",
		"custom_validated_by", "custom_purchases", "per_received", "per_billed",
	];

	// Klik kolom Purchases -> list Purchase Invoice terfilter ke PO baris itu.
	// `frappe.route_options` dibaca list_view.parse_filters_from_route_options, yang
	// mengenali kunci "Child DocType.fieldname" -> filter ke tabel anak. Handler-nya
	// didelegasikan ke document karena baris list dirender ulang tiap refresh.
	$(document)
		.off("click.cmi_po_invoices")
		.on("click.cmi_po_invoices", "a.cmi-po-invoices", function (e) {
			e.preventDefault();
			e.stopPropagation();
			frappe.route_options = {
				"Purchase Invoice Item.purchase_order": $(this).attr("data-po"),
			};
			frappe.set_route("List", "Purchase Invoice");
		});

	// --- Lebar kolom Title (Subject) ---
	// Frappe memberi tiap kolom `flex: 1` dan kolom Subject (`.list-subject`) `flex: 2`,
	// jadi lebarnya = 2/(2+jumlah kolom lain) lalu dipotong `.ellipsis`. Subject PO memuat
	// "PO/FJMT/CMI/2026/0001 - PT Astra Internasional" (~46 karakter), jadi lebarnya
	// dikunci di sini khusus list Purchase Order; kolom lain membagi sisa ruang rata.
	function cmi_po_subject_width(listview) {
		if (!document.getElementById("cmi-po-list-style")) {
			const style = document.createElement("style");
			style.id = "cmi-po-list-style";
			style.textContent = `
				.cmi-po-list .list-subject { flex: 0 0 320px; }
				.cmi-po-list .list-row-col { min-width: 0; }
			`;
			document.head.appendChild(style);
		}
		listview.page.main.addClass("cmi-po-list");
	}

	// make_standard_filters SELALU menambahkan quick filter untuk title_field dan tidak
	// menyediakan flag untuk mematikannya (beda dengan hide_name_filter). Jadi kotaknya
	// dibuang di sini; ia juga dilepas dari fields_dict supaya tidak ikut jadi filter query.
	function cmi_po_drop_title_filter(listview) {
		const fieldname = listview.meta && listview.meta.title_field;
		const control = fieldname && listview.page.fields_dict[fieldname];
		if (!control) return;
		control.$wrapper.closest(".col-md-2").addBack(".col-md-2").first().remove();
		delete listview.page.fields_dict[fieldname];
	}

	function cmi_po_search(listview) {
		if (listview._cmi_search_ready) return;
		listview._cmi_search_ready = true;

		// JANGAN pakai page.add_field: itu mendaftarkan kontrol ke page.fields_dict, dan
		// FilterArea.get_standard_filters() menjadikan SETIAP isi fields_dict sebagai filter
		// query -> "Field not permitted in query: cmi_po_search".
		// Selain itu parent-nya HARUS .standard-filter-section (tempat quick filter bawaan
		// dirender); kalau ditaruh langsung di page_form, kotaknya jadi kolom Bootstrap
		// tersendiri di luar barisan dan jaraknya kacau. Markupnya disamakan persis dengan
		// add_field: class col-md-2 pada wrapper kontrol.
		listview.page.show_form && listview.page.show_form();
		const section = listview.page.page_form.find(".standard-filter-section");
		const parent = section.length ? section : listview.page.page_form;
		const field = frappe.ui.form.make_control({
			df: {
				fieldname: "cmi_po_search",
				fieldtype: "Data",
				label: __("Search"),
				placeholder: __("Search All"),
				input_class: "input-xs",
				change() {
					const q = (field.get_value() || "").trim();
					if (q === (listview._cmi_q || "")) return;
					listview._cmi_q = q;
					listview.start = 0;
					listview.refresh();
				},
			},
			parent: parent,
			only_input: true,
			render_input: true,
		});
		$(field.wrapper).addClass("col-md-2 cmi-po-search").prependTo(parent);
		field.refresh();

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
		window.cmi_workflow_list_actions(listview, "Purchase Order", __("Purchase Order"));
		cmi_po_search(listview);
		cmi_po_subject_width(listview);
		cmi_po_drop_title_filter(listview);
	};
	settings.refresh = function (listview) {
		if (typeof previous_refresh === "function") previous_refresh(listview);
		window.cmi_workflow_list_actions(listview, "Purchase Order", __("Purchase Order"));
		cmi_po_drop_title_filter(listview);
	};

	frappe.listview_settings["Purchase Order"] = settings;
})();

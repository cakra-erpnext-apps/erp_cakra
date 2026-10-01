// Kolom list "Source No" (custom_shipping_list_nos) di Sales Invoice & Proforma Invoice:
// isinya nomor Shipping List + Packing List dipisah koma. Tiap nomor jadi tautan ke list
// view modulnya, tersaring ke nomor itu. Jenisnya dari awalan nomor (naming series
// PL/... = Packing List, SH/... = Shipping List); selain PL/ dianggap Shipping List karena
// kolom ini dulunya memang cuma berisi Shipping List.
// Dimuat untuk list kedua doctype (hooks doctype_list_js), jadi berkas ini jalan dua kali:
// penjaga di bawah mencegah handler klik terdaftar dobel.
window.cmi_source_no_html = function (value) {
	const esc = frappe.utils.escape_html;
	const nos = String(value || "").split(",").map((s) => s.trim()).filter(Boolean);
	const links = nos.map((no) => {
		const dt = no.startsWith("PL/") ? "Packing List" : "Shipping List";
		return `<a href="#" class="cmi-source-no" data-dt="${esc(dt)}" data-no="${esc(no)}">${esc(no)}</a>`;
	});
	return `<span class="ellipsis" title="${esc(nos.join(", "))}">${links.join(", ")}</span>`;
};

// preventDefault + stopPropagation WAJIB: tanpa itu klik diteruskan ke baris list dan yang
// terbuka malah invoicenya (pola sama dengan kolom Payment, sales_invoice_list.js).
if (!window._cmi_source_no_click) {
	window._cmi_source_no_click = true;
	$(document).on("click", "a.cmi-source-no", function (e) {
		e.preventDefault();
		e.stopPropagation();
		frappe.set_route("List", $(this).data("dt"), { name: String($(this).data("no")) });
	});
}

(function () {
	const base = frappe.listview_settings["Proforma Invoice"] || {};
	base.formatters = Object.assign(base.formatters || {}, {
		custom_shipping_list_nos: (value) => cmi_source_no_html(value),
	});
	frappe.listview_settings["Proforma Invoice"] = base;
})();

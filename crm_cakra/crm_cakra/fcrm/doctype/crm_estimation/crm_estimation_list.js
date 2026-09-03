// List view desk untuk CRM Estimation (/app/crm-estimation).
//
// CONTOH LENGKAP pola list view CMI — salin file ini untuk doctype lain (mis. Packing List):
//   1. add_fields   -> tarik kolom yang dipakai indikator & aksi bulk (tidak jadi kolom sendiri)
//   2. get_indicator-> badge status; string ke-3 = filter yang dipasang saat badge diklik
//   3. formatters   -> render kolom tampilan (created_by) dari field standar Frappe (owner)
//   4. onload/refresh -> pasang aksi bulk dari erpnext_custom (workflow_list.js, app_include_js)
//
// Urutan & pilihan KOLOM tidak diatur di sini: kolom berasal dari in_list_view di
// crm_estimation.json, urutannya dari record List View Settings "CRM Estimation"
// (dibuat di crm_cakra/install.py). Lihat catatan di sana.

frappe.listview_settings["CRM Estimation"] = {
	// `validated` & `disabled` dipakai get_indicator DAN aksi bulk untuk menentukan arah
	// tiap dokumen — tanpa ini get_checked_items() mengembalikan baris tanpa field tsb
	// dan semua dokumen dianggap belum tervalidasi/aktif.
	add_fields: ["validated", "disabled", "owner"],

	// PENTING: formatter WAJIB mengembalikan HTML (diawali "<"), bukan teks polos.
	// list_view.js melakukan `$(column_html)` — string yang tidak diawali "<" dianggap
	// CSS SELECTOR oleh jQuery. Nilai seperti email ("a@b.com") bukan selector valid ->
	// jQuery throw -> render list MATI (list kosong padahal datanya ada). Ini terjadi
	// saat user tak punya Full Name, karena frappe.user.full_name() jatuh ke email.
	formatters: {
		created_by(value, df, doc) {
			const u = frappe.user.full_name(doc.owner) || doc.owner || "";
			return "<span>" + frappe.utils.escape_html(u) + "</span>";
		},
		validated_by(value) {
			const u = value ? frappe.user.full_name(value) || value : "";
			return "<span>" + frappe.utils.escape_html(u) + "</span>";
		},
	},

	// Disabled menang atas Validated: estimasi yang dimatikan memang tidak boleh dipakai
	// lagi, apa pun status validasinya — menampilkan "Validated" di situ menyesatkan.
	get_indicator(doc) {
		if (doc.disabled) return [__("Disabled"), "gray", "disabled,=,1"];
		if (doc.validated) return [__("Validated"), "green", "validated,=,1"];
		return [__("Draft"), "orange", "validated,=,0"];
	},

	// Dipanggil dari onload DAN refresh: saat `onload`, `listview.page` bisa belum siap.
	// Kedua fungsi di bawah menjaga dirinya sendiri (cek page + pasang sekali saja).
	onload(listview) {
		this.setup_actions(listview);
	},
	refresh(listview) {
		this.setup_actions(listview);
	},
	setup_actions(listview) {
		// checkbox: true -> state dibaca dari kolom `validated` (CRM Estimation terdaftar
		// di CHECKBOX pada erpnext_custom/workflow.py), bukan dari docstatus.
		// void: false -> doctype ini tidak punya field `void`, jadi menunya tidak dipasang.
		window.cmi_workflow_list_actions &&
			window.cmi_workflow_list_actions(listview, "CRM Estimation", __("Estimation"), {
				checkbox: true,
				void: false,
			});
		window.cmi_disable_list_actions &&
			window.cmi_disable_list_actions(listview, "CRM Estimation", __("Estimation"));
	},
};

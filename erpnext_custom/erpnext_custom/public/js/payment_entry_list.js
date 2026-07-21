// List View Payment Entry:
// - Menu Actions: "Validate / Invalidate" & "Void / Unvoid" — logikanya di
//   public/js/workflow_list.js (dipakai bareng Sales Invoice), server-nya
//   erpnext_custom.workflow, jadi role & guard-nya identik dengan aksi satuan.
// - Badge status memakai istilah CMI (Draft / Validated / Void), bukan Submitted/Cancelled.
//
// Kolom & urutannya BUKAN di sini — diatur install._setup_payment_entry_list_columns
// (in_list_view + List View Settings), supaya sama untuk semua user.
//
// ERPNext sudah punya payment_entry_list.js sendiri (membatasi pilihan Party Type di filter
// sidebar) dan file itu dimuat LEBIH DULU (frappe/desk/form/meta.py: _add_code lalu
// add_code_via_hook). Jadi settings-nya di-EXTEND, bukan ditimpa — menimpa berarti diam-diam
// membuang perilaku bawaannya.
(function () {
	const prev = frappe.listview_settings["Payment Entry"] || {};

	frappe.listview_settings["Payment Entry"] = Object.assign({}, prev, {
		add_fields: (prev.add_fields || []).concat(["docstatus"]),
		get_indicator: cmi_workflow_indicator,

		onload(listview) {
			if (prev.onload) prev.onload(listview);
			cmi_workflow_list_actions(listview, "Payment Entry", __("Payment Entry"));
		},
		refresh(listview) {
			if (prev.refresh) prev.refresh(listview);
			cmi_workflow_list_actions(listview, "Payment Entry", __("Payment Entry"));
		},
	});
})();

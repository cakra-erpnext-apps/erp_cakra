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

	settings.add_fields = [...new Set([...(settings.add_fields || []), "docstatus"])];
	settings.get_indicator = function (doc) {
		if (cint(doc.docstatus) === 2) return [__("Void"), "red", "docstatus,=,2"];
		if (cint(doc.docstatus) === 1) return [__("Validate"), "blue", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	};
	settings.onload = function (listview) {
		if (typeof previous_onload === "function") previous_onload(listview);
		window.cmi_workflow_list_actions(listview, "Purchase Invoice", __("Purchase Invoice"));
	};
	settings.refresh = function (listview) {
		if (typeof previous_refresh === "function") previous_refresh(listview);
		window.cmi_workflow_list_actions(listview, "Purchase Invoice", __("Purchase Invoice"));
	};
	frappe.listview_settings["Purchase Invoice"] = settings;
})();

// Purchase Receipt: route native Submit/Cancel through the CMI workflow.
function cmiPrValidate(frm) {
	const run = () => frappe.call({
		method: "erpnext_custom.workflow.validate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Validate Purchase Receipt…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
	if (frm.is_new() || frm.is_dirty()) return frm.save().then(run);
	return run();
}

function cmiPrInvalidate(frm) {
	return frappe.call({
		method: "erpnext_custom.workflow.invalidate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Invalidate Purchase Receipt…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
}

function cmiPrPatchWorkflow(frm) {
	if (frm._cmi_workflow_patched) return;
	frm._cmi_workflow_patched = true;
	frm.savesubmit = () => cmiPrValidate(frm);
	frm.savecancel = () => cmiPrInvalidate(frm);
}

frappe.ui.form.on("Purchase Receipt", {
	onload(frm) {
		cmiPrPatchWorkflow(frm);
	},
	refresh(frm) {
		cmiPrPatchWorkflow(frm);
		window.cmi_workflow_menu(frm, __("Purchase Receipt"));
	},
	// Tombol "Set Vehicle" (Button field di atas tabel Items): isi Vehicle SEMUA
	// baris sekaligus. Vehicle juga bisa diisi per baris di grid; kosongkan lewat
	// dialog = kosongkan semua baris.
	custom_set_vehicle(frm) {
		cmiPrPromptVehicle(frm);
	},
});

function cmiPrPromptVehicle(frm) {
		frappe.prompt(
			{
				fieldname: "vehicle",
				fieldtype: "Link",
				label: __("Vehicle"),
				options: "Vehicle",
				description: __("Diterapkan ke semua baris item. Kosongkan untuk menghapus vehicle dari semua baris."),
			},
			(values) => {
				(frm.doc.items || []).forEach((row) => {
					frappe.model.set_value(row.doctype, row.name, "custom_vehicle", values.vehicle || null);
				});
			},
			__("Set Vehicle untuk Semua Item")
		);
}

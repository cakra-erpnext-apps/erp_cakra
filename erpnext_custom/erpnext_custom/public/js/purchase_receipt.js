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
	},
});

// Purchase Invoice (erpnext_custom): tab Assistant + Email (app `agents`) +
// Amounts smart-input (Discount/PPh/Tax/Materai -> Net Total), mirror Sales Invoice.

// --- Tab Assistant + Email (load on-demand & eval, /assets/assistant tak tersaji) ---
window.cmi_load_assistant = window.cmi_load_assistant || function (frm) {
	if (window.cmi_asst_render) { window.cmi_asst_render(frm); return; }
	frappe.call({ method: "assistant.assistant.api.assistant_js" }).then((r) => {
		if (r && r.message && !window.cmi_asst_render) {
			try { eval(r.message); } catch (e) { console.error("assistant_tabs eval", e); }
		}
		if (window.cmi_asst_render) window.cmi_asst_render(frm);
	});
};

// --- Amounts (logika dipisah di cmi_amounts.js, dimuat on-demand) ---
function cmiPiAmt(frm, fn) {
	if (window.cmiAmt) { fn(); return; }
	frappe.require("/assets/erpnext_custom/js/cmi_amounts.js", fn);
}
function cmiPiCompute(frm) { cmiPiAmt(frm, () => window.cmiAmt.compute(frm)); }
function cmiPiComputeDelayed(frm) { cmiPiAmt(frm, () => setTimeout(() => window.cmiAmt.compute(frm), 200)); }

function cmiPiEnableDate(frm) {
	if (frm.doc.docstatus !== 0) return;
	if (!cint(frm.doc.set_posting_time)) frm.set_value("set_posting_time", 1);
	frm.set_df_property("posting_date", "read_only", 0);
	// User hanya diminta mengubah Date; posting time tetap dikelola sistem.
	frm.set_df_property("posting_time", "read_only", 1);
}

function cmiPiValidate(frm) {
	const run = () => frappe.call({
		method: "erpnext_custom.workflow.validate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Validate Purchase Invoice…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
	if (frm.is_new() || frm.is_dirty()) {
		return frm.save().then(run);
	}
	return run();
}

function cmiPiInvalidate(frm) {
	return frappe.call({
		method: "erpnext_custom.workflow.invalidate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Invalidate Purchase Invoice…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
}

function cmiPiPatchWorkflow(frm) {
	if (frm._cmi_workflow_patched) return;
	frm._cmi_workflow_patched = true;
	frm.savesubmit = () => cmiPiValidate(frm);
	frm.savecancel = () => cmiPiInvalidate(frm);
}

function cmiPiPreventDuplicatePoMapping() {
	if (
		!erpnext.utils.map_current_doc ||
		erpnext.utils.map_current_doc.__cmi_prevents_duplicate_po
	) return;

	const original = erpnext.utils.map_current_doc;
	const wrapped = function (opts) {
		if (
			cur_frm?.doctype === "Purchase Invoice" &&
			opts?.source_doctype === "Purchase Order" &&
			opts?.method === "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice"
		) {
			opts = {
				...opts,
				method: "erpnext_custom.purchase_invoice.mapping.make_purchase_invoice",
				get_query_method: "erpnext_custom.purchase_invoice.mapping.purchase_order_query",
				setters: {
					...opts.setters,
					status: undefined,
				},
			};
		}
		return original.call(this, opts);
	};
	wrapped.__cmi_prevents_duplicate_po = true;
	erpnext.utils.map_current_doc = wrapped;
}

frappe.ui.form.on("Purchase Invoice", {
	onload(frm) {
		cmiPiPatchWorkflow(frm);
		cmiPiPreventDuplicatePoMapping();
		cmiPiAmt(frm, () => window.cmiAmt.hydrate(frm));
	},
	refresh(frm) {
		cmiPiPatchWorkflow(frm);
		window.cmi_workflow_menu(frm, __("Purchase Invoice"));
		cmiPiPreventDuplicatePoMapping();
		cmiPiEnableDate(frm);
		setTimeout(() => cmiPiEnableDate(frm), 100);
		window.cmi_load_assistant(frm);
		cmiPiAmt(frm, () => { window.cmiAmt.hydrate(frm); window.cmiAmt.compute(frm); });
	},
	currency(frm) { cmiPiCompute(frm); },
	custom_discount_input(frm) { cmiPiAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[0])); },
	custom_pph_input(frm) { cmiPiAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[1])); },
	custom_tax_input(frm) { cmiPiAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[2])); },
	custom_materai(frm) { cmiPiCompute(frm); },
	custom_ignore_tax(frm) { cmiPiCompute(frm); },
	custom_adjustment(frm) { cmiPiCompute(frm); },
	items_remove(frm) { cmiPiComputeDelayed(frm); },
});

frappe.ui.form.on("Purchase Invoice Item", {
	qty(frm) { cmiPiComputeDelayed(frm); },
	rate(frm) { cmiPiComputeDelayed(frm); },
	amount(frm) { cmiPiComputeDelayed(frm); },
});

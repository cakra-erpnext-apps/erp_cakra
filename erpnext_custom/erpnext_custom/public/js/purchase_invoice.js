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

frappe.ui.form.on("Purchase Invoice", {
	onload(frm) { cmiPiAmt(frm, () => window.cmiAmt.hydrate(frm)); },
	refresh(frm) {
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

// Purchase Order (erpnext_custom): tab Assistant + Email (app `agents`) +
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
function cmiPoAmt(frm, fn) {
	if (window.cmiAmt) { fn(); return; }
	frappe.require("/assets/erpnext_custom/js/cmi_amounts.js", fn);
}
function cmiPoCompute(frm) { cmiPoAmt(frm, () => window.cmiAmt.compute(frm)); }
function cmiPoComputeDelayed(frm) { cmiPoAmt(frm, () => setTimeout(() => window.cmiAmt.compute(frm), 200)); }

frappe.ui.form.on("Purchase Order", {
	onload(frm) { cmiPoAmt(frm, () => window.cmiAmt.hydrate(frm)); },
	refresh(frm) {
		window.cmi_load_assistant(frm);
		cmiPoAmt(frm, () => { window.cmiAmt.hydrate(frm); window.cmiAmt.compute(frm); });
	},
	currency(frm) { cmiPoCompute(frm); },
	custom_discount_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[0])); },
	custom_pph_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[1])); },
	custom_tax_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[2])); },
	custom_materai(frm) { cmiPoCompute(frm); },
	custom_ignore_tax(frm) { cmiPoCompute(frm); },
	custom_adjustment(frm) { cmiPoCompute(frm); },
	items_remove(frm) { cmiPoComputeDelayed(frm); },
});

frappe.ui.form.on("Purchase Order Item", {
	qty(frm) { cmiPoComputeDelayed(frm); },
	rate(frm) { cmiPoComputeDelayed(frm); },
	amount(frm) { cmiPoComputeDelayed(frm); },
});

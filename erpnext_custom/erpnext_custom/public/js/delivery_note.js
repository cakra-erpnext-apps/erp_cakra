// Delivery Note smart amounts: "10%" or nominal for Discount/PPh/Tax.
function cmiDnAmounts(frm, callback) {
	if (window.cmiAmt) return callback();
	frappe.require("/assets/erpnext_custom/js/cmi_amounts.js", callback);
}

function cmiDnCompute(frm) {
	cmiDnAmounts(frm, () => window.cmiAmt.compute(frm));
}

function cmiDnComputeDelayed(frm) {
	cmiDnAmounts(frm, () => setTimeout(() => window.cmiAmt.compute(frm), 200));
}

frappe.ui.form.on("Delivery Note", {
	onload(frm) {
		cmiDnAmounts(frm, () => window.cmiAmt.hydrate(frm));
	},
	refresh(frm) {
		cmiDnAmounts(frm, () => {
			window.cmiAmt.hydrate(frm);
			window.cmiAmt.compute(frm);
		});
	},
	currency(frm) { cmiDnCompute(frm); },
	custom_discount_input(frm) {
		cmiDnAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[0]));
	},
	custom_pph_input(frm) {
		cmiDnAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[1]));
	},
	custom_tax_input(frm) {
		cmiDnAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[2]));
	},
	custom_materai(frm) { cmiDnCompute(frm); },
	custom_ignore_tax(frm) { cmiDnCompute(frm); },
	items_remove(frm) { cmiDnComputeDelayed(frm); },
});

frappe.ui.form.on("Delivery Note Item", {
	qty(frm) { cmiDnComputeDelayed(frm); },
	rate(frm) { cmiDnComputeDelayed(frm); },
	amount(frm) { cmiDnComputeDelayed(frm); },
});

// Sales Order smart amounts: "10%" or nominal for Discount/PPh/Tax.
function cmiSoAmounts(frm, callback) {
	if (window.cmiAmt) return callback();
	frappe.require("/assets/erpnext_custom/js/cmi_amounts.js", callback);
}

function cmiSoCompute(frm) {
	cmiSoAmounts(frm, () => window.cmiAmt.compute(frm));
}

function cmiSoComputeDelayed(frm) {
	cmiSoAmounts(frm, () => setTimeout(() => window.cmiAmt.compute(frm), 200));
}

frappe.ui.form.on("Sales Order", {
	onload(frm) {
		cmiSoAmounts(frm, () => window.cmiAmt.hydrate(frm));
	},
	refresh(frm) {
		cmiSoAmounts(frm, () => {
			window.cmiAmt.hydrate(frm);
			window.cmiAmt.compute(frm);
		});
	},
	currency(frm) { cmiSoCompute(frm); },
	custom_discount_input(frm) {
		cmiSoAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[0]));
	},
	custom_pph_input(frm) {
		cmiSoAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[1]));
	},
	custom_tax_input(frm) {
		cmiSoAmounts(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[2]));
	},
	custom_materai(frm) { cmiSoCompute(frm); },
	custom_ignore_tax(frm) { cmiSoCompute(frm); },
	items_remove(frm) { cmiSoComputeDelayed(frm); },
});

frappe.ui.form.on("Sales Order Item", {
	qty(frm) { cmiSoComputeDelayed(frm); },
	rate(frm) { cmiSoComputeDelayed(frm); },
	amount(frm) { cmiSoComputeDelayed(frm); },
});

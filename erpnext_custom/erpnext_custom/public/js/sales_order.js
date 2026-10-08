// Sales Order smart amounts: "10%" or nominal for Discount/PPh/Tax.
function cmiSoAmounts(frm, callback) {
	if (window.cmiAmt) return callback();
	frappe.require("/assets/erpnext_custom/js/cmi_amounts.js?v=2", callback);
}

function cmiSoCompute(frm) {
	cmiSoAmounts(frm, () => window.cmiAmt.compute(frm));
}

function cmiSoComputeDelayed(frm) {
	cmiSoAmounts(frm, () => setTimeout(() => window.cmiAmt.compute(frm), 200));
}

// Baris Customer: Customer 2 kolom, Currency/Exchange Rate 1 kolom (sama dengan
// cmiPoWideSupplier di purchase_order.js; Frappe tak punya lebar per kolom).
function cmiSoWideCustomer(frm) {
	const field = frm.get_field("customer");
	if (!field) return;
	const cols = field.$wrapper.closest(".form-column").parent().children(".form-column");
	if (cols.length !== 3) return;
	["50%", "25%", "25%"].forEach((w, i) => cols.eq(i).css({ flex: `0 0 ${w}`, maxWidth: w }));
}

// Exchange Rate tetap tampil walau mata uang = mata uang company
// (lihat cmiPoKeepExchangeRate di purchase_order.js).
function cmiSoKeepExchangeRate(frm) {
	const f = frm.fields_dict.conversion_rate;
	if (!f || f.df.get_status) return;
	f.df.get_status = () => (frm.doc.docstatus === 0 ? "Write" : "Read");
	f.refresh();
}

frappe.ui.form.on("Sales Order", {
	onload(frm) {
		cmiSoAmounts(frm, () => window.cmiAmt.hydrate(frm));
	},
	refresh(frm) {
		cmiSoWideCustomer(frm);
		cmiSoKeepExchangeRate(frm);
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

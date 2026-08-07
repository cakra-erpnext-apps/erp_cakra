function recalc(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		row.amount = flt(row.qty) * flt(row.rate);
		total += row.amount;
	});
	frm.set_value("total_amount", total);
	frm.refresh_field("items");
}

frappe.ui.form.on("Maintenance Item", {
	qty: recalc,
	rate: recalc,
	items_remove: recalc,
});

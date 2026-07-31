// Pick List: use Delivery as the default for a new document.
frappe.ui.form.on("Pick List", {
	onload(frm) {
		if (
			frm.is_new() &&
			!frm.doc.work_order &&
			!frm.doc.material_request &&
			frm.doc.purpose === "Material Transfer for Manufacture"
		) {
			frm.set_value("purpose", "Delivery");
		}
	},
});

// Status Draft -> Validate/Invalidate -> Void/Unvoid memakai mesin state CMI yang sama
// dengan invoice & Expense Note (erpnext_custom.workflow), jadi role-nya ikut terjaga.
function act(frm, method, args) {
	frappe.call({
		method: "erpnext_custom.workflow." + method,
		args: { doctype: "Maintenance", name: frm.doc.name, ...(args || {}) },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}

function recalc(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		row.amount = flt(row.qty) * flt(row.rate);
		total += row.amount;
	});
	frm.set_value("total_amount", total);
	frm.refresh_field("items");
}

frappe.ui.form.on("Maintenance", {
	setup(frm) {
		// Hanya item di bawah Item Group "Sparepart" — pakai descendants supaya sub-grup
		// (Oli, Ban, dst) ikut terbawa tanpa perlu menyentuh kode ini lagi.
		frm.set_query("item", "items", () => ({
			filters: { item_group: ["descendants of (inclusive)", "Sparepart"], disabled: 0 },
		}));
		frm.set_query("warehouse", "items", () => ({ filters: { is_group: 0, company: frm.doc.company } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry)
			);
		}
		// Turunan Purchase Receipt: statusnya diatur di sana, jadi tombolnya tidak ditampilkan.
		if (frm.doc.purchase_receipt) {
			frm.dashboard.set_headline(
				__("Sparepart dipakai langsung dari Purchase Receipt {0}. Pembatalan lewat dokumen itu.", [
					`<a href="/app/purchase-receipt/${frm.doc.purchase_receipt}">${frm.doc.purchase_receipt}</a>`,
				])
			);
			return;
		}

		if (frm.doc.void) {
			frm.add_custom_button(__("Unvoid"), () => act(frm, "unvoid_doc"));
			return;
		}
		if (frm.doc.validated) {
			frm.add_custom_button(__("Invalidate"), () => act(frm, "invalidate_doc"));
			frm.add_custom_button(__("Void"), () =>
				frappe.prompt(
					{ fieldtype: "Small Text", fieldname: "reason", label: __("Alasan Void"), reqd: 1 },
					(v) => act(frm, "void_doc", { reason: v.reason }),
					__("Void Maintenance")
				)
			);
			return;
		}
		frm.add_custom_button(__("Validate"), () => act(frm, "validate_doc")).addClass("btn-primary");
	},
});

frappe.ui.form.on("Maintenance Item", {
	qty: recalc,
	rate: recalc,
	items_remove: recalc,
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.item && !row.description) {
			frappe.db.get_value("Item", row.item, "item_name").then((r) => {
				frappe.model.set_value(cdt, cdn, "description", r.message.item_name);
			});
		}
	},
});

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
		// Penanda sparepart di sistem ini adalah Item Category (dipakai juga oleh aturan
		// tipe pembelian), bukan Item Group — item sparepart boleh ada di grup mana saja.
		// Penyaringan saldo (item & gudang harus punya stok) ada di server, lihat maintenance.py.
		const q = (m) => "erp.fleet.doctype.maintenance.maintenance." + m;
		frm.set_query("item", "items", (doc, cdt, cdn) => ({
			query: q("sparepart_query"),
			filters: { warehouse: locals[cdt][cdn].warehouse },
		}));
		frm.set_query("warehouse", "items", (doc, cdt, cdn) => ({
			query: q("warehouse_query"),
			filters: { item: locals[cdt][cdn].item, company: frm.doc.company },
		}));
	},

	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () =>
				frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry)
			);
		}
		// Turunan PR/PI: statusnya diatur di sana, jadi tombolnya tidak ditampilkan.
		const source = frm.doc.purchase_receipt
			? { doctype: __("Purchase Receipt"), name: frm.doc.purchase_receipt, route: "purchase-receipt" }
			: frm.doc.purchase_invoice
			? { doctype: __("Purchase Invoice"), name: frm.doc.purchase_invoice, route: "purchase-invoice" }
			: null;
		if (source) {
			// Isinya cermin dokumen pembelian: dikunci di layar juga, bukan cuma di server,
			// supaya orang tidak mengetik dulu baru ditolak saat simpan.
			["items", "vehicle", "date", "supplier", "maintenance_type", "company"].forEach((f) =>
				frm.set_df_property(f, "read_only", 1)
			);
			frm.dashboard.set_headline(
				__("Sparepart dipakai langsung dari {0} {1}. Pembatalan lewat dokumen itu.", [
					source.doctype,
					`<a href="/desk/${source.route}/${source.name}">${source.name}</a>`,
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

// Harga baris stock TIDAK diketik user: barang keluar gudang dinilai dengan valuation-nya.
// Ditarik sejak Draft supaya total di form sudah masuk akal sebelum Validate — angka
// finalnya tetap dari Stock Entry yang terbit saat Validate.
function fill_valuation(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item || !row.is_stock_item || !row.warehouse) return;
	frappe.db
		.get_value("Bin", { item_code: row.item, warehouse: row.warehouse }, "valuation_rate")
		.then((r) => {
			frappe.model.set_value(cdt, cdn, "rate", flt(r.message && r.message.valuation_rate));
			recalc(frm);
		});
}

frappe.ui.form.on("Maintenance Item", {
	qty: recalc,
	rate: recalc,
	items_remove: recalc,
	warehouse: fill_valuation,
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) return;
		frappe.db.get_value("Item", row.item, "is_stock_item").then((r) => {
			frappe.model.set_value(cdt, cdn, "is_stock_item", (r.message || {}).is_stock_item);
			fill_valuation(frm, cdt, cdn);
		});
	},
});

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
		// ERPNext menyembunyikan Exchange Rate saat currency = mata uang company;
		// CMI ingin selalu tampil sejajar Currency.
		frm.toggle_display("conversion_rate", true);
	},
	currency(frm) {
		cmiDnCompute(frm);
		frm.toggle_display("conversion_rate", true);
	},
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
	// Saran rak barang keluar: FIFO (stok tertua dulu), tie terdekat lalu terbawah.
	// Satu rak tidak cukup -> baris dipecah. Replan = klik lagi.
	// Lihat erpnext_custom/rack_suggest.py.
	custom_suggest_rack(frm) {
		frappe.prompt(
			{ fieldname: "overwrite", fieldtype: "Check", label: __("Atur ulang semua pilihan rak sesuai saran sistem"),
				description: __("Jika tidak dicentang, hanya baris yang raknya masih kosong yang akan diisi.") },
			(v) => cmiDnSuggestRack(frm, v.overwrite),
			__("Suggest Rack")
		);
	},
});

function cmiDnSuggestRack(frm, overwrite) {
	const originals = [...(frm.doc.items || [])];
	const rows = originals.map((r) => ({
		item_code: r.item_code, qty: r.qty, stock_qty: r.stock_qty,
	}));
	frappe.call({
		method: "erpnext_custom.rack_suggest.suggest",
		args: { direction: "out", company: frm.doc.company, rows: JSON.stringify(rows) },
		freeze: true,
		callback(res) {
			let skipped = 0, shortage = 0;
			originals.forEach((row, i) => {
				const s = (res.message || [])[i];
				if (!s || s.skip) { if (row.item_code) skipped++; return; }
				if (row.warehouse && !overwrite) return;
				const cf = row.conversion_factor || 1;
				const alloc = s.allocations;
				frappe.model.set_value(row.doctype, row.name, "warehouse", alloc[0].warehouse);
				if (alloc.length > 1) {
					frappe.model.set_value(row.doctype, row.name, "qty", alloc[0].qty / cf);
					alloc.slice(1).forEach((a) => {
						const clone = Object.assign({}, row);
						["name", "idx", "owner", "creation", "modified", "modified_by",
							"docstatus", "__islocal", "__unsaved"].forEach((k) => delete clone[k]);
						Object.assign(clone, { warehouse: a.warehouse, qty: a.qty / cf });
						frm.add_child("items", clone);
					});
				}
				if (s.shortage) shortage++;
			});
			frm.refresh_field("items");
			if (skipped) frappe.show_alert(__("{0} baris dilewati (tanpa stok / qty kosong)", [skipped]));
			if (shortage) frappe.msgprint(__("Stok kurang untuk {0} baris — alokasi hanya sebagian.", [shortage]));
		},
	});
}

frappe.ui.form.on("Delivery Note Item", {
	qty(frm) { cmiDnComputeDelayed(frm); },
	rate(frm) { cmiDnComputeDelayed(frm); },
	amount(frm) { cmiDnComputeDelayed(frm); },
});

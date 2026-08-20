// Purchase Receipt: route native Submit/Cancel through the CMI workflow.
function cmiPrValidate(frm) {
	const run = () => frappe.call({
		method: "erpnext_custom.workflow.validate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Validate Purchase Receipt…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
	if (frm.is_new() || frm.is_dirty()) return frm.save().then(run);
	return run();
}

function cmiPrInvalidate(frm) {
	return frappe.call({
		method: "erpnext_custom.workflow.invalidate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Invalidate Purchase Receipt…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
}

function cmiPrPatchWorkflow(frm) {
	if (frm._cmi_workflow_patched) return;
	frm._cmi_workflow_patched = true;
	frm.savesubmit = () => cmiPrValidate(frm);
	frm.savecancel = () => cmiPrInvalidate(frm);
}

frappe.ui.form.on("Purchase Receipt", {
	onload(frm) {
		cmiPrPatchWorkflow(frm);
		// WMS ringan: Gudang = warehouse group; Rack (warehouse core) terfilter
		// hanya child gudang yang dipilih di baris itu.
		frm.set_query("custom_gudang", "items", () => ({
			filters: { is_group: 1, company: frm.doc.company },
		}));
		frm.set_query("warehouse", "items", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const filters = { is_group: 0, company: frm.doc.company };
			if (row.custom_gudang) filters.parent_warehouse = row.custom_gudang;
			return { filters };
		});
	},
	refresh(frm) {
		cmiPrPatchWorkflow(frm);
		cmiPrSplitGudang(frm);
		window.cmi_workflow_menu(frm, __("Purchase Receipt"));
	},
	// Tombol "Set Vehicle" (Button field di atas tabel Items): isi Vehicle SEMUA
	// baris sekaligus. Vehicle juga bisa diisi per baris di grid; kosongkan lewat
	// dialog = kosongkan semua baris.
	custom_set_vehicle(frm) {
		cmiPrPromptVehicle(frm);
	},
	// Saran rak barang masuk (replan = klik lagi). Lihat erpnext_custom/rack_suggest.py.
	custom_suggest_rack(frm) {
		frappe.prompt(
			{ fieldname: "overwrite", fieldtype: "Check", label: __("Atur ulang semua pilihan rak sesuai saran sistem"),
				description: __("Jika tidak dicentang, hanya baris yang raknya masih kosong yang akan diisi.") },
			(v) => {
				const rows = (frm.doc.items || []).map((r) => ({
					item_code: r.item_code, qty: r.qty, gudang: r.custom_gudang,
				}));
				frappe.call({
					method: "erpnext_custom.rack_suggest.suggest",
					args: { direction: "in", company: frm.doc.company, rows: JSON.stringify(rows) },
					freeze: true,
					callback(res) {
						let skipped = 0;
						(frm.doc.items || []).forEach((row, i) => {
							const s = (res.message || [])[i];
							if (!s || s.skip) { if (row.item_code) skipped++; return; }
							if (row.warehouse && !v.overwrite) return;
							frappe.model.set_value(row.doctype, row.name, "warehouse", s.allocations[0].warehouse);
						});
						if (skipped) frappe.show_alert(__("{0} baris dilewati (gudang belum dipilih / tanpa rak)", [skipped]));
					},
				});
			},
			__("Suggest Rack")
		);
	},
});

// PR dari PO membawa GUDANG di kolom Rack. Pindahkan ke kolom Warehouse selagi
// dokumen masih draft, supaya user langsung melihat raknya kosong dan tombol
// Suggest Rack punya gudang untuk dipakai. Server menjaga hal yang sama saat
// simpan (rack_suggest.split_gudang_from_rack) — ini murni supaya form tidak
// menunggu sampai disimpan dulu.
async function cmiPrSplitGudang(frm) {
	if (frm.doc.docstatus !== 0) return;
	const rows = (frm.doc.items || []).filter((r) => r.warehouse && !r.custom_gudang);
	if (!rows.length) return;
	const groups = new Set(
		(await frappe.db.get_list("Warehouse", { filters: { is_group: 1 }, fields: ["name"], limit: 0 }))
			.map((w) => w.name)
	);
	rows.forEach((r) => {
		// set custom_gudang memicu handler di bawah yang mengosongkan rak-nya.
		if (groups.has(r.warehouse)) frappe.model.set_value(r.doctype, r.name, "custom_gudang", r.warehouse);
	});
}

frappe.ui.form.on("Purchase Receipt Item", {
	// Ganti gudang = pilihan rak lama tidak berlaku lagi.
	custom_gudang(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "warehouse", null);
	},
});

function cmiPrPromptVehicle(frm) {
		frappe.prompt(
			{
				fieldname: "vehicle",
				fieldtype: "Link",
				label: __("Vehicle"),
				options: "Vehicle",
				description: __("Diterapkan ke semua baris item. Kosongkan untuk menghapus vehicle dari semua baris."),
			},
			(values) => {
				(frm.doc.items || []).forEach((row) => {
					frappe.model.set_value(row.doctype, row.name, "custom_vehicle", values.vehicle || null);
				});
			},
			__("Set Vehicle untuk Semua Item")
		);
}

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

// Submit native dijaga server. Arahkan entry point toolbar ke workflow CMI agar
// flag cmi_action_ok dipasang oleh endpoint Validate sebelum doc.submit().
function cmiPoValidate(frm) {
	const run = () => frappe.call({
		method: "erpnext_custom.workflow.validate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Validate Purchase Order…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
	if (frm.is_new() || frm.is_dirty()) {
		return frm.save().then(run);
	}
	return run();
}

function cmiPoInvalidate(frm) {
	return frappe.call({
		method: "erpnext_custom.workflow.invalidate_doc",
		args: { doctype: frm.doctype, name: frm.doc.name },
		freeze: true,
		freeze_message: __("Invalidate Purchase Order…"),
		callback(r) {
			if (r.message?.ok) frm.reload_doc();
		},
	});
}

function cmiPoPatchWorkflow(frm) {
	if (frm._cmi_workflow_patched) return;
	frm._cmi_workflow_patched = true;
	frm.savesubmit = () => cmiPoValidate(frm);
	frm.savecancel = () => cmiPoInvalidate(frm);
}

// --- Item picker: hanya kategori barang/jasa yang bisa dibeli ---
const CMI_PO_ITEM_CATEGORIES = ["Stock", "Asset", "Sparepart", "Service"];

function cmiPoItemQuery(frm) {
	frm.set_query("item_code", "items", () => ({
		query: "erpnext.controllers.queries.item_query",
		filters: {
			supplier: frm.doc.supplier,
			is_purchase_item: 1,
			has_variants: 0,
			item_category: ["in", CMI_PO_ITEM_CATEGORIES],
		},
	}));
}

// --- Warehouse picker: GUDANG saja, raknya baru dipilih di Purchase Receipt ---
// Rak dikenali dari custom_rack_order (terisi otomatis dari nama ber-skema
// A-AA-01, lihat rack_suggest.py). Node akar dibuang lewat parent_warehouse.
function cmiPoWarehouseQuery(frm) {
	const gudang = () => ({
		filters: [
			["company", "=", frm.doc.company],
			["custom_rack_order", "=", 0],
			["parent_warehouse", "is", "set"],
		],
	});
	frm.set_query("warehouse", "items", gudang);
	frm.set_query("set_warehouse", gudang);
}

// --- Baris Supplier: Supplier 2 kolom, Delivery From/To 1 kolom ---
// Frappe membagi lebar kolom RATA (Column.resize_all_columns) dan tidak punya properti
// lebar per kolom, jadi satu-satunya jalan adalah inline style — menang atas class
// col-sm-* dan tidak ikut terhapus saat kolom di-resize ulang.
// ponytail: inline style di satu tempat; angkat ke CSS kalau nanti ada baris lain yang butuh.
function cmiPoWideSupplier(frm) {
	const field = frm.get_field("supplier");
	if (!field) return;
	const cols = field.$wrapper.closest(".form-column").parent().children(".form-column");
	if (cols.length !== 3) return;
	["50%", "25%", "25%"].forEach((w, i) => cols.eq(i).css({ flex: `0 0 ${w}`, maxWidth: w }));
}

// --- Exchange Rate tetap tampil ---
// erpnext transaction.js men-toggle_display `conversion_rate` OFF setiap mata uang
// dokumen == mata uang company (PO IDR di company IDR = selalu hilang). `df.get_status`
// dibaca PALING AWAL oleh base_control.get_status, jadi override sekali per form
// mengalahkan toggle itu; docstatus tetap dihormati supaya dokumen yang sudah Validate
// tidak berubah jadi editable.
// NB: field read-only kosong (SubTotal/Net Total/Branch/...) TIDAK perlu ditangani di
// sini — System Settings "Hide empty read-only fields" dimatikan di install.after_migrate.
function cmiPoKeepExchangeRate(frm) {
	const f = frm.fields_dict.conversion_rate;
	if (!f || f.df.get_status) return;
	f.df.get_status = () => (frm.doc.docstatus === 0 ? "Write" : "Read");
	f.refresh();
}

frappe.ui.form.on("Purchase Order", {
	onload(frm) { cmiPoAmt(frm, () => window.cmiAmt.hydrate(frm)); },
	refresh(frm) {
		cmiPoPatchWorkflow(frm);
		cmiPoKeepExchangeRate(frm);
		cmiPoWideSupplier(frm);
		window.cmi_workflow_menu(frm, __("Purchase Order"));
		cmiPoItemQuery(frm);
		cmiPoWarehouseQuery(frm);
		window.cmi_load_assistant(frm);
		cmiPoAmt(frm, () => { window.cmiAmt.hydrate(frm); window.cmiAmt.compute(frm); });
	},
	currency(frm) { cmiPoCompute(frm); },
	custom_discount_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[0])); },
	custom_pph_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[1])); },
	custom_tax_input(frm) { cmiPoAmt(frm, () => window.cmiAmt.applyInput(frm, window.cmiAmt.SMART[2])); },
	custom_materai(frm) { cmiPoCompute(frm); },
	custom_ignore_tax(frm) { cmiPoCompute(frm); },
	items_remove(frm) { cmiPoComputeDelayed(frm); },
});

frappe.ui.form.on("Purchase Order Item", {
	qty(frm) { cmiPoComputeDelayed(frm); },
	rate(frm) { cmiPoComputeDelayed(frm); },
	amount(frm) { cmiPoComputeDelayed(frm); },
});

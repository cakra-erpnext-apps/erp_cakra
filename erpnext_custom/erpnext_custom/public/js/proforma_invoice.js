// Proforma Invoice: doctype terpisah dengan form yang sama persis dengan Sales Invoice
// (handler-nya di public/js/sales_invoice.js, didaftarkan ke dua doctype sekaligus).
//
// Yang perlu ditambahkan cuma mesin hitung sisi CLIENT. Sales Invoice memakai
// erpnext.accounts.SalesInvoiceController — kelas itu hidup di form script Sales Invoice
// sendiri, jadi tidak tersedia di sini. Induknya, SellingController, memang global
// (erpnext.bundle.js) dan sudah berisi semua yang dipakai proforma: qty x rate -> amount,
// kurs & price list, diskon, baris pajak, total berjalan. Yang tidak ikut hanya bagian
// khusus invoice (POS, loyalty, alokasi uang muka) yang proforma memang tidak punya.
//
// Dua jebakan saat memasangnya di event `setup`:
// 1. Frappe menyusun daftar handler `setup` SEBELUM handler ini jalan, jadi `setup()` milik
//    controller tidak pernah terpanggil -> dipanggil sendiri di sini.
// 2. `setup()` controller memasang handler baris ke `frm.doctype + " Item"`, yaitu
//    "Proforma Invoice Item" (tidak ada). Baris proforma = "Sales Invoice Item", jadi
//    handler itu dipindah ke sana, dibatasi ke form proforma. Tanpa ini ubah Price/Rate
//    tidak menghitung ulang Amount.
const CMI_PF_ITEM_DT = "Proforma Invoice Item";

frappe.ui.form.on("Proforma Invoice", {
	setup(frm) {
		if (frm.__cmi_selling_ctrl) return;
		// Kelas SellingController baru DIDEFINISIKAN saat setup_selling_controller() dipanggil
		// (biasanya oleh form script Sales Invoice). Proforma dibuka tanpa pernah membuka
		// invoice = kelasnya belum ada -> panggil sendiri.
		if (!window.erpnext?.selling?.SellingController) erpnext.sales_common?.setup_selling_controller();
		if (!window.erpnext?.selling?.SellingController || !window.extend_cscript) return;
		frm.__cmi_selling_ctrl = true;
		extend_cscript(frm.cscript, new erpnext.selling.SellingController({ frm }));
		frm.cscript.setup();
		cmi_pf_rebind_item_handlers();
	},
});

function cmi_pf_rebind_item_handlers() {
	const events = frappe.ui.form.handlers[CMI_PF_ITEM_DT] || {};
	Object.entries(events).forEach(([event, fns]) => {
		(fns || []).forEach((fn) => {
			frappe.ui.form.on("Sales Invoice Item", event, (frm, cdt, cdn) => {
				if (frm.doctype === "Proforma Invoice") return fn(frm, cdt, cdn);
			});
		});
	});
	delete frappe.ui.form.handlers[CMI_PF_ITEM_DT];
}

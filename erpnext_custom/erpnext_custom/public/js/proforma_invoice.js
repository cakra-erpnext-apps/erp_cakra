// Proforma Invoice: doctype terpisah dengan form yang sama persis dengan Sales Invoice
// (handler-nya di public/js/sales_invoice.js, didaftarkan ke dua doctype sekaligus).
//
// Yang perlu ditambahkan cuma mesin hitung sisi CLIENT. Sales Invoice memakai
// erpnext.accounts.SalesInvoiceController — kelas itu hidup di form script Sales Invoice
// sendiri, jadi tidak tersedia di sini. Induknya, SellingController, memang global
// (erpnext.bundle.js) dan sudah berisi semua yang dipakai proforma: qty x rate -> amount,
// kurs & price list, diskon, baris pajak, total berjalan. Yang tidak ikut hanya bagian
// khusus invoice (POS, loyalty, alokasi uang muka) yang proforma memang tidak punya.
frappe.ui.form.on("Proforma Invoice", {
	setup(frm) {
		if (frm.__cmi_selling_ctrl) return;
		if (!window.erpnext?.selling?.SellingController || !window.extend_cscript) return;
		frm.__cmi_selling_ctrl = true;
		extend_cscript(frm.cscript, new erpnext.selling.SellingController({ frm }));
	},
});

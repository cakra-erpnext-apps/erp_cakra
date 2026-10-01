// Menu Tax (Tax Invoice / Tax Expense / Tax ARAP Note / Tax Purchase): warna Status.
// Barisnya dibuat sistem dari dokumen sumber (erpnext_custom/tax_records.py), jadi doctype
// ini in_create: tidak ada tombol New.
["Tax Invoice", "Tax Expense", "Tax ARAP Note", "Tax Purchase"].forEach((doctype) => {
	frappe.listview_settings[doctype] = {
		get_indicator(doc) {
			const color = { Belum: "orange", Sudah: "green", Batal: "red" }[doc.status] || "gray";
			return [__(doc.status), color, `status,=,${doc.status}`];
		},
	};
});

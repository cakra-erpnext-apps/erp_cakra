// Dropdown "Stock Entry Type" hanya menampilkan tipe yang belum dicentang Disabled
// (custom field `custom_disabled` di Stock Entry Type — dikelola di install.py).
//
// Filter bawaan ERPNext (menyembunyikan tipe subcontracting, atau justru HANYA
// menampilkannya saat dokumen berasal dari Subcontracting Inward Order) sengaja
// ditulis ulang di sini. Kalau set_query kita menimpanya tanpa menyalin filter itu,
// alur subcontracting bawaan ikut rusak diam-diam.
//
// Ini penyaring TAMPILAN saja. Server tidak menolak tipe yang dicentang Disabled —
// dan itu memang disengaja, karena ERPNext membuat Stock Entry sendiri dengan tipe
// seperti "Material Transfer for Manufacture" atau "Disassemble" lewat kode.
const CMI_SUBCONTRACT_PURPOSES = [
	"Receive from Customer",
	"Return Raw Material to Customer",
	"Subcontracting Delivery",
	"Subcontracting Return",
];

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		frm.set_query("stock_entry_type", () => ({
			filters: {
				custom_disabled: 0,
				purpose: [
					frm.doc.subcontracting_inward_order ? "in" : "not in",
					CMI_SUBCONTRACT_PURPOSES,
				],
			},
		}));
	},
});

// Pick List: default purpose Delivery, dan pemilih RAK asal per baris.
//
// Barisnya dipecah PER RAK: satu rak tidak cukup, sisanya lanjut ke rak berikutnya.
// Pemecahan itu aman terhadap Sales Order karena ERPNext menjumlahkan picked_qty
// per sales_order_item (get_picked_items_qty), bukan per baris.

// Field yang ikut disalin waktu satu baris dipecah jadi beberapa rak. Sengaja
// daftar putih: menyalin seluruh objek baris ikut membawa name/idx/parent dan
// baris barunya bentrok dengan baris lama.
const CMI_PICK_KEEP = [
	"item_code", "item_name", "description", "item_group", "warehouse",
	"uom", "conversion_factor", "stock_uom", "sales_order", "sales_order_item",
	"product_bundle_item", "material_request", "material_request_item",
	"batch_no", "serial_no", "use_serial_batch_fields",
];

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

	custom_suggest_bin(frm) {
		const src = (frm.doc.locations || []).filter((r) => r.item_code && r.warehouse);
		if (!src.length) return frappe.msgprint(__("Isi tabel Item Locations dulu."));

		frappe.call({
			method: "erpnext_custom.picking_list.picking_list.suggest_bins",
			args: {
				rows: JSON.stringify(
					src.map((r) => ({
						item_code: r.item_code,
						warehouse: r.warehouse,
						batch_no: r.batch_no,
						qty: flt(r.picked_qty) || flt(r.stock_qty) || flt(r.qty),
					}))
				),
				exclude: frm.doc.name,
			},
			freeze: true,
			freeze_message: __("Mencari rak..."),
			callback(res) {
				const hasil = res.message || [];
				const kurang = [];
				const baris = [];

				src.forEach((row, i) => {
					const s = hasil[i] || {};
					const alloc = s.allocations || [];
					const dasar = {};
					CMI_PICK_KEEP.forEach((f) => {
						if (row[f] !== undefined && row[f] !== null) dasar[f] = row[f];
					});

					// Tidak ketemu rak: barisnya DIPERTAHANKAN tanpa bin, tidak dibuang.
					// Membuangnya diam-diam berarti pengiriman berkurang tanpa ada yang tahu.
					if (!alloc.length) {
						kurang.push(`${row.item_code}: ${s.skip || __("tidak ketemu rak")}`);
						baris.push(
							Object.assign(dasar, {
								qty: row.qty,
								stock_qty: row.stock_qty,
								picked_qty: row.picked_qty,
							})
						);
						return;
					}

					const cf = flt(row.conversion_factor) || 1;
					alloc.forEach((a) =>
						baris.push(
							Object.assign({}, dasar, {
								custom_bin_location: a.bin_location,
								stock_qty: a.qty,
								picked_qty: a.qty,
								qty: flt(a.qty / cf, precision("qty", row)),
							})
						)
					);
					if (s.shortage)
						kurang.push(`${row.item_code}: ${s.shortage} ${__("tidak kebagian rak")}`);
				});

				frm.clear_table("locations");
				baris.forEach((b) => Object.assign(frm.add_child("locations"), b));
				frm.refresh_field("locations");

				// WAJIB: tanpa ini set_item_locations() membangun ulang tabelnya waktu
				// save (before_save) dan rak yang barusan dipilih lenyap tanpa pesan.
				frm.set_value("pick_manually", 1);

				if (kurang.length)
					frappe.msgprint({
						title: __("Sebagian tanpa rak"),
						message:
							kurang.join("<br>") +
							"<br><br>" +
							__("Baris tanpa rak tetap dikirim, tapi rak asalnya baru ditentukan FIFO waktu Delivery Note submit."),
						indicator: "orange",
					});
			},
		});
	},
});

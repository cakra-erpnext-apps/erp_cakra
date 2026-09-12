// Goods Receive: penerimaan barang ke bin. Tidak menyentuh stok/jurnal — stok
// sudah diakui di Purchase Invoice, di sini cuma letak fisiknya.
frappe.ui.form.on("Goods Receive", {
	onload(frm) {
		// PI yang stoknya sudah masuk; PI tanpa update_stock tidak menambah apa pun ke gudang.
		frm.set_query("purchase_invoice", () => ({
			filters: { docstatus: 1, update_stock: 1, is_return: 0 },
		}));
		frm.set_query("gudang", () => ({ filters: { is_group: 0 } }));
		frm.set_query("bin_location", "items", () => ({
			filters: { gudang: frm.doc.gudang || "", disabled: 0 },
		}));
	},

	gudang(frm) {
		// Ganti gudang = bin yang sudah dipilih tidak berlaku lagi.
		(frm.doc.items || []).forEach((row) => {
			if (row.bin_location) frappe.model.set_value(row.doctype, row.name, "bin_location", null);
		});
	},

	// Gudang diisi begitu notanya dipilih, tidak menunggu Get Data. Nota yang
	// memakai lebih dari satu gudang tidak bisa ditebak, jadi dibiarkan kosong.
	purchase_invoice(frm) {
		frm.clear_table("items"); // baris nota lama tidak berlaku untuk nota baru
		frm.refresh_field("items");
		if (!frm.doc.purchase_invoice) return;
		frappe.call({
			method: "erpnext_custom.bin_layout.invoice_gudang",
			args: { purchase_invoice: frm.doc.purchase_invoice },
			callback(res) {
				if (res.message) return frm.set_value("gudang", res.message);
				frm.set_value("gudang", null);
				frappe.show_alert({
					message: __("Nota ini memakai lebih dari satu gudang, pilih gudangnya sendiri."),
					indicator: "orange",
				});
			},
		});
	},

	// Tarik baris nota, dikurangi yang sudah diterima lewat Goods Receive lain.
	pull_purchase_invoice(frm) {
		if (!frm.doc.purchase_invoice) return frappe.msgprint(__("Pilih Purchase Invoice dulu."));
		frappe.call({
			method: "erpnext_custom.bin_layout.pull_purchase_invoice",
			args: { purchase_invoice: frm.doc.purchase_invoice, gudang: frm.doc.gudang || "" },
			freeze: true,
			callback(res) {
				const out = res.message || {};
				const rows = out.rows || [];
				if (!rows.length) return frappe.msgprint(__("Semua barang nota ini sudah diterima."));
				// Gudang diturunkan dari notanya kalau user belum memilih.
				if (!frm.doc.gudang && out.gudang) frm.set_value("gudang", out.gudang);
				frm.clear_table("items");
				rows.forEach((r) => Object.assign(frm.add_child("items"), r));
				frm.refresh_field("items");
				frappe.show_alert(__("{0} item ditarik. Klik Suggest Bin untuk membaginya.", [rows.length]));
			},
		});
	},

	// Bagi tiap baris ke bin yang masih muat. Satu bin tidak cukup = barisnya dipecah.
	suggest_bin(frm) {
		if (!frm.doc.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		const rows = (frm.doc.items || [])
			.filter((r) => r.item_code && r.qty > 0)
			.map((r) => ({ item_code: r.item_code, qty: r.qty }));
		if (!rows.length) return frappe.msgprint(__("Tabel masih kosong."));
		frappe.call({
			method: "erpnext_custom.bin_layout.suggest",
			args: { gudang: frm.doc.gudang, rows: JSON.stringify(rows) },
			freeze: true,
			callback(res) {
				const result = res.message || [];
				const source = (frm.doc.items || []).filter((r) => r.item_code && r.qty > 0);
				const kurang = [];
				const planned = [];
				source.forEach((row, i) => {
					const s = result[i];
					if (!s || s.skip) return kurang.push(`${row.item_code}: ${(s && s.skip) || __("dilewati")}`);
					(s.allocations || []).forEach((a) =>
						planned.push({ item_code: row.item_code, bin_location: a.bin_location, qty: a.qty, stock_uom: row.stock_uom })
					);
					if (s.shortage) kurang.push(`${row.item_code}: ${s.shortage} ${__("tidak kebagian bin")}`);
				});
				if (!planned.length) return frappe.msgprint({ title: __("Tidak ada bin"), message: kurang.join("<br>"), indicator: "red" });
				frm.clear_table("items");
				planned.forEach((p) => Object.assign(frm.add_child("items"), p));
				frm.refresh_field("items");
				if (kurang.length)
					frappe.msgprint({ title: __("Sebagian belum dapat bin"), message: kurang.join("<br>"), indicator: "orange" });
			},
		});
	},
});

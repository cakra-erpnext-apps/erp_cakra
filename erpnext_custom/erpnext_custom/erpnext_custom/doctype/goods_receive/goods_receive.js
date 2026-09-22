// Goods Receive: put-away. Tidak menyentuh stok/jurnal — stoknya sudah diakui di
// Purchase Invoice dan barangnya mendarat di bin penampung (staging); dokumen ini
// yang menaikkannya ke rak.

// Nama rak dan bin panjang ("AA01A - Gudang Jakarta - CMI") karena harus unik
// lintas gudang. Yang dibaca orang cuma kodenya, dan gudangnya sudah tertulis di
// kepala dokumen — jadi di tabel mana pun tampilkan potongan pertamanya saja.
["Rack", "Bin Location"].forEach((doctype) => {
	frappe.form.link_formatters[doctype] = (value) => (value || "").split(" - ")[0];
});

// Allocated dikunci begitu tabel Penempatan terisi (baris di bawah dibagi DARI
// angka itu, jadi mengubahnya diam-diam bikin dua tabel bercerita beda). Kuncinya
// DEKLARATIF di read_only_depends_on field-nya, BUKAN grid.toggle_enable():
// toggle_enable menulisi salinan meta yang di-cache per dokumen, jadi sekali
// terkunci ia tidak pernah terbuka lagi sampai halamannya dimuat ulang -- termasuk
// di dokumen baru. Mau ubah alokasi lagi? kosongkan tabel Penempatan.

frappe.ui.form.on("Goods Receive", {
	onload(frm) {
		// PI yang stoknya sudah masuk DAN masih punya sisa belum ditaruh. Nota yang
		// barangnya sudah naik rak semua tidak ditawarkan lagi.
		frm.set_query("purchase_invoice", () => ({
			query: "erpnext_custom.bin_layout.invoices_to_place",
			filters: { gudang: frm.doc.gudang || "" },
		}));
		frm.set_query("gudang", () => ({ filters: { is_group: 0 } }));
		["bin_location", "from_bin_location"].forEach((field) =>
			frm.set_query(field, "items", () => ({
				filters: { gudang: frm.doc.gudang || "", disabled: 0 },
			}))
		);
	},

	gudang(frm) {
		// Ganti gudang = bin yang sudah dipilih tidak berlaku lagi.
		(frm.doc.items || []).forEach((row) => {
			if (row.bin_location) frappe.model.set_value(row.doctype, row.name, "bin_location", null);
		});
	},

	// Satu dokumen boleh memuat beberapa nota, jadi memilih nota MENAMBAH barisnya
	// ke tabel — bukan mengganti isinya. Pilih nota berikutnya untuk menambah lagi.
	purchase_invoice(frm) {
		const nota = frm.doc.purchase_invoice;
		if (!nota) return;
		if ((frm.doc.invoice_items || []).some((r) => r.purchase_invoice === nota))
			return frappe.show_alert({
				message: __("Nota {0} sudah ada di tabel.", [nota]),
				indicator: "orange",
			});
		// Qty yang sudah terdaftar di dokumen ini ikut dikirim, supaya jatah barang
		// yang menunggu di penampung tidak dihitung dua kali untuk dua nota.
		const listed = {};
		(frm.doc.invoice_items || []).forEach((r) => {
			listed[r.item_code] = (listed[r.item_code] || 0) + flt(r.max_qty || r.qty);
		});
		frappe.call({
			method: "erpnext_custom.bin_layout.pull_invoices",
			args: {
				invoices: JSON.stringify([nota]),
				gudang: frm.doc.gudang || "",
				listed: JSON.stringify(listed),
			},
			freeze: true,
			callback(res) {
				const out = res.message || {};
				if (!frm.doc.gudang && out.gudang) frm.set_value("gudang", out.gudang);
				if (out.supplier) frm.set_value("supplier_name", out.supplier);
				const rows = out.rows || [];
				if (!rows.length)
					return frappe.msgprint(
						__("Barang nota ini sudah ditempatkan semua, tidak ada sisa di bin penampung.")
					);
				rows.forEach((r) => Object.assign(frm.add_child("invoice_items"), r));
				frm.refresh_field("invoice_items");
				frappe.show_alert(
					__("{0} baris ditambahkan. Isi kolom Allocated, lalu klik Recommendation.", [
						rows.length,
					])
				);
			},
		});
	},

	// Bagi qty yang DIALOKASIKAN ke bin yang masih muat: terdekat dari staging dan
	// tingkat terbawah dulu. Satu bin tidak cukup = barisnya dipecah ke bin berikutnya.
	suggest_bin(frm) {
		if (!frm.doc.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		const source = (frm.doc.invoice_items || []).filter(
			(r) => r.item_code && flt(r.allocated) > 0
		);
		if (!source.length)
			return frappe.msgprint({
				title: __("Allocation Qty belum diisi"),
				message: __(
					"Isi kolom <b>Allocated</b> di tabel Purchase Invoice dulu — itu yang dibagi ke bin. Sisanya tetap di bin penampung sebagai Outstanding."
				),
				indicator: "red",
			});
		frappe.call({
			method: "erpnext_custom.bin_layout.suggest",
			args: {
				gudang: frm.doc.gudang,
				rows: JSON.stringify(source.map((r) => ({ item_code: r.item_code, qty: r.allocated }))),
			},
			freeze: true,
			callback(res) {
				const result = res.message || [];
				const kurang = [];
				const planned = [];
				source.forEach((row, i) => {
					const s = result[i];
					if (!s || s.skip) return kurang.push(`${row.item_code}: ${(s && s.skip) || __("dilewati")}`);
					(s.allocations || []).forEach((a) =>
						planned.push({
							item_code: row.item_code,
							item_name: row.item_name,
							bin_location: a.bin_location,
							rack: a.rack,
							qty: a.qty,
							weight: a.weight,
							stock_uom: row.stock_uom,
							purchase_invoice: row.purchase_invoice,
						})
					);
					if (s.shortage) kurang.push(`${row.item_code}: ${s.shortage} ${__("tidak kebagian bin")}`);
				});
				if (!planned.length)
					return frappe.msgprint({
						title: __("Tidak ada bin"),
						message: kurang.join("<br>"),
						indicator: "red",
					});
				frm.clear_table("items");
				planned.forEach((p) => Object.assign(frm.add_child("items"), p));
				frm.refresh_field("items");
				frm.layout.refresh_dependency(); // Allocated terkunci sekarang juga
				if (kurang.length)
					frappe.msgprint({
						title: __("Sebagian belum dapat bin"),
						message: kurang.join("<br>"),
						indicator: "orange",
					});
			},
		});
	},
});

frappe.ui.form.on("Goods Receive Invoice Item", {
	// Outstanding tidak pernah diketik: selalu Qty dikurangi Allocated.
	allocated(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// Batasnya Outstanding baris ini, bukan qty notanya: sebagian barang bisa
		// sudah dinaikkan lewat Goods Receive lain.
		const batas = flt(row.max_qty) || flt(row.qty);
		if (flt(row.allocated) > batas) {
			frappe.show_alert({
				message: __("Alokasi dipotong ke Outstanding: {0}", [batas]),
				indicator: "orange",
			});
			frappe.model.set_value(cdt, cdn, "allocated", batas);
			return;
		}
		frappe.model.set_value(cdt, cdn, "outstanding", batas - flt(row.allocated));
	},
});

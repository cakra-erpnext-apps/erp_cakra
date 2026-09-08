// Form bawaan cuma punya tabel Voucher Type + Voucher No yang harus diketik satu per satu,
// jadi repost serentak (mis. Januari s/d bulan ini) tidak praktis. Lihat repost_bulk.py.
//
// Dua jalan dari dialog yang sama:
//   Isi Tabel Saja  -> hasil filter dimasukkan ke form ini, kamu yang Submit (untuk dicek dulu)
//   Repost Sekarang -> dokumen batch dibuat & dijalankan sendiri di background
const CMI_REPOST_BATCH = 1000;

frappe.ui.form.on("Repost Accounting Ledger", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Vouchers"), () => cmi_repost_pick(frm));
		}
		if (!frm._cmi_repost_listener) {
			frm._cmi_repost_listener = true;
			frappe.realtime.on("cmi_bulk_repost", (d) => {
				const gagal = d.failed && d.failed.length ? __(" ({0} gagal)", [d.failed.length]) : "";
				frappe.show_alert(
					{
						message: __("Repost batch {0}/{1} selesai: {2}{3}", [d.done, d.total, d.batch, gagal]),
						indicator: d.done === d.total ? "green" : "blue",
					},
					7
				);
			});
		}
	},
});

function cmi_repost_pick(frm) {
	if (!frm.doc.company) {
		frappe.msgprint(__("Pilih Company dulu."));
		return;
	}
	frappe.call("erpnext_custom.repost_bulk.get_allowed_types").then(({ message: types }) => {
		const d = new frappe.ui.Dialog({
			title: __("Get Vouchers"),
			size: "large",
			fields: [
				{
					fieldname: "from_date", fieldtype: "Date", label: __("From Date"), reqd: 1,
					default: frappe.datetime.year_start(),
				},
				{ fieldname: "cb1", fieldtype: "Column Break" },
				{
					fieldname: "to_date", fieldtype: "Date", label: __("To Date"), reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ fieldname: "sb1", fieldtype: "Section Break" },
				{
					fieldname: "voucher_types", fieldtype: "MultiSelectPills", label: __("Voucher Type"),
					description: __("Kosong = semua tipe yang diizinkan."),
					get_data: () => (types || []).map((t) => ({ value: t, description: "" })),
				},
				{ fieldname: "sb2", fieldtype: "Section Break" },
				{
					fieldname: "party_type", fieldtype: "Select", label: __("Cari Party Sebagai"),
					options: ["", "Customer", "Supplier"].join("\n"),
				},
				{ fieldname: "cb2", fieldtype: "Column Break" },
				{
					fieldname: "party", fieldtype: "Dynamic Link", label: __("Party"),
					options: "party_type",
					depends_on: "party_type",
					description: __("Dicocokkan lewat nama: Payment Entry Pay maupun Receive ikut terambil."),
				},
				{ fieldname: "sb3", fieldtype: "Section Break" },
				{
					fieldname: "batch_size", fieldtype: "Int", label: __("Ukuran Batch"),
					default: CMI_REPOST_BATCH,
					description: __("Di bawah angka ini semuanya jadi satu dokumen, tanpa dipecah."),
				},
				{ fieldname: "cb3", fieldtype: "Column Break" },
				{
					fieldname: "delete_cancelled_entries", fieldtype: "Check", default: 1,
					label: __("Delete Cancelled Entries"),
					description: __("Wajib kalau akun dokumennya berubah -- Payment Ledger ikut dibangun ulang."),
				},
				{ fieldname: "sb4", fieldtype: "Section Break" },
				{
					fieldname: "replace", fieldtype: "Check", label: __("Ganti isi tabel"), default: 1,
					description: __("Hanya untuk tombol \"Isi Tabel Saja\"."),
				},
			],
			primary_action_label: __("Repost Sekarang"),
			primary_action: (v) => cmi_repost_run(frm, d, v),
			secondary_action_label: __("Isi Tabel Saja"),
			secondary_action: () => cmi_repost_fill_only(frm, d, d.get_values()),
		});
		d.show();
	});
}

function cmi_repost_fill_only(frm, d, v) {
	if (!v) return;
	frappe.call({
		method: "erpnext_custom.repost_bulk.get_vouchers",
		freeze: true,
		freeze_message: __("Mencari dokumen..."),
		args: {
			company: frm.doc.company, from_date: v.from_date, to_date: v.to_date,
			voucher_types: v.voucher_types || [], party_type: v.party_type || null,
			party: v.party || null,
		},
	}).then(({ message: res }) => {
		d.hide();
		cmi_repost_fill(frm, res, v.replace);
	});
}

function cmi_repost_run(frm, d, v) {
	frappe.call({
		method: "erpnext_custom.repost_bulk.get_vouchers",
		freeze: true,
		freeze_message: __("Menghitung dokumen..."),
		args: {
			company: frm.doc.company, from_date: v.from_date, to_date: v.to_date,
			voucher_types: v.voucher_types || [], party_type: v.party_type || null,
			party: v.party || null, limit: 0,
		},
	}).then(({ message: res }) => {
		const total = res.total;
		if (!total) {
			frappe.msgprint(__("Tidak ada dokumen yang cocok."));
			return;
		}
		const size = v.batch_size || CMI_REPOST_BATCH;
		const batches = Math.ceil(total / size);
		const rincian =
			batches > 1
				? __("{0} dokumen dipecah jadi {1} batch (@{2}), dijalankan berurutan.", [total, batches, size])
				: __("{0} dokumen, langsung satu kali repost tanpa dipecah.", [total]);
		frappe.confirm(
			rincian +
				"<br><br>" +
				__("GL, Payment Ledger, dan Advance Payment Ledger dokumen-dokumen itu dibangun ulang. Lanjutkan?"),
			() => {
				frappe.call({
					method: "erpnext_custom.repost_bulk.run_bulk_repost",
					freeze: true,
					freeze_message: __("Menyiapkan batch..."),
					args: {
						company: frm.doc.company, from_date: v.from_date, to_date: v.to_date,
						voucher_types: v.voucher_types || [], party_type: v.party_type || null,
						party: v.party || null, batch_size: size,
						delete_cancelled_entries: v.delete_cancelled_entries ? 1 : 0,
					},
				}).then(({ message: out }) => {
					d.hide();
					const links = out.batches
						.map((n) => `<a href="/app/repost-accounting-ledger/${encodeURIComponent(n)}">${n}</a>`)
						.join("<br>");
					frappe.msgprint({
						title: __("Repost berjalan di background"),
						indicator: "blue",
						message:
							__("{0} dokumen, {1} batch:", [out.total, out.batches.length]) +
							"<br><br>" + links +
							"<br><br>" +
							__("Progresnya muncul sebagai notifikasi. Batch yang gagal ditinggal berstatus draft."),
					});
				});
			}
		);
	});
}

function cmi_repost_fill(frm, res, replace) {
	const rows = (res && res.rows) || [];
	if (!rows.length) {
		frappe.msgprint(__("Tidak ada dokumen yang cocok."));
		return;
	}
	if (replace) frm.clear_table("vouchers");
	const seen = new Set((frm.doc.vouchers || []).map((r) => `${r.voucher_type}|${r.voucher_no}`));
	let added = 0;
	for (const r of rows) {
		const key = `${r.voucher_type}|${r.voucher_no}`;
		if (seen.has(key)) continue;
		seen.add(key);
		frm.add_child("vouchers", { voucher_type: r.voucher_type, voucher_no: r.voucher_no });
		added++;
	}
	frm.refresh_field("vouchers");
	let msg = __("{0} dokumen dimasukkan.", [added]);
	if (res.truncated) msg += " " + __("Ketemu {0}, dipotong di {1}.", [res.total, rows.length]);
	frappe.show_alert({ message: msg, indicator: "green" }, 7);

	// Submit manual dari form ini lewat on_submit bawaan: satu job di queue "default"
	// (timeout 300 detik) dan tidak bisa dilanjutkan kalau mati di tengah.
	if (frm.doc.vouchers.length > 500) {
		frappe.msgprint({
			title: __("Terlalu banyak untuk Submit manual"),
			indicator: "orange",
			message: __(
				"Tabel berisi {0} dokumen. Submit dari form ini jalan sebagai satu job dengan timeout 300 detik dan tidak bisa dilanjutkan kalau mati.<br><br>Pakai tombol <b>Repost Sekarang</b> supaya dipecah per batch dan dijalankan di queue panjang.",
				[frm.doc.vouchers.length]
			),
		});
	}
}

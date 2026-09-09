// Pending Cash Refund — pengembalian uang muka per PARTY, satu transfer untuk beberapa
// kasbon sekaligus.
//
// User memilih sendiri kasbonnya di tabel; Refund Amount di kepala dokumen TURUNAN dari
// jumlah baris (read-only), jadi angka atas dan isi tabel tidak akan pernah berbeda.
// Sisa tiap kasbon diambil dari server (method `row_info`), tidak pernah dihitung di sini:
// angka yang dilihat user harus sama dengan yang dipakai validate menolak kelebihan.

// Validated -> isi dokumen dikunci di form; Invalidate membukanya lagi. Void juga
// mengunci (tidak ada Unvoid — dokumennya sudah jadi jejak). Server memaksa aturan yang
// sama lewat _guard_locked_fields; ini supaya kelihatan di form, bukan gantinya.
function pcr_toggle_lock(frm) {
	const locked = !!frm.doc.validated || !!frm.doc.void;
	frm.meta.fields.forEach((df) => {
		if (frappe.model.no_value_type.includes(df.fieldtype)) return;
		frm.set_df_property(df.fieldname, "read_only", locked || df.read_only ? 1 : 0);
	});
	// Tabel alokasi tidak ikut loop di atas: Table termasuk no_value_type. Read-only di
	// field Table-nya sekaligus mematikan tambah/hapus baris, bukan cuma isinya.
	frm.set_df_property("allocations", "read_only", locked ? 1 : 0);
	frm.refresh_field("allocations");
}

function pcr_pending_cash_query(frm) {
	// Daftarnya dibatasi server (open_pending_cash_query): sudah Paid, belum Void, sisanya
	// masih ada, dan belum dipilih di baris lain — jadi yang muncul pasti bisa disimpan.
	return {
		query: "erp.fico.doctype.pending_cash_refund.pending_cash_refund.open_pending_cash_query",
		filters: {
			party_type: frm.doc.party_type,
			party: frm.doc.party,
			company: frm.doc.company,
			currency: frm.doc.currency,
			exclude: frm.is_new() ? "" : frm.doc.name,
			chosen: (frm.doc.allocations || []).map((r) => r.pending_cash).filter(Boolean),
		},
	};
}

function pcr_sum_rows(frm) {
	// Amount MURNI turunan baris — termasuk jadi 0 waktu baris terakhir dihapus.
	frm.set_value(
		"amount",
		(frm.doc.allocations || []).reduce((t, r) => t + flt(r.amount), 0)
	);
}

frappe.ui.form.on("Pending Cash Refund", {
	setup(frm) {
		// Sumber/tujuan dana dipilih dari master Bank Account (daftar rekening
		// perusahaan), bukan dari Chart of Accounts — sama seperti di Pending Cash.
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, is_company_account: 1, disabled: 0 },
		}));
		// Hanya kasbon party ini yang sudah dibayar & belum void. Yang sisanya sudah
		// habis tetap muncul di sini tapi ditolak saat simpan — menyaringnya butuh
		// hitungan per dokumen, terlalu mahal untuk sekadar mengisi dropdown.
		frm.set_query("pending_cash", "allocations", () => pcr_pending_cash_query(frm));
	},

	refresh(frm) {
		pcr_toggle_lock(frm);
		if (frm.doc.void) frm.page.set_indicator(__("Void"), "gray");
		else if (frm.doc.validated) frm.page.set_indicator(__("Validated"), "green");
		else if (!frm.is_new()) frm.page.set_indicator(__("Draft"), "orange");

		if (frm.is_new()) return;
		const act = (method, msg) => () =>
			frappe.confirm(msg, () =>
				frappe
					.call({
						method: `erp.fico.doctype.pending_cash_refund.pending_cash_refund.${method}`,
						args: { names: [frm.doc.name] },
						freeze: true,
					})
					.then((r) => {
						pc_report(r.message);
						frm.reload_doc();
					})
			);

		if (!frm.doc.void) {
			// Satu pasangan bolak-balik: Validate menerbitkan jurnal, Invalidate
			// membatalkan lalu menghapusnya. Arahnya ditentukan status dokumen.
			if (frm.doc.validated) {
				frm.add_custom_button(
					__("Invalidate"),
					act(
						"bulk_invalidate",
						__("Invalidate {0}? Jurnalnya di-cancel lalu DIHAPUS, dokumen balik ke Draft.", [
							frm.doc.name,
						])
					)
				);
			} else {
				frm.add_custom_button(
					__("Validate"),
					act("bulk_validate", __("Validate {0}? Jurnal refund diterbitkan.", [frm.doc.name]))
				);
			}
			// Void = jejak: jurnalnya di-cancel tapi TETAP disimpan, dan nomor refund ini
			// tetap terpakai (refund berikutnya lanjut ke urutan sesudahnya).
			frm.add_custom_button(
				__("Void"),
				act(
					"bulk_void",
					__("Void refund {0}? Jurnalnya di-cancel (tetap disimpan sebagai jejak).", [frm.doc.name])
				)
			);
		}
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
			);
		}
	},

	party_type(frm) {
		// Party lama pasti salah jenis sesudah tipenya diganti — dikosongkan supaya
		// tidak tersimpan diam-diam sebagai link ke doctype yang bukan-bukan.
		frm.set_value("party", null);
	},

	party(frm) {
		// Baris kasbon milik party sebelumnya jelas tidak berlaku lagi.
		frm.clear_table("allocations");
		frm.refresh_field("allocations");
	},

	currency(frm) {
		// Mata uang yang sama dengan company: kursnya WAJIB 1 (dipaksa juga di server).
		// Baris lama dibuang — tabel cuma boleh berisi kasbon semata uang dengan dokumen ini.
		frm.clear_table("allocations");
		frm.refresh_field("allocations");
		if (!frm.doc.company || !frm.doc.currency) return;
		frappe.db.get_value("Company", frm.doc.company, "default_currency").then((r) => {
			if (r.message && r.message.default_currency === frm.doc.currency) {
				frm.set_value("exchange_rate", 1);
			}
		});
	},
});

frappe.ui.form.on("Pending Cash Refund Allocation", {
	pending_cash(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.pending_cash) return;
		frappe
			.call({
				method: "erp.fico.doctype.pending_cash_refund.pending_cash_refund.row_info",
				args: { pending_cash: row.pending_cash, exclude: frm.is_new() ? null : frm.doc.name },
			})
			.then((r) => {
				const d = r.message || {};
				frappe.model.set_value(cdt, cdn, "paid_date", d.paid_date);
				frappe.model.set_value(cdt, cdn, "outstanding", d.available || 0);
				// Diperingatkan di sini, bukan cuma saat simpan: tanggalnya diketik jauh
				// sebelum baris ini dipilih, jadi errornya harus muncul di dekat sebabnya.
				if (frm.doc.refund_date && d.paid_date && frm.doc.refund_date < d.paid_date) {
					frappe.show_alert({
						message: __("Refund Date lebih awal dari Paid Date kasbon ini ({0}).", [
							frappe.format(d.paid_date, { fieldtype: "Date" }),
						]),
						indicator: "orange",
					});
				}
				// Default = kembalikan seluruh sisanya; sebagian tinggal diketik ulang.
				if (!flt(row.amount)) frappe.model.set_value(cdt, cdn, "amount", d.available || 0);
				else pcr_sum_rows(frm);
			});
	},

	amount(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		// Batas atas = sisa kasbonnya. Dikembalikan ke batas, bukan sekadar ditolak:
		// server menolaknya juga, tapi baru saat simpan — terlalu jauh dari ketikannya.
		if (row.outstanding && flt(row.amount) > flt(row.outstanding)) {
			frappe.show_alert({
				message: __("Refund {0} melebihi Outstanding {1} — dipotong ke sisanya.", [
					format_currency(row.amount, frm.doc.currency),
					format_currency(row.outstanding, frm.doc.currency),
				]),
				indicator: "orange",
			});
			frappe.model.set_value(cdt, cdn, "amount", row.outstanding);
			return; // set_value memicu handler ini lagi; penjumlahannya di putaran itu
		}
		pcr_sum_rows(frm);
	},

	allocations_remove: pcr_sum_rows,
});

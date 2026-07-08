// ============================================================================
// Payment Entry — tabel "Expense Note" (Pay → Supplier).
//
// Section "Expense Note" (depends Pay+Supplier) berisi tombol "Tarik Expense Note"
// + tabel custom_expense_notes. Tombol menarik Expense Note (Validated, belum Void)
// milik supplier yang Journal Entry-nya masih punya sisa hutang, lalu mengisi tabel.
// Satu Payment Entry boleh berisi BANYAK Expense Note.
//
// Akuntansi: saat Save, server (erpnext_custom.overrides.payment_entry.before_validate)
// menurunkan baris tabel References (reference_doctype="Journal Entry") dari tabel ini,
// sehingga submit memposting Dr Hutang Usaha — Cr Bank (paid_from) dan sisa hutang
// Expense Note berkurang. Angka outstanding 100% dari mesin ERPNext (server:
// get_expense_note_outstanding → get_outstanding_on_journal_entry).
// ============================================================================
frappe.ui.form.on("Payment Entry", {
	custom_get_expense_notes(frm) { cmi_en_open(frm); },
	custom_expense_notes_remove(frm) { cmi_en_sync_paid(frm); },
});

frappe.ui.form.on("Payment Entry Expense Note", {
	allocated(frm) { cmi_en_sync_paid(frm); },
});

function cmi_en_money(n) {
	return flt(n).toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// paid_amount = total Dibayar dari tabel tarikan (Expense Note + Transaksi;
// hanya bila user belum set manual lebih besar).
function cmi_en_sync_paid(frm) {
	const sum = (rows) => (rows || []).reduce((s, r) => s + flt(r.allocated || r.outstanding), 0);
	const total = sum(frm.doc.custom_expense_notes) + sum(frm.doc.custom_transactions);
	if (total > 0 && flt(frm.doc.paid_amount) < total) frm.set_value("paid_amount", total);
}

function cmi_en_open(frm) {
	if (frm.doc.payment_type !== "Pay" || frm.doc.party_type !== "Supplier") {
		frappe.msgprint(__("Tabel ini untuk pembayaran <b>Pay → Supplier</b>.")); return;
	}
	if (!frm.doc.party) { frappe.msgprint(__("Pilih <b>Supplier</b> dulu.")); return; }
	if (!frm.doc.paid_from) { frappe.msgprint(__("Pilih <b>Account Paid From</b> (Bank) dulu.")); return; }

	frappe.call({
		method: "erpnext_custom.overrides.payment_entry.get_expense_note_outstanding",
		args: { supplier: frm.doc.party, company: frm.doc.company },
		freeze: true,
		freeze_message: __("Mengambil Expense Note…"),
		callback(r) {
			const rows = r.message || [];
			const taken = new Set((frm.doc.custom_expense_notes || []).map((d) => d.expense_note));
			const avail = rows.filter((d) => !taken.has(d.expense_note));
			if (!avail.length) {
				frappe.msgprint(__("Tidak ada Expense Note tervalidasi dengan sisa hutang untuk supplier ini (atau semua sudah ditarik)."));
				return;
			}
			cmi_en_dialog(frm, avail);
		},
	});
}

function cmi_en_dialog(frm, rows) {
	const esc = frappe.utils.escape_html;
	const dlg = new frappe.ui.Dialog({
		title: __("Tarik Expense Note"),
		size: "large",
		fields: [{ fieldname: "list_html", fieldtype: "HTML" }],
		primary_action_label: __("Tambahkan Terpilih"),
		primary_action() { cmi_en_add(frm, dlg, rows); },
	});

	const body = rows.map((d, i) => `
		<tr>
			<td style="text-align:center"><input type="checkbox" class="cmi-en-chk" data-i="${i}" checked></td>
			<td>${esc(d.expense_note)}</td>
			<td>${esc(d.posting_date || "")}</td>
			<td class="text-muted">${esc(d.journal_entry)}</td>
			<td style="text-align:right">${cmi_en_money(d.net_total)}</td>
			<td style="text-align:right"><b>${cmi_en_money(d.outstanding)}</b></td>
		</tr>`).join("");

	dlg.fields_dict.list_html.$wrapper.html(`
		<div class="text-muted small" style="margin-bottom:6px">${rows.length} Expense Note · centang yang mau ditarik</div>
		<div style="max-height:52vh;overflow:auto">
		<table class="table table-bordered" style="font-size:12.5px;margin-bottom:0">
			<thead><tr>
				<th style="width:34px;text-align:center"><input type="checkbox" class="cmi-en-all" checked></th>
				<th>Expense Note</th><th>Tanggal</th><th>Journal Entry</th>
				<th style="text-align:right">Net Total</th><th style="text-align:right">Sisa Hutang</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table></div>
		<div style="text-align:right;margin-top:8px;font-weight:600">Total terpilih: Rp <span class="cmi-en-sum">0</span></div>`);

	const $w = dlg.fields_dict.list_html.$wrapper;
	const recalc = () => {
		let s = 0;
		$w.find(".cmi-en-chk:checked").each(function () { s += flt(rows[$(this).data("i")].outstanding); });
		$w.find(".cmi-en-sum").text(cmi_en_money(s));
	};
	$w.find(".cmi-en-all").on("change", function () {
		$w.find(".cmi-en-chk").prop("checked", this.checked); recalc();
	});
	$w.on("change", ".cmi-en-chk", recalc);
	recalc();
	dlg.show();
}

function cmi_en_add(frm, dlg, rows) {
	const picked = [];
	dlg.fields_dict.list_html.$wrapper.find(".cmi-en-chk:checked").each(function () {
		picked.push(rows[$(this).data("i")]);
	});
	if (!picked.length) { frappe.msgprint(__("Belum ada Expense Note dipilih.")); return; }

	picked.forEach((d) => {
		const row = frm.add_child("custom_expense_notes");
		row.expense_note = d.expense_note;
		row.journal_entry = d.journal_entry;
		row.posting_date = d.posting_date;
		row.net_total = d.net_total;
		row.outstanding = d.outstanding;
		row.allocated = d.outstanding;
		row.currency = d.currency;
	});
	frm.refresh_field("custom_expense_notes");
	cmi_en_sync_paid(frm);

	dlg.hide();
	frappe.show_alert({ message: __("{0} Expense Note ditambahkan. Klik Save untuk membuat References.", [picked.length]), indicator: "green" });
}

// ============================================================================
// Mode CMI: "Expense / Income" (custom_direct) & Mode of Payment "Settlement".
// - Default (tanpa centang, mode of payment lain): perilaku native — party -> bank.
// - Expense/Income: party & tarikan transaksi disembunyikan; isi Pay To + tabel
//   item manual (note/account/amount) -> total otomatis jadi paid_amount.
// - Mode of Payment "Settlement": field Bank disembunyikan, diganti akun
//   custom_settlement_account (server yang menukar paid_from/paid_to saat save).
// ============================================================================
function cmi_pe_is_settlement(frm) {
	return (frm.doc.mode_of_payment || "").trim().toLowerCase() === "settlement";
}

function cmi_pe_toggle(frm) {
	const direct = !!frm.doc.custom_direct;
	const settle = cmi_pe_is_settlement(frm);
	const receive = frm.doc.payment_type === "Receive";
	// Field pihak + tarikan transaksi: sembunyikan saat mode direct.
	["party_type", "party", "party_balance", "references",
		"custom_expense_notes", "custom_get_expense_notes"].forEach((f) => {
		if (frm.fields_dict[f]) frm.toggle_display(f, !direct);
	});
	// Sisi akun party (Pay: paid_to, Receive: paid_from) ikut hilang saat direct.
	frm.toggle_display(receive ? "paid_from" : "paid_to", !direct);
	// Sisi bank (Pay: paid_from, Receive: paid_to) hilang saat settlement.
	frm.toggle_display(receive ? "paid_to" : "paid_from", !settle);
	// Kunci akun yang terisi otomatis: sisi party terkunci saat party dipilih,
	// sisi bank terkunci saat Company Bank Account dipilih.
	frm.set_df_property(receive ? "paid_from" : "paid_to", "read_only", frm.doc.party ? 1 : 0);
	frm.set_df_property(receive ? "paid_to" : "paid_from", "read_only", frm.doc.bank_account ? 1 : 0);
}

function cmi_pe_sync_direct_total(frm) {
	if (!frm.doc.custom_direct) return;
	const total = (frm.doc.custom_direct_items || []).reduce((s, r) => s + flt(r.amount), 0);
	if (total > 0) {
		frm.set_value("paid_amount", total);
		frm.set_value("received_amount", total);
	}
}

frappe.ui.form.on("Payment Entry", {
	onload(frm) {
		frm.set_query("account", "custom_direct_items", () => ({
			filters: { company: frm.doc.company, is_group: 0 },
		}));
		frm.set_query("custom_settlement_account", () => ({
			filters: { company: frm.doc.company, is_group: 0 },
		}));
	},
	refresh: cmi_pe_toggle,
	payment_type: cmi_pe_toggle,
	custom_direct(frm) {
		if (frm.doc.custom_direct) {
			frm.set_value("party_type", "");
			frm.set_value("party", "");
			frm.clear_table("references");
			frm.clear_table("custom_expense_notes");
			frm.refresh_field("references");
			frm.refresh_field("custom_expense_notes");
			cmi_pe_sync_direct_total(frm);
		}
		cmi_pe_toggle(frm);
	},
	mode_of_payment: cmi_pe_toggle,
	party: cmi_pe_toggle,
	bank_account: cmi_pe_toggle,
});

// ============================================================================
// "Tarik Transaksi" — transaksi outstanding milik party (Customer/Receive ->
// Sales Invoice, Supplier/Pay -> Purchase Invoice) ke tabel custom_transactions.
// Server (before_validate) menurunkan baris References dari tabel ini saat Save.
// ============================================================================
frappe.ui.form.on("Payment Entry", {
	custom_get_transactions(frm) { cmi_txn_open(frm); },
	custom_transactions_remove(frm) { cmi_en_sync_paid(frm); },
});

frappe.ui.form.on("Payment Entry Transaction", {
	allocated(frm) { cmi_en_sync_paid(frm); },
});

function cmi_txn_open(frm) {
	const ok = (frm.doc.payment_type === "Receive" && frm.doc.party_type === "Customer")
		|| (frm.doc.payment_type === "Pay" && frm.doc.party_type === "Supplier");
	if (!ok) {
		frappe.msgprint(__("Tarik Transaksi untuk <b>Receive → Customer</b> atau <b>Pay → Supplier</b>."));
		return;
	}
	if (!frm.doc.party) { frappe.msgprint(__("Pilih <b>Party</b> dulu.")); return; }

	frappe.call({
		method: "erpnext_custom.overrides.payment_entry.get_party_outstanding_transactions",
		args: {
			party_type: frm.doc.party_type,
			party: frm.doc.party,
			company: frm.doc.company,
			payment_type: frm.doc.payment_type,
		},
		freeze: true,
		freeze_message: __("Mengambil transaksi outstanding…"),
		callback(r) {
			const rows = r.message || [];
			const taken = new Set((frm.doc.custom_transactions || []).map((d) => d.transaction));
			const avail = rows.filter((d) => !taken.has(d.transaction));
			if (!avail.length) {
				frappe.msgprint(__("Tidak ada transaksi outstanding untuk party ini (atau semua sudah ditarik)."));
				return;
			}
			cmi_txn_dialog(frm, avail);
		},
	});
}

function cmi_txn_dialog(frm, rows) {
	const esc = frappe.utils.escape_html;
	const dlg = new frappe.ui.Dialog({
		title: __("Tarik Transaksi"),
		size: "large",
		fields: [{ fieldname: "list_html", fieldtype: "HTML" }],
		primary_action_label: __("Tambahkan Terpilih"),
		primary_action() { cmi_txn_add(frm, dlg, rows); },
	});

	const body = rows.map((d, i) => `
		<tr>
			<td style="text-align:center"><input type="checkbox" class="cmi-txn-chk" data-i="${i}" checked></td>
			<td>${esc(d.transaction)}</td>
			<td>${esc(d.date || "")}</td>
			<td style="text-align:right">${cmi_en_money(d.grand_total)}</td>
			<td style="text-align:right"><b>${cmi_en_money(d.outstanding)}</b></td>
		</tr>`).join("");

	dlg.fields_dict.list_html.$wrapper.html(`
		<div class="text-muted small" style="margin-bottom:6px">${rows.length} transaksi outstanding · centang yang mau ditarik</div>
		<div style="max-height:52vh;overflow:auto">
		<table class="table table-bordered" style="font-size:12.5px;margin-bottom:0">
			<thead><tr>
				<th style="width:34px;text-align:center"><input type="checkbox" class="cmi-txn-all" checked></th>
				<th>Transaksi</th><th>Tanggal</th>
				<th style="text-align:right">Total</th><th style="text-align:right">Sisa</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table></div>
		<div style="text-align:right;margin-top:8px;font-weight:600">Total terpilih: Rp <span class="cmi-txn-sum">0</span></div>`);

	const $w = dlg.fields_dict.list_html.$wrapper;
	const recalc = () => {
		let s = 0;
		$w.find(".cmi-txn-chk:checked").each(function () { s += flt(rows[$(this).data("i")].outstanding); });
		$w.find(".cmi-txn-sum").text(cmi_en_money(s));
	};
	$w.find(".cmi-txn-all").on("change", function () {
		$w.find(".cmi-txn-chk").prop("checked", this.checked); recalc();
	});
	$w.on("change", ".cmi-txn-chk", recalc);
	recalc();
	dlg.show();
}

function cmi_txn_add(frm, dlg, rows) {
	const picked = [];
	dlg.fields_dict.list_html.$wrapper.find(".cmi-txn-chk:checked").each(function () {
		picked.push(rows[$(this).data("i")]);
	});
	if (!picked.length) { frappe.msgprint(__("Belum ada transaksi dipilih.")); return; }

	picked.forEach((d) => {
		const row = frm.add_child("custom_transactions");
		row.reference_doctype = d.reference_doctype;
		row.transaction = d.transaction;
		row.date = d.date;
		row.grand_total = d.grand_total;
		row.outstanding = d.outstanding;
		row.allocated = d.outstanding;
	});
	frm.refresh_field("custom_transactions");
	cmi_en_sync_paid(frm);

	dlg.hide();
	frappe.show_alert({ message: __("{0} transaksi ditambahkan. Klik Save untuk membuat References.", [picked.length]), indicator: "green" });
}

// Mode of Payment "Settlement" sengaja TANPA default account (akunnya dipilih user
// di field Settlement Account) — cegat helper core supaya tidak memanggil
// get_bank_cash_account (frappe.throw "Please set default Cash or Bank account").
if (erpnext?.accounts?.pos?.get_payment_mode_account) {
	const cmi_core_get_pma = erpnext.accounts.pos.get_payment_mode_account;
	erpnext.accounts.pos.get_payment_mode_account = function (frm, mode_of_payment, callback) {
		if ((mode_of_payment || "").trim().toLowerCase() === "settlement") return;
		return cmi_core_get_pma.call(this, frm, mode_of_payment, callback);
	};
}

frappe.ui.form.on("Payment Entry Direct Item", {
	amount(frm) { cmi_pe_sync_direct_total(frm); },
	custom_direct_items_remove(frm) { cmi_pe_sync_direct_total(frm); },
});

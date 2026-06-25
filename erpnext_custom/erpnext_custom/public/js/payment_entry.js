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

// paid_amount = total Dibayar dari tabel (hanya bila user belum set manual lebih besar).
function cmi_en_sync_paid(frm) {
	const total = (frm.doc.custom_expense_notes || [])
		.reduce((s, r) => s + flt(r.allocated || r.outstanding), 0);
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

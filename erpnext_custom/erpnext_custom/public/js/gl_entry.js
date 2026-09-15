// GL Entry cuma SATU baris buku besar. Form bawaan menampilkan baris itu saja, jadi
// sulit membaca jurnalnya. Di sini seluruh baris satu voucher (yang sama status
// batal/tidaknya) digambar sebagai tabel "Accounting Entries" ala Journal Entry,
// lengkap dengan total debit/kredit + selisih. Baris yang sedang dibuka disorot.
//
// Murni client-side: dipasang lewat frm.dashboard.add_section, jadi tidak ada Custom
// Field / fixture / migrate yang perlu diurus.

frappe.ui.form.on("GL Entry", {
	refresh(frm) {
		// Section digambar ulang tiap refresh -- buang versi lama dulu.
		frm.dashboard.parent.find(".gle-voucher").remove();
		if (!frm.doc.voucher_no) return;

		Promise.all([
			frappe.db.get_list("GL Entry", {
				filters: {
					voucher_type: frm.doc.voucher_type,
					voucher_no: frm.doc.voucher_no,
					is_cancelled: cint(frm.doc.is_cancelled),
				},
				fields: [
					"name",
					"account",
					"party_type",
					"party",
					"cost_center",
					"debit",
					"credit",
				],
				order_by: "creation asc",
				limit: 500,
			}),
			frappe.db.get_value("Company", frm.doc.company, "default_currency"),
		]).then(([rows, company]) => {
			if (!rows || !rows.length) return;
			render(frm, rows, (company.message || {}).default_currency);
		});
	},
});

function render(frm, rows, currency) {
	let total_debit = 0;
	let total_credit = 0;

	const body = rows
		.map((r, i) => {
			total_debit += flt(r.debit);
			total_credit += flt(r.credit);
			const party = r.party ? `${r.party_type || ""} ${r.party}`.trim() : "";
			return `<tr class="${r.name === frm.doc.name ? "gle-current" : ""}">
				<td class="text-muted">${i + 1}</td>
				<td>${link(r)}${party ? `<div class="text-muted small">${frappe.utils.escape_html(party)}</div>` : ""}</td>
				<td>${frappe.utils.escape_html(r.cost_center || "")}</td>
				<td class="text-right">${amount(r.debit, currency)}</td>
				<td class="text-right">${amount(r.credit, currency)}</td>
			</tr>`;
		})
		.join("");

	const diff = flt(total_debit - total_credit, frappe.boot.sysdefaults.currency_precision || 2);
	const diff_row = diff
		? `<tr><td colspan="3" class="text-right text-danger">${__("Difference")}</td>
			<td colspan="2" class="text-right text-danger">${format_currency(diff, currency)}</td></tr>`
		: "";

	const html = `
		<style>
			.gle-voucher .gle-current > td { background: var(--highlight-color); font-weight: 600; }
			.gle-voucher table { margin-bottom: 0; }
			.gle-voucher td, .gle-voucher th { vertical-align: middle; }
		</style>
		<div class="text-muted small" style="margin-bottom: 8px;">
			${frappe.utils.escape_html(frm.doc.voucher_type || "")}
			${frappe.utils.get_form_link(frm.doc.voucher_type, frm.doc.voucher_no, true)}
			${frappe.datetime.str_to_user(frm.doc.posting_date)}
			${cint(frm.doc.is_cancelled) ? `<span class="indicator-pill red">${__("Cancelled")}</span>` : ""}
		</div>
		<table class="table table-bordered table-sm">
			<thead><tr>
				<th style="width: 40px;"></th>
				<th>${__("Account")}</th>
				<th style="width: 22%;">${__("Cost Center")}</th>
				<th class="text-right" style="width: 16%;">${__("Debit")}</th>
				<th class="text-right" style="width: 16%;">${__("Credit")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot>
				<tr>
					<td colspan="3" class="text-right"><b>${__("Total")}</b></td>
					<td class="text-right"><b>${format_currency(total_debit, currency)}</b></td>
					<td class="text-right"><b>${format_currency(total_credit, currency)}</b></td>
				</tr>
				${diff_row}
			</tfoot>
		</table>
		${frm.doc.remarks ? `<div class="text-muted small" style="margin-top: 8px;">${frappe.utils.escape_html(frm.doc.remarks)}</div>` : ""}
	`;

	frm.dashboard.add_section(html, __("Accounting Entries"), "custom gle-voucher");
}

function link(row) {
	return frappe.utils.get_form_link("GL Entry", row.name, true, frappe.utils.escape_html(row.account));
}

function amount(value, currency) {
	return flt(value) ? format_currency(flt(value), currency) : "";
}

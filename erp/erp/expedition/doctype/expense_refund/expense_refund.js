// Expense Refund — tabel Refund Items HANYA bisa diisi lewat tombol "Add Transaction"
// (Add Row bawaan grid disembunyikan). Dialognya mirror picker "Tarik Expense Note" di
// Sales Invoice (Invoice Reimburse): satu frappe.call flat, dikelompokkan per Expense Note
// di client (tabel dengan baris group-header + baris item, checkbox cascade, search lokal)
// — bukan dialog paging server seperti Add Items Payment Entry.

// Supplier/Currency/Rate dikunci HANYA selagi ada baris di tabel (biar tidak diam-diam
// mengubah dasar baris yang sudah ditarik). Dikelola manual (bukan read_only_depends_on
// di JSON) karena hapus baris lewat grid tidak memicu Frappe meng-evaluasi ulang
// depends_on field lain -- field-nya nyangkut kekunci walau tabel sudah kosong.
function er_lock_header(frm) {
	const locked = !!(frm.doc.items || []).length;
	["vendor", "currency", "conversion_rate"].forEach((f) => frm.set_df_property(f, "read_only", locked));
}

frappe.ui.form.on("Expense Refund", {
	refresh(frm) {
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (grid) {
			grid.cannot_add_rows = true; // baris hanya lewat tombol Add Transaction
			grid.refresh();
		}
		er_lock_header(frm);
	},

	vendor(frm) {
		if ((frm.doc.items || []).length) return; // sudah ada baris -> vendor terkunci
		frm.set_value("currency", "");
		frm.set_value("conversion_rate", 1);
	},

	add_transaction(frm) {
		if (!frm.doc.vendor) {
			frappe.msgprint(__("Pilih <b>Supplier</b> dulu."));
			return;
		}
		er_open_picker(frm);
	},

	// Baris dihapus lewat grid -> kalau tabel jadi kosong, header harus terbuka lagi.
	items_remove(frm) {
		er_lock_header(frm);
	},
});

function er_open_picker(frm) {
	const company = frm.doc.company || frappe.defaults.get_default("company");
	const dlg = new frappe.ui.Dialog({
		title: __("Pilih Expense Note"),
		size: "extra-large",
		fields: [{ fieldname: "list_html", fieldtype: "HTML" }],
		primary_action_label: __("Tambahkan"),
		primary_action() { er_picker_add(frm, dlg); },
	});
	dlg.show();
	dlg.fields_dict.list_html.$wrapper.html('<div class="text-muted" style="padding:12px;">Memuat…</div>');
	frappe.call({
		method: "erp.expedition.doctype.expense_refund.expense_refund.get_expense_note_transactions",
		args: { vendor: frm.doc.vendor, company },
	}).then((r) => er_picker_render(dlg, r.message || []));
}

// Render picker: dikelompokkan per Expense Note (header = No EN + tanggal + sisa yang
// bisa direfund), baris item di bawahnya. Search menyaring No EN / deskripsi / akun.
function er_picker_render(dlg, rows) {
	const esc = frappe.utils.escape_html;
	const cur = (dlg._currency = rows[0] && rows[0].currency) || "IDR";
	const fmt = (v) => format_currency(v || 0, cur);
	dlg._rows = rows;
	const $w = dlg.fields_dict.list_html.$wrapper;

	// Kelompokkan per EN dengan urutan kemunculan; simpan index asli tiap baris (data-i).
	const groups = [];
	const gmap = {};
	rows.forEach((r, i) => {
		let g = gmap[r.expense_note];
		if (!g) { g = gmap[r.expense_note] = { en: r, items: [] }; groups.push(g); }
		g.items.push({ r, i });
	});

	const bodyHtml = groups.map((g) => {
		const en = g.en;
		const date = en.date ? frappe.datetime.str_to_user(en.date) : "";
		const badge = `<span class="indicator-pill green" style="margin-left:8px;">${esc(__("Sisa"))} ${fmt(en.sisa_en)}</span>`;
		const gsearch = (en.expense_note || "").toLowerCase();
		const head = `
			<tr class="er-rgroup" data-s="${esc(gsearch)}" style="background:#f4f5f6;">
				<td style="text-align:center;"><input type="checkbox" class="er-rpick-grp"></td>
				<td colspan="3">
					<b>${esc(en.expense_note || "")}</b>${badge}
					<span class="text-muted small" style="margin-left:8px;">${esc(date)}</span>
				</td>
			</tr>`;
		const lines = g.items.map(({ r, i }) => `
			<tr class="er-rrow" data-s="${esc(((r.description || r.expense_account || "") + " " + gsearch).toLowerCase())}">
				<td style="text-align:center;"><input type="checkbox" class="er-rpick" data-i="${i}"></td>
				<td></td>
				<td>${esc(r.description || r.expense_account || "-")}</td>
				<td style="text-align:right;">${fmt(r.amount)}</td>
			</tr>`).join("");
		return head + lines;
	}).join("") || `<tr><td colspan="4" class="text-muted text-center" style="padding:12px;">${esc(__("Tidak ada Expense Note yang bisa direfund."))}</td></tr>`;

	$w.html(`
		<div style="display:flex; gap:10px; align-items:center; margin-bottom:8px;">
			<input type="text" class="form-control input-sm er-rsearch" style="max-width:340px;"
				placeholder="${esc(__("Cari: No Expense Note / Deskripsi / Akun"))}">
			<span class="text-muted small">${rows.length} ${esc(__("baris"))}</span>
		</div>
		<div style="max-height:52vh;overflow:auto;">
		<table class="table table-bordered" style="font-size:12.5px;margin-bottom:0;">
			<thead><tr>
				<th style="width:34px;text-align:center;"><input type="checkbox" class="er-rpick-all"></th>
				<th></th><th>${esc(__("Deskripsi / Akun"))}</th><th style="text-align:right;">${esc(__("Jumlah"))}</th>
			</tr></thead>
			<tbody>${bodyHtml}</tbody>
		</table></div>`);

	// Centang semua -> hanya baris yang sedang terlihat (hasil search).
	$w.find(".er-rpick-all").on("change", function () {
		$w.find("tr.er-rrow:visible .er-rpick").prop("checked", this.checked);
		$w.find("tr.er-rgroup:visible .er-rpick-grp").prop("checked", this.checked);
	});
	// Centang per-EN (header group) -> semua item milik EN itu.
	$w.on("change", ".er-rpick-grp", function () {
		const $rows = $(this).closest("tr").nextUntil(".er-rgroup").filter(":visible");
		$rows.find(".er-rpick").prop("checked", this.checked);
	});
	// Search: saring group + baris item; group tampil kalau masih ada baris cocok.
	$w.find(".er-rsearch").on("input", function () {
		const q = (this.value || "").trim().toLowerCase();
		$w.find("tr.er-rgroup").each(function () {
			const $g = $(this);
			const $lines = $g.nextUntil(".er-rgroup");
			if (!q) { $g.show(); $lines.show(); return; }
			let any = false;
			$lines.each(function () {
				const hit = ($(this).data("s") || "").indexOf(q) !== -1;
				$(this).toggle(hit);
				if (hit) any = true;
			});
			$g.toggle(any || ($g.data("s") || "").indexOf(q) !== -1);
			if (!any && ($g.data("s") || "").indexOf(q) !== -1) $lines.show();
		});
	});
}

function er_picker_add(frm, dlg) {
	const $w = dlg.fields_dict.list_html.$wrapper;
	const picked = [];
	$w.find(".er-rpick:checked").each(function () { picked.push(dlg._rows[$(this).data("i")]); });
	if (!picked.length) { frappe.msgprint(__("Belum ada baris dipilih.")); return; }
	if (!frm.doc.currency) {
		frm.set_value("currency", picked[0].currency);
		frm.set_value("conversion_rate", picked[0].conversion_rate || 1);
	}
	const seen = new Set((frm.doc.items || []).map((it) => it.expense_note_item).filter(Boolean));
	let added = 0;
	picked.forEach((d) => {
		if (seen.has(d.expense_note_item)) return;
		const row = frm.add_child("items");
		row.expense_note = d.expense_note;
		row.expense_note_item = d.expense_note_item;
		row.description = d.description;
		row.expense_account = d.expense_account;
		row.max_refundable = d.sisa_en;
		row.refund_amount = d.amount;
		row.tax = d.tax;
		row.pph = d.pph;
		row.discount = d.discount;
		row.materai = d.materai;
		seen.add(d.expense_note_item);
		added++;
	});
	dlg.hide();
	setTimeout(() => {
		frm.refresh_field("items");
		er_lock_header(frm);
		frm.dirty();
		frappe.show_alert({ message: __("{0} baris ditambahkan.", [added]), indicator: "green" });
	}, 50);
}

// ============================================================================
// Payment Entry — SATU tabel "Items" (custom_transactions) + tombol "Add Items".
//
// Tombol menarik dokumen outstanding milik party:
//   Pay     -> Supplier: Expense Note (Validated) + Purchase Invoice + Debit Note (PI retur)
//   Receive -> Customer: Sales Invoice + Credit Note (SI retur)
// Baris Debit/Credit Note sisanya NEGATIF (pengurang tagihan) — memang begitu.
//
// Akuntansi: saat Save, server (erpnext_custom.overrides.payment_entry.before_validate)
// menurunkan baris tabel References dari tabel ini — baris Expense Note direferensikan ke
// JOURNAL ENTRY-nya (di sanalah hutangnya), baris invoice ke dokumennya sendiri. Angka
// outstanding 100% dari mesin ERPNext (get_outstanding_reference_documents /
// get_outstanding_on_journal_entry), jadi tak akan beda dengan dialog native.
// ============================================================================
// ---- Bank -> Bank Account -> Account From (rantai otomatis) ----
// custom_bank (master Bank) dipilih -> cari Bank Account rekening company milik bank
// itu -> bank_account terisi -> Account From (Pay) / Account Paid To (Receive) diisi
// akun GL milik rekening tsb. Dokumen baru: Bank dgn custom_default_bank tercentang
// terpilih otomatis.
function cmi_pe_apply_bank(frm) {
	if (!frm.doc.custom_bank) return;
	const filters = { bank: frm.doc.custom_bank, is_company_account: 1 };
	if (frm.doc.company) filters.company = frm.doc.company;
	frappe.db.get_value("Bank Account", filters, ["name", "account"]).then((r) => {
		const m = (r && r.message) || {};
		if (!m.name) {
			frappe.show_alert({
				message: __("Bank {0} belum punya Bank Account (rekening company).", [frm.doc.custom_bank]),
				indicator: "orange",
			});
			return;
		}
		if (frm.doc.bank_account !== m.name) frm.set_value("bank_account", m.name);
		const side = frm.doc.payment_type === "Receive" ? "paid_to" : "paid_from";
		if (m.account && frm.doc[side] !== m.account) frm.set_value(side, m.account);
	});
}

function cmi_pe_default_bank(frm) {
	if (!frm.is_new() || frm.doc.custom_bank || frm.doc.bank_account) return;
	frappe.db.get_value("Bank", { custom_default_bank: 1 }, "name").then((r) => {
		const name = r && r.message && r.message.name;
		if (name) frm.set_value("custom_bank", name);
	});
}

// Currency & Exchange Rate selalu tampil: core menyembunyikan exchange rate saat
// currency = currency company (toggle_display). Jalankan belakangan (setTimeout)
// supaya menang atas toggle core.
function cmi_pe_show_currency(frm) {
	setTimeout(() => {
		frm.set_df_property("source_exchange_rate", "hidden", 0);
		frm.toggle_display("source_exchange_rate", true);
		frm.toggle_display("paid_from_account_currency", true);
	}, 300);
}

frappe.ui.form.on("Payment Entry", {
	custom_get_transactions(frm) { cmi_items_open(frm); },
	custom_transactions_remove(frm) { cmi_sync_paid(frm); },
	custom_bank(frm) { cmi_pe_apply_bank(frm); },
	custom_get_pending(frm) {
		// Scaffold: sumber tarikan dokumen Pending Cash belum ditentukan —
		// sementara baris diisi manual di tabelnya.
		frappe.msgprint(__("Sumber dokumen Pending Cash belum dikonfigurasi. Untuk sekarang isi barisnya manual di tabel Pending Cash."));
	},
	custom_tax_input(frm) { cmi_pe_smart(frm, "custom_tax_input", "custom_tax_pct", "custom_tax_amount"); },
	custom_pph_input(frm) { cmi_pe_smart(frm, "custom_pph_input", "custom_pph_pct", "custom_pph_amount"); },
});

// Smart input Amount Tax / PPh (mirror Expense Note): "11%" -> persen, "150000" ->
// nominal; tampilan dirapikan jadi format money. Parser toleran titik/koma.
function cmi_pe_to_number(s) {
	s = String(s == null ? "" : s).replace(/[^\d.,-]/g, "");
	if (!s) return 0;
	const lastDot = s.lastIndexOf("."), lastComma = s.lastIndexOf(",");
	let dec = null;
	if (lastDot !== -1 && lastComma !== -1) dec = lastDot > lastComma ? "." : ",";
	else if (lastComma !== -1) dec = /^-?\d{1,3}(,\d{3})+$/.test(s) ? null : ",";
	else if (lastDot !== -1) dec = /^-?\d{1,3}(\.\d{3})+$/.test(s) ? null : ".";
	let intp = s, frac = "";
	if (dec) {
		const i = s.lastIndexOf(dec);
		intp = s.slice(0, i);
		frac = s.slice(i + 1);
	}
	intp = intp.replace(/[.,]/g, "");
	frac = frac.replace(/[.,]/g, "");
	return parseFloat(intp + (frac ? "." + frac : "")) || 0;
}

function cmi_pe_smart(frm, in_f, pct_f, amt_f) {
	const raw = (frm.doc[in_f] || "").trim();
	if (!raw) { frm.doc[pct_f] = 0; frm.doc[amt_f] = 0; return; }
	const is_pct = raw.indexOf("%") !== -1;
	const num = cmi_pe_to_number(raw);
	let text;
	if (is_pct) {
		frm.doc[pct_f] = num;
		const base = (frm.doc.custom_transactions || []).reduce((s, r) => s + flt(r.allocated || r.outstanding), 0);
		frm.doc[amt_f] = base * num / 100;
		text = String(num).replace(".", ",") + "%";
	} else {
		frm.doc[pct_f] = 0;
		frm.doc[amt_f] = num;
		text = format_number(num, null, 2);
	}
	if (frm.doc[in_f] !== text) { frm.doc[in_f] = text; frm.refresh_field(in_f); }
	frm.set_df_property(in_f, "description", frm.doc[amt_f]
		? __("= {0}", [format_currency(frm.doc[amt_f], frm.doc.paid_from_account_currency || "IDR")])
		: __('Ketik mis. "11%" atau "150000"'));
}

frappe.ui.form.on("Payment Entry Transaction", {
	allocated(frm) { cmi_sync_paid(frm); },
});

function cmi_money(n) {
	return flt(n).toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// paid_amount = total kolom Dibayar (hanya bila user belum set manual lebih besar).
function cmi_sync_paid(frm) {
	const total = (frm.doc.custom_transactions || [])
		.reduce((s, r) => s + flt(r.allocated || r.outstanding), 0);
	if (total > 0 && flt(frm.doc.paid_amount) < total) frm.set_value("paid_amount", total);
}

const CMI_PAGE_LENGTH = 20;

function cmi_items_open(frm) {
	const pay = frm.doc.payment_type === "Pay" && frm.doc.party_type === "Supplier";
	const receive = frm.doc.payment_type === "Receive" && frm.doc.party_type === "Customer";
	if (!pay && !receive) {
		frappe.msgprint(__("Add Items untuk <b>Pay → Supplier</b> atau <b>Receive → Customer</b>."));
		return;
	}
	if (!frm.doc.party) { frappe.msgprint(__("Pilih <b>Party</b> dulu.")); return; }
	cmi_items_dialog(frm);
}

// Dialog Add Items — pencarian & paging di SERVER (party bisa punya ribuan transaksi;
// mengirim + merender semuanya membuat browser tersendat). Yang dikirim hanya satu halaman.
//
// `picked` menyimpan baris yang DICENTANG lintas halaman & lintas pencarian (key = nomor
// dokumen), jadi user bisa cari "EXP", centang, cari "PINV", centang lagi, lalu Tambahkan
// sekali — centang halaman sebelumnya tidak hilang.
function cmi_items_dialog(frm) {
	const esc = frappe.utils.escape_html;
	const picked = new Map();
	const state = { start: 0, total: 0, search: "", rows: [], loading: false };

	const dlg = new frappe.ui.Dialog({
		title: __("Add Items"),
		size: "large",
		fields: [
			{ fieldname: "search", fieldtype: "Data", label: __("Cari"),
			  description: __("Nomor dokumen, tipe, atau owner.") },
			{ fieldname: "list_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Tambahkan & Tutup"),
		primary_action() {
			if (cmi_items_add(frm, picked)) dlg.hide();
		},
		// Tambah tanpa menutup dialog: baris masuk ke tabel, daftar dimuat ulang (yang baru
		// ditambah otomatis hilang dari daftar karena dikirim sebagai `exclude`), user bisa
		// lanjut cari & tambah lagi. set_secondary_action melakukan .off("click") -> dialog
		// TIDAK ikut tertutup.
		secondary_action_label: __("Tambahkan & Lanjut"),
		secondary_action() {
			if (!cmi_items_add(frm, picked)) return;
			picked.clear();
			state.start = 0;
			load();
		},
	});

	const $w = dlg.fields_dict.list_html.$wrapper;

	const render = () => {
		const body = state.rows.map((d) => `
			<tr>
				<td style="text-align:center">
					<input type="checkbox" class="cmi-item-chk" data-name="${esc(d.transaction)}"
						${picked.has(d.transaction) ? "checked" : ""}></td>
				<td>${esc(d.doc_label || d.reference_doctype)}</td>
				<td>${esc(d.transaction)}</td>
				<td>${esc(d.owner_name || "")}</td>
				<td>${esc(d.date || "")}</td>
				<td style="text-align:right">${cmi_money(d.grand_total)}</td>
				<td style="text-align:right"><b>${cmi_money(d.outstanding)}</b></td>
			</tr>`).join("");

		const from = state.total ? state.start + 1 : 0;
		const to = Math.min(state.start + CMI_PAGE_LENGTH, state.total);
		const sum = [...picked.values()].reduce((s, d) => s + flt(d.outstanding), 0);

		$w.html(`
			<div style="max-height:48vh;overflow:auto">
			<table class="table table-bordered" style="font-size:12.5px;margin-bottom:0">
				<thead><tr>
					<th style="width:34px;text-align:center"><input type="checkbox" class="cmi-item-all"></th>
					<th>Type</th><th>Document</th><th>Owner</th><th>Tanggal</th>
					<th style="text-align:right">Total</th><th style="text-align:right">Sisa</th>
				</tr></thead>
				<tbody>${body || `<tr><td colspan="7" class="text-muted text-center" style="padding:14px">${
					state.loading ? __("Memuat…") : __("Tidak ada dokumen outstanding.")}</td></tr>`}</tbody>
			</table></div>
			<div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;gap:10px">
				<div class="text-muted small">${__("Menampilkan {0}-{1} dari {2}", [from, to, state.total])}</div>
				<div>
					<button class="btn btn-xs btn-default cmi-refresh" ${state.loading ? "disabled" : ""}>${__("Refresh")}</button>
					<button class="btn btn-xs btn-default cmi-prev" ${state.start <= 0 ? "disabled" : ""}>${__("Sebelumnya")}</button>
					<button class="btn btn-xs btn-default cmi-next" ${to >= state.total ? "disabled" : ""}>${__("Berikutnya")}</button>
				</div>
			</div>
			<div style="text-align:right;margin-top:6px;font-weight:600">
				${__("Terpilih")}: ${picked.size} — Rp <span>${cmi_money(sum)}</span></div>`);
	};

	// refresh=1 membuang cache 2 menit di server (dipakai tombol Refresh) — untuk kasus
	// dokumen baru divalidasi/dibuat saat dialog sedang terbuka.
	const load = (refresh) => {
		state.loading = true;
		render();
		frappe.call({
			method: "erpnext_custom.overrides.payment_entry.get_payment_items",
			args: {
				party_type: frm.doc.party_type,
				party: frm.doc.party,
				company: frm.doc.company,
				payment_type: frm.doc.payment_type,
				search: state.search,
				// Yang sudah ada di tabel tidak boleh muncul lagi. Dikirim ke server supaya
				// hitungan total & paging-nya benar (kalau disaring di client, halaman jadi bolong).
				exclude: (frm.doc.custom_transactions || []).map((d) => d.transaction),
				start: state.start,
				page_length: CMI_PAGE_LENGTH,
				refresh: refresh ? 1 : 0,
			},
			callback(r) {
				const res = r.message || {};
				state.loading = false;
				state.rows = res.rows || [];
				state.total = res.total || 0;
				state.start = res.start || 0;
				render();
			},
			error() { state.loading = false; render(); },
		});
	};

	$w.on("change", ".cmi-item-chk", function () {
		const name = $(this).data("name");
		const row = state.rows.find((d) => d.transaction === name);
		if (this.checked && row) picked.set(name, row);
		else picked.delete(name);
		render();
	});
	$w.on("change", ".cmi-item-all", function () {
		const on = this.checked;
		state.rows.forEach((d) => (on ? picked.set(d.transaction, d) : picked.delete(d.transaction)));
		render();
	});
	$w.on("click", ".cmi-prev", () => { state.start = Math.max(0, state.start - CMI_PAGE_LENGTH); load(); });
	$w.on("click", ".cmi-next", () => { state.start += CMI_PAGE_LENGTH; load(); });
	$w.on("click", ".cmi-refresh", () => load(true));

	// Ketik -> tunggu 300ms baru cari (jangan satu request per huruf).
	let timer = null;
	dlg.fields_dict.search.$input.on("input", function () {
		const val = this.value;
		clearTimeout(timer);
		timer = setTimeout(() => {
			state.search = val;
			state.start = 0;
			load();
		}, 300);
	});

	dlg.show();
	load();
}

// Masukkan baris tercentang ke tabel Items. Return true kalau ada yang ditambahkan
// (pemanggil yang memutuskan menutup dialog atau lanjut).
function cmi_items_add(frm, picked) {
	if (!picked.size) {
		frappe.msgprint(__("Belum ada dokumen dipilih."));
		return false;
	}

	picked.forEach((d) => {
		const row = frm.add_child("custom_transactions");
		row.reference_doctype = d.reference_doctype;
		row.doc_label = d.doc_label || d.reference_doctype;
		row.transaction = d.transaction;
		row.journal_entry = d.journal_entry || null;
		row.owner_name = d.owner_name || "";
		row.date = d.date;
		row.grand_total = d.grand_total;
		row.outstanding = d.outstanding;
		row.allocated = d.outstanding;
	});
	frm.refresh_field("custom_transactions");
	cmi_sync_paid(frm);

	frappe.show_alert({
		message: __("{0} dokumen ditambahkan. Klik Save untuk membuat References.", [picked.size]),
		indicator: "green",
	});
	return true;
}

// ============================================================================
// Mode CMI: "Expense / Income" (custom_direct) & Mode of Payment "Settlement".
// - Default (tanpa centang, mode of payment lain): perilaku native — party -> bank.
// - Expense/Income: party & tabel Items disembunyikan; isi Pay To + tabel item manual
//   (note/account/amount) -> total otomatis jadi paid_amount.
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
	// Field pihak + tabel Items: sembunyikan saat mode direct.
	["party_type", "party", "party_balance", "references",
		"custom_transactions", "custom_get_transactions"].forEach((f) => {
		if (frm.fields_dict[f]) frm.toggle_display(f, !direct);
	});
	// Sisi akun party (Pay: paid_to, Receive: paid_from) ikut hilang saat direct.
	frm.toggle_display(receive ? "paid_from" : "paid_to", !direct);
	// Sisi bank (Pay: paid_from, Receive: paid_to) hilang saat settlement.
	frm.toggle_display(receive ? "paid_to" : "paid_from", !settle);
	// Akun TIDAK dipilih manual: sisi party ikut party, sisi bank ikut Company Bank Account
	// (atau Settlement Account). Jadi keduanya read-only, sekadar penampil hasil.
	frm.set_df_property("paid_from", "read_only", 1);
	frm.set_df_property("paid_to", "read_only", 1);
	// Baris hanya boleh masuk lewat Add Items (Document & Type read-only -> baris manual
	// tidak ada gunanya). Yang bisa diedit user cuma kolom Dibayar.
	const grid = frm.fields_dict.custom_transactions && frm.fields_dict.custom_transactions.grid;
	if (grid) grid.cannot_add_rows = true;
}

// Tombol "Get Outstanding Invoices" & "Get Outstanding Orders" (bawaan, section Reference)
// dibuat SEJAJAR. Lewat CSS, bukan Column Break: Meta.sort_fields sengaja menggeser custom
// break ke ujung section, jadi Section Break penutupnya selalu mendarat SESUDAH tabel
// References dan tabel itu ikut terjebak di kolom sempit.
// Kelas (bukan style inline) supaya depends_on tetap bisa menyembunyikannya: toggle_display
// mengembalikan display ke "" -> aturan kelas berlaku lagi.
function cmi_pe_inline_buttons() {
	if (document.getElementById("cmi-pe-style")) return;
	const s = document.createElement("style");
	s.id = "cmi-pe-style";
	s.textContent = `
	[data-fieldname="get_outstanding_invoices"], [data-fieldname="get_outstanding_orders"] {
		display: inline-block; vertical-align: top; margin-right: 8px; }`;
	document.head.appendChild(s);
}

// branch_office read-only & selalu = branch user. Server mengisinya lagi di before_insert
// (crm_cakra set_branch_from_user); ini supaya field tak terlihat kosong di form baru.
function cmi_pe_set_branch(frm) {
	if (frm.doc.branch_office || !frm.is_new()) return;
	frappe.call({ method: "crm_cakra.api.permissions.get_my_branch", callback(r) {
		if (r.message && !frm.doc.branch_office) frm.set_value("branch_office", r.message);
	} });
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
		// Bank Account = rekening company; menyempit ke bank terpilih.
		frm.set_query("bank_account", () => {
			const f = { is_company_account: 1 };
			if (frm.doc.company) f.company = frm.doc.company;
			if (frm.doc.custom_bank) f.bank = frm.doc.custom_bank;
			return { filters: f };
		});
		cmi_pe_set_branch(frm);
		cmi_pe_default_bank(frm);
	},
	refresh(frm) {
		cmi_pe_inline_buttons();
		cmi_pe_toggle(frm);
		cmi_pe_set_branch(frm);
		cmi_pe_show_currency(frm);
		// Dokumen baru: pilih Bank default (guard di dalam fungsi — hanya saat masih
		// kosong). Ditaruh di refresh juga karena onload kadang jalan sebelum default
		// form lain terpasang.
		cmi_pe_default_bank(frm);
	},
	payment_type: cmi_pe_toggle,
	custom_direct(frm) {
		if (frm.doc.custom_direct) {
			frm.set_value("party_type", "");
			frm.set_value("party", "");
			frm.clear_table("references");
			frm.clear_table("custom_transactions");
			frm.refresh_field("references");
			frm.refresh_field("custom_transactions");
			cmi_pe_sync_direct_total(frm);
		}
		cmi_pe_toggle(frm);
	},
	mode_of_payment: cmi_pe_toggle,
	party: cmi_pe_toggle,
	bank_account: cmi_pe_toggle,
});

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

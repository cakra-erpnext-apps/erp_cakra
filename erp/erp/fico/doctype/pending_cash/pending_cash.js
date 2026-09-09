// Pending Cash (kasbon) — form script. Dialog Validate/Pay ada di
// erp/public/js/pending_cash_actions.js (dipakai bareng list view).

// Validated -> isi dokumen dikunci. Bank Account read-only di form (diisi dari dialog Pay).
// Server memaksa aturan yang sama; ini supaya kelihatan di form, bukan gantinya.
function pc_is_locked(frm) {
	return !!frm.doc.validated && !frm.doc.void;
}

function pc_toggle_lock(frm) {
	const locked = pc_is_locked(frm);
	frm.meta.fields.forEach((df) => {
		if (frappe.model.no_value_type.includes(df.fieldtype)) return;
		frm.set_df_property(df.fieldname, "read_only", locked || df.read_only ? 1 : 0);
	});
}

function pc_state_ui(frm) {
	// Section Status disembunyikan, jadi status & jurnalnya ditampilkan di header.
	if (frm.doc.void) frm.page.set_indicator(__("Void"), "gray");
	else if (frm.doc.paid) frm.page.set_indicator(__("Paid"), "green");
	else if (frm.doc.validated) frm.page.set_indicator(__("Validated"), "blue");
	else if (!frm.is_new()) frm.page.set_indicator(__("Draft"), "orange");

	if (frm.is_new()) return;

	// Tombolnya mengikuti status: tiap pasangan aksi (Validate/Invalidate, Pay/Unpaid,
	// Void/Unvoid) tampil satu arah saja, sesuai yang masuk akal dari status sekarang.
	const act = (kind) => pc_run_toggle(kind, [frm.doc], () => frm.reload_doc());
	const run = (action) => pc_run_action(action, [frm.doc], () => frm.reload_doc());

	if (frm.doc.void) {
		frm.add_custom_button(__("Unvoid"), () => act("void"));
	} else {
		// Paid berdiri di atas Validated — selama masih Paid, Invalidate ditolak server,
		// jadi tombolnya pun tidak ditawarkan (Unpaid dulu).
		if (!frm.doc.paid) {
			frm.add_custom_button(frm.doc.validated ? __("Invalidate") : __("Validate"), () => act("validate"));
		}
		// Pay ditawarkan sejak Draft: membayar dokumen yang belum divalidasi otomatis
		// memvalidasinya (lihat bulk_pay), jadi tombolnya tidak perlu menunggu Validate.
		frm.add_custom_button(frm.doc.paid ? __("Unpaid") : __("Pay"), () => act("pay"));
		// Void hanya untuk kasbon yang uangnya belum bergerak — yang sudah Paid lewat
		// Unpaid atau Refund (server menolaknya juga, ini supaya tidak ditawarkan).
		if (!frm.doc.paid) frm.add_custom_button(__("Void"), () => act("void"));
		// Refund bisa berkali-kali (kembalian dicicil) dan tiap kali membuat DOKUMEN
		// sendiri bernomor, jadi tombolnya berdiri sendiri — pembatalannya dilakukan
		// dengan Void di dokumen refund-nya, bukan di sini.
		//
		// Ditawarkan hanya kalau MASIH ADA sisanya: kasbon yang sudah habis (dipakai di
		// Payment Entry atau sudah direfund penuh) ditolak server, jadi tombolnya cuma
		// jadi jebakan. Sisanya ditanyakan ke server — rumusnya satu, bukan ditebak dari
		// refunded_amount yang tidak tahu soal pemakaian di Payment Entry.
		if (frm.doc.paid) {
			frappe
				.call({
					method: "erp.fico.doctype.pending_cash_refund.pending_cash_refund.row_info",
					args: { pending_cash: frm.doc.name },
				})
				.then((r) => {
					if (flt(r.message && r.message.available) > 0) {
						frm.add_custom_button(__("Refund"), () => run("refund"));
					}
				});
		}
	}

	if (frm.doc.journal_entry) {
		frm.add_custom_button(__("Journal Entry"), () =>
			frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
		);
	}
}

function pc_company_currency(frm) {
	return frappe.get_doc(":Company", frm.doc.company)?.default_currency;
}

function pc_is_company_currency(frm) {
	const cc = pc_company_currency(frm);
	return !cc || !frm.doc.currency || frm.doc.currency === cc;
}

// Kurs terkunci 1 saat mata uangnya sama dengan company — biar tak ada yang mengetik
// angka lain di sana (server juga memaksanya, ini cuma supaya jelas di form).
function pc_toggle_rate(frm) {
	const same = pc_is_company_currency(frm);
	frm.set_df_property("exchange_rate", "read_only", same || pc_is_locked(frm) ? 1 : 0);
	if (same && flt(frm.doc.exchange_rate) !== 1) frm.set_value("exchange_rate", 1);
}

// Kolom section Frappe selalu dibagi rata (12/n), tak ada span per field. Total & Bank
// Account diminta selebar 2 kolom, jadi dilebarkan langsung di wrapper-nya — ruang di
// kanannya memang kosong (kolom Branch cuma berisi satu field).
// ponytail: melebar menimpa kolom sebelah; ganti tata letak kalau kolom 4 nanti diisi.
function pc_wide_fields(frm) {
	["pay_to", "receive_from", "total", "bank_account", "paid_notes"].forEach((fn) => frm.get_field(fn)?.$wrapper.css("width", "205%"));
}

// ---- tabel Refund di section Refund ---------------------------------------
// Refund adalah dokumen sendiri (Pending Cash Refund), jadi tidak ada grid bawaan yang
// bisa dipakai. Datanya diambil apa adanya lewat frappe.db.get_list — pencarian & urutan
// dikerjakan di BROWSER: satu kasbon paling banyak berisi puluhan refund, memanggil server
// tiap ketikan cuma menambah kerja tanpa menambah kecepatan.
// Tingginya dipatok 10 baris; sisanya digulir, kepala tabel ikut menempel saat digulir.
const PC_REFUND_COLS = [
	{ key: "name", label: __("No RF"), sortable: true },
	{ key: "refund_date", label: __("Refund Date"), sortable: true },
	{ key: "amount", label: __("Refund Paid"), sortable: true, right: true },
	{ key: "remark", label: __("Notes") },
];

function pc_refund_sort(frm) {
	return (frm.__refund_sort = frm.__refund_sort || { key: "name", desc: false });
}

function pc_refund_rows(frm) {
	const term = (frm.__refund_search || "").toLowerCase();
	const sort = pc_refund_sort(frm);
	const rows = (frm.__refunds || []).filter((r) =>
		!term ||
		[r.name, r.refund_date, String(r.amount), r.remark]
			.some((v) => (v || "").toString().toLowerCase().includes(term))
	);
	return rows.sort((a, b) => {
		const [x, y] = [a[sort.key], b[sort.key]];
		const cmp = sort.key === "amount" ? flt(x) - flt(y) : String(x || "").localeCompare(String(y || ""));
		return sort.desc ? -cmp : cmp;
	});
}

function pc_refund_table(frm) {
	const field = frm.get_field("refund_table");
	if (!field) return;
	const rows = pc_refund_rows(frm);
	const sort = pc_refund_sort(frm);
	const money = (v) => frappe.format(v, { fieldtype: "Currency", options: "currency" }, {}, frm.doc);
	const head = PC_REFUND_COLS.map(
		(c) =>
			`<th data-key="${c.key}" style="position:sticky;top:0;background:var(--fg-color);cursor:${
				c.sortable ? "pointer" : "default"
			};text-align:${c.right ? "right" : "left"}">${c.label}${
				c.sortable && sort.key === c.key ? (sort.desc ? " &darr;" : " &uarr;") : ""
			}</th>`
	).join("");

	const body = rows.length
		? rows
				.map(
					(r) => `<tr style="${r.void ? "opacity:.5;text-decoration:line-through" : ""}">
					<td><a href="/app/pending-cash-refund/${encodeURIComponent(r.name)}">${frappe.utils.escape_html(r.name)}</a>
						${r.void ? ` <span class="text-muted">(${__("Void")})</span>` : ""}</td>
					<td>${frappe.format(r.refund_date, { fieldtype: "Date" })}</td>
					<td style="text-align:right">${money(r.amount)}</td>
					<td>${frappe.utils.escape_html(r.remark || "")}</td>
				</tr>`
				)
				.join("")
		: `<tr><td colspan="4" class="text-muted">${__("Belum ada refund.")}</td></tr>`;

	// Total = refund AKTIF saja; yang void uangnya tidak jadi kembali. Angkanya diambil dari
	// rollup dokumen (refunded_amount), bukan dijumlah ulang dari baris yang sedang tersaring —
	// kalau tidak, mengetik di kotak cari akan mengubah "Total Refund".
	field.$wrapper.html(`
		<div class="form-group">
			<input type="text" class="form-control input-sm pc-refund-search"
				placeholder="${__("Cari nomor, tanggal, nominal, catatan...")}" value="${frappe.utils.escape_html(
					frm.__refund_search || ""
				)}">
		</div>
		<div style="max-height:320px;overflow:auto;border:1px solid var(--border-color);border-radius:var(--border-radius)">
			<table class="table table-sm" style="margin:0"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
		</div>
		<div class="text-right" style="margin-top:6px">
			<b>${__("Total Refund")}:</b> ${money(frm.doc.refunded_amount)}
		</div>`);

	field.$wrapper.find("th[data-key]").on("click", (e) => {
		const key = e.currentTarget.dataset.key;
		if (!PC_REFUND_COLS.find((c) => c.key === key)?.sortable) return;
		frm.__refund_sort = { key, desc: sort.key === key ? !sort.desc : false };
		pc_refund_table(frm);
	});
	// Fokus & posisi kursor dipulihkan: tabelnya digambar ulang tiap ketikan.
	const input = field.$wrapper.find(".pc-refund-search");
	input.on("input", (e) => {
		frm.__refund_search = e.target.value;
		pc_refund_table(frm);
		const box = frm.get_field("refund_table").$wrapper.find(".pc-refund-search");
		box.focus().val(frm.__refund_search);
	});
}

function pc_load_refunds(frm) {
	if (frm.is_new()) return;
	// Lewat server: refund sekarang menunjuk kasbon lewat CHILD TABLE alokasinya
	// (satu refund bisa memotong beberapa kasbon), dan itu join yang tidak bisa
	// dilakukan frappe.db.get_list dari browser.
	frappe
		.call({
			method: "erp.fico.doctype.pending_cash.pending_cash.refund_rows",
			args: { pending_cash: frm.doc.name },
		})
		.then((r) => {
			frm.__refunds = (r.message || []).map((x) => ({ ...x, name: x.parent }));
			// Section Refund cuma muncul kalau kasbon ini MEMANG pernah direfund. Dibuka
			// dari sini, bukan lewat depends_on: yang menentukan adalah ada/tidaknya
			// dokumen refund (yang void ikut — itu jejak), bukan angka di dokumen ini.
			frm.toggle_display("sb_refund", frm.__refunds.length > 0);
			pc_refund_table(frm);
		});
}

frappe.ui.form.on("Pending Cash", {
	setup(frm) {
		// Sumber dana dipilih dari master Bank Account (daftar rekening perusahaan),
		// bukan dari Chart of Accounts. Akun GL-nya menyusul dari Bank Account.account.
		frm.set_query("bank_account", () => ({
			filters: {
				company: frm.doc.company,
				is_company_account: 1,
				disabled: 0,
			},
		}));
		frm.set_query("pending_cash_type", () => ({ filters: { enabled: 1 } }));
		// Cost Center: milik company dokumen & bukan group node.
		frm.set_query("cost_center", () => ({
			filters: frm.doc.company ? { company: frm.doc.company, is_group: 0 } : { is_group: 0 },
		}));

		// Number (Dynamic Link) memakai query kustom supaya bisa dicari lewat NOMOR maupun
		// NAMA customer/vendor, dan dropdown-nya membaca keduanya:
		//   SH/00001/CMI/26 - PT ENERGI UNGGUL
		// (link query bawaan hanya mencari & menampilkan nama dokumen.)
		frm.set_query("number", () => ({
			query: "erp.fico.doctype.pending_cash.pending_cash.connection_query",
			// Party ikut dikirim: uang muka atas Purchase Order hanya boleh menunjuk PO
			// milik supplier yang dibayar, dan arah Masuk hanya boleh menunjuk Sales Order
			// milik customer yang menyetor (server juga menjaganya saat Save).
			filters: {
				modul: frm.doc.modul,
				pay_to: frm.doc.pay_to,
				receive_from: frm.doc.receive_from,
			},
		}));
	},

	onload(frm) {
		// Company hidden tapi reqd: server mengisinya di autoname, TAPI cek mandatory di
		// browser jalan lebih dulu — tanpa ini Save langsung ditolak "Missing Fields".
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		if (frm.is_new() && !frm.doc.currency) {
			frm.set_value("currency", frappe.defaults.get_default("currency"));
		}
		// Default Cost Center company — reqd, dan cek mandatory browser jalan sebelum
		// server sempat mengisi default-nya (kasus yang sama dengan company di atas).
		if (frm.is_new() && !frm.doc.cost_center && frm.doc.company) {
			frappe.db.get_value("Company", frm.doc.company, "cost_center").then((r) => {
				if (r.message?.cost_center && !frm.doc.cost_center) {
					frm.set_value("cost_center", r.message.cost_center);
				}
			});
		}
	},

	refresh(frm) {
		// Urutan penting: lock dulu (menyentuh semua field), baru kunci kurs — kalau
		// dibalik, pc_toggle_lock membuka lagi exchange_rate pada dokumen non-locked.
		pc_toggle_lock(frm);
		pc_toggle_rate(frm);
		pc_state_ui(frm);
		pc_wide_fields(frm);
		pc_load_refunds(frm);
	},

	company: pc_toggle_rate,

	currency(frm) {
		pc_toggle_rate(frm);
		if (!frm.doc.currency || pc_is_company_currency(frm)) return;
		// Kurs dari master Currency Exchange ERPNext (bukan angka karangan) —
		// user tetap boleh menimpanya.
		frappe.call({
			method: "erpnext.setup.utils.get_exchange_rate",
			args: {
				from_currency: frm.doc.currency,
				to_currency: pc_company_currency(frm),
				transaction_date: frm.doc.date,
			},
			callback(r) { if (r.message) frm.set_value("exchange_rate", r.message); },
		});
	},

	modul(frm) {
		// Ganti modul -> nomor lama tak lagi berlaku.
		frm.set_value("number", null);
		frm.set_value("connection_party", null);
	},

	number(frm) {
		if (!frm.doc.modul || !frm.doc.number) {
			frm.set_value("connection_party", null);
			return;
		}
		frappe.call({
			method: "erp.fico.doctype.pending_cash.pending_cash.get_connection_party",
			args: { modul: frm.doc.modul, number: frm.doc.number },
			callback(r) { frm.set_value("connection_party", r.message || null); },
		});
	},
});

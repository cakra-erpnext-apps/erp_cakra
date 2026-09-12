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
	else if (frm.doc.settled) frm.page.set_indicator(__("Completed"), "purple");
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

// Net Amount Paid = Amount Paid + Admin Charge + Materai — yang benar-benar keluar dari
// bank. Server menghitung ulang saat simpan; ini supaya angkanya sudah terlihat benar
// sebelum disimpan.
function pc_sync_net(frm) {
	frm.set_value(
		"net_amount_paid",
		flt(frm.doc.total) + flt(frm.doc.admin_fee) + flt(frm.doc.stamp_duty)
	);
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

// Kolom section Frappe selalu dibagi rata (12/n) dan menumpuk isinya ke bawah — tidak ada
// span per field maupun dua field sebaris di dalam satu kolom. Kolom kanan ini butuh
// keduanya, jadi bentuknya diatur di sini: form kolomnya dilebarkan ke 2 kolom lalu
// dijadikan flex-wrap, isinya sebaris penuh, kecuali Materai & Admin Charge yang setengah.
// Ruang yang dipakai melebar memang kosong (kolom keempat tidak berisi field).
// ponytail: melebar menimpa kolom sebelah; ganti tata letak kalau kolom 4 nanti diisi.
function pc_wide_column(frm) {
	if (!document.getElementById("pc-wide-style")) {
		const el = document.createElement("style");
		el.id = "pc-wide-style";
		el.textContent = `
		/* Kolom keempat (spacer) berdiri SESUDAH kolom ini di DOM, jadi tanpa z-index
		   div kosongnya menutupi separuh kanan isi yang melebar — field di situ jadi
		   sulit/tidak bisa diklik. */
		.pc-wide-col { position: relative; z-index: 1; }
		.pc-wide-col > form { width: 205%; display: flex; flex-wrap: wrap; align-items: flex-start; }
		.pc-wide-col > form > .frappe-control { flex: 0 0 100%; }
		.pc-wide-col > form > .frappe-control[data-fieldname="stamp_duty"],
		.pc-wide-col > form > .frappe-control[data-fieldname="admin_fee"] { flex: 0 0 50%; }
		.pc-wide-col > form > .frappe-control[data-fieldname="stamp_duty"] { padding-right: 15px; }`;
		document.head.appendChild(el);
	}
	frm.get_field("pay_to")?.$wrapper.closest(".form-column").addClass("pc-wide-col");
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
		pc_wide_column(frm);
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

	total: pc_sync_net,
	admin_fee: pc_sync_net,
	stamp_duty: pc_sync_net,

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

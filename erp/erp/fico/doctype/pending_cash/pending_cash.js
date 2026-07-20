// Pending Cash (kasbon) — form script. Dialog Validate/Pay ada di
// erp/public/js/pending_cash_actions.js (dipakai bareng list view).

// Validated -> isi dokumen dikunci, KECUALI Bank Account (masih boleh direvisi).
// Paid -> semuanya terkunci, jurnalnya sudah memakai rekening itu.
// Server memaksa aturan yang sama; ini supaya kelihatan di form, bukan gantinya.
function pc_is_locked(frm) {
	return !!frm.doc.validated && !frm.doc.void;
}

function pc_toggle_lock(frm) {
	const locked = pc_is_locked(frm);
	frm.meta.fields.forEach((df) => {
		if (frappe.model.no_value_type.includes(df.fieldtype)) return;
		const editable = df.fieldname === "bank_account" && !frm.doc.paid;
		frm.set_df_property(df.fieldname, "read_only", locked && !editable ? 1 : df.read_only ? 1 : 0);
	});
}

function pc_state_ui(frm) {
	// Section Status disembunyikan, jadi status & jurnalnya ditampilkan di header.
	if (frm.doc.void) frm.page.set_indicator(__("Void"), "gray");
	else if (frm.doc.paid) frm.page.set_indicator(__("Paid"), "green");
	else if (frm.doc.validated) frm.page.set_indicator(__("Validated"), "blue");
	else if (!frm.is_new()) frm.page.set_indicator(__("Draft"), "orange");

	if (frm.is_new() || frm.doc.void) return;

	if (!frm.doc.validated) {
		frm.add_custom_button(__("Validate"), () => pc_confirm_validate([frm.doc.name], () => frm.reload_doc()));
	} else if (!frm.doc.paid) {
		frm.add_custom_button(__("Pay"), () => {
			if (!frm.doc.bank_account) {
				frappe.msgprint({
					title: __("Bank Account Kosong"),
					indicator: "red",
					message: __("Isi <b>Bank Account</b> dulu (dan simpan) sebelum membayar Pending Cash ini."),
				});
				return;
			}
			pc_prompt_pay([frm.doc.name], () => frm.reload_doc());
		});
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
		frm.set_query("pending_cash_type", () => ({ filters: { disabled: 0 } }));
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
			filters: { modul: frm.doc.modul },
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

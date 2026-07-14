// Pending Cash (kasbon) — form script.
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
	frm.set_df_property("exchange_rate", "read_only", same ? 1 : 0);
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
	},

	refresh: pc_toggle_rate,
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

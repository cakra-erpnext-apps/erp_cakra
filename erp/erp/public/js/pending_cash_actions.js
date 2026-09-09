// Aksi status Pending Cash — dipakai form (pending_cash.js) MAUPUN Actions di list
// (pending_cash_list.js), jadi ditaruh di app_include_js: doctype JS hanya dimuat di
// halaman form, sedangkan list view butuh dialog & pesan yang sama persis.
//
// Aksinya BOLAK-BALIK berpasangan (Validate/Invalidate, Pay/Unpaid, Void/Unvoid): user
// memilih SATU menu per pasangan, arahnya ditentukan dari status tiap dokumen. Satu
// pilihan bisa memuat dokumen dengan status campur (sebagian Paid, sebagian belum) —
// itu sengaja tidak ditolak, tapi dikelompokkan dan diperlihatkan apa adanya di dialog,
// supaya user melihat persis dokumen mana yang akan diapakan sebelum menekan tombol.


// ---- Kolom "{nomor} +N" di list view -------------------------------------------------
// Dipakai kolom Source No / Payment (list Pending Cash) dan PC (list Pending Cash Refund):
// satu sel bisa memuat beberapa nomor dokumen (dipisah ", "). Yang DITAMPILKAN cuma nomor
// pertama + "+N" sisanya supaya kolomnya tidak melebar mengikuti baris terpanjang; daftar
// lengkapnya ada di tooltip. Klik = buka modulnya dengan filter `name in [...]` sehingga
// SEMUA nomor di baris itu tampil sekaligus — dengan `=` hanya nomor pertama yang terlihat.
window.pc_doc_links = function (value, doctype) {
	const names = String(value == null ? "" : value)
		.split(",")
		.map((x) => x.trim())
		.filter(Boolean);
	if (!names.length) return "<span></span>";
	const filter = encodeURIComponent(JSON.stringify(["in", names]));
	const href = `/app/${frappe.router.slug(doctype)}?name=${filter}`;
	const esc = frappe.utils.escape_html;
	// "+N" DIPISAH jadi elemennya sendiri: sel list view memotong isinya dengan ellipsis
	// dari UJUNG, jadi kalau disambung ke teks nomor justru "+N"-nya yang hilang.
	const more = names.length > 1 ? `<span class="erp-pc-more"> +${names.length - 1}</span>` : "";
	return `<a href="${href}" title="${esc(names.join(", "))}" class="erp-pc-docs"><span class="erp-pc-first">${esc(names[0])}</span>${more}</a>`;
};

window.pc_link_style = function () {
	if (document.getElementById("erp-pc-style")) return;
	const s = document.createElement("style");
	s.id = "erp-pc-style";
	s.textContent = `
	a.erp-pc-docs { display: flex; align-items: baseline; min-width: 0; }
	a.erp-pc-docs .erp-pc-first { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
	a.erp-pc-docs .erp-pc-more { flex: 0 0 auto; white-space: pre; color: var(--text-muted); }`;
	document.head.appendChild(s);
};

window.PC_ACTIONS = {
	validate: {
		verb: () => __("Validate"),
		method: "bulk_validate",
		note: () => __("Setelah Validate, isi dokumen terkunci. <b>Bank Account</b> diisi saat Pay."),
	},
	invalidate: {
		verb: () => __("Invalidate"),
		method: "bulk_invalidate",
		note: () => __("Dokumen kembali ke <b>Draft</b> dan isinya bisa direvisi lagi."),
	},
	pay: {
		verb: () => __("Pay"),
		method: "bulk_pay",
		pay_fields: true,
		note: () => __("Dokumen yang masih <b>Draft</b> ikut di-Validate di langkah ini."),
	},
	unpaid: {
		verb: () => __("Unpaid"),
		method: "bulk_unpaid",
		note: () =>
			__("<b>Journal Entry</b>-nya dihapus dan dokumen kembali ke <b>Validated</b>.") +
			" " +
			__("Untuk merevisi isinya, lanjutkan dengan <b>Invalidate</b>."),
	},
	void: {
		verb: () => __("Void"),
		method: "bulk_void",
		note: () => __("Hanya untuk kasbon yang belum Paid. Yang sudah Paid: <b>Unpaid</b> dulu, atau <b>Refund</b>."),
	},
	refund: {
		verb: () => __("Refund"),
		method: "bulk_refund",
		refund_fields: true,
		note: () =>
			__("Dibuat dokumen <b>Pending Cash Refund</b> bernomor sendiri (RF-...-01, -02, ...) dengan jurnal baru bertanggal refund, kebalikan jurnal Paid.") +
			" " +
			__("Jurnal Paid-nya tidak disentuh, jadi aman walau bulan pembayarannya sudah tutup periode.") +
			" " +
			__("Salah refund? <b>Void</b> dokumen refund-nya, lalu buat lagi."),
	},
	unvoid: {
		verb: () => __("Unvoid"),
		method: "bulk_unvoid",
		note: () => __("Dokumen yang statusnya Paid akan mendapat <b>Journal Entry baru</b>."),
	},
};

// Status dokumen -> aksi yang berlaku untuk tiap pasangan menu.
const PC_TOGGLE = {
	validate: (d) => (d.validated ? "invalidate" : "validate"),
	pay: (d) => (d.paid ? "unpaid" : "pay"),
	void: (d) => (d.void ? "unvoid" : "void"),
};

// Laporkan hasilnya apa adanya — yang gagal disebut satu per satu, jangan cuma bilang
// "berhasil" padahal ada dokumen yang tidak jadi diproses.
window.pc_report = function (res) {
	if (!res) return;
	if (res.done?.length) {
		frappe.show_alert({ message: __("{0} Pending Cash diproses", [res.done.length]), indicator: "green" });
	}
	if (res.failed?.length) {
		frappe.msgprint({
			title: __("Tidak Diproses"),
			indicator: "red",
			message: res.failed.map((f) => `<b>${f.name}</b>: ${f.error}`).join("<br>"),
		});
	}
};

// Refund TIDAK ikut pola bolak-balik: satu dokumen boleh direfund berkali-kali (kembalian
// dicicil), jadi arahnya tidak bisa disimpulkan dari status. Menunya dipilih user langsung.
window.pc_run_action = function (action, docs, done) {
	if (!(docs || []).length) {
		frappe.msgprint(__("Pilih dulu Pending Cash yang mau diproses."));
		return;
	}
	pc_confirm_actions({ [action]: docs.map((d) => d.name) }, done, docs.length === 1 ? docs[0] : null);
};

// docs = dokumen terpilih (butuh name + validated/paid/void). Form mengirim [frm.doc],
// list mengirim baris tercentang (field statusnya ikut lewat add_fields).
window.pc_run_toggle = function (kind, docs, done) {
	const groups = {};
	(docs || []).forEach((d) => {
		const action = PC_TOGGLE[kind](d);
		(groups[action] = groups[action] || []).push(d.name);
	});
	if (!Object.keys(groups).length) {
		frappe.msgprint(__("Pilih dulu Pending Cash yang mau diproses."));
		return;
	}
	// Dokumen tunggal (dari form) ikut dibawa: Bank Account & company-nya jadi default dan
	// filter di dialog Pay. Bulk dari list = banyak dokumen, banknya dipilih sekali untuk semua.
	pc_confirm_actions(groups, done, docs.length === 1 ? docs[0] : null);
};

// Dialog konfirmasi: tiap kelompok aksi menyebut dokumennya satu per satu. Nama dokumen
// tetap di-escape — nomor memang aman, tapi ini disuntikkan sebagai HTML.
function pc_confirm_actions(groups, done, single) {
	const actions = Object.keys(groups);
	const needs_pay_fields = actions.some((a) => PC_ACTIONS[a].pay_fields);
	const needs_refund_fields = actions.some((a) => PC_ACTIONS[a].refund_fields);

	const body = actions
		.map((action) => {
			const a = PC_ACTIONS[action];
			const items = groups[action]
				.map((name) => `<li>${frappe.utils.escape_html(name)}</li>`)
				.join("");
			return `
				<p>${__("Apakah Anda yakin ingin {0} Pending Cash di bawah ini?", [`<b>${a.verb()}</b>`])}</p>
				<ul>${items}</ul>
				${a.note ? `<p class="text-muted small">${a.note()}</p>` : ""}`;
		})
		.join("<hr>");

	const fields = [{ fieldtype: "HTML", options: body }];
	if (needs_pay_fields) {
		fields.push(
			{ fieldtype: "Section Break" },
			{
				fieldtype: "Link",
				fieldname: "bank_account",
				label: __("Bank Account"),
				options: "Bank Account",
				reqd: 1,
				default: single?.bank_account,
				get_query: () => ({
					filters: Object.assign(
						{ is_company_account: 1, disabled: 0 },
						single?.company ? { company: single.company } : {}
					),
				}),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "paid_date",
				label: __("Paid Date"),
				reqd: 1,
				// Jurnal pembayaran tidak boleh mendahului dokumennya, jadi default-nya
				// hari ini ATAU tanggal dokumen bila dokumennya bertanggal maju.
				// Server memaksa aturan yang sama untuk bulk dari list.
				default:
					single?.date > frappe.datetime.get_today()
						? single.date
						: frappe.datetime.get_today(),
			},
			{ fieldtype: "Section Break" },
			{ fieldtype: "Small Text", fieldname: "paid_notes", label: __("Paid Notes") }
		);
	}

	if (needs_refund_fields) {
		fields.push(
			{ fieldtype: "Section Break" },
			{
				fieldtype: "Date",
				fieldname: "refund_date",
				label: __("Refund Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			// Nominal hanya ditawarkan untuk satu dokumen: sisa tiap dokumen berbeda, jadi
			// satu angka untuk banyak dokumen pasti salah di sebagian. Bulk = refund penuh.
			...(single
				? [{
						fieldtype: "Currency",
						fieldname: "amount",
						label: __("Amount"),
						description: __("Kosongkan untuk mengembalikan seluruh sisa."),
				  }]
				: []),
			{ fieldtype: "Data", fieldname: "remark", label: __("Remark") }
		);
	}

	const d = new frappe.ui.Dialog({
		title: actions.length === 1 ? PC_ACTIONS[actions[0]].verb() : __("Pending Cash"),
		fields,
		primary_action_label: actions.length === 1 ? PC_ACTIONS[actions[0]].verb() : __("Proses"),
		primary_action(values) {
			d.hide();
			pc_run_actions(groups, values || {}, done);
		},
	});
	d.show();
}

// Tiap kelompok dijalankan BERURUTAN (bukan paralel): dua aksi pada dokumen yang sama-sama
// menyentuh jurnal bisa saling mendahului kalau ditembakkan bersamaan. Hasilnya digabung
// supaya user melihat satu laporan, bukan dua alert terpisah.
function pc_run_actions(groups, values, done) {
	const merged = { done: [], failed: [] };
	let chain = Promise.resolve();

	Object.keys(groups).forEach((action) => {
		const a = PC_ACTIONS[action];
		const args = { names: groups[action] };
		if (a.pay_fields) {
			args.bank_account = values.bank_account;
			args.paid_date = values.paid_date;
			args.paid_notes = values.paid_notes;
		}
		if (a.refund_fields) {
			args.refund_date = values.refund_date;
			args.amount = values.amount;
			args.remark = values.remark;
		}
		chain = chain.then(() =>
			frappe
				.call({
					method: `erp.fico.doctype.pending_cash.pending_cash.${a.method}`,
					args,
					freeze: true,
					freeze_message: __("{0}...", [a.verb()]),
				})
				.then((r) => {
					const m = r.message || {};
					merged.done.push(...(m.done || []));
					merged.failed.push(...(m.failed || []));
				})
		);
	});

	chain.then(() => {
		pc_report(merged);
		done?.();
	});
}

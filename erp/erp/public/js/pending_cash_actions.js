// Aksi status Pending Cash — dipakai form (pending_cash.js) MAUPUN Actions di list
// (pending_cash_list.js), jadi ditaruh di app_include_js: doctype JS hanya dimuat di
// halaman form, sedangkan list view butuh dialog & pesan yang sama persis.
//
// Aksinya BOLAK-BALIK berpasangan (Validate/Invalidate, Pay/Unpaid, Void/Unvoid): user
// memilih SATU menu per pasangan, arahnya ditentukan dari status tiap dokumen. Satu
// pilihan bisa memuat dokumen dengan status campur (sebagian Paid, sebagian belum) —
// itu sengaja tidak ditolak, tapi dikelompokkan dan diperlihatkan apa adanya di dialog,
// supaya user melihat persis dokumen mana yang akan diapakan sebelum menekan tombol.

window.PC_ACTIONS = {
	validate: {
		verb: () => __("Validate"),
		method: "bulk_validate",
		note: () => __("Setelah Validate, isi dokumen terkunci kecuali <b>Bank Account</b>."),
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
		note: () => __("Jurnalnya (bila sudah Paid) ikut di-cancel sebagai jejak, tidak dihapus."),
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
	pc_confirm_actions(groups, done);
};

// Dialog konfirmasi: tiap kelompok aksi menyebut dokumennya satu per satu. Nama dokumen
// tetap di-escape — nomor memang aman, tapi ini disuntikkan sebagai HTML.
function pc_confirm_actions(groups, done) {
	const actions = Object.keys(groups);
	const needs_pay_fields = actions.some((a) => PC_ACTIONS[a].pay_fields);

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
				fieldtype: "Date",
				fieldname: "paid_date",
				label: __("Paid Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{ fieldtype: "Small Text", fieldname: "paid_notes", label: __("Notes") }
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
			args.paid_date = values.paid_date;
			args.paid_notes = values.paid_notes;
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

// Aksi Validate / Pay Pending Cash — dipakai form (pending_cash.js) MAUPUN Actions di
// list (pending_cash_list.js), jadi ditaruh di app_include_js: doctype JS hanya dimuat di
// halaman form, sedangkan list view butuh dialog & pesan yang sama persis. Keduanya bulk:
// form cuma mengirim satu nama.

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

window.pc_confirm_validate = function (names, done) {
	frappe.confirm(
		names.length > 1
			? __("Apakah Anda yakin ingin validate {0} Pending Cash ini?", [names.length])
			: __("Apakah Anda yakin ingin validate Pending Cash ini?"),
		() => {
			frappe.call({
				method: "erp.fico.doctype.pending_cash.pending_cash.bulk_validate",
				args: { names },
				freeze: true,
				freeze_message: __("Validating..."),
				callback: (r) => {
					pc_report(r.message);
					done?.();
				},
			});
		}
	);
};

// Undo Paid = koreksi salah input: jurnalnya di-cancel LALU DIHAPUS dan dokumen kembali
// Draft (bisa direvisi penuh). Server menolak bila Pending Cash-nya sudah ditarik ke
// Payment Entry — lepas dulu barisnya di sana.
window.pc_confirm_undo_paid = function (names, done) {
	frappe.confirm(
		(names.length > 1
			? __("Batalkan Paid {0} Pending Cash ini?", [names.length])
			: __("Batalkan Paid Pending Cash ini?")) +
			"<br>" +
			__("Journal Entry-nya akan <b>dihapus</b> dan dokumen kembali ke <b>Draft</b> untuk direvisi."),
		() => {
			frappe.call({
				method: "erp.fico.doctype.pending_cash.pending_cash.bulk_undo_paid",
				args: { names },
				freeze: true,
				freeze_message: __("Undoing..."),
				callback: (r) => {
					pc_report(r.message);
					done?.();
				},
			});
		}
	);
};

window.pc_prompt_pay = function (names, done) {
	const d = new frappe.ui.Dialog({
		title: __("Pay Pending Cash"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${
					names.length > 1
						? __("Apakah Anda yakin ingin membayar {0} Pending Cash ini?", [names.length])
						: __("Apakah Anda yakin ingin membayar Pending Cash ini?")
				}</p>`,
			},
			{
				fieldtype: "Date",
				fieldname: "paid_date",
				label: __("Paid Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{ fieldtype: "Small Text", fieldname: "paid_notes", label: __("Notes") },
		],
		primary_action_label: __("Pay"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "erp.fico.doctype.pending_cash.pending_cash.bulk_pay",
				args: { names, paid_date: values.paid_date, paid_notes: values.paid_notes },
				freeze: true,
				freeze_message: __("Paying..."),
				callback: (r) => {
					pc_report(r.message);
					done?.();
				},
			});
		},
	});
	d.show();
};

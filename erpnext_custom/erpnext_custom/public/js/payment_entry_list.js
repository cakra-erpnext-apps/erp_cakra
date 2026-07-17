// List View Payment Entry:
// - Menu Actions: "Validate / Invalidate" & "Void / Unvoid". Aksinya dijalankan mesin yang
//   sama dengan doctype lain (erpnext_custom.workflow), jadi role & guard-nya identik:
//   submit/cancel bawaan tetap ditutup guard_submit/guard_cancel.
// - Badge status memakai istilah CMI (Draft / Validated / Void), bukan Submitted/Cancelled.
//
// Payment Entry memakai DOCSTATUS (bukan checkbox seperti Expense Note):
//   0 Draft  --Validate-->  1 Validated  --Void-->  2 Void
//        <--Invalidate--            <--Unvoid-- (kembali ke Draft, bukan ke Validated)
//
// Kolom & urutannya BUKAN di sini — diatur install._setup_payment_entry_list_columns
// (in_list_view + List View Settings), supaya sama untuk semua user.
//
// ERPNext sudah punya payment_entry_list.js sendiri (membatasi pilihan Party Type di filter
// sidebar) dan file itu dimuat LEBIH DULU (frappe/desk/form/meta.py: _add_code lalu
// add_code_via_hook). Jadi settings-nya di-EXTEND, bukan ditimpa — menimpa berarti diam-diam
// membuang perilaku bawaannya.
(function () {
	const prev = frappe.listview_settings["Payment Entry"] || {};

	frappe.listview_settings["Payment Entry"] = Object.assign({}, prev, {
		add_fields: (prev.add_fields || []).concat(["docstatus"]),

		get_indicator(doc) {
			const d = cint(doc.docstatus);
			if (d === 2) return [__("Void"), "red", "docstatus,=,2"];
			if (d === 1) return [__("Validated"), "green", "docstatus,=,1"];
			return [__("Draft"), "gray", "docstatus,=,0"];
		},

		onload(listview) {
			if (prev.onload) prev.onload(listview);
			cmi_pe_list_actions(listview);
		},
		refresh(listview) {
			if (prev.refresh) prev.refresh(listview);
			cmi_pe_list_actions(listview);
		},
	});
})();

// DIGUARD: saat `onload`, `listview.page` bisa BELUM siap — kalau langsung dipanggil,
// throw -> list view gagal init -> daftar tampak KOSONG. Karena itu dicek dulu, dan
// dipasang sekali saja (dipanggil ulang dari refresh saat page sudah ada).
function cmi_pe_list_actions(listview) {
	if (!listview || !listview.page || typeof listview.page.add_actions_menu_item !== "function") return;
	if (listview._cmi_pe_actions) return;
	listview._cmi_pe_actions = true;
	try {
		// Dua tombol TOGGLE: aksinya ditentukan dari state tiap dokumen terpilih.
		listview.page.add_actions_menu_item(__("Validate / Invalidate"), () => cmi_pe_list_toggle(listview, "validate"), true);
		listview.page.add_actions_menu_item(__("Void / Unvoid"), () => cmi_pe_list_toggle(listview, "void"), true);
	} catch (e) {
		console.error("payment entry bulk actions", e);
	}
}

// kind='validate' -> Draft di-Validate, yang tervalidasi di-Invalidate (yang Void dilewati).
// kind='void'     -> yang tervalidasi di-Void, yang Void di-Unvoid (Draft dilewati).
// Modal menampilkan SEMUA dokumen terpilih dikelompokkan per aksi — termasuk yang dilewati —
// supaya user tahu persis apa yang akan terjadi ke masing-masing saat seleksinya campuran.
function cmi_pe_list_toggle(listview, kind) {
	const docs = listview.get_checked_items();
	if (!docs.length) {
		frappe.msgprint(__("Centang Payment Entry dulu."));
		return;
	}

	const isVoid = kind === "void";
	const onAction = isVoid ? "void" : "validate";
	const offAction = isVoid ? "unvoid" : "invalidate";
	const onLabel = isVoid ? __("Void") : __("Validate");
	const offLabel = isVoid ? __("Unvoid") : __("Invalidate");

	// Void: 1 -> Void, 2 -> Unvoid, 0 (draft) dilewati.
	// Validate: 0 -> Validate, 1 -> Invalidate, 2 (void) dilewati.
	const onFrom = isVoid ? 1 : 0;
	const offFrom = isVoid ? 2 : 1;
	const toOn = docs.filter((d) => cint(d.docstatus) === onFrom).map((d) => d.name);
	const toOff = docs.filter((d) => cint(d.docstatus) === offFrom).map((d) => d.name);
	const skipped = docs.filter((d) => ![onFrom, offFrom].includes(cint(d.docstatus))).map((d) => d.name);

	if (!toOn.length && !toOff.length) {
		frappe.msgprint(isVoid
			? __("Payment Entry terpilih masih Draft — Validate dulu sebelum bisa di-Void.")
			: __("Payment Entry terpilih sudah Void — pakai Unvoid dulu."));
		return;
	}

	const esc = frappe.utils.escape_html;
	const listHtml = (title, arr, color) =>
		arr.length
			? `<div style="margin-bottom:8px"><b style="color:var(--${color})">${title} (${arr.length})</b><br>` +
			  arr.map((n) => esc(n)).join("<br>") + "</div>"
			: "";

	// Kalimat konfirmasi & label tombol mengikuti aksinya. Seleksi seragam -> pakai kata
	// aksinya; campuran -> sebut keduanya, tombolnya generik.
	let actionWord, btnLabel;
	if (toOn.length && !toOff.length) {
		actionWord = onLabel;
		btnLabel = onLabel;
	} else if (toOff.length && !toOn.length) {
		actionWord = offLabel;
		btnLabel = offLabel;
	} else {
		actionWord = `${onLabel} / ${offLabel}`;
		btnLabel = __("Proses");
	}

	let body = `<p style="margin-bottom:10px">${
		__("Apakah anda yakin ingin {0} Payment Entry di bawah ini?", [actionWord])}</p>`;
	body += listHtml(onLabel, toOn, isVoid ? "red-600" : "green-600");
	body += listHtml(offLabel, toOff, isVoid ? "blue-600" : "orange-600");
	body += listHtml(__("Dilewati"), skipped, "gray-600");

	const needReason = isVoid && toOn.length;
	const d = new frappe.ui.Dialog({
		title: isVoid ? __("Void / Unvoid") : __("Validate / Invalidate"),
		fields: [
			{ fieldtype: "HTML", fieldname: "info", options: body },
			...(needReason
				? [{ fieldtype: "Small Text", fieldname: "reason", label: __("Alasan Void"), reqd: 1 }]
				: []),
		],
		primary_action_label: btnLabel,
		primary_action(v) {
			d.hide();
			cmi_pe_list_run(listview, [
				{ names: toOn, action: onAction, reason: v.reason },
				{ names: toOff, action: offAction },
			]);
		},
	});
	d.show();
}

// Jalankan grup aksi (validate+invalidate atau void+unvoid) BERURUTAN — bukan paralel:
// keduanya menyentuh GL/Payment Ledger dokumen yang sama-sama sedang diproses.
// Lalu tampilkan ringkasan gabungan berhasil/gagal.
function cmi_pe_list_run(listview, groups) {
	groups = groups.filter((g) => g.names && g.names.length);
	const okAll = [], failAll = [];
	const step = (i) => {
		if (i >= groups.length) {
			let msg = __("Berhasil: {0}", [okAll.length]);
			if (failAll.length) {
				msg += "<br><br>" + __("Gagal: {0}", [failAll.length]) + "<br>" +
					failAll.map((f) => `<b>${frappe.utils.escape_html(f.name)}</b>: ${
						frappe.utils.escape_html(f.error)}`).join("<br>");
			}
			frappe.msgprint({
				title: __("Selesai"), message: msg,
				indicator: failAll.length ? "orange" : "green",
			});
			listview.clear_checked_items && listview.clear_checked_items();
			listview.refresh();
			return;
		}
		const g = groups[i];
		frappe.call({
			method: "erpnext_custom.workflow.bulk_set_state",
			args: { doctype: "Payment Entry", names: g.names, action: g.action, reason: g.reason },
			freeze: true,
			freeze_message: __("Memproses…"),
			callback(r) {
				const res = (r && r.message) || {};
				(res.ok || []).forEach((n) => okAll.push(n));
				(res.failed || []).forEach((f) => failAll.push(f));
				step(i + 1);
			},
			error() { step(i + 1); },
		});
	};
	step(0);
}

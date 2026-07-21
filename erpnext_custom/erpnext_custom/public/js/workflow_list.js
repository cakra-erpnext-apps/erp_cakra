// Aksi bulk Validate / Invalidate / Void / Unvoid di LIST VIEW, dipakai bersama oleh
// doctype ber-docstatus (Sales Invoice, Payment Entry, ...). Server-nya satu:
// erpnext_custom.workflow.bulk_set_state -> role & guard identik dengan aksi satuan.
//
//   0 Draft  --Validate-->  1 Validated  --Void-->  2 Void
//        <--Invalidate--            <--Unvoid-- (kembali ke Draft, bukan ke Validated)
//
// Dimuat lewat app_include_js supaya tersedia di semua halaman list.
(function () {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

	// DIGUARD: saat `onload`, `listview.page` bisa BELUM siap — kalau langsung dipakai,
	// throw -> list view gagal init -> daftar tampak KOSONG. Karena itu dicek dulu, dan
	// dipasang sekali saja (dipanggil ulang dari refresh saat page sudah ada).
	window.cmi_workflow_list_actions = function (listview, doctype, label) {
		if (!listview || !listview.page || typeof listview.page.add_actions_menu_item !== "function") return;
		if (listview._cmi_wf_actions) return;
		listview._cmi_wf_actions = true;
		try {
			// Dua tombol TOGGLE: aksinya ditentukan dari state tiap dokumen terpilih.
			listview.page.add_actions_menu_item(__("Validate / Invalidate"), () => toggle(listview, doctype, label, "validate"), true);
			listview.page.add_actions_menu_item(__("Void / Unvoid"), () => toggle(listview, doctype, label, "void"), true);
		} catch (e) {
			console.error("cmi workflow bulk actions", e);
		}
	};

	// Badge status memakai istilah CMI (Draft / Validated / Void), bukan Submitted/Cancelled.
	window.cmi_workflow_indicator = function (doc) {
		const d = cint(doc.docstatus);
		if (d === 2) return [__("Void"), "red", "docstatus,=,2"];
		if (d === 1) return [__("Validated"), "green", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	};

	// kind='validate' -> Draft di-Validate, yang tervalidasi di-Invalidate (yang Void dilewati).
	// kind='void'     -> yang tervalidasi di-Void, yang Void di-Unvoid (Draft dilewati).
	// Modal menampilkan SEMUA dokumen terpilih dikelompokkan per aksi — termasuk yang dilewati —
	// supaya user tahu persis apa yang akan terjadi ke masing-masing saat seleksinya campuran.
	function toggle(listview, doctype, label, kind) {
		const docs = listview.get_checked_items();
		if (!docs.length) {
			frappe.msgprint(__("Centang {0} dulu.", [label]));
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
				? __("{0} terpilih masih Draft — Validate dulu sebelum bisa di-Void.", [label])
				: __("{0} terpilih sudah Void — pakai Unvoid dulu.", [label]));
			return;
		}

		const listHtml = (title, arr, color) =>
			arr.length
				? `<div style="margin-bottom:8px"><b style="color:var(--${color})">${title} (${arr.length})</b><br>` +
				  arr.map(esc).join("<br>") + "</div>"
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
			__("Apakah anda yakin ingin {0} {1} di bawah ini?", [actionWord, label])}</p>`;
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
				run(listview, doctype, [
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
	function run(listview, doctype, groups) {
		groups = groups.filter((g) => g.names && g.names.length);
		const okAll = [], failAll = [];
		const step = (i) => {
			if (i >= groups.length) {
				let msg = __("Berhasil: {0}", [okAll.length]);
				if (failAll.length) {
					msg += "<br><br>" + __("Gagal: {0}", [failAll.length]) + "<br>" +
						failAll.map((f) => `<b>${esc(f.name)}</b>: ${esc(f.error)}`).join("<br>");
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
				args: { doctype: doctype, names: g.names, action: g.action, reason: g.reason },
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
})();

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
	// opts.void === false  -> menu Void/Unvoid tidak dipasang (doctype tanpa field `void`).
	// opts.checkbox === true -> state dibaca dari kolom `validated`/`void`, bukan `docstatus`
	//   (doctype custom seperti Expense Note / CRM Estimation; lihat CHECKBOX di workflow.py).
	//   Kolomnya HARUS ada di add_fields listview, kalau tidak get_checked_items() tak memuatnya.
	window.cmi_workflow_list_actions = function (listview, doctype, label, opts) {
		if (!listview || !listview.page || typeof listview.page.add_actions_menu_item !== "function") return;
		if (listview._cmi_wf_actions) return;
		listview._cmi_wf_actions = true;
		try {
			// Dua tombol TOGGLE: aksinya ditentukan dari state tiap dokumen terpilih.
			const checkbox = !!(opts && opts.checkbox);
			listview.page.add_actions_menu_item(__("Validate / Invalidate"), () => toggle(listview, doctype, label, "validate", checkbox), true);
			if (!opts || opts.void !== false)
				listview.page.add_actions_menu_item(__("Void / Unvoid"), () => toggle(listview, doctype, label, "void", checkbox), true);
		} catch (e) {
			console.error("cmi workflow bulk actions", e);
		}
	};

	// Enable / Disable massal untuk doctype yang punya field `disabled` (CRM Estimation,
	// dan doctype lain yang butuh nanti). Dialog & ringkasannya memakai jalur yang sama
	// dengan Validate/Void di atas, hanya endpoint-nya yang beda.
	window.cmi_disable_list_actions = function (listview, doctype, label) {
		if (!listview || !listview.page || typeof listview.page.add_actions_menu_item !== "function") return;
		if (listview._cmi_disable_actions) return;
		listview._cmi_disable_actions = true;
		try {
			listview.page.add_actions_menu_item(__("Disable / Enable"), () => toggle_disabled(listview, doctype, label), true);
		} catch (e) {
			console.error("cmi disable bulk action", e);
		}
	};

	// Yang masih aktif -> Disable, yang sudah disabled -> Enable. Tidak ada yang dilewati:
	// tiap dokumen selalu jatuh ke salah satu sisi.
	function toggle_disabled(listview, doctype, label) {
		const docs = listview.get_checked_items();
		if (!docs.length) {
			frappe.msgprint(__("Centang {0} dulu.", [label]));
			return;
		}
		const toOn = docs.filter((d) => !cint(d.disabled)).map((d) => d.name); // -> Disable
		const toOff = docs.filter((d) => cint(d.disabled)).map((d) => d.name); // -> Enable
		confirm_and_run(listview, {
			title: __("Disable / Enable"),
			label: label,
			onLabel: __("Disable"),
			offLabel: __("Enable"),
			onColor: "orange-600",
			offColor: "green-600",
			toOn: toOn,
			toOff: toOff,
			skipped: [],
			groups: () => [
				{ names: toOn, method: DISABLE_METHOD, args: { doctype: doctype, disabled: 1 } },
				{ names: toOff, method: DISABLE_METHOD, args: { doctype: doctype, disabled: 0 } },
			],
		});
	}

	const DISABLE_METHOD = "erpnext_custom.workflow.bulk_set_disabled";

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
	function toggle(listview, doctype, label, kind, checkbox) {
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

		let toOn, toOff, skipped;
		if (checkbox) {
			// Doctype checkbox: tiap dokumen selalu jatuh ke salah satu sisi, tak ada yang
			// dilewati. Server tetap yang memutuskan sah/tidaknya (mis. Validate saat void).
			const field = isVoid ? "void" : "validated";
			toOn = docs.filter((d) => !cint(d[field])).map((d) => d.name);
			toOff = docs.filter((d) => cint(d[field])).map((d) => d.name);
			skipped = [];
		} else {
			// Void: 1 -> Void, 2 -> Unvoid, 0 (draft) dilewati.
			// Validate: 0 -> Validate, 1 -> Invalidate, 2 (void) dilewati.
			const onFrom = isVoid ? 1 : 0;
			const offFrom = isVoid ? 2 : 1;
			toOn = docs.filter((d) => cint(d.docstatus) === onFrom).map((d) => d.name);
			toOff = docs.filter((d) => cint(d.docstatus) === offFrom).map((d) => d.name);
			skipped = docs.filter((d) => ![onFrom, offFrom].includes(cint(d.docstatus))).map((d) => d.name);
		}

		if (!toOn.length && !toOff.length) {
			frappe.msgprint(isVoid
				? __("{0} terpilih masih Draft — Validate dulu sebelum bisa di-Void.", [label])
				: __("{0} terpilih sudah Void — pakai Unvoid dulu.", [label]));
			return;
		}

		confirm_and_run(listview, {
			title: isVoid ? __("Void / Unvoid") : __("Validate / Invalidate"),
			label: label,
			onLabel: onLabel,
			offLabel: offLabel,
			onColor: isVoid ? "red-600" : "green-600",
			offColor: isVoid ? "blue-600" : "orange-600",
			toOn: toOn,
			toOff: toOff,
			skipped: skipped,
			// Void butuh alasan (hanya untuk yang akan di-Void).
			needReason: isVoid && !!toOn.length,
			groups: (reason) => [
				{ names: toOn, args: { doctype: doctype, action: onAction, reason: reason } },
				{ names: toOff, args: { doctype: doctype, action: offAction } },
			],
		});
	}

	// Dialog konfirmasi bersama: menampilkan SEMUA dokumen terpilih dikelompokkan per aksi —
	// termasuk yang dilewati — supaya user tahu persis apa yang akan terjadi ke masing-masing
	// saat seleksinya campuran.
	function confirm_and_run(listview, spec) {
		const listHtml = (title, arr, color) =>
			arr.length
				? `<div style="margin-bottom:8px"><b style="color:var(--${color})">${title} (${arr.length})</b><br>` +
				  arr.map(esc).join("<br>") + "</div>"
				: "";

		// Kalimat konfirmasi & label tombol mengikuti aksinya. Seleksi seragam -> pakai kata
		// aksinya; campuran -> sebut keduanya, tombolnya generik.
		let actionWord, btnLabel;
		if (spec.toOn.length && !spec.toOff.length) {
			actionWord = btnLabel = spec.onLabel;
		} else if (spec.toOff.length && !spec.toOn.length) {
			actionWord = btnLabel = spec.offLabel;
		} else {
			actionWord = `${spec.onLabel} / ${spec.offLabel}`;
			btnLabel = __("Proses");
		}

		let body = `<p style="margin-bottom:10px">${
			__("Apakah anda yakin ingin {0} {1} di bawah ini?", [actionWord, spec.label])}</p>`;
		body += listHtml(spec.onLabel, spec.toOn, spec.onColor);
		body += listHtml(spec.offLabel, spec.toOff, spec.offColor);
		body += listHtml(__("Dilewati"), spec.skipped || [], "gray-600");

		const d = new frappe.ui.Dialog({
			title: spec.title,
			fields: [
				{ fieldtype: "HTML", fieldname: "info", options: body },
				...(spec.needReason
					? [{ fieldtype: "Small Text", fieldname: "reason", label: __("Alasan Void"), reqd: 1 }]
					: []),
			],
			primary_action_label: btnLabel,
			primary_action(v) {
				d.hide();
				run(listview, spec.groups(v.reason));
			},
		});
		d.show();
	}

	// Jalankan grup aksi (validate+invalidate atau void+unvoid) BERURUTAN — bukan paralel:
	// keduanya menyentuh GL/Payment Ledger dokumen yang sama-sama sedang diproses.
	// Lalu tampilkan ringkasan gabungan berhasil/gagal.
	function run(listview, groups) {
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
				method: g.method || "erpnext_custom.workflow.bulk_set_state",
				args: Object.assign({ names: g.names }, g.args),
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

	// --- buang aksi bulk Submit & Cancel BAWAAN di doctype ber-alur CMI ------------
	// Keduanya memanggil doc.submit()/doc.cancel() langsung, yang PASTI ditolak
	// guard_submit/guard_cancel di server. Penggantinya sudah ada di menu yang sama:
	// "Validate / Invalidate" dan "Void / Unvoid".
	//
	// Menu Actions dirakit di setup_page(), yang jalan SEBELUM listview.onload — jadi
	// menyaringnya harus di prototype, bukan dari list js masing-masing doctype.
	const CMI_DOCTYPES = [
		"Sales Invoice", "Purchase Invoice", "Purchase Order",
		"Purchase Receipt", "Payment Entry",
	];
	const LV = frappe.views && frappe.views.ListView;
	if (LV && !LV.prototype._cmi_bulk_patched) {
		LV.prototype._cmi_bulk_patched = true;
		const original = LV.prototype.get_actions_menu_items;
		LV.prototype.get_actions_menu_items = function () {
			const items = original.call(this);
			if (!CMI_DOCTYPES.includes(this.doctype)) return items;
			// label dibandingkan lewat __() bersignature sama seperti core, supaya
			// tetap cocok saat kata "Submit" diterjemahkan jadi "Validate".
			const drop = [
				__("Submit", null, "Button in list view actions menu"),
				__("Cancel", null, "Button in list view actions menu"),
			];
			return items.filter((i) => !(i.standard && drop.includes(i.label)));
		};
	}
})();

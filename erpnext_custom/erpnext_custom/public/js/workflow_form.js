// Menu Validate / Invalidate / Void / Unvoid di FORM, dipakai bersama oleh
// Purchase Order, Purchase Receipt, dan Purchase Invoice. Endpoint-nya sama dengan
// aksi bulk di list view (erpnext_custom.workflow), jadi role dan guard-nya identik.
//
//   0 Draft  --Validate-->  1 Validated  --Void-->  2 Void
//        <--Invalidate--            <--Unvoid-- (kembali ke Draft, bukan ke Validated)
//
// Izin di sini HANYA menyembunyikan menu. Keputusan sebenarnya tetap di server
// (_assert_action), jadi menu yang bocor pun tidak bisa menembus.
//
// Dimuat lewat app_include_js supaya tersedia sebelum doctype_js masing-masing jalan.
(function () {
	// Izinnya PER DOCTYPE, dibaca dari Role Permission Manager (workflow.PERM_GATED):
	//   kolom Submit (tampil "Validate") -> Validate & Invalidate
	//   kolom Cancel                     -> Void & Unvoid
	const PTYPE = { validate: "submit", invalidate: "submit", void: "cancel", unvoid: "cancel" };
	const can = (frm, action) => !!(frm.perm && frm.perm[0] && frm.perm[0][PTYPE[action]]);

	function run(frm, method, label, args) {
		return frappe.call({
			method: "erpnext_custom.workflow." + method,
			args: Object.assign({ doctype: frm.doctype, name: frm.doc.name }, args || {}),
			freeze: true,
			freeze_message: label + "…",
			callback(r) {
				if (r.message && r.message.ok) frm.reload_doc();
			},
		});
	}

	function voidPrompt(frm, label) {
		frappe.prompt(
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Alasan Void"), reqd: 1 },
			(v) => run(frm, "void_doc", __("Void"), { reason: v.reason }),
			__("Void {0} {1}", [label, frm.doc.name]),
			__("Void")
		);
	}

	// standard=false -> item tampil di ATAS menu "..." dengan divider di bawahnya.
	window.cmi_workflow_menu = function (frm, label) {
		if (frm.is_new()) return;
		const state = cint(frm.doc.docstatus);

		// Tombol secondary "Cancel" bawaan dibuang. Ia MUNCUL berdasarkan izin Cancel,
		// tetapi klik-nya sudah lama dibelokkan ke Invalidate, yang izinnya justru ada
		// di kolom Validate — jadi kombinasi Cancel=1 & Validate=0 memunculkan tombol
		// yang pasti ditolak server. Menu di bawah sudah menyediakan Invalidate dan Void
		// masing-masing dengan gerbang yang benar.
		// Aman dipanggil di sini: refresh_header() (yang memasang tombolnya) jalan
		// SEBELUM trigger refresh milik doctype.
		if (state === 1) frm.page.clear_secondary_action();

		if (state === 1 && can(frm, "invalidate")) {
			frm.page.add_menu_item(__("Invalidate"), () => frappe.confirm(
				__("Invalidate {0} <b>{1}</b>?<br><br>Jurnalnya <b>dihapus</b> dan dokumen kembali ke draft.",
					[label, frm.doc.name]),
				() => run(frm, "invalidate_doc", __("Invalidate"))
			), false);
		}
		if (state === 1 && can(frm, "void")) {
			frm.page.add_menu_item(__("Void"), () => voidPrompt(frm, label), false);
		}
		if (state === 2 && can(frm, "unvoid")) {
			frm.page.add_menu_item(__("Unvoid"), () => frappe.confirm(
				__("Unvoid {0} <b>{1}</b>?<br><br>Dokumen kembali ke <b>draft</b> dan perlu di-Validate lagi.",
					[label, frm.doc.name]),
				() => run(frm, "unvoid_doc", __("Unvoid"))
			), false);
		}
	};
})();

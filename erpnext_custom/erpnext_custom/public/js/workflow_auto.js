// Menu Validate / Invalidate / Void / Unvoid / Close / Open GENERIK, untuk doctype yang
// didaftarkan workflow.boot (Sales Order, Delivery Note, Stock Entry, Journal Entry,
// Shipping List, Packing List, ...). Doctype yang sudah punya file sendiri (SI, PI, PO,
// PR, PE, Expense Note, ...) tidak ikut di sini.
//
//   docstatus  : 0 Draft --Validate--> 1 Validated --Void--> 2 Void
//                (Invalidate/Unvoid kembali ke Draft; tidak ada untuk dokumen stok)
//   master_job : Open --Close--> Closed, Open --Void--> Void (tanpa Validate)
//
// Role hanya menyembunyikan menu; keputusan tetap di server (erpnext_custom.workflow).
(function () {
	const cfg = () => frappe.boot.cmi_workflow || { doctypes: {} };
	// izin per doctype (ERPNext Custom Setting > Workflow Access), lihat workflow_list.js
	const can = (frm, a) => window.cmi_wf_can(frm.doctype, a);

	function call(frm, method, label, args) {
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

	function confirm(frm, method, label, text) {
		frappe.confirm(text, () => call(frm, method, label));
	}

	function prompt(frm, method, label, reqd) {
		frappe.prompt(
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Alasan {0}", [label]), reqd: reqd ? 1 : 0 },
			(v) => call(frm, method, label, { reason: v.reason }),
			__("{0} {1}", [label, frm.doc.name]),
			label
		);
	}

	function docstatus_menu(frm, c) {
		const state = cint(frm.doc.docstatus);
		// Submit/Cancel bawaan diarahkan ke endpoint CMI (server menolak jalur bawaan).
		frm.savesubmit = () => {
			const run = () => call(frm, "validate_doc", __("Validate"));
			return frm.is_new() || frm.is_dirty() ? frm.save().then(run) : run();
		};
		frm.savecancel = () => prompt(frm, "void_doc", __("Void"), true);
		if (state === 1) frm.page.clear_secondary_action();
		if (state === 0 && !frm.is_dirty() && !can(frm, "validate")) frm.page.clear_primary_action();

		if (state === 1 && c.revert && can(frm, "invalidate")) {
			frm.page.add_menu_item(__("Invalidate"), () => confirm(frm, "invalidate_doc", __("Invalidate"),
				__("Invalidate <b>{0}</b>?<br><br>Jurnalnya dihapus dan dokumen kembali ke draft.", [frm.doc.name])), false);
		}
		if ((state === 0 || state === 1) && can(frm, "void")) {
			frm.page.add_menu_item(__("Void"), () => prompt(frm, "void_doc", __("Void"), true), false);
		}
		if (state === 2 && c.revert && can(frm, "unvoid")) {
			frm.page.add_menu_item(__("Unvoid"), () => confirm(frm, "unvoid_doc", __("Unvoid"),
				__("Unvoid <b>{0}</b>?<br><br>Dokumen kembali ke draft dan perlu di-Validate lagi.", [frm.doc.name])), false);
		}
		// Sales Order: Close/Re-open memakai tombol Status bawaan ERPNext, yang di server
		// dibelokkan ke izin Close/Open yang sama (workflow.so_update_status).
	}

	function master_job_menu(frm) {
		const d = frm.doc;
		if (cint(d.void)) frm.page.set_indicator(__("Void"), "red");
		else if (cint(d.closed)) frm.page.set_indicator(__("Closed"), "gray");
		else frm.page.set_indicator(__("Open"), "green");

		if (!cint(d.void) && !cint(d.closed) && can(frm, "close")) {
			frm.page.add_menu_item(__("Close"), () => prompt(frm, "close_doc", __("Close"), false), false);
		}
		if (cint(d.closed) && can(frm, "open")) {
			frm.page.add_menu_item(__("Open"), () => confirm(frm, "open_doc", __("Open"),
				__("Buka lagi <b>{0}</b>? Dokumen bisa ditarik transaksi berikutnya lagi.", [d.name])), false);
		}
		if (!cint(d.void) && can(frm, "void")) {
			frm.page.add_menu_item(__("Void"), () => prompt(frm, "void_doc", __("Void"), true), false);
		}
		if (cint(d.void) && can(frm, "unvoid")) {
			frm.page.add_menu_item(__("Unvoid"), () => confirm(frm, "unvoid_doc", __("Unvoid"),
				__("Unvoid <b>{0}</b>?", [d.name])), false);
		}
	}

	// frappe.boot sudah terisi sebelum app_include_js dimuat (desk.html), jadi didaftarkan
	// langsung -- menunggu app_ready bisa terlambat untuk form yang dibuka lewat URL.
	Object.entries(cfg().doctypes).forEach(([dt, c]) => {
		frappe.ui.form.on(dt, {
			refresh(frm) {
				if (frm.is_new()) return;
				if (c.mode === "master_job") master_job_menu(frm);
				else docstatus_menu(frm, c);
			},
		});
	});

	// List: aksi bulk dipasang dari refresh (prototype), karena list js tiap doctype
	// bisa menimpa listview_settings kapan saja. cmi_workflow_list_actions idempoten.
	const LV = frappe.views && frappe.views.ListView;
	if (LV && !LV.prototype._cmi_auto_patched) {
		LV.prototype._cmi_auto_patched = true;
		const original = LV.prototype.refresh;
		LV.prototype.refresh = function () {
			const out = original.apply(this, arguments);
			const c = cfg().doctypes[this.doctype];
			if (c && window.cmi_workflow_list_actions) {
				const label = __(this.doctype);
				if (c.mode === "master_job") {
					window.cmi_workflow_list_actions(this, this.doctype, label,
						{ checkbox: true, validate: false, close: true });
				} else {
					window.cmi_workflow_list_actions(this, this.doctype, label);
				}
			}
			return out;
		};
	}
})();

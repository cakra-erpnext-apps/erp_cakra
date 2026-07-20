// Halaman Print (/app/print) — pengaturan print out Sales Invoice yang persisten.
//
// Dua input sidebar khusus Sales Invoice (keduanya HIDDEN di form invoice — sengaja,
// supaya user hanya menemuinya di konteks print):
//   - "Invoice Title"  -> Sales Invoice.custom_invoice_title  (judul print out)
//   - "Watermark Paid" -> Sales Invoice.custom_watermark_paid (watermark PAID)
// Keduanya di-seed dari dokumen saat sidebar dibuat, dan disimpan balik ke dokumen saat
// tombol PRINT ditekan — jadi user lain yang membuka print melihat setelan terakhir.
//
// Checkbox watermark HANYA dirender kalau invoice sudah Customer Paid; server tidak bisa
// menyaringnya (get_print_settings statis, tak tahu dokumennya), jadi filternya di sini.
//
// Di-inject lewat hook page_js["print"] (jalan setelah script page print frappe, sebelum
// instance dibuat, jadi patch prototype selalu kepakai).
(function () {
	const PV = frappe.ui.form.PrintView;
	if (!PV || PV.prototype._cmi_title_patched) return;
	PV.prototype._cmi_title_patched = true;

	const TITLE_FIELD = 'invoice_title'; // field sidebar (meta Print Settings)
	const DOC_TITLE = 'custom_invoice_title'; // storage per-dokumen (Sales Invoice)
	const WM_FIELD = 'watermark_paid';
	const DOC_WM = 'custom_watermark_paid';
	// Sentinel: checkbox tak punya "nilai kosong", jadi print_settings.watermark_paid saja
	// tidak cukup untuk membedakan "user meng-uncheck" dari "render tanpa sidebar (PDF/
	// email)". Key tambahan ini HANYA dikirim dari sidebar; template memakainya kalau ada,
	// dan jatuh ke doc.custom_watermark_paid kalau tidak.
	const WM_SENTINEL = 'cmi_watermark';

	const is_si = (doc) => doc && doc.doctype === 'Sales Invoice';

	// Field sidebar bawaan yang DISEMBUNYIKAN — tidak ada satu pun print format di bench
	// ini yang memakainya (semua format custom Jinja, header-nya ambil Company.company_logo,
	// bukan Letter Head). Sisanya: Print Format + field custom kita.
	//   language / letterhead  -> dibuat di setup_sidebar, controlnya MASIH dipakai kode
	//                             frappe (get_letterhead, set_default_print_language) jadi
	//                             hanya di-hide via CSS, JANGAN di-remove.
	//   compact_item_print dkk -> field dinamis, cukup dilewati saat render.
	const HIDE_STATIC = ['language', 'letterhead'];
	const HIDE_DYNAMIC = ['compact_item_print', 'print_uom_after_quantity', 'print_taxes_with_zero_amount'];

	function inject_style() {
		if (document.getElementById('cmi-print-sidebar-style')) return;
		const s = document.createElement('style');
		s.id = 'cmi-print-sidebar-style';
		s.textContent = `
		${HIDE_STATIC.map((f) => `.print-preview-sidebar .frappe-control[data-fieldname="${f}"]`).join(',')}
		{ display: none !important; }
		/* Pesan info bawaan (mis. peringatan "Repeat Header and Footer") ikut hilang. */
		.print-preview-sidebar .form-message { display: none !important; }`;
		document.head.appendChild(s);
	}

	const orig_setup_sidebar = PV.prototype.setup_sidebar;
	PV.prototype.setup_sidebar = function () {
		const out = orig_setup_sidebar.apply(this, arguments);
		inject_style();
		return out;
	};

	// Replika add_settings_to_sidebar bawaan + simpan referensi kontrol per fieldname
	// + seed nilai dari dokumen + skip field yang tidak relevan.
	PV.prototype.add_settings_to_sidebar = function (settings) {
		this._cmi_dynamic_fields = {};
		const doc = this.frm && this.frm.doc;
		for (let df of settings) {
			if (HIDE_DYNAMIC.includes(df.fieldname)) continue;
			if (is_si(doc)) {
				// Watermark: hanya untuk invoice yang sudah dibayar customer.
				if (df.fieldname === WM_FIELD && !cint(doc.custom_customer_paid)) continue;
				if (df.fieldname === TITLE_FIELD) {
					df = Object.assign({}, df, { default: doc[DOC_TITLE] || 'INVOICE' });
				}
				if (df.fieldname === WM_FIELD) {
					df = Object.assign({}, df, { default: cint(doc[DOC_WM]) });
				}
			} else if (df.fieldname === WM_FIELD || df.fieldname === TITLE_FIELD) {
				// Field ini milik Sales Invoice; jangan bocor ke doctype lain.
				continue;
			}
			let field = this.add_sidebar_item(
				{
					...df,
					change: () => {
						const val = field.get_value();
						this.additional_settings[field.df.fieldname] = val;
						if (field.df.fieldname === WM_FIELD) {
							this.additional_settings[WM_SENTINEL] = cint(val) ? '1' : '0';
						}
						this.preview();
					},
				},
				true
			);
			this._cmi_dynamic_fields[df.fieldname] = field;
		}
		// Nilai seed ikut dikirim ke render (settings) supaya preview & PDF konsisten.
		if (is_si(doc)) {
			const tf = this._cmi_dynamic_fields[TITLE_FIELD];
			if (tf) this.additional_settings[TITLE_FIELD] = tf.get_value() || tf.df.default || '';
			const wf = this._cmi_dynamic_fields[WM_FIELD];
			if (wf) {
				const on = cint(wf.get_value() != null ? wf.get_value() : wf.df.default);
				this.additional_settings[WM_FIELD] = on;
				this.additional_settings[WM_SENTINEL] = on ? '1' : '0';
			}
			if (tf || wf) this.preview();
		}
	};

	// Tombol Print -> simpan setelan terbaru ke dokumen (kalau berubah), lalu print.
	const orig_printit = PV.prototype.printit;
	PV.prototype.printit = function () {
		try {
			const doc = this.frm && this.frm.doc;
			const ctl = this._cmi_dynamic_fields || {};
			if (is_si(doc)) {
				const updates = {};
				const tf = ctl[TITLE_FIELD];
				if (tf) {
					const val = (tf.get_value() || '').trim();
					if (val && val !== (doc[DOC_TITLE] || '')) updates[DOC_TITLE] = val;
				}
				const wf = ctl[WM_FIELD];
				if (wf) {
					const val = cint(wf.get_value());
					if (val !== cint(doc[DOC_WM])) updates[DOC_WM] = val;
				}
				if (Object.keys(updates).length) {
					Object.assign(doc, updates); // salinan lokal ikut baru
					frappe.db.set_value('Sales Invoice', doc.name, updates);
				}
			}
		} catch (e) {
			console.error('cmi print settings:', e); // jangan sampai menghalangi print
		}
		return orig_printit.apply(this, arguments);
	};
})();

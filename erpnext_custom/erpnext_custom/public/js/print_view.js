// Halaman Print (/app/print) — judul print out Sales Invoice yang persisten.
//
// Field sidebar "Invoice Title" di-seed dari Sales Invoice.custom_invoice_title
// (judul terakhir yang dipakai); saat tombol PRINT ditekan, isian terbaru disimpan
// kembali ke dokumen — jadi user lain yang membuka print melihat judul terakhir.
// Di-inject lewat hook page_js["print"] (jalan setelah script page print frappe,
// sebelum instance dibuat, jadi patch prototype selalu kepakai).
(function () {
	const PV = frappe.ui.form.PrintView;
	if (!PV || PV.prototype._cmi_title_patched) return;
	PV.prototype._cmi_title_patched = true;

	const TITLE_FIELD = 'invoice_title'; // field sidebar (meta Print Settings)
	const DOC_FIELD = 'custom_invoice_title'; // storage per-dokumen (Sales Invoice)

	// Replika add_settings_to_sidebar bawaan + simpan referensi kontrol per fieldname
	// + seed nilai Invoice Title dari dokumen (fallback "INVOICE").
	PV.prototype.add_settings_to_sidebar = function (settings) {
		this._cmi_dynamic_fields = {};
		const doc = this.frm && this.frm.doc;
		for (let df of settings) {
			if (df.fieldname === TITLE_FIELD && doc && doc.doctype === 'Sales Invoice') {
				df = Object.assign({}, df, { default: doc[DOC_FIELD] || 'INVOICE' });
			}
			let field = this.add_sidebar_item(
				{
					...df,
					change: () => {
						const val = field.get_value();
						this.additional_settings[field.df.fieldname] = val;
						this.preview();
					},
				},
				true
			);
			this._cmi_dynamic_fields[df.fieldname] = field;
		}
		// Nilai seed ikut dikirim ke render (settings) supaya preview & PDF konsisten.
		const tf = this._cmi_dynamic_fields[TITLE_FIELD];
		if (tf && doc && doc.doctype === 'Sales Invoice') {
			this.additional_settings[TITLE_FIELD] = tf.get_value() || tf.df.default || '';
			this.preview();
		}
	};

	// Tombol Print -> simpan judul terbaru ke dokumen (kalau berubah), lalu print.
	const orig_printit = PV.prototype.printit;
	PV.prototype.printit = function () {
		try {
			const doc = this.frm && this.frm.doc;
			const tf = this._cmi_dynamic_fields && this._cmi_dynamic_fields[TITLE_FIELD];
			if (doc && doc.doctype === 'Sales Invoice' && tf) {
				const val = (tf.get_value() || '').trim();
				if (val && val !== (doc[DOC_FIELD] || '')) {
					doc[DOC_FIELD] = val; // salinan lokal ikut baru
					frappe.db.set_value('Sales Invoice', doc.name, DOC_FIELD, val);
				}
			}
		} catch (e) {
			console.error('cmi print title:', e); // jangan sampai menghalangi print
		}
		return orig_printit.apply(this, arguments);
	};
})();

// Halaman Print (/app/print) — setelan print out Sales Invoice yang persisten.
//
// Semua setelan print Sales Invoice HIDDEN di form invoice dan hanya muncul di sidebar
// print view. Nilainya di-seed dari dokumen saat sidebar dibuat, dan disimpan balik ke
// dokumen saat tombol PRINT ditekan — jadi user lain yang membuka print melihat setelan
// terakhir. Pasangan field sidebar <-> field dokumen ada di FIELDS di bawah.
//
// Field sidebar sendiri didaftarkan server lewat CMISalesInvoice.get_print_settings
// (dipanggil PADA dokumennya, jadi watermark_paid cuma ikut kalau invoice sudah paid).
//
// Di-inject lewat hook page_js["print"] (jalan setelah script page print frappe, sebelum
// instance dibuat, jadi patch prototype selalu kepakai).
(function () {
	const PV = frappe.ui.form.PrintView;
	if (!PV || PV.prototype._cmi_title_patched) return;
	PV.prototype._cmi_title_patched = true;

	// sidebar (meta Print Settings) -> penyimpanan per-dokumen (Sales Invoice).
	// save:false = tampil & ikut ke render, tapi TIDAK pernah ditulis balik ke dokumen.
	const FIELDS = [
		{ sidebar: 'invoice_title', doc: 'custom_invoice_title', type: 'data', fallback: 'INVOICE' },
		{ sidebar: 'watermark_paid', doc: 'custom_watermark_paid', type: 'check' },
		{ sidebar: 'print_as_currency', doc: 'custom_print_as_currency', type: 'data' },
		{ sidebar: 'printed_by', doc: 'custom_printed_by', type: 'data' },
		// Kontrol akses — di sidebar cuma sebagai informasi (read_only di Print Settings).
		{ sidebar: 'branch_office', doc: 'branch_office', type: 'data', save: false },
	];
	const BY_SIDEBAR = {};
	FIELDS.forEach((f) => (BY_SIDEBAR[f.sidebar] = f));

	// Sentinel untuk watermark: Check tidak punya "nilai kosong", jadi
	// print_settings.watermark_paid saja tidak bisa membedakan "user meng-uncheck" dari
	// "render tanpa sidebar" (PDF/email). Key ini HANYA dikirim dari sidebar; template
	// memakainya kalau ada, dan jatuh ke doc.custom_watermark_paid kalau tidak.
	// Field lain tidak butuh ini karena string kosong sudah cukup jadi penanda.
	const WM_SENTINEL = 'cmi_watermark';

	const is_si = (doc) => doc && doc.doctype === 'Sales Invoice';
	const norm = (f, v) => (f.type === 'check' ? cint(v) : (v || '').toString().trim());

	// Nilai awal kontrol: nilai tersimpan di dokumen, kalau kosong baru fallback.
	// Untuk Select, fallback-nya adalah OPSI PERTAMA. Opsi Printed By disusun server dengan
	// baris Default di depan (erpnext_custom/printed_by.py), jadi ini otomatis memilih
	// Default tanpa perlu request tambahan. Wajib eksplisit: set_input("") pada <select>
	// yang tidak punya opsi kosong bikin selectedIndex = -1 -> tampil BLANK, bukan opsi
	// pertama, dan get_value() ikut mengembalikan "".
	function seed_value(f, df, doc) {
		const stored = norm(f, doc[f.doc]);
		if (stored) return stored;
		if (df.fieldtype === 'Select') {
			const first = (df.options || '').split('\n').map((o) => o.trim()).filter(Boolean)[0];
			if (first) return first;
		}
		return f.fallback || '';
	}

	// Field sidebar bawaan yang DISEMBUNYIKAN — tidak ada print format di bench ini yang
	// memakainya (semua format custom Jinja, header-nya ambil Company.company_logo, bukan
	// Letter Head). Sisanya: Print Format + field custom kita.
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
	// + seed nilai dari dokumen + skip field yang tidak dipakai.
	PV.prototype.add_settings_to_sidebar = function (settings) {
		this._cmi_dynamic_fields = {};
		const doc = this.frm && this.frm.doc;
		for (let df of settings) {
			if (HIDE_DYNAMIC.includes(df.fieldname)) continue;
			const f = BY_SIDEBAR[df.fieldname];
			if (f) {
				// Field ini milik Sales Invoice; jangan bocor ke doctype lain.
				if (!is_si(doc)) continue;
				df = Object.assign({}, df, { default: seed_value(f, df, doc) });
			}
			let field = this.add_sidebar_item(
				{
					...df,
					change: () => {
						const val = field.get_value();
						this.additional_settings[field.df.fieldname] = val;
						if (field.df.fieldname === 'watermark_paid') {
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
			let seeded = false;
			for (const f of FIELDS) {
				const ctl = this._cmi_dynamic_fields[f.sidebar];
				if (!ctl) continue;
				const val = norm(f, ctl.get_value() != null ? ctl.get_value() : ctl.df.default);
				this.additional_settings[f.sidebar] = val;
				if (f.sidebar === 'watermark_paid') {
					this.additional_settings[WM_SENTINEL] = val ? '1' : '0';
				}
				seeded = true;
			}
			if (seeded) this.preview();
		}
	};

	// Tombol Print -> simpan setelan terbaru ke dokumen (kalau berubah), lalu print.
	const orig_printit = PV.prototype.printit;
	PV.prototype.printit = function () {
		try {
			const doc = this.frm && this.frm.doc;
			const ctl = this._cmi_dynamic_fields || {};
			if (is_si(doc)) {
				for (const f of FIELDS) {
					if (f.save === false) continue;
					const c = ctl[f.sidebar];
					if (!c) continue;
					const val = norm(f, c.get_value());
					if (val === norm(f, doc[f.doc])) continue;
					if (f.fallback && !val) continue; // jangan timpa judul dengan string kosong
					doc[f.doc] = val; // salinan lokal ikut baru
					// PENTING: pakai bentuk 4 argumen (fieldname, value) — BUKAN
					// set_value(dt, name, {obj}). Helper client selalu mengirim `value`;
					// saat undefined, frappe.client.set_value masuk cabang `else` dan
					// menyusun {"<json fieldname>": "undefined"} -> doc.update() dengan
					// fieldname sampah = no-op DIAM-DIAM (save sukses, tidak ada error,
					// tidak ada yang tersimpan).
					frappe.db.set_value('Sales Invoice', doc.name, f.doc, val);
				}
			}
		} catch (e) {
			console.error('cmi print settings:', e); // jangan sampai menghalangi print
		}
		return orig_printit.apply(this, arguments);
	};
})();

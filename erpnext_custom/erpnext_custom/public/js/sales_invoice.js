// Dependensi InvoiceType -> InvoiceTypeNo (opsi menyesuaikan kategori).
const CMI_TYPE_NO = {
	Expedition: ["C/E", "C/EA", "T/E"],
	Depo: ["C/E", "C/EA", "T/E"],
	Trading: ["C/T"],
	Reimburse: ["IR"],
};

// Header wajib sebelum mengisi Items / Reimburse.
const CMI_REQUIRED = {
	custom_invoice_type: "Invoice Type",
	custom_invoice_type_no: "Invoice Type No",
	customer: "Customer",
	invoice_date: "Invoice Date",
};

function cmi_missing_header(frm) {
	return Object.keys(CMI_REQUIRED).filter((k) => !frm.doc[k]).map((k) => CMI_REQUIRED[k]);
}

function cmi_require_header(frm) {
	const missing = cmi_missing_header(frm);
	if (missing.length) {
		frappe.msgprint({
			title: __("Lengkapi header dulu"),
			message: __("Isi dulu: <b>{0}</b> sebelum mengisi Items / Reimburse.", [missing.join(", ")]),
			indicator: "orange",
		});
		return false;
	}
	return true;
}

function cmi_set_type_no_options(frm) {
	const opts = CMI_TYPE_NO[frm.doc.custom_invoice_type] || ["C/E", "C/EA", "T/E", "C/T", "IR"];
	frm.set_df_property("custom_invoice_type_no", "options", "\n" + opts.join("\n"));
	if (frm.doc.custom_invoice_type_no && !opts.includes(frm.doc.custom_invoice_type_no)) {
		frm.set_value("custom_invoice_type_no", "");
	}
}

// InvoiceType/No read-only kalau ada baris terisi (item_code / expense_note).
function cmi_lock_type(frm) {
	const hasItems = (frm.doc.items || []).some((r) => r.item_code);
	const hasReimburse = (frm.doc.custom_reimburse_items || []).some((r) => r.expense_note);
	const locked = hasItems || hasReimburse ? 1 : 0;
	frm.set_df_property("custom_invoice_type", "read_only", locked);
	frm.set_df_property("custom_invoice_type_no", "read_only", locked);
}

// Paksa Exchange Rate (conversion_rate) selalu tampil.
function cmi_show_rate(frm) {
	setTimeout(() => {
		frm.set_df_property("conversion_rate", "hidden", 0);
		frm.set_df_property("conversion_rate", "read_only", 0);
	}, 300);
}

// Set nilai tanpa men-trigger event field (hindari loop).
function cmi_set(frm, field, val) {
	if (flt(frm.doc[field]) === flt(val)) return;
	frm.doc[field] = val;
	frm.refresh_field(field);
}

// Set nilai TEXT tanpa men-trigger event (untuk field gabungan Discount/PPh/Tax).
function cmi_set_text(frm, field, val) {
	if ((frm.doc[field] || "") === (val || "")) return;
	frm.doc[field] = val || "";
	frm.refresh_field(field);
}

// Presisi desimal nominal = default sistem (System Settings > Currency Precision).
function cmi_prec() {
	const p = cint(frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency_precision);
	return p > 0 ? p : 2;
}

// Format persen ringkas: titik ribuan, koma desimal, tanpa nol buntut. 10 -> "10"; 1.5 -> "1,5".
function cmi_fmt_pct(n) {
	n = flt(n);
	const neg = n < 0;
	const parts = String(Math.abs(n)).split(".");
	const intp = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
	return (neg ? "-" : "") + intp + (parts[1] ? "," + parts[1] : "");
}

// Format nominal mengikuti number format + presisi default sistem.
function cmi_fmt_nominal(n) {
	return format_number(flt(n, cmi_prec()), null, cmi_prec());
}

// Parse field gabungan: "10%" -> {pct:10}; "10.000,001" -> {amt: dibulatkan ke presisi
// default}; "" -> {empty}. Locale: titik = ribuan, koma = desimal (selaras server).
// PENTING: pakai parseFloat, BUKAN flt(string) — flt menganggap "." sebagai pemisah
// ribuan locale sehingga "1000.00" terbaca 100000 (bug x100 saat teks terformat
// ter-parse ulang oleh event form).
function cmi_parse_input(raw) {
	const s = (raw == null ? "" : String(raw)).trim();
	if (!s) return { pct: null, amt: null, empty: true };
	const is_pct = s.indexOf("%") !== -1;
	const cleaned = s.replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(/,/g, ".");
	const num = parseFloat(cleaned) || 0;
	return is_pct ? { pct: num, amt: null } : { pct: null, amt: flt(num, cmi_prec()) };
}

// SATU field gabungan per komponen: ketik "10%" (persen) ATAU nominal. Storage
// tersembunyi percent/amount dikonsumsi compute + server + print. Tampilan nominal
// dirapikan jadi format ribuan ("50.000") setelah diketik / saat dimuat.
const CMI_SMART = [
	{ input: "custom_discount_input", pct: "custom_discount_percent", amt: "custom_discount_amount" },
	{ input: "custom_pph_input", pct: "custom_pph_percent", amt: "custom_pph_amount" },
	{ input: "custom_tax_input", pct: "custom_tax_percent", amt: "custom_tax_amount" },
];
const CMI_SMART_HELP = __('Ketik mis. "10%" atau "50000"');

// User mengetik di field gabungan -> isi percent/amount tersembunyi, hitung ulang,
// lalu rapikan tampilan (nominal -> "50.000"; persen tetap "10%").
function cmi_apply_input(frm, cfg) {
	const p = cmi_parse_input(frm.doc[cfg.input]);
	if (p.empty) {
		cmi_set(frm, cfg.pct, 0);
		cmi_set(frm, cfg.amt, 0);
	} else if (p.pct !== null) {
		cmi_set(frm, cfg.pct, p.pct);
	} else {
		cmi_set(frm, cfg.pct, 0);
		cmi_set(frm, cfg.amt, p.amt);
	}
	cmi_compute_amounts(frm);
	cmi_render_input(frm, cfg);
}

// Tampilan field gabungan dari storage: "10%" (mode persen) atau nominal terformat
// dengan desimal sesuai presisi default sistem.
function cmi_render_input(frm, cfg) {
	const p = flt(frm.doc[cfg.pct]);
	const a = flt(frm.doc[cfg.amt]);
	cmi_set_text(frm, cfg.input, p > 0 ? cmi_fmt_pct(p) + "%" : a ? cmi_fmt_nominal(a) : "");
}

// Saat dokumen dimuat: bangun teks field gabungan dari percent/amount tersimpan (idempotent).
function cmi_hydrate_inputs(frm) {
	CMI_SMART.forEach((cfg) => cmi_render_input(frm, cfg));
}

// Tampilkan hasil konversi "= Rp X" di bawah tiap field gabungan.
function cmi_update_hints(frm) {
	const cur = frm.doc.currency || "IDR";
	CMI_SMART.forEach((cfg) => {
		let hint = CMI_SMART_HELP;
		if (cfg.input === "custom_tax_input" && frm.doc.custom_ignore_tax) {
			hint = __("Tax diabaikan (Ignore Tax aktif)");
		} else if (flt(frm.doc[cfg.pct]) > 0 || flt(frm.doc[cfg.amt])) {
			hint = __("= {0}", [format_currency(flt(frm.doc[cfg.amt]), cur)]);
		}
		frm.set_df_property(cfg.input, "description", hint);
	});
}

// Hitung amounts live + auto-isi Amount dari % (mirror logika server).
// % menang kalau diisi (Amount keisi otomatis); kalau % kosong, pakai Amount manual.
function cmi_compute_amounts(frm) {
	const total = flt(frm.doc.total);
	let discount;
	if (flt(frm.doc.custom_discount_percent) > 0) {
		discount = (total * flt(frm.doc.custom_discount_percent)) / 100;
		cmi_set(frm, "custom_discount_amount", discount);
	} else {
		discount = flt(frm.doc.custom_discount_amount);
	}
	const dpp = total - discount;
	let tax;
	if (frm.doc.custom_ignore_tax) {
		tax = 0;
		cmi_set(frm, "custom_tax_amount", 0);
	} else if (flt(frm.doc.custom_tax_percent) > 0) {
		tax = (dpp * flt(frm.doc.custom_tax_percent)) / 100;
		cmi_set(frm, "custom_tax_amount", tax);
	} else {
		tax = flt(frm.doc.custom_tax_amount);
	}
	let pph;
	if (flt(frm.doc.custom_pph_percent) > 0) {
		pph = (dpp * flt(frm.doc.custom_pph_percent)) / 100;
		cmi_set(frm, "custom_pph_amount", pph);
	} else {
		pph = flt(frm.doc.custom_pph_amount);
	}
	const materai = flt(frm.doc.custom_materai);
	const adj = flt(frm.doc.custom_adjustment);
	const reimb = (frm.doc.custom_reimburse_items || []).reduce((s, r) => s + flt(r.line_amount), 0);
	cmi_set(frm, "custom_amount_total", total + reimb);
	cmi_set(frm, "custom_net_total", total - discount + tax - pph + materai + adj + reimb);
	cmi_update_hints(frm);
}

function cmi_compute_delayed(frm) {
	setTimeout(() => cmi_compute_amounts(frm), 150);
}

function cmi_reimburse_line(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "line_amount", (row.amount || 0) * (row.rate || 1));
}

// Filter item di grid Items menurut Invoice Type:
// Expedition/Depo -> Item Group "Services"; Trading -> "Products"; lainnya bebas.
const CMI_ITEM_GROUP_BY_TYPE = { Expedition: "Services", Depo: "Services", Trading: "Products" };

function cmi_setup_item_query(frm) {
	frm.set_query("item_code", "items", () => {
		const g = CMI_ITEM_GROUP_BY_TYPE[frm.doc.custom_invoice_type];
		// Tetap pakai query item standar ERPNext (sembunyikan disabled/non-sales),
		// ditambah filter group per Invoice Type.
		return {
			query: "erpnext.controllers.queries.item_query",
			filters: g ? { item_group: g } : {},
		};
	});
}

// Alamat customer di header: field custom (custom_customer_address) di kolom kanan
// samping Customer. Dropdown terfilter alamat milik customer; pilihan disinkronkan
// ke field core customer_address/address_display (dipakai print & logika ERPNext).
function cmi_setup_address_query(frm) {
	frm.set_query("custom_customer_address", () => ({
		query: "frappe.contacts.doctype.address.address.address_query",
		filters: { link_doctype: "Customer", link_name: frm.doc.customer || "" },
	}));
}

function cmi_address_changed(frm) {
	const a = frm.doc.custom_customer_address;
	frm.set_value("customer_address", a || "");
	if (!a) {
		frm.set_value("custom_address_display", "");
		return;
	}
	frappe.db
		.get_value("Address", a, ["address_line1", "address_line2", "city", "state", "pincode", "country"])
		.then((r) => {
			const d = (r && r.message) || {};
			const parts = [
				d.address_line1,
				d.address_line2,
				[d.city, d.pincode].filter(Boolean).join(" "),
				d.state,
				d.country,
			].filter(Boolean);
			frm.set_value("custom_address_display", parts.join("\n"));
		});
}

frappe.ui.form.on("Sales Invoice", {
	onload(frm) {
		cmi_set_type_no_options(frm);
		cmi_lock_type(frm);
		cmi_show_rate(frm);
		cmi_hydrate_inputs(frm);
		cmi_setup_address_query(frm);
		cmi_setup_item_query(frm);
	},
	refresh(frm) {
		cmi_set_type_no_options(frm);
		cmi_lock_type(frm);
		cmi_show_rate(frm);
		cmi_hydrate_inputs(frm);
		cmi_compute_amounts(frm);
		cmi_setup_address_query(frm);
		cmi_setup_item_query(frm);
	},
	customer(frm) {
		// Ganti customer -> alamat lama tidak berlaku lagi.
		if (frm.doc.custom_customer_address) frm.set_value("custom_customer_address", "");
	},
	custom_customer_address: cmi_address_changed,
	custom_invoice_type: cmi_set_type_no_options,
	currency(frm) { cmi_show_rate(frm); cmi_compute_amounts(frm); },
	company: cmi_show_rate,

	// Field gabungan: ketik "10%" (persen) ATAU nominal -> auto-konversi + tampilan rapi.
	custom_discount_input(frm) { cmi_apply_input(frm, CMI_SMART[0]); },
	custom_pph_input(frm) { cmi_apply_input(frm, CMI_SMART[1]); },
	custom_tax_input(frm) { cmi_apply_input(frm, CMI_SMART[2]); },
	custom_materai: cmi_compute_amounts,
	custom_ignore_tax: cmi_compute_amounts,
	custom_adjustment: cmi_compute_amounts,

	items_remove(frm) { cmi_lock_type(frm); cmi_compute_delayed(frm); },
	custom_reimburse_items_remove(frm) { cmi_lock_type(frm); cmi_compute_delayed(frm); },

	custom_get_expense_notes(frm) {
		if (!cmi_require_header(frm)) return;
		frappe.call({
			method: "erpnext_custom.overrides.sales_invoice.get_reimburse_expense_notes",
			args: { customer: frm.doc.customer, currency: frm.doc.currency },
			freeze: true,
			callback(r) {
				const rows = r.message || [];
				if (!rows.length) {
					frappe.msgprint(__("Tidak ada Expense Note reimburse yang memenuhi syarat."));
					return;
				}
				const rate = frm.doc.conversion_rate || 1;
				rows.forEach((d) => {
					const row = frm.add_child("custom_reimburse_items");
					row.expense_note = d.expense_note;
					row.document_date = d.document_date;
					row.document_no_fp = d.document_no_fp;
					row.note = d.note;
					row.currency = d.currency || frm.doc.currency;
					row.amount = d.amount;
					row.rate = rate;
					row.line_amount = (d.amount || 0) * rate;
				});
				frm.refresh_field("custom_reimburse_items");
				cmi_lock_type(frm);
				cmi_compute_amounts(frm);
				frm.dirty();
				frappe.show_alert({ message: __("{0} Expense Note ditambahkan.", [rows.length]), indicator: "green" });
			},
		});
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		if (!locals[cdt][cdn].item_code) return;
		if (!cmi_require_header(frm)) {
			frappe.model.set_value(cdt, cdn, "item_code", "");
			return;
		}
		cmi_lock_type(frm);
	},
	qty: cmi_compute_delayed,
	rate: cmi_compute_delayed,
	amount: cmi_compute_delayed,
});

frappe.ui.form.on("Reimburse Item", {
	expense_note(frm, cdt, cdn) {
		if (!locals[cdt][cdn].expense_note) return;
		if (!cmi_require_header(frm)) {
			frappe.model.set_value(cdt, cdn, "expense_note", "");
			return;
		}
		cmi_lock_type(frm);
	},
	rate(frm, cdt, cdn) { cmi_reimburse_line(cdt, cdn); cmi_compute_delayed(frm); },
	amount(frm, cdt, cdn) { cmi_reimburse_line(cdt, cdn); cmi_compute_delayed(frm); },
	custom_reimburse_items_remove(frm) { cmi_compute_delayed(frm); },
});

// ---- Penomoran tertangguh (draft agent: nomor invoice diberikan saat Save / Confirm) ----
// Draft invoice buatan agent bernama sementara "DRAFT-...". Nomor asli baru diminta
// ke server saat user menyimpan / klik Confirm, lalu form pindah ke nomor barunya.
function cmi_inv_is_draft(frm) {
	return !frm.is_new() && (frm.doc.name || "").startsWith("DRAFT-");
}
function cmi_inv_assign_number(frm) {
	frappe.call({
		method: "erpnext_custom.overrides.sales_invoice.assign_invoice_number",
		args: { docname: frm.doc.name },
		freeze: true,
		freeze_message: __("Memberi nomor…"),
		callback(r) {
			const m = r && r.message;
			if (m && m.changed) {
				frappe.show_alert({ message: __("Nomor invoice: {0}", [m.name]), indicator: "green" });
				frappe.set_route("Form", "Sales Invoice", m.name);
			}
		},
	});
}
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (!cmi_inv_is_draft(frm)) return;
		frm.dashboard.set_headline(__("📝 Draft belum bernomor — nomor diberikan saat Save / klik Confirm."));
		frm.add_custom_button(__("Confirm & Beri Nomor"), () => {
			if (frm.is_dirty()) frm.save();
			else cmi_inv_assign_number(frm);
		}).addClass("btn-primary");
	},
	after_save(frm) { if (cmi_inv_is_draft(frm)) cmi_inv_assign_number(frm); },
});

// ---- Tab Connection: Packing List / Shipping List -> BL -> Container ----
// Pilih sumber -> nomor BL terisi; pilih BL -> container yang berhubungan dimuat
// otomatis ke tabel `custom_containers` (bisa di-add/remove manual).
function cmi_conn_call(method, args) {
	return frappe.call({ method, args }).then((r) => (r && r.message) || []);
}

// Sumber dokumen yang sedang dipilih (Packing List dan/atau Shipping List).
function cmi_conn_sources(frm) {
	const out = [];
	if (frm.doc.custom_packing_list) out.push({ doctype: "Packing List", name: frm.doc.custom_packing_list });
	if (frm.doc.custom_shipping_list) out.push({ doctype: "Shipping List", name: frm.doc.custom_shipping_list });
	return out;
}

// Bangun ulang opsi BL dari sumber terpilih + peta bl_no -> sumbernya.
// autoload=true: kalau cuma ada 1 BL, langsung dipilih (memicu muat container).
function cmi_conn_refresh_bls(frm, autoload) {
	const sources = cmi_conn_sources(frm);
	if (!sources.length) {
		frm._cmi_bl_map = {};
		frm.set_df_property("custom_bl_no", "options", "");
		if (frm.doc.custom_bl_no) frm.set_value("custom_bl_no", "");
		return;
	}
	Promise.all(
		sources.map((s) =>
			cmi_conn_call("erpnext_custom.connection.get_bls", { source_doctype: s.doctype, source_name: s.name }).then(
				(bls) => bls.map((b) => ({ bl_no: b.bl_no, doctype: s.doctype, name: s.name }))
			)
		)
	).then((lists) => {
		const map = {};
		const opts = [];
		[].concat(...lists).forEach((b) => {
			if (b.bl_no && !(b.bl_no in map)) {
				map[b.bl_no] = { doctype: b.doctype, name: b.name };
				opts.push(b.bl_no);
			}
		});
		frm._cmi_bl_map = map;
		frm.set_df_property("custom_bl_no", "options", "\n" + opts.join("\n"));
		if (frm.doc.custom_bl_no && !(frm.doc.custom_bl_no in map)) {
			frm.set_value("custom_bl_no", "");
		} else if (autoload && !frm.doc.custom_bl_no && opts.length === 1) {
			frm.set_value("custom_bl_no", opts[0]); // -> trigger custom_bl_no -> muat container
		}
	});
}

// Muat container untuk BL terpilih (menggantikan isi tabel).
function cmi_conn_load_containers(frm) {
	const bl = frm.doc.custom_bl_no;
	let src = (frm._cmi_bl_map || {})[bl];
	if (!src) {
		// Fallback (mis. form baru dibuka, peta belum dibangun) bila hanya satu sumber.
		const sources = cmi_conn_sources(frm);
		if (sources.length === 1) src = sources[0];
	}
	if (!src) return;
	const reuse = frm.doc.custom_reuse_master_job ? 1 : 0;
	cmi_conn_call("erpnext_custom.connection.get_containers", {
		source_doctype: src.doctype,
		source_name: src.name,
		bl_no: bl,
		current_invoice: frm.doc.__islocal ? null : frm.doc.name,
		include_invoiced: reuse,
	}).then((rows) => {
		frm.clear_table("custom_containers");
		(rows || []).forEach((d) => {
			Object.assign(frm.add_child("custom_containers"), {
				source_doctype: d.source_doctype,
				source_name: d.source_name,
				bl_no: d.bl_no,
				container_no: d.container_no,
				seal_no: d.seal_no,
				container_size: d.container_size,
				goods_description: d.goods_description,
				customer: d.customer,
			});
		});
		frm.refresh_field("custom_containers");
		frm.dirty();
		cmi_lock_customer(frm);
		if (rows && rows.length) {
			frappe.show_alert({ message: __("{0} container dimuat (BL {1}).", [rows.length, bl || "-"]), indicator: "green" });
		} else {
			const hint = reuse ? "" : __(" — mungkin semua sudah di-invoice. Centang 'Re Use Master Job' untuk menampilkan semua.");
			frappe.show_alert({ message: __("Tidak ada container untuk BL {0}.", [bl || "-"]) + hint, indicator: "orange" });
		}
	});
}

// Kunci Customer selama invoice ini terhubung ke Master Job (Shipping/Packing List
// ATAU sudah ada containers). Buka kembali HANYA kalau user menghapus shipping/packing
// list DAN semua containers di tab Connection. Cegah ganti customer di tengah jalan
// (customer sudah otomatis dari BL saat Create Invoice).
function cmi_lock_customer(frm) {
	const linked = !!(frm.doc.custom_shipping_list || frm.doc.custom_packing_list || (frm.doc.custom_containers || []).length);
	frm.set_df_property("customer", "read_only", linked ? 1 : 0);
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		cmi_conn_refresh_bls(frm, false); // bangun ulang opsi BL; jangan muat ulang container
		cmi_lock_customer(frm);
		// Source document hanya untuk customer invoice ini: SL muncul kalau consignee (BL)
		// ATAU customer (container) = customer; PL kalau item-nya bercustomer itu. Principle
		// SL hanya muncul kalau Invoice Type No = C/EA (dikirim ke query lewat type_no).
		frm.set_query("custom_shipping_list", () => ({
			query: "erpnext_custom.connection.shipping_lists_for_customer",
			filters: { customer: frm.doc.customer, reuse: frm.doc.custom_reuse_master_job ? 1 : 0, type_no: frm.doc.custom_invoice_type_no },
		}));
		frm.set_query("custom_packing_list", () => ({
			query: "erpnext_custom.connection.packing_lists_for_customer",
			filters: { customer: frm.doc.customer, reuse: frm.doc.custom_reuse_master_job ? 1 : 0 },
		}));
	},
	custom_packing_list(frm) {
		cmi_conn_refresh_bls(frm, true);
		cmi_lock_customer(frm);
	},
	custom_shipping_list(frm) {
		cmi_conn_refresh_bls(frm, true);
		cmi_lock_customer(frm);
	},
	custom_containers_remove(frm) { cmi_lock_customer(frm); },
	custom_bl_no(frm) {
		if (frm.doc.custom_bl_no) cmi_conn_load_containers(frm);
	},
	custom_reuse_master_job(frm) {
		// Centang/lepas → muat ulang container sesuai mode (semua vs hanya yang belum di-invoice).
		// Filter Master Job di picker source ikut berubah saat picker dibuka berikutnya.
		if (frm.doc.custom_bl_no) cmi_conn_load_containers(frm);
	},
	custom_reload_containers(frm) {
		if (!frm.doc.custom_bl_no) {
			frappe.msgprint(__("Pilih nomor BL dulu."));
			return;
		}
		cmi_conn_load_containers(frm);
	},
});

// ---- Modal "Pilih Containers" (untuk Invoice Type non-Trading) ----
// Multi-pilih container dari Packing List / Shipping List terpilih. Default hanya
// yang BELUM di-invoice; checkbox menampilkan yang sudah di-invoice juga.
function cmi_pick_sources(frm) {
	const out = [];
	if (frm.doc.custom_packing_list) out.push({ doctype: "Packing List", name: frm.doc.custom_packing_list });
	if (frm.doc.custom_shipping_list) out.push({ doctype: "Shipping List", name: frm.doc.custom_shipping_list });
	return out;
}

function cmi_open_container_picker(frm) {
	const sources = cmi_pick_sources(frm);
	if (!sources.length) {
		frappe.msgprint(__("Pilih Packing List / Shipping List dulu (tab Connection → Source Documents)."));
		return;
	}
	const dlg = new frappe.ui.Dialog({
		title: __("Pilih Containers"),
		size: "extra-large",
		fields: [
			{
				fieldname: "show_invoiced", fieldtype: "Check",
				label: __("Show BL/Containers Already Invoiced"),
				onchange() { cmi_picker_load(frm, dlg, sources); },
			},
			{ fieldname: "list_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Tambahkan Terpilih"),
		primary_action() { cmi_picker_add(frm, dlg); },
	});
	dlg.show();
	cmi_picker_load(frm, dlg, sources);
}

function cmi_picker_load(frm, dlg, sources) {
	const inc = dlg.get_value("show_invoiced") ? 1 : 0;
	dlg.fields_dict.list_html.$wrapper.html('<div class="text-muted" style="padding:12px;">Memuat…</div>');
	Promise.all(
		sources.map((s) =>
			frappe.call({
				method: "erpnext_custom.connection.get_pickable_containers",
				args: { source_doctype: s.doctype, source_name: s.name, current_invoice: frm.doc.name, include_invoiced: inc },
			}).then((r) => r.message || [])
		)
	).then((lists) => cmi_picker_render(dlg, [].concat(...lists)));
}

function cmi_picker_render(dlg, rows) {
	const esc = frappe.utils.escape_html;
	dlg._rows = rows;
	const $w = dlg.fields_dict.list_html.$wrapper;
	const body = rows.map((r, i) => `
		<tr class="${r.invoiced ? "text-muted" : ""}">
			<td style="text-align:center;"><input type="checkbox" class="cmi-cpick" data-i="${i}" ${r.invoiced ? "disabled" : ""}></td>
			<td>${i + 1}</td>
			<td>${esc(r.bl_no || "")}</td>
			<td>${esc(r.bl_date || "")}</td>
			<td>${esc(r.container_size || "")}</td>
			<td>${esc(r.cargo || "")}${r.invoiced ? ` <span class="indicator-pill orange" title="${esc(r.invoiced_in)}">sudah di-invoice</span>` : ""}</td>
		</tr>`).join("") || `<tr><td colspan="6" class="text-muted text-center" style="padding:12px;">Tidak ada container untuk ditampilkan.</td></tr>`;
	$w.html(`
		<div class="text-muted small" style="margin-bottom:6px;">${rows.length} container · centang yang mau ditambahkan</div>
		<div style="max-height:52vh;overflow:auto;">
		<table class="table table-bordered" style="font-size:12.5px;margin-bottom:0;">
			<thead><tr>
				<th style="width:34px;text-align:center;"><input type="checkbox" class="cmi-cpick-all"></th>
				<th style="width:42px;">No</th><th>BL Number</th><th>BL Date</th><th>Size</th><th>Cargo</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table></div>`);
	$w.find(".cmi-cpick-all").on("change", function () {
		$w.find(".cmi-cpick:not(:disabled)").prop("checked", this.checked);
	});
}

function cmi_picker_add(frm, dlg) {
	const $w = dlg.fields_dict.list_html.$wrapper;
	const picked = [];
	$w.find(".cmi-cpick:checked").each(function () { picked.push(dlg._rows[$(this).data("i")]); });
	if (!picked.length) { frappe.msgprint(__("Belum ada container dipilih.")); return; }
	const seen = new Set((frm.doc.custom_containers || []).map((c) => (c.source_name || "") + "|" + (c.container_no || "")));
	let added = 0;
	picked.forEach((r) => {
		const key = (r.source_name || "") + "|" + (r.container_no || "");
		if (seen.has(key)) return;
		Object.assign(frm.add_child("custom_containers"), {
			source_doctype: r.source_doctype, source_name: r.source_name, bl_no: r.bl_no,
			container_no: r.container_no, seal_no: r.seal_no, container_size: r.container_size,
			goods_description: r.goods_description, customer: r.customer,
		});
		seen.add(key); added++;
	});
	frm.refresh_field("custom_containers");
	frm.dirty();
	cmi_lock_customer(frm);
	dlg.hide();
	frappe.show_alert({ message: __("{0} container ditambahkan.", [added]), indicator: "green" });
}

frappe.ui.form.on("Sales Invoice", {
	custom_pick_containers(frm) { cmi_open_container_picker(frm); },
});

// ---- Tab Assistant + Email (shared dari app `agents`) — load on-demand & eval karena
// /assets/assistant tak tersaji di frontend. Render ke custom_assistant_html/custom_email_html
// + inject CSS sendiri (cmi_asst_style). Sama pola dgn doctype erp. ----
window.cmi_load_assistant = window.cmi_load_assistant || function (frm) {
	if (window.cmi_asst_render) { window.cmi_asst_render(frm); return; }
	frappe.call({ method: "assistant.assistant.api.assistant_js" }).then((r) => {
		if (r && r.message && !window.cmi_asst_render) {
			try { eval(r.message); } catch (e) { console.error("assistant_tabs eval", e); }
		}
		if (window.cmi_asst_render) window.cmi_asst_render(frm);
	});
};
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) { window.cmi_load_assistant(frm); },
});

// Sembunyikan grup tombol native "Get Items From" (Sales Order / Quotation / Delivery Note / Timesheet).
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		setTimeout(() => {
			const grp = __("Get Items From");
			["Sales Order", "Quotation", "Delivery Note", "Timesheet"].forEach((b) => frm.remove_custom_button(b, grp));
			// fallback: sembunyikan kontainer grup kalau masih ada (mis. child dari app lain)
			$(frm.page.inner_toolbar)
				.find(".custom-btn-group > button, .custom-btn-group > .dropdown-toggle")
				.filter(function () { return $(this).text().trim().indexOf(grp) === 0; })
				.closest(".custom-btn-group").hide();
		}, 50);
	},
});

// ---- Aksi Validate / Void / Revisi (pengganti Submit/Cancel) ----
// Ditaruh di dalam menu "..." (add_menu_item), BUKAN tombol toolbar. Tombol toolbar
// kelihatan kedip karena form ini memicu `refresh` berkali-kali (loader Assistant
// async, hitung amounts, dll) dan core membersihkan lalu menambah ulang tombol tiap
// refresh. Isi menu "..." juga dibersihkan+ditambah ulang tiap refresh, TAPI menunya
// tertutup sehingga churn-nya tak terlihat → stabil. Item custom muncul di paling
// atas menu, dipisah divider dari item standar (Discard/Email/Reload/...).
function cmi_do_validate(frm) {
	frappe.confirm(
		__("Validasi invoice <b>{0}</b>?<br>Setelah divalidasi, angka terkunci dan jurnal diposting.", [frm.doc.name]),
		() => {
			frappe.call({
				method: "erpnext_custom.overrides.sales_invoice.validate_invoice",
				args: { docname: frm.doc.name },
				freeze: true, freeze_message: __("Memvalidasi..."),
				callback() { frm.reload_doc(); },
			});
		}
	);
}
function cmi_do_void(frm) {
	frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Alasan Void"), reqd: 1 }],
		(v) => {
			frappe.call({
				method: "erpnext_custom.overrides.sales_invoice.void_invoice",
				args: { docname: frm.doc.name, reason: v.reason },
				freeze: true, freeze_message: __("Mem-void invoice..."),
				callback() { frm.reload_doc(); },
			});
		},
		__("Void Invoice"), __("Void")
	);
}
function cmi_do_revise(frm) {
	frappe.confirm(
		__("Revisi invoice <b>{0}</b>?<br><br>Invoice ini akan di-cancel (jurnalnya dibatalkan) " +
			"lalu dibuat ulang sebagai <b>draft dengan nomor yang sama</b> — silakan edit lalu Submit lagi.", [frm.doc.name]),
		() => {
			frappe.call({
				method: "erpnext_custom.overrides.sales_invoice.revise_invoice",
				args: { docname: frm.doc.name },
				freeze: true, freeze_message: __("Merevisi invoice..."),
				callback(r) {
					if (r && r.message) {
						frappe.show_alert({ message: __("Invoice {0} kembali jadi draft - silakan edit.", [r.message]), indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		}
	);
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.is_new()) return;
		const has = (r) => (frappe.user_roles || []).includes(r) || (frappe.user_roles || []).includes("System Manager");
		// standard=false → item custom, tampil di ATAS menu "..." dengan divider di bawah.
		if (frm.doc.docstatus === 0 && has("Invoice Validate")) {
			frm.page.add_menu_item(__("Validate"), () => cmi_do_validate(frm), false);
		}
		if (frm.doc.docstatus === 1 && has("Invoice Void")) {
			frm.page.add_menu_item(__("Void"), () => cmi_do_void(frm), false);
		}
		if (frm.doc.docstatus === 1 && has("Accounts Manager")) {
			frm.page.add_menu_item(__("Revisi"), () => cmi_do_revise(frm), false);
		}
	},
});

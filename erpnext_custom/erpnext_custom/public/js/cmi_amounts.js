// Shared smart-amount logic untuk form CMI (Sales/Purchase): field gabungan
// Discount/PPh/Tax ("10%" persen ATAU "50000" nominal) -> storage tersembunyi
// (percent/amount) + hitung Net Total live. Dipakai oleh purchase_order.js /
// purchase_invoice.js via frappe.require. Locale ID: titik=ribuan, koma=desimal.
(function () {
	if (window.cmiAmt) return;
	const flt = window.flt || ((v) => parseFloat(v) || 0);
	const SMART = [
		{ input: "custom_discount_input", pct: "custom_discount_percent", amt: "custom_discount_amount" },
		{ input: "custom_pph_input", pct: "custom_pph_percent", amt: "custom_pph_amount" },
		{ input: "custom_tax_input", pct: "custom_tax_percent", amt: "custom_tax_amount" },
	];
	const HELP = 'Ketik mis. "10%" atau "50000"';

	function parse(raw) {
		const s = (raw == null ? "" : String(raw)).trim();
		if (!s) return { empty: true, pct: null, amt: 0 };
		const isPct = s.indexOf("%") !== -1;
		const cleaned = s.replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(/,/g, ".");
		const num = parseFloat(cleaned) || 0;
		return isPct ? { empty: false, pct: num, amt: 0 } : { empty: false, pct: null, amt: num };
	}
	function fmtNominal(n) {
		const v = flt(n);
		return v % 1 === 0 ? v.toLocaleString("id-ID") : String(v).replace(".", ",");
	}
	function setNum(frm, field, val) {
		if (flt(frm.doc[field]) !== flt(val)) frm.set_value(field, val);
	}
	function setText(frm, field, text) {
		if ((frm.doc[field] || "") !== (text || "")) frm.set_value(field, text);
	}

	function applyInput(frm, cfg) {
		const p = parse(frm.doc[cfg.input]);
		if (p.empty) { setNum(frm, cfg.pct, 0); setNum(frm, cfg.amt, 0); }
		else if (p.pct !== null) { setNum(frm, cfg.pct, p.pct); }
		else { setNum(frm, cfg.pct, 0); setNum(frm, cfg.amt, p.amt); }
		compute(frm);
	}
	function hydrate(frm) {
		SMART.forEach((cfg) => {
			const p = flt(frm.doc[cfg.pct]), a = flt(frm.doc[cfg.amt]);
			setText(frm, cfg.input, p > 0 ? fmtNominal(p) + "%" : (a ? fmtNominal(a) : ""));
		});
	}
	function updateHints(frm) {
		const cur = frm.doc.currency || "IDR";
		SMART.forEach((cfg) => {
			let hint = HELP;
			if (cfg.input === "custom_tax_input" && frm.doc.custom_ignore_tax) {
				hint = "Tax diabaikan (Ignore Tax aktif)";
			} else if (flt(frm.doc[cfg.pct]) > 0 || flt(frm.doc[cfg.amt])) {
				hint = "= " + format_currency(flt(frm.doc[cfg.amt]), cur);
			}
			frm.set_df_property(cfg.input, "description", hint);
		});
	}
	// Estimasi Net Total live (server menghitung ulang dari grand_total saat save).
	function compute(frm) {
		const total = flt(frm.doc.total);
		let discount;
		if (flt(frm.doc.custom_discount_percent) > 0) {
			discount = (total * flt(frm.doc.custom_discount_percent)) / 100;
			setNum(frm, "custom_discount_amount", discount);
		} else discount = flt(frm.doc.custom_discount_amount);
		const dpp = total - discount;
		let tax;
		if (frm.doc.custom_ignore_tax) { tax = 0; setNum(frm, "custom_tax_amount", 0); }
		else if (flt(frm.doc.custom_tax_percent) > 0) {
			tax = (dpp * flt(frm.doc.custom_tax_percent)) / 100;
			setNum(frm, "custom_tax_amount", tax);
		} else tax = flt(frm.doc.custom_tax_amount);
		let pph;
		if (flt(frm.doc.custom_pph_percent) > 0) {
			pph = (dpp * flt(frm.doc.custom_pph_percent)) / 100;
			setNum(frm, "custom_pph_amount", pph);
		} else pph = flt(frm.doc.custom_pph_amount);
		const materai = flt(frm.doc.custom_materai);
		const adj = flt(frm.doc.custom_adjustment);
		setNum(frm, "custom_amount_total", total);
		setNum(frm, "custom_net_total", total - discount + tax - pph + materai + adj);
		updateHints(frm);
	}

	window.cmiAmt = { SMART, applyInput, hydrate, compute, updateHints };
})();

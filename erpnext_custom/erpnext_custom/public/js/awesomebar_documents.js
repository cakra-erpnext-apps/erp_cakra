// Kotak search desk (Ctrl+K) bawaannya cuma menawarkan nama doctype/report/halaman; untuk
// sampai ke dokumennya harus lewat langkah kedua "Search for ..." yang nyaris tidak pernah
// menemukan nomor transaksi (alasan lengkapnya di erpnext_custom/quick_search.py).
//
// File ini menyisipkan hasil dokumen ke dropdown yang sama, di baris paling atas: ketik
// nomornya (atau nama customer/supplier) lalu Enter, langsung ke formnya.
//
// Disisipkan di add_defaults(), bukan di build_options(), karena build_options harus
// sinkron (hasilnya langsung dipakai) sedangkan pencarian dokumen perlu ke server. Jadi
// daftar dropdown-nya ditulis ulang setelah jawabannya datang.
//
// Tes manual dari console browser: cmi_doc_search_test("PI/00001")
(function () {
	const MIN_CHARS = 3;
	// "Search for ..." bawaan pakai index 100; dokumen harus di atasnya
	const INDEX = 120;
	let seq = 0;

	function fetch_documents(bar, txt) {
		if (txt.length < MIN_CHARS || txt.charAt(0) === "#") return;

		const mine = ++seq;
		frappe.xcall("erpnext_custom.quick_search.find_documents", { txt }).then((docs) => {
			// jawaban untuk ketikan lama: user sudah lanjut mengetik, jangan timpa
			if (mine !== seq || !docs || !docs.length) return;

			const options = docs.map((d, i) => ({
				label: `${frappe.utils.xss_sanitise(d.name)} <span class="text-muted">${__(
					d.doctype
				)}</span>`,
				// dipakai Awesomplete sebagai kunci item, harus unik antar baris
				value: `${d.name} (${d.doctype})`,
				description: frappe.utils.xss_sanitise(d.description),
				route: ["Form", d.doctype, d.name],
				index: INDEX - i,
				match: txt,
				default: "Document",
			}));

			bar.options = options.concat(bar.options);
			bar.awesomplete.list = bar.deduplicate(bar.options);
		});
	}

	// tiap huruf = 1 panggilan yang menyapu ~130 tabel; tunggu ketikannya berhenti dulu
	// (input handler bawaan cuma menahan 50 ms, terlalu pendek untuk ini)
	const fetch_documents_later = frappe.utils.debounce(fetch_documents, 250);

	function patch() {
		const proto = frappe.search && frappe.search.AwesomeBar && frappe.search.AwesomeBar.prototype;
		if (!proto || proto.__cmi_documents) return !!proto;

		const add_defaults = proto.add_defaults;
		proto.add_defaults = function (txt) {
			add_defaults.call(this, txt);
			fetch_documents_later(this, txt);
		};
		proto.__cmi_documents = true;
		return true;
	}

	// AwesomeBar datang dari desk.bundle.js; kalau file ini kebetulan jalan lebih dulu,
	// tunggu sebentar alih-alih menyerah diam-diam (pola yang sama dgn report_fit_width.js)
	if (!patch()) {
		let tries = 0;
		const timer = setInterval(() => {
			if (patch() || ++tries > 40) clearInterval(timer);
			if (tries > 40) console.warn("[cmi] frappe.search.AwesomeBar tidak pernah muncul");
		}, 250);
	}

	window.cmi_doc_search_test = function (txt) {
		frappe.xcall("erpnext_custom.quick_search.find_documents", { txt: txt || "00001" }).then((d) =>
			console.log("[cmi] patched:", !!frappe.search.AwesomeBar.prototype.__cmi_documents, d)
		);
	};
})();

// Tabel query report tidak memenuhi lebar layar: frappe membangun datatable dengan
// `layout: "fixed"` (query_report.js), jadi lebar tabel = JUMLAH lebar kolom yang
// didefinisikan report, dan sisa layar tertinggal sebagai ruang kosong. Payment Ledger
// total kolomnya 900px, Trial Balance 1390px — di monitor lebar sisanya banyak.
//
// Kenapa BUKAN `layout: "fluid"` bawaan datatable: fluid memasang `overflow-x: hidden`
// pada badan tabel (frappe-datatable/src/style.js), jadi report yang kolomnya melebihi
// lebar layar justru terpotong dan tidak bisa digeser. Di sini kolom hanya DILEBARKAN
// saat memang ada sisa ruang; kalau tabelnya sudah selebar layar, tidak ada yang
// disentuh dan scroll horizontal tetap jalan.
//
// Disisipkan di window.DataTable, bukan di QueryReport.render_datatable, supaya KEDUA
// jalur ikut tertangani: pembuatan tabel pertama kali DAN `datatable.refresh()` yang
// dipakai saat filter diganti (jalur refresh membangun ulang lebar kolom, jadi kalau
// hanya membungkus render_datatable hasilnya tertimpa lagi).
//
// Tes manual dari console browser: cmi_report_fit_test()
(function () {
	// Sisa di bawah ini tidak sepadan dibagi-bagi ke kolom.
	const MIN_GAP = 8;
	// Layout kadang belum selesai saat konstruktor balik; ukur ulang beberapa kali.
	const RETRIES = [0, 120, 400];

	function measure(dt) {
		const wrap = dt && (dt.datatableWrapper || dt.wrapper);
		const header = dt && dt.header;
		const row = header && header.querySelector(".dt-row");
		return {
			available: wrap ? wrap.clientWidth : 0,
			used: row ? row.offsetWidth : 0,
			row: !!row,
		};
	}

	function fit(dt, verbose) {
		try {
			const m = measure(dt);
			if (!m.available || !m.row) {
				if (verbose) console.warn("[cmi] fit dilewati — belum terukur", m);
				return 0;
			}
			const gap = m.available - m.used;
			if (gap <= MIN_GAP) {
				if (verbose) console.log("[cmi] fit dilewati — tabel sudah penuh", m, "gap", gap);
				return 0;
			}
			const columns = dt.datamanager.getColumns().filter((c) => c.resizable);
			if (!columns.length) {
				if (verbose) console.warn("[cmi] fit dilewati — tak ada kolom resizable");
				return 0;
			}
			// -1 per kolom sebagai jarak aman terhadap border, supaya penambahan ini
			// sendiri tidak malah memunculkan scrollbar horizontal.
			const extra = Math.floor(gap / columns.length) - 1;
			if (extra <= 0) return 0;

			columns.forEach((col) => {
				const cell = dt.header.querySelector(`.dt-cell--col-${col.colIndex}`);
				const width = (cell ? cell.offsetWidth : col.width) + extra;
				dt.datamanager.updateColumn(col.colIndex, { width });
				dt.columnmanager.setColumnWidth(col.colIndex, width);
			});
			if (verbose) console.log("[cmi] fit:", m, "+", extra, "px x", columns.length, "kolom");
			return extra;
		} catch (e) {
			console.error("[cmi] fit gagal", e);
			return 0;
		}
	}

	function fit_later(dt) {
		RETRIES.forEach((ms) => setTimeout(() => fit(dt, ms === RETRIES[0]), ms));
	}

	function patch() {
		const Base = window.DataTable;
		if (!Base) return false;
		if (Base.__cmi_fit) return true;

		class CmiDataTable extends Base {
			constructor(wrapper, options) {
				super(wrapper, options);
				fit_later(this);
				window.addEventListener("resize", () => fit(this));
			}
			refresh(...args) {
				const out = super.refresh(...args);
				fit_later(this);
				return out;
			}
		}
		CmiDataTable.__cmi_fit = true;
		window.DataTable = CmiDataTable;
		console.log("[cmi] report fit-width aktif");
		return true;
	}

	// window.DataTable dipasang saat report.bundle.js dimuat. Kalau kebetulan file ini
	// jalan lebih dulu, tunggu sebentar alih-alih menyerah diam-diam.
	if (!patch()) {
		let tries = 0;
		const timer = setInterval(() => {
			if (patch() || ++tries > 40) clearInterval(timer);
			if (tries > 40) console.warn("[cmi] window.DataTable tidak pernah muncul");
		}, 250);
	}

	window.cmi_report_fit_test = function () {
		const dt = frappe.query_report && frappe.query_report.datatable;
		if (!dt) return console.warn("[cmi] buka halaman query report dulu");
		console.log("[cmi] patched:", !!(window.DataTable && window.DataTable.__cmi_fit));
		console.log("[cmi] ukuran  :", measure(dt));
		console.log("[cmi] hasil   :", fit(dt, true), "px per kolom");
	};
})();

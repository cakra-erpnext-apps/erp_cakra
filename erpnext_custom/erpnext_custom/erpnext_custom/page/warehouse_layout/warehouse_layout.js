// Layout Gudang: denah 2D per gudang -- rak, staging area, pintu, dan kantor.
//
// SEMUA angka di halaman ini METER. Posisi disimpan di Rack.map_x/map_y, dan ukuran kotak
// ADALAH ukuran fisik raknya (Rack.panjang x Rack.lebar) -- menarik gagang kotak mengubah
// ukuran rak yang sebenarnya, bukan angka gambar tersendiri. Tidak ada lagi map_w/map_h.
// Perbesaran (px per meter) cuma tampilan, tidak pernah tersimpan, jadi denah selalu
// sesuai skala.
//
// Tinggi tidak bisa digambar di denah 2D, jadi diisi di panel samping; volume mengikuti
// panjang x lebar x tinggi dan tampil di sana juga.
// Isi bin selalu dihitung ulang dari Item Bin Qty, tidak pernah disimpan di denah.
frappe.pages["warehouse-layout"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Layout Gudang"),
		single_column: true,
	});

	const SNAP = 0.1; // geser/ubah ukuran dipatok kelipatan 10 cm supaya angkanya bulat
	const ZOOMS = [20, 30, 50]; // px per meter
	// 20 px/m batas bawah: di bawah itu kotak rak (2,8 m) tipis dan tulisannya tidak
	// kebaca lagi. Gudang yang lebih besar dari layar digulung, bukan dikecilkan.
	const MIN_ZOOM = ZOOMS[0];
	const MAX_ZOOM = ZOOMS[ZOOMS.length - 1];
	const clampZoom = (z) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Math.round(z * 10) / 10));
	// Halaman dibuka langsung sebagai denah dengan binnya tergambar: itu yang dicari
	// orang gudang, dan tabel/tanpa-bin tinggal satu tombol.
	const state = { gudang: null, racks: [], edit: false, dirty: new Map(), selected: null,
		jarak: false, zoom: MIN_ZOOM, bin: true, binMap: null, view: "denah",
		warna: "isi", uomList: [] };

	const m2px = (m) => m * state.zoom;
	const px2m = (px) => px / state.zoom;
	const snap = (m) => Math.max(0, Math.round(m / SNAP) * SNAP);
	const fmtM = (m) => format_number(m, null, 2);

	const $body = $(`
		<div class="wl">
			<style>
				.wl { display: flex; gap: 12px; align-items: flex-start; padding: 8px 0; }
				.wl-canvas-wrap { flex: 1 1 auto; overflow: auto; border: 1px solid var(--border-color);
					border-radius: var(--border-radius-md); background: var(--fg-color); min-height: 480px; }
				/* kotak grid = 1 meter (ukurannya diset ulang tiap perbesaran berubah) */
				.wl-canvas { position: relative; min-height: 480px;
					background-image: linear-gradient(var(--border-color) 1px, transparent 1px),
						linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
					background-size: 40px 40px; opacity: 1; }
				.wl-rack { position: absolute; border: 1px solid var(--gray-500); border-radius: 3px;
					background: var(--gray-100); cursor: pointer; white-space: nowrap;
					font-size: var(--text-xs); user-select: none; }
				/* Label rak duduk DI LUAR kotak, pojok kiri atas: di dalam kotak yang muat
				   cuma kode bin, dan label yang menumpuk petak bikin kodenya tidak kebaca. */
				.wl-label { position: absolute; left: 0; bottom: 100%; margin-bottom: 1px;
					display: flex; gap: 6px; line-height: 1.2; pointer-events: none; z-index: 2; }
				/* rak punggung-ke-punggung: pita di atasnya sudah dipakai kotak lain,
				   labelnya turun ke bawah kotak supaya tidak menimpa kode bin tetangga */
				.wl-label-bawah { bottom: auto; top: 100%; margin: 1px 0 0; }
				.wl-label .wl-code { font-weight: 600; }
				.wl-label .wl-sub { color: var(--text-muted); }
				/* isi kotak = bar terisi dari bawah, jadi penuh/kosongnya kebaca sekilas */
				.wl-fill { position: absolute; left: 0; right: 0; bottom: 0; opacity: .35; }
				.wl-lo .wl-fill { background: var(--green-500); }
				.wl-mid .wl-fill { background: var(--orange-500); }
				.wl-hi .wl-fill { background: var(--red-500); }
				.wl-rack.wl-off { opacity: .45; border-style: dashed; }
				/* jenis kotak selain rak: warnanya beda supaya denah kebaca sekilas */
				.wl-k-Staging { background: var(--yellow-100); border-color: var(--yellow-500); }
				.wl-k-Pintu { background: var(--blue-100); border-color: var(--blue-500); border-style: dashed; }
				.wl-k-Kantor { background: var(--gray-200); border-color: var(--gray-500); }
				.wl-rack.wl-sel { outline: 2px solid var(--primary); outline-offset: 1px; }
				.wl-edit .wl-rack { cursor: move; }
				.wl-grip { position: absolute; right: 0; bottom: 0; width: 12px; height: 12px;
					background: var(--primary); cursor: nwse-resize; display: none; }
				.wl-edit .wl-grip { display: block; }
				.wl-side { flex: 0 0 340px; max-height: 78vh; overflow: auto;
					border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
					background: var(--fg-color); padding: 12px; }
				.wl-side h5 { margin: 0 0 2px; }
				.wl-muted { color: var(--text-muted); font-size: var(--text-xs); }
				.wl-lv { border: 1px solid var(--border-color); border-radius: 4px;
					padding: 6px 8px; margin-top: 6px; cursor: pointer; }
				.wl-lv:hover { background: var(--bg-color); }
				.wl-lv-head { display: flex; justify-content: space-between; gap: 8px; }
				.wl-bar { height: 4px; border-radius: 2px; background: var(--gray-200); margin-top: 4px; }
				.wl-bar > div { height: 100%; border-radius: 2px; background: var(--primary); }
				.wl-bin { padding: 4px 0 4px 10px; border-left: 2px solid var(--border-color); margin-top: 6px; }
				.wl-empty { padding: 40px; text-align: center; color: var(--text-muted); }
				/* Petak bin di dalam kotak rak, digambar seperti rak TAMPAK DEPAN:
				   kolom = bay, baris = tingkat (E paling atas, A paling bawah). Satu
				   petak = satu bin, diklik untuk melihat isinya di panel samping. */
				.wl-bins { position: absolute; inset: 0; display: grid; }
				/* kode bin tetap dicetak walau kecil (ukuran hurufnya ikut lebar petak);
				   yang tidak muat dipotong, bukan melebar keluar petak */
				.wl-cell { border-right: 1px solid var(--gray-400);
					border-bottom: 1px solid var(--gray-400); background: var(--gray-50);
					min-width: 0; min-height: 0; cursor: pointer; overflow: hidden;
					display: flex; align-items: center; justify-content: center;
					line-height: 1; letter-spacing: -0.2px; }
				.wl-cell-kosong { background: transparent; cursor: default; } /* binnya memang tidak ada */
				.wl-cell-lo { background: var(--green-400); }
				.wl-cell-mid { background: var(--orange-400); }
				.wl-cell-hi { background: var(--red-400); }
				.wl-cell:hover { outline: 1px solid var(--primary); outline-offset: -1px; }
				.wl-cell-pilih { outline: 2px solid var(--primary); outline-offset: -2px; }
				/* bin yang sedang masuk Replan yang belum disetujui: barangnya sedang
				   dipindah orang, jangan ada yang menitipkan barang ke situ dulu */
				.wl-cell-lock { outline: 2px dashed var(--gray-700); outline-offset: -2px; }
				/* Tampilan Tabel Bin: rak yang sama, tapi tidak berskala supaya kode binnya
				   terbaca -- persis bentuk denah di file Excel gudang. */
				.wl-tabel { padding: 10px 12px; }
				.wl-tblok { margin-bottom: 18px; }
				.wl-tblok h5 { margin: 0 0 6px; }
				.wl-tb { border-collapse: collapse; }
				.wl-tb th { font-size: var(--text-xs); color: var(--text-muted); font-weight: 500;
					padding: 2px 5px; text-align: center; }
				.wl-tlv { text-align: right; }
				.wl-tcell { padding: 3px 6px; font-size: var(--text-xs); text-align: center;
					white-space: nowrap; border: 1px solid var(--border-color); }
				.wl-tkosong { border: 1px dashed var(--border-color); }
				.wl-zona { font-weight: 600; margin: 0 0 8px; }
				.wl-legend { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
				.wl-chip { display: inline-flex; align-items: center; gap: 4px;
					font-size: var(--text-xs); color: var(--text-muted); }
				.wl-chip > i { width: 12px; height: 12px; border-radius: 3px;
					border: 1px solid var(--border-color); background: var(--gray-50); }
				/* penanda jarak: pita di celah antar kotak, angkanya dalam meter */
				.wl-dist { position: absolute; pointer-events: none; display: flex;
					align-items: center; justify-content: center; font-size: 10px;
					color: var(--blue-600); background: var(--blue-50); }
				.wl-dist-v { border-top: 1px dashed var(--blue-500); border-bottom: 1px dashed var(--blue-500); }
				.wl-dist-h { border-left: 1px dashed var(--blue-500); border-right: 1px dashed var(--blue-500);
					writing-mode: vertical-rl; }
				/* panel ukuran di samping: tinggi & volume yang tidak bisa digambar di denah */
				.wl-size { display: grid; grid-template-columns: auto 1fr; gap: 4px 8px;
					align-items: center; margin-top: 10px; }
				.wl-size input { width: 100%; padding: 2px 6px; text-align: right;
					border: 1px solid var(--border-color); border-radius: 4px;
					background: var(--control-bg); color: var(--text-color); }
				.wl-size .wl-vol { font-weight: 600; }
			</style>
			<div class="wl-canvas-wrap"><div class="wl-canvas"></div><div class="wl-tabel"></div></div>
			<div class="wl-side"></div>
		</div>
	`).appendTo(page.main);

	const $canvas = $body.find(".wl-canvas");

	// Ctrl + scroll = perbesar/perkecil, seperti peta pada umumnya. Titik di bawah
	// kursor dipertahankan supaya tidak kehilangan tempat saat mendekat.
	$body.find(".wl-canvas-wrap").on("wheel", function (e) {
		if (!e.ctrlKey) return;
		e.preventDefault();
		const $wrap = $(this);
		const rect = this.getBoundingClientRect();
		const mx = px2m(e.clientX - rect.left + $wrap.scrollLeft());
		const my = px2m(e.clientY - rect.top + $wrap.scrollTop());
		const arah = (e.originalEvent || e).deltaY < 0 ? 1.25 : 0.8;
		state.zoom = clampZoom(state.zoom * arah);
		zoomField.set_value(String(state.zoom));
		applyZoom();
		render();
		$wrap.scrollLeft(m2px(mx) - (e.clientX - rect.left));
		$wrap.scrollTop(m2px(my) - (e.clientY - rect.top));
	});
	const $side = $body.find(".wl-side");

	// ---------------------------------------------------------------- kontrol
	const gudangField = page.add_field({
		fieldname: "gudang",
		label: __("Gudang"),
		fieldtype: "Link",
		options: "Warehouse",
		get_query: () => ({ filters: { is_group: 0 } }),
		change() {
			flush().then(() => {
				state.gudang = gudangField.get_value();
				load();
			});
		},
	});

	// Perbesaran murni tampilan: denah tetap tersimpan dalam meter, jadi mengubah ini
	// tidak pernah menggeser apa pun.
	const zoomField = page.add_field({
		fieldname: "zoom",
		label: __("Perbesaran"),
		fieldtype: "Select",
		options: ZOOMS.map((z) => ({ label: __("{0} px / meter", [z]), value: String(z) })),
		default: String(state.zoom),
		change() {
			state.zoom = parseFloat(zoomField.get_value()) || MIN_ZOOM;
			applyZoom();
			render();
		},
	});

	// Dua cara mewarnai petak bin: seberapa penuh (harian) atau peruntukan kemasan
	// (bentuk denah di file Excel gudang). Datanya sama, cuma warnanya beda.
	const warnaField = page.add_field({
		fieldname: "warna",
		label: __("Warna"),
		fieldtype: "Select",
		options: [
			{ label: __("Isi bin"), value: "isi" },
			{ label: __("Peruntukan"), value: "uom" },
		],
		default: "isi",
		change() {
			state.warna = warnaField.get_value() || "isi";
			render();
		},
	});

	// Palet peruntukan diturunkan dari datanya, bukan daftar UOM yang dihardcode:
	// satuan baru di master langsung dapat warna sendiri.
	const uomWarna = (uom) => `hsl(${(state.uomList.indexOf(uom) * 67) % 360} 65% 78%)`;

	// Bin yang dikunci replan digambar bergaris putus-putus di kedua tampilan, apa pun
	// cara pewarnaannya: yang perlu dilihat orang gudang itu "jangan taruh di sini
	// dulu", bukan seberapa penuh binnya.
	const gembok = (b) => (b.locked ? " wl-cell-lock" : "");
	const judul = (b) => (b.locked ? `, replan ${b.locked}` : "");

	function warnaPetak(b) {
		if (state.warna === "uom") {
			return {
				cls: gembok(b).trim(),
				style: b.uom ? `background:${uomWarna(b.uom)}` : "",
			};
		}
		const p = pct(b.used, b.capacity);
		// bin kosong dibiarkan abu-abu: yang dicari mata itu yang TERISI
		const cls = b.qty <= 0 ? "" : p >= 85 ? "wl-cell-hi" : p >= 50 ? "wl-cell-mid" : "wl-cell-lo";
		return { cls: cls + gembok(b), style: "" };
	}

	function legenda() {
		if (state.warna !== "uom" || !state.uomList.length) return "";
		const chip = state.uomList
			.map(
				(u) =>
					`<span class="wl-chip"><i style="background:${uomWarna(u)}"></i>${frappe.utils.escape_html(u)}</span>`
			)
			.join("");
		return `<div class="wl-legend">${chip}<span class="wl-chip"><i></i>${__("tanpa peruntukan")}</span></div>`;
	}

	function applyZoom() {
		$canvas.css("background-size", `${m2px(1)}px ${m2px(1)}px`);
	}

	// Kanvas dipaskan ke isi denah + satu meter kelonggaran, supaya scrollbar-nya
	// jujur: tanpa ini kotak yang jauh terpotong, dan denah kecil menyisakan
	// hamparan kosong yang bikin susah mencari kotaknya.
	function fitCanvas() {
		let maxX = 0;
		let maxY = 0;
		state.racks.forEach((r) => {
			maxX = Math.max(maxX, r.x + r.w);
			maxY = Math.max(maxY, r.y + r.h);
		});
		$canvas.css({ width: m2px(maxX + 1), height: m2px(maxY + 1) });
	}

	// Perbesaran yang pas supaya SELURUH denah muat di lebar layar. Dipakai tombol
	// Muat Layar dan saat gudang pertama kali dimuat -- tidak ada gunanya membuka
	// denah 60 meter pada perbesaran yang cuma menampilkan sepertiganya.
	function zoomFit() {
		if (!state.racks.length) return;
		let maxX = 0;
		let maxY = 0;
		state.racks.forEach((r) => {
			maxX = Math.max(maxX, r.x + r.w);
			maxY = Math.max(maxY, r.y + r.h);
		});
		const lebar = $body.find(".wl-canvas-wrap").innerWidth() - 24;
		const tinggi = Math.max(360, $(window).height() * 0.6);
		const pas = Math.min(lebar / (maxX + 1), tinggi / (maxY + 1));
		state.zoom = clampZoom(pas);
		zoomField.set_value(String(state.zoom));
		applyZoom();
		render();
	}

	page.add_menu_item(__("Muat Layar"), () => zoomFit());
	page.add_menu_item(__("Tambah Kotak"), () => addBox());
	page.add_menu_item(__("Rapikan Otomatis"), () => arrange());
	page.add_menu_item(__("Hitung Jarak dari Pintu"), () => distanceFromMap());

	// Kotak apa pun (termasuk staging area kedua) dibuat dari sini, lalu digeser
	// ke tempatnya di denah.
	function addBox() {
		if (!state.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		// Menambah kotak memuat ulang denah dari server, jadi geseran yang belum
		// disimpan harus diamankan dulu.
		flush().then(() => promptBox());
	}

	function promptBox() {
		frappe.prompt(
			[
				{
					fieldname: "kind",
					label: __("Jenis"),
					fieldtype: "Select",
					options: ["Rak", "Staging", "Pintu", "Kantor"],
					default: "Staging",
					reqd: 1,
				},
				{ fieldname: "code", label: __("Kode"), fieldtype: "Data", reqd: 1 },
			],
			(v) => {
				frappe.call({
					method: "erpnext_custom.bin_layout.add_box",
					args: { gudang: state.gudang, kind: v.kind, code: v.code },
					freeze: true,
					callback() {
						frappe.show_alert(__("{0} {1} dibuat.", [v.kind, v.code]));
						load();
					},
				});
			},
			__("Tambah Kotak di Denah"),
			__("Tambah")
		);
	}

	// Titik awal denah: rak dijadikan lorong berpasangan. Menimpa posisi rak yang
	// ada, jadi ditanya dulu.
	function arrange() {
		if (!state.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		frappe.confirm(
			__("Posisi semua rak ditata ulang jadi lorong berpasangan. Pintu dan kantor yang sudah ditaruh tidak diubah. Lanjut?"),
			() =>
				flush().then(() =>
					frappe.call({
						method: "erpnext_custom.bin_layout.arrange",
						args: { gudang: state.gudang },
						freeze: true,
						callback(res) {
							frappe.show_alert(__("{0} kotak ditata ulang. Geser seperlunya.", [res.message]));
							load();
						},
					})
				)
		);
	}

	function distanceFromMap() {
		if (!state.gudang) return frappe.msgprint(__("Pilih gudang dulu."));
		// Jaraknya dihitung dari map_x/map_y di DB, bukan dari layar.
		flush().then(() => runDistanceFromMap());
	}

	function runDistanceFromMap() {
		frappe.call({
			method: "erpnext_custom.bin_layout.distance_from_map",
			args: { gudang: state.gudang },
			freeze: true,
			callback(res) {
				frappe.show_alert(__("Urutan jarak {0} rak diperbarui dari pintu terdekat.", [res.message]));
			},
		});
	}

	const $viewBtn = page.add_button(state.view === "tabel" ? __("Denah") : __("Tabel Bin"), () =>
		toggleView()
	);
	const $binBtn = page.add_button(state.bin ? __("Sembunyikan Bin") : __("Tampilkan Bin"), () =>
		toggleBin()
	);

	// Dua cara melihat rak yang sama: denah berskala (posisi benar, kode bin tidak
	// muat) dan tabel (kode bin terbaca, posisi tidak berarti). Datanya satu, bin_map.
	function toggleView() {
		state.view = state.view === "tabel" ? "denah" : "tabel";
		$viewBtn.text(state.view === "tabel" ? __("Denah") : __("Tabel Bin"));
		if (state.view === "tabel") toggleEdit(false); // tidak ada yang bisa digeser di tabel
		render();
	}
	const $distBtn = page.add_button(__("Check Distance"), () => toggleJarak());
	const $editBtn = page.set_secondary_action(__("Atur Denah"), () => toggleEdit());
	const $saveBtn = page.set_primary_action(__("Simpan Denah"), () => save());
	$saveBtn.hide();

	function toggleEdit(force) {
		state.edit = force === undefined ? !state.edit : force;
		$body.toggleClass("wl-edit", state.edit);
		$editBtn.text(state.edit ? __("Selesai Atur") : __("Atur Denah"));
		state.edit ? $saveBtn.show() : $saveBtn.hide();
		if (!state.edit && state.dirty.size) save();
	}

	// Posisi yang baru digeser cuma hidup di state.dirty. Apa pun yang memuat ulang
	// denah atau membaca posisi dari server WAJIB lewat sini dulu -- kalau tidak,
	// geserannya hilang tanpa kabar (itu yang dulu bikin denah "reset" saat
	// Tambah Kotak).
	function flush() {
		if (!state.dirty.size) return Promise.resolve();
		const jumlah = state.dirty.size;
		return frappe
			.call({
				method: "erpnext_custom.bin_layout.save_layout",
				args: { positions: JSON.stringify([...state.dirty.values()]) },
				freeze: true,
			})
			.then(() => {
				state.dirty.clear();
				frappe.show_alert(__("{0} kotak disimpan.", [jumlah]));
			});
	}

	// Isi rak digambar sebagai petak bay di dalam kotaknya. Petanya ditarik sekali
	// saat tombolnya dinyalakan -- payload-nya berat, tidak perlu ikut tiap muat denah.
	function toggleBin() {
		state.bin = !state.bin;
		$binBtn.text(state.bin ? __("Sembunyikan Bin") : __("Tampilkan Bin"));
		drawBins();
	}

	function loadBinMap() {
		if (state.binMap) return Promise.resolve(state.binMap);
		return frappe
			.call({
				method: "erpnext_custom.bin_layout.bin_map",
				args: { gudang: state.gudang },
				freeze: true,
			})
			.then((res) => {
				state.binMap = res.message || {};
				state.uomList = [
					...new Set(
						Object.values(state.binMap)
							.flatMap((petak) => petak.flatMap((s) => s.bins.map((b) => b.uom)))
							.filter(Boolean)
					),
				].sort();
				return state.binMap;
			});
	}

	function drawBins() {
		$canvas.find(".wl-bins").remove();
		$canvas.find(".wl-fill").show();
		if (!state.bin) return;
		if (!state.binMap) return loadBinMap().then(drawBins);
		$canvas.find(".wl-rack").each(function () {
			const $el = $(this);
			const rack = $el.data("rack");
			const petak = (state.binMap || {})[rack.name];
			if (!petak || !petak.length) return;
			// tingkat diambil dari bin yang benar-benar ada, jadi rak 2 tingkat tidak
			// digambar 5 baris. E di atas, A di bawah -- seperti orang berdiri di depan rak.
			const tingkat = [...new Set(petak.flatMap((s) => s.bins.map((b) => b.level)))]
				.sort()
				.reverse();
			// huruf dipaskan ke lebar petak supaya kode bin tetap tercetak walau kecil;
			// 0,62 = lebar rata-rata satu huruf terhadap ukuran hurufnya
			const panjangKode = Math.max(
				4,
				...petak.flatMap((s) => s.bins.map((b) => (b.bin_code || "").length))
			);
			const lebarPetak = m2px(rack.w) / petak.length;
			const $grid = $('<div class="wl-bins"></div>').css({
				gridTemplateColumns: `repeat(${petak.length}, 1fr)`,
				gridTemplateRows: `repeat(${tingkat.length}, 1fr)`,
				fontSize: `${Math.max(4, Math.min(11, lebarPetak / (0.62 * panjangKode)))}px`,
			});
			tingkat.forEach((lv) => {
				petak.forEach((s) => {
					const b = s.bins.find((x) => x.level === lv);
					if (!b) return $('<div class="wl-cell wl-cell-kosong"></div>').appendTo($grid);
					const w = warnaPetak(b);
					$(`<div class="wl-cell ${w.cls}" style="${w.style}" title="${frappe.utils.escape_html(
						`${b.bin_code}: ${format_number(b.qty)} unit, ${pct(b.used, b.capacity)}%${
							b.uom ? ", " + b.uom : ""
						}${judul(b)}`
					)}"></div>`)
						.text(b.bin_code)
						.data({ bin: b, rack: rack, bay: s.bay })
						.appendTo($grid);
				});
			});
			$grid.prependTo($el);
			$el.find(".wl-fill").hide(); // bar isi rak diganti petak bin, jangan menumpuk
		});
	}

	// Klik petak = klik satu KOLOM bin (bay): yang dilihat orang gudang itu satu tiang
	// rak dari bawah ke atas, bukan satu petak. Dipasang sekali di kanvas (render() cuma
	// mengosongkan isinya, bukan menghapus kanvasnya), jadi tidak perlu dipasang ulang.
	$body.find(".wl-canvas-wrap").on("click", ".wl-cell", function (e) {
		if (state.edit) return;
		e.stopPropagation(); // jangan ikut membuka panel rak
		const { rack, bay } = $(this).data();
		if (!rack || bay === undefined) return;
		$body.find(".wl-cell").removeClass("wl-cell-pilih");
		$body
			.find(".wl-cell")
			.filter(function () {
				const d = $(this).data();
				return d.rack === rack && d.bay === bay;
			})
			.addClass("wl-cell-pilih");
		$canvas.find(".wl-rack").removeClass("wl-sel");
		showBay(rack, bay);
	});

	// Tabel rak: kolom = bay, baris = tingkat, isinya kode bin. Tidak berskala, jadi
	// dipakai kalau yang dicari kode binnya; warnanya sama dengan di denah.
	function drawTabel() {
		const $t = $body.find(".wl-tabel").empty();
		const isi = state.racks.filter((r) => ((state.binMap || {})[r.name] || []).length);
		if (!isi.length) {
			return $t.html(`<div class="wl-empty">${__("Gudang ini belum punya bin.")}</div>`);
		}
		// dikelompokkan per zona, seperti label "A Zone / B Zone / C Zone" di file Excel
		const zona = {};
		isi.forEach((r) => (zona[r.zone || ""] = (zona[r.zone || ""] || []).concat([r])));
		Object.keys(zona)
			.sort()
			.forEach((z) => {
				$(`<div class="wl-zona">${z ? __("Zona {0}", [frappe.utils.escape_html(z)]) : __("Tanpa zona")}</div>`).appendTo($t);
				zona[z].forEach(gambarRak);
			});

		function gambarRak(rack) {
			const petak = state.binMap[rack.name];
			const tingkat = [...new Set(petak.flatMap((s) => s.bins.map((b) => b.level)))]
				.sort()
				.reverse();
			const $tb = $('<table class="wl-tb"></table>');
			const $head = $("<tr></tr>").append("<th></th>");
			petak.forEach((s) => $head.append($("<th></th>").text(s.bay)));
			$tb.append($("<thead></thead>").append($head));
			const $body_ = $("<tbody></tbody>");
			tingkat.forEach((lv) => {
				const $tr = $("<tr></tr>").append($('<th class="wl-tlv"></th>').text(lv));
				petak.forEach((s) => {
					const b = s.bins.find((x) => x.level === lv);
					if (!b) return $tr.append('<td class="wl-tkosong"></td>');
					const w = warnaPetak(b);
					$tr.append(
						$(`<td class="wl-cell wl-tcell ${w.cls}" style="${w.style}"></td>`)
							.text(b.bin_code)
							.attr(
								"title",
								`${format_number(b.qty)} unit, ${pct(b.used, b.capacity)}%${
									b.uom ? ", " + b.uom : ""
								}${judul(b)}`
							)
							.data({ bin: b, rack: rack, bay: s.bay })
					);
				});
				$body_.append($tr);
			});
			$tb.append($body_);
			$(
				`<div class="wl-tblok"><h5>${frappe.utils.escape_html(rack.rack_code)}
					<span class="wl-muted">${petak.reduce((n, s) => n + s.bins.length, 0)} ${__("bin")}</span></h5></div>`
			)
				.append($tb)
				.appendTo($t);
		}
	}

	// Isi satu KOLOM bin. Rincian item sengaja TIDAK ikut bin_map -- payloadnya jadi
	// berkali lipat untuk 500 bin padahal yang dilihat cuma satu kolom; seluruh rak
	// ditarik sekali di sini lalu disaring ke bin kolom itu (satu panggilan, bukan
	// satu per tingkat).
	function showBay(rack, bay) {
		const petak = ((state.binMap || {})[rack.name] || []).find((s) => s.bay === bay);
		if (!petak) return;
		const bins = [...petak.bins].sort((a, b) => (a.level < b.level ? 1 : -1)); // E atas, A bawah
		const kepala = `
			<h5>${frappe.utils.escape_html(rack.rack_code)} ${__("kolom")} ${frappe.utils.escape_html(String(bay))}</h5>
			<div class="wl-muted">${bins.length} ${__("bin")}</div>`;
		$side.html(`${kepala}<div class="wl-muted">${__("Memuat isi bin")}...</div>`);
		frappe.call({
			method: "erpnext_custom.bin_layout.rack_level_contents",
			args: { rack: rack.name },
			callback(res) {
				const isi = {};
				(res.message || []).forEach((r) => (isi[r.bin] = r));
				$side.html(`
					${kepala}
					${bins.map((b) => kartuBin(rack, b, isi[b.bin])).join("")}
					<div style="margin-top:10px"><a class="wl-balik" href="#">${__("Lihat seluruh rak")}</a></div>
				`);
				$side.find(".wl-balik").on("click", (e) => {
					e.preventDefault();
					reselect(rack);
				});
			},
		});
	}

	// Satu bin di panel samping: judul "kode - kapasitas", lalu rak + tingkatnya,
	// lalu daftar item dengan rasio isinya terhadap seluruh isi bin itu.
	function kartuBin(rack, bin, row) {
		const cap = flt((row || bin).capacity);
		const items = (row && row.items) || [];
		// rasio dihitung dari BERAT kalau item-itemnya punya berat master; kalau tidak
		// (kebanyakan master belum diisi) jatuh ke jumlah unit, supaya tetap ada angka
		const totalBerat = items.reduce((n, it) => n + flt(it.weight), 0);
		const totalQty = items.reduce((n, it) => n + flt(it.qty), 0);
		const total = totalBerat || totalQty;
		const daftar = items.length
			? items
					.map((it) => {
						const bagian = totalBerat ? flt(it.weight) : flt(it.qty);
						const r = total > 0 ? Math.round((bagian / total) * 100) : 0;
						return `<div>- ${frappe.utils.escape_html(it.item_name || it.item_code)} =
							${format_number(it.qty)} ${frappe.utils.escape_html(it.stock_uom || "")}
							- ${__("Rasio")} (${r}%)</div>`;
					})
					.join("")
			: `<div class="wl-muted">${__("kosong")}</div>`;
		return `
			<div class="wl-bin">
				<div><b>${frappe.utils.escape_html(bin.bin_code)}</b>
					<span class="wl-muted">- ${cap ? format_number(cap) + " kg" : __("tanpa batas")}</span></div>
				<div class="wl-muted">${frappe.utils.escape_html(rack.rack_code)},
					${__("Tingkat")} ${frappe.utils.escape_html(bin.level)}</div>
				<div style="margin-top:4px">${__("List Item")} :</div>
				${daftar}
			</div>`;
	}

	// Jarak antar kotak, dihitung dari posisi di denah lalu dikali skala (px -> meter).
	function toggleJarak() {
		state.jarak = !state.jarak;
		$distBtn.text(state.jarak ? __("Sembunyikan Jarak") : __("Check Distance"));
		drawJarak();
	}

	function save() {
		if (!state.dirty.size) return frappe.show_alert(__("Tidak ada perubahan posisi."));
		flush();
	}

	// ---------------------------------------------------------------- data
	function load() {
		if (!state.gudang) return;
		frappe.call({
			method: "erpnext_custom.bin_layout.layout",
			args: { gudang: state.gudang },
			freeze: true,
			callback(res) {
				state.racks = res.message || [];
				state.binMap = null; // peta bin milik gudang lain tidak berlaku di sini
				state.pasSekali = false;
				state.dirty.clear();
				applyZoom();
				render();
			},
		});
	}

	function render() {
		$canvas.empty();
		$side.empty();
		const tabel = state.view === "tabel";
		$canvas.toggle(!tabel);
		$body.find(".wl-tabel").toggle(tabel);
		if (tabel) {
			return loadBinMap().then(() => {
				$side.html(
					legenda() +
						`<div class="wl-muted">${__("Klik satu bin untuk melihat seluruh kolomnya. Tombol Denah untuk kembali ke gambar berskala.")}</div>`
				);
				drawTabel();
			});
		}
		if (!state.racks.length) {
			$canvas.html(
				`<div class="wl-empty">${__("Gudang ini belum punya kotak. Pakai menu Tambah Kotak.")}</div>`
			);
			return;
		}
		state.racks.forEach(drawRack);
		fitCanvas();
		// sekali saja per gudang: buka denah pada perbesaran yang memuat semuanya
		if (!state.pasSekali && state.racks.length) {
			state.pasSekali = true;
			return zoomFit();
		}
		drawBins();
		drawJarak();
		$side.html(
			legenda() +
				`<div class="wl-muted">${__("Klik satu kolom bin untuk melihat isinya, atau kotak raknya untuk ringkasan per tingkat.")}</div>`
		);
	}

	function pct(used, capacity) {
		return capacity > 0 ? Math.min(100, Math.round((used / capacity) * 100)) : 0;
	}

	const LABEL_PX = 16; // tinggi satu baris label

	// Label maunya di ATAS kotak, tapi rak punggung-ke-punggung tidak menyisakan pita
	// di situ -- labelnya akan duduk di atas kode bin tetangganya. Kalau begitu, dan
	// di bawah lebih lega, labelnya dipindah ke bawah. Kalau dua-duanya sempit, tetap
	// di atas: setidaknya semua label sejajar.
	function labelKeBawah(rack) {
		const perlu = px2m(LABEL_PX);
		const sela = (naik) => {
			let g = naik ? rack.y : Infinity; // ke atas dibatasi tepi kanvas
			state.racks.forEach((b) => {
				if (b === rack) return;
				if (b.x >= rack.x + rack.w || b.x + b.w <= rack.x) return; // tidak bertumpuk mendatar
				const d = naik ? rack.y - (b.y + b.h) : b.y - (rack.y + rack.h);
				if (d >= 0) g = Math.min(g, d);
			});
			return g;
		};
		const atas = sela(true);
		return atas < perlu && sela(false) > atas;
	}

	function drawRack(rack) {
		const kind = rack.kind || "Rak";
		const holdsStock = kind === "Rak" || kind === "Staging";
		const p = holdsStock ? pct(rack.used, rack.capacity) : 0;
		const band = p >= 85 ? "wl-hi" : p >= 50 ? "wl-mid" : "wl-lo";
		// pintu & kantor tidak punya isi, jadi yang ditulis jenisnya saja
		// ukurannya ikut ditulis di kotak: denah ini memang gambar berskala, bukan diagram
		const ukuran = rack.w && rack.h ? `${fmtM(rack.w)} x ${fmtM(rack.h)} m` : "";
		const sub = holdsStock ? `${rack.bins} ${__("bin")}, ${p}%` : __(kind);
		const $el = $(`
			<div class="wl-rack wl-k-${kind} ${band} ${rack.disabled ? "wl-off" : ""}">
				<div class="wl-fill" style="height:${p}%"></div>
				<div class="wl-label ${labelKeBawah(rack) ? "wl-label-bawah" : ""}">
					<span class="wl-code">${frappe.utils.escape_html(rack.rack_code)}</span>
					<span class="wl-sub">${sub}</span>
					<span class="wl-sub wl-dim">${ukuran}</span>
				</div>
				<div class="wl-grip"></div>
			</div>
		`)
			.css({ left: m2px(rack.x), top: m2px(rack.y), width: m2px(rack.w), height: m2px(rack.h) })
			.data("rack", rack)
			.appendTo($canvas);

		$el.on("click", () => {
			if (state.edit) return;
			$canvas.find(".wl-rack").removeClass("wl-sel");
			$el.addClass("wl-sel");
			state.selected = rack;
			showRack(rack);
		});
		makeDraggable($el, rack);
	}

	// Geser & ubah ukuran pakai pointer events langsung: cuma perlu satu kotak,
	// tidak sepadan menarik library drag apa pun.
	function makeDraggable($el, rack) {
		let mode = null, sx = 0, sy = 0, ox = 0, oy = 0, ow = 0, oh = 0;

		$el.on("pointerdown", (e) => {
			if (!state.edit) return;
			mode = $(e.target).hasClass("wl-grip") ? "resize" : "move";
			sx = e.clientX; sy = e.clientY;
			ox = rack.x; oy = rack.y; ow = rack.w; oh = rack.h;
			$el[0].setPointerCapture(e.pointerId);
			e.preventDefault();
		});

		$el.on("pointermove", (e) => {
			if (!mode) return;
			// geseran layar (px) dikembalikan ke meter dulu -- itu satuan yang disimpan
			const dx = px2m(e.clientX - sx), dy = px2m(e.clientY - sy);
			if (mode === "move") {
				rack.x = snap(ox + dx);
				rack.y = snap(oy + dy);
				$el.css({ left: m2px(rack.x), top: m2px(rack.y) });
			} else {
				// menarik gagang = mengubah panjang x lebar rak yang SEBENARNYA
				rack.w = Math.max(SNAP, snap(ow + dx));
				rack.h = Math.max(SNAP, snap(oh + dy));
				rack.panjang = rack.w;
				rack.lebar = rack.h;
				rack.volume = rack.w * rack.h * (rack.tinggi || 0);
				$el.css({ width: m2px(rack.w), height: m2px(rack.h) });
				$el.find(".wl-dim").text(`${fmtM(rack.w)} x ${fmtM(rack.h)} m`);
				if (state.selected === rack) showRack(rack);
			}
		});

		$el.on("pointerup pointercancel", (e) => {
			if (!mode) return;
			mode = null;
			$el[0].releasePointerCapture(e.pointerId);
			redrawBox(rack); // posisi baru bisa bikin labelnya harus pindah atas/bawah
			tandaiBerubah(rack);
			drawJarak(); // celahnya berubah begitu kotaknya dilepas
		});
	}

	// Untuk tiap kotak dicari tetangga TERDEKAT ke kanan dan ke bawah yang
	// proyeksinya bertumpuk, lalu celahnya diberi pita berlabel. Cuma tetangga
	// terdekat, supaya denah tidak penuh garis.
	function drawJarak() {
		$canvas.find(".wl-dist").remove();
		if (!state.jarak) return;
		const kotak = state.racks;
		const label = (m) => `${fmtM(m)} m`;

		kotak.forEach((a) => {
			let kanan = null;
			let bawah = null;
			kotak.forEach((b) => {
				if (b === a) return;
				const tumpangY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
				if (tumpangY > 0) {
					const sela = b.x - (a.x + a.w);
					if (sela >= 0 && (!kanan || sela < kanan.sela)) kanan = { b, sela, tumpangY };
				}
				const tumpangX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
				if (tumpangX > 0) {
					const sela = b.y - (a.y + a.h);
					if (sela >= 0 && (!bawah || sela < bawah.sela)) bawah = { b, sela, tumpangX };
				}
			});

			if (bawah && bawah.sela > 0) {
				const x = Math.max(a.x, bawah.b.x);
				$(`<div class="wl-dist wl-dist-v">${label(bawah.sela)}</div>`)
					.css({ left: m2px(x), top: m2px(a.y + a.h),
						width: m2px(bawah.tumpangX), height: m2px(bawah.sela) })
					.appendTo($canvas);
			}
			if (kanan && kanan.sela > 0) {
				const y = Math.max(a.y, kanan.b.y);
				$(`<div class="wl-dist wl-dist-h">${label(kanan.sela)}</div>`)
					.css({ left: m2px(a.x + a.w), top: m2px(y),
						width: m2px(kanan.sela), height: m2px(kanan.tumpangY) })
					.appendTo($canvas);
			}
		});
	}

	// ---------------------------------------------------------------- panel isi
	function showRack(rack) {
		const p = pct(rack.used, rack.capacity);
		const levels = rack.levels
			.map((lv) => {
				const lp = pct(lv.used, lv.capacity);
				return `
					<div class="wl-lv" data-level="${frappe.utils.escape_html(lv.level)}">
						<div class="wl-lv-head">
							<b>${__("Tingkat")} ${frappe.utils.escape_html(lv.level)}</b>
							<span class="wl-muted">${lv.bins} ${__("bin")}, ${lp}%</span>
						</div>
						<div class="wl-muted">${__("Isi")} ${format_number(lv.qty)}, ${__("berat")}
							${format_number(lv.used)} / ${lv.capacity ? format_number(lv.capacity) : "tanpa batas"} kg</div>
						<div class="wl-bar"><div style="width:${lp}%"></div></div>
						<div class="wl-detail"></div>
					</div>`;
			})
			.join("");

		$side.html(`
			<h5>${frappe.utils.escape_html(rack.rack_code)}</h5>
			<div class="wl-muted">${__(rack.kind || "Rak")}, ${rack.bins} ${__("bin")}, ${__("terisi")} ${p}%
				${rack.zone ? ", " + __("zona") + " " + frappe.utils.escape_html(rack.zone) : ""}</div>
			<div class="wl-size">
				<span class="wl-muted">${__("Panjang")}</span>
				<input type="number" step="0.1" min="0" data-f="panjang" value="${flt(rack.panjang || rack.w)}">
				<span class="wl-muted">${__("Lebar")}</span>
				<input type="number" step="0.1" min="0" data-f="lebar" value="${flt(rack.lebar || rack.h)}">
				<span class="wl-muted">${__("Tinggi")}</span>
				<input type="number" step="0.1" min="0" data-f="tinggi" value="${flt(rack.tinggi)}">
				<span class="wl-muted">${__("Volume")}</span>
				<span class="wl-vol">${fmtM(rack.volume || 0)} m³</span>
			</div>
			<div class="wl-muted">${__("Semua dalam meter. Panjang &amp; lebar juga bisa ditarik langsung di denah; tinggi hanya di sini.")}</div>
			<div style="margin-top:8px">
				<a href="/app/rack/${encodeURIComponent(rack.name)}">${__("Buka master rak")}</a>
			</div>
			${levels || `<div class="wl-muted" style="margin-top:10px">${__("Kotak ini belum punya bin.")}</div>`}
		`);

		// Mengetik ukuran = kotaknya langsung berubah di denah, TAPI belum disimpan.
		// Server tidak dipanggil per ketikan (tiap angka akan jadi satu request dan
		// satu save doc); perubahannya menumpuk di state.dirty seperti hasil geseran,
		// lalu ikut tersimpan sekali lewat tombol Simpan Denah.
		$side.find(".wl-size input").on("input", function () {
			const ukuran = {};
			$side.find(".wl-size input").each(function () {
				ukuran[$(this).data("f")] = flt($(this).val());
			});
			Object.assign(rack, ukuran, { w: ukuran.panjang, h: ukuran.lebar });
			// volume di sini cuma pratinjau; yang dipakai tetap hitungan controller Rack
			rack.volume = ukuran.panjang * ukuran.lebar * ukuran.tinggi;
			$side.find(".wl-vol").text(`${fmtM(rack.volume || 0)} m³`);
			redrawBox(rack);
			drawJarak(); // celah ke tetangganya ikut berubah
			tandaiBerubah(rack);
		});

		$side.find(".wl-lv").on("click", function () {
			const $lv = $(this);
			const $detail = $lv.find(".wl-detail");
			if ($detail.children().length) return $detail.empty(); // klik lagi = tutup
			frappe.call({
				method: "erpnext_custom.bin_layout.rack_level_contents",
				args: { rack: rack.name, level: $lv.data("level") },
				callback(res) {
					$detail.html(renderBins(res.message || []));
				},
			});
		});
	}

	// render() menggambar ulang seluruh denah, jadi kotak yang sedang dipilih harus
	// ditandai & panelnya dibuka lagi.
	// Gambar ulang satu kotak saja. render() penuh akan membuang seleksi dan
	// menutup panel samping tepat saat orangnya sedang mengetik di situ.
	function redrawBox(rack) {
		$canvas.find(".wl-rack").each(function () {
			const $el = $(this);
			if ($el.data("rack") !== rack) return;
			$el.css({ left: m2px(rack.x), top: m2px(rack.y), width: m2px(rack.w), height: m2px(rack.h) });
			if (rack.w && rack.h) $el.find(".wl-dim").text(`${fmtM(rack.w)} x ${fmtM(rack.h)} m`);
			// kotaknya pindah/berubah ukuran -> pita di atasnya bisa jadi tidak lega lagi
			$el.find(".wl-label").toggleClass("wl-label-bawah", labelKeBawah(rack));
		});
	}

	function tandaiBerubah(rack) {
		state.dirty.set(rack.name, {
			name: rack.name, x: rack.x, y: rack.y, w: rack.w, h: rack.h, tinggi: rack.tinggi,
		});
		$saveBtn.show(); // ukuran bisa diubah tanpa masuk mode Atur Denah
	}

	function reselect(rack) {
		$canvas.find(".wl-rack").each(function () {
			if ($(this).data("rack") === rack) $(this).addClass("wl-sel");
		});
		state.selected = rack;
		showRack(rack);
	}

	function renderBins(bins) {
		if (!bins.length) return `<div class="wl-muted">${__("Tidak ada bin.")}</div>`;
		return bins
			.map((b) => {
				const items = b.items.length
					? b.items
							.map(
								(it) =>
									`<div>${frappe.utils.escape_html(it.item_name || it.item_code)}:
									${format_number(it.qty)} ${frappe.utils.escape_html(it.stock_uom || "")}</div>`
							)
							.join("")
					: `<div class="wl-muted">${__("kosong")}</div>`;
				return `
					<div class="wl-bin">
						<div><b>${frappe.utils.escape_html(b.bin_code)}</b>
							<span class="wl-muted">${format_number(b.used)} /
							${b.capacity ? format_number(b.capacity) : "tanpa batas"} kg</span></div>
						${items}
					</div>`;
			})
			.join("");
	}

	// gudang pertama yang punya rak dipilih otomatis supaya halaman tidak tampil kosong
	frappe.db
		.get_list("Rack", { fields: ["gudang"], limit: 1, order_by: "gudang" })
		.then((rows) => {
			if (rows.length) gudangField.set_value(rows[0].gudang);
		});
};

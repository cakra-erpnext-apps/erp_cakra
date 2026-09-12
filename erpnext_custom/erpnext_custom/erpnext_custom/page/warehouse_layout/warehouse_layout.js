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
	const ZOOMS = [3, 5, 8, 12.5, 20, 30, 50]; // px per meter
	// 12,5 px/m: gudang 60 x 40 m jadi 750 x 500 px, muat satu layar.
	const state = { gudang: null, racks: [], edit: false, dirty: new Map(), selected: null,
		jarak: false, zoom: 12.5, bin: false, binMap: null };

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
					background: var(--gray-100); overflow: hidden; cursor: pointer;
					display: flex; align-items: center; gap: 6px; padding: 0 6px; white-space: nowrap;
					font-size: var(--text-xs); user-select: none; }
				.wl-rack .wl-code { font-weight: 600; }
				.wl-rack .wl-sub { color: var(--text-muted); font-size: var(--text-xs); }
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
				/* petak bin di dalam kotak rak. Denah ini tampak atas, jadi yang terlihat
				   bay sepanjang rak; tingkat A..E menumpuk ke arah kita dan dirangkum. */
				.wl-bays { position: absolute; inset: 0; display: flex; }
				.wl-bay { flex: 1 1 0; border-right: 1px solid var(--gray-400); position: relative;
					background: var(--gray-50); }
				.wl-bay:last-child { border-right: 0; }
				.wl-bay > i { position: absolute; left: 0; right: 0; bottom: 0; display: block; }
				.wl-bay-lo > i { background: var(--green-400); }
				.wl-bay-mid > i { background: var(--orange-400); }
				.wl-bay-hi > i { background: var(--red-400); }
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
			<div class="wl-canvas-wrap"><div class="wl-canvas"></div></div>
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
		state.zoom = Math.max(2, Math.min(50, Math.round(state.zoom * arah * 10) / 10));
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
			state.zoom = parseFloat(zoomField.get_value()) || 12.5;
			applyZoom();
			render();
		},
	});

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
		state.zoom = Math.max(2, Math.min(50, Math.round(pas * 10) / 10));
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

	const $binBtn = page.add_button(__("Tampilkan Bin"), () => toggleBin());
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
		if (!state.bin) return drawBins();
		if (state.binMap) return drawBins();
		frappe.call({
			method: "erpnext_custom.bin_layout.bin_map",
			args: { gudang: state.gudang },
			freeze: true,
			callback(res) {
				state.binMap = res.message || {};
				drawBins();
			},
		});
	}

	function drawBins() {
		$canvas.find(".wl-bays").remove();
		if (!state.bin || !state.binMap) return;
		$canvas.find(".wl-rack").each(function () {
			const $el = $(this);
			const rack = $el.data("rack");
			const petak = (state.binMap || {})[rack.name];
			if (!petak || !petak.length) return;
			const $bays = $('<div class="wl-bays"></div>');
			petak.forEach((s) => {
				const isi = s.capacity > 0 ? Math.min(100, Math.round((s.used / s.capacity) * 100)) : 0;
				const band = isi >= 85 ? "wl-bay-hi" : isi >= 50 ? "wl-bay-mid" : "wl-bay-lo";
				const rinci = s.bins.map((b) => `${b.bin_code} ${format_number(b.qty)}`).join(", ");
				$(`<div class="wl-bay ${band}" title="${frappe.utils.escape_html(
					`${rack.rack_code} bay ${s.bay}: ${s.bins.length} bin, ${isi}%, ${rinci}`
				)}"><i style="height:${isi}%"></i></div>`).appendTo($bays);
			});
			$bays.prependTo($el);
		});
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
			`<div class="wl-muted">${__("Klik satu kotak untuk melihat isinya. Menu Tambah Kotak untuk staging area, pintu, atau kantor.")}</div>`
		);
	}

	function pct(used, capacity) {
		return capacity > 0 ? Math.min(100, Math.round((used / capacity) * 100)) : 0;
	}

	function drawRack(rack) {
		const kind = rack.kind || "Rak";
		const holdsStock = kind === "Rak" || kind === "Staging";
		const p = holdsStock ? pct(rack.used, rack.capacity) : 0;
		const band = p >= 85 ? "wl-hi" : p >= 50 ? "wl-mid" : "wl-lo";
		// pintu & kantor tidak punya isi, jadi yang ditulis jenisnya saja
		// ukurannya ikut ditulis di kotak: denah ini memang gambar berskala, bukan diagram
		const ukuran = rack.w && rack.h ? `${fmtM(rack.w)} x ${fmtM(rack.h)} m` : "";
		const sub = [holdsStock ? `${rack.bins} ${__("bin")}, ${p}%` : __(kind), ukuran]
			.filter(Boolean)
			.join(" · ");
		const $el = $(`
			<div class="wl-rack wl-k-${kind} ${band} ${rack.disabled ? "wl-off" : ""}">
				<div class="wl-fill" style="height:${p}%"></div>
				<div class="wl-code" style="position:relative">${frappe.utils.escape_html(rack.rack_code)}</div>
				<div class="wl-sub" style="position:relative">${sub}</div>
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
				$el.find(".wl-sub").text(`${fmtM(rack.w)} x ${fmtM(rack.h)} m`);
				if (state.selected === rack) showRack(rack);
			}
		});

		$el.on("pointerup pointercancel", (e) => {
			if (!mode) return;
			mode = null;
			$el[0].releasePointerCapture(e.pointerId);
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
			if (rack.w && rack.h) $el.find(".wl-sub").text(`${fmtM(rack.w)} x ${fmtM(rack.h)} m`);
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

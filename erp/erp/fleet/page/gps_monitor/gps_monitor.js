// GPS Vehicle: peta posisi unit + tabel Branch | Nopol | Status | Job | Notifikasi.
// Klik branch = filter peta + 4 tabel lain. Auto-refresh 60 detik (posisi/zoom peta tidak ter-reset).
frappe.pages['gps-monitor'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('GPS Vehicle'),
		single_column: true,
	});

	// tabel data: 1 kolom masing-masing, baris sejajar antar tabel
	const COLS = [
		// driver hanya terisi kalau sudah absen hari ini (lihat get_rows), jadi cukup disaring Boolean
		{ key: 'nopol', label: __('Nopol'), parts: ['branch_code', 'nopol', 'driver'], sep: ' - ', width: '235px' },
		// 150px: badge terpanjang ("Moving No Job", "Offline Active") harus muat satu baris
		{ key: 'status', label: __('Status'), width: '150px' },
		{ key: 'job', label: __('Job'), parts: ['packing_list', 'job', 'route'], sep: ' &middot; ' }, // PL - DPO - rute
		{ key: 'note', label: __('Notifikasi') },
		{ key: 'last_note', label: __('Note') }, // note terakhir unit itu, 1 baris
	];

	const $body = $(`
		<div class="gm">
			<style>
				/* tinggi .gm dipatok fit_tables; isinya flex column supaya tabel mengambil sisa
				   ruang dan discroll di dalam dirinya sendiri, bukan memanjangkan halaman */
				.gm { padding: 8px 0; display: flex; flex-direction: column; overflow: hidden; }
				/* z-index:0 = stacking context sendiri, pane Leaflet tidak menimpa header halaman */
				.gm-map-wrap { position: relative; z-index: 0; flex: 0 0 auto; }
				/* satu baris kendali melayang di bawah peta: branch, status, absensi, suara */
				.gm-bar { position: absolute; left: 8px; right: 8px; bottom: 8px; z-index: 500;
					display: flex; flex-wrap: nowrap; align-items: center; gap: 12px; pointer-events: none; }
				.gm-bar > div { display: flex; flex-wrap: nowrap; gap: 6px; align-items: center; min-width: 0; }
				/* kiri & kanan sama-sama flex:1 -> sisa ruangnya terbagi rata, jadi kelompok
				   status di tengah benar-benar center walau lebar kedua sisinya berbeda */
				.gm-branches { flex: 1 1 0; justify-content: flex-start; }
				.gm-status { flex: 0 1 auto; justify-content: center; }
				.gm-extra { flex: 1 1 0; justify-content: flex-end; }
				.gm-bar .gm-sbtn { white-space: nowrap; }
				.gm-bar .gm-sbtn { pointer-events: auto; border: 1px solid rgba(0,0,0,.18); border-radius: 14px;
					padding: 2px 10px; font-size: 11px; font-weight: 600; line-height: 16px;
					background: rgba(255,255,255,.94); color: #111; box-shadow: 0 1px 4px rgba(0,0,0,.3); }
				.gm-bar .gm-sbtn b { font-weight: 700; opacity: .75; }
				/* branch & absensi aktif = terisi biru; status aktif = digaris biru supaya
				   warna badge status itu sendiri tidak hilang */
				.gm-branches .gm-sbtn.gm-on, .gm-extra .gm-sbtn.gm-on { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
				.gm-status .gm-sbtn.gm-on { box-shadow: 0 0 0 2px #1d4ed8, 0 1px 4px rgba(0,0,0,.3); }
				.gm-sound { pointer-events: auto; width: 28px; height: 28px; flex: 0 0 28px;
					border: 1px solid rgba(0,0,0,.18); border-radius: 50%; background: rgba(255,255,255,.94);
					display: flex; align-items: center; justify-content: center; padding: 0;
					box-shadow: 0 1px 4px rgba(0,0,0,.3); color: var(--text-muted); }
				.gm-sound.gm-on { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
				.gm-sound svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 1.8;
					stroke-linecap: round; stroke-linejoin: round; }
				.gm-full { background: var(--bg-color, #fff); overflow: auto; padding: 0 16px; }
				.gm-full .gm-map { height: 68vh; }
				.gm-map { height: 62vh; min-height: 340px; border-radius: 8px; border: 1px solid var(--border-color); }
				.gm-drag { flex: 0 0 12px; height: 12px; cursor: row-resize; display: flex; align-items: center; justify-content: center; }
				.gm-drag span { width: 60px; height: 4px; border-radius: 2px; background: var(--border-color, #d1d5db); }
				.gm-drag:hover span { background: #1d4ed8; }
				.gm-tables { display: flex; gap: 8px; align-items: stretch; flex: 1 1 auto; min-height: 0; }
				.gm-col { flex: 1 1 0; min-width: 0; min-height: 0; border: 1px solid var(--border-color); border-radius: 8px;
					display: flex; flex-direction: column; }
				.gm-col.gm-branch { flex: 0 0 180px; }
				.gm-col h6 { margin: 0; padding: 5px 8px; font-size: 11px; font-weight: 600;
					background: var(--bg-light-gray, #f3f4f6); border-bottom: 1px solid var(--border-color); border-radius: 8px 8px 0 0; }
				/* isi tabel memanjang ke bawah dan discroll sendiri, tidak mendorong peta */
				.gm-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
				.gm-cell { height: 29px; padding: 0 8px; font-size: 12px; border-bottom: 1px solid var(--border-color);
					cursor: pointer; display: flex; flex-direction: column; justify-content: center; }
				.gm-cell:last-child { border-bottom: none; }
				.gm-cell .gm-main { line-height: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.gm-cell .gm-sub { font-size: 10px; line-height: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.gm-cell.gm-on { background: var(--highlight-color, #eef2ff); }
				.gm-pill { padding: 0 7px; border-radius: 9px; font-size: 11px; font-weight: 600; align-self: flex-start; }
				.gm-count { float: right; color: var(--text-muted); font-weight: 400; }
				/* penanda note: dibuat saat ada job (No DPO) atau tidak */
				.gm-tag { display: inline-block; font-size: 10px; font-weight: 700; padding: 0 6px; border-radius: 8px; }
				.gm-tag-job { background: #dbeafe; color: #1e40af; }
				.gm-tag-idle { background: var(--bg-light-gray, #f3f4f6); color: var(--text-muted); }
				.gm-empty { padding: 12px; color: var(--text-muted); font-size: 13.5px; }
				/* label nopol kecil di atas ikon truk */
				.leaflet-tooltip.gm-plate { background: #000; color: #fff; border: none; box-shadow: none;
					font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
				.leaflet-tooltip.gm-plate:before { display: none; }
				/* kartu detail di popup peta */
				.leaflet-popup-content { margin: 10px 12px; width: 580px !important; }
				.gm-pop-wrap { display: flex; gap: 12px; align-items: stretch; }
				.gm-pop-wrap > .gm-pop { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; }
				.gm-pop-wrap > .gm-pop dl { flex: 1 1 auto; align-content: start; }
				.gm-route { flex: 0 0 235px; border-left: 1px solid var(--border-color); padding-left: 12px;
					display: flex; flex-direction: column; }
				.gm-route h6 { font-size: 11px; font-weight: 700; color: #374151; text-transform: uppercase;
					letter-spacing: .03em; margin: 0 0 6px; }
				/* nomor ditulis manual di teksnya supaya selalu ikut terbawa & tidak terpotong */
				.gm-route ol { margin: 0; padding-left: 0; list-style: none; flex: 1 1 auto; overflow-y: auto; min-height: 0; }
				.gm-route li .gm-num { font-weight: 700; color: #374151; }
				.gm-route li { font-size: 12.5px; line-height: 16px; margin-bottom: 5px;
					white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.gm-route li.gm-done { color: #16a34a; font-weight: 600; }
				.gm-route .gm-cur { background: #1d4ed8; color: #fff; font-weight: 700; padding: 1px 6px; border-radius: 9px; }
				/* lebar kolom dipatok muat "05 Agu 26 18:00 - 05 Agu 26 18:00"; nama titik ikut dipotong di lebar itu */
				.gm-route .gm-range { display: block; padding-left: 17px; font-size: 11.5px; color: #374151;
					white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.gm-route .gm-none { font-size: 13px; color: var(--text-muted); flex: 1 1 auto; }
				.gm-route .gm-act { border-top: 1px solid var(--border-color); margin-top: 8px; padding-top: 8px;
					display: flex; gap: 6px; }
				.gm-pop .gm-pop-do { font-size: 15px; font-weight: 700; line-height: 18px; }
				.gm-pop .gm-pop-route { font-size: 12.5px; font-weight: 600; color: #374151; margin-bottom: 8px; }
				.gm-pop dl { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 10px; margin: 0 0 8px; }
				.gm-pop dl > div { min-width: 0; }
				.gm-pop dt { font-size: 11px; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: .03em; }
				.gm-pop dd { margin: 0; font-size: 13.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.gm-pop .gm-move { border-top: 1px solid var(--border-color); padding-top: 6px; font-size: 12.5px; color: #374151; font-weight: 500; }
				.gm-pop .gm-act { display: flex; gap: 6px; border-top: 1px solid var(--border-color); margin-top: 8px; padding-top: 8px; }
				/* tombol kiri & kanan disamakan tinggi/ukurannya */
				.gm-pop .gm-act .btn, .gm-route .gm-act .btn { flex: 1 1 0; font-size: 12.5px; padding: 5px 6px; line-height: 16px; }
			</style>
			<div class="gm-map-wrap"><div class="gm-map"></div><div class="gm-bar"><div class="gm-branches"></div><div class="gm-status"></div><div class="gm-extra"><button class="gm-sbtn gm-absen"></button><button class="gm-sbtn gm-job"></button><button class="gm-sound"></button></div></div></div>
			<div class="gm-drag" title="${__('Geser untuk mengatur tinggi peta')}"><span></span></div>
			<div class="gm-tables"></div>
		</div>
	`).appendTo(page.body);

	page.set_secondary_action(__('Refresh'), load);

	// fullscreen: seluruh panel (peta + tabel) memakai layar penuh, tombol Back untuk keluar
	const $full = $(`<button class="btn btn-default btn-xs" style="margin-right:8px">${__('Fullscreen')}</button>`);
	const $back = $(`<button class="btn btn-default btn-xs" style="margin-right:8px;display:none">${__('Back')}</button>`);
	page.page_actions.prepend($back).prepend($full);

	// GPS Monitoring punya HALAMAN SENDIRI (erp/fleet/page/gps_monitoring) supaya tata
	// letak dindingnya bebas diubah tanpa menyentuh tampilan halaman ini.
	const $idle = $('<button class="btn btn-default btn-xs" style="margin-right:8px">' +
		__('GPS Monitoring') + '</button>');
	page.page_actions.prepend($idle);
	$idle.on('click', () => frappe.set_route('gps-monitoring'));
	// fullscreen dipasang di wrapper halaman supaya header + tombol Back ikut kelihatan
	$full.on('click', () => wrapper.requestFullscreen && wrapper.requestFullscreen());
	$back.on('click', () => document.exitFullscreen && document.exitFullscreen());
	$(document).on('fullscreenchange.gm', () => {
		const on = document.fullscreenElement === wrapper;
		$full.toggle(!on);
		$back.toggle(on);
		$(wrapper).toggleClass('gm-full', on);
		setTimeout(() => {
			map.invalidateSize();
			fit_tables();
		}, 200);
	});
	$(window).on('resize.gm', () => fit_tables());
	$(wrapper).on('remove', () => {
		$(document).off('fullscreenchange.gm');
		$(window).off('resize.gm');
	});

	const $map = $body.find('.gm-map');
	const map = L.map($map[0], { attributionControl: false }).setView([-2.5, 118], 5);
	// basemap jalan (OSM, keyless) + opsi satelit; CARTO dilepas karena minta API key
	const jalan = L.tileLayer('/tiles/{z}/{x}/{y}.png', {
		attribution: '&copy; OpenStreetMap',
		subdomains: 'abcd',
		maxZoom: 19,
	}).addTo(map);
	const satelit = L.layerGroup([
		L.tileLayer(
			'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
			{ attribution: '&copy; Esri', maxZoom: 19 }
		),
		L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
			subdomains: 'abcd',
			maxZoom: 19,
		}),
	]);
	L.control.layers({ [__('Peta')]: jalan, [__('Satelit')]: satelit }, {}, { position: 'topright' }).addTo(map);
	// kontainer masih 0px saat map dibuat -> tile abu-abu sampai invalidateSize dipanggil
	new ResizeObserver(() => $map[0].offsetWidth && map.invalidateSize()).observe($map[0]);

	const esc = frappe.utils.escape_html;
	// Palet datang dari server (erp/fleet/vehicle_status.py) supaya status baru tidak perlu
	// didaftarkan ulang di tiap halaman.
	let STATUS_STYLE = {};
	const TRUCK = L.icon({
		iconUrl: '/assets/erp/images/truck.png',
		iconSize: [50, 50],
		iconAnchor: [25, 25],
		popupAnchor: [0, -20],
	});
	// Warna pin mengikuti warna badge status (dipetakan server di vehicle_status.COLOR_ICON).
	// L.icon di-cache per url: satu instance dipakai bersama semua marker sewarna.
	let STATUS_ICON = {};
	const icon_cache = {};
	function truck_icon(status) {
		const url = STATUS_ICON[status];
		if (!url) return TRUCK;
		if (!icon_cache[url]) {
			icon_cache[url] = L.icon({
				iconUrl: url,
				iconSize: [50, 50],
				iconAnchor: [25, 25],
				popupAnchor: [0, -20],
			});
		}
		return icon_cache[url];
	}
	let markers = {};
	let details = {}; // cache detail popup per unit, dibuang tiap refresh data
	let fitted = false;
	let data = { branches: [], rows: [] };
	let branch = ''; // '' = All
	let status = ''; // '' = All, diklik dari tombol status di atas peta
	let absen_only = false; // tombol Absensi: hanya unit yang drivernya sudah absen hari ini
	let job_only = false; // tombol Job: hanya unit yang sedang punya job ter-assign
	let query = '';

	// pencarian: nopol, origin/destination, no DPO, no packing list
	const SEARCH_KEYS = ['nopol', 'route', 'job', 'packing_list'];
	// all_status / all_branch: dipakai tombol filter supaya cacahnya tetap terlihat
	// walau filter yang bersangkutan sedang aktif
	const filtered = (opts) =>
		data.rows.filter(
			(r) =>
				((opts && opts.all_branch) || !branch || r.branch === branch) &&
				((opts && opts.all_status) || !status || r.status === status) &&
				((opts && opts.all_absen) || !absen_only || r.absen) &&
				((opts && opts.all_job) || !job_only || r.job) &&
				(!query || SEARCH_KEYS.some((k) => String(r[k] || '').toLowerCase().includes(query)))
		);
	const visible = () => filtered();

	const $search = $(
		`<input type="text" class="form-control input-xs" style="width:250px;display:inline-block;margin-right:8px"
			placeholder="${__('Cari nopol / DPO / PL / origin / destination')}">`
	);
	page.page_actions.prepend($search);
	$search.on(
		'input',
		frappe.utils.debounce(function () {
			query = String($(this).val() || '').trim().toLowerCase();
			fitted = false; // hasil pencarian ikut diarahkan di peta
			paint_map();
			paint_tables();
		}, 250)
	);

	const dt = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 19)) : '-');

	// "01 Des 26 18:00 - 23:59" (sehari), "01 Des 26 18:00 - 02 Des 26 01:00" (beda hari),
	// "01 Des 26 18:00 - On Going" (baru IN), "-" (belum ada dua-duanya)
	const BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
	const tgl = (s) => {
		const [d, m, y] = [s.slice(8, 10), Number(s.slice(5, 7)) - 1, s.slice(2, 4)];
		return `${d} ${BULAN[m]} ${y}`;
	};
	const jam = (s) => s.slice(11, 16);
	function in_out(a, b) {
		if (!a && !b) return '-';
		if (a && !b) return `${tgl(a)} ${jam(a)} - ${__('On Going')}`;
		if (!a && b) return `? - ${tgl(b)} ${jam(b)}`;
		return a.slice(0, 10) === b.slice(0, 10)
			? `${tgl(a)} ${jam(a)} - ${jam(b)}`
			: `${tgl(a)} ${jam(a)} - ${tgl(b)} ${jam(b)}`;
	}

	function route_html(r, det) {
		if (!det) {
			return `<div class="gm-route"><h6>${__('Route Assigned')}</h6>
				<div class="gm-none">${__('Memuat...')}</div></div>`;
		}
		const pts = det.route_points || [];
		// titik yang sedang dikerjakan = titik pertama yang OUT-nya belum keluar
		const cur = pts.findIndex((p) => !p.end);
		const list = pts.length
			? `<ol>${pts
					.map((p, i) => {
						const nama = i === cur ? `<span class="gm-cur">${esc(p.point)}</span>` : esc(p.point);
						const rentang = in_out(p.start, p.end);
						return `<li class="${p.end ? 'gm-done' : ''}" title="${i + 1}. ${esc(p.point)} ${rentang}">
							<span class="gm-num">${i + 1}.</span> ${nama}
							<span class="gm-range">${rentang}</span></li>`;
					})
					.join('')}</ol>`
			: `<div class="gm-none">${r.dpo ? __('Belum ada titik rute.') : __('Tidak ada job aktif.')}</div>`;
		return `<div class="gm-route">
			<h6>${__('Route Assigned')}${pts.length ? ` (${pts.length})` : ''}</h6>
			${list}
			<div class="gm-act">
				<button class="btn btn-default btn-xs gm-play" ${det.dpo_item ? '' : 'disabled'}>${__('Playback')}</button>
				<button class="btn btn-default btn-xs gm-show" ${pts.length ? '' : 'disabled'}>${__('Show Route')}</button>
			</div>
		</div>`;
	}

	function popup_html(r, det) {
		const pair = (label, val) => `<div><dt>${label}</dt><dd title="${esc(val || '')}">${esc(val || '-')}</dd></div>`;
		const badge = `<span class="gm-pill" style="${STATUS_STYLE[r.status] || ''}">${esc(r.status)}</span>`;
		const hijau = (v) =>
			v ? `<span class="gm-pill" style="background:#dcfce7;color:#166534">${esc(v)}</span>` : '-';
		return `<div class="gm-pop-wrap"><div class="gm-pop" data-name="${esc(r.name)}">
			<div class="gm-pop-do">${esc(r.job || r.nopol)}</div>
			${r.route ? `<div class="gm-pop-route">${esc(r.route)}</div>` : '<div style="height:6px"></div>'}
			<dl>
				<div><dt>${__('Nopol')}</dt><dd>${hijau(r.nopol)}</dd></div>
				<div><dt>${__('Driver')}</dt><dd>${hijau(r.driver || (det && det.job_driver))}</dd></div>
				${pair(__('Packing List'), r.packing_list)}${pair(__('Customer'), det ? det.customer : '...')}
				${pair(__('Container No'), det ? det.container_no : '...')}<div></div>
				${pair(__('Assign Date'), det ? dt(det.assign_at) : '...')}${pair(__('ATD'), det ? dt(det.atd) : '...')}
				<div><dt>${__('Status')}</dt><dd>${badge}</dd></div><div></div>
			</dl>
			<div class="gm-move">${__('Last Moving')}: ${dt(r.last_moving)} &middot; ${esc(r.note)}</div>
			<div class="gm-act">
				<button class="btn btn-default btn-xs gm-note">${__('Note')}</button>
				<button class="btn btn-primary btn-xs gm-check" ${r.dpo ? '' : 'disabled'}>${__('Show Dispatch')}</button>
			</div>
		</div>${route_html(r, det)}</div>`;
	}

	function paint_map() {
		const rows = visible();
		const bounds = [];
		for (const r of rows) {
			if (!r.latitude || !r.longitude) continue;
			const pos = [r.latitude, r.longitude];
			bounds.push(pos);
			const label = popup_html(r);
			if (markers[r.name])
				markers[r.name].setLatLng(pos).setPopupContent(label).setIcon(truck_icon(r.status));
			else
				markers[r.name] = L.marker(pos, { icon: truck_icon(r.status) })
					.addTo(map)
					.bindPopup(label, { autoPan: true, autoPanPadding: [30, 50], keepInView: true })
					.bindTooltip(esc(r.nopol), {
						permanent: true,
						direction: 'top',
						offset: [0, -22],
						className: 'gm-plate',
					});
		}
		for (const name of Object.keys(markers)) {
			if (!rows.find((r) => r.name === name && r.latitude && r.longitude)) {
				map.removeLayer(markers[name]);
				delete markers[name];
			}
		}
		if (bounds.length && !fitted) {
			map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
			fitted = true;
		}
	}

	function cell(main, sub, i) {
		return `<div class="gm-cell" data-i="${i}" title="${esc(sub || main || '')}">
			<div class="gm-main">${main || '-'}</div>
			${sub ? `<div class="gm-sub">${esc(sub)}</div>` : ''}
		</div>`;
	}

	// seluruh panel dipatok setinggi sisa layar; peta tetap setinggi aslinya, tabel mengambil
	// sisanya dan discroll sendiri -- halaman tidak ikut memanjang ke bawah
	function fit_tables() {
		if (!$body.is(':visible')) return;
		const top = $body.offset().top - $(window).scrollTop();
		$body.css('height', Math.max(window.innerHeight - top - 10, 320) + 'px');
	}

	const fbtn = (label, key, n, style, on) =>
		`<button class="gm-sbtn ${on ? 'gm-on' : ''}" data-key="${esc(key)}" style="${style || ''}">${esc(label)} <b>${n}</b></button>`;

	// tombol branch melayang di peta (rata kiri, di atas baris status)
	function paint_branches() {
		const rows = filtered({ all_branch: true });
		const $b = $body.find('.gm-branches').empty();
		// All BUKAN salah satu pilihan branch: dia membersihkan SEMUA filter (branch, status,
		// absensi, pencarian). Cacahnya pun total mentah, bukan hasil saringan.
		const bersih = !branch && !status && !absen_only && !query;
		$b.append(
			`<button class="gm-sbtn gm-all ${bersih ? 'gm-on' : ''}">${__('All')} <b>${data.rows.length}</b></button>`
		);
		data.branches
			.filter((x) => x.name) // entri "All" bawaan server dilewati, All di sini beda arti
			.forEach((x) =>
				$b.append(fbtn(x.label, x.name, rows.filter((r) => r.branch === x.name).length, '', x.name === branch))
			);
		$b.find('.gm-all').on('click', () => {
			branch = status = query = '';
			absen_only = false;
			$search.val('');
			fitted = false;
			paint_map();
			paint_tables();
		});
		$b.find('.gm-sbtn:not(.gm-all)').on('click', function () {
			const v = $(this).data('key') || '';
			branch = branch === v ? '' : v;
			fitted = false;
			paint_map();
			paint_tables();
		});
	}

	// tombol Absensi: saring unit yang drivernya sudah absen hari ini
	function paint_absen() {
		const n = filtered({ all_absen: true }).filter((r) => r.absen).length;
		$body
			.find('.gm-absen')
			.toggleClass('gm-on', absen_only)
			.attr('title', __('Hanya unit yang drivernya sudah absen hari ini'))
			.html(`${__('Absensi')} <b>${n}</b>`);
	}

	// tombol Job: saring unit yang sedang membawa job (item DPO ter-assign)
	function paint_job() {
		const n = filtered({ all_job: true }).filter((r) => r.job).length;
		$body
			.find('.gm-job')
			.toggleClass('gm-on', job_only)
			.attr('title', __('Hanya unit yang sedang punya job ter-assign'))
			.html(`${__('Job')} <b>${n}</b>`);
	}

	// tombol status melayang di bawah peta: klik = filter, klik lagi = lepas
	function paint_status() {
		const rows = filtered({ all_status: true });
		const count = {};
		rows.forEach((r) => (count[r.status] = (count[r.status] || 0) + 1));
		const $s = $body.find('.gm-status').empty();
		Object.keys(count)
			.sort()
			.forEach((k) => $s.append(fbtn(k, k, count[k], STATUS_STYLE[k], k === status)));
		$s.find('.gm-sbtn').on('click', function () {
			const v = $(this).data('key') || '';
			status = status === v ? '' : v;
			fitted = false; // ganti filter = peta ikut menyesuaikan
			paint_map();
			paint_tables();
		});
	}

	function paint_tables() {
		const rows = visible();
		paint_branches();
		paint_status();
		paint_absen();
		paint_job();
		const $t = $body.find('.gm-tables').empty();

		for (const col of COLS) {
			const $c = $(`<div class="gm-col"><h6>${col.label}</h6><div class="gm-scroll"></div></div>`).appendTo($t);
			if (col.width) $c.css('flex', `0 0 ${col.width}`);
			if (!rows.length) {
				$c.find('.gm-scroll').append(`<div class="gm-empty">${__('Tidak ada unit.')}</div>`);
				continue;
			}
			rows.forEach((r, i) => {
				let main;
				if (col.key === 'status') {
					main = `<span class="gm-pill" style="${STATUS_STYLE[r.status] || ''}">${esc(r.status)}</span>`;
				} else if (col.join || col.parts) {
					const parts = (col.parts || [col.key, col.join]).map((k) => r[k]).filter(Boolean).map(esc);
					main = parts.length ? parts.join(col.sep) : '-';
				} else {
					main = esc(r[col.key] || '-');
				}
				$c.find('.gm-scroll').append(cell(main, col.sub ? r[col.sub] : '', i));
			});
		}

		$t.find('.gm-col .gm-cell').on('click', function () {
			focus_vehicle(rows[$(this).data('i')].name);
		});

		fit_tables();
	}

	// Playback: jejak GPS per menit sejak job mulai. History-nya BARU diambil saat tombol ditekan.
	// Sorot satu unit: tandai barisnya di tabel, geser peta, buka popupnya.
	// Dipakai klik tabel dan putaran Auto supaya perilakunya persis sama.
	function focus_vehicle(name) {
		const rows = visible();
		const i = rows.findIndex((x) => x.name === name);
		const r = rows[i];
		if (!r) return;
		const $t = $body.find('.gm-tables');
		$t.find('.gm-col:not(.gm-branch) .gm-cell').removeClass('gm-on');
		const $cells = $t.find(`.gm-col:not(.gm-branch) .gm-cell[data-i="${i}"]`).addClass('gm-on');
		const $first = $cells.first();
		if ($first.length) {
			// bawa baris yang sedang disorot ke area yang kelihatan
			const $sc = $first.closest('.gm-scroll');
			$sc.length && $sc.scrollTop($sc.scrollTop() + $first.position().top - 40);
		}
		if (r.latitude && r.longitude) {
			map.setView([r.latitude, r.longitude], Math.max(map.getZoom(), 13));
			markers[r.name] && markers[r.name].openPopup();
		}
	}

	function show_playback(r, det) {
		frappe
			.call('erp.fleet.doctype.dispatch_order.dispatch_order.get_route_history', {
				dpo_item: det && det.dpo_item,
				trip: (det && det.trip) || 1,
			})
			.then((res) => {
				const pts = res.message || [];
				if (!pts.length) {
					frappe.msgprint(__('Belum ada history perjalanan untuk {0}.', [r.nopol]));
					return;
				}
				const d = new frappe.ui.Dialog({
					title: __('Playback {0} — {1}', [r.nopol, r.job || '-']),
					size: 'extra-large',
					fields: [{ fieldtype: 'HTML', fieldname: 'map' }],
				});
				d.show();
				setTimeout(() => {
					const $w = d.get_field('map').$wrapper;
					$w.html(`
						<div class="gm-play-map border rounded" style="height:460px"></div>
						<div style="margin-top:8px;display:flex;gap:10px;align-items:center;">
							<button class="btn btn-sm btn-primary gm-play-btn">${__('Play')}</button>
							<input type="range" class="gm-play-slider" min="0" max="${pts.length - 1}" value="0" style="flex:1">
							<span class="gm-play-info text-muted" style="min-width:230px;font-size:12px"></span>
						</div>`);
					const pmap = L.map($w.find('.gm-play-map')[0], { attributionControl: false }).setView([-2.5, 118], 5);
					L.tileLayer('/tiles/{z}/{x}/{y}.png', {
						attribution: '&copy; OpenStreetMap',
						subdomains: 'abcd',
						maxZoom: 19,
					}).addTo(pmap);
					const latlngs = pts.map((p) => [p.latitude, p.longitude]);
					// rute yang di-assign ikut digambar sebagai acuan
					const rpts = ((det && det.route_points) || []).filter((p) => p.latitude && p.longitude);
					if (rpts.length) route_group(rpts).addTo(pmap);
					const line = L.polyline(latlngs, { color: '#dc2626', weight: 3, opacity: 0.7 }).addTo(pmap);
					L.marker(latlngs[0], { icon: num_icon('S', '#16a34a') })
						.addTo(pmap)
						.bindTooltip(__('Start: {0}', [pts[0].recorded_at]));
					L.marker(latlngs[latlngs.length - 1], { icon: num_icon('E', '#dc2626') })
						.addTo(pmap)
						.bindTooltip(__('End: {0}', [pts[pts.length - 1].recorded_at]));
					const mover = L.marker(latlngs[0], { zIndexOffset: 1000, icon: TRUCK }).addTo(pmap);
					pmap.fitBounds(line.getBounds().pad(0.2));
					setTimeout(() => pmap.invalidateSize(), 300);

					const $info = $w.find('.gm-play-info');
					const $slider = $w.find('.gm-play-slider');
					const $btn = $w.find('.gm-play-btn');
					let idx = 0,
						timer = null;
					const show = (i) => {
						idx = i;
						mover.setLatLng(latlngs[i]);
						pmap.panTo(latlngs[i]);
						$slider.val(i);
						$info.text(`${i + 1}/${pts.length}  ${pts[i].recorded_at}`);
					};
					const stop = () => {
						timer && clearInterval(timer);
						timer = null;
						$btn.text(__('Play'));
					};
					$btn.on('click', () => {
						if (timer) return stop();
						if (idx >= pts.length - 1) idx = 0;
						$btn.text(__('Pause'));
						timer = setInterval(() => (idx >= pts.length - 1 ? stop() : show(idx + 1)), 200);
					});
					$slider.on('input', function () {
						stop();
						show(Number(this.value));
					});
					show(0);
					d.$wrapper.on('hidden.bs.modal', () => {
						stop();
						pmap.remove();
					});
				}, 300);
			});
	}

	// Note -> doctype Monitoring Notes. Dari unit: nopol/driver/DPO/status ikut terisi.
	// Dari pin peta: hanya koordinat, status sengaja dikosongkan.
	function note_dialog(payload, judul, pick_unit) {
		const fields = [
			{ fieldtype: 'HTML', options: `<div style="font-weight:700;margin-bottom:6px">${__('Note Anda')}</div>` },
		];
		if (pick_unit) {
			// pilih unit: label "nopol — driver", nilainya nama Vehicle; kolom lain diisi server
			fields.push({
				fieldname: 'vehicle',
				fieldtype: 'Select',
				label: __('Nopol - Driver'),
				options: [{ label: __('(tanpa unit)'), value: '' }].concat(
					data.rows.map((r) => ({
						label: `${r.nopol}${r.driver ? ' - ' + r.driver : ''}`,
						value: r.name,
					}))
				),
			});
		}
		fields.push(
			{ fieldname: 'note_date', fieldtype: 'Datetime', label: __('Note Date'), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldname: 'note', fieldtype: 'Small Text', label: __('Note Anda'), reqd: 1 },
			{
				fieldname: 'suspend',
				fieldtype: 'Check',
				label: __('Suspend'),
				description: __('Unit sedang bermasalah. Status jadi Suspend sampai ada note baru tanpa centang ini.'),
			},
			{ fieldtype: 'Column Break' },
			{ fieldtype: 'HTML', fieldname: 'history' }
		);
		const d = new frappe.ui.Dialog({
			title: judul,
			size: 'large',
			fields: fields,
			primary_action_label: __('Submit'),
			secondary_action_label: __('Cancel'),
			secondary_action: () => d.hide(),
			primary_action: (v) => {
				frappe
					.call('erp.fleet.page.gps_monitor.gps_monitor.add_note', {
						...payload,
						vehicle: v.vehicle || payload.vehicle || null,
						note_date: v.note_date,
						note: v.note,
						suspend: v.suspend ? 1 : 0,
					})
					.then((res) => {
						d.hide();
						frappe.show_alert({ message: __('Note tersimpan: {0}', [res.message]), indicator: 'green' });
					});
			},
		});
		d.show();

		// kolom kanan: history note untuk job (atau unit) yang sama
		const load_history = (vehicle) => {
			const $h = d.get_field('history').$wrapper;
			const head = `<div style="font-weight:700;margin-bottom:6px">${__('Notes')}</div>`;
			$h.html(`${head}<div class="text-muted" style="font-size:12px">${__('Memuat...')}</div>`);
			frappe
				.call('erp.fleet.page.gps_monitor.gps_monitor.get_notes', {
					dpo_no: payload.dpo_no || '',
					vehicle: vehicle || payload.vehicle || '',
				})
				.then((res) => {
					const rows = res.message || [];
					const isi = rows.length
						? rows
								.map(
									(n) => `<div style="border-bottom:1px solid var(--border-color);padding:6px 0">
										<div style="font-size:11px;font-weight:700;color:#374151">${dt(n.note_date)}${
										n.nopol ? ' &middot; ' + esc(n.nopol) : ''
									}</div>
										<div style="font-size:12.5px">${esc(n.note)}</div>
										<div style="font-size:10.5px;color:var(--text-muted)">${esc(n.owner)}
											${
												n.dpo_no
													? `<span class="gm-tag gm-tag-job">${esc(n.dpo_no)}</span>`
													: `<span class="gm-tag gm-tag-idle">${__('Tanpa job')}</span>`
											}</div>
									</div>`
								)
								.join('')
						: `<div class="text-muted" style="font-size:12px">${__('Belum ada note.')}</div>`;
					$h.html(`${head}<div style="max-height:260px;overflow-y:auto">${isi}</div>`);
				});
		};
		load_history();
		if (pick_unit) d.fields_dict.vehicle.$input.on('change', (e) => load_history($(e.target).val()));
	}

	const note_on_vehicle = (r, det) =>
		note_dialog(
			{
				vehicle: r.name,
				nopol: r.nopol,
				driver: r.driver || (det && det.job_driver),
				dpo_no: r.job,
				status: r.status,
				latitude: r.latitude,
				longitude: r.longitude,
			},
			__('Note {0}', [r.nopol])
		);

	// tombol pin di peta: sekali klik -> klik titik di peta -> kotak note (status kosong)
	let pinning = false;
	const PinControl = L.Control.extend({
		options: { position: 'topleft' },
		onAdd() {
			const el = L.DomUtil.create('div', 'leaflet-bar');
			el.innerHTML = `<a href="#" title="${__('Pin Note')}"><img src="/assets/erp/images/flag.png"
				style="width:18px;height:18px;margin:4px 0;vertical-align:middle"></a>`;
			L.DomEvent.on(el, 'click', (ev) => {
				L.DomEvent.stop(ev);
				pinning = !pinning;
				$(el).find('a').css('background', pinning ? '#dbeafe' : '');
				$map.css('cursor', pinning ? 'crosshair' : '');
			});
			return el;
		},
	});
	map.addControl(new PinControl());

	// tombol di bawah pin: hapus rute yang sedang tampil di peta
	const ClearControl = L.Control.extend({
		options: { position: 'topleft' },
		onAdd() {
			const el = L.DomUtil.create('div', 'leaflet-bar');
			el.innerHTML = `<a href="#" title="${__('Clear Route')}"><img src="/assets/erp/images/clear.png"
				style="width:18px;height:18px;margin:4px 0;vertical-align:middle"></a>`;
			L.DomEvent.on(el, 'click', (ev) => {
				L.DomEvent.stop(ev);
				clear_route();
			});
			return el;
		},
	});
	map.addControl(new ClearControl());
	map.on('click', (e) => {
		if (!pinning) return;
		pinning = false;
		$map.css('cursor', '');
		$('.leaflet-bar a[title]').css('background', '');
		note_dialog({ latitude: e.latlng.lat, longitude: e.latlng.lng }, __('Note Titik Peta'), true);
	});

	// garis rute di peta utama, hanya digambar kalau tombol Show Route ditekan
	let route_layer = null;
	function clear_route() {
		if (route_layer) {
			map.removeLayer(route_layer);
			route_layer = null;
		}
	}

	// selalu bersihkan rute lama dulu supaya tidak dobel; rute TETAP tampil walau popup ditutup
	function show_route(det) {
		clear_route();
		const pts = ((det && det.route_points) || []).filter((p) => p.latitude && p.longitude);
		if (!pts.length) {
			frappe.show_alert({ message: __('Titik rute belum punya koordinat.'), indicator: 'orange' });
			return;
		}
		route_layer = route_group(pts).addTo(map);
		map.fitBounds(L.polyline(pts.map((p) => [p.latitude, p.longitude])).getBounds().pad(0.25));
	}

	// garis putus-putus + pin bernomor titik rute (hijau = sudah OUT)
	const route_group = (pts) =>
		L.layerGroup([
			L.polyline(
				pts.map((p) => [p.latitude, p.longitude]),
				{ color: '#1d4ed8', weight: 3, opacity: 0.7, dashArray: '6 6' }
			),
			...pts.map((p, i) =>
				L.marker([p.latitude, p.longitude], {
					icon: num_icon(i + 1, p.end ? '#16a34a' : '#1d4ed8'),
				}).bindTooltip(`${i + 1}. ${p.point}`)
			),
		]);

	const num_icon = (n, bg) =>
		L.divIcon({
			className: '',
			html: `<div style="width:22px;height:22px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;
				box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;
				font-weight:700;font-size:11px;">${n}</div>`,
			iconSize: [22, 22],
			iconAnchor: [11, 11],
		});

	// Isi + tombol popup dipakai peta besar DAN peta kecil di dinding CCTV.
	// `owner` = peta pemilik popup; `pan` dimatikan untuk peta kecil (kotaknya sempit).
	function popup_ready(popup, owner, pan) {
		const el = popup.getElement();
		if (el && pan) {
			// popup tinggi -> geser peta ke bawah supaya kartunya utuh, tidak mepet tepi atas
			const px = owner.project(popup.getLatLng());
			px.y -= el.clientHeight / 2;
			owner.panTo(owner.unproject(px), { animate: true });
		}
		const r = data.rows.find((x) => x.name === $(el).find('.gm-pop').data('name'));
		if (!r) return;

		const bind = (det) => {
			const $p = $(popup.getElement());
			$p.find('.gm-check').on('click', () => frappe.set_route('Form', 'Dispatch Order', r.dpo));
			$p.find('.gm-note').on('click', () => note_on_vehicle(r, det));
			$p.find('.gm-show').on('click', () => show_route(det));
			$p.find('.gm-play').on('click', () => show_playback(r, det));
		};

		// detail (customer, container, ATD, titik rute) baru diambil sekarang, bukan saat halaman dibuka
		if (details[r.name]) {
			bind(details[r.name]);
		} else {
			bind(null);
			frappe.call('erp.fleet.page.gps_monitor.gps_monitor.get_detail', { vehicle: r.name }).then((res) => {
				details[r.name] = res.message || {};
				if (!owner.hasLayer(popup)) return; // popup keburu ditutup
				popup.setContent(popup_html(r, details[r.name]));
				bind(details[r.name]);
			});
		}
	}

	map.on('popupopen', (e) => popup_ready(e.popup, map, true));

	// Bunyi saat ada unit BERUBAH STATUS antar refresh. Nadanya dibangkitkan WebAudio, jadi
	// tidak perlu file suara; AudioContext baru dibuat saat tombol diklik (syarat autoplay browser).
	const $sound = $body.find('.gm-sound');
	let sound_on = localStorage.getItem('gm_sound') === '1';
	let audio_ctx = null;
	let prev_status = null;

	const SPEAKER = '<path d="M4 7h3l4.5-3.5v13L7 13H4z"/>';
	function paint_sound() {
		$sound
			.toggleClass('gm-on', sound_on)
			.attr('title', sound_on ? __('Suara aktif: berbunyi saat ada unit berubah status') : __('Suara mati'))
			.html(
				`<svg viewBox="0 0 20 20">${SPEAKER}${
					sound_on ? '<path d="M14 7.5a3.5 3.5 0 0 1 0 5"/><path d="M16 5a6.5 6.5 0 0 1 0 10"/>' : '<path d="M14.5 8l4 4M18.5 8l-4 4"/>'
				}</svg>`
			);
	}
	paint_sound();
	$body.find('.gm-absen').on('click', () => {
		absen_only = !absen_only;
		fitted = false;
		paint_map();
		paint_tables();
	});
	$body.find('.gm-job').on('click', () => {
		job_only = !job_only;
		fitted = false;
		paint_map();
		paint_tables();
	});

	$sound.on('click', () => {
		sound_on = !sound_on;
		localStorage.setItem('gm_sound', sound_on ? '1' : '0');
		paint_sound();
		if (sound_on) beep(); // sekaligus contoh bunyinya, dan membuka AudioContext
	});

	function beep() {
		if (!sound_on) return;
		try {
			audio_ctx = audio_ctx || new (window.AudioContext || window.webkitAudioContext)();
			const t = audio_ctx.currentTime;
			const o = audio_ctx.createOscillator();
			const g = audio_ctx.createGain();
			o.type = 'sine';
			o.frequency.setValueAtTime(880, t);
			o.frequency.setValueAtTime(1320, t + 0.14);
			g.gain.setValueAtTime(0.0001, t);
			g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
			g.gain.exponentialRampToValueAtTime(0.0001, t + 0.32);
			o.connect(g).connect(audio_ctx.destination);
			o.start(t);
			o.stop(t + 0.34);
		} catch (e) {
			// browser menolak audio (belum ada interaksi / tab dibisukan) -- diamkan saja
		}
	}

	function load() {
		frappe.call('erp.fleet.page.gps_monitor.gps_monitor.get_rows').then((r) => {
			data = r.message || { branches: [], rows: [] };
			const now_status = Object.fromEntries(data.rows.map((x) => [x.name, x.status]));
			if (prev_status) {
				const ubah = data.rows.filter((x) => prev_status[x.name] && prev_status[x.name] !== x.status);
				if (ubah.length) {
					beep();
					frappe.show_alert({
						message: __('{0} unit berubah status: {1}', [ubah.length, ubah.map((x) => x.nopol).join(', ')]),
						indicator: 'blue',
					});
				}
			}
			prev_status = now_status;
			STATUS_STYLE = data.status_colors || STATUS_STYLE;
			STATUS_ICON = data.status_icons || STATUS_ICON;
			details = {};
			paint_map();
			paint_tables();
			apply_interval(data.refresh_seconds);
			// datang dari tombol peta di halaman Monitoring: langsung zoom + buka popup unitnya
			const target = frappe.route_options && frappe.route_options.vehicle;
			if (target) {
				frappe.route_options = null;
				const r0 = data.rows.find((x) => x.name === target);
				if (r0 && r0.latitude && r0.longitude) {
					map.setView([r0.latitude, r0.longitude], 14);
					markers[r0.name] && markers[r0.name].openPopup();
				}
			}
		});
	}

	// batas peta/tabel bisa digeser atas-bawah
	let drag = null;
	$body.find('.gm-drag').on('mousedown', (e) => {
		drag = { y: e.clientY, h: $map.height() };
		$('body').css('user-select', 'none');
		e.preventDefault();
	});
	$(document).on('mousemove.gm', (e) => {
		if (!drag) return;
		const h = Math.min(Math.max(drag.h + (e.clientY - drag.y), 180), window.innerHeight - 180);
		$map.height(h);
		fit_tables();
	});
	$(document).on('mouseup.gm', () => {
		if (!drag) return;
		drag = null;
		$('body').css('user-select', '');
		map.invalidateSize();
	});

	// interval refresh mengikuti Fleet Settings (default 3 menit)
	let timer = null;
	let timer_seconds = 0;
	function apply_interval(seconds) {
		seconds = Number(seconds) || 180;
		if (seconds === timer_seconds) return;
		timer_seconds = seconds;
		clearInterval(timer);
		timer = setInterval(load, seconds * 1000);
	}

	load();
	apply_interval(180);
	$(wrapper).on('remove', () => {
		clearInterval(timer);
		$(document).off('mousemove.gm mouseup.gm');
	});
};

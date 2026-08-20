// GPS Monitoring: dinding ala CCTV untuk petugas GPS — 1 kolom per branch x 2 baris unit.
//
// Sengaja HALAMAN SENDIRI, bukan mode di dalam GPS Vehicle: kartunya dulu memakai
// popup_html() milik halaman itu, sehingga setiap kali tata letak dinding diubah tampilan
// GPS Vehicle ikut berubah. Di sini kartunya milik sendiri dan bebas diatur.
//
// Datanya menumpang endpoint GPS Vehicle (get_rows / get_detail) supaya tidak ada dua
// sumber kebenaran status di server.
frappe.pages['gps-monitoring'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('GPS Monitoring'),
		single_column: true,
	});

	const ROWS = 2; // baris unit per kolom branch
	const ROTATE_SECONDS = 15; // ganti unit di kotak
	const REFRESH_SECONDS = 60; // tarik data baru
	const DETAIL_TTL = 5 * 60 * 1000; // umur cache detail unit

	const API = 'erp.fleet.page.gps_monitor.gps_monitor.';
	const esc = frappe.utils.escape_html;
	const TRUCK_URL = '/assets/erp/images/truck.png';

	let data = { branches: [], rows: [], status_colors: {} };
	let cams = [];
	let groups = {};
	let offset = 0;
	let rotate_timer = null;
	let refresh_timer = null;
	const details = {};
	const detail_at = {};

	const $body = $(`
		<div class="im-wrap">
			<style>
				.im-wrap { height: calc(100vh - 72px); }
				.im-grid { display: grid; gap: 6px; height: 100%; }
				.im-cam { position: relative; display: flex; flex-direction: column; overflow: hidden;
					border: 1px solid var(--border-color); border-radius: 6px; background: var(--card-bg); }
				.im-map { flex: 1 1 auto; min-height: 100px; }
				.im-br { position: absolute; top: 0; left: 0; z-index: 500; font-size: 11px;
					background: rgba(0,0,0,.55); color: #fff; padding: 2px 8px; border-bottom-right-radius: 6px; }
				/* Hold: kunci SATU kotak saja supaya isinya tidak ikut berganti/refresh */
				.im-hold { position: absolute; top: 4px; right: 4px; z-index: 600; font-size: 10.5px;
					font-weight: 700; padding: 2px 9px; border-radius: 10px; cursor: pointer;
					border: 1px solid rgba(0,0,0,.25); background: rgba(255,255,255,.9); color: #374151; }
				.im-hold.on { background: #f59e0b; color: #fff; border-color: #b45309; }
				.im-cam.held { outline: 2px solid #f59e0b; outline-offset: -2px; }
				/* penanda unit: status di atas, nopol, lalu ikon truk */
				.im-pin { display: flex; flex-direction: column; align-items: center; line-height: 1; }
				.im-pin-st { font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 9px;
					white-space: nowrap; box-shadow: 0 1px 3px rgba(0,0,0,.35); }
				.im-pin-no { font-size: 13px; font-weight: 800; color: #111827; background: #fff;
					padding: 1px 7px; border-radius: 4px; margin: 2px 0; white-space: nowrap;
					box-shadow: 0 1px 3px rgba(0,0,0,.35); }
				.im-pin img { width: 44px; height: 44px; filter: drop-shadow(0 1px 3px rgba(0,0,0,.45)); }
				/* kartu data: 3 kolom, teks besar, rapat */
				.im-card { flex: 0 0 auto; border-top: 1px solid var(--border-color); padding: 6px 9px 7px; }
				.im-head { font-size: 14px; font-weight: 700; line-height: 17px; margin-bottom: 5px;
					white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.im-head span { color: var(--text-muted); font-weight: 600; }
				.im-dl { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px 10px; }
				.im-dl > div { min-width: 0; }
				.im-dt { font-size: 9.5px; font-weight: 700; color: var(--text-muted);
					text-transform: uppercase; line-height: 11px; }
				.im-dd { font-size: 14px; font-weight: 600; line-height: 17px;
					white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
				.im-act { display: flex; gap: 5px; margin-top: 6px; }
				.im-act .btn { flex: 1 1 0; font-size: 11px; padding: 3px 6px; line-height: 14px; }
				.im-empty { display: flex; align-items: center; justify-content: center; height: 100%;
					color: var(--text-muted); font-size: 12px; }
			</style>
			<div class="im-grid"></div>
		</div>
	`).appendTo(page.body);

	page.set_secondary_action(__('Refresh'), load);
	const $full = $(`<button class="btn btn-default btn-xs" style="margin-right:8px">${__('Fullscreen')}</button>`);
	page.page_actions.prepend($full);
	$full.on('click', () => wrapper.requestFullscreen && wrapper.requestFullscreen());
	$(wrapper).on('fullscreenchange', () => setTimeout(resize_all, 200));

	const tiles = () =>
		L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
			subdomains: 'abcd',
			maxZoom: 20,
		});

	const num_icon = (n, bg) =>
		L.divIcon({
			className: '',
			html: `<div style="width:20px;height:20px;border-radius:50%;background:${bg};color:#fff;border:2px solid #fff;
				box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;
				font-weight:700;font-size:10px;">${n}</div>`,
			iconSize: [20, 20],
			iconAnchor: [10, 10],
		});

	// ikon unit = status + nopol + gambar truk, jadi terbaca tanpa membuka apa pun
	const unit_icon = (r) =>
		L.divIcon({
			className: '',
			html: `<div class="im-pin">
				<div class="im-pin-st" style="${data.status_colors[r.status] || ''}">${esc(r.status || '')}</div>
				<div class="im-pin-no">${esc(r.nopol || '')}</div>
				<img src="${TRUCK_URL}">
			</div>`,
			iconSize: [160, 84],
			iconAnchor: [80, 62],
		});

	const dt = (v) => (v ? frappe.datetime.str_to_user(String(v).slice(0, 19)) : '-');

	function card_html(r, det) {
		const cell = (label, val) =>
			`<div><div class="im-dt">${label}</div><div class="im-dd" title="${esc(val || '')}">${esc(val || '-')}</div></div>`;
		const head = r.job
			? `${esc(r.job)} <span>- ${esc(r.packing_list || '-')}</span>`
			: `<span>${__('Tanpa job aktif')}</span>`;
		return `<div class="im-head">${head}</div>
			<div class="im-dl">
				${cell(__('Driver'), r.driver || (det && det.job_driver))}
				${cell(__('Container No'), det ? det.container_no : '...')}
				${cell(__('Customer'), det ? det.customer : '...')}
				${cell(__('ATD'), det ? dt(det.atd) : '...')}
				${cell(__('Assign Date'), det ? dt(det.assign_at) : '...')}
				<div></div>
			</div>
			<div class="im-act">
				<button class="btn btn-default btn-xs im-note">${__('Note')}</button>
				<button class="btn btn-primary btn-xs im-dpo" ${r.dpo ? '' : 'disabled'}>${__('Show Dispatch')}</button>
			</div>`;
	}

	function note_dialog(r) {
		const d = new frappe.ui.Dialog({
			title: __('Note {0}', [r.nopol]),
			fields: [
				{ fieldtype: 'Small Text', fieldname: 'note', label: __('Catatan'), reqd: 1 },
				{ fieldtype: 'Check', fieldname: 'suspend', label: __('Suspend unit ini') },
			],
			primary_action_label: __('Simpan'),
			primary_action(v) {
				frappe
					.call(API + 'add_note', {
						note: v.note,
						suspend: v.suspend ? 1 : 0,
						vehicle: r.name,
						nopol: r.nopol,
						driver: r.driver,
						dpo_no: r.job,
						status: r.status,
						latitude: r.latitude,
						longitude: r.longitude,
					})
					.then(() => {
						frappe.show_alert({ message: __('Catatan tersimpan'), indicator: 'green' });
						d.hide();
					});
			},
		});
		d.show();
	}

	function build() {
		const branches = (data.branches || []).filter((b) => b.name).map((b) => b.name);
		const $g = $body.find('.im-grid').empty();
		$g.css({
			'grid-template-columns': `repeat(${Math.max(branches.length, 1)}, 1fr)`,
			'grid-template-rows': `repeat(${ROWS}, 1fr)`,
		});
		cams = [];
		for (let row = 0; row < ROWS; row++) {
			branches.forEach((br) => {
				const $c = $(
					`<div class="im-cam"><div class="im-br">${esc(br)}</div>` +
						`<button class="im-hold" title="${__('Kunci kotak ini supaya tidak berganti')}">${__('Hold')}</button>` +
						`<div class="im-map"></div><div class="im-card"></div></div>`
				).appendTo($g);
				const m = L.map($c.find('.im-map')[0], {
					attributionControl: false,
					zoomControl: false,
					dragging: false,
					scrollWheelZoom: false,
					doubleClickZoom: false,
					boxZoom: false,
					keyboard: false,
				}).setView([-2.5, 118], 5);
				tiles().addTo(m);
				const cam = { branch: br, row, map: m, marker: null, route: null, route_pts: null,
					shown: null, hold: false, $cell: $c };
				$c.find('.im-hold').on('click', () => set_hold(cam, !cam.hold));
				cams.push(cam);
			});
		}
		paint();
		setTimeout(resize_all, 250);
	}

	const resize_all = () => cams.forEach((c) => c.map.invalidateSize());

	function group_rows() {
		const prio = data.status_priority || {};
		const by = {};
		(data.rows || [])
			.filter((r) => r.latitude && r.longitude)
			.forEach((r) => {
				const b = r.branch || '-';
				(by[b] = by[b] || []).push(r);
			});
		Object.values(by).forEach((list) =>
			list.sort(
				(a, b) =>
					(prio[a.status] === undefined ? 999 : prio[a.status]) -
						(prio[b.status] === undefined ? 999 : prio[b.status]) ||
					String(a.nopol || '').localeCompare(String(b.nopol || ''))
			)
		);
		return by;
	}

	function clear_route(c) {
		if (c.route) {
			c.map.removeLayer(c.route);
			c.route = null;
		}
		c.route_pts = null;
	}

	// ada rute -> tampilkan seluruh rute + posisi unit; tanpa rute -> zoom ke unitnya
	function fit(c, pos) {
		if (c.route_pts && c.route_pts.length) {
			const all = c.route_pts.map((p) => [p.latitude, p.longitude]).concat([pos]);
			c.map.fitBounds(L.latLngBounds(all).pad(0.3), { animate: false });
		} else {
			c.map.setView(pos, 14, { animate: false });
		}
	}

	function fill(c, r) {
		const $card = c.$cell.find('.im-card');
		const draw = (det) => {
			$card.html(card_html(r, det));
			$card.find('.im-note').on('click', () => {
				set_hold(c, true); // kotak dikunci dulu; user melepasnya sendiri lewat tombol Hold
				note_dialog(r);
			});
			$card.find('.im-dpo').on('click', () => frappe.set_route('Form', 'Dispatch Order', r.dpo));
			clear_route(c);
			const pts = ((det && det.route_points) || []).filter((x) => x.latitude && x.longitude);
			if (pts.length) {
				c.route_pts = pts;
				c.route = L.layerGroup([
					L.polyline(pts.map((p) => [p.latitude, p.longitude]), {
						color: '#1d4ed8',
						weight: 3,
						opacity: 0.7,
						dashArray: '6 6',
					}),
					...pts.map((p, i) =>
						L.marker([p.latitude, p.longitude], { icon: num_icon(i + 1, p.end ? '#16a34a' : '#1d4ed8') })
					),
				]).addTo(c.map);
			}
			fit(c, [r.latitude, r.longitude]);
		};
		draw(details[r.name] || null);
		// detail dianggap segar selama DETAIL_TTL supaya rotasi tidak memanggil server terus
		if (!details[r.name] || Date.now() - (detail_at[r.name] || 0) > DETAIL_TTL) {
			frappe.call(API + 'get_detail', { vehicle: r.name }).then((res) => {
				details[r.name] = res.message || {};
				detail_at[r.name] = Date.now();
				if (c.shown === r.name) draw(details[r.name]);
			});
		}
	}

	// Hold hanya berlaku untuk KOTAK ITU: kotak lain tetap berputar & menyegarkan data.
	function set_hold(c, on) {
		c.hold = !!on;
		c.$cell.toggleClass('held', c.hold);
		c.$cell.find('.im-hold').toggleClass('on', c.hold).text(c.hold ? __('Holding') : __('Hold'));
	}

	function paint() {
		cams.forEach((c) => {
			if (c.hold) return; // sedang dikunci user — jangan diganggu
			const list = groups[c.branch] || [];
			const r = list.length ? list[(c.row + offset * ROWS) % list.length] : null;
			if (!r) {
				c.shown = null;
				clear_route(c);
				if (c.marker) {
					c.map.removeLayer(c.marker);
					c.marker = null;
				}
				c.$cell.find('.im-card').html(`<div class="im-empty">${__('Tidak ada unit')}</div>`);
				return;
			}
			const pos = [r.latitude, r.longitude];
			if (c.marker) c.map.removeLayer(c.marker);
			c.marker = L.marker(pos, { icon: unit_icon(r), zIndexOffset: 1000 }).addTo(c.map);
			if (c.shown !== r.name) {
				c.shown = r.name;
				clear_route(c);
				fill(c, r);
			} else {
				fit(c, pos);
			}
		});
	}

	function load() {
		frappe.call(API + 'get_rows').then((res) => {
			data = res.message || data;
			groups = group_rows();
			if (!cams.length) build();
			else paint();
		});
	}

	load();
	rotate_timer = setInterval(() => {
		offset += 1;
		paint();
	}, ROTATE_SECONDS * 1000);
	refresh_timer = setInterval(load, REFRESH_SECONDS * 1000);
	$(window).on('resize.im', resize_all);

	// halaman ini memang untuk dipajang — langsung layar penuh begitu dibuka
	setTimeout(() => wrapper.requestFullscreen && wrapper.requestFullscreen().catch(() => {}), 400);

	$(wrapper).on('remove', () => {
		clearInterval(rotate_timer);
		clearInterval(refresh_timer);
		cams.forEach((c) => c.map.remove());
		$(window).off('resize.im');
	});
};

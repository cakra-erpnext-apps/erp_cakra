// Form peta untuk master ber-titik (Fleet Location): peta di samping field (1:2),
// klik peta -> set Latitude/Longitude, lingkaran = Radius (KM).
(function () {
	function render(frm) {
		const field = frm.get_field('map_html');
		if (!field) return;

		const $section = field.$wrapper.closest('.form-section');
		const $cols = $section.find('.section-body').first().children('.form-column');
		if ($cols.length >= 2) {
			$cols.eq(0).css({ flex: '0 0 33.333%', 'max-width': '33.333%' });
			$cols.eq(1).css({ flex: '0 0 66.667%', 'max-width': '66.667%' });
		}

		if (!frm._geo_map || !document.body.contains(frm._geo_map.getContainer())) {
			field.$wrapper.html(`
				<div class="geo-search position-relative mb-2">
					<input type="text" class="form-control geo-search-input" autocomplete="off"
						placeholder="${__('Cari alamat, mis. Pelabuhan Belawan')}">
					<div class="geo-search-results list-group position-absolute w-100 shadow"
						style="z-index:10; display:none; max-height:260px; overflow:auto"></div>
				</div>
				<div class="geo-map border rounded" style="height:420px"></div>
			`);
			bind_search(frm, field);
			// Leaflet 1.2 (bundel frappe) crash kalau layer ditambahkan sebelum view di-set
			frm._geo_map = L.map(field.$wrapper.find('.geo-map')[0], { attributionControl: false }).setView([-2.5, 118], 5);
			try {
				// CARTO Voyager: tile OSM langsung sering ditolak (blank), yang ini gratis & stabil
				const tiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
					attribution: '&copy; OpenStreetMap, &copy; CARTO',
					subdomains: 'abcd',
					maxZoom: 20,
				});
				tiles.on('tileerror', (e) => console.error('geo_point_form tileerror:', e.tile && e.tile.src));
				tiles.addTo(frm._geo_map);
			} catch (err) {
				console.error('geo_point_form tileLayer gagal:', err);
			}
			frm._geo_map.on('click', (e) => {
				// wrap(): peta boleh digeser terus melewati batas dunia, dan klik di
				// salinan peta sebelah mengembalikan bujur seperti -261 -- letaknya sama
				// tapi mesin rute menolaknya sebagai angka di luar batas.
				const p = e.latlng.wrap();
				frm.set_value('latitude', Number(p.lat.toFixed(6)));
				frm.set_value('longitude', Number(p.lng.toFixed(6)));
			});
			frm._geo_fitted = false;
		}
		if (frm._geo_layer) {
			frm._geo_layer.remove();
			frm._geo_layer = null;
		}
		const { latitude: lat, longitude: lng, radius_km } = frm.doc;
		if (lat && lng) {
			frm._geo_layer = L.featureGroup([
				L.circleMarker([lat, lng], { radius: 8, color: '#1d4ed8', fillColor: '#3b82f6', fillOpacity: 0.9 }),
				L.circle([lat, lng], { radius: (radius_km || 0) * 1000, color: '#3b82f6', weight: 1, fillOpacity: 0.08 }),
			]).addTo(frm._geo_map);
			if (!frm._geo_fitted) {
				frm._geo_map.fitBounds(frm._geo_layer.getBounds().pad(0.2));
				frm._geo_fitted = true;
			}
		} else if (!frm._geo_fitted) {
			frm._geo_map.setView([-2.5, 118], 5);
		}
		// Peta dibuat saat kontainer masih 0px (form belum selesai layout) -> tile abu-abu.
		// Pantau ukurannya: begitu kontainer punya lebar, hitung ulang & zoom ke pin.
		if (frm._geo_ro) frm._geo_ro.disconnect();
		const el = frm._geo_map.getContainer();
		frm._geo_ro = new ResizeObserver(() => {
			if (!el.offsetWidth || !frm._geo_map) return;
			frm._geo_map.invalidateSize();
			if (frm._geo_layer && frm._geo_needs_fit) {
				frm._geo_map.fitBounds(frm._geo_layer.getBounds().pad(0.2));
				frm._geo_needs_fit = false;
			}
		});
		frm._geo_needs_fit = true;
		frm._geo_ro.observe(el);
	}

	// Cari alamat lewat OpenStreetMap, lalu taruh pin di hasilnya. Jauh lebih
	// cepat daripada menggeser peta manual dari zoom seluruh Indonesia.
	function bind_search(frm, field) {
		const $input = field.$wrapper.find('.geo-search-input');
		const $list = field.$wrapper.find('.geo-search-results');
		let timer = null;

		function hide() {
			$list.hide().empty();
		}

		function apply(row) {
			frm.set_value('latitude', row.lat);
			frm.set_value('longitude', row.lon);
			// Alamat yang sudah diisi orang tidak ditimpa usulan OSM.
			if (frm.fields_dict.alamat && !frm.doc.alamat) frm.set_value('alamat', row.address);
			frm._geo_fitted = false;
			render(frm);
		}

		function show_results(rows) {
			if (!rows.length) {
				$list.html(`<div class="list-group-item text-muted">${__('Alamat tidak ditemukan')}</div>`);
				return;
			}
			$list.empty();
			for (const row of rows) {
				const $item = $('<a class="list-group-item list-group-item-action" href="#"></a>');
				$item.append($('<div></div>').text(row.label));
				if (row.detail) {
					$item.append($('<small class="text-muted d-block text-truncate"></small>').text(row.detail));
				}
				// mousedown, bukan click: blur input duluan menutup daftar sebelum klik mendarat.
				$item.on('mousedown', (e) => {
					e.preventDefault();
					apply(row);
					$input.val(row.label);
					hide();
				});
				$list.append($item);
			}
		}

		async function search(q) {
			$list.html(`<div class="list-group-item text-muted">${__('Mencari...')}</div>`).show();
			let rows = [];
			try {
				const r = await frappe.call({ method: 'erp.fleet.geocode.search_address', args: { q } });
				rows = r.message || [];
			} catch (e) {
				console.error('geo_point_form: pencarian alamat gagal', e);
			}
			show_results(rows);
		}

		$input.on('input', function () {
			const q = this.value.trim();
			clearTimeout(timer);
			if (q.length < 3) return hide();
			// 600ms: satu permintaan per jeda mengetik, bukan per huruf -- Nominatim
			// membatasi 1 permintaan per detik.
			timer = setTimeout(() => search(q), 600);
		});
		$input.on('blur', () => setTimeout(hide, 200));
	}

	function reset_and_render(frm) {
		frm._geo_fitted = false;
		render(frm);
	}

	for (const dt of ['Fleet Location', 'Incident']) {
		frappe.ui.form.on(dt, {
			refresh: reset_and_render,
			latitude: render,
			longitude: render,
			radius_km: render,
		});
	}
})();

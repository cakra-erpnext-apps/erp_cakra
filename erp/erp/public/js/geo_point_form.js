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
			field.$wrapper.html('<div class="border rounded" style="height:420px"></div>');
			// Leaflet 1.2 (bundel frappe) crash kalau layer ditambahkan sebelum view di-set
			frm._geo_map = L.map(field.$wrapper.children()[0]).setView([-2.5, 118], 5);
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
				frm.set_value('latitude', Number(e.latlng.lat.toFixed(6)));
				frm.set_value('longitude', Number(e.latlng.lng.toFixed(6)));
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

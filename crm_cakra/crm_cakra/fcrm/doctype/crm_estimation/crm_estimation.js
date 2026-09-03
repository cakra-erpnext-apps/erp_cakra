// Peta rute di tab Route (field HTML route_map): pin bernomor route1..8 dengan
// garis solid, Loading/Unloading sebagai deret putus-putus pudar -- tampilan
// sama dengan RouteMap.vue/MiniMap.vue di portal CRM. Basemap OSM,
// pola sama dengan erp/public/js/geo_point_form.js (Leaflet = bundel frappe).

(function () {
	const ROUTE_FIELDS = ["route1", "route2", "route3", "route4", "route5", "route6", "route7", "route8"];
	const MAP_FIELDS = [...ROUTE_FIELDS, "loading", "unloading"];

	function pin(text, faded) {
		return L.divIcon({
			className: "",
			html:
				'<div style="background:#2563eb;color:#fff;border:2px solid #fff;border-radius:9999px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600' +
				(faded ? ";opacity:.55" : "") +
				'">' + text + "</div>",
			iconSize: [24, 24],
			iconAnchor: [12, 12],
		});
	}

	function series(pts, faded) {
		const latlngs = pts.map((p) => [p.lat, p.lng]);
		return [
			L.polyline(latlngs, {
				color: "#2563eb",
				weight: 3,
				opacity: faded ? 0.45 : 1,
				dashArray: faded ? "6 8" : null,
			}),
			...pts.map((p, i) =>
				L.marker(latlngs[i], { icon: pin(p.text, faded), opacity: faded ? 0.7 : 1 }).bindTooltip(p.label)
			),
		];
	}

	function ensure_map(frm, field) {
		if (frm._route_map && document.body.contains(frm._route_map.getContainer())) return;
		field.$wrapper.html('<div class="route-map border rounded" style="height:420px"></div>');
		frm._route_map = L.map(field.$wrapper.find(".route-map")[0], { attributionControl: false }).setView([-2.5, 118], 5);
		// Tile lewat /tiles/ = proxy+cache nginx sendiri (lihat nginx-inject.sh). CARTO Voyager ditinggalkan sejak basemap-nya minta API key.
		L.tileLayer("/tiles/{z}/{x}/{y}.png", {
			attribution: "&copy; OpenStreetMap",
			subdomains: "abcd",
			maxZoom: 19,
		}).addTo(frm._route_map);
		// Tab Route belum tentu terbuka saat render -> kontainer 0px, tile abu-abu.
		// Begitu kontainer punya lebar (tab dibuka), hitung ulang & zoom ke rute.
		const el = frm._route_map.getContainer();
		frm._route_ro = new ResizeObserver(() => {
			if (!el.offsetWidth || !frm._route_map) return;
			frm._route_map.invalidateSize();
			if (frm._route_layer && frm._route_needs_fit) {
				frm._route_map.fitBounds(frm._route_layer.getBounds().pad(0.2), { maxZoom: 16 });
				frm._route_needs_fit = false;
			}
		});
		frm._route_ro.observe(el);
	}

	async function render(frm) {
		const field = frm.get_field("route_map");
		if (!field || typeof L === "undefined") return;
		ensure_map(frm, field);

		// Nomor pin diikat ke posisi field, bukan urutan hasil filter: Route 4
		// tetap pin "4" walau Route 3 dikosongkan.
		const entries = MAP_FIELDS.map((f, i) => ({
			name: frm.doc[f],
			end: i >= ROUTE_FIELDS.length,
			text: i < ROUTE_FIELDS.length ? String(i + 1) : f === "loading" ? "L" : "U",
		})).filter((e) => e.name);

		let byName = {};
		if (entries.length) {
			const seq = (frm._route_seq = (frm._route_seq || 0) + 1);
			const r = await frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Fleet Location",
					filters: { name: ["in", [...new Set(entries.map((e) => e.name))]] },
					fields: ["name", "latitude", "longitude"],
					limit_page_length: 0,
				},
			});
			// User bisa ganti field lagi selagi fetch jalan; hasil lama dibuang.
			if (seq !== frm._route_seq) return;
			byName = Object.fromEntries((r.message || []).map((x) => [x.name, x]));
		}

		// Lokasi tanpa koordinat dilewati diam-diam: masternya boleh saja belum
		// di-pin, dan itu bukan alasan mengosongkan peta.
		const resolve = (list) =>
			list
				.map((e) => ({ row: byName[e.name], text: e.text }))
				.filter((p) => p.row && p.row.latitude && p.row.longitude)
				.map((p) => ({ lat: p.row.latitude, lng: p.row.longitude, label: p.row.name, text: p.text }));
		const main = resolve(entries.filter((e) => !e.end));
		const dashed = resolve(entries.filter((e) => e.end));

		if (frm._route_layer) {
			frm._route_layer.remove();
			frm._route_layer = null;
		}
		if (!main.length && !dashed.length) return;
		frm._route_layer = L.featureGroup([
			...(main.length ? series(main, false) : []),
			...(dashed.length ? series(dashed, true) : []),
		]).addTo(frm._route_map);
		if (frm._route_map.getContainer().offsetWidth) {
			frm._route_map.invalidateSize();
			frm._route_map.fitBounds(frm._route_layer.getBounds().pad(0.2), { maxZoom: 16 });
		} else {
			frm._route_needs_fit = true;
		}
	}

	// "Kode - Nama Item" di grid Revenue/Expense: baris child cuma menyimpan
	// type_id (kode), jadi namanya diambil sekali per dokumen ke cache lalu
	// disisipkan lewat link formatter. Formatter Item global milik erpnext
	// (item_code) di-chain supaya perilakunya di form lain tetap jalan.
	const item_names = {};
	const prev_fmt = frappe.form.link_formatters["Item"];
	frappe.form.link_formatters["Item"] = function (value, doc, df) {
		if (df && df.fieldname === "type_id" && value && item_names[value] && item_names[value] !== value)
			return value + " - " + item_names[value];
		return prev_fmt ? prev_fmt.apply(this, arguments) : value;
	};

	async function load_item_names(frm) {
		const codes = [
			...new Set(
				[...(frm.doc.revenue_items || []), ...(frm.doc.expense_items || [])]
					.map((d) => d.type_id)
					.filter((c) => c && !(c in item_names))
			),
		];
		if (!codes.length) return;
		const r = await frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Item",
				filters: { name: ["in", codes] },
				fields: ["name", "item_name"],
				limit_page_length: 0,
			},
		});
		for (const x of r.message || []) item_names[x.name] = x.item_name;
		frm.refresh_field("revenue_items");
		frm.refresh_field("expense_items");
	}

	// Baris baru Revenue/Expense: currency mengikuti default sistem (Global Defaults),
	// bukan "IDR" yang dulu dipatok di doctype -- site dengan mata uang lain jadi ikut
	// benar. Rate 1 = tidak dikonversi. Server mengisi ulang keduanya kalau baris masuk
	// lewat jalur non-UI (lihat CRMEstimation.before_save).
	//
	// is_expense juga dipasang di sini, padahal server menetapkannya lagi saat before_save:
	// tanpa itu, penanda wajib di kolom Status (mandatory_depends_on: eval:doc.is_expense)
	// baru menyala SETELAH simpan ditolak server. Dengan ini user melihatnya sejak awal.
	function row_defaults(frm, cdt, cdn, is_expense) {
		const row = locals[cdt][cdn];
		if (!row.currency) frappe.model.set_value(cdt, cdn, "currency", frappe.defaults.get_default("currency"));
		if (!row.rate) frappe.model.set_value(cdt, cdn, "rate", 1);
		frappe.model.set_value(cdt, cdn, "is_expense", is_expense);
	}

	// Kolom Status hanya berlaku di Expense. Revenue & Expense memakai child doctype yang
	// SAMA, jadi kolomnya tidak bisa dibedakan lewat in_list_view di doctype.
	//
	// `editable_fields` adalah daftar kolom milik SATU grid, jadi grid Expense tidak ikut
	// terpengaruh. update_docfield_property TIDAK bisa dipakai untuk ini: salinan docfield
	// di-cache per nama dokumen INDUK (frappe.meta.docfield_copy[doctype][docname]),
	// sehingga kedua grid berbagi objek yang sama -- menyembunyikan Status di Revenue akan
	// ikut menyembunyikannya di Expense.
	const REVENUE_COLUMNS = ["product_id", "type_id", "csize", "area_id", "dest_id", "amount",
		"remarks", "currency", "rate"].map((fieldname) => ({ fieldname }));

	function setup_revenue_columns(frm) {
		const grid = frm.fields_dict.revenue_items && frm.fields_dict.revenue_items.grid;
		if (!grid || grid._cmi_columns_set) return;
		grid._cmi_columns_set = true;
		grid.editable_fields = REVENUE_COLUMNS;
		// visible_columns sudah terlanjur dihitung saat render pertama, dan
		// setup_visible_columns() berhenti lebih awal kalau isinya sudah ada.
		grid.reset_grid();
	}

	const handlers = {
		refresh(frm) {
			setup_revenue_columns(frm);
			render(frm);
			load_item_names(frm);
		},
		revenue_items_add: (frm, cdt, cdn) => row_defaults(frm, cdt, cdn, 0),
		expense_items_add: (frm, cdt, cdn) => row_defaults(frm, cdt, cdn, 1),
	};
	for (const f of MAP_FIELDS) handlers[f] = render;
	frappe.ui.form.on("CRM Estimation", handlers);
	frappe.ui.form.on("CRM Estimation Detail", { type_id: load_item_names });
})();

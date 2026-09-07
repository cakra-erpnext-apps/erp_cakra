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

	// "Kode - Nama" di grid Revenue/Expense: baris child cuma menyimpan kodenya
	// (type_id -> Item, product_id -> CRM Product), jadi namanya diambil sekali per
	// dokumen ke cache lalu disisipkan lewat link formatter. Formatter global yang
	// sudah ada (mis. milik erpnext untuk Item) di-chain supaya perilakunya di form
	// lain tetap jalan.
	const LABEL_SOURCES = {
		type_id: { doctype: "Item", name_field: "item_name" },
		product_id: { doctype: "CRM Product", name_field: "product_name" },
	};

	// Dikunci per doctype: satu kode bisa ada di Item DAN di CRM Product tanpa
	// menunjuk hal yang sama, jadi cache-nya tidak boleh berbagi ruang nama.
	const labels = {};
	const label_key = (doctype, value) => doctype + "::" + value;

	for (const [fieldname, src] of Object.entries(LABEL_SOURCES)) {
		const prev_fmt = frappe.form.link_formatters[src.doctype];
		frappe.form.link_formatters[src.doctype] = function (value, doc, df) {
			const name = value && labels[label_key(src.doctype, value)];
			if (df && df.fieldname === fieldname && name && name !== value)
				return value + " - " + name;
			return prev_fmt ? prev_fmt.apply(this, arguments) : value;
		};
	}

	async function load_row_labels(frm) {
		const rows = [...(frm.doc.revenue_items || []), ...(frm.doc.expense_items || [])];
		let fetched = false;
		for (const [fieldname, src] of Object.entries(LABEL_SOURCES)) {
			const codes = [
				...new Set(
					rows
						.map((d) => d[fieldname])
						.filter((c) => c && !(label_key(src.doctype, c) in labels))
				),
			];
			if (!codes.length) continue;
			const r = await frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: src.doctype,
					filters: { name: ["in", codes] },
					fields: ["name", src.name_field],
					limit_page_length: 0,
				},
			});
			for (const x of r.message || []) labels[label_key(src.doctype, x.name)] = x[src.name_field];
			fetched = true;
		}
		if (!fetched) return;
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

	// Revenue & Expense memakai child doctype yang SAMA, jadi dua kolom yang cuma milik
	// salah satu sisi tidak bisa dibedakan lewat in_list_view di doctype:
	//   CRM Product -> hanya Revenue (asalnya produk quotation)
	//   Status      -> hanya Expense (Per Doc / By Qty)
	//
	// `editable_fields` adalah daftar kolom milik SATU grid, jadi keduanya bisa diatur
	// sendiri-sendiri. update_docfield_property TIDAK bisa dipakai untuk ini: salinan
	// docfield di-cache per nama dokumen INDUK (frappe.meta.docfield_copy[doctype][docname]),
	// sehingga kedua grid berbagi objek yang sama -- menyembunyikan Status di Revenue akan
	// ikut menyembunyikannya di Expense.
	const GRID_COLUMNS = {
		revenue_items: ["product_id", "type_id", "csize", "area_id", "dest_id", "amount",
			"remarks", "currency", "rate"],
		expense_items: ["type_id", "csize", "area_id", "dest_id", "status", "amount",
			"remarks", "currency", "rate"],
	};

	// Kolom CRM Product read-only, tapi begitu barisnya diklik Frappe menukar SEMUA
	// kolom baris itu jadi control dengan `only_input`. Untuk field yang tidak bisa
	// ditulis, jalur itu merender <input> mentah yang di-disable -- tanpa link
	// formatter -- sehingga "C-00056 - TRUCKING + ISOTANK" berubah jadi "C-00056"
	// begitu barisnya aktif. Frappe tidak menyediakan opsi "kolom ini jangan
	// diaktifkan", jadi selnya dikunci tetap memakai static_area, yang isinya memang
	// sudah lewat formatter (lihat LABEL_SOURCES di atas).
	//
	// Padding & perataan selnya dipatok sendiri supaya isinya tidak bergeser saat
	// barisnya aktif. Frappe memakai dua aturan berbeda untuk dua keadaan itu:
	// baris diam `.grid-static-col { padding: 6px 8px }`, baris aktif
	// `.editable-row .grid-static-col { padding: 0 }` -- karena di baris aktif yang
	// memberi jarak adalah input masing-masing kolom (`--input-padding: 6px 8px`).
	// Sel kita tidak pernah jadi input, jadi tanpa ini teksnya menempel ke atas saat
	// baris aktif (tinggi baris bertambah) lalu lompat 8px ke kiri (padding dinolkan).
	// Satu aturan untuk kedua keadaan: jarak kiri 8px, tegaknya diserahkan ke flex.
	const STATIC_PRODUCT_CELL =
		'.frappe-control[data-fieldname="revenue_items"] .grid-static-col[data-fieldname="product_id"]';
	frappe.dom.set_style(
		`${STATIC_PRODUCT_CELL} {
			display: flex !important;
			align-items: center !important;
			padding: 0 8px !important;
		 }
		 ${STATIC_PRODUCT_CELL} > .field-area { display: none !important; }
		 ${STATIC_PRODUCT_CELL} > .static-area { display: block !important; flex: 1; min-width: 0; }`,
		"cmi-estimation-static-product"
	);

	function setup_grid_columns(frm) {
		for (const [table, fieldnames] of Object.entries(GRID_COLUMNS)) {
			const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
			if (!grid || grid._cmi_columns_set) continue;
			grid._cmi_columns_set = true;
			grid.editable_fields = fieldnames.map((fieldname) => ({ fieldname }));
			// visible_columns sudah terlanjur dihitung saat render pertama, dan
			// setup_visible_columns() berhenti lebih awal kalau isinya sudah ada.
			grid.reset_grid();
		}
	}

	// Kolom Item di grid Revenue/Expense dibatasi Item Group yang diatur di ERPNext Custom
	// Setting > Expedition; daftarnya ikut boot (lihat erpnext_custom/item_scope.boot).
	// Kosong = semua item boleh. Portal CRM memakai daftar yang sama lewat boot-nya sendiri.
	function setup_item_queries(frm) {
		const scopes = [
			["revenue_items", "cmi_revenue_item_groups"],
			["expense_items", "cmi_expense_item_groups"],
		];
		for (const [table, boot_key] of scopes) {
			const groups = frappe.boot[boot_key] || [];
			frm.set_query("type_id", table, () =>
				groups.length ? { filters: { item_group: ["in", groups] } } : {}
			);
		}
	}

	const handlers = {
		refresh(frm) {
			setup_item_queries(frm);
			setup_grid_columns(frm);
			render(frm);
			load_row_labels(frm);
		},
		revenue_items_add: (frm, cdt, cdn) => row_defaults(frm, cdt, cdn, 0),
		expense_items_add: (frm, cdt, cdn) => row_defaults(frm, cdt, cdn, 1),
	};
	for (const f of MAP_FIELDS) handlers[f] = render;
	frappe.ui.form.on("CRM Estimation", handlers);
	frappe.ui.form.on("CRM Estimation Detail", { type_id: load_row_labels });
})();

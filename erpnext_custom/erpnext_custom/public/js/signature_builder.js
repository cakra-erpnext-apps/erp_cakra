// Pembuat signature perusahaan untuk ERPNext Custom Setting > Mailbox (dipasang oleh
// erpnext_custom_setting.js). Blok ditarik dari palet ke kolom signature (Sortable, sudah ada
// di bundel desk), gayanya diatur di panel kanan, dan kanvasnya langsung menampilkan hasil
// dengan data user yang sedang login.
//
// Sumber kebenarannya susunan blok (`mailbox_signature_layout`, JSON). Template Jinja
// `mailbox_signature_template` -- yang dirender server untuk tiap user -- DIBUAT dari susunan itu
// setiap ada perubahan, jadi jangan diedit tangan kalau pembuat ini masih dipakai.
(function () {
	const IMG = "/assets/erpnext_custom/images/mailbox_signature";
	const FIELDS = [
		["full_name", __("Name")],
		["job_title", __("Job Title")],
		["email", __("Email")],
		["company", __("Company")],
		["branch_office", __("Branch Office")],
		["office_address", __("Branch Address")],
		["office_phone", __("Branch Phone")],
		["mobile_no", __("Mobile")],
		["website", __("Website")],
	];
	const ELEMENTS = [
		["text", __("Text")],
		["image", __("Image")],
		["social", __("Social Icons")],
		["spacer", __("Space")],
	];
	const FONTS = [
		"'Times New Roman', serif",
		"Arial, sans-serif",
		"Calibri, sans-serif",
		"'Segoe UI', sans-serif",
		"Georgia, serif",
		"Verdana, sans-serif",
	];
	const GREY = "#767171";
	const ORANGE = "#ed7d31";
	const DARK = "#3b3838";

	// Sama dengan signature email Cakraindo aslinya (lihat company_signature.html).
	const DEFAULT_LAYOUT = {
		font: FONTS[0],
		line_height: 20,
		columns: [
			{ width: 150, blocks: [{ type: "image", src: `${IMG}/logos.png`, width: 135 }] },
			{
				width: 0,
				blocks: [
					{ type: "field", field: "full_name", size: 16, color: DARK, bold: 1 },
					{ type: "field", field: "job_title", size: 10, color: ORANGE, bold: 1, italic: 1 },
					{ type: "field", field: "email", size: 8, color: GREY, underline: 1 },
					{ type: "field", field: "company", size: 12, color: DARK, bold: 1 },
					{ type: "field", field: "branch_office", suffix: " Office", size: 9, color: ORANGE, bold: 1, italic: 1 },
					{ type: "field", field: "office_address", size: 8, color: GREY },
					{ type: "field", field: "office_phone", prefix: "P: ", size: 8, color: GREY },
					{ type: "field", field: "mobile_no", prefix: "M: ", size: 8, color: GREY },
					{ type: "field", field: "website", size: 8, color: "#0000ff", bold: 1, italic: 1, link: 1 },
					{
						type: "social",
						size: 23,
						items: [
							{ icon: `${IMG}/linkedin.png`, url: "https://id.linkedin.com/company/cakraindo-mitra-internasional" },
							{ icon: `${IMG}/instagram.png`, url: "https://www.instagram.com/cakraindo_official/" },
							{
								icon: `${IMG}/facebook.png`,
								url: "https://www.facebook.com/PT-Cakraindo-Mitra-Internasional-108062534429141/",
							},
						],
					},
				],
			},
		],
	};

	// ------------------------------------------------------------ HTML dari susunan blok

	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	// Teks tetap (awalan, teks bebas, alamat gambar) masuk template Jinja: kurung kurawal
	// dinetralkan supaya tidak bisa menjadi ekspresi Jinja.
	const lit = (s) => esc(s).replace(/\{/g, "&#123;").replace(/\}/g, "&#125;");

	function style_of(b, layout) {
		const size = Number(b.size) || 10;
		const lh = Math.max(layout.line_height || 20, Math.round(size * 1.75));
		return [
			`font-size: ${size}pt`,
			b.color && `color: ${b.color}`,
			b.bold && "font-weight: bold",
			b.italic && "font-style: italic",
			b.underline && "text-decoration: underline",
			lh > (layout.line_height || 20) && `line-height: ${lh}px`,
		]
			.filter(Boolean)
			.join("; ");
	}

	// template = true: placeholder Jinja (disimpan); false: nilai user yang sedang login (kanvas).
	function block_html(b, layout, values, template) {
		const label = (FIELDS.find(([f]) => f === b.field) || [])[1] || b.field;
		// Kosong di profil user yang login: barisnya TIDAK ikut di email ({% if %} di template).
		// Ditulis terang-terangan supaya tidak diakali dengan mengetik nilai di Prefix/Suffix.
		const empty = `<span style="color: #b0b7bd;" title="${esc(
			__("Empty in your user profile, so this line is left out of your emails")
		)}">[${esc(__("{0} empty", [label]))}]</span>`;

		if (b.type === "field" && b.field === "office_address") {
			const line = (value) => `<div style="${style_of(b, layout)}">${lit(b.prefix)}${value}${lit(b.suffix)}</div>`;
			if (template) return `{% for line in office_address_lines %}${line("{{ line }}")}{% endfor %}`;
			const lines = values.office_address_lines || [];
			return lines.length ? lines.map(line).join("") : line(empty);
		}
		if (b.type === "field") {
			const value = template ? `{{ ${b.field} }}` : values[b.field] || empty;
			let inner = `${lit(b.prefix)}${value}${lit(b.suffix)}`;
			if (b.link && b.field === "website") {
				const href = template ? "{{ website_url }}" : values.website_url || "#";
				inner = `<a href="${href}" style="color: inherit;">${inner}</a>`;
			}
			if (b.link && b.field === "email") {
				inner = `<a href="mailto:${template ? "{{ email }}" : values.email || ""}" style="color: inherit;">${inner}</a>`;
			}
			const div = `<div style="${style_of(b, layout)}">${inner}</div>`;
			return template ? `{% if ${b.field} %}${div}{% endif %}` : div;
		}
		if (b.type === "text") {
			return `<div style="${style_of(b, layout)}">${lit(b.text) || (template ? "" : empty)}</div>`;
		}
		if (b.type === "image") {
			const w = Number(b.width) || 120;
			if (!b.src) return template ? "" : `<div>${empty}</div>`;
			const img = `<img src="${lit(b.src)}" width="${w}" alt="" style="width: ${w}px; display: block;">`;
			return `<div>${b.url ? `<a href="${lit(b.url)}">${img}</a>` : img}</div>`;
		}
		if (b.type === "social") {
			const s = Number(b.size) || 23;
			const icons = (b.items || [])
				.filter((i) => i.icon)
				.map(
					(i) =>
						`<a href="${lit(i.url)}" style="text-decoration: none;"><img src="${lit(i.icon)}" width="${s}" height="${s}"
							alt="" style="width: ${s}px; height: ${s}px;"></a>`
				)
				.join("&nbsp;&nbsp;");
			return `<div style="margin-top: 4px;">${icons || (template ? "" : empty)}</div>`;
		}
		if (b.type === "spacer") return `<div style="height: ${Number(b.height) || 8}px;"></div>`;
		return "";
	}

	function build_html(layout, values, template) {
		const cells = layout.columns
			.map(
				(col) =>
					`<td style="padding: 5pt 9pt 5pt 5pt; vertical-align: top;${col.width ? ` width: ${col.width}px;` : ""}">
${col.blocks.map((b) => block_html(b, layout, values, template)).join("\n")}
</td>`
			)
			.join("\n");
		return `<table style="border-collapse: collapse; border-spacing: 0; font-family: ${lit(layout.font)}; line-height: ${
			Number(layout.line_height) || 20
		}px;"><tr>
${cells}
</tr></table>`;
	}

	// ------------------------------------------------------------ tampilan pembuat

	function style() {
		if (document.getElementById("sgb-style")) return;
		$('<style id="sgb-style">')
			.text(
				`
			.sgb { display: flex; gap: 16px; align-items: flex-start; }
			.sgb-palette { flex: 0 0 170px; }
			.sgb-palette-title { font-size: var(--text-sm); color: var(--text-muted); margin: 8px 0 4px; }
			.sgb-item { padding: 6px 10px; margin-bottom: 4px; border: 1px dashed var(--border-color);
				border-radius: var(--border-radius-md); background: var(--fg-color); cursor: grab;
				font-size: var(--text-sm); }
			.sgb-item:hover { border-color: var(--gray-500); }
			.sgb-canvas-wrap { flex: 1 1 auto; min-width: 0; }
			.sgb-canvas { display: flex; background: #fff; color: #1f272e; padding: 12px;
				border: 1px solid var(--border-color); border-radius: var(--border-radius-md); overflow-x: auto; }
			/* nowrap: baris tidak terlipat karena panel sempit; di email aslinya juga tidak */
			.sgb-col { min-width: 90px; min-height: 120px; padding: 5pt 9pt 5pt 5pt; white-space: nowrap;
				outline: 1px dashed #d8dee4; outline-offset: -2px; }
			.sgb-col + .sgb-col { margin-left: 4px; }
			.sgb-block { position: relative; cursor: grab; border-radius: 3px; }
			.sgb-block:hover { box-shadow: 0 0 0 1px #9bb9d8; }
			.sgb-block.active { box-shadow: 0 0 0 2px #2490ef; }
			.sgb-block.sortable-ghost, .sgb-item.sortable-ghost { opacity: 0.4; }
			.sgb-hint { font-size: var(--text-sm); color: var(--text-muted); margin-top: 6px; }
			.sgb-props { flex: 0 0 250px; }
			.sgb-props label { display: block; font-size: var(--text-sm); color: var(--text-muted);
				margin: 8px 0 2px; font-weight: normal; }
			.sgb-props .sgb-check { display: flex; gap: 6px; align-items: center; color: var(--text-color); }
			.sgb-props input[type=color] { width: 48px; height: 28px; padding: 0; border: 0; background: none; }
			.sgb-props .sgb-row { display: flex; gap: 8px; align-items: center; }
			.sgb-props .sgb-social { border-top: 1px solid var(--border-color); padding-top: 6px; margin-top: 6px; }
			.sgb-props-title { font-weight: 600; margin-bottom: 4px; }
			.sgb-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
		`
			)
			.appendTo(document.head);
	}

	class SignatureBuilder {
		constructor(frm, $wrapper) {
			this.frm = frm;
			this.$wrapper = $wrapper;
			this.values = {};
			this.selected = null;
			this.sortables = [];
			style();
			this.load();
			frappe
				.xcall("erpnext_custom.erpnext_custom.doctype.mailbox_signature.mailbox_signature.signature_preview")
				.then((values) => {
					this.values = values || {};
					this.render();
				});
		}

		// Susunan dari dokumen (sesudah simpan/muat ulang), atau bawaan kalau belum pernah dibuat.
		load() {
			let layout = null;
			try {
				layout = JSON.parse(this.frm.doc.mailbox_signature_layout || "null");
			} catch {
				layout = null;
			}
			this.layout = layout && layout.columns ? layout : JSON.parse(JSON.stringify(DEFAULT_LAYOUT));
			let n = 0;
			for (const col of this.layout.columns) for (const b of col.blocks) b.id = b.id || `b${Date.now()}${n++}`;
			this.selected = null;
			this.render();
		}

		set_company(name) {
			this.values.company = esc(name);
			this.render();
		}

		save() {
			const layout = JSON.parse(JSON.stringify(this.layout));
			this.frm.set_value("mailbox_signature_layout", JSON.stringify(layout, null, 1));
			this.frm.set_value("mailbox_signature_template", build_html(layout, null, true));
		}

		// Langsung ditulis ke dokumen (tanpa jeda): Save yang ditekan sesaat sesudah menarik blok
		// tetap menyimpan susunan terbaru. Perubahan datang per "change", bukan per ketukan.
		changed() {
			this.render();
			this.save();
		}

		find(id) {
			for (const col of this.layout.columns) {
				const b = col.blocks.find((x) => x.id === id);
				if (b) return b;
			}
			return null;
		}

		new_block(type, field) {
			const id = `b${Date.now()}${Math.floor(Math.random() * 1000)}`;
			const base = { id, size: 9, color: GREY };
			if (type === "field") return { ...base, type, field };
			if (type === "text") return { ...base, type, text: __("Text") };
			if (type === "image") return { id, type, src: "", width: 120 };
			if (type === "social") return { id, type, size: 23, items: [] };
			return { id, type: "spacer", height: 8 };
		}

		render() {
			for (const s of this.sortables) s.destroy();
			this.sortables = [];

			const palette = (title, rows, type) => `
				<div class="sgb-palette-title">${title}</div>
				${rows
					.map(
						([key, label]) =>
							`<div class="sgb-item" data-type="${type || key}" ${type ? `data-field="${key}"` : ""}>${esc(label)}</div>`
					)
					.join("")}`;

			this.$wrapper.html(`
				<div class="sgb">
					<div class="sgb-palette">
						${palette(__("Fields"), FIELDS, "field")}
						${palette(__("Elements"), ELEMENTS)}
					</div>
					<div class="sgb-canvas-wrap">
						<div class="sgb-canvas" style="font-family: ${esc(this.layout.font)}; line-height: ${
							Number(this.layout.line_height) || 20
						}px;">
							${this.layout.columns
								.map(
									(col, i) => `
								<div class="sgb-col" data-col="${i}" style="${col.width ? `width: ${Number(col.width)}px; flex: 0 0 auto;` : "flex: 1 1 auto;"}">
									${col.blocks
										.map(
											(b) => `
										<div class="sgb-block ${this.selected === b.id ? "active" : ""}" data-id="${esc(b.id)}">
											${block_html(b, this.layout, this.values, false)}
										</div>`
										)
										.join("")}
								</div>`
								)
								.join("")}
						</div>
						<div class="sgb-hint">${__(
							"Drag fields and elements into a column, drag blocks to reorder or move them, and click a block to change its style. The preview uses your own user data; every user gets their own values. A field that is empty in a user's profile is left out of that user's emails."
						)}</div>
					</div>
					<div class="sgb-props"></div>
				</div>
			`);

			const $palette = this.$wrapper.find(".sgb-palette");
			this.sortables.push(
				new Sortable($palette[0], { group: { name: "sgb", pull: "clone", put: false }, sort: false, animation: 150 })
			);
			this.$wrapper.find(".sgb-col").each((_i, el) => {
				this.sortables.push(
					new Sortable(el, {
						group: "sgb",
						animation: 150,
						// Sortable masih menyelesaikan drag saat event ini jalan: tata ulang sesudahnya.
						onEnd: () => setTimeout(() => this.from_dom(), 0),
						onAdd: () => setTimeout(() => this.from_dom(), 0),
					})
				);
			});

			this.$wrapper.find(".sgb-block").on("click", (e) => {
				this.selected = e.currentTarget.getAttribute("data-id");
				this.render();
			});
			this.$wrapper.find(".sgb-canvas").on("click", (e) => {
				if (e.target === e.currentTarget || $(e.target).hasClass("sgb-col")) {
					this.selected = null;
					this.render();
				}
			});
			this.render_props();
		}

		// Susunan baru dibaca dari DOM sesudah drag: blok lama lewat data-id, blok dari palet
		// lewat data-type (salinan item palet yang dijatuhkan ke kolom).
		from_dom() {
			const columns = this.$wrapper
				.find(".sgb-col")
				.map((i, el) => {
					const blocks = [];
					for (const child of el.children) {
						const id = child.getAttribute("data-id");
						if (id) {
							const b = this.find(id);
							if (b) blocks.push(b);
						} else if (child.getAttribute("data-type")) {
							const b = this.new_block(child.getAttribute("data-type"), child.getAttribute("data-field"));
							blocks.push(b);
							this.selected = b.id;
						}
					}
					return { ...this.layout.columns[i], blocks };
				})
				.get();
			this.layout.columns = columns;
			this.changed();
		}

		render_props() {
			const $p = this.$wrapper.find(".sgb-props");
			const b = this.selected && this.find(this.selected);
			if (!b) return this.render_layout_props($p);

			const title = (FIELDS.find(([f]) => f === b.field) || ELEMENTS.find(([t]) => t === b.type) || [])[1];
			const text_style = `
				<label>${__("Font size (pt)")}</label>
				<input type="number" class="form-control input-xs" data-key="size" min="6" max="40" value="${esc(b.size)}">
				<label>${__("Color")}</label>
				<input type="color" data-key="color" value="${esc(b.color || "#000000")}">
				<label class="sgb-check"><input type="checkbox" data-key="bold" ${b.bold ? "checked" : ""}> ${__("Bold")}</label>
				<label class="sgb-check"><input type="checkbox" data-key="italic" ${b.italic ? "checked" : ""}> ${__("Italic")}</label>
				<label class="sgb-check"><input type="checkbox" data-key="underline" ${b.underline ? "checked" : ""}> ${__(
				"Underline"
			)}</label>`;

			let body = "";
			if (b.type === "field") {
				body = `
					<label>${__("Text before")}</label>
					<input type="text" class="form-control input-xs" data-key="prefix" value="${esc(b.prefix)}" placeholder="P: ">
					<label>${__("Text after")}</label>
					<input type="text" class="form-control input-xs" data-key="suffix" value="${esc(b.suffix)}" placeholder=" Office">
					${text_style}
					${
						["website", "email"].includes(b.field)
							? `<label class="sgb-check"><input type="checkbox" data-key="link" ${b.link ? "checked" : ""}> ${__(
									"Clickable link"
							  )}</label>`
							: ""
					}`;
			} else if (b.type === "text") {
				body = `
					<label>${__("Text")}</label>
					<input type="text" class="form-control input-xs" data-key="text" value="${esc(b.text)}">
					${text_style}`;
			} else if (b.type === "image") {
				body = `
					<label>${__("Image")}</label>
					<div class="sgb-row">
						<input type="text" class="form-control input-xs" data-key="src" value="${esc(b.src)}">
						<button class="btn btn-default btn-xs sgb-upload" data-key="src">${__("Upload")}</button>
					</div>
					<label>${__("Width (px)")}</label>
					<input type="number" class="form-control input-xs" data-key="width" min="10" max="600" value="${esc(b.width)}">
					<label>${__("Link (optional)")}</label>
					<input type="text" class="form-control input-xs" data-key="url" value="${esc(b.url)}" placeholder="https://">`;
			} else if (b.type === "social") {
				body = `
					<label>${__("Icon size (px)")}</label>
					<input type="number" class="form-control input-xs" data-key="size" min="10" max="64" value="${esc(b.size)}">
					${(b.items || [])
						.map(
							(item, i) => `
						<div class="sgb-social">
							<label>${__("Icon {0}", [i + 1])}</label>
							<div class="sgb-row">
								<input type="text" class="form-control input-xs" data-item="${i}" data-key="icon" value="${esc(item.icon)}">
								<button class="btn btn-default btn-xs sgb-upload" data-item="${i}" data-key="icon">${__("Upload")}</button>
							</div>
							<label>${__("Link")}</label>
							<input type="text" class="form-control input-xs" data-item="${i}" data-key="url" value="${esc(item.url)}"
								placeholder="https://">
							<button class="btn btn-default btn-xs sgb-social-remove" data-item="${i}" style="margin-top: 6px;">${__(
								"Remove icon"
							)}</button>
						</div>`
						)
						.join("")}
					<button class="btn btn-default btn-xs sgb-social-add" style="margin-top: 8px;">${__("Add icon")}</button>`;
			} else if (b.type === "spacer") {
				body = `
					<label>${__("Height (px)")}</label>
					<input type="number" class="form-control input-xs" data-key="height" min="2" max="80" value="${esc(b.height)}">`;
			}

			$p.html(`
				<div class="sgb-props-title">${esc(title)}</div>
				${body}
				<div class="sgb-actions">
					<button class="btn btn-default btn-xs sgb-delete">${__("Delete block")}</button>
				</div>
			`);

			const set = (el) => {
				const key = el.getAttribute("data-key");
				const value = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value;
				const item = el.getAttribute("data-item");
				if (item !== null) b.items[Number(item)][key] = value;
				else b[key] = value;
				this.changed();
			};
			// "change", bukan "input": kanvas digambar ulang setiap perubahan, dan menggambar ulang
			// di tengah ketikan melepas fokus dari kotak isian.
			$p.find("input").on("change", (e) => set(e.currentTarget));
			$p.find(".sgb-upload").on("click", (e) => {
				const btn = e.currentTarget;
				new frappe.ui.FileUploader({
					allow_multiple: false,
					make_attachments_public: 1,
					restrictions: { allowed_file_types: ["image/*"] },
					on_success: (file) => {
						const item = btn.getAttribute("data-item");
						if (item !== null) b.items[Number(item)][btn.getAttribute("data-key")] = file.file_url;
						else b[btn.getAttribute("data-key")] = file.file_url;
						this.changed();
					},
				});
			});
			$p.find(".sgb-social-add").on("click", () => {
				b.items = [...(b.items || []), { icon: "", url: "" }];
				this.changed();
			});
			$p.find(".sgb-social-remove").on("click", (e) => {
				b.items.splice(Number(e.currentTarget.getAttribute("data-item")), 1);
				this.changed();
			});
			$p.find(".sgb-delete").on("click", () => {
				for (const col of this.layout.columns) col.blocks = col.blocks.filter((x) => x.id !== b.id);
				this.selected = null;
				this.changed();
			});
		}

		// Tanpa blok terpilih: pengaturan seluruh signature.
		render_layout_props($p) {
			const layout = this.layout;
			$p.html(`
				<div class="sgb-props-title">${__("Signature")}</div>
				<label>${__("Font")}</label>
				<select class="form-control input-xs" data-key="font">
					${FONTS.map(
						(f) => `<option value="${esc(f)}" ${f === layout.font ? "selected" : ""}>${esc(f.split(",")[0].replace(/'/g, ""))}</option>`
					).join("")}
				</select>
				<label>${__("Line height (px)")}</label>
				<input type="number" class="form-control input-xs" data-key="line_height" min="12" max="40"
					value="${esc(layout.line_height)}">
				${layout.columns
					.map(
						(col, i) => `
					<label>${__("Column {0} width (px, 0 = auto)", [i + 1])}</label>
					<input type="number" class="form-control input-xs" data-col="${i}" min="0" max="600" value="${esc(col.width || 0)}">`
					)
					.join("")}
				<div class="sgb-actions">
					<button class="btn btn-default btn-xs sgb-col-add">${__("Add column")}</button>
					${layout.columns.length > 1 ? `<button class="btn btn-default btn-xs sgb-col-remove">${__("Remove last column")}</button>` : ""}
					<button class="btn btn-default btn-xs sgb-reset">${__("Reset to default")}</button>
				</div>
				<div class="sgb-hint">${__("Click a block in the preview to change it.")}</div>
			`);

			$p.find("[data-key]").on("change", (e) => {
				layout[e.currentTarget.getAttribute("data-key")] = e.currentTarget.value;
				this.changed();
			});
			$p.find("[data-col]").on("change", (e) => {
				layout.columns[Number(e.currentTarget.getAttribute("data-col"))].width = Number(e.currentTarget.value) || 0;
				this.changed();
			});
			$p.find(".sgb-col-add").on("click", () => {
				layout.columns.push({ width: 0, blocks: [] });
				this.changed();
			});
			$p.find(".sgb-col-remove").on("click", () => {
				const last = layout.columns[layout.columns.length - 1];
				const drop = () => {
					layout.columns.pop();
					this.changed();
				};
				if (last.blocks.length) frappe.confirm(__("Remove the last column and its blocks?"), drop);
				else drop();
			});
			$p.find(".sgb-reset").on("click", () =>
				frappe.confirm(__("Replace the signature with the default layout?"), () => {
					this.frm.doc.mailbox_signature_layout = "";
					this.load();
					this.save();
				})
			);
		}
	}

	// untuk pemeriksaan di luar form (mis. membuat template dari susunan bawaan)
	SignatureBuilder.build_html = build_html;
	SignatureBuilder.DEFAULT_LAYOUT = DEFAULT_LAYOUT;
	window.SignatureBuilder = SignatureBuilder;
})();

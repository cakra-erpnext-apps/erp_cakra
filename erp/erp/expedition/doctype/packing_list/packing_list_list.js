// List view Packing List: kolom finansial Inv / Exp / Margin sebagai KOLOM asli di grid,
// sama seperti Shipping List (lihat shipping_list_list.js untuk penjelasan lengkap).
// Blok window.erp_fin_list_setup HARUS identik dengan yang di shipping_list_list.js
// (di-guard, hanya definisi pertama yang dipakai runtime).

window.erp_fin_list_setup =
	window.erp_fin_list_setup ||
	function (cfg) {
		const COLS = cfg.columns || [
			{ key: 'inv', label: 'Inv', kind: 'inv', w: 150 },
			{ key: 'exp', label: 'Exp', kind: 'exp', w: 150 },
			{ key: 'margin', label: 'Margin', fin: true, right: 1, w: 120 },
		];
		const NEEDS_FIN = COLS.some((c) => c.kind || c.fin);

		function inject_style() {
			if (document.getElementById('erp-fin-style')) return;
			const s = document.createElement('style');
			s.id = 'erp-fin-style';
			s.textContent = `
			/* Sel kolom tambahan: sela 5px di kanan (lebar diatur inline per kolom). */
			.erp-fin-list .erp-fin-col { padding-right: 5px !important; }
			.erp-fin-list .erp-fin-right { text-align: right; justify-content: flex-end; }
			.erp-fin-list .list-row-head .erp-fin-h span { font-weight: inherit; }
			.erp-fin-list .erp-fin-c a.erp-fin-link { color: var(--text-color); text-decoration: none; }
			.erp-fin-list .erp-fin-c a.erp-fin-link:hover { text-decoration: underline; }
			.erp-fin-list .erp-fin-c .erp-fin-more { color: var(--text-muted); font-size: 11px; }
			.erp-fin-list .erp-fin-margin-pos { color: var(--green-600, #2e7d32); font-weight: 600; }
			.erp-fin-list .erp-fin-margin-neg { color: var(--red-600, #c62828); font-weight: 600; }
			/* Kolom ID (subject): pas dengan isi (nomor panjang …/OGM/26 utuh) + sela 5px di kanan. */
			.erp-fin-list .list-row-head .list-subject, .erp-fin-list .list-row .list-subject { flex: 0 0 220px !important; max-width: 220px !important; padding-right: 5px !important; }
			.erp-fin-list .list-subject .ellipsis, .erp-fin-list .list-subject a, .erp-fin-list .list-subject .level-item, .erp-fin-list .list-subject span {
				max-width: none !important; overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; }
			`;
			document.head.appendChild(s);
		}

		function mark(listview) {
			// Tandai halaman list ini agar CSS pelebar kolom ID hanya berlaku di sini.
			if (listview && listview.page && listview.page.wrapper) $(listview.page.wrapper).addClass('erp-fin-list');
		}

		const cell_style = (c) => `flex:0 0 ${c.w}px;max-width:${c.w}px`;

		// cfg.replace_native: kolom native Frappe (in_list_view) DIHAPUS dari DOM supaya
		// tidak dobel dengan kolom injected (cfg.columns berisi set kolom lengkap). Hanya
		// subject (ID) & sel kita (.erp-fin-*) yang dipertahankan.
		function strip_native($container) {
			if (!cfg.replace_native) return;
			$container.children('.list-row-col').each(function () {
				const $c = $(this);
				if ($c.hasClass('list-subject') || $c.hasClass('erp-fin-h') || $c.hasClass('erp-fin-c')) return;
				$c.remove();
			});
		}

		// Header: sisipkan sel kolom tepat setelah kolom subject (ID). Frappe membangun
		// ulang header tiap render, jadi selalu bersihkan lalu tambah lagi.
		function paint_header(listview) {
			const $head = listview.$result.find('.list-row-head .list-header-subject').first();
			const $subj = $head.children('.list-subject').first();
			if (!$subj.length) return;
			$subj.siblings('.erp-fin-h').remove();
			strip_native($head);
			const cells = COLS.map((c) =>
				`<div class="list-row-col hidden-xs erp-fin-h erp-fin-col${c.right ? ' erp-fin-right' : ''}" style="${cell_style(c)}"><span>${__(c.label)}</span></div>`
			).join('');
			$(cells).insertAfter($subj);
		}

		// Isi HTML satu sel finansial (inv/exp/margin) dari data list_financials.
		function fin_cell(c, fin, brief, cur) {
			if (!fin) return '<span class="text-muted">-</span>';
			if (c.kind === 'inv') {
				const list = (fin.invoices || []).map((iv) => iv.name + (iv.draft ? ' (draft)' : ''));
				return list.length ? `<a href="#" class="erp-fin-link">${brief(list)}</a>` : '<span class="text-muted">-</span>';
			}
			if (c.kind === 'exp') {
				const list = (fin.expenses || []).map((en) => en.name + (en.reimburse ? ' (reimburse)' : ''));
				return list.length ? `<a href="#" class="erp-fin-link">${brief(list)}</a>` : '<span class="text-muted">-</span>';
			}
			// margin
			if ((fin.invoices || []).length || (fin.expenses || []).length) {
				const mcls = (fin.margin || 0) >= 0 ? 'erp-fin-margin-pos' : 'erp-fin-margin-neg';
				const pct = fin.margin_pct != null ? ` (${fin.margin_pct}%)` : '';
				return `<span class="${mcls}">${format_currency(fin.margin || 0, cur)}${pct}</span>`;
			}
			return '<span class="text-muted">-</span>';
		}

		// Baris: isi/segarkan sel setelah subject tiap row. Dipanggil 2x — sekali kosong
		// (langsung, agar kolom sejajar saat loading) lalu sekali dgn data finansial.
		function paint_rows(listview, map) {
			const esc = frappe.utils.escape_html;
			const brief = (arr) => {
				if (!arr.length) return '<span class="text-muted">-</span>';
				const first = esc(arr[0]);
				return arr.length > 1 ? `${first} <span class="erp-fin-more">+${arr.length - 1}</span>` : first;
			};
			const dataByName = {};
			(listview.data || []).forEach((d) => { if (d && d.name) dataByName[d.name] = d; });

			listview.$result.find('.list-row-container').each(function () {
				const $c = $(this);
				if ($c.find('.list-row-head').length) return; // lewati baris header
				const $left = $c.find('.list-row .level-left').first();
				const $subj = $left.children('.list-subject').first();
				if (!$subj.length) return;
				$left.children('.erp-fin-c').remove();
				strip_native($left);
				const name = $c.find('[data-name]').first().attr('data-name');
				const docData = dataByName[name] || {};
				const fin = name && map[name];
				const cur = (fin && fin.currency) || 'IDR';

				const cellHtml = COLS.map((c) => {
					let html, clickable = false;
					if (c.doc) {
						html = esc(c.doc(docData) || '') || '<span class="text-muted">-</span>';
					} else {
						html = fin_cell(c, fin, brief, cur);
						clickable = !!(c.kind && fin);
					}
					const attrs = clickable ? ` data-kind="${c.kind}" data-doc="${esc(name)}" title="${esc(__('Lihat semua untuk {0}', [name || '']))}"` : '';
					return `<div class="list-row-col hidden-xs ellipsis erp-fin-c${c.right ? ' erp-fin-right' : ''}" style="${cell_style(c)}"${attrs}>${html}</div>`;
				}).join('');
				$(cellHtml).insertAfter($subj);
			});
		}

		// Klik sel Inv/Exp → buka list terfilter. Delegasi di $result (match sel masa depan);
		// stopPropagation supaya tidak ikut membuka dokumen (klik baris).
		function bind_clicks(listview) {
			listview.$result.off('click.erpfin').on('click.erpfin', '.erp-fin-c[data-kind] a.erp-fin-link', function (ev) {
				ev.preventDefault();
				ev.stopPropagation();
				const $cell = $(this).closest('.erp-fin-c');
				const name = $cell.attr('data-doc');
				if (!name) return;
				if ($cell.attr('data-kind') === 'inv') {
					frappe.route_options = { [cfg.inv_filter_field]: name };
					frappe.set_route('List', 'Sales Invoice', 'List');
				} else {
					frappe.route_options = { [cfg.en_filter_field]: name };
					frappe.set_route('List', 'Expense Note', 'List');
				}
			});
		}

		function render(listview) {
			inject_style();
			mark(listview);
			paint_header(listview);
			paint_rows(listview, {}); // sel awal → kolom langsung sejajar saat loading
			bind_clicks(listview);
			if (!NEEDS_FIN) return;
			const names = (listview.data || []).map((d) => d.name).filter(Boolean);
			if (!names.length) return;
			frappe.call({
				method: 'erp.expedition.financials.list_financials',
				args: { source_doctype: cfg.source_doctype, names: names },
			}).then((r) => paint_rows(listview, (r && r.message) || {}));
		}

		return {
			add_fields: cfg.add_fields,
			onload(listview) { render(listview); },
			refresh(listview) { render(listview); },
		};
	};

frappe.listview_settings['Packing List'] = window.erp_fin_list_setup({
	source_doctype: 'Packing List',
	inv_filter_field: 'custom_packing_list',
	en_filter_field: 'packing_list',
	// Kolom default (Inv, Exp, Margin) — tidak diubah.
});

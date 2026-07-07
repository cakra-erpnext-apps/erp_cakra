// List view Packing List: baris finansial Inv / Exp / Margin di bawah tiap row,
// sama seperti Shipping List (lihat shipping_list_list.js).
// Blok window.erp_fin_list_setup identik dengan yang di shipping_list_list.js
// (di-guard, hanya definisi pertama yang dipakai).

window.erp_fin_list_setup =
	window.erp_fin_list_setup ||
	function (cfg) {
		function inject_style() {
			if (document.getElementById('erp-fin-style')) return;
			const s = document.createElement('style');
			s.id = 'erp-fin-style';
			s.textContent = `
			.erp-fin-line { padding: 0 15px 6px; margin-top: -2px; font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.erp-fin-line .erp-fin-seg { margin-right: 18px; }
			.erp-fin-line .erp-fin-label { font-weight: 600; }
			.erp-fin-line a.erp-fin-link { color: inherit; text-decoration: none; }
			.erp-fin-line a.erp-fin-link:hover { color: var(--text-color); text-decoration: underline; }
			.erp-fin-line .erp-fin-margin-pos { color: var(--green-600, #2e7d32); font-weight: 600; }
			.erp-fin-line .erp-fin-margin-neg { color: var(--red-600, #c62828); font-weight: 600; }
			`;
			document.head.appendChild(s);
		}

		function render(listview) {
			const names = (listview.data || []).map((d) => d.name).filter(Boolean);
			if (!names.length) return;
			frappe.call({
				method: 'erp.expedition.financials.list_financials',
				args: { source_doctype: cfg.source_doctype, names: names },
			}).then((r) => {
				const map = (r && r.message) || {};
				listview.$result.find('.list-row-container').each(function () {
					const $c = $(this);
					const name = $c.find('[data-name]').first().attr('data-name');
					$c.find('.erp-fin-line').remove();
					const fin = name && map[name];
					if (!fin) return;

					const esc = frappe.utils.escape_html;
					const cur = fin.currency || 'IDR';
					// Tampilkan 1 nomor saja; lebih dari 1 diringkas jadi "..." (klik untuk list lengkap).
					const brief = (list) => (list.length > 1 ? list[0] + ' ...' : list.join(''));
					const invs = brief((fin.invoices || []).map((iv) => esc(iv.name) + (iv.draft ? ' (draft)' : '')));
					const exps = brief((fin.expenses || []).map((en) => esc(en.name) + (en.reimburse ? ' (reimburse)' : '')));

					const seg = (label, val, kind) => {
						const inner = `<span class="erp-fin-label">${label}:</span> ${val || '<span class="text-muted">-</span>'}`;
						return kind
							? `<a href="#" class="erp-fin-seg erp-fin-link" data-kind="${kind}" title="${__('Lihat list {0} untuk {1}', [label, esc(name)])}">${inner}</a>`
							: `<span class="erp-fin-seg">${inner}</span>`;
					};

					let margin = seg('Margin', '<span class="text-muted">-</span>');
					if ((fin.invoices || []).length || (fin.expenses || []).length) {
						const cls = (fin.margin || 0) >= 0 ? 'erp-fin-margin-pos' : 'erp-fin-margin-neg';
						const pct = fin.margin_pct != null ? ` (${fin.margin_pct}%)` : '';
						margin = seg('Margin', `<span class="${cls}">${format_currency(fin.margin || 0, cur)}${pct}</span>`);
					}

					const $line = $(`<div class="erp-fin-line"></div>`).html(
						seg('Inv', invs, 'inv') + seg('Exp', exps, 'exp') + margin
					);
					$line.on('click', 'a.erp-fin-link', function (ev) {
						ev.preventDefault();
						ev.stopPropagation();
						if ($(this).data('kind') === 'inv') {
							frappe.route_options = { [cfg.inv_filter_field]: name };
							frappe.set_route('List', 'Sales Invoice', 'List');
						} else {
							frappe.route_options = { [cfg.en_filter_field]: name };
							frappe.set_route('List', 'Expense Note', 'List');
						}
					});
					$c.append($line);
				});
			});
		}

		return {
			onload(listview) {
				inject_style();
				render(listview);
			},
			refresh(listview) {
				inject_style();
				render(listview);
			},
		};
	};

frappe.listview_settings['Packing List'] = window.erp_fin_list_setup({
	source_doctype: 'Packing List',
	inv_filter_field: 'custom_packing_list',
	en_filter_field: 'packing_list',
});

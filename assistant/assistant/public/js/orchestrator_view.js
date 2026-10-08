// Tampilan halaman Orchestrator (konsol Controller/Admin) dan Laporan Saya (semua user):
// satu kode, dua mode, supaya perbaikan tampilan berlaku di keduanya.
//   mode 'admin' = Orchestrator: semua tab, tampilan Tim/Uji Diam/Saran, perancang workflow.
//   mode 'user'  = Laporan Saya: hanya milik user sendiri (temuan, task, rantai), walau dibuka manager.
// Hak sebenarnya tetap dicek di server (orchestrator.py, audit.py, advisor.py, chain.py).
// Dimuat lewat frappe.require oleh page/orchestrator dan page/laporan_saya.
window.cmi_orchestrator_view = function (wrapper, mode) {
	const admin = mode === 'admin';
	const page = frappe.ui.make_app_page({ parent: wrapper, title: admin ? __('Orchestrator') : __('Laporan Saya'), single_column: true });
	// Tampilan dimuat sesudah route berganti, jadi breadcrumb bawaan sudah digambar tanpa judul.
	const crumb = () => frappe.breadcrumbs.add({ type: 'Custom', label: admin ? __('Orchestrator') : __('Laporan Saya'),
		route: admin ? '/app/orchestrator' : '/app/laporan-saya' });
	crumb();
	const M = 'assistant.assistant.orchestrator.';
	const esc = frappe.utils.escape_html;
	const TONE = { Critical: 'red', High: 'red', Medium: 'orange', Low: 'gray', Open: 'orange', 'In Progress': 'blue', Resolved: 'green',
		Email: 'blue', Fleet: 'purple', Job: 'orange', Document: 'cyan', Audit: 'pink', Chain: 'blue', Advisor: 'green', Manual: 'gray' };
	const ADV = 'assistant.assistant.advisor.';
	const A = 'assistant.assistant.audit.';
	const REPORT_ROWS = 30;
	const STATUS = { Open: __('Menunggu action'), 'In Progress': __('Ditangani'), Resolved: __('Selesai') };
	const KIND = { event: __('Kejadian'), notify: __('Notifikasi'), escalate: __('Eskalasi'), action: __('Action'),
		note: __('Langkah'), agent: __('Agent'), resolve: __('Selesai') };
	const SOURCES = ['Email', 'Fleet', 'Job', 'Document', 'Audit', 'Chain', 'Advisor', 'Manual'];
	// Peta lebih dari ini tidak terbaca lagi; yang paling mendesak didahulukan (rows sudah urut severity).
	const MAP_LIMIT = 150;
	// Pasang di .layout-main-section (punya padding bawaan desk), sama seperti halaman Assistant Administrator.
	let $main = $(wrapper).find('.layout-main-section');
	if (!$main.length) $main = $(page.main || page.body);
	const st = { todo: null, chains: null, scope: admin ? 'report' : 'todo', rview: 'mine', report: null, showAll: false, rows: [], current: null, manager: false, users: {}, fetched: Date.now(), wf: null,
		workflows: [], escalation_run: {}, activity: [], who: 'all',
		map: { off: new Set(), escalated: false } };

	$(`<style>
		.orc{display:flex;flex-direction:column;gap:16px;padding:8px 16px 24px}
		.orc-kpi{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
		.orc-k{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:10px 14px;display:flex;align-items:baseline;gap:10px}
		.orc-k b{font-size:20px;font-weight:600;line-height:1.2}
		.orc-k span{color:var(--text-muted);font-size:12.5px}
		.orc-k.warn b{color:var(--red-600)}
		.orc-tabs{display:flex;gap:22px;border-bottom:1px solid var(--border-color)}
		.orc-tab{padding:8px 2px;margin-bottom:-1px;color:var(--text-muted);border:0;border-bottom:2px solid transparent;background:none;cursor:pointer;font-weight:500}
		.orc-tab.on{color:var(--text-color);border-bottom-color:var(--text-color)}
		.orc-body{display:flex;gap:16px;align-items:flex-start}
		.orc-list{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
		.orc-row{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:10px 14px;cursor:pointer;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:4px 12px;align-items:center;text-align:left;width:100%;color:inherit}
		.orc-row:hover{border-color:var(--gray-400)}
		.orc-row.on{border-color:var(--text-color);box-shadow:0 0 0 1px var(--text-color)}
		.orc-row .sub{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.orc-row .end{display:flex;gap:8px;align-items:center;justify-self:end;font-size:12px;color:var(--text-muted);white-space:nowrap}
		.orc-row .orc-meta,.orc-row .res{grid-column:2 / 4}
		.orc-meta{display:flex;gap:6px 14px;flex-wrap:wrap;font-size:12px;color:var(--text-muted)}
		.orc-late{color:var(--red-600);font-weight:500}
		.orc-side{width:420px;flex-shrink:0;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:14px;position:sticky;top:70px;max-height:calc(100vh - 90px);overflow:auto}
		.orc-side .ttl{font-size:15px;font-weight:600;line-height:1.35}
		.orc-dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;font-size:12.5px}
		.orc-dl dt{color:var(--text-muted);font-weight:400}
		.orc-dl dd{margin:0;overflow:hidden;text-overflow:ellipsis}
		.orc-sec{display:flex;flex-direction:column;gap:6px;padding-top:12px;border-top:1px solid var(--border-color)}
		.orc-sec h6{margin:0;font-size:12px;color:var(--text-muted);font-weight:500;display:flex;justify-content:space-between;align-items:center}
		.orc-txt{white-space:pre-line;line-height:1.5;font-size:13px}
		.orc-btns{display:flex;gap:6px;flex-wrap:wrap}
		.orc-acts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
		.orc-log{display:flex;flex-direction:column;gap:10px;font-size:12px}
		.orc-log div{display:grid;grid-template-columns:76px minmax(0,1fr);gap:8px;align-items:start}
		.orc-log .t{color:var(--text-muted)}
		.orc-empty{padding:30px;text-align:center;color:var(--text-muted);background:var(--card-bg);border:1px dashed var(--border-color);border-radius:10px}
		.orc-map{position:relative;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;overflow:hidden}
		.orc-map-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 12px;border-bottom:1px solid var(--border-color);font-size:12px}
		.orc-chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;border:1px solid var(--border-color);background:var(--card-bg);color:var(--text-color);cursor:pointer;font-size:12px}
		.orc-chip.off{opacity:.45}
		.orc-chip.on{background:var(--text-color);color:var(--card-bg);border-color:var(--text-color)}
		.orc-chip i,.orc-legend i{display:inline-block;width:9px;height:9px;border-radius:50%}
		.orc-map svg{display:block;width:100%;height:560px;touch-action:none;cursor:grab}
		.orc-map text{font-size:11px;fill:var(--text-color);pointer-events:none}
		.orc-map g.n{cursor:pointer}
		.orc-tip{position:absolute;pointer-events:none;background:var(--card-bg);border:1px solid var(--border-color);border-radius:8px;padding:6px 10px;font-size:12px;line-height:1.4;max-width:280px;box-shadow:var(--shadow-md);display:none}
		.orc-legend{display:flex;gap:6px 16px;flex-wrap:wrap;padding:8px 12px;border-top:1px solid var(--border-color);font-size:12px;color:var(--text-muted);align-items:center}
		.orc-legend i{margin-right:5px;vertical-align:-1px}
		.orc-wide .orc-side{display:none}
		.orc-wf{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
		.orc-wf.off{opacity:.65}
		.orc-wf-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
		.orc-wf-head b{font-size:14px;margin-right:4px}
		.orc-wf-nums{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;font-size:12px;color:var(--text-muted)}
		.orc-wf-nums b{display:block;font-size:16px;color:var(--text-color);font-weight:600}
		.orc-bar{display:flex;gap:8px 14px;align-items:center;flex-wrap:wrap;font-size:12.5px;color:var(--text-muted)}
		.orc-bar .btn{margin-left:auto}
		.orc-err{color:var(--red-600)}
		.orc-act{display:grid;grid-template-columns:110px minmax(0,1fr);gap:4px 12px;padding:10px 14px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;font-size:12.5px}
		.orc-act .t{color:var(--text-muted)}
		.orc-act .who{font-weight:600}
		.orc-prev{display:flex;flex-direction:column;gap:6px;font-size:12.5px}
		.orc-prev div{padding:6px 10px;border:1px solid var(--border-color);border-radius:8px}
		@media (max-width: 991px){.orc-wf-nums{grid-template-columns:repeat(2,minmax(0,1fr))}.orc-act{grid-template-columns:1fr}}
		.orc-rep{display:flex;flex-direction:column;gap:12px}
		.orc-chain{background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
		.orc-chain.stop{border-color:var(--red-500)}
		.orc-chain-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
		.orc-chain-steps{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap}
		.orc-step{flex:1 1 180px;min-width:0;border:1px solid var(--border-color);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:4px;font-size:12.5px}
		.orc-step.user{border-style:dashed}
		.orc-step .who{font-size:11.5px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em}
		.orc-arrow{align-self:center;color:var(--text-muted);flex:0 0 auto}
		.orc-rep-sum{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:12px 16px}
		.orc-rep-sum b{display:block;font-size:18px;font-weight:600;font-variant-numeric:tabular-nums}
		.orc-rep-sum span{font-size:12px;color:var(--text-muted)}
		.orc-rep h5{margin:6px 0 0;font-size:13px;font-weight:600}
		.orc-rep-row{display:grid;grid-template-columns:120px minmax(0,1fr) auto;gap:6px 14px;align-items:start;background:var(--card-bg);border:1px solid var(--border-color);border-radius:10px;padding:12px 14px}
		.orc-rep-row .tags{display:flex;flex-direction:column;gap:4px;align-items:flex-start;font-size:11.5px;color:var(--text-muted)}
		.orc-rep-row .body{display:flex;flex-direction:column;gap:3px;min-width:0;font-size:13px}
		.orc-rep-row .body b{font-weight:600}
		.orc-rep-row .prep{color:var(--text-muted)}
		.orc-rep-row .acts{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
		.orc-rep-new{color:var(--blue-600);font-weight:600}
		.orc-rep-checks{width:100%;font-size:12.5px;border-collapse:collapse;background:var(--card-bg)}
		.orc-rep-checks th,.orc-rep-checks td{padding:7px 10px;border-bottom:1px solid var(--border-color);text-align:left}
		.orc-rep-checks td.n{text-align:right;font-variant-numeric:tabular-nums}
		@media (max-width: 767px){.orc-rep-row{grid-template-columns:1fr}.orc-rep-row .tags{flex-direction:row;align-items:center}.orc-rep-row .acts{justify-content:flex-start}.orc-rep-sum{grid-template-columns:repeat(2,minmax(0,1fr))}}
		@media (max-width: 991px){.orc-body{flex-direction:column}.orc-side{width:100%;position:static;max-height:none}.orc-kpi{grid-template-columns:repeat(2,minmax(0,1fr))}}
	</style>`).appendTo($main);

	const $root = $(`<div class="orc">
		<div class="orc-kpi"></div>
		<div class="orc-tabs" role="tablist"></div>
		<div class="orc-body"><div class="orc-list"></div><aside class="orc-side"></aside></div>
	</div>`).appendTo($main);

	page.set_secondary_action(__('Refresh'), () => load());
	if (admin) page.add_menu_item(__('Aturan Orchestrator'), () => frappe.set_route('Form', 'Assistant Settings'));

	const pill = (txt, tone) => `<span class="indicator-pill ${tone || 'gray'}">${esc(txt || '')}</span>`;
	const when = (s) => (s ? frappe.datetime.comment_when(s) : '');
	const formLink = (dt, dn, label) => `<a href="${frappe.utils.get_form_link(dt, dn)}" onclick="event.stopPropagation()">${esc(label || `${dt} ${dn}`)}</a>`;
	const refLink = (r) => (r.reference_name ? formLink(r.reference_doctype, r.reference_name) : '');
	// due_in dihitung server (menit); dikurangi waktu sejak data diambil supaya hitung mundur tetap jalan.
	function due(r) {
		if (r.status === 'Resolved' || r.due_in == null) return '';
		const mins = r.due_in - Math.floor((Date.now() - st.fetched) / 60000);
		return mins >= 0
			? `<span>${__('Eskalasi dalam {0} menit', [mins])}</span>`
			: `<span class="orc-late">${__('Lewat batas {0} menit', [-mins])}</span>`;
	}
	const levelPill = (r) => (r.escalation_level > 0 ? pill(__('Eskalasi: {0}', [r.level_label]), 'red') : '');

	function renderTabs() {
		const tabs = admin ? [['report', __('Laporan')], ['mine', __('Inbox Saya')]]
			: [['todo', __('Tugas Saya')], ['report', __('Temuan')], ['mine', __('Semua Task Saya')]];
		// Peta Kerja, Semua, Workflow, Aktivitas = alat Controller/Admin
		if (st.manager) tabs.push(['map', __('Peta Kerja')], ['all', __('Semua')]);
		tabs.push(['chain', __('Rantai')]);
		if (st.manager) tabs.push(['workflow', __('Workflow')], ['activity', __('Aktivitas')]);
		tabs.push(['knowledge', __('Pengetahuan')]);
		$root.find('.orc-tabs').html(tabs.map(([k, l]) => `<button type="button" role="tab" aria-selected="${st.scope === k}" class="orc-tab ${st.scope === k ? 'on' : ''}" data-k="${k}">${l}</button>`).join(''));
	}

	function renderKpi(c) {
		const k = [[c.open, __('menunggu action'), ''], [c.escalated, __('sudah dieskalasi'), c.escalated ? 'warn' : ''],
			[c.in_progress, __('sedang ditangani'), ''], [c.resolved_today, __('selesai hari ini'), '']];
		$root.find('.orc-kpi').html(k.map(([v, l, cls]) => `<div class="orc-k ${cls}"><b>${v || 0}</b><span>${l}</span></div>`).join(''));
	}

	function renderList() {
		$root.toggleClass('orc-wide', ['workflow', 'activity', 'report', 'chain', 'todo'].includes(st.scope));
		$root.find('.orc-kpi').toggle(!['report', 'chain', 'workflow', 'todo'].includes(st.scope));
		if (st.scope === 'todo') return renderTodo();
		if (st.scope === 'report') return renderReport();
		if (st.scope === 'chain') return renderChains();
		if (st.scope === 'map') return renderMap();
		if (st.scope === 'workflow') return renderWorkflows();
		if (st.scope === 'activity') return renderActivity();
		const $l = $root.find('.orc-list');
		const rows = st.wf ? st.rows.filter((r) => r.workflow === st.wf) : st.rows;
		const wfBar = st.wf ? `<div class="orc-bar">${__('Workflow: {0}', [esc(st.wf)])}<button type="button" class="btn btn-default btn-xs" data-wf-clear="1">${__('Tampilkan semua')}</button></div>` : '';
		if (!rows.length) {
			$l.html(wfBar + `<div class="orc-empty">${st.scope === 'knowledge' ? __('Belum ada task yang selesai.') : __('Tidak ada task yang menunggu. Semua beres.')}</div>`);
			return;
		}
		const kb = st.scope === 'knowledge';
		$l.html(wfBar + rows.map((r) => `<button type="button" class="orc-row ${st.current === r.name ? 'on' : ''}" data-name="${esc(r.name)}">
			${pill(r.severity, TONE[r.severity])}
			<span class="sub">${esc(r.subject)}</span>
			<span class="end">${pill(r.workflow || r.source, TONE[r.source])}<span>${when(kb ? r.resolved_at : r.event_at)}</span></span>
			<span class="orc-meta">
				<span>${esc(r.name)}</span>${refLink(r) ? `<span>${refLink(r)}</span>` : ''}
				<span>${esc(r.assigned_name || __('Belum ada pemegang'))}</span>
				${kb ? `<span>${esc(r.outcome || '')}</span>`
					: `<span>${esc(STATUS[r.status])}</span>${r.escalation_level > 0 ? `<span class="orc-late">${__('Eskalasi: {0}', [esc(r.level_label)])}</span>` : ''}${due(r)}`}
			</span>
			${kb && r.resolution ? `<span class="res orc-txt text-muted">${esc(r.resolution)}</span>` : ''}
		</button>`).join(''));
	}

	function renderDetail(d) {
		const $s = $root.find('.orc-side');
		if (!d) {
			$s.html(`<div class="text-muted">${st.scope === 'map' ? __('Klik titik event di peta untuk melihat detailnya.') : __('Pilih task untuk melihat detail.')}</div>`);
			return;
		}
		const open = d.status !== 'Resolved';
		const log = (d.log || []).slice().reverse().map((x) => `<div>
			<span>${pill(KIND[x.kind] || x.kind, x.kind === 'escalate' ? 'red' : x.kind === 'resolve' ? 'green' : 'gray')}</span>
			<span><span class="orc-txt">${esc(x.message || '')}</span><br><span class="t">${esc(x.actor === 'agent' ? 'Agent' : (st.users[x.actor] || x.actor || ''))}, ${when(x.at)}</span></span>
		</div>`).join('');
		$s.html(`
			<div class="orc-btns">${pill(d.severity, TONE[d.severity])}${pill(STATUS[d.status], TONE[d.status])}${pill(d.workflow || d.source, TONE[d.source])}${levelPill(d)}</div>
			<div class="ttl">${esc(d.subject)}</div>
			<dl class="orc-dl">
				<dt>${__('Task')}</dt><dd>${formLink('Agent Task', d.name, d.name)}</dd>
				${d.reference_name ? `<dt>${__('Dokumen')}</dt><dd>${refLink(d)}</dd>` : ''}
				<dt>${__('Pemegang')}</dt><dd>${esc(d.assigned_name || __('Belum ada pemegang'))}</dd>
				${open && due(d) ? `<dt>${__('Batas')}</dt><dd>${due(d)}</dd>` : ''}
			</dl>
			${open ? `<div class="orc-acts">
				${d.status === 'Open' ? `<button class="btn btn-primary btn-sm" data-act="ack">${__('Tangani')}</button>` : ''}
				<button class="btn ${d.status === 'Open' ? 'btn-default' : 'btn-primary'} btn-sm" data-act="resolve">${__('Selesai')}</button>
				<button class="btn btn-default btn-sm" data-act="note">${__('Catat Langkah')}</button>
				<button class="btn btn-default btn-sm" data-act="reassign">${__('Oper')}</button>
			</div>` : ''}
			<div class="orc-sec"><h6>${__('Kejadian')}</h6><div class="orc-txt">${esc(d.description || '')}</div></div>
			<div class="orc-sec"><h6>${__('Analisa Agent')}${open ? `<button class="btn btn-default btn-xs" data-act="agent">${d.agent_note ? __('Analisa ulang') : __('Minta analisa')}</button>` : ''}</h6>
				<div class="orc-txt ${d.agent_note ? '' : 'text-muted'}">${esc(d.agent_note || __('Belum ada analisa.'))}</div></div>
			${!open ? `<div class="orc-sec"><h6>${__('Penyelesaian')}</h6><div class="orc-txt"><b>${esc(d.outcome || '')}</b>: ${esc(d.resolution || '')}</div></div>` : ''}
			<div class="orc-sec"><h6>${__('Riwayat')}</h6><div class="orc-log">${log}</div></div>`);
	}

	// --- Peta Kerja: graf event <-> user <-> dokumen, dikelompokkan per sumber ----------------
	// ponytail: simulasi gaya O(n^2) per frame; aman sampai MAP_LIMIT event, pakai d3-force kalau mau ribuan.
	const SRC_COLOR = { Email: '#1a5a9c', Fleet: '#5b34a8', Job: '#a14b0e', Document: '#0e7c86', Audit: '#a3266b', Chain: '#2f6fb0', Advisor: '#2e7d4f', Manual: '#6b6b6b' };
	const SEV_COLOR = { Critical: '#b42318', High: '#d92d20', Medium: '#f79009', Low: '#98a2b3' };
	const graph = { nodes: new Map(), links: [], frames: 0, raf: null, drag: null, moved: false };
	const NS = 'http://www.w3.org/2000/svg';
	const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
	const cut = (t, n) => (t && t.length > n ? t.slice(0, n - 1) + '...' : t || '');

	function mapRows() {
		const rows = st.rows.filter((r) => !st.map.off.has(r.source) && (!st.map.escalated || r.escalation_level > 0));
		return { rows: rows.slice(0, MAP_LIMIT), total: rows.length };
	}

	function renderMapBar($m) {
		const { rows, total } = mapRows();
		$m.find('.orc-map-bar').html(`
			${SOURCES.map((s) => `<button type="button" class="orc-chip ${st.map.off.has(s) ? 'off' : ''}" data-src="${s}" aria-pressed="${!st.map.off.has(s)}"><i style="background:${SRC_COLOR[s]}"></i>${s}</button>`).join('')}
			<button type="button" class="orc-chip ${st.map.escalated ? 'on' : ''}" data-esc="1" aria-pressed="${st.map.escalated}">${__('Hanya yang dieskalasi')}</button>
			<span class="text-muted" style="margin-left:auto">${total > rows.length
				? __('{0} dari {1} event, paling mendesak dulu. Persempit dengan filter.', [rows.length, total])
				: __('{0} event', [total])}</span>`);
	}

	function renderMap() {
		const $l = $root.find('.orc-list');
		if (!st.rows.length) { $l.html(`<div class="orc-empty">${__('Tidak ada event yang sedang dikerjakan.')}</div>`); return; }
		let $m = $l.find('.orc-map');
		if (!$m.length) {
			$l.html(`<div class="orc-map"><div class="orc-map-bar"></div>
				<svg aria-label="${__('Peta Kerja')}"><g class="l"></g><g class="g"></g></svg>
				<div class="orc-tip"></div>
				<div class="orc-legend">
					<span><i style="background:#171717"></i>${__('User')}</span>
					<span><i style="background:#d0d5dd"></i>${__('Dokumen')}</span>
					<span><i style="background:${SEV_COLOR.High}"></i>${__('Event, warna = severity')}</span>
					<span>${__('Garis putus = belum ada pemegang. Cincin merah = dieskalasi, biru = sedang ditangani.')}</span>
				</div></div>`);
			$m = $l.find('.orc-map');
			bindDrag($m.find('svg')[0], $m.find('.orc-tip'));
		}
		renderMapBar($m);
		const svg = $m.find('svg')[0];
		const W = svg.clientWidth || 800, H = svg.clientHeight || 560;
		svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
		const old = graph.nodes, nodes = new Map(), links = [];
		const add = (id, o) => {
			if (!nodes.has(id)) {
				const p = old.get(id);
				nodes.set(id, Object.assign({ id, x: p ? p.x : W / 2 + (Math.random() - 0.5) * 200, y: p ? p.y : H / 2 + (Math.random() - 0.5) * 200, vx: 0, vy: 0 }, o));
			}
			return nodes.get(id);
		};
		mapRows().rows.forEach((r) => {
			const t = 't:' + r.name;
			add('s:' + r.source, { kind: 'source', label: r.source, r: 22, color: SRC_COLOR[r.source] || '#6b6b6b' });
			add(t, { kind: 'task', label: cut(r.subject, 34), row: r, r: { Critical: 12, High: 10, Medium: 8, Low: 7 }[r.severity] || 8,
				color: SEV_COLOR[r.severity] || '#98a2b3',
				tip: `<b>${esc(r.subject)}</b><br>${esc(r.name)}, ${esc(STATUS[r.status])}${r.escalation_level > 0 ? `, ${__('Eskalasi: {0}', [esc(r.level_label)])}` : ''}<br>${esc(r.assigned_name || __('Belum ada pemegang'))}` });
			links.push({ a: 's:' + r.source, b: t, len: 80 });
			// pemegang = garis penuh; belum ada pemegang = garis putus ke semua yang dikabari
			const people = r.assigned_to ? [r.assigned_to] : (r.watchers || '').split('\n').filter(Boolean);
			people.forEach((u) => {
				add('u:' + u, { kind: 'user', label: cut(st.users[u] || u, 20), r: 14, color: '#171717', tip: esc(st.users[u] || u) });
				links.push({ a: t, b: 'u:' + u, len: 100, dash: !r.assigned_to });
			});
			if (r.reference_name) {
				const d = 'd:' + r.reference_doctype + '/' + r.reference_name;
				add(d, { kind: 'doc', r: 5, color: '#d0d5dd', route: [r.reference_doctype, r.reference_name],
					tip: `${esc(r.reference_doctype)} ${esc(r.reference_name)}` });
				links.push({ a: t, b: d, len: 45 });
			}
		});
		graph.nodes = nodes; graph.links = links;
		drawMap(svg);
		graph.frames = 0;
		if (!graph.raf) graph.raf = requestAnimationFrame(step);
	}

	function drawMap(svg) {
		const gl = svg.querySelector('g.l'), gn = svg.querySelector('g.g');
		gl.innerHTML = ''; gn.innerHTML = '';
		graph.links.forEach((k) => {
			k.el = svgEl('line', { stroke: '#c0c4cc', 'stroke-width': 1.2 });
			if (k.dash) k.el.setAttribute('stroke-dasharray', '4 4');
			gl.appendChild(k.el);
		});
		graph.nodes.forEach((n) => {
			const g = svgEl('g', { class: 'n' });
			const row = n.row || {};
			const picked = n.kind === 'task' && st.current === row.name;
			const c = svgEl('circle', { r: n.r, fill: n.color });
			if (n.kind === 'task') {
				const ring = picked ? ['#171717', 3]
					: row.escalation_level > 0 ? ['#b42318', 3]
					: row.status === 'In Progress' ? ['#1a5a9c', 3] : ['#ffffff', 1.5];
				c.setAttribute('stroke', ring[0]); c.setAttribute('stroke-width', ring[1]);
			}
			g.appendChild(c);
			if (n.kind === 'user') {
				const ini = svgEl('text', { 'text-anchor': 'middle', dy: 4, style: 'fill:#fff;font-weight:600;font-size:10.5px' });
				ini.textContent = n.label.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
				g.appendChild(ini);
			}
			// Label hanya untuk sumber, user, dan event yang dipilih; sisanya lewat tooltip supaya tidak tumpuk.
			if (n.kind === 'source' || n.kind === 'user' || picked) {
				const tx = svgEl('text', { 'text-anchor': 'middle', dy: n.r + 13 });
				tx.textContent = n.label;
				if (n.kind === 'source') tx.setAttribute('style', 'font-weight:600;font-size:12px');
				if (picked) tx.setAttribute('style', 'font-weight:600');
				g.appendChild(tx);
			}
			n.el = g; g.__node = n;
			gn.appendChild(g);
		});
		place();
	}

	function place() {
		graph.links.forEach((k) => {
			const a = graph.nodes.get(k.a), b = graph.nodes.get(k.b);
			k.el.setAttribute('x1', a.x); k.el.setAttribute('y1', a.y); k.el.setAttribute('x2', b.x); k.el.setAttribute('y2', b.y);
		});
		graph.nodes.forEach((n) => n.el.setAttribute('transform', `translate(${n.x},${n.y})`));
	}

	function step() {
		graph.raf = null;
		const svg = $root.find('.orc-map svg')[0];
		if (!svg || st.scope !== 'map') return;
		const W = svg.clientWidth || 800, H = svg.clientHeight || 560;
		const ns = [...graph.nodes.values()];
		for (let i = 0; i < ns.length; i++) {
			for (let j = i + 1; j < ns.length; j++) {
				const a = ns[i], b = ns[j];
				let dx = b.x - a.x, dy = b.y - a.y;
				const d2 = dx * dx + dy * dy || 0.01, d = Math.sqrt(d2), f = 1200 / d2;
				dx /= d; dy /= d;
				a.vx -= dx * f; a.vy -= dy * f; b.vx += dx * f; b.vy += dy * f;
			}
		}
		graph.links.forEach((k) => {
			const a = graph.nodes.get(k.a), b = graph.nodes.get(k.b);
			const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
			const f = (d - k.len) * 0.02;
			a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
		});
		ns.forEach((n) => {
			if (n === graph.drag) return;
			n.vx += (W / 2 - n.x) * 0.002; n.vy += (H / 2 - n.y) * 0.003;
			n.vx *= 0.82; n.vy *= 0.82;
			n.x = Math.max(n.r + 4, Math.min(W - n.r - 4, n.x + n.vx));
			n.y = Math.max(n.r + 4, Math.min(H - n.r - 18, n.y + n.vy));
		});
		place();
		if (++graph.frames < 400 || graph.drag) graph.raf = requestAnimationFrame(step);
	}

	function bindDrag(svg, $tip) {
		const pt = (e) => {
			const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
			return { x: (e.clientX - r.left) * (vb.width / r.width), y: (e.clientY - r.top) * (vb.height / r.height) };
		};
		svg.addEventListener('pointerover', (e) => {
			const g = e.target.closest('g.n');
			if (!g || !g.__node.tip || graph.drag) return;
			const n = g.__node;
			$tip.html(n.tip).css({ left: Math.min(n.x + 16, svg.clientWidth - 290), top: n.y + svg.offsetTop - 10 }).show();
		});
		svg.addEventListener('pointerout', (e) => { if (e.target.closest('g.n')) $tip.hide(); });
		svg.addEventListener('pointerdown', (e) => {
			const g = e.target.closest('g.n');
			if (!g) return;
			$tip.hide();
			graph.drag = g.__node; graph.moved = false;
			svg.setPointerCapture(e.pointerId);
			graph.frames = 0;
			if (!graph.raf) graph.raf = requestAnimationFrame(step);
		});
		svg.addEventListener('pointermove', (e) => {
			if (!graph.drag) return;
			const p = pt(e);
			graph.moved = true;
			Object.assign(graph.drag, { x: p.x, y: p.y, vx: 0, vy: 0 });
		});
		// pointer capture membuat click jatuh ke <svg>, jadi klik titik (tanpa geser) ditangani di sini
		const up = () => {
			const n = graph.drag;
			graph.drag = null;
			if (!n || graph.moved) return;
			if (n.kind === 'task') { open(n.row.name); drawMap(svg); }
			else if (n.kind === 'doc') frappe.set_route('Form', n.route[0], n.route[1]);
		};
		svg.addEventListener('pointerup', up);
		svg.addEventListener('pointercancel', up);
	}

	// --- Workflow: daftar + status putaran terakhir + perancang ---------------------------

	const mins = (m) => (m == null ? '-' : m < 60 ? __('{0} menit', [Math.round(m)])
		: m < 1440 ? __('{0} jam', [Math.round(m / 60)]) : __('{0} hari', [Math.round(m / 1440)]));

	function runLine(run, enabled) {
		if (!run || !run.at) return `<span>${enabled ? __('Belum pernah jalan') : __('Mati, tidak dijalankan')}</span>`;
		if (run.error) return `<span class="orc-err">${__('Gagal {0}: {1}', [when(run.at), esc(run.error)])}</span>`;
		return `<span>${__('Terakhir jalan {0}: dicek {1}, task baru {2}, ditutup otomatis {3}',
			[when(run.at), run.checked || 0, run.new || 0, run.resolved || 0])}</span>`;
	}

	function renderWorkflows() {
		const $l = $root.find('.orc-list');
		const er = st.escalation_run || {};
		const sw = st.switches || {};
		const off = sw.enabled === false ? __('Orchestrator dimatikan') : sw.audit_enabled === false ? __('Pemeriksaan dimatikan') : '';
		const head = (off ? `<div class="orc-empty orc-err" style="padding:10px">${__('{0} di ERPNext Custom Setting > tab Orchestrator. Workflow di bawah tidak dijalankan scheduler.', [off])}
			<a href="/app/erpnext-custom-setting">${__('Buka setting')}</a></div>` : '') + `<div class="orc-bar">
			<span>${__('Email dicek tiap menit; Fleet, Job, workflow Document, dan pemeriksaan tiap 15 menit. Laporan pemeriksaan dikirim tiap pagi jam 07.00.')}</span>
			${er.at ? `<span>${__('Pemeriksa eskalasi jalan {0}', [when(er.at)])}</span>` : ''}
			${st.manager ? `<button type="button" class="btn btn-primary btn-sm" data-wf="new">${__('Workflow Baru')}</button>` : ''}
		</div>`;
		if (!st.workflows.length) { $l.html(head + `<div class="orc-empty">${__('Belum ada workflow.')}</div>`); return; }
		$l.html(head + st.workflows.map((w) => {
			const doc = w.source === 'Document', audit = w.source === 'Audit';
			const btn = (act, label) => `<button type="button" class="btn btn-default btn-xs" data-wf="${act}" data-name="${esc(w.name)}">${label}</button>`;
			return `<div class="orc-wf ${w.enabled ? '' : 'off'}">
				<div class="orc-wf-head"><b>${esc(w.label)}</b>${pill(doc ? w.document_type : w.source, TONE[w.source])}${audit && w.shadow ? pill(__('Uji Diam'), 'yellow') : ''}${audit && !w.shadow && w.autonomy === 'Otomatis' ? pill(__('Otomatis'), 'purple') : ''}
					${pill(w.enabled ? __('Aktif') : __('Mati'), w.enabled ? 'green' : 'gray')}${pill(w.severity, TONE[w.severity])}</div>
				<div class="orc-bar">${runLine(w.run, w.enabled)}</div>
				<div class="orc-wf-nums">
					<span><b>${w.open}</b>${__('task terbuka')}</span>
					<span><b class="${w.escalated ? 'orc-err' : ''}">${w.escalated}</b>${__('dieskalasi')}</span>
					<span><b>${w.resolved}</b>${__('selesai 30 hari')}</span>
					<span><b>${mins(w.avg_minutes)}</b>${__('rata-rata sampai selesai')}</span>
				</div>
				<div class="orc-btns">
					${w.open ? btn('tasks', __('Lihat Task')) : ''}
					${st.manager ? btn('toggle', w.enabled ? __('Matikan') : __('Aktifkan')) : ''}
					${st.manager && doc ? btn('edit', __('Ubah')) + btn('run', __('Jalankan Sekarang')) + btn('delete', __('Hapus')) : ''}
					${st.manager && audit ? btn('run', __('Jalankan Sekarang')) + btn('shadow', w.shadow ? __('Akhiri Uji Diam') : __('Kembali ke Uji Diam')) : ''}
					${st.manager && !doc ? btn('settings', __('Atur')) : ''}
				</div>
			</div>`;
		}).join(''));
	}

	function workflowAction(act, name) {
		const w = st.workflows.find((x) => x.name === name) || {};
		const done = () => load(true);
		if (act === 'new') return workflowDialog({});
		if (act === 'edit') return workflowDialog(w);
		if (act === 'settings') return frappe.set_route('Form', 'Assistant Settings');
		if (act === 'tasks') { st.wf = w.label; st.scope = st.manager ? 'all' : 'mine'; return load(); }
		if (act === 'toggle') return frappe.xcall(M + 'toggle_workflow', { name, enabled: w.enabled ? 0 : 1 }).then(done);
		if (act === 'shadow') {
			const msg = w.shadow ? __('Akhiri uji diam {0}? Temuan langsung masuk laporan PIC dan Setujui akan menjalankan perbaikan.', [esc(w.label)])
				: __('Kembalikan {0} ke uji diam? Temuan baru hanya terlihat Controller dan Admin.', [esc(w.label)]);
			return frappe.confirm(msg, () => frappe.xcall(A + 'toggle_shadow', { name, shadow: w.shadow ? 0 : 1 }).then(done));
		}
		if (act === 'run') {
			return frappe.xcall(M + 'run_workflow', { name }).then((r) => {
				frappe.show_alert(r && r.error ? { message: r.error, indicator: 'red' }
					: { message: __('Selesai: dicek {0}, task baru {1}', [(r && r.checked) || 0, (r && r.new) || 0]), indicator: 'green' });
				done();
			});
		}
		if (act === 'delete') {
			return frappe.confirm(__('Hapus workflow {0}? Task yang sudah ada tetap tersimpan.', [esc(w.label)]),
				() => frappe.xcall(M + 'delete_workflow', { name }).then(done));
		}
	}

	// Perancang workflow Document: DocType + filter (FilterGroup bawaan) + kondisi + ambang + PIC.
	function workflowDialog(w) {
		let filters = null;
		const d = new frappe.ui.Dialog({
			title: w.name ? __('Ubah Workflow') : __('Workflow Baru'),
			size: 'large',
			fields: [
				{ fieldtype: 'Section Break', label: __('Kapan task dibuat') },
				{ fieldname: 'workflow_name', fieldtype: 'Data', label: __('Nama Workflow'), reqd: 1 },
				{ fieldname: 'document_type', fieldtype: 'Link', options: 'DocType', label: __('DocType'), reqd: 1,
					get_query: () => ({ filters: { istable: 0, issingle: 0 } }), change: () => setDoctype(false) },
				{ fieldname: 'filter_area', fieldtype: 'HTML' },
				{ fieldname: 'doc_filters_json', fieldtype: 'Code', options: 'JSON', label: __('Filter (JSON)'), hidden: 1,
					description: __('Anda tidak punya akses baca DocType ini di desk, jadi filter ditulis sebagai JSON, contoh: [["docstatus", "=", 1]]') },
				{ fieldname: 'doc_condition', fieldtype: 'Code', options: 'Python', label: __('Kondisi Tambahan (Python, opsional)'),
					description: __('Per dokumen, contoh: doc.grand_total > 100000000. Field child table tidak tersedia.') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'date_field', fieldtype: 'Select', label: __('Field Tanggal'), options: [{ value: 'creation', label: 'creation' }], default: 'creation' },
				{ fieldname: 'threshold_hours', fieldtype: 'Int', label: __('Lewat Berapa Jam'), default: 0,
					description: __('Task dibuat kalau Field Tanggal sudah lewat sekian jam. 0 = langsung saat cocok filter.') },
				{ fieldname: 'subject_template', fieldtype: 'Data', label: __('Judul Task'),
					description: __('Jinja, contoh: PO {{ doc.name }} belum disetujui ({{ doc.supplier }})') },
				{ fieldname: 'message_template', fieldtype: 'Small Text', label: __('Isi Task (opsional)') },
				{ fieldname: 'fields_help', fieldtype: 'HTML' },
				{ fieldtype: 'Section Break', label: __('Siapa yang menangani') },
				{ fieldname: 'assign_field', fieldtype: 'Select', label: __('PIC dari Field Dokumen'), options: [''],
					description: __('Kosong = semua user dengan Role Penanggung Jawab.') },
				{ fieldname: 'handler_role', fieldtype: 'Link', options: 'Role', label: __('Role Penanggung Jawab') },
				{ fieldname: 'severity', fieldtype: 'Select', options: 'Low\nMedium\nHigh\nCritical', default: 'Medium', label: __('Severity') },
				{ fieldname: 'send_email', fieldtype: 'Check', label: __('Kirim Email'), default: 1 },
				{ fieldname: 'ai_note', fieldtype: 'Check', label: __('Agent Tulis Analisa') },
				{ fieldtype: 'Column Break' },
				{ fieldname: 'response_minutes', fieldtype: 'Int', label: __('Batas Action (menit)'), default: 240 },
				{ fieldname: 'progress_minutes', fieldtype: 'Int', label: __('Batas Selesai Sesudah Ditangani (menit)'), default: 1440 },
				{ fieldname: 'controller_role', fieldtype: 'Link', options: 'Role', label: __('Controller (Role)'), default: 'Orchestrator Controller' },
				{ fieldname: 'escalate_minutes', fieldtype: 'Int', label: __('Batas Controller (menit)'), default: 480 },
				{ fieldname: 'admin_role', fieldtype: 'Link', options: 'Role', label: __('Admin (Role)'), default: 'Orchestrator Admin' },
				{ fieldname: 'enabled', fieldtype: 'Check', label: __('Aktif') },
				{ fieldtype: 'Section Break', label: __('Hasil Uji') },
				{ fieldname: 'preview', fieldtype: 'HTML', options: `<div class="text-muted">${__('Klik Uji untuk melihat dokumen yang akan jadi task.')}</div>` },
			],
			primary_action_label: __('Simpan'),
			primary_action(v) {
				frappe.xcall(M + 'save_workflow', { data: values(v) }).then(() => {
					d.hide();
					frappe.show_alert({ message: __('Workflow disimpan'), indicator: 'green' });
					load(true);
				});
			},
			secondary_action_label: __('Uji'),
			secondary_action() {
				const v = d.get_values();
				if (!v) return;
				const $p = d.fields_dict.preview.$wrapper.html(`<div class="text-muted">${__('Menguji...')}</div>`);
				frappe.xcall(M + 'preview_workflow', { data: values(v) }).then((r) => {
					$p.html(`<div class="orc-prev">
						<b>${r.cut ? __('Lebih dari {0} dokumen cocok sekarang; ditampilkan 20 pertama.', [r.count])
							: __('{0} dokumen akan jadi task sekarang.', [r.count])}</b>
						${r.sample.map((x) => `<div><b>${esc(x.subject)}</b><br>${esc(x.message)}<br>
							<span class="text-muted">${esc(x.name)}, PIC: ${esc(x.holder)}</span></div>`).join('')}
					</div>`);
				}).catch(() => $p.empty());
			},
		});
		// FilterGroup memberi [doctype, field, operator, nilai, ...]; disimpan [field, operator, nilai].
		const values = (v) => {
			const out = { ...v, name: w.name || null,
				doc_filters: filters ? JSON.stringify(filters.get_filters().map((f) => f.slice(1, 4))) : (v.doc_filters_json || '[]') };
			delete out.doc_filters_json;
			return out;
		};

		let shown = null;
		function setDoctype(init) {
			const dt = d.get_value('document_type');
			// set_input saat membuka workflow juga memicu change: jangan buang filter yang baru dimuat
			if (!init && dt === shown) return;
			shown = dt;
			const $area = d.fields_dict.filter_area.$wrapper.empty();
			filters = null;
			if (!dt) return;
			frappe.xcall(M + 'doctype_fields', { doctype: dt }).then((m) => {
				if (d.get_value('document_type') !== dt) return;
				d.set_df_property('date_field', 'options', [{ value: 'creation', label: __('Dibuat (creation)') },
					{ value: 'modified', label: __('Diubah (modified)') }, ...m.dates]);
				d.set_df_property('assign_field', 'options', [{ value: '', label: '' }, { value: 'owner', label: __('Pembuat dokumen (owner)') },
					{ value: '_assign', label: __('Orang pertama di Assign To (_assign)') }, ...m.users]);
				d.fields_dict.fields_help.$wrapper.html(`<div class="text-muted small">${__('Field untuk Judul, Isi, dan Kondisi')}:
					${m.fields.map((f) => `doc.${esc(f)}`).join(', ')}</div>`);
				d.set_value('date_field', (init && w.date_field) || 'creation');
				d.set_value('assign_field', (init && w.assign_field) || '');
				const saved = init && w.doc_filters ? w.doc_filters : '[]';
				// FilterGroup bawaan membuang diam-diam filter yang field-nya tak boleh dibaca user:
				// tanpa akses baca, filter ditulis sebagai JSON supaya tidak hilang saat disimpan.
				d.set_df_property('doc_filters_json', 'hidden', m.can_read ? 1 : 0);
				if (!m.can_read) { d.set_value('doc_filters_json', saved); return; }
				frappe.model.with_doctype(dt, () => {
					$area.html(`<label class="control-label">${__('Filter')}</label><div class="orc-filter"></div>`);
					filters = new frappe.ui.FilterGroup({ parent: $area.find('.orc-filter'), doctype: dt, on_change: () => {} });
					let list = JSON.parse(saved);
					if (!Array.isArray(list)) list = Object.entries(list).map(([k, v]) => [k, ...(Array.isArray(v) ? v : ['=', v])]);
					if (list.length) filters.add_filters_to_filter_group(list.map((f) => [dt, ...f]));
				});
			});
		}

		d.show();
		if (w.name) {
			const skip = ['date_field', 'assign_field', 'document_type'];
			d.set_values(Object.fromEntries(Object.entries(w).filter(([k]) => d.fields_dict[k] && !skip.includes(k))));
			// set document_type terakhir, lalu setDoctype memuat filter tersimpan
			d.fields_dict.document_type.set_input(w.document_type);
			setDoctype(true);
		}
	}

	// --- Aktivitas: apa yang dikerjakan agent, sistem, dan user --------------------------

	function renderActivity() {
		const $l = $root.find('.orc-list');
		const chip = (k, l) => `<button type="button" class="orc-chip ${st.who === k ? 'on' : ''}" data-who="${k}" aria-pressed="${st.who === k}">${l}</button>`;
		const bar = `<div class="orc-bar">${chip('all', __('Semua'))}${chip('system', __('Agent dan Sistem'))}${chip('user', __('User'))}
			<span>${__('{0} aktivitas terakhir', [st.activity.length])}</span></div>`;
		if (!st.activity.length) { $l.html(bar + `<div class="orc-empty">${__('Belum ada aktivitas.')}</div>`); return; }
		$l.html(bar + st.activity.map((a) => {
			if (a.type === 'agent') {
				return `<div class="orc-act"><span class="t">${when(a.at)}</span>
					<span><span class="who">${esc(a.agent_name || __('Agent'))}</span> ${pill(a.channel || 'Chat', 'blue')}
					${a.subject ? `<b>${esc(a.subject)}</b>` : ''}<br><span class="orc-txt">${esc(a.message || '')}</span>
					${a.document || a.customer ? `<br><span class="t">${esc([a.document, a.customer].filter(Boolean).join(', '))}</span>` : ''}</span></div>`;
			}
			const who = a.actor === 'agent' ? __('Sistem') : (st.users[a.actor] || a.actor);
			return `<div class="orc-act"><span class="t">${when(a.at)}</span>
				<span><span class="who">${esc(who)}</span> ${pill(KIND[a.kind] || a.kind, a.kind === 'escalate' ? 'red' : a.kind === 'resolve' ? 'green' : 'gray')}
				<a href="#" data-task="${esc(a.task)}">${esc(a.subject || a.task)}</a>
				<span class="t">${esc(a.workflow || a.source || '')}</span><br><span class="orc-txt">${esc(a.message || '')}</span></span></div>`;
		}).join(''));
	}

	// --- Tugas Saya: semua yang harus dikerjakan user, dari sumber mana pun -------------------

	const TODO_LABEL = { Audit: __('Temuan'), Chain: __('Rantai'), Advisor: __('Saran'), Fleet: __('GPS'), Document: __('Dokumen'),
		Email: __('Email'), Job: __('Job'), Manual: __('Manual') };

	function renderTodo() {
		const $l = $root.find('.orc-list');
		const m = st.todo;
		if (!m) { $l.html(`<div class="orc-empty">${__('Memuat tugas...')}</div>`); return; }
		const b = (act, label, name, primary) => `<button type="button" class="btn ${primary ? 'btn-primary' : 'btn-default'} btn-xs" data-rep="${act}" data-name="${esc(name || '')}">${label}</button>`;
		const row = (r, waiting) => {
			let acts = '';
			if (!waiting && r.action === 'decide') acts = b('Setuju', __('Setujui'), r.name, true) + b('Koreksi', __('Koreksi'), r.name) + b('Tolak', __('Tolak'), r.name);
			if (!waiting && r.action === 'exception') acts = b('exc-yes', __('Setujui Pengecualian'), r.name, true) + b('exc-no', __('Tolak Pengecualian'), r.name);
			if (!waiting && r.action === 'open' && r.doc_name) acts = `<a class="btn btn-primary btn-xs" href="${frappe.utils.get_form_link(r.doc_doctype, r.doc_name)}">${__('Buka {0}', [esc(r.doc_name)])}</a>`;
			if (!waiting && r.action === 'go' && r.button) acts = b('go', esc(r.button), r.name, true);
			if (!waiting && r.action === 'finish') {
				acts = (r.doc_name ? `<a class="btn btn-default btn-xs" href="${frappe.utils.get_form_link(r.doc_doctype, r.doc_name)}">${__('Buka {0}', [esc(r.doc_name)])}</a>` : '')
					+ b('finish', __('Selesai'), r.name, true);
			}
			if (r.action === 'advice') acts = `<a class="btn btn-primary btn-xs" href="/app/orchestrator?view=advice">${__('Buka Saran Bulanan')}</a>`;
			if (!waiting && r.action === 'task' && r.status === 'Open' && r.name) acts = b('ack', __('Tangani'), r.name, true);
			if (r.name) acts += b('detail', __('Detail'), r.name);
			const late = r.escalation_level > 0 ? `<span class="orc-late">${__('Sudah dieskalasi ke {0}', [esc(r.level_label)])}</span>` : '';
			const hand = r.handed_by ? `<span>${__('Dioper oleh {0} {1}', [esc(r.handed_by), when(r.handed_at)])}</span>` : '';
			return `<div class="orc-rep-row">
				<div class="tags">${pill(TODO_LABEL[r.source] || r.source, TONE[r.source])}${r.severity && r.severity !== 'Medium' ? pill(r.severity, TONE[r.severity]) : ''}</div>
				<div class="body">
					<b>${esc(r.step)}</b>
					<span>${esc(r.subject || '')}</span>
					<span class="orc-meta">${r.workflow && r.workflow !== r.source ? `<span>${esc(r.workflow)}</span>` : ''}${r.reference_name ? `<span>${formLink(r.reference_doctype, r.reference_name)}</span>` : ''}
						${r.since ? `<span>${__('sejak {0}', [when(r.since)])}</span>` : ''}${hand}${late}</span>
				</div>
				<div class="acts">${acts}</div></div>`;
		};
		const head = `<div class="orc-rep-sum">
			<div><b>${m.todo.length}</b><span>${__('tugas yang harus Anda kerjakan')}</span></div>
			<div><b>${m.todo.filter((r) => r.escalation_level > 0).length}</b><span>${__('sudah dieskalasi')}</span></div>
			<div><b>${m.waiting.length}</b><span>${__('menunggu orang lain')}</span></div>
			<div><b>${m.done.length}</b><span>${__('selesai hari ini')}</span></div></div>`;
		const todo = m.todo.length ? m.todo.map((r) => row(r)).join('')
			: `<div class="orc-empty">${__('Tidak ada yang harus Anda kerjakan sekarang.')}</div>`;
		const waiting = m.waiting.length ? `<h5>${__('Menunggu orang lain')}</h5>${m.waiting.map((r) => row(r, true)).join('')}` : '';
		const done = m.done.length ? `<h5>${__('Selesai hari ini')}</h5><div class="orc-bar">${m.done.map((d) => esc(d.subject)).join(', ')}</div>` : '';
		$l.html(`<div class="orc-rep"><div class="orc-bar">${__('Semua yang harus Anda kerjakan, dari mana pun asalnya: temuan pemeriksaan, email customer, job, langkah validasi dari agent, dan task yang dioper ke Anda. Paling mendesak di atas.')}</div>
			${head}<h5>${__('Kerjakan')}</h5>${todo}${waiting}${done}
			<div class="orc-bar"><a href="/app/manual-laporan-saya">${__('Cara pakai')}</a></div></div>`);
	}

	// --- Rantai antar agent ----------------------------------------------------------------

	const ARROW = '<svg class="orc-arrow" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
	const SRC_DT = { Reimburse: 'Expense Note', Trading: 'Delivery Note', Pembelian: 'Purchase Invoice' };

	function renderChains() {
		const $l = $root.find('.orc-list');
		const m = st.chains;
		if (!m) { $l.html(`<div class="orc-empty">${__('Memuat rantai...')}</div>`); return; }
		const off = Object.entries(m.enabled || {}).filter(([, on]) => !on).map(([k]) => k);
		const bar = `<div class="orc-bar"><span>${__('Agent saling serah terima lewat Orchestrator. Agent hanya membuat draft dan memeriksa; validasi tetap oleh user.')}</span>
			${off.length ? `<span class="orc-err">${__('Mati: {0}.', [off.map((k) => __('Rantai {0}', [k])).join(', ')])} <a href="/app/erpnext-custom-setting">${__('Nyalakan di ERPNext Custom Setting > tab Orchestrator')}</a></span>` : ''}</div>`;
		if (!m.rows.length) { $l.html(bar + `<div class="orc-empty">${__('Belum ada rantai yang berjalan.')}</div>`); return; }
		const stepHtml = (s) => {
			const done = s.status === 'Resolved';
			const stopped = !done && s.agent_role !== 'User' && s.watchers;
			const state = done ? pill(__('Selesai'), 'green') : stopped ? pill(__('Berhenti, ke Controller'), 'red')
				: s.agent_role === 'User' ? pill(__('Menunggu user'), 'orange') : pill(__('Dikerjakan agent'), 'blue');
			return `<div class="orc-step ${s.agent_role === 'User' ? 'user' : ''}">
				<span class="who">${esc(s.agent_role === 'User' ? (st.users[s.assigned_to] || s.assigned_to || __('User')) : s.agent_role)}</span>
				<b>${esc(s.chain_step)}</b>${state}
				${s.reference_name ? `<span>${formLink(s.reference_doctype, s.reference_name, s.reference_name)}</span>` : ''}
				${s.resolution ? `<span class="text-muted">${esc(s.resolution)}</span>` : ''}
				<a href="#" data-task="${esc(s.name)}" class="text-muted">${esc(s.name)}</a>
			</div>`;
		};
		$l.html(bar + m.rows.map((c) => `<div class="orc-chain ${c.stopped ? 'stop' : ''}">
			<div class="orc-chain-head"><b>${__('Rantai {0}', [esc(c.chain)])}</b>${formLink(SRC_DT[c.chain] || 'Expense Note', c.source, c.source)}
				<span class="text-muted">${when(c.at)}</span></div>
			<div class="orc-chain-steps">${c.steps.map(stepHtml).join(ARROW)}</div>
		</div>`).join(''));
	}
	$root.on('click', '.orc-chain [data-task]', function (e) { e.preventDefault(); st.scope = st.manager ? 'all' : 'mine'; st.current = this.dataset.task; load(); });

	// --- Laporan pemeriksaan: final check -------------------------------------------------

	const rupiah = (v) => format_currency(v || 0, 'IDR', 0);
	const FIX_DT = { draft_pi_from_po: 'Purchase Invoice', draft_si_from_dn: 'Sales Invoice', close_packing_list: 'Packing List' };

	function repRow(r, mode) {
		const b = (act, label, primary) => `<button type="button" class="btn ${primary ? 'btn-primary' : 'btn-default'} btn-xs" data-rep="${act}" data-name="${esc(r.name)}">${label}</button>`;
		let acts = '';
		if (mode === 'todo') acts = b('Setuju', __('Setujui'), true) + b('Koreksi', __('Koreksi')) + b('Tolak', __('Tolak'));
		if (mode === 'exception' && st.manager) acts = b('exc-yes', __('Setujui Pengecualian'), true) + b('exc-no', __('Tolak Pengecualian'));
		if ((mode === 'working' || mode === 'auto') && r.fix_result) acts = b('undo', __('Batalkan')) + acts;
		acts += b('detail', __('Detail dan Tanya Agent'));
		let state = '';
		if (mode === 'auto') {
			const res = r.fix_result && r.fix_kind ? formLink(FIX_DT[r.fix_kind], r.fix_result, r.fix_result) : '';
			state = `<span class="prep">${__('Dikerjakan agent atas nama {0}', [esc(r.assigned_name || '')])}${res ? `: ${res}` : ''}</span>`;
		}
		if (mode === 'working') {
			const res = r.fix_result && r.fix_kind ? `. ${__('Hasil')}: ${formLink(FIX_DT[r.fix_kind], r.fix_result, r.fix_result)}` : '';
			state = `<span class="prep">${esc(__('Keputusan: {0}', [r.decision]))}${r.decision_note ? `, ${esc(r.decision_note)}` : ''}${res}</span>`;
		}
		if (mode === 'exception') state = `<span class="prep">${esc(__('Alasan {0}: {1}', [r.assigned_name || '', r.decision_note || '']))}</span>`;
		const who = st.rview !== 'mine' ? `, ${esc(r.assigned_name || __('tanpa PIC, ke Controller'))}` : '';
		return `<div class="orc-rep-row">
			<div class="tags">${pill(r.confidence || '-', r.confidence === 'Pasti' ? 'green' : 'orange')}${r.undone ? pill(__('Pernah dibatalkan'), 'gray') : ''}<span>${esc(r.check_title || r.check)}</span><span>${esc(r.category || '')}</span></div>
			<div class="body">
				<b>${r.new ? `<span class="orc-rep-new">${__('Baru')}</span> ` : ''}${esc(r.subject)}</b>
				<span class="orc-txt">${esc(r.description || '')}</span>
				<span class="prep">${r.reference_name ? formLink(r.reference_doctype, r.reference_name) : ''}${r.amount ? `, ${rupiah(r.amount)}` : ''}, ${__('{0} hari', [r.age])}${who}</span>
				${state}
			</div>
			<div class="acts">${acts}</div>
		</div>`;
	}

	function renderAdvice() {
		const $l = $root.find('.orc-list');
		const m = st.advice;
		const chip = (k, l) => `<button type="button" class="orc-chip ${st.rview === k ? 'on' : ''}" data-rview="${k}" aria-pressed="${st.rview === k}">${l}</button>`;
		const bar = `<div class="orc-bar">${chip('mine', __('Temuan Saya'))}${chip('team', __('Tim'))}${chip('shadow', __('Uji Diam'))}${chip('advice', __('Saran Bulanan'))}
			<button type="button" class="btn btn-default btn-sm" data-adv="run">${__('Jalankan Tinjauan Sekarang')}</button></div>`;
		if (!m) { $l.html(`<div class="orc-rep">${bar}<div class="orc-empty">${__('Memuat saran...')}</div></div>`); return; }
		const off = m.enabled ? '' : `<div class="orc-bar">${__('Tinjauan bulanan otomatis mati (ERPNext Custom Setting > tab Orchestrator). Tombol Jalankan Tinjauan Sekarang tetap bisa dipakai.')}</div>`;
		const intro = `<div class="orc-bar">${__('Tanggal 1 tiap bulan agent meninjau bulan sebelumnya dan memberi saran dengan angka. Agent tidak mengubah data; Anda yang memutuskan.')}</div>`;
		const rows = m.rows.map((r) => `<div class="orc-rep-row">
			<div class="tags">${pill(r.category, 'green')}<span>${esc(r.since_date ? frappe.datetime.str_to_user(r.since_date).slice(3) : '')}</span></div>
			<div class="body"><b>${esc(r.subject)}</b><span class="orc-txt">${esc(r.description || '')}</span></div>
			<div class="acts">
				<button type="button" class="btn btn-primary btn-xs" data-adv="follow" data-name="${esc(r.name)}">${__('Tindak lanjuti')}</button>
				<button type="button" class="btn btn-default btn-xs" data-adv="ignore" data-name="${esc(r.name)}">${__('Abaikan')}</button>
				<button type="button" class="btn btn-default btn-xs" data-rep="detail" data-name="${esc(r.name)}">${__('Detail dan Tanya Agent')}</button>
			</div></div>`).join('');
		const useful = `<h5>${__('Kegunaan saran (12 bulan)')}</h5><div style="overflow-x:auto"><table class="orc-rep-checks">
			<tr><th>${__('Jenis saran')}</th><th>${__('Ditindaklanjuti')}</th><th>${__('Diabaikan')}</th></tr>
			${m.useful.map((u) => `<tr><td>${esc(u.title)}</td><td class="n">${u.follow}</td><td class="n">${u.ignore}</td></tr>`).join('')}</table></div>`;
		$l.html(`<div class="orc-rep">${bar}${off}${intro}${rows || `<div class="orc-empty">${__('Belum ada saran yang menunggu keputusan.')}</div>`}${useful}</div>`);
	}

	function adviceAction(act, name) {
		const done = (msg) => { if (msg) frappe.show_alert({ message: msg, indicator: 'green' }); load(true); };
		if (act === 'run') {
			return frappe.call({ method: ADV + 'run_month', args: { force: 1 }, freeze: true })
				.then((r) => done(__('Tinjauan {0}: {1} saran baru', [r.message.period, r.message.made])));
		}
		const follow = act === 'follow';
		frappe.prompt([
			{ fieldname: 'note', fieldtype: 'Small Text', reqd: 1, label: follow ? __('Tindakan yang akan diambil') : __('Kenapa diabaikan?') },
			...(follow ? [{ fieldname: 'assign_to', fieldtype: 'Link', options: 'User', label: __('Serahkan ke (opsional)'),
				description: __('Diisi = jadi task manual untuk orang itu, ikut eskalasi Orchestrator.') }] : []),
		], (v) => frappe.call({ method: ADV + 'decide', args: { task: name, decision: follow ? 'Tindak lanjuti' : 'Abaikan', note: v.note, assign_to: v.assign_to }, freeze: true })
			.then((r) => done(r.message ? __('Ditindaklanjuti, task {0} dibuat', [r.message]) : __('Keputusan dicatat'))),
		follow ? __('Tindak Lanjuti Saran') : __('Abaikan Saran'));
	}
	$root.on('click', '[data-adv]', function () { adviceAction(this.dataset.adv, this.dataset.name); });

	function renderReport() {
		if (st.rview === 'advice') return renderAdvice();
		const $l = $root.find('.orc-list');
		const m = st.report;
		if (!m) { $l.html(`<div class="orc-empty">${__('Memuat laporan...')}</div>`); return; }
		const s = m.summary;
		const chip = (k, l) => `<button type="button" class="orc-chip ${st.rview === k ? 'on' : ''}" data-rview="${k}" aria-pressed="${st.rview === k}">${l}</button>`;
		const bar = st.manager ? `<div class="orc-bar">${chip('mine', __('Temuan Saya'))}${chip('team', __('Tim'))}${chip('shadow', __('Uji Diam'))}${chip('advice', __('Saran Bulanan'))}
			${st.rview === 'team' && m.unassigned ? `<span>${__('{0} temuan tanpa PIC', [m.unassigned])}</span>` : ''}</div>` : '';
		const failed = (m.failed || []).map((f) => `<div class="orc-empty orc-err" style="padding:10px">${esc(__('Pemeriksaan tidak jalan: {0}. {1}', [f.check, f.error]))}</div>`).join('');
		const off = m.enabled ? '' : `<div class="orc-empty orc-err" style="padding:10px">${__('Pemeriksaan sedang dimatikan di ERPNext Custom Setting > tab Orchestrator. Temuan di bawah tidak diperbarui dan laporan harian tidak dikirim.')}</div>`;
		const intro = st.rview === 'shadow'
			? `<div class="orc-bar">${__('Uji diam: temuan ini belum dikirim ke user dan Setuju tidak menjalankan perbaikan. Putuskan beberapa untuk mengukur ketepatannya, lalu akhiri uji diam dari tab Workflow.')}</div>` : '';
		const sum = `<div class="orc-rep-sum">
			<div><b>${s.todo}</b><span>${__('perlu keputusan dari {0} temuan', [s.count])}</span></div>
			<div><b>${rupiah(s.amount)}</b><span>${__('nilai tertahan')}</span></div>
			<div><b>${__('{0} hari', [s.oldest])}</b><span>${__('temuan tertua')}</span></div>
			<div><b>${s.new} / ${s.resolved}</b><span>${s.since ? __('baru / beres sejak laporan {0}', [when(s.since)]) : __('baru / beres 24 jam terakhir')}</span></div>
		</div>`;
		const checks = m.checks ? `<h5>${__('Ketepatan per pemeriksaan (90 hari)')}</h5><div style="overflow-x:auto"><table class="orc-rep-checks">
			<tr><th>${__('Pemeriksaan')}</th><th>${__('Mode')}</th><th>${__('Terbuka')}</th><th>${__('Setuju')}</th><th>${__('Koreksi')}</th><th>${__('Tolak')}</th><th>${__('Batal')}</th><th>${__('Otomatis')}</th><th>${__('Tepat')}</th><th>${__('Naik ke Otomatis')}</th></tr>
			${m.checks.map((c) => `<tr><td>${esc(c.title)}<br><span class="text-muted">${esc(c.code)}</span></td>
				<td>${c.shadow ? __('Uji Diam') : esc(c.autonomy)}</td>
				<td class="n">${c.open}</td><td class="n">${c.Setuju}</td><td class="n">${c.Koreksi}</td><td class="n">${c.Tolak}</td><td class="n">${c.Batal}</td><td class="n">${c.Otomatis}</td>
				<td class="n">${c.total ? Math.round(100 * c.Setuju / c.total) + '%' : '-'}</td>
				<td>${c.autonomy === 'Otomatis'
					? (m.is_admin ? `<button type="button" class="btn btn-default btn-xs" data-rep="demote" data-name="${esc(c.name)}">${__('Kembali ke Final Check')}</button>` : __('Sudah otomatis'))
					: c.eligible
						? (m.is_admin ? `<button type="button" class="btn btn-primary btn-xs" data-rep="promote" data-name="${esc(c.name)}">${__('Jadikan Otomatis')}</button>` : __('Layak, menunggu Admin'))
						: `<span class="text-muted">${c.reasons.map(esc).join('<br>')}</span>`}</td></tr>`).join('')}</table></div>` : '';
		const legend = (m.legend || []).length ? `<details><summary class="text-muted" style="cursor:pointer">${__('Apa saja yang diperiksa')}</summary>
			<div style="overflow-x:auto;margin-top:8px"><table class="orc-rep-checks">${m.legend.map((c) => `<tr><td style="white-space:nowrap"><b>${esc(c.title)}</b><br><span class="text-muted">${esc(c.code)}${c.days ? `, ${__('tenggang {0} hari', [c.days])}` : ''}</span></td>
				<td>${esc(c.meaning)}</td></tr>`).join('')}</table></div></details>` : '';
		const todo = st.showAll ? m.todo : m.todo.slice(0, REPORT_ROWS);
		const more = m.todo.length > todo.length ? `<button type="button" class="btn btn-default btn-sm" data-rep="more">${__('Tampilkan {0} temuan lainnya', [m.todo.length - todo.length])}</button>` : '';
		const approve = s.approvable && st.rview === 'mine' ? `<div class="orc-bar"><span>${__('{0} temuan berlabel Pasti siap disetujui sekaligus.', [s.approvable])}</span>
			<button type="button" class="btn btn-primary btn-sm" data-rep="all">${__('Setujui Semua yang Pasti ({0})', [s.approvable])}</button></div>` : '';
		const section = (title, rows, mode) => (rows.length ? `<h5>${title}</h5>${rows.map((r) => repRow(r, mode)).join('')}` : '');
		const empty = !m.todo.length && !m.exceptions.length && !m.working.length && !(m.auto || []).length
			? `<div class="orc-empty">${st.rview === 'mine' ? __('Tidak ada temuan untuk Anda.') : __('Tidak ada temuan di sini.')}
				${Object.entries((st.manager && m.elsewhere) || {}).filter(([, n]) => n).map(([v, n]) => `<div style="margin-top:8px">${__('{0} temuan ada di', [n])}
					<button type="button" class="btn btn-default btn-xs" data-rview="${v}">${v === 'shadow' ? __('Uji Diam') : __('Tim')}</button></div>`).join('')}</div>` : '';
		const autoBar = s.auto ? `<div class="orc-bar">${__('{0} temuan dikerjakan agent otomatis sejak laporan lalu. Periksa di bagian Dikerjakan agent otomatis; Batalkan kalau salah.', [s.auto])}</div>` : '';
		const help = `<div class="orc-bar"><a href="/app/manual-laporan-saya">${__('Cara pakai laporan ini')}</a></div>`;
		$l.html(`<div class="orc-rep">${off}${bar}${intro}${failed}${sum}${autoBar}${approve}
			${section(__('Perlu keputusan'), todo, 'todo')}${more}
			${section(__('Menunggu persetujuan pengecualian'), m.exceptions, 'exception')}
			${section(__('Dikerjakan agent otomatis, menunggu dokumennya selesai'), m.auto || [], 'auto')}
			${section(__('Sudah diputuskan, menunggu dokumennya selesai'), m.working, 'working')}
			${empty}${checks}${legend}${help}</div>`);
	}

	function reportAction(act, name) {
		const done = (msg) => { if (msg) frappe.show_alert({ message: msg, indicator: 'green' }); load(true); };
		if (act === 'more') { st.showAll = true; return renderReport(); }
		if (act === 'undo') {
			return frappe.confirm(__('Batalkan hasil perbaikan ini? Draft dihapus atau Packing List dibuka lagi, dan temuan kembali ke final check. Kalau hasilnya dari mode Otomatis, pemeriksaan ini turun ke Final check.'), () =>
				frappe.call({ method: A + 'undo', args: { task: name }, freeze: true }).then((r) => done(r.message)));
		}
		if (act === 'promote') {
			return frappe.prompt({ fieldname: 'max_amount', fieldtype: 'Currency', label: __('Batas Nominal Otomatis'), default: 0,
				description: __('Temuan di atas nilai ini tetap ke final check. 0 = tanpa batas.') },
			(v) => frappe.call({ method: A + 'set_autonomy', args: { name, mode: 'Otomatis', max_amount: v.max_amount }, freeze: true })
				.then(() => done(__('Pemeriksaan sekarang Otomatis'))), __('Jadikan Otomatis'), __('Jadikan Otomatis'));
		}
		if (act === 'demote') {
			return frappe.call({ method: A + 'set_autonomy', args: { name, mode: 'Final check' }, freeze: true })
				.then(() => done(__('Pemeriksaan kembali ke Final check')));
		}
		if (act === 'detail') { st.scope = st.manager ? 'all' : 'mine'; st.current = name; return load(); }
		if (act === 'go') {
			const r = ((st.todo && st.todo.todo) || []).find((x) => x.name === name);
			if (!r) return;
			const go = () => {
				if (r.url) {
					const url = new URL(r.url, window.location.origin);
					frappe.route_options = Object.fromEntries(url.searchParams.entries());
					return frappe.set_route(url.pathname.replace(/^\/(desk|app)\//, ''));
				}
				frappe.set_route('Form', r.reference_doctype, r.reference_name);
			};
			return r.status === 'Open' ? frappe.xcall(M + 'ack', { task: name }).then(go) : go();
		}
		if (act === 'finish') {
			return frappe.prompt([
				{ fieldname: 'outcome', fieldtype: 'Select', label: __('Hasil'), options: ['Ditangani', 'Normal', 'Tidak Valid'], default: 'Ditangani', reqd: 1 },
				{ fieldname: 'resolution', fieldtype: 'Small Text', label: __('Catatan (opsional)'),
					description: __('Isi kalau caranya perlu diingat agent untuk kejadian serupa. Wajib kalau hasilnya Normal atau Tidak Valid.') },
			], (v) => frappe.call({ method: M + 'resolve', args: { task: name, outcome: v.outcome, resolution: v.resolution }, freeze: true })
				.then(() => done(__('Task selesai'))), __('Selesaikan Task'));
		}
		if (act === 'ack') return frappe.call({ method: M + 'ack', args: { task: name }, freeze: true }).then(() => done(__('Task Anda pegang. Kerjakan, lalu klik Selesai di Detail.')));
		if (act === 'all') {
			return frappe.confirm(__('Setujui semua temuan berlabel Pasti? Perbaikan yang disiapkan akan dijalankan.'), () =>
				frappe.call({ method: A + 'approve_all', freeze: true }).then((r) => {
					const x = r.message || {};
					if (x.failed && x.failed.length) frappe.msgprint({ title: __('Sebagian gagal'), message: x.failed.map(esc).join('<br>'), indicator: 'orange' });
					done(__('{0} temuan disetujui', [x.done || 0]));
				}));
		}
		if (act === 'exc-yes' || act === 'exc-no') {
			return frappe.call({ method: A + 'decide_exception', args: { task: name, approve: act === 'exc-yes' ? 1 : 0 }, freeze: true })
				.then(() => done(act === 'exc-yes' ? __('Pengecualian disetujui') : __('Pengecualian ditolak, temuan kembali ke PIC')));
		}
		const send = (note) => frappe.call({ method: A + 'decide', args: { task: name, decision: act, note }, freeze: true }).then((r) => done(r.message));
		if (act === 'Setuju') return send();
		frappe.prompt({ fieldname: 'note', fieldtype: 'Small Text', reqd: 1,
			label: act === 'Tolak' ? __('Kenapa temuan ini salah atau tidak perlu?') : __('Apa yang perlu dikoreksi?'),
			description: act === 'Tolak' ? __('Pengecualian berlaku setelah disetujui Controller, dan dibuka lagi kalau kondisinya berubah.') : '' },
		(v) => send(v.note), act === 'Tolak' ? __('Tolak Temuan') : __('Koreksi Temuan'));
	}

	// --- data & aksi ----------------------------------------------------------------------

	function call(method, args) {
		return frappe.call({ method: M + method, args, freeze: true }).then((r) => {
			if (r && r.message && r.message.name) renderDetail(r.message);
			load(true);
			return r && r.message;
		});
	}

	function open(name) {
		st.current = name;
		$root.find('.orc-row').removeClass('on').filter(function () { return this.dataset.name === name; }).addClass('on');
		frappe.call({ method: M + 'get_task', args: { task: name } }).then((r) => renderDetail(r.message));
	}

	function load(keepDetail) {
		const scope = st.scope === 'map' ? (st.manager ? 'all' : 'mine')
			: ['workflow', 'activity', 'report', 'chain', 'todo'].includes(st.scope) ? 'mine' : st.scope;
		const extra = st.scope === 'todo' ? frappe.xcall(M + 'my_tasks').then((m) => { st.todo = m; })
			: st.scope === 'report' && st.rview === 'advice' ? frappe.xcall(ADV + 'report').then((m) => { st.advice = m; })
			: st.scope === 'chain' ? frappe.xcall('assistant.assistant.chain.chains', { mine: admin ? 0 : 1 }).then((m) => { st.chains = m; })
			: st.scope === 'report' ? frappe.xcall(A + 'report', { view: st.rview }).then((m) => { st.report = m; st.rview = m.view; })
			: st.scope === 'workflow' ? frappe.xcall(M + 'workflows').then((m) => { st.workflows = m.rows; st.escalation_run = m.escalation_run; st.switches = m; })
			: st.scope === 'activity' ? frappe.xcall(M + 'activity', { who: st.who }).then((m) => { st.activity = m.rows; Object.assign(st.users, m.users); })
			: Promise.resolve();
		return Promise.all([frappe.call({ method: M + 'inbox', args: { scope } }), extra]).then(([r]) => {
			const m = r.message || {};
			st.rows = m.rows || [];
			st.users = Object.assign(st.users, m.users || {});
			st.manager = admin && !!m.is_manager;
			st.fetched = Date.now();
			renderKpi(m.counts || {});
			// user biasa: halaman ini = laporannya sendiri, bukan konsol Orchestrator
			page.set_title(admin ? __('Orchestrator') : __('Laporan Saya'));
			renderTabs();
			renderList();
			if (st.manager && !page.__manual) {
				page.__manual = true;
				page.set_primary_action(__('Task Manual'), manualDialog);
			}
			if (keepDetail) return;
			if (st.current) open(st.current);
			else renderDetail(null);
		});
	}

	function manualDialog() {
		const d = new frappe.ui.Dialog({
			title: __('Task Manual'),
			fields: [
				{ fieldname: 'subject', fieldtype: 'Data', label: __('Judul'), reqd: 1 },
				{ fieldname: 'assign_to', fieldtype: 'Link', options: 'User', label: __('Pemegang'), reqd: 1 },
				{ fieldname: 'severity', fieldtype: 'Select', options: 'Low\nMedium\nHigh\nCritical', default: 'Medium', label: __('Severity') },
				{ fieldname: 'response_minutes', fieldtype: 'Int', default: 60, label: __('Batas Action (menit)') },
				{ fieldname: 'reference_doctype', fieldtype: 'Link', options: 'DocType', label: __('Dokumen') },
				{ fieldname: 'reference_name', fieldtype: 'Dynamic Link', options: 'reference_doctype', label: __('No Dokumen') },
				{ fieldname: 'description', fieldtype: 'Small Text', label: __('Keterangan') },
			],
			primary_action_label: __('Buat'),
			primary_action(v) {
				frappe.call({ method: M + 'create_manual', args: v }).then((r) => { d.hide(); st.current = r.message; load(); });
			},
		});
		d.show();
	}

	const actions = {
		ack: () => call('ack', { task: st.current }),
		agent: () => call('ask_agent', { task: st.current }),
		note: () => frappe.prompt({ fieldname: 'note', fieldtype: 'Small Text', label: __('Apa yang sudah dikerjakan?'), reqd: 1 },
			(v) => call('add_note', { task: st.current, note: v.note }), __('Catat Langkah')),
		reassign: () => frappe.prompt({ fieldname: 'user', fieldtype: 'Link', options: 'User', label: __('Oper ke'), reqd: 1 },
			(v) => call('reassign', { task: st.current, user: v.user }), __('Oper Task')),
		resolve: () => frappe.prompt([
			{ fieldname: 'outcome', fieldtype: 'Select', label: __('Hasil'), options: 'Ditangani\nNormal\nTidak Valid', default: 'Ditangani', reqd: 1,
				description: __('Normal = ternyata bukan masalah (agent belajar ini bukan kejadian berbahaya).') },
			{ fieldname: 'resolution', fieldtype: 'Small Text', label: __('Catatan (opsional)'),
				description: __('Isi kalau caranya perlu diingat agent untuk kejadian serupa. Wajib kalau hasilnya Normal atau Tidak Valid.') },
		], (v) => call('resolve', { task: st.current, outcome: v.outcome, resolution: v.resolution }), __('Selesaikan Task')),
	};

	$root.on('click', '.orc-tab', function () { st.scope = this.dataset.k; st.current = null; st.wf = null; load(); });
	$root.on('click', '[data-wf-clear]', () => { st.wf = null; renderList(); });
	$root.on('click', '[data-rep]', function () { reportAction(this.dataset.rep, this.dataset.name); });
	$root.on('click', '[data-rview]', function () { st.rview = this.dataset.rview; st.showAll = false; load(true); });
	$root.on('click', '[data-wf]', function () { workflowAction(this.dataset.wf, this.dataset.name); });
	$root.on('click', '[data-who]', function () { st.who = this.dataset.who; load(true); });
	$root.on('click', '.orc-act [data-task]', function (e) { e.preventDefault(); st.scope = st.manager ? 'all' : 'mine'; st.current = this.dataset.task; load(); });
	$root.on('click', '.orc-row', function () { open(this.dataset.name); });
	$root.on('click', '[data-act]', function () { actions[this.dataset.act](); });
	$root.on('click', '.orc-chip', function () {
		if (this.dataset.esc) st.map.escalated = !st.map.escalated;
		else if (st.map.off.has(this.dataset.src)) st.map.off.delete(this.dataset.src);
		else st.map.off.add(this.dataset.src);
		renderMap();
	});

	frappe.realtime.on('orchestrator_update', () => { if (frappe.get_route()[0] === 'orchestrator') load(true); });
	setInterval(() => { if (frappe.get_route()[0] === 'orchestrator' && !['map', 'workflow', 'activity', 'report', 'chain', 'todo'].includes(st.scope)) renderList(); }, 30000);

	page.__open_from_route = () => {
		crumb();
		const t = (frappe.route_options && frappe.route_options.task) || new URLSearchParams(location.search).get('task');
		const view = (frappe.route_options && frappe.route_options.view) || new URLSearchParams(location.search).get('view');
		frappe.route_options = null;
		if (!t && view) {
			st.scope = 'report';
			st.rview = admin && ['team', 'shadow', 'advice'].includes(view) ? view : 'mine';
			if (!admin && view === 'todo') st.scope = 'todo';
			load();
			return;
		}
		if (t) { st.scope = st.manager ? 'all' : 'mine'; st.current = t; load(); }
	};
	load().then(page.__open_from_route);
	wrapper.__orc_page = page;
};

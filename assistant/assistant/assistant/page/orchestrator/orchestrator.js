// Orchestrator = Agent Inbox: semua kejadian (email, GPS, job, manual) yang perlu action,
// satu daftar + Peta Kerja. Logika & aturan di assistant/assistant/orchestrator.py.
frappe.pages['orchestrator'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Orchestrator'), single_column: true });
	const M = 'assistant.assistant.orchestrator.';
	const esc = frappe.utils.escape_html;
	const TONE = { Critical: 'red', High: 'red', Medium: 'orange', Low: 'gray', Open: 'orange', 'In Progress': 'blue', Resolved: 'green',
		Email: 'blue', Fleet: 'purple', Job: 'orange', Manual: 'gray' };
	const STATUS = { Open: __('Menunggu action'), 'In Progress': __('Ditangani'), Resolved: __('Selesai') };
	const KIND = { event: __('Kejadian'), notify: __('Notifikasi'), escalate: __('Eskalasi'), action: __('Action'),
		note: __('Langkah'), agent: __('Agent'), resolve: __('Selesai') };
	const SOURCES = ['Email', 'Fleet', 'Job', 'Manual'];
	// Peta lebih dari ini tidak terbaca lagi; yang paling mendesak didahulukan (rows sudah urut severity).
	const MAP_LIMIT = 150;
	// Pasang di .layout-main-section (punya padding bawaan desk), sama seperti halaman Assistant Administrator.
	let $main = $(wrapper).find('.layout-main-section');
	if (!$main.length) $main = $(page.main || page.body);
	const st = { scope: 'mine', rows: [], current: null, manager: false, users: {}, fetched: Date.now(),
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
		@media (max-width: 991px){.orc-body{flex-direction:column}.orc-side{width:100%;position:static;max-height:none}.orc-kpi{grid-template-columns:repeat(2,minmax(0,1fr))}}
	</style>`).appendTo($main);

	const $root = $(`<div class="orc">
		<div class="orc-kpi"></div>
		<div class="orc-tabs" role="tablist"></div>
		<div class="orc-body"><div class="orc-list"></div><aside class="orc-side"></aside></div>
	</div>`).appendTo($main);

	page.set_secondary_action(__('Refresh'), () => load());
	page.add_menu_item(__('Aturan Orchestrator'), () => frappe.set_route('Form', 'Assistant Settings'));

	const pill = (txt, tone) => `<span class="indicator-pill ${tone || 'gray'}">${esc(txt || '')}</span>`;
	const when = (s) => (s ? frappe.datetime.comment_when(s) : '');
	const formLink = (dt, dn, label) => `<a href="${frappe.utils.get_form_link(dt, dn)}" onclick="event.stopPropagation()">${esc(label || `${dt} ${dn}`)}</a>`;
	const refLink = (r) => (r.reference_name ? formLink(r.reference_doctype, r.reference_name) : '');
	// due_in dihitung server (menit); dikurangi waktu sejak data diambil supaya hitung mundur tetap jalan.
	function due(r) {
		if (r.status !== 'Open' || r.due_in == null) return '';
		const mins = r.due_in - Math.floor((Date.now() - st.fetched) / 60000);
		return mins >= 0
			? `<span>${__('Eskalasi dalam {0} menit', [mins])}</span>`
			: `<span class="orc-late">${__('Lewat batas {0} menit', [-mins])}</span>`;
	}
	const levelPill = (r) => (r.escalation_level > 0 ? pill(__('Eskalasi: {0}', [r.level_label]), 'red') : '');

	function renderTabs() {
		const tabs = [['mine', __('Inbox Saya')], ['map', __('Peta Kerja')]];
		if (st.manager) tabs.push(['all', __('Semua')]);
		tabs.push(['knowledge', __('Pengetahuan')]);
		$root.find('.orc-tabs').html(tabs.map(([k, l]) => `<button type="button" role="tab" aria-selected="${st.scope === k}" class="orc-tab ${st.scope === k ? 'on' : ''}" data-k="${k}">${l}</button>`).join(''));
	}

	function renderKpi(c) {
		const k = [[c.open, __('menunggu action'), ''], [c.escalated, __('sudah dieskalasi'), c.escalated ? 'warn' : ''],
			[c.in_progress, __('sedang ditangani'), ''], [c.resolved_today, __('selesai hari ini'), '']];
		$root.find('.orc-kpi').html(k.map(([v, l, cls]) => `<div class="orc-k ${cls}"><b>${v || 0}</b><span>${l}</span></div>`).join(''));
	}

	function renderList() {
		if (st.scope === 'map') return renderMap();
		const $l = $root.find('.orc-list');
		if (!st.rows.length) {
			$l.html(`<div class="orc-empty">${st.scope === 'knowledge' ? __('Belum ada task yang selesai.') : __('Tidak ada task yang menunggu. Semua beres.')}</div>`);
			return;
		}
		const kb = st.scope === 'knowledge';
		$l.html(st.rows.map((r) => `<button type="button" class="orc-row ${st.current === r.name ? 'on' : ''}" data-name="${esc(r.name)}">
			${pill(r.severity, TONE[r.severity])}
			<span class="sub">${esc(r.subject)}</span>
			<span class="end">${pill(r.source, TONE[r.source])}<span>${when(kb ? r.resolved_at : r.event_at)}</span></span>
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
			<div class="orc-btns">${pill(d.severity, TONE[d.severity])}${pill(STATUS[d.status], TONE[d.status])}${pill(d.source, TONE[d.source])}${levelPill(d)}</div>
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
	const SRC_COLOR = { Email: '#1a5a9c', Fleet: '#5b34a8', Job: '#a14b0e', Manual: '#6b6b6b' };
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
		const scope = st.scope === 'map' ? (st.manager ? 'all' : 'mine') : st.scope;
		return frappe.call({ method: M + 'inbox', args: { scope } }).then((r) => {
			const m = r.message || {};
			st.rows = m.rows || [];
			st.users = m.users || {};
			st.manager = !!m.is_manager;
			st.fetched = Date.now();
			renderKpi(m.counts || {});
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
			{ fieldname: 'resolution', fieldtype: 'Small Text', label: __('Cara Penyelesaian'), reqd: 1,
				description: __('Ditulis singkat: dipakai agent sebagai acuan untuk kejadian serupa.') },
		], (v) => call('resolve', { task: st.current, outcome: v.outcome, resolution: v.resolution }), __('Selesaikan Task')),
	};

	$root.on('click', '.orc-tab', function () { st.scope = this.dataset.k; st.current = null; load(); });
	$root.on('click', '.orc-row', function () { open(this.dataset.name); });
	$root.on('click', '[data-act]', function () { actions[this.dataset.act](); });
	$root.on('click', '.orc-chip', function () {
		if (this.dataset.esc) st.map.escalated = !st.map.escalated;
		else if (st.map.off.has(this.dataset.src)) st.map.off.delete(this.dataset.src);
		else st.map.off.add(this.dataset.src);
		renderMap();
	});

	frappe.realtime.on('orchestrator_update', () => { if (frappe.get_route()[0] === 'orchestrator') load(true); });
	setInterval(() => { if (frappe.get_route()[0] === 'orchestrator' && st.scope !== 'map') renderList(); }, 30000);

	page.__open_from_route = () => {
		const t = (frappe.route_options && frappe.route_options.task) || new URLSearchParams(location.search).get('task');
		frappe.route_options = null;
		if (t) { st.current = t; open(t); }
	};
	load().then(page.__open_from_route);
	wrapper.__orc_page = page;
};

frappe.pages['orchestrator'].on_page_show = function (wrapper) {
	const page = wrapper.__orc_page;
	if (page && page.__open_from_route) page.__open_from_route();
};

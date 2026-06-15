// Markdown renderer untuk pesan agent: tabel beneran (frappe.markdown {tables:true}) +
// link /app/... jadi tombol yang membuka dokumen via router SPA. Guarded global agar
// satu definisi dipakai board, form tab, dan doctype History (tidak tergantung cache file lain).
// Rapikan body email: hilangkan enter berlebih (baris-kosong beruntun → satu), pertahankan baris tunggal.
window.cmiCleanMail = window.cmiCleanMail || function (t) { return (t == null ? '' : String(t)).replace(/\r\n/g, '\n').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim(); };
window.cmiRenderMd = window.cmiRenderMd || function (text) {
	text = text == null ? '' : String(text);
	let html;
	try { html = frappe.markdown(text); }
	catch (e) { html = frappe.utils.escape_html(text).replace(/\n/g, '<br>'); }
	const wrap = document.createElement('div');
	wrap.innerHTML = html;
	wrap.querySelectorAll('a[href]').forEach(function (a) {
		const href = a.getAttribute('href') || '';
		const idx = href.indexOf('/app/');
		if (idx !== -1) {
			const route = href.slice(idx + 5).replace(/^\/+/, '').replace(/[?#].*$/, '');
			a.setAttribute('href', '/app/' + route);
			a.setAttribute('data-cmi-route', route);
			a.classList.add('cmi-route-btn');
			const label = (a.textContent || '').trim();
			if (!label || label.indexOf('/app/') !== -1 || label.charAt(0) === '#') {
				a.textContent = '🔗 Buka ' + decodeURIComponent(route.split('/').slice(1).join('/') || route);
			}
		} else if (/^https?:/i.test(href)) {
			a.setAttribute('target', '_blank');
			a.setAttribute('rel', 'noopener noreferrer');
		}
	});
	return wrap.innerHTML;
};
if (!window.__cmiRouteBound) {
	window.__cmiRouteBound = true;
	$(document).on('click', 'a.cmi-route-btn', function (e) {
		e.preventDefault();
		const route = this.getAttribute('data-cmi-route');
		if (!route) return;
		const segs = route.split('/');
		const slug = decodeURIComponent(segs[0]);
		const rest = segs.slice(1).map(decodeURIComponent).join('/');
		frappe.set_route(rest ? [slug, rest] : [slug]);
	});
}

// Render arsip Agent History (chat bubble + email thread) — dipakai tab History modal.
// Guarded supaya tidak bentrok dgn definisi di agent_administrator.js (doctype form).
window.cmi_history_render = window.cmi_history_render || function ($wrapper, opts) {
	const esc = frappe.utils.escape_html;
	const when = (s) => esc(frappe.datetime.str_to_user(s) || s || '');
	$wrapper.html('<div class="text-muted" style="padding:12px;">Memuat history…</div>');
	frappe.call({ method: 'agents.agent.history.get_agent_history', args: opts }).then((r) => {
		const d = (r && r.message) || { chat: [], emails: [] };
		const chat = d.chat || [], emails = d.emails || [];
		const chatHtml = chat.map((m) => {
			const body = m.role === 'user' ? esc(m.text) : (window.cmiRenderMd || esc)(m.text);
			const cls = m.role === 'user' ? 'u' : 'a fl-md';
			return `<div class="fl-msg ${cls}">${body}<div style="font-size:10px;opacity:.6;margin-top:2px;">${when(m.at)}</div></div>`;
		}).join('') || '<div class="text-muted small" style="padding:8px;">Belum ada chat tersimpan.</div>';
		const mailHtml = emails.slice().reverse().map((m) => `<div class="fl-mail"><div class="fl-mail-h"><b>${m.role === 'customer' ? '📨 ' + esc(m.mail_to || 'Customer') : '🤖 keluar'}</b><span class="fl-mbadge ${esc(m.status)}">${esc(m.status || '')}</span></div><div class="fl-mail-m">${esc(m.mail_to || '-')} · ${when(m.at)}</div><div class="fl-mail-s">${esc(m.subject || '')}</div><div class="fl-mail-b">${esc(window.cmiCleanMail(m.body || ''))}</div></div>`).join('') || '<div class="text-muted small" style="padding:8px;">Belum ada email tersimpan.</div>';
		$wrapper.html(`<div class="fl-hist"><div style="display:flex;gap:6px;margin-bottom:8px;"><button class="btn btn-xs btn-primary fl-h-t" data-t="chat">💬 Chat (${chat.length})</button><button class="btn btn-xs btn-default fl-h-t" data-t="email">✉ Email (${emails.length})</button></div><div class="fl-chatlog fl-h-chat">${chatHtml}</div><div class="fl-maillog fl-h-email" style="display:none;">${mailHtml}</div></div>`);
		$wrapper.find('.fl-h-t').on('click', function () {
			const t = $(this).data('t');
			$wrapper.find('.fl-h-t').removeClass('btn-primary').addClass('btn-default');
			$(this).removeClass('btn-default').addClass('btn-primary');
			$wrapper.find('.fl-h-chat').toggle(t === 'chat'); $wrapper.find('.fl-h-email').toggle(t === 'email');
		});
	});
};

frappe.pages['assistant'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: 'Assistant Center', single_column: true });
	let $body = $(wrapper).find('.layout-main-section');
	if (!$body.length && page && page.body) $body = $(page.body);
	if (!$body.length && page && page.main) $body = $(page.main);
	if (!$body.length) $body = $(wrapper);

	const M = {
		list: 'agents.agent.fleet.list_my_agents',
		detail: 'agents.agent.fleet.detail',
		broadcast: 'agents.agent.fleet.broadcast',
		eligible: 'agents.agent.fleet.eligible',
		handoff: 'agents.agent.fleet.handoff',
		sendMail: 'agents.agent.fleet.send_mail',
		mailAttach: 'agents.agent.fleet.save_email_attachment',
		chat: 'agents.agent.api.chat',
		newSession: 'agents.agent.api.new_session',
		createJob: 'agents.agent.center.create_job',
		upload: 'agents.agent.api.upload_attachment',
	};
	const DOC_LABEL = { 'sales-invoice': 'Invoice', 'expense-note': 'Expense', 'shipping-list': 'Shipping List', 'packing-list': 'Packing List' };
	const KIND_LABEL = { active: 'Active', working: 'Working', waiting: 'Waiting', idle: 'Idle', error: 'Error' };
	const MAX_MB = 15, NOTICE_TTL = 15 * 60 * 1000;
	const esc = frappe.utils.escape_html;
	const state = { scope: 'active', agents: [], selected: null, tab: 'chat', busy: false, pending: 0, mailAttachments: [] };

	$body.html(`
		<div class="fl">
			<div class="fl-top">
				<div class="fl-tabs">
					<button class="btn btn-xs btn-primary fl-tab" data-scope="active">Board</button>
					<button class="btn btn-xs btn-default fl-tab" data-scope="history">History</button>
				</div>
				<div class="fl-actions">
					<button class="btn btn-xs btn-default fl-new-chat">＋ Chat Assistant</button>
					<button class="btn btn-xs btn-primary fl-new-pdf">⬆ PDF Job</button>
				</div>
			</div>
			<div class="fl-stats"></div>
			<div class="fl-bcast">
				<input type="text" class="form-control input-sm fl-bcast-input" placeholder="Minta REVIEW hasil ke semua agent aktif… (mis. 'review hasil pekerjaanmu', 'sudah lengkap belum?', 'ada yang kurang?')">
				<button class="btn btn-sm btn-primary fl-bcast-send">Minta review</button>
			</div>
			<div class="fl-bcast-replies" style="display:none;"></div>
			<div class="fl-board"></div>
			<input type="file" class="fl-pdf-file" accept="application/pdf" multiple style="display:none;" />
			<input type="file" class="fl-chat-file" accept="application/pdf,image/png,image/jpeg,image/webp,image/gif" multiple style="display:none;" />
			<input type="file" class="fl-mail-file" multiple style="display:none;" />
		</div>
	`);

	const $stats = $body.find('.fl-stats');
	const $board = $body.find('.fl-board');
	const $bcastReplies = $body.find('.fl-bcast-replies');
	const $pdfFile = $body.find('.fl-pdf-file');
	const $chatFile = $body.find('.fl-chat-file');
	const $mailFile = $body.find('.fl-mail-file');

	// ---------- seen-state for the attention bubble ----------
	function seenMap() { try { return JSON.parse(localStorage.getItem('agent-reminder-seen') || '{}'); } catch (e) { return {}; } }
	function markSeen(intake, at) { const m = seenMap(); m[intake] = at || new Date().toISOString(); localStorage.setItem('agent-reminder-seen', JSON.stringify(m)); }
	function bubbleFor(a) {
		const r = a.last_reply; if (!r || !r.created_at) return null;
		const t = new Date(r.created_at.replace(' ', 'T')).getTime();
		if (isNaN(t) || Date.now() - t > NOTICE_TTL) return null;
		const seen = seenMap()[a.name]; if (seen && new Date(seen).getTime() >= t) return null;
		return r;
	}
	function fmtAgo(s) {
		if (!s) return '';
		const t = new Date(s.replace(' ', 'T')).getTime(); if (isNaN(t)) return '';
		const m = Math.floor((Date.now() - t) / 60000);
		if (m < 1) return 'baru saja'; if (m < 60) return m + 'm lalu';
		const h = Math.floor(m / 60); if (h < 24) return h + 'j lalu'; return Math.floor(h / 24) + 'h lalu';
	}
	function avatar(name) { const base = (name || '?').replace(/^\s*agent\s+/i, ''); const s = base.replace(/[^A-Za-z0-9]/g, ''); return (s.slice(0, 2) || '??').toUpperCase(); }

	// ---------- stats ----------
	function renderStats() {
		const by = { active: 0, working: 0, waiting: 0, idle: 0, error: 0 };
		state.agents.forEach((a) => { by[a.kind] = (by[a.kind] || 0) + 1; });
		const cell = (n, l, k) => `<div class="fl-stat fl-stat-${k}"><div class="fl-stat-n">${n}</div><div class="fl-stat-l">${l}</div></div>`;
		$stats.html(
			cell(state.agents.length, 'Agents', 'all') + cell(by.active, 'Active', 'active') +
			cell(by.working, 'Working', 'working') + cell(by.waiting, 'Waiting', 'waiting') +
			cell(by.idle + by.error, 'Idle', 'idle')
		);
	}

	// ---------- board cards ----------
	function stepper(a) {
		return '<div class="fl-stepper">' + (a.steps || []).map((s, i) => {
			const cls = i < a.step ? 'done' : (i === a.step ? 'cur' : '');
			return `<span class="fl-seg ${cls}" title="${esc(s)}"></span>`;
		}).join('') + '</div>';
	}
	function tokenBar(a) {
		const pct = a.token_limit ? Math.min(100, Math.round((a.tokens_used / a.token_limit) * 100)) : 0;
		return `<div class="fl-tok"><span style="width:${pct}%"></span></div>`;
	}
	function card(a) {
		const loc = (a.module && a.ref_id)
			? `<div class="fl-loc">📍 ${esc(a.location)} <a href="/app/${a.module}/${encodeURIComponent(a.ref_id)}" target="_blank" class="fl-open">${esc(DOC_LABEL[a.module] || 'Open')} ▸</a></div>` : '';
		const job = (a.job_ref || a.customer) ? `<div class="fl-job">${esc(a.job_ref || '')}${a.customer ? ' · ' + esc(a.customer) : ''}</div>` : '';
		const b = bubbleFor(a);
		const bubble = b ? renderBubble(a, b) : '';
		return `
			<div class="fl-card st-${a.kind}${b ? ' has-bubble' : ''}" data-intake="${esc(a.name)}">
				${bubble}
				<div class="fl-card-head">
					<div class="fl-ava">${esc(avatar(a.agent_name))}</div>
					<div class="fl-id">
						<div class="fl-name">${esc(a.agent_name)}</div>
						<div class="fl-sub">by ${esc(a.owner_name || '')} · <span class="fl-phase">${esc(a.phase_label)}</span></div>
					</div>
					<span class="fl-pill pill-${a.kind}"><i></i>${esc(KIND_LABEL[a.kind] || a.status)}</span>
				</div>
				${loc}${job}
				<div class="fl-task">${esc(a.task)}</div>
				${stepper(a)}
				<div class="fl-step-row"><span>${esc(a.step_label)}</span><span class="fl-ago">${fmtAgo(a.last_activity_at)}</span></div>
				${tokenBar(a)}
			</div>`;
	}
	function renderBubble(a, r) {
		const head = r.channel === 'email' ? `🔔 Reminder · ${esc(a.agent_name)}` : `💬 ${esc(a.agent_name)}`;
		const text = r.channel === 'email' ? (r.subject || r.body) : r.body;
		return `<div class="fl-bubble" data-intake="${esc(a.name)}" data-at="${esc(r.created_at)}">
			<button class="fl-bubble-x" title="Tutup">×</button>
			<div class="fl-bubble-h">${head}</div>
			<div class="fl-bubble-b">${esc(text)}</div></div>`;
	}
	function renderBoard() {
		if (!state.agents.length) {
			$board.html(`<div class="fl-empty text-muted">Belum ada agent ${state.scope === 'active' ? 'aktif' : 'di history'}. Klik <b>＋ Chat Agent</b> atau <b>⬆ PDF Job</b>.</div>`);
			return;
		}
		$board.html(state.agents.map(card).join(''));
	}

	function load(silent) {
		return frappe.call({ method: M.list, args: { scope: state.scope }, freeze: !silent }).then((r) => {
			state.agents = (r && r.message) || [];
			renderStats(); renderBoard();
		});
	}

	// ---------- board events (delegated) ----------
	$board.on('click', '.fl-bubble-x', function (e) {
		e.stopPropagation();
		const $b = $(this).closest('.fl-bubble'); markSeen($b.data('intake'), $b.data('at')); $b.remove();
		$(this).closest('.fl-card').removeClass('has-bubble');
	});
	$board.on('click', '.fl-bubble', function (e) {
		e.stopPropagation(); markSeen($(this).data('intake'), $(this).data('at')); openModal($(this).data('intake'), 'chat');
	});
	$board.on('click', '.fl-card', function () { openModal($(this).data('intake'), 'chat'); });
	$board.on('click', '.fl-open', function (e) { e.stopPropagation(); });

	// ---------- tabs / scope ----------
	$body.find('.fl-tab').on('click', function () {
		state.scope = $(this).data('scope');
		$body.find('.fl-tab').each(function () { const on = $(this).data('scope') === state.scope; $(this).toggleClass('btn-primary', on).toggleClass('btn-default', !on); });
		load();
	});

	// ---------- create agents ----------
	$body.find('.fl-new-chat').on('click', () => frappe.call({ method: M.newSession, args: { source: 'Chat' } }).then((r) => {
		if (r && r.message) { state.scope = 'active'; syncTabs(); load(true).then(() => openModal(r.message.intake, 'chat')); }
	}));
	$body.find('.fl-new-pdf').on('click', () => $pdfFile.trigger('click'));
	$pdfFile.on('change', (e) => {
		const fs = Array.from(e.target.files || []); $pdfFile.val('');
		fs.forEach((file) => {
			if (file.size > MAX_MB * 1024 * 1024) { frappe.show_alert({ message: `${file.name}: > ${MAX_MB}MB`, indicator: 'red' }); return; }
			const reader = new FileReader();
			reader.onload = () => {
				const b64 = String(reader.result).split(',')[1] || '';
				frappe.call({ method: M.createJob, args: { filename: file.name, content_b64: b64 } }).then((r) => {
					const m = (r && r.message) || {};
					if (m.error) frappe.show_alert({ message: `${file.name}: ${m.error}`, indicator: 'red' });
					else frappe.show_alert({ message: `${m.agent_name} mengerjakan ${file.name}`, indicator: 'blue' });
					state.scope = 'active'; syncTabs(); load(true);
				});
			};
			reader.readAsDataURL(file);
		});
	});
	function syncTabs() { $body.find('.fl-tab').each(function () { const on = $(this).data('scope') === state.scope; $(this).toggleClass('btn-primary', on).toggleClass('btn-default', !on); }); }

	// ---------- broadcast ----------
	function broadcast() {
		const msg = ($body.find('.fl-bcast-input').val() || '').trim(); if (!msg) return;
		$bcastReplies.show().html('<div class="text-muted small" style="padding:8px;">Menanyakan ke agent yang aktif…</div>');
		frappe.call({ method: M.broadcast, args: { message: msg } }).then((r) => {
			const rows = (r && r.message) || [];
			if (!rows.length) { $bcastReplies.html('<div class="text-muted small" style="padding:8px;">Tidak ada agent aktif.</div>'); return; }
			$bcastReplies.html(
				`<div class="fl-bcast-top"><b>${rows.length} balasan</b> <button class="btn btn-xs btn-default fl-bcast-clear">Bersihkan</button></div>` +
				rows.map((x) => `<div class="fl-bcast-reply" data-intake="${esc(x.agent_id)}"><span class="fl-pill pill-${kindOf(x.status)}"><i></i>${esc(x.agent_name)}</span> ${esc(x.reply)}</div>`).join('')
			);
			load(true);
		});
	}
	function kindOf(status) { return ({ New: 'active', 'In Progress': 'working', 'Awaiting Review': 'waiting', Completed: 'idle', Error: 'error' })[status] || 'idle'; }
	$body.find('.fl-bcast-send').on('click', broadcast);
	$body.find('.fl-bcast-input').on('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); broadcast(); } });
	$bcastReplies.on('click', '.fl-bcast-clear', () => $bcastReplies.hide().empty());
	$bcastReplies.on('click', '.fl-bcast-reply', function () { openModal($(this).data('intake'), 'chat'); });

	// ---------- detail modal ----------
	let $modal = null, modalData = null;
	function openModal(intake, tab) {
		state.selected = intake; state.tab = tab || 'chat'; state.pending = 0; state.mailAttachments = [];
		if (!$modal) buildModalShell();
		$modal.show();
		$modal.find('.fl-m-body').html('<div class="text-muted" style="padding:24px;">Memuat…</div>');
		refreshModal();
	}
	function refreshModal() {
		if (!state.selected) return;
		return frappe.call({ method: M.detail, args: { intake: state.selected } }).then((r) => {
			modalData = (r && r.message) || null; if (modalData) renderModal(modalData);
		});
	}
	function buildModalShell() {
		$modal = $(`
			<div class="fl-modal-back" style="display:none;">
				<div class="fl-modal">
					<div class="fl-m-head"></div>
					<div class="fl-m-tabs">
						<button class="fl-m-tab" data-tab="chat">Chat</button>
						<button class="fl-m-tab" data-tab="email">Email</button>
						<button class="fl-m-tab" data-tab="exec">Activity</button>
						<button class="fl-m-tab" data-tab="history">📜 History</button>
					</div>
					<div class="fl-m-handoff" style="display:none;"></div>
					<div class="fl-m-body"></div>
					<div class="fl-m-foot"></div>
				</div>
			</div>`).appendTo($body);
		$modal.on('click', (e) => { if (e.target === $modal[0]) closeModal(); });
		$modal.on('click', '.fl-m-tab', function () { state.tab = $(this).data('tab'); $modal.find('.fl-m-handoff').hide(); renderModalBody(); markTabs(); });
		$chatFile.on('change', (e) => { Array.from(e.target.files || []).forEach(uploadAttach); $chatFile.val(''); });
		$mailFile.on('change', (e) => { Array.from(e.target.files || []).forEach(uploadMailAttach); $mailFile.val(''); });
	}
	function closeModal() { state.selected = null; if ($modal) $modal.hide(); load(true); }
	function markTabs() { $modal.find('.fl-m-tab').each(function () { $(this).toggleClass('on', $(this).data('tab') === state.tab); }); }

	function renderModal(d) {
		const a = d.agent;
		const loc = (a.module && a.ref_id) ? ` · 📍 ${esc(a.location)}` : '';
		$modal.find('.fl-m-head').html(`
			<div class="fl-m-title">
				<span class="fl-ava sm">${esc(avatar(a.agent_name))}</span>
				<div>
					<div class="fl-m-name">${esc(a.agent_name)} <span class="fl-pill pill-${a.kind}"><i></i>${esc(KIND_LABEL[a.kind] || a.status)}</span> <span class="fl-chip">🗂 ${esc(a.phase_label)}</span></div>
					<div class="fl-m-meta">by ${esc(a.owner_name || '')}${loc} · Job: ${esc(a.job_ref || '-')}${a.customer ? ' · ' + esc(a.customer) : ''}${a.contact_email ? ' · ✉ ' + esc(a.contact_email) : ''} · Tokens ${a.tokens_used}/${a.token_limit || '∞'}</div>
				</div>
			</div>
			<button class="fl-m-close" title="Tutup">×</button>`);
		$modal.find('.fl-m-tab[data-tab="chat"]').text(`Chat (${(d.messages || []).length})`);
		$modal.find('.fl-m-tab[data-tab="email"]').text(`Email (${(d.mails || []).length})`);
		$modal.find('.fl-m-tab[data-tab="exec"]').text(`Activity (${(d.events || []).length})`);
		$modal.find('.fl-m-close').on('click', closeModal);
		markTabs(); renderFoot(a); renderModalBody();
	}

	const EVENT_ICON = { created: '✨', intake: '📥', chat: '💬', broadcast: '📣', reminder: '🔔', email: '✉️', expense: '🧾', awaiting: '⏳', done: '✅', nudge: '👉', handoff: '🤝', report: '📝' };
	// Topik ramah-user untuk tab Activity (tanpa metadata teknis).
	const EVENT_TOPIC = { created: 'Dibuat', intake: 'Intake', chat: 'Chat', broadcast: 'Broadcast', reminder: 'Pengingat', email: 'Email', expense: 'Expense Note', awaiting: 'Menunggu', done: 'Selesai', nudge: 'Dorongan', handoff: 'Oper fase', report: 'Laporan' };
	function renderModalBody() {
		if (!modalData) return;
		const d = modalData, a = d.agent, $b = $modal.find('.fl-m-body');
		if (state.tab === 'history') { if (window.cmi_history_render) window.cmi_history_render($b, { agent_id: a.name }); return; }
		if (state.tab === 'chat') {
			const msgs = (d.messages || []).map((m) => m.role === 'user'
				? `<div class="fl-msg u">${esc(m.text)}</div>`
				: `<div class="fl-msg a fl-md">${(window.cmiRenderMd || esc)(m.text)}</div>`).join('') || '<div class="text-muted small" style="padding:8px;">Belum ada percakapan.</div>';
			// Chat baru/kosong → tombol "command" cepat: mau buat dokumen apa?
			const isEmpty = !(d.messages || []).length;
			const quick = isEmpty ? `
				<div class="fl-quick" style="padding:8px 4px;">
					<div style="font-size:12px;color:var(--text-muted,#6c7680);margin-bottom:6px;">Mau buat apa? (klik)</div>
					<div style="display:flex;gap:8px;flex-wrap:wrap;">
						<button class="btn btn-sm btn-default fl-quick-cmd" data-cmd="Shipping List">📦 Shipping List</button>
						<button class="btn btn-sm btn-default fl-quick-cmd" data-cmd="Packing List">📋 Packing List</button>
						<button class="btn btn-sm btn-default fl-quick-cmd" data-cmd="Expense Note">🧾 Expense Note</button>
						<button class="btn btn-sm btn-default fl-quick-cmd" data-cmd="Invoice">💰 Invoice</button>
					</div>
				</div>` : '';
			$b.html(`<div class="fl-chatlog">${msgs}</div>${quick}
				<div class="fl-chat-input"><button class="btn btn-default fl-attach" title="Lampirkan">📎</button>
				<textarea class="form-control fl-chat-text" rows="2" placeholder="Instruksi / kriteria untuk ${esc(a.agent_name)}… (Enter kirim)"></textarea>
				<button class="btn btn-primary fl-chat-send">Kirim</button></div>`);
			const $log = $b.find('.fl-chatlog'); $log.scrollTop($log[0].scrollHeight);
			$b.find('.fl-chat-send').on('click', sendChat);
			$b.find('.fl-chat-text').on('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } });
			$b.find('.fl-attach').on('click', () => $chatFile.trigger('click'));
			$b.find('.fl-quick-cmd').on('click', function () {
				const cmd = $(this).data('cmd');
				$b.find('.fl-chat-text').val(`Saya mau membuat ${cmd}. Tolong langsung pandu saya mengisi datanya.`);
				sendChat();
			});
		} else if (state.tab === 'email') {
			const drafts = [];
			const mails = (d.mails || []).slice().reverse().map((m, i) => {
				let extra = '';
				if (m.status === 'draft') {
					const idx = drafts.push({ subject: m.subject || '', body: m.body || '', to: m.mail_to || '' }) - 1;
					extra = `<button class="btn btn-xs btn-default fl-use-draft" data-draft="${idx}">✎ Pakai draft ini & kirim manual</button>`;
				}
				const latest = i === 0 ? '<span class="fl-mbadge latest">★ Terbaru</span>' : '';
				return `
				<div class="fl-mail${i === 0 ? ' fl-mail-latest' : ''}">
					<div class="fl-mail-h"><b>${m.role === 'user' ? '🧑 You' : '🤖 ' + esc(a.agent_name)}</b>
						<span>${latest}<span class="fl-mbadge ${esc(m.status)}">${esc(m.status === 'draft' ? 'draft (perlu konfirmasi)' : m.status)}</span></span></div>
					<div class="fl-mail-m">To: ${esc(m.mail_to || '-')} · ${esc(frappe.datetime.comment_when(m.creation))}</div>
					<div class="fl-mail-s">${esc(m.subject || '')}</div>
					<div class="fl-mail-b">${esc(window.cmiCleanMail(m.body || ''))}</div>
					${extra}
				</div>`;
			}).join('') || '<div class="text-muted small" style="padding:8px;">Belum ada email.</div>';
			const md = d.mail_defaults || {};
			const mailHint = (d.mails || []).length ? '<div class="fl-mail-hint">📧 Urutan: <b>email terbaru di atas</b> ↓</div>' : '';
			$b.html(`${mailHint}<div class="fl-maillog">${mails}</div>
				<div class="fl-mail-compose">
					<input class="form-control input-sm fl-mail-to" placeholder="To (email)" value="${esc(md.to || a.contact_email || '')}">
					<input class="form-control input-sm fl-mail-subj" placeholder="Subject" value="${esc(md.subject || '')}">
					<textarea class="form-control fl-mail-body" rows="7" placeholder="Isi email…"></textarea>
					<div class="fl-mail-attach">
						<button class="btn btn-default btn-sm fl-mail-attach-btn" title="Lampirkan file">📎 Lampirkan</button>
						<span class="fl-mail-chips"></span>
					</div>
					<button class="btn btn-sm btn-primary fl-mail-send">Kirim email</button>
				</div>`);
			$b.find('.fl-mail-send').on('click', sendMail);
			$b.find('.fl-mail-attach-btn').on('click', () => $mailFile.trigger('click'));
			$b.find('.fl-use-draft').on('click', function () {
				const dft = drafts[$(this).data('draft')] || {};
				$b.find('.fl-mail-subj').val(dft.subject || '');
				$b.find('.fl-mail-body').val(dft.body || '');
				if (dft.to) $b.find('.fl-mail-to').val(dft.to);
				$b.find('.fl-mail-body')[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
			});
			renderMailChips();
		} else {
			const ev = (d.events || []).map((e) => {
				const isChat = e.kind === 'chat';
				const topic = EVENT_TOPIC[e.kind] || (e.kind || 'Aktivitas');
				const tag = isChat ? '💬 Chat' : ('⚙ ' + esc(topic));
				const when = frappe.datetime.str_to_user(e.creation);
				return `<div class="fl-ev2">
					<div class="fl-ev2-top"><span class="fl-ev2-when">${esc(when)}</span> · <span class="fl-ev2-topic">${tag}</span></div>
					<div class="fl-ev2-msg">${esc(e.message || topic)}</div>
				</div>`;
			}).join('') || '<div class="text-muted small" style="padding:8px;">Belum ada aktivitas.</div>';
			$b.html(`<div class="fl-execlog">${ev}</div>`);
		}
	}
	function renderFoot(a) {
		const open = (a.module && a.ref_id) ? `<a class="btn btn-xs btn-default" href="/app/${a.module}/${encodeURIComponent(a.ref_id)}" target="_blank">Open record ▸</a>` : '';
		$modal.find('.fl-m-foot').html(`${open}
			<button class="btn btn-xs btn-default fl-handoff-toggle">Lanjut ke fase ▸</button>
			<button class="btn btn-xs btn-default fl-close2">Tutup</button>`);
		$modal.find('.fl-close2').on('click', closeModal);
		$modal.find('.fl-handoff-toggle').on('click', toggleHandoff);
	}

	// ---------- chat (instruct agent) ----------
	function sendChat() {
		if (state.busy) return;
		const $t = $modal.find('.fl-chat-text'), msg = ($t.val() || '').trim();
		if (!msg && state.pending === 0) return;
		const $log = $modal.find('.fl-chatlog'); $log.find('.text-muted').remove();
		$log.append(`<div class="fl-msg u">${esc(msg)}${state.pending ? '  📎×' + state.pending : ''}</div>`);
		$t.val(''); state.pending = 0; state.busy = true;
		$modal.find('.fl-chat-send').prop('disabled', true).text('…');
		const $typing = $(`<div class="fl-msg a">…</div>`).appendTo($log); $log.scrollTop($log[0].scrollHeight);
		frappe.call({ method: M.chat, args: { intake: state.selected, message: msg } }).then((r) => {
			$typing.remove(); state.busy = false; $modal.find('.fl-chat-send').prop('disabled', false).text('Kirim');
			const m = r && r.message; if (m && m.reply) $log.append(`<div class="fl-msg a fl-md">${(window.cmiRenderMd || esc)(m.reply)}</div>`);
			$log.scrollTop($log[0].scrollHeight); refreshModal(); load(true);
		}).catch(() => { $typing.remove(); state.busy = false; $modal.find('.fl-chat-send').prop('disabled', false).text('Kirim'); });
	}
	function uploadAttach(file) {
		if (!state.selected) return;
		const reader = new FileReader();
		reader.onload = () => {
			const b64 = String(reader.result).split(',')[1] || '';
			frappe.call({ method: M.upload, args: { intake: state.selected, filename: file.name, content_b64: b64 } }).then((r) => {
				const m = (r && r.message) || {};
				if (m.ok) { state.pending += 1; frappe.show_alert({ message: `📎 ${file.name}`, indicator: 'green' }); }
				else frappe.show_alert({ message: m.error || 'Ditolak', indicator: 'red' });
			});
		};
		reader.readAsDataURL(file);
	}

	// ---------- email ----------
	function renderMailChips() {
		const $chips = $modal && $modal.find('.fl-mail-chips'); if (!$chips || !$chips.length) return;
		$chips.html((state.mailAttachments || []).map((f, i) =>
			`<span class="fl-mail-chip">📎 ${esc(f.file_name)} <a href="#" class="fl-chip-x" data-i="${i}">×</a></span>`).join(''));
		$chips.find('.fl-chip-x').on('click', (e) => {
			e.preventDefault(); state.mailAttachments.splice($(e.currentTarget).data('i'), 1); renderMailChips();
		});
	}
	function uploadMailAttach(file) {
		if (!state.selected) return;
		if (file.size > MAX_MB * 1024 * 1024) { frappe.show_alert({ message: `${file.name} > ${MAX_MB}MB`, indicator: 'red' }); return; }
		const reader = new FileReader();
		reader.onload = () => {
			const b64 = String(reader.result).split(',')[1] || '';
			frappe.call({ method: M.mailAttach, args: { intake: state.selected, filename: file.name, content_b64: b64 } }).then((r) => {
				const m = (r && r.message) || {};
				if (m.file_url) { state.mailAttachments.push({ file_url: m.file_url, file_name: m.file_name || file.name }); renderMailChips(); frappe.show_alert({ message: `📎 ${m.file_name || file.name}`, indicator: 'green' }); }
				else frappe.show_alert({ message: 'Gagal lampirkan', indicator: 'red' });
			}).catch(() => frappe.show_alert({ message: 'Gagal lampirkan', indicator: 'red' }));
		};
		reader.readAsDataURL(file);
	}
	function sendMail() {
		const to = ($modal.find('.fl-mail-to').val() || '').trim();
		const subject = ($modal.find('.fl-mail-subj').val() || '').trim();
		const body = ($modal.find('.fl-mail-body').val() || '').trim();
		if (!body) { frappe.show_alert({ message: 'Isi email dulu', indicator: 'orange' }); return; }
		const attachments = JSON.stringify((state.mailAttachments || []).map((f) => f.file_url));
		frappe.call({ method: M.sendMail, args: { intake: state.selected, mail_to: to, subject, body, role: 'user', attachments }, freeze: true }).then((r) => {
			const m = (r && r.message) || {};
			state.mailAttachments = [];
			frappe.show_alert({ message: __('Email {0} → {1}', [m.status, m.to || '-']), indicator: m.status === 'sent' ? 'green' : 'orange' });
			refreshModal();
		});
	}

	// ---------- handoff ----------
	function toggleHandoff() {
		const $h = $modal.find('.fl-m-handoff');
		if ($h.is(':visible')) { $h.hide(); return; }
		$h.show().html('<div class="text-muted small">Memuat…</div>');
		frappe.call({ method: M.eligible, args: { intake: state.selected } }).then((r) => {
			const e = (r && r.message) || {};
			if (e.is_done) { $h.html('<div class="text-muted small">Job sudah di fase akhir (Done).</div>'); return; }
			const opts = (e.users || []).map((u) => `<option value="${esc(u.name)}">${esc(u.full_name)} (${esc(u.name)})</option>`).join('');
			$h.html(`
				<div class="fl-h-row"><b>Oper job ke fase:</b> <span class="fl-chip">${esc(e.next_label)}</span>
					${e.fallback_all ? '<span class="text-muted small">(belum ada user di divisi ini — tampil semua user)</span>' : ''}</div>
				<div class="fl-h-row"><select class="form-control input-sm fl-h-user">${opts || '<option value="">— tidak ada user —</option>'}</select>
					<button class="btn btn-sm btn-primary fl-h-go">Oper ke user</button></div>`);
			$h.find('.fl-h-go').on('click', () => {
				const to = $h.find('.fl-h-user').val(); if (!to) return;
				frappe.call({ method: M.handoff, args: { intake: state.selected, to_user: to }, freeze: true }).then(() => {
					frappe.show_alert({ message: __('Job dioper ke {0}', [to]), indicator: 'green' }); closeModal();
				});
			});
		});
	}

	// ---------- poll ----------
	// Board refreshes every 8s (bubbles surface within seconds). The open modal is NOT
	// auto-refreshed on poll so a half-typed chat/email is never wiped — it updates after
	// each action (send/handoff/advance) instead.
	load();
	const timer = setInterval(() => { load(true); }, 8000);
	$(wrapper).on('remove', () => clearInterval(timer));
};

// Markdown renderer pesan agent (tabel + tombol link /app/...). Guarded global.
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

// Tab "📜 History" di Agent Administrator — arsip chat + email (gaya bubble/thread,
// "seperti dulu") dari doctype Agent History. Akses dibatasi server (hanya System
// Manager / user yang terlibat). Render di-expose global agar board (assistant page)
// bisa pakai ulang.
window.cmi_history_render = window.cmi_history_render || function ($wrapper, opts) {
	const esc = frappe.utils.escape_html;
	const when = (s) => esc(frappe.datetime.str_to_user(s) || s || '');
	if (!window._cmi_hist_style) {
		window._cmi_hist_style = 1;
		$('<style>').text(`
		.cmi-h{font-size:13px;max-width:900px}
		.cmi-h-tabs{display:flex;gap:6px;margin-bottom:8px}
		.cmi-h-tab{cursor:pointer;border:1px solid var(--border-color,#e2e2e2);border-radius:999px;padding:2px 12px;font-size:12px}
		.cmi-h-tab.on{background:var(--primary,#2490ef);color:#fff;border-color:transparent}
		.cmi-h-log{max-height:60vh;overflow:auto;border:1px solid var(--border-color,#e2e2e2);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px;background:var(--card-bg,#fff)}
		.cmi-h-msg{max-width:82%;padding:7px 11px;border-radius:12px;white-space:pre-wrap;word-wrap:break-word;line-height:1.4}
		.cmi-h-msg.u{margin-left:auto;background:var(--primary,#2490ef);color:#fff}
		.cmi-h-msg.a{margin-right:auto;background:var(--control-bg,#f4f5f6)}
		.cmi-h-msg.cmi-md{white-space:normal;max-width:100%}
		.cmi-md > :first-child{margin-top:0} .cmi-md > :last-child{margin-bottom:0}
		.cmi-md p{margin:0 0 6px}
		.cmi-md table{border-collapse:collapse;width:100%;margin:6px 0;font-size:12.5px;background:var(--card-bg,#fff)}
		.cmi-md th,.cmi-md td{border:1px solid var(--border-color,#e2e2e2);padding:5px 9px;text-align:left;vertical-align:top}
		.cmi-md thead th{background:var(--control-bg,#f4f5f6);font-weight:600}
		.cmi-md code{background:rgba(0,0,0,.06);padding:1px 4px;border-radius:4px;font-size:.92em}
		.cmi-md ul,.cmi-md ol{margin:4px 0 6px;padding-left:20px}
		.cmi-route-btn{display:inline-flex;align-items:center;gap:4px;margin:2px 0;padding:3px 10px;border-radius:6px;background:var(--primary,#2490ef);color:#fff !important;font-weight:600;font-size:12px;text-decoration:none !important}
		.cmi-route-btn:hover{filter:brightness(.94);color:#fff !important}
		.cmi-h-msg .cmi-h-t{display:block;font-size:10.5px;opacity:.7;margin-top:3px}
		.cmi-h-mail{border:1px solid var(--border-color,#e2e2e2);border-radius:8px;padding:8px 10px}
		.cmi-h-mail.in{background:var(--control-bg,#f4f5f6);align-self:flex-start;max-width:88%}
		.cmi-h-mail.out{background:rgba(36,144,239,.06);align-self:flex-end;max-width:88%}
		.cmi-h-empty{padding:18px;color:var(--text-muted,#6c7680)}
		`).appendTo('head');
	}
	$wrapper.html('<div class="text-muted" style="padding:12px;">Memuat history…</div>');
	frappe.call({ method: 'agents.agent.history.get_agent_history', args: opts }).then((r) => {
		const d = (r && r.message) || { chat: [], emails: [] };
		const chat = d.chat || [], emails = d.emails || [];
		const chatHtml = chat.map((m) => {
			const body = m.role === 'user' ? esc(m.text) : (window.cmiRenderMd || esc)(m.text);
			const cls = m.role === 'user' ? 'u' : 'a cmi-md';
			return `<div class="cmi-h-msg ${cls}">${body}<span class="cmi-h-t">${when(m.at)}</span></div>`;
		}).join('') || '<div class="cmi-h-empty">Belum ada chat tersimpan.</div>';
		const mailHtml = emails.slice().reverse().map((m) => {
			const incoming = (m.role === 'customer');
			return `<div class="cmi-h-mail ${incoming ? 'in' : 'out'}">
				<div class="text-muted small">${incoming ? '📨 ' + esc(m.mail_to || 'Customer') : '🤖 keluar → ' + esc(m.mail_to || '-')} · ${when(m.at)}${m.status ? ' · ' + esc(m.status) : ''}</div>
				<div><b>${esc(m.subject || '(tanpa subjek)')}</b></div>
				<div style="white-space:pre-wrap;margin-top:2px;line-height:1.55;">${esc(window.cmiCleanMail(m.body || ''))}</div></div>`;
		}).join('') || '<div class="cmi-h-empty">Belum ada email tersimpan.</div>';
		$wrapper.html(`
			<div class="cmi-h">
				<div class="cmi-h-tabs">
					<span class="cmi-h-tab on" data-t="chat">💬 Chat (${chat.length})</span>
					<span class="cmi-h-tab" data-t="email">✉ Email (${emails.length})</span>
				</div>
				<div class="cmi-h-log cmi-h-chat">${chatHtml}</div>
				<div class="cmi-h-log cmi-h-email" style="display:none;">${mailHtml}</div>
			</div>`);
		$wrapper.find('.cmi-h-tab').on('click', function () {
			const t = $(this).data('t');
			$wrapper.find('.cmi-h-tab').removeClass('on'); $(this).addClass('on');
			$wrapper.find('.cmi-h-chat').toggle(t === 'chat');
			$wrapper.find('.cmi-h-email').toggle(t === 'email');
		});
	});
};

frappe.ui.form.on('Agent Administrator', {
	refresh(frm) {
		const fd = frm.fields_dict.history_html;
		if (!fd || !fd.$wrapper) return;
		if (frm.is_new()) { fd.$wrapper.html('<div class="text-muted" style="padding:12px;">Simpan dulu.</div>'); return; }
		window.cmi_history_render(fd.$wrapper, { agent_id: frm.doc.name });
	},
});

// Shared "Assistant" + "Email" tabs untuk dokumen yang di-handle agent.
// Di-load global via hooks.app_include_js. Tab "Assistant" = chat + activity dengan
// Agent Administrator yang me-link dokumen ini; tab "Email" = thread email job itu.
// Doctype cukup punya field HTML `assistant_html`/`email_html` (atau `custom_*` untuk
// core SI). Semua via agents.agent.fleet / api.
(function () {
	const CMI_EV_ICON = { created: '✨', intake: '📥', chat: '💬', broadcast: '📣', reminder: '🔔', email: '✉️', expense: '🧾', awaiting: '⏳', done: '✅', nudge: '👉', handoff: '🤝', report: '📝' };
	const ASSIST_DOCTYPES = ['Packing List', 'Shipping List', 'Expense Note', 'Sales Invoice'];

	// Render markdown pesan agent jadi HTML (tabel beneran via frappe.markdown {tables:true}),
	// dan ubah link /app/... jadi tombol yang membuka dokumen lewat router SPA.
	// Rapikan body email: hilangkan enter berlebih (CRLF→LF, baris-kosong beruntun → satu),
	// tapi pertahankan baris tunggal (tanda tangan/alamat tidak digabung).
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

	function cmi_asst_style() {
		if (document.getElementById('cmi-asst-style')) return;
		const css = `
		.cmi-asst { display:flex; flex-direction:column; gap:10px; max-width:900px; }
		.cmi-asst-empty { padding:20px; color:var(--text-muted,#6c7680); }
		.cmi-asst-head { display:flex; gap:10px; align-items:center; border-bottom:1px solid var(--border-color,#e2e2e2); padding-bottom:8px; }
		.cmi-ava { width:30px; height:30px; border-radius:50%; background:linear-gradient(135deg,var(--primary,#2490ef),#6aa8e8); color:#fff; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; flex:0 0 auto; }
		.cmi-pill { font-size:.7rem; font-weight:600; border-radius:999px; padding:1px 8px; background:var(--control-bg,#f4f5f6); }
		.cmi-pill.active{background:rgba(40,167,69,.12);color:#1a7f37} .cmi-pill.working{background:rgba(36,144,239,.12);color:#0a58ca}
		.cmi-pill.waiting{background:rgba(232,163,61,.14);color:#b96a00} .cmi-pill.idle{background:var(--control-bg,#f4f5f6);color:#6c7680} .cmi-pill.error{background:rgba(226,76,76,.12);color:#b42318}
		.cmi-chip { font-size:.7rem; font-weight:600; border-radius:999px; padding:1px 8px; background:rgba(36,144,239,.12); color:#0a58ca; }
		.cmi-chatlog { max-height:46vh; overflow-y:auto; display:flex; flex-direction:column; border:1px solid var(--border-color,#e2e2e2); border-radius:8px; padding:10px; background:var(--card-bg,#fff); }
		.cmi-msg { max-width:82%; margin-bottom:8px; padding:7px 11px; border-radius:12px; white-space:pre-wrap; word-wrap:break-word; font-size:13px; line-height:1.4; }
		.cmi-msg.u { margin-left:auto; background:var(--primary,#2490ef); color:#fff; border-bottom-right-radius:2px; }
		.cmi-msg.a { margin-right:auto; background:var(--control-bg,#f4f5f6); border-bottom-left-radius:2px; }
		.cmi-msg.cmi-md { white-space:normal; max-width:100%; }
		.cmi-md > :first-child { margin-top:0; } .cmi-md > :last-child { margin-bottom:0; }
		.cmi-md p { margin:0 0 6px; }
		.cmi-md table { border-collapse:collapse; width:100%; margin:6px 0; font-size:12.5px; background:var(--card-bg,#fff); }
		.cmi-md th, .cmi-md td { border:1px solid var(--border-color,#e2e2e2); padding:5px 9px; text-align:left; vertical-align:top; }
		.cmi-md thead th { background:var(--control-bg,#f4f5f6); font-weight:600; }
		.cmi-md code { background:rgba(0,0,0,.06); padding:1px 4px; border-radius:4px; font-size:.92em; }
		.cmi-md ul, .cmi-md ol { margin:4px 0 6px; padding-left:20px; }
		.cmi-route-btn { display:inline-flex; align-items:center; gap:4px; margin:2px 0; padding:3px 10px; border-radius:6px; background:var(--primary,#2490ef); color:#fff !important; font-weight:600; font-size:12px; text-decoration:none !important; }
		.cmi-route-btn:hover { filter:brightness(.94); color:#fff !important; }
		.cmi-chat-input { display:flex; gap:8px; align-items:flex-end; }
		.cmi-chat-text { resize:none; } .cmi-chat-send { height:38px; white-space:nowrap; }
		.cmi-act { border-top:1px dashed var(--border-color,#e2e2e2); padding-top:8px; }
		.cmi-act-h { font-weight:600; font-size:12px; margin-bottom:4px; }
		.cmi-ev { font-size:12px; padding:2px 0; } .cmi-ev-t { color:var(--text-muted,#6c7680); }
		.cmi-maillog { max-height:62vh; overflow-y:auto; }
		.cmi-mail { border:1px solid var(--border-color,#e2e2e2); border-radius:8px; padding:8px 10px; margin-bottom:8px; }
		.cmi-mail-h { display:flex; justify-content:space-between; align-items:center; }
		.cmi-mail-b { font-size:13px; white-space:pre-wrap; margin-top:4px; line-height:1.55; }
		.cmi-mail { padding:10px 12px; }
		.cmi-body { min-height:150px; }
		.cmi-mbadge { font-size:10.5px; font-weight:600; border-radius:999px; padding:1px 8px; }
		.cmi-mbadge.sent{background:rgba(40,167,69,.14);color:#1a7f37} .cmi-mbadge.logged{background:var(--control-bg,#f4f5f6);color:#6c7680} .cmi-mbadge.failed{background:rgba(226,76,76,.12);color:#b42318}
		.cmi-mail-compose { display:flex; flex-direction:column; gap:6px; margin-top:10px; border-top:1px dashed var(--border-color,#e2e2e2); padding-top:10px; }
		.cmi-mail-toolbar { display:flex; gap:8px; margin-bottom:4px; }
		.cmi-maillog { display:flex; flex-direction:column; gap:8px; }
		.cmi-mail.in { background:var(--control-bg,#f4f5f6); align-self:flex-start; max-width:88%; }
		.cmi-mail.out { background:rgba(36,144,239,.06); border-color:rgba(36,144,239,.28); align-self:flex-end; max-width:88%; }
		.cmi-mail-subj-line { margin-top:2px; }
		.cmi-mail-actions { margin-top:6px; }
		.cmi-compose-h { font-weight:600; }
		.cmi-compose-btns { display:flex; gap:8px; }
		.cmi-attach-row { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
		.cmi-mail-chips { display:inline-flex; flex-wrap:wrap; gap:6px; }
		.cmi-chip { font-size:11px; background:var(--control-bg,#f4f5f6); border:1px solid var(--border-color,#e2e2e2); border-radius:999px; padding:1px 8px; }
		.cmi-chip .cmi-chip-x { color:#b42318; text-decoration:none; margin-left:2px; font-weight:700; }
		.cmi-mbadge.draft{background:rgba(245,166,35,.16);color:#a35b00}
		.cmi-mbadge.latest{background:rgba(36,144,239,.16);color:#0a58ca}
		.cmi-mail-latest{border-color:var(--primary,#2490ef);box-shadow:0 0 0 1px var(--primary,#2490ef) inset;}
		.cmi-mail-hint{font-size:11.5px;color:var(--text-muted,#6c7680);margin-bottom:6px;}
		`;
		$('<style id="cmi-asst-style">').text(css).appendTo('head');
	}

	function cmi_ava(name) { const s = (name || '?').replace(/[^A-Za-z0-9]/g, ''); return (s.slice(0, 2) || '??').toUpperCase(); }

	function cmi_asst_render(frm) {
		const fd = frm.fields_dict || {};
		const fa = fd.assistant_html || fd.custom_assistant_html;
		const fe = fd.email_html || fd.custom_email_html;
		if (!fa || !fe) return;
		cmi_asst_style();
		const $a = fa.$wrapper, $e = fe.$wrapper;
		if (frm.is_new()) {
			$a.html('<div class="cmi-asst-empty">Simpan dokumen dulu untuk mengaktifkan Assistant.</div>');
			$e.html('<div class="cmi-asst-empty">Simpan dulu.</div>');
			return;
		}
		frappe.call({ method: 'agents.agent.fleet.doc_assistant', args: { doctype: frm.doctype, name: frm.doc.name } }).then((r) => {
			const d = (r && r.message) || {};
			if (!d.agent) {
				$a.html(`<div class="cmi-asst-empty">Belum ada Assistant untuk dokumen ini.<br><br>
					<button class="btn btn-sm btn-primary cmi-asst-start">🤖 Mulai Assistant</button></div>`);
				$a.find('.cmi-asst-start').on('click', () => {
					frappe.call({ method: 'agents.agent.fleet.ensure_agent_for', args: { doctype: frm.doctype, name: frm.doc.name }, freeze: true })
						.then(() => cmi_asst_render(frm));
				});
				$e.html('<div class="cmi-asst-empty">Mulai Assistant dulu (di tab Assistant).</div>');
				return;
			}
			cmi_asst_chat($a, frm, d);
			cmi_asst_email($e, frm, d);
		});
	}

	function cmi_asst_chat($w, frm, d) {
		const a = d.agent, esc = frappe.utils.escape_html;
		const msgs = (d.messages || []).map((m) => m.role === 'user'
			? `<div class="cmi-msg u">${esc(m.text)}</div>`
			: `<div class="cmi-msg a cmi-md">${window.cmiRenderMd(m.text)}</div>`).join('')
			|| '<div class="cmi-asst-empty" style="padding:8px;">Belum ada percakapan. Mulai chat dengan agent di bawah.</div>';
		const ev = (d.events || []).slice(0, 10).map((e) => `<div class="cmi-ev">${CMI_EV_ICON[e.kind] || '•'} ${esc(e.message || e.kind)} <span class="cmi-ev-t">· ${esc(frappe.datetime.comment_when(e.creation))}</span></div>`).join('')
			|| '<div class="text-muted small">Belum ada aktivitas.</div>';
		$w.html(`
			<div class="cmi-asst">
				<div class="cmi-asst-head"><span class="cmi-ava">${esc(cmi_ava(a.agent_name))}</span>
					<div><b>${esc(a.agent_name)}</b> <span class="cmi-pill ${a.kind}">${esc(a.kind_label || a.status)}</span> <span class="cmi-chip">🗂 ${esc(a.phase_label)}</span>
						<div class="text-muted small">${esc(a.task || '')}</div></div></div>
				<div class="cmi-chatlog">${msgs}</div>
				<div class="cmi-chat-input">
					<button class="btn btn-default cmi-chat-attach" title="Lampirkan PDF / gambar">📎</button>
					<textarea class="form-control cmi-chat-text" rows="2" placeholder="Chat / instruksi ke ${esc(a.agent_name)}… (Enter kirim)"></textarea>
					<button class="btn btn-primary cmi-chat-send">Kirim</button>
				</div>
				<div class="cmi-attach-note text-muted small" style="display:none;"></div>
				<input type="file" class="cmi-chat-file" accept="application/pdf,image/png,image/jpeg,image/webp,image/gif" multiple style="display:none;" />
				<div class="cmi-act"><div class="cmi-act-h">Aktivitas</div>${ev}</div>
			</div>`);
		const $log = $w.find('.cmi-chatlog'); $log.scrollTop($log[0].scrollHeight);
		const $file = $w.find('.cmi-chat-file'), $note = $w.find('.cmi-attach-note');
		let pending = 0, busy = false;
		const showPending = () => { $note.toggle(pending > 0).text(pending ? `📎 ${pending} lampiran siap dikirim bersama pesan` : ''); };
		$w.find('.cmi-chat-attach').on('click', () => $file.trigger('click'));
		$file.on('change', (e) => {
			Array.from(e.target.files || []).forEach((file) => {
				const reader = new FileReader();
				reader.onload = () => {
					const b64 = String(reader.result).split(',')[1] || '';
					frappe.call({ method: 'agents.agent.api.upload_attachment', args: { intake: a.name, filename: file.name, content_b64: b64 } }).then((r) => {
						const m = (r && r.message) || {};
						if (m.ok) { pending += 1; showPending(); frappe.show_alert({ message: `📎 ${file.name}`, indicator: 'green' }); }
						else frappe.show_alert({ message: m.error || 'Lampiran ditolak', indicator: 'red' });
					});
				};
				reader.readAsDataURL(file);
			});
			$file.val('');
		});
		const send = () => {
			if (busy) return;
			const $t = $w.find('.cmi-chat-text'), msg = ($t.val() || '').trim();
			if (!msg && pending === 0) return;
			$log.find('.cmi-asst-empty').remove();
			$log.append(`<div class="cmi-msg u">${esc(msg)}${pending ? '  📎×' + pending : ''}</div>`); $t.val('');
			const $typing = $('<div class="cmi-msg a">…</div>').appendTo($log); $log.scrollTop($log[0].scrollHeight);
			busy = true; pending = 0; showPending();
			$w.find('.cmi-chat-send').prop('disabled', true).text('…');
			frappe.call({ method: 'agents.agent.api.chat', args: { intake: a.name, message: msg } }).then((r) => {
				$typing.remove(); busy = false; $w.find('.cmi-chat-send').prop('disabled', false).text('Kirim');
				const m = r && r.message; if (m && m.reply) $log.append(`<div class="cmi-msg a cmi-md">${window.cmiRenderMd(m.reply)}</div>`);
				$log.scrollTop($log[0].scrollHeight); cmi_asst_render(frm);
			}).catch(() => { $typing.remove(); busy = false; $w.find('.cmi-chat-send').prop('disabled', false).text('Kirim'); });
		};
		$w.find('.cmi-chat-send').on('click', send);
		$w.find('.cmi-chat-text').on('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
	}

	function cmi_asst_email($w, frm, d) {
		const a = d.agent, esc = frappe.utils.escape_html;
		const mails = (d.mails || []).slice().reverse().map((m, i) => {
			const incoming = (m.role === 'customer');
			const who = incoming ? esc(m.mail_to || 'Customer') : '🤖 ' + esc(a.agent_name);
			const badge = incoming ? '<span class="cmi-mbadge logged">masuk</span>'
				: `<span class="cmi-mbadge ${esc(m.status)}">${esc(m.status)}</span>`;
			const latest = i === 0 ? '<span class="cmi-mbadge latest">★ Terbaru</span>' : '';
			return `<div class="cmi-mail ${incoming ? 'in' : 'out'}${i === 0 ? ' cmi-mail-latest' : ''}" data-to="${esc(m.mail_to || '')}" data-subj="${esc(m.subject || '')}">
				<div class="cmi-mail-h"><b>${incoming ? '📨 ' + who : who}</b><span>${latest}${badge}</span></div>
				<div class="text-muted small">${incoming ? 'From' : 'To'}: ${esc(m.mail_to || '-')} · ${esc(frappe.datetime.comment_when(m.creation))}</div>
				<div class="cmi-mail-subj-line"><b>${esc(m.subject || '(tanpa subjek)')}</b></div>
				<div class="cmi-mail-b">${esc(window.cmiCleanMail(m.body || ''))}</div>
				<div class="cmi-mail-actions"><button class="btn btn-xs btn-default cmi-reply">↩ Balas</button></div>
			</div>`;
		}).join('') || '<div class="cmi-asst-empty" style="padding:8px;">Belum ada email. Klik "Tulis email" atau "Catat email masuk".</div>';
		$w.html(`
			<div class="cmi-asst">
				<div class="cmi-mail-toolbar">
					<button class="btn btn-sm btn-primary cmi-new">✉️ Tulis email</button>
					<button class="btn btn-sm btn-default cmi-incoming">📥 Catat email masuk</button>
				</div>
				${(d.mails || []).length ? '<div class="cmi-mail-hint">📧 Urutan: <b>email terbaru di atas</b> ↓</div>' : ''}
				<div class="cmi-maillog">${mails}</div>
				<div class="cmi-mail-compose" style="display:none;">
					<div class="cmi-compose-h text-muted small"></div>
					<input class="form-control input-sm cmi-to" placeholder="To (email)">
					<input class="form-control input-sm cmi-subj" placeholder="Subject">
					<textarea class="form-control cmi-body" rows="8" placeholder="Tulis pesan…"></textarea>
					<div class="cmi-attach-row"><button class="btn btn-sm btn-default cmi-mail-attach" title="Lampirkan file">📎 Lampirkan</button> <span class="cmi-mail-chips"></span></div>
					<div class="cmi-compose-btns">
						<button class="btn btn-sm btn-primary cmi-send">Kirim</button>
						<button class="btn btn-sm btn-default cmi-cancel">Batal</button>
					</div>
					<input type="file" class="cmi-mail-file" multiple style="display:none;" />
				</div>
			</div>`);
		const $compose = $w.find('.cmi-mail-compose');
		let kind = 'send'; // 'send' = email keluar | 'incoming' = catat email masuk
		let mailAtt = []; // lampiran email keluar (file_url + nama)
		const $mailFile = $w.find('.cmi-mail-file'), $chips = $w.find('.cmi-mail-chips');
		const renderChips = () => {
			$chips.html(mailAtt.map((f, i) => `<span class="cmi-chip">📎 ${esc(f.file_name)} <a href="#" class="cmi-chip-x" data-i="${i}">×</a></span>`).join(''));
			$chips.find('.cmi-chip-x').on('click', (e) => { e.preventDefault(); mailAtt.splice($(e.currentTarget).data('i'), 1); renderChips(); });
		};
		$w.find('.cmi-mail-attach').on('click', () => $mailFile.trigger('click'));
		$mailFile.on('change', (e) => {
			Array.from(e.target.files || []).forEach((file) => {
				const reader = new FileReader();
				reader.onload = () => {
					const b64 = String(reader.result).split(',')[1] || '';
					frappe.call({ method: 'agents.agent.fleet.save_email_attachment', args: { intake: a.name, filename: file.name, content_b64: b64 } }).then((r) => {
						const m = (r && r.message) || {};
						if (m.file_url) { mailAtt.push({ file_url: m.file_url, file_name: m.file_name || file.name }); renderChips(); frappe.show_alert({ message: `📎 ${m.file_name || file.name}`, indicator: 'green' }); }
						else frappe.show_alert({ message: 'Gagal lampirkan', indicator: 'red' });
					});
				};
				reader.readAsDataURL(file);
			});
			$mailFile.val('');
		});
		const openCompose = (opts) => {
			kind = opts.incoming ? 'incoming' : 'send';
			mailAtt = []; renderChips();
			$w.find('.cmi-attach-row').toggle(!opts.incoming); // lampiran hanya untuk email keluar
			$w.find('.cmi-compose-h').text(opts.incoming ? 'Catat email MASUK dari customer' : (opts.reply ? 'Balas email' : 'Email baru'));
			const md = d.mail_defaults || {};
			$w.find('.cmi-to').attr('placeholder', opts.incoming ? 'From (email customer)' : 'To (email)')
				.val(opts.to || (opts.incoming ? '' : (md.to || a.contact_email || '')));
			$w.find('.cmi-subj').val(opts.subj || (opts.incoming ? '' : (md.subject || '')));
			$w.find('.cmi-body').val('');
			$compose.show();
			$w.find('.cmi-body').focus();
		};
		$w.find('.cmi-new').on('click', () => openCompose({}));
		$w.find('.cmi-incoming').on('click', () => openCompose({ incoming: true }));
		$w.find('.cmi-reply').on('click', function () {
			const $m = $(this).closest('.cmi-mail');
			const subj = String($m.data('subj') || '');
			openCompose({ reply: true, to: $m.data('to') || '', subj: /^re:/i.test(subj) ? subj : ('Re: ' + subj) });
		});
		$w.find('.cmi-cancel').on('click', () => $compose.hide());
		$w.find('.cmi-send').on('click', () => {
			const to = ($w.find('.cmi-to').val() || '').trim();
			const subject = ($w.find('.cmi-subj').val() || '').trim();
			const body = ($w.find('.cmi-body').val() || '').trim();
			if (!body) { frappe.show_alert({ message: 'Isi pesan dulu', indicator: 'orange' }); return; }
			const method = kind === 'incoming' ? 'agents.agent.fleet.log_incoming_mail' : 'agents.agent.fleet.send_mail';
			const args = kind === 'incoming'
				? { intake: a.name, from_email: to, subject, body }
				: { intake: a.name, mail_to: to, subject, body, role: 'user', attachments: JSON.stringify(mailAtt.map((f) => f.file_url)) };
			frappe.call({ method, args, freeze: true }).then((r) => {
				const m = (r && r.message) || {};
				const ok = kind === 'incoming' || m.status === 'sent';
				frappe.show_alert({
					message: kind === 'incoming' ? 'Email masuk dicatat' : `Email ${m.status || 'logged'} → ${m.to || to || '-'}`,
					indicator: ok ? 'green' : 'orange',
				});
				cmi_asst_render(frm);
			});
		});
	}

	// Di-load ON-DEMAND via frappe.require() dari masing-masing doctype JS. Di build
	// production (tanpa node / `bench build`), app_include_js path-mentah TIDAK ke-inject
	// ke desk — jadi doctype JS yang memanggil window.cmi_asst_render(frm) saat refresh.
	void ASSIST_DOCTYPES;
	window.cmi_asst_render = cmi_asst_render;
})();

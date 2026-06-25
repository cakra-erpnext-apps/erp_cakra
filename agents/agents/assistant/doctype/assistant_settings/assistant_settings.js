frappe.ui.form.on('Assistant Settings', {
	refresh(frm) {
		frm.add_custom_button(__('Test Connection'), () => {
			frappe.dom.freeze(__('Pinging AI accounts…'));
			frappe
				.call('agents.agent.api.test_connection')
				.then((r) => {
					frappe.dom.unfreeze();
					const m = r.message || {};
					if (!(m.accounts || []).length) {
						frappe.msgprint({ title: __('Not configured'), indicator: 'red', message: frappe.utils.escape_html(m.error || 'No accounts') });
						return;
					}
					const rows = m.accounts
						.map((a) => {
							const ok = a.ok ? '🟢' : '🔴';
							const info = a.ok ? __('replied: {0}', [a.reply || '']) : (a.error || 'failed');
							return `<tr><td>${ok}</td><td><b>${frappe.utils.escape_html(a.label || '')}</b><br><span class="text-muted small">${frappe.utils.escape_html(a.provider || '')} · ${frappe.utils.escape_html(a.model || '')}</span></td><td>${frappe.utils.escape_html(info)}</td></tr>`;
						})
						.join('');
					frappe.msgprint({
						title: __('AI Accounts'),
						indicator: m.ok ? 'green' : 'orange',
						message: `<table class="table table-bordered"><tbody>${rows}</tbody></table>`,
					});
				})
				.catch(() => frappe.dom.unfreeze());
		});

		frm.add_custom_button(__('Add AI Account'), () => {
			frm.add_child('providers', {
				provider: 'Anthropic (Claude)',
				base_url: 'https://api.anthropic.com',
				model: 'claude-opus-4-8',
				priority: 10,
				enabled: 1,
			});
			frm.refresh_field('providers');
			frappe.show_alert({ message: __('Akun ditambahkan — isi Label + API Key, lalu Save.'), indicator: 'blue' });
		});

		frm.add_custom_button(__('Reset Usage'), () => {
			frappe.confirm(__('Zero out all token counters and clear cooldowns?'), () => {
				frappe.call('agents.agent.api.reset_usage').then(() => {
					frappe.show_alert({ message: __('Usage reset.'), indicator: 'green' });
					frm.reload_doc();
				});
			});
		}, __('Usage'));

		frm.add_custom_button(__('View Usage'), () => {
			frappe.call('agents.agent.api.usage').then((r) => {
				const m = r.message || {};
				const rows = (m.accounts || [])
					.map((a) => `<tr><td>${frappe.utils.escape_html(a.label || '')}</td><td>${a.requests}</td><td>${a.tokens_in}</td><td>${a.tokens_out}</td><td>${a.tokens_today}${a.daily_token_limit ? ' / ' + a.daily_token_limit : ''}</td><td>${a.cooling_down ? '⏳ cooldown' : (a.limit_remaining || '-')}</td></tr>`)
					.join('');
				frappe.msgprint({
					title: __('AI Usage (failover: {0})', [m.auto_failover ? 'on' : 'off']),
					message: `<table class="table table-bordered"><thead><tr><th>Account</th><th>Req</th><th>Tok In</th><th>Tok Out</th><th>Today</th><th>Remaining</th></tr></thead><tbody>${rows || '<tr><td colspan=6>No accounts</td></tr>'}</tbody></table>`,
				});
			});
		}, __('Usage'));

		frm.add_custom_button(__('Load Default Skills'), () => {
			frappe.confirm(
				__('Replace the Document & Chat skills below with the built-in defaults? Unsaved edits will be overwritten.'),
				() => {
					frappe.call('agents.agent.api.get_default_skills').then((r) => {
						const d = r.message || {};
						frm.set_value('doc_extraction_skill', d.doc_extraction_skill || '');
						frm.set_value('chat_extraction_skill', d.chat_extraction_skill || '');
						frappe.show_alert({ message: __('Default skills loaded — review and Save.'), indicator: 'green' });
					});
				}
			);
		});

		frm.add_custom_button(__('Open Agent Chat'), () => {
			frappe.set_route('assistant-center');
		});
	},
});

// Auto-fill Base URL + Model when the provider is chosen on an account row.
frappe.ui.form.on('Agent Provider', {
	provider(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const map = {
			'Anthropic (Claude)': ['https://api.anthropic.com', 'claude-opus-4-8'],
			'OpenAI (ChatGPT)': ['https://api.openai.com/v1', 'gpt-4o'],
			'Google (Gemini)': ['https://generativelanguage.googleapis.com/v1beta/openai', 'gemini-2.0-flash'],
			'OpenAI Compatible': ['', ''],
		};
		const d = map[row.provider];
		if (!d) return;
		frappe.model.set_value(cdt, cdn, 'base_url', d[0]);
		frappe.model.set_value(cdt, cdn, 'model', d[1]);
	},
});

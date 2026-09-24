// Section "Email" di bagian bawah form transaksi, tepat di atas Comments: email yang
// tertaut ke dokumen ini (dari Outlook lewat add-in ERPNext, atau dari halaman Mailbox),
// ditampilkan seperti Mailbox -- daftar di kiri, isi di kanan, terbaru langsung terbuka.
//
// Dimuat di semua halaman desk (hooks app_include_js) dan dipasang lewat event
// `form-refresh` yang dikirim Frappe setiap form dimuat ulang. Section hanya muncul kalau
// dokumennya punya email tertaut; server menjawab kosong untuk doctype yang bukan
// transaksi, jadi form lain tidak kena apa-apa.
//
// Data dari erpnext_custom.mail_inbox.linked_emails / linked_email: izinnya dari dokumen
// transaksi, bukan dari Communication. Email yang sudah tampil di sini disembunyikan dari
// Activity supaya tidak dobel. Badan email = HTML kiriman orang luar, jadi dirender di
// <iframe sandbox> tanpa allow-scripts, sama seperti halaman Mailbox.
(function () {
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

	function style() {
		if (document.getElementById("cmi-lm-style")) return;
		$('<style id="cmi-lm-style">')
			.text(
				`
			.cmi-email-section { margin: 8px 0 24px; }
			.cmi-lm-head { display: flex; justify-content: space-between; align-items: center;
				margin-bottom: 12px; }
			.cmi-lm-title { font-size: var(--text-lg); font-weight: 600; color: var(--heading-color, var(--text-color)); }
			.cmi-lm-title .cmi-lm-count { color: var(--text-muted); font-weight: normal; }
			.cmi-lm-box { display: flex; height: 480px; border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); overflow: hidden; background: var(--fg-color); }
			.cmi-lm-list { flex: 0 0 300px; overflow: auto; border-right: 1px solid var(--border-color); }
			.cmi-lm-reader { flex: 1 1 auto; display: flex; flex-direction: column; min-width: 0; }
			.cmi-lm-item { padding: 9px 12px; border-bottom: 1px solid var(--border-color);
				cursor: pointer; border-left: 3px solid transparent; }
			.cmi-lm-item:hover { background: var(--fg-hover-color, var(--gray-100)); }
			.cmi-lm-item.active { background: var(--bg-blue, var(--gray-200));
				border-left-color: var(--blue-500, #2490ef); }
			.cmi-lm-top { display: flex; justify-content: space-between; gap: 8px; }
			.cmi-lm-from, .cmi-lm-subj, .cmi-lm-snip { overflow: hidden; text-overflow: ellipsis;
				white-space: nowrap; }
			.cmi-lm-date, .cmi-lm-snip { color: var(--text-muted); font-size: var(--text-sm); }
			.cmi-lm-date { white-space: nowrap; }
			.cmi-lm-tag { font-size: 10.5px; padding: 0 6px; border-radius: 8px;
				background: var(--bg-green, var(--gray-100)); margin-right: 4px; }
			.cmi-lm-rhead { padding: 10px 14px; border-bottom: 1px solid var(--border-color); }
			.cmi-lm-rhead h5 { margin: 0 0 4px; font-size: var(--text-lg); }
			.cmi-lm-meta { color: var(--text-muted); font-size: var(--text-sm); line-height: 1.6; }
			.cmi-lm-files { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
			.cmi-lm-files a { font-size: var(--text-sm); padding: 2px 8px; border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); }
			.cmi-lm-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
			/* latar putih: badan email ditulis untuk latar terang */
			.cmi-lm-body { flex: 1 1 auto; border: 0; width: 100%; background: #fff; }
			.cmi-lm-empty { padding: 32px 16px; text-align: center; color: var(--text-muted); }
			@media (max-width: 900px) { .cmi-lm-list { flex-basis: 200px; } }
			/* Penanda .cmi-has-email-section ada di frm.wrapper, yang membungkus tab-tab DAN
			   bagian bawah form (section Email, Comments, Activity) sekaligus. */

			/* Email sudah tampil di section Email, jadi tidak diulang di Activity. Hanya item
			   berikon "mail" (email); pesan otomatis ("notification"), telepon, rapat tetap. */
			.cmi-has-email-section .timeline-item[data-doctype="Communication"]:has(> .timeline-badge[title="Mail"]) {
				display: none;
			}

			/* Di tab Assistant, section Email tidak ikut tampil. */
			.cmi-has-email-section:has(.tab-pane.active [data-fieldname="assistant_html"]) .cmi-email-section,
			.cmi-has-email-section:has(.tab-pane.active [data-fieldname="custom_assistant_html"]) .cmi-email-section {
				display: none;
			}
			`
			)
			.appendTo("head");
	}

	function when(value) {
		if (!value) return "";
		const d = frappe.datetime.str_to_obj(value);
		if (d.toDateString() === new Date().toDateString()) return d.toTimeString().slice(0, 5);
		return frappe.datetime.str_to_user(value).split(" ")[0];
	}

	function snippet(text) {
		const flat = (text || "").replace(/\s+/g, " ").trim();
		return flat.length > 120 ? flat.slice(0, 120) + "..." : flat;
	}

	// Section dibuat sekali per form, disisipkan sebelum Comments (.comment-box).
	function section(frm) {
		const $footer = frm.footer && frm.footer.wrapper;
		if (!$footer) return null;
		let $s = $footer.find(".cmi-email-section");
		if (!$s.length) $s = $('<div class="cmi-email-section"></div>').insertBefore($footer.find(".comment-box"));
		return $s;
	}

	function clear(frm) {
		$(frm.wrapper).removeClass("cmi-has-email-section");
		if (frm.footer && frm.footer.wrapper) frm.footer.wrapper.find(".cmi-email-section").remove();
	}

	function refresh(frm) {
		if (!frm || !frm.doc || frm.is_new()) return frm && clear(frm);

		const doctype = frm.doctype;
		const docname = frm.doc.name;
		frappe
			.xcall("erpnext_custom.mail_inbox.linked_emails", { doctype, name: docname })
			.then((mails) => {
				// form sudah pindah ke dokumen lain sebelum jawaban datang
				if (frm.doctype !== doctype || frm.doc.name !== docname) return;
				if (!mails || !mails.length) return clear(frm);

				style();
				$(frm.wrapper).addClass("cmi-has-email-section");
				render(frm, section(frm), mails);
			})
			.catch(() => clear(frm));
	}

	function render(frm, $s, mails) {
		if (!$s) return;
		$s.html(`
			<div class="cmi-lm-head">
				<span class="cmi-lm-title">${__("Email")} <span class="cmi-lm-count">(${mails.length})</span></span>
				<button class="btn btn-xs btn-default cmi-lm-refresh">${__("Muat ulang")}</button>
			</div>
			<div class="cmi-lm-box">
				<div class="cmi-lm-list">${mails.map(item).join("")}</div>
				<div class="cmi-lm-reader"></div>
			</div>`);

		$s.find(".cmi-lm-refresh").on("click", () => refresh(frm));
		$s.find(".cmi-lm-item").on("click", function () {
			open(frm, $s, this.getAttribute("data-name"));
		});
		// terbaru langsung terbuka
		open(frm, $s, mails[0].name);
	}

	function item(m) {
		const sent = m.sent_or_received === "Sent";
		const who = sent ? m.recipients : m.sender_full_name || m.sender;
		return `
			<div class="cmi-lm-item" data-name="${esc(m.name)}">
				<div class="cmi-lm-top">
					<span class="cmi-lm-from">${sent ? `<span class="cmi-lm-tag">${__("Terkirim")}</span>` : ""}${esc(who)}</span>
					<span class="cmi-lm-date">${esc(when(m.communication_date))}</span>
				</div>
				<div class="cmi-lm-subj">${esc(m.subject || __("(tanpa judul)"))}</div>
				<div class="cmi-lm-snip">${esc(snippet(m.text_content))}</div>
			</div>`;
	}

	function open(frm, $s, name) {
		$s.find(".cmi-lm-item").removeClass("active");
		$s.find(`.cmi-lm-item[data-name="${CSS.escape(name)}"]`).addClass("active");
		const $reader = $s.find(".cmi-lm-reader").html(`<div class="cmi-lm-empty">${__("Memuat...")}</div>`);

		frappe
			.xcall("erpnext_custom.mail_inbox.linked_email", {
				doctype: frm.doctype,
				name: frm.doc.name,
				communication: name,
			})
			.then((m) => {
				$reader.html(`
					<div class="cmi-lm-rhead">
						<h5>${esc(m.subject || __("(tanpa judul)"))}</h5>
						<div class="cmi-lm-meta">
							<div><b>${esc(m.sender_full_name || m.sender)}</b> ${m.sender ? "&lt;" + esc(m.sender) + "&gt;" : ""}</div>
							<div>${__("Kepada")}: ${esc(m.recipients || "")}</div>
							${m.cc ? `<div>Cc: ${esc(m.cc)}</div>` : ""}
							<div>${esc(frappe.datetime.str_to_user(m.communication_date))}</div>
						</div>
						<div class="cmi-lm-files">${(m.attachments || [])
							.map((f) => `<a href="${esc(f.file_url)}" target="_blank">${esc(f.file_name || f.file_url)}</a>`)
							.join("")}</div>
						<div class="cmi-lm-actions">
							<button class="btn btn-xs btn-default" data-act="reply">${__("Balas")}</button>
							<button class="btn btn-xs btn-default" data-act="reply-all">${__("Balas Semua")}</button>
							<button class="btn btn-xs btn-default" data-act="forward">${__("Teruskan")}</button>
							<button class="btn btn-xs btn-default" data-act="unlink">${__("Lepas tautan")}</button>
						</div>
					</div>
					<iframe class="cmi-lm-body" sandbox="allow-popups allow-popups-to-escape-sandbox"></iframe>`);

				const body = m.content || (m.text_content ? `<pre>${esc(m.text_content)}</pre>` : "");
				$reader.find(".cmi-lm-body").attr(
					"srcdoc",
					`<!doctype html><html><head><meta charset="utf-8"><base target="_blank">
					<style>body{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;font-size:13px;color:#1f272e;margin:14px;word-wrap:break-word}
					img{max-width:100%;height:auto}table{max-width:100%}
					blockquote{border-left:2px solid #d1d8dd;margin:0;padding-left:12px;color:#6b7580}</style></head>
					<body>${body}</body></html>`
				);

				$reader.find("[data-act]").on("click", function () {
					const act = this.getAttribute("data-act");
					if (act === "unlink") return unlink(frm, m);
					// Menulis balasan memakai komposer halaman Mailbox; balasannya otomatis
					// tertaut ke transaksi yang sama dengan email aslinya.
					// message_id: Mailbox mode laptop mencari suratnya di mailbox Microsoft user.
					frappe.route_options = { open: m.name, compose: act, message_id: m.message_id };
					frappe.set_route("mailbox");
				});
			});
	}

	function unlink(frm, m) {
		frappe.confirm(
			__("Lepas percakapan \"{0}\" (email ini beserta balasan-balasannya) dari {1}? Emailnya tidak dihapus, hanya tidak tampil lagi di sini.", [
				esc(m.subject || __("(tanpa judul)")),
				esc(frm.doc.name),
			]),
			() =>
				frappe
					.xcall("erpnext_custom.mail_inbox.unlink_transaction", {
						communication: m.name,
						doctype: frm.doctype,
						name: frm.doc.name,
					})
					.then(() => refresh(frm))
		);
	}

	$(document).on("form-refresh", (_e, frm) => refresh(frm));
})();

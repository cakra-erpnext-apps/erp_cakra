// Mailbox: tampilan tiga panel (folder | daftar | isi surat) untuk email yang sudah
// ditarik Email Account ke Communication. Inbox bawaan desk cuma daftar dokumen biasa
// dan setiap surat harus dibuka sebagai form -- di sini isinya langsung terbaca di
// sebelah kanan seperti webmail.
//
// Sumber datanya tetap Communication, tidak ada tabel baru: folder cuma kombinasi filter
// yang sama dengan inbox bawaan (lihat get_filters), jadi apa yang tampil di sini sama
// dengan yang tampil di /app/communication.
//
// Badan email adalah HTML kiriman orang luar, jadi selalu dirender di dalam <iframe
// sandbox> tanpa allow-scripts: skrip, form, dan navigasi dari dalam email tidak bisa
// jalan. Jangan pernah menempelkan doc.content langsung ke halaman.
frappe.pages["mailbox"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Mailbox"),
		single_column: true,
	});

	new Mailbox(page);
};

const PAGE_LENGTH = 50;
const SNIPPET_LENGTH = 160;
// Sent/Spam/Trash ikut terdaftar di frappe.boot.email_accounts sebagai akun semu -- itu
// folder, bukan mailbox, jadi tidak boleh masuk pemilih akun.
const PSEUDO_ACCOUNTS = ["Sent", "Spam", "Trash", "All Accounts"];

class Mailbox {
	constructor(page) {
		this.page = page;
		this.accounts = (frappe.boot.email_accounts || []).filter(
			(a) => !PSEUDO_ACCOUNTS.includes(a.email_account)
		);
		this.account = this.accounts.length ? this.accounts[0].email_account : null;
		this.folder = "Inbox";
		this.search = "";
		this.start = 0;
		this.mails = [];
		this.current = null;

		this.render_shell();
		this.setup_toolbar();
		this.bind();

		if (!this.account) {
			this.show_no_account();
			return;
		}

		this.load_list();
		this.load_counts();
	}

	render_shell() {
		this.$body = $(`
			<div class="mbx">
				<style>
					.mbx { display: flex; gap: 12px; align-items: stretch;
						height: calc(100vh - 160px); min-height: 420px; }
					.mbx-pane { border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md); background: var(--fg-color);
						overflow: auto; }
					.mbx-folders { flex: 0 0 200px; padding: 8px; }
					.mbx-list { flex: 0 0 360px; padding: 0; }
					.mbx-reader { flex: 1 1 auto; display: flex; flex-direction: column;
						overflow: hidden; }

					.mbx-folder { display: flex; justify-content: space-between; align-items: center;
						gap: 8px; padding: 7px 10px; border-radius: var(--border-radius-md);
						cursor: pointer; font-size: var(--text-md); }
					.mbx-folder:hover { background: var(--fg-hover-color, var(--gray-100)); }
					.mbx-folder.active { background: var(--bg-blue, var(--gray-200)); font-weight: 600; }
					.mbx-folder .mbx-count { color: var(--text-muted); font-size: var(--text-sm); }
					.mbx-account { width: 100%; margin-bottom: 8px; }

					.mbx-item { padding: 10px 12px; border-bottom: 1px solid var(--border-color);
						cursor: pointer; border-left: 3px solid transparent; }
					.mbx-item:hover { background: var(--fg-hover-color, var(--gray-100)); }
					.mbx-item.active { background: var(--bg-blue, var(--gray-200));
						border-left-color: var(--blue-500, #2490ef); }
					/* belum dibaca: tebal + pita biru, sama isyaratnya dengan webmail lain */
					.mbx-item.unread { border-left-color: var(--blue-500, #2490ef); }
					.mbx-item.unread .mbx-from, .mbx-item.unread .mbx-subject { font-weight: 700; }
					.mbx-item-top { display: flex; justify-content: space-between; gap: 8px; }
					.mbx-from { font-size: var(--text-md); overflow: hidden;
						text-overflow: ellipsis; white-space: nowrap; }
					.mbx-date { color: var(--text-muted); font-size: var(--text-sm);
						white-space: nowrap; }
					.mbx-subject { font-size: var(--text-md); margin-top: 2px;
						overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
					.mbx-snippet { color: var(--text-muted); font-size: var(--text-sm);
						margin-top: 2px; overflow: hidden; text-overflow: ellipsis;
						white-space: nowrap; }

					.mbx-head { padding: 12px 16px; border-bottom: 1px solid var(--border-color); }
					.mbx-head h4 { margin: 0 0 6px; font-size: var(--text-xl); }
					.mbx-meta { color: var(--text-muted); font-size: var(--text-sm);
						line-height: 1.6; }
					.mbx-actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
					.mbx-attachments { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
					.mbx-attachments a { font-size: var(--text-sm); padding: 3px 8px;
						border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md); }
					/* Latar iframe dipaksa putih: badan email ditulis untuk latar terang,
					   ikut tema gelap desk bikin banyak email jadi hitam-di-hitam. */
					.mbx-body { flex: 1 1 auto; border: 0; width: 100%; background: #fff; }
					.mbx-empty { padding: 40px 16px; text-align: center; color: var(--text-muted); }
					.mbx-more { padding: 10px; text-align: center; }

					@media (max-width: 1200px) {
						.mbx-folders { flex-basis: 150px; }
						.mbx-list { flex-basis: 300px; }
						.mbx-snippet { display: none; }
					}
				</style>
				<div class="mbx-pane mbx-folders"></div>
				<div class="mbx-pane mbx-list"></div>
				<div class="mbx-pane mbx-reader">
					<div class="mbx-empty">${__("Pilih satu email untuk dibaca")}</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$folders = this.$body.find(".mbx-folders");
		this.$list = this.$body.find(".mbx-list");
		this.$reader = this.$body.find(".mbx-reader");
		this.render_folders();
	}

	setup_toolbar() {
		this.page.set_primary_action(__("Tulis"), () => this.compose(), "add");
		// Tarik Email menghubungi server mail; Muat Ulang cuma membaca ulang dari database.
		// Dua-duanya perlu: penarikan makan waktu, membaca ulang instan.
		this.page.set_secondary_action(__("Tarik Email"), () => this.sync(), "refresh");
		this.page.add_menu_item(__("Muat Ulang"), () => {
			this.refresh();
			this.load_counts();
		});

		// Penarikan jalan di latar, jadi hasilnya datang lewat realtime, bukan balasan
		// panggilan tadi.
		frappe.realtime.on("cmi_mailbox_synced", (data) => this.on_synced(data));

		this.$search = this.page.add_field({
			fieldtype: "Data",
			fieldname: "mbx_search",
			label: __("Cari pengirim atau judul"),
			change: frappe.utils.debounce(() => {
				this.search = (this.$search.get_value() || "").trim();
				this.refresh();
			}, 400),
		});
	}

	render_folders() {
		const folders = [
			{ name: "Inbox", label: __("Kotak Masuk") },
			{ name: "Sent", label: __("Terkirim") },
			{ name: "Spam", label: __("Spam") },
			{ name: "Trash", label: __("Sampah") },
		];

		const options = this.accounts
			.map(
				(a) =>
					`<option value="${frappe.utils.escape_html(a.email_account)}">
						${frappe.utils.escape_html(a.email_id)}
					</option>`
			)
			.join("");

		this.$folders.html(`
			<select class="form-control mbx-account">${options}</select>
			${folders
				.map(
					(f) => `
				<div class="mbx-folder ${f.name === this.folder ? "active" : ""}" data-folder="${f.name}">
					<span>${f.label}</span>
					<span class="mbx-count" data-count="${f.name}"></span>
				</div>`
				)
				.join("")}
		`);
		this.$folders.find(".mbx-account").val(this.account);
	}

	bind() {
		this.$folders.on("change", ".mbx-account", (e) => {
			this.account = $(e.currentTarget).val();
			this.refresh();
			this.load_counts();
		});

		this.$folders.on("click", ".mbx-folder", (e) => {
			this.folder = $(e.currentTarget).data("folder");
			this.$folders.find(".mbx-folder").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.refresh();
		});

		this.$list.on("click", ".mbx-item", (e) => this.open($(e.currentTarget).data("name")));
		this.$list.on("click", ".mbx-more button", () => this.load_list(true));
	}

	refresh() {
		this.start = 0;
		this.mails = [];
		this.load_list();
	}

	sync() {
		this.page.btn_secondary.prop("disabled", true);
		frappe.show_alert({ message: __("Menarik email dari server..."), indicator: "blue" });

		frappe
			.call({
				method: "erpnext_custom.mail_inbox.pull_now",
				args: { email_account: this.account },
			})
			.catch(() => this.page.btn_secondary.prop("disabled", false));
	}

	on_synced(data) {
		if (!data || data.email_account !== this.account) return;

		this.page.btn_secondary.prop("disabled", false);

		if (data.error) {
			frappe.show_alert({ message: __("Gagal menarik: {0}", [data.error]), indicator: "red" });
			return;
		}

		frappe.show_alert({
			message: data.baru
				? __("{0} email baru", [data.baru])
				: __("Tidak ada email baru"),
			indicator: data.baru ? "green" : "gray",
		});

		this.refresh();
		this.load_counts();
	}

	// Folder di sini cuma kombinasi filter Communication -- disamakan dengan inbox bawaan
	// (frappe/public/js/frappe/views/inbox/inbox_view.js) supaya isi keduanya tidak beda.
	// Bedanya satu: Kotak Masuk TIDAK menyaring status=Open, karena email yang sudah
	// dibalas tetap harus kelihatan di kotak masuk seperti di webmail mana pun.
	get_filters() {
		const filters = [
			["communication_type", "=", "Communication"],
			["communication_medium", "=", "Email"],
		];

		if (this.folder === "Sent") {
			filters.push(["sent_or_received", "=", "Sent"]);
			filters.push(["email_account", "=", this.account]);
			filters.push(["email_status", "not in", ["Spam", "Trash"]]);
		} else if (this.folder === "Spam" || this.folder === "Trash") {
			filters.push(["email_status", "=", this.folder]);
			filters.push(["email_account", "=", this.account]);
		} else {
			filters.push(["sent_or_received", "=", "Received"]);
			filters.push(["email_account", "=", this.account]);
			filters.push(["email_status", "not in", ["Spam", "Trash"]]);
		}

		return filters;
	}

	get_or_filters() {
		if (!this.search) return null;
		const like = `%${this.search}%`;
		return [
			["subject", "like", like],
			["sender", "like", like],
			["sender_full_name", "like", like],
		];
	}

	load_list(append = false) {
		if (!append) this.start = 0;

		const args = {
			doctype: "Communication",
			filters: this.get_filters(),
			fields: [
				"name",
				"subject",
				"sender",
				"sender_full_name",
				"recipients",
				"communication_date",
				"seen",
				"has_attachment",
				"text_content",
			],
			order_by: "communication_date desc",
			limit_start: this.start,
			limit_page_length: PAGE_LENGTH,
		};

		// or_filters HANYA dikirim kalau memang ada pencarian. Kirim nilai kosong dan
		// jQuery menuliskannya sebagai string kosong di badan permintaan; Frappe
		// menerjemahkan string di posisi itu sebagai nama dokumen, jadi query-nya jadi
		// `AND name = ''` dan daftarnya selalu kosong -- tanpa error, tanpa Error Log.
		const or_filters = this.get_or_filters();
		if (or_filters) args.or_filters = or_filters;

		frappe.call({
			method: "frappe.client.get_list",
			args: args,
		}).then((r) => {
			const rows = r.message || [];
			this.mails = append ? this.mails.concat(rows) : rows;
			this.start = this.mails.length;
			this.render_list(rows.length === PAGE_LENGTH);
		});
	}

	render_list(has_more) {
		if (!this.mails.length) {
			this.$list.html(`<div class="mbx-empty">${__("Tidak ada email di folder ini")}</div>`);
			return;
		}

		const html = this.mails.map((m) => this.item_html(m)).join("");
		this.$list.html(
			html +
				(has_more
					? `<div class="mbx-more"><button class="btn btn-default btn-sm">${__(
							"Muat lagi"
					  )}</button></div>`
					: "")
		);

		if (this.current) {
			this.$list.find(`[data-name="${this.current.name}"]`).addClass("active");
		}
	}

	item_html(m) {
		// Di folder Terkirim yang penting lawan bicaranya, bukan diri sendiri.
		const who =
			this.folder === "Sent"
				? m.recipients || ""
				: m.sender_full_name || m.sender || "";

		return `
			<div class="mbx-item ${m.seen ? "" : "unread"}" data-name="${frappe.utils.escape_html(m.name)}">
				<div class="mbx-item-top">
					<span class="mbx-from">${frappe.utils.escape_html(who)}</span>
					<span class="mbx-date">${this.format_date(m.communication_date)}</span>
				</div>
				<div class="mbx-subject">
					${m.has_attachment ? '<span title="Ada lampiran">&#128206;</span> ' : ""}
					${frappe.utils.escape_html(m.subject || __("(tanpa judul)"))}
				</div>
				<div class="mbx-snippet">${frappe.utils.escape_html(this.snippet(m.text_content))}</div>
			</div>
		`;
	}

	snippet(text) {
		if (!text) return "";
		const flat = text.replace(/\s+/g, " ").trim();
		return flat.length > SNIPPET_LENGTH ? flat.slice(0, SNIPPET_LENGTH) + "..." : flat;
	}

	// Hari ini cukup jamnya, tahun ini tanggal-bulan, lebih lama baru tahunnya ikut --
	// kolom tanggal sempit dan yang dicari orang biasanya "kapan kira-kira", bukan detik.
	format_date(value) {
		if (!value) return "";
		const d = frappe.datetime.str_to_obj(value);
		const now = frappe.datetime.now_datetime ? frappe.datetime.str_to_obj(frappe.datetime.now_datetime()) : new Date();

		if (d.toDateString() === now.toDateString()) {
			return d.toTimeString().slice(0, 5);
		}
		if (d.getFullYear() === now.getFullYear()) {
			return frappe.datetime.str_to_user(value).slice(0, 5);
		}
		return frappe.datetime.str_to_user(value).split(" ")[0];
	}

	open(name) {
		this.$list.find(".mbx-item").removeClass("active");
		this.$list.find(`[data-name="${name}"]`).addClass("active");
		this.$reader.html(`<div class="mbx-empty">${__("Memuat...")}</div>`);

		frappe.db.get_doc("Communication", name).then((doc) => {
			this.current = doc;
			this.render_reader(doc);
			this.mark_seen(doc);
		});
	}

	mark_seen(doc) {
		if (doc.seen || this.folder === "Sent") return;

		frappe.db.set_value("Communication", doc.name, "seen", 1).then(() => {
			doc.seen = 1;
			const row = this.mails.find((m) => m.name === doc.name);
			if (row) row.seen = 1;
			this.$list.find(`[data-name="${doc.name}"]`).removeClass("unread");
			this.load_counts();
		});
	}

	render_reader(doc) {
		this.$reader.html(`
			<div class="mbx-head">
				<h4>${frappe.utils.escape_html(doc.subject || __("(tanpa judul)"))}</h4>
				<div class="mbx-meta">
					<div><b>${frappe.utils.escape_html(doc.sender_full_name || doc.sender || "")}</b>
						${doc.sender ? "&lt;" + frappe.utils.escape_html(doc.sender) + "&gt;" : ""}</div>
					<div>${__("Kepada")}: ${frappe.utils.escape_html(doc.recipients || "")}</div>
					${doc.cc ? `<div>Cc: ${frappe.utils.escape_html(doc.cc)}</div>` : ""}
					<div>${frappe.datetime.str_to_user(doc.communication_date)}</div>
				</div>
				<div class="mbx-attachments"></div>
				<div class="mbx-actions">
					<button class="btn btn-default btn-sm" data-act="reply">${__("Balas")}</button>
					<button class="btn btn-default btn-sm" data-act="reply-all">${__("Balas Semua")}</button>
					<button class="btn btn-default btn-sm" data-act="forward">${__("Teruskan")}</button>
					<button class="btn btn-default btn-sm" data-act="doc">${__("Buka Dokumen")}</button>
				</div>
			</div>
			<iframe class="mbx-body" sandbox="allow-popups allow-popups-to-escape-sandbox"></iframe>
		`);

		this.$reader.find("[data-act]").on("click", (e) => {
			const act = $(e.currentTarget).data("act");
			if (act === "doc") frappe.set_route("Form", "Communication", doc.name);
			else this.compose(act);
		});

		this.render_body(doc);
		this.load_attachments(doc);
	}

	render_body(doc) {
		const body =
			doc.content ||
			(doc.text_content ? `<pre>${frappe.utils.escape_html(doc.text_content)}</pre>` : "");

		// srcdoc + sandbox tanpa allow-scripts: HTML email dirender apa adanya tapi
		// skripnya mati. base target=_blank supaya tautan di dalamnya buka tab baru,
		// bukan menggantikan halaman desk.
		const html = `<!doctype html>
			<html><head><meta charset="utf-8"><base target="_blank">
			<style>
				body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					font-size: 13px; color: #1f272e; margin: 16px; word-wrap: break-word; }
				img { max-width: 100%; height: auto; }
				table { max-width: 100%; }
				blockquote { border-left: 2px solid #d1d8dd; margin: 0; padding-left: 12px;
					color: #6b7580; }
			</style></head>
			<body>${body}</body></html>`;

		this.$reader.find(".mbx-body").attr("srcdoc", html);
	}

	load_attachments(doc) {
		if (!doc.has_attachment) return;

		frappe.db
			.get_list("File", {
				filters: { attached_to_doctype: "Communication", attached_to_name: doc.name },
				fields: ["file_name", "file_url"],
				limit: 50,
			})
			.then((files) => {
				if (!files || !files.length) return;
				this.$reader.find(".mbx-attachments").html(
					files
						.map(
							(f) =>
								`<a href="${frappe.utils.escape_html(f.file_url)}" target="_blank">
									${frappe.utils.escape_html(f.file_name || f.file_url)}
								</a>`
						)
						.join("")
				);
			});
	}

	compose(act) {
		const doc = this.current;
		if (!act || !doc) {
			new frappe.views.CommunicationComposer({});
			return;
		}

		const forward = act === "forward";
		const clean = (doc.subject || "").replace(/^((re|fwd):\s*)+/i, "");

		new frappe.views.CommunicationComposer({
			doc: { doctype: "Communication", name: doc.name },
			subject: (forward ? __("Fwd: ") : __("Re: ")) + clean,
			recipients: forward ? "" : doc.sender,
			cc: act === "reply-all" ? doc.cc : "",
			is_a_reply: !forward,
			forward: forward,
			last_email: doc,
			real_name: doc.sender_full_name,
		});
	}

	load_counts() {
		if (!this.account) return;

		frappe.db
			.count("Communication", {
				filters: {
					communication_type: "Communication",
					communication_medium: "Email",
					sent_or_received: "Received",
					email_account: this.account,
					seen: 0,
				},
			})
			.then((count) => {
				this.$folders.find('[data-count="Inbox"]').text(count || "");
			});
	}

	show_no_account() {
		this.$body.find(".mbx-list, .mbx-reader").html(`
			<div class="mbx-empty">
				${__("Belum ada mailbox untuk user ini.")}<br>
				${__("Tambahkan Email Account incoming, lalu daftarkan di tab Email pada User.")}
			</div>
		`);
	}
}

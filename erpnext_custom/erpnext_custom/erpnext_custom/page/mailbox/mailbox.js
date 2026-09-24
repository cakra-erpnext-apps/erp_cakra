// Mailbox: tampilan tiga panel (folder | daftar | isi surat) untuk email yang sudah
// ditarik Email Account ke Communication. Inbox bawaan desk cuma daftar dokumen biasa
// dan setiap surat harus dibuka sebagai form -- di sini isinya langsung terbaca di
// sebelah kanan seperti webmail, dan menulis/membalas juga di panel itu (bukan modal).
//
// Sumber datanya tetap Communication, tidak ada tabel baru. Folder kiri = folder IMAP yang
// didaftarkan di Email Account (asal tiap surat dicatat ke Communication.imap_folder oleh
// erpnext_custom.mail_inbox), ditambah Terkirim/Spam/Sampah yang berupa status. Folder IMAP
// bertanda "Folder Terkirim" (Sent Items) tidak didaftar sendiri: isinya masuk Terkirim.
//
// Badan email adalah HTML kiriman orang luar, jadi selalu dirender di dalam <iframe
// sandbox> tanpa allow-scripts: skrip, form, dan navigasi dari dalam email tidak bisa
// jalan. Jangan pernah menempelkan doc.content langsung ke halaman.
//
// TIDAK ADA frappe.realtime di sini. Di desk ini `frappe.realtime.on` membuang listener
// diam-diam kalau socket belum terbentuk saat halaman dimuat (lihat
// public/js/notification_badge.js); tombol Tarik Email versi pertama menunggu sinyal
// realtime dan macet sampai halaman di-refresh. Semuanya polling ke mailbox_state.
//
// Menu Inbox dan Sent membuka halaman ini dengan ?folder=Inbox|Sent (requested_folder).
//
// LOCAL MODE (LocalMailbox, di bawah): kalau Local Mode dicentang di ERPNext Custom Setting >
// Mailbox, semua user memakai mode ini; kalau tidak, akun server (Email Account). Email
// user diambil browser langsung dari Microsoft 365 dan disimpan di folder laptop pilihannya
// (mesinnya public/js/mailbox_local.js); server hanya menyimpan email yang ditautkan. Tampilan
// dan komposer di sini dipakai bersama: LocalMailbox cuma mengganti sumber datanya (fetch_rows,
// fetch_doc, persist_seen, fetch_links, save_links, deliver, ...).
frappe.pages["mailbox"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Mailbox"),
		single_column: true,
	});

	frappe
		.xcall("erpnext_custom.outlook_addin.mailbox_config")
		.catch(() => null)
		.then((cfg) => {
			// client_id kosong = Local Mode mati (outlook_addin.mailbox_config)
			const local = cfg && cfg.client_id && cfg.email ? cfg : null;
			wrapper.mailbox = local ? new LocalMailbox(page, local) : new Mailbox(page);
			wrapper.mailbox.on_show();
		});

	// Folder tinggal di sidebar kiri desk (mount_sidebar). Sidebar menu Mail dirender ulang
	// SESUDAH halaman tampil (event router "change"), jadi dipasang lagi di situ.
	frappe.router.on("change", () => {
		if (frappe.get_route()[0] === "mailbox" && wrapper.mailbox) wrapper.mailbox.mount_sidebar();
	});
	$(wrapper).on("hide", () => wrapper.mailbox && wrapper.mailbox.unmount_sidebar());
};

frappe.pages["mailbox"].on_page_show = function (wrapper) {
	if (wrapper.mailbox) wrapper.mailbox.on_show();
};

const PAGE_LENGTH = 50;
const SNIPPET_LENGTH = 160;
// Tiap berapa lama halaman menanyakan ada surat baru. Tarikan dari server mail sendiri
// jalan tiap menit (scheduler), jadi lebih rapat dari ini tidak menambah apa-apa.
const POLL_MS = 15000;
// Selama tombol Tarik Email menunggu hasilnya.
const PULL_POLL_MS = 2500;
const PULL_GIVE_UP_MS = 3 * 60 * 1000;
// Sent/Spam/Trash ikut terdaftar di frappe.boot.email_accounts sebagai akun semu -- itu
// folder, bukan mailbox, jadi tidak boleh masuk pemilih akun.
const PSEUDO_ACCOUNTS = ["Sent", "Spam", "Trash", "All Accounts"];
// Nilai pemilih akun di Local Mode (bukan nama Email Account).
const LAPTOP = "__laptop__";
// Garis pemisah balasan dari riwayat yang dikutip (<hr>). Gayanya ditulis di elemennya supaya
// ikut terkirim dan tampil sama di Outlook/Gmail penerima.
const DIVIDER_STYLE = "border: 0; border-top: 1px solid #c8cfd6; margin: 12px 0;";
// Baris signature perusahaan di daftar signature (bukan dokumen Mailbox Signature).
const COMPANY_SIGNATURE = "__company__";

// Teks polos satu baris dari HTML: ada-tidaknya ketikan user di editor.
function flat_text(html) {
	return frappe.utils.html2text(html || "").replace(/\s+/g, " ").trim();
}

// Pilihan akun server terakhir per user di browser ini (nama Email Account).

function mode_pref(value) {
	const key = `erp-mailbox-mode|${frappe.session.user}`;
	try {
		if (value === undefined) return localStorage.getItem(key);
		localStorage.setItem(key, value);
	} catch {
		// penyimpanan browser diblokir: pakai bawaan
		return null;
	}
}

// Kotak CC komposer: MultiSelect (saran kontak) di atas textarea, supaya jadi satu blok
// setinggi dua baris dan alamat yang banyak terlihat semua.
class CcControl extends frappe.ui.form.ControlMultiSelect {
	static html_element = "textarea";
}

const FILE_ICONS = [
	[/\.(png|jpe?g|gif|bmp|webp|svg|heic)$/i, "file-image"],
	[/\.(xlsx?|xlsm|csv|ods)$/i, "file-spreadsheet"],
	[/\.(zip|rar|7z|gz|tar)$/i, "file-archive"],
	[/\.(pdf|docx?|odt|rtf|txt|pptx?)$/i, "file-text"],
];

// Lampiran ala Outlook: ikon jenis berkas dan namanya di bawah (dipotong 2 baris, nama lengkap
// di tooltip). `extra` = isi tambahan, mis. tombol hapus di komposer.
function file_tile(f, extra = "") {
	const esc = frappe.utils.escape_html;
	const name = f.file_name || f.name || f.file_url || "";
	const icon = (FILE_ICONS.find(([re]) => re.test(name)) || [null, "file"])[1];
	return `
		<a class="mbx-tile" href="${esc(f.file_url || "#")}" target="_blank" title="${esc(name)}"
			${f.download ? `download="${esc(name)}"` : ""}>
			${frappe.utils.icon(icon, "lg")}
			<span class="mbx-tile-name">${esc(name)}</span>
			${extra}
		</a>`;
}

class Mailbox {
	constructor(page, local_cfg) {
		this.page = page;
		this.local_cfg = local_cfg || null;
		this.accounts = (frappe.boot.email_accounts || []).filter(
			(a) => !PSEUDO_ACCOUNTS.includes(a.email_account)
		);
		const pref = mode_pref();
		this.account = this.is_local
			? LAPTOP
			: this.accounts.some((a) => a.email_account === pref)
			? pref
			: this.accounts.length
			? this.accounts[0].email_account
			: null;
		// Folder IMAP akun (tabel IMAP Folder di Email Account), dimuat di load_folders.
		// Sent/Spam/Trash di bawahnya bukan folder IMAP, melainkan status Communication.
		this.imap_folders = ["INBOX"];
		this.want_folder = this.requested_folder();
		this.folder = this.folder_for(this.want_folder) || "INBOX";
		this.search = "";
		this.dates = null;
		this.start = 0;
		this.mails = [];
		this.current = null;
		this.composer = null;
		this.state = null;
		// Buka otomatis email terbaru hanya saat halaman/folder baru dibuka, dan hanya kalau
		// belum ada permintaan buka yang eksplisit (dari tab Email, notifikasi, atau klik).
		this.want_auto_open = true;

		this.render_shell();
		this.setup_toolbar();
		this.bind();
		this.boot();
	}

	get is_local() {
		return false;
	}

	// Bukan start(): this.start sudah dipakai sebagai posisi halaman daftar.
	boot() {
		if (!this.account) {
			this.show_no_account();
			return;
		}

		this.load_list();
		this.load_folders();
		this.start_polling();
	}

	// Menu Inbox/Sent: ?folder=Inbox|Sent. Diambil sekali lalu dibuang dari alamat dan
	// route_options, supaya kembali ke halaman ini (Back) tidak memaksa folder itu lagi.
	requested_folder() {
		const folder = (frappe.route_options && frappe.route_options.folder) || frappe.utils.get_url_arg("folder");
		if (!folder) return null;
		if (frappe.route_options) delete frappe.route_options.folder;
		const url = new URL(window.location.href);
		url.searchParams.delete("folder");
		window.history.replaceState(null, "", url.pathname + url.search);
		return folder;
	}

	// "Inbox"/"Sent" dari menu -> nama folder di halaman ini.
	folder_for(want) {
		return want === "Sent" ? "Sent" : want ? "INBOX" : null;
	}

	show_requested_folder() {
		const want = this.requested_folder();
		const folder = this.folder_for(want);
		// Local Mode yang belum siap: dipakai saat daftar foldernya datang (ready).
		if (want && !folder) this.want_folder = want;
		if (!folder || folder === this.folder) return;
		this.folder = folder;
		this.render_folders();
		this.switch_folder();
	}

	on_show() {
		this.show_requested_folder();
		// Dari lonceng/toast notifikasi: /desk/mailbox?open=<Communication>
		const open = (frappe.route_options && frappe.route_options.open) || frappe.utils.get_url_arg("open");
		// Dari tab Email di form transaksi: langsung buka komposer Balas/Balas Semua/Teruskan.
		const compose = frappe.route_options && frappe.route_options.compose;
		if (open && this.account) {
			frappe.route_options = null;
			// Buang ?open= dari alamat, kalau tidak surat yang sama terbuka lagi setiap kali
			// halaman ini dikunjungi ulang.
			window.history.replaceState(null, "", window.location.pathname);
			this.open(open, { compose });
		}
	}

	load_folders() {
		return frappe.db.get_doc("Email Account", this.account).then((doc) => {
			const names = (doc.imap_folder || [])
				.filter((row) => !row.cmi_is_sent)
				.map((row) => row.folder_name);
			// INBOX selalu paling atas seperti di Outlook; sisanya urut tabel di akun.
			this.imap_folders = ["INBOX", ...names.filter((name) => name !== "INBOX")];
			this.render_folders();
			this.load_counts();
		});
	}

	render_shell() {
		this.$body = $(`
			<div class="mbx">
				<style>
					.mbx { display: flex; gap: 12px; align-items: stretch;
						height: calc(100vh - 64px); min-height: 420px; }
					.mbx-pane { border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md); background: var(--fg-color);
						overflow: auto; }
					.mbx-list { flex: 0 0 360px; padding: 0; }
					.mbx-reader { flex: 1 1 auto; display: flex; flex-direction: column;
						overflow: hidden; }

					/* folder di sidebar kiri desk (mount_sidebar), gaya item sidebar bawaan */
					.mbx-side .item-anchor { cursor: pointer; }
					.mbx-side .mbx-count { margin-left: auto; padding: 0 7px;
						color: var(--text-muted); font-size: var(--text-sm); }
					.mbx-account { width: 100%; margin-bottom: 8px; }
					.mbx-head-fields { display: flex; gap: 8px; margin-left: 16px; }
					.mbx-head-fields .frappe-control { flex: 0 0 220px; max-width: none;
						padding: 0; margin: 0; }
					.mbx-banner .mbx-warn { margin: 0 0 8px; padding: 8px 10px; }

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
					.mbx-subject { font-size: var(--text-md); margin-top: 2px; display: flex;
						gap: 4px; align-items: center; overflow: hidden; white-space: nowrap; }
					.mbx-subject span { overflow: hidden; text-overflow: ellipsis; }
					.mbx-snippet { color: var(--text-muted); font-size: var(--text-sm);
						margin-top: 2px; overflow: hidden; text-overflow: ellipsis;
						white-space: nowrap; }

					.mbx-head { padding: 12px 16px; border-bottom: 1px solid var(--border-color); }
					.mbx-head h4 { margin: 0 0 6px; font-size: var(--text-xl); }
					.mbx-meta { color: var(--text-muted); font-size: var(--text-sm);
						line-height: 1.6; }
					.mbx-actions { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
					.mbx-chip { font-size: var(--text-sm); padding: 3px 8px;
						border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md); }
					/* lampiran ala Outlook: ikon jenis berkas, nama di bawahnya (maks 2 baris) */
					.mbx-tiles { display: flex; gap: 8px; flex-wrap: wrap; }
					.mbx-tiles:not(:empty) { margin-top: 8px; }
					.mbx-tile { position: relative; width: 92px; padding: 8px 6px 6px;
						display: flex; flex-direction: column; align-items: center; gap: 4px;
						border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
						color: var(--text-color); text-decoration: none; }
					.mbx-tile:hover { background: var(--fg-hover-color, var(--gray-100));
						text-decoration: none; }
					.mbx-tile-name { width: 100%; font-size: var(--text-xs); line-height: 1.3;
						text-align: center; overflow-wrap: anywhere; overflow: hidden;
						display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
					.mbx-tile-remove { position: absolute; top: 2px; right: 2px; cursor: pointer;
						color: var(--text-muted); line-height: 0; }

					/* tautan ke transaksi */
					.mbx-links { margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap;
						align-items: center; font-size: var(--text-sm); }
					.mbx-links-label { color: var(--text-muted); }
					.mbx-chip { display: inline-flex; gap: 6px; align-items: center;
						background: var(--bg-color); }
					.mbx-chip a { border: 0; padding: 0; cursor: pointer; }
					.mbx-chip .mbx-unlink { color: var(--text-muted); display: inline-flex; line-height: 0; }

					/* Latar iframe dipaksa putih: badan email ditulis untuk latar terang,
					   ikut tema gelap desk bikin banyak email jadi hitam-di-hitam. */
					.mbx-body { flex: 1 1 auto; border: 0; width: 100%; background: #fff; }
					.mbx-empty { padding: 40px 16px; text-align: center; color: var(--text-muted); }
					.mbx-empty .btn { margin-top: 12px; }
					.mbx-more, .mbx-older { padding: 10px; text-align: center; }
					/* teguran Local Mode (di .mbx-banner, atas panel): masuk ulang Microsoft, gagal sinkron */
					.mbx-note { margin-top: 12px; padding: 8px 10px; font-size: var(--text-sm);
						color: var(--text-muted); border-top: 1px solid var(--border-color); }
					.mbx-note .btn { margin-top: 6px; }
					.mbx-warn { color: var(--text-color); background: var(--bg-orange, var(--gray-100));
						border-radius: var(--border-radius-md); border-top: 0; }

					/* komposer di panel kanan */
					.mbx-compose { flex: 1 1 auto; overflow: auto; padding: 12px 16px;
						display: flex; flex-direction: column; }
					.mbx-compose hr { margin: 8px 0; }
					.mbx-compose .frappe-control { margin-bottom: 6px; }
					/* Message mengisi sisa tinggi panel (paling sedikit 320px); rantai flex sampai
					   ke kotak editor Quill, isinya bergulir di dalam editor. */
					.mbx-c-message { flex: 1 1 0; min-height: 320px; display: flex; flex-direction: column; }
					.mbx-c-message .frappe-control, .mbx-c-message .form-group,
					.mbx-c-message .control-input-wrapper, .mbx-c-message .control-input {
						flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0;
						margin-bottom: 0; }
					.mbx-c-message .ql-container { flex: 1 1 auto; min-height: 0; }
					.mbx-c-message .ql-editor { min-height: 0; max-height: none; height: 100%; }
					/* di bawah editor: pilihan signature, lalu signature + kutipan apa adanya */
					.mbx-c-tail { flex: 0 0 auto; margin-top: 8px; }
					.mbx-c-sigbar { display: flex; gap: 8px; align-items: center; margin-bottom: 6px;
						font-size: var(--text-sm); }
					.mbx-c-sigbar select { width: auto; }
					/* latar putih seperti panel baca: signature/email ditulis untuk latar terang */
					.mbx-c-tailframe { width: 100%; border: 0; background: #fff; display: block; }
					/* From | To | CC, lalu Subject | CC: CC satu blok setinggi dua baris */
					.mbx-compose-head { display: grid; column-gap: 12px;
						grid-template-columns: 1fr 1.4fr 1.4fr;
						grid-template-areas: "from to cc" "subject subject cc"; }
					.mbx-c-from { grid-area: from; }
					.mbx-c-to { grid-area: to; }
					.mbx-c-subject { grid-area: subject; }
					.mbx-c-cc { grid-area: cc; }
					.mbx-c-cc textarea { height: 98px; resize: none; }
					@media (max-width: 1100px) {
						.mbx-compose-head { grid-template-columns: 1fr;
							grid-template-areas: "from" "to" "cc" "subject"; }
						.mbx-c-cc textarea { height: 56px; }
					}
					/* Lampiran | Transaksi: dua kotak berdampingan, isinya bergulir ke samping */
					.mbx-compose-split { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }
					@media (max-width: 1100px) { .mbx-compose-split { grid-template-columns: 1fr; } }
					.mbx-compose-half { display: flex; align-items: center; gap: 8px; min-width: 0;
						padding: 6px; border: 1px solid var(--border-color);
						border-radius: var(--border-radius-md); }
					.mbx-compose-half > .btn { flex: 0 0 auto; }
					.mbx-scroll-x { flex: 1 1 auto; min-width: 0; display: flex; gap: 6px;
						align-items: center; overflow-x: auto; overflow-y: hidden; padding-bottom: 2px; }
					.mbx-scroll-x > * { flex: 0 0 auto; white-space: nowrap; }
					.mbx-scroll-x:empty::before { content: attr(data-empty); color: var(--text-muted);
						font-size: var(--text-sm); }
					.mbx-compose-group { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
					.mbx-compose-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
					/* modal Tautkan ke Transaksi (dialog di luar .mbx, tapi style ini global) */
					.mbx-pick { display: flex; gap: 8px; align-items: flex-start; padding: 6px 4px;
						border-bottom: 1px solid var(--border-color); margin: 0; cursor: pointer;
						font-weight: normal; }
					.mbx-pick input { margin-top: 3px; }

					/* dialog Settings: tab Local Email | Signature | Rule (juga di luar .mbx) */
					.mbx-set-tabs { margin-bottom: 14px; }
					.mbx-set-tabs .nav-link { cursor: pointer; }
					.mbx-set-title { font-weight: 600; margin: 14px 0 6px; }
					.mbx-set-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
					.mbx-sig { display: flex; gap: 16px; align-items: flex-start; }
					.mbx-sig-list { flex: 0 0 210px; }
					.mbx-sig-item { padding: 8px 10px; margin-top: 4px; cursor: pointer;
						border-radius: var(--border-radius-md); }
					.mbx-sig-item:hover { background: var(--fg-hover-color, var(--gray-100)); }
					.mbx-sig-item.active { background: var(--bg-blue, var(--gray-200)); }
					.mbx-sig-edit { flex: 1 1 auto; min-width: 0; }
					.mbx-sig-edit .ql-editor { min-height: 180px; }
					.mbx-rule { padding: 10px 0; border-bottom: 1px solid var(--border-color); }
					.mbx-rule-on { display: flex; gap: 8px; align-items: center; margin: 0; }
					.mbx-rule-actions { display: flex; gap: 6px; margin-top: 6px; }

					@media (max-width: 1200px) {
						.mbx-list { flex-basis: 300px; }
						.mbx-snippet { display: none; }
					}
				</style>
				<div class="mbx-pane mbx-list"></div>
				<div class="mbx-pane mbx-reader">
					<div class="mbx-empty">${__("Select an email to read")}</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		// Dipindah ke sidebar desk oleh mount_sidebar; handler delegasinya ikut pindah.
		this.$folders = $('<div class="mbx-side"></div>');
		// Teguran (sesi Microsoft habis, gagal sinkron) di atas panel.
		this.$banner = $('<div class="mbx-banner"></div>').insertBefore(this.$body);
		this.$list = this.$body.find(".mbx-list");
		this.$reader = this.$body.find(".mbx-reader");
		this.render_folders();
	}

	setup_toolbar() {
		this.page.set_primary_action(__("New Email"), () => this.compose("new"), "add");
		// Sync menghubungi server mail (Local Mode: Microsoft) lalu memuat ulang daftar.
		this.page.set_secondary_action(__("Sync"), () => this.sync(), "refresh");

		// Cari & tanggal di baris judul, di samping "Mailbox", bukan di baris form bawahnya.
		const $head = $('<div class="mbx-head-fields"></div>').insertAfter(this.page.$title_area);
		this.$search = this.page.add_field({
			fieldtype: "Data",
			fieldname: "mbx_search",
			label: __("Search sender or subject"),
			change: frappe.utils.debounce(() => {
				this.search = (this.$search.get_value() || "").trim();
				this.refresh();
			}, 400),
		}, $head);

		this.$dates = this.page.add_field({
			fieldtype: "DateRange",
			fieldname: "mbx_dates",
			label: __("Date"),
			change: () => {
				const value = this.$dates.get_value();
				const dates = value && value[0] && value[1] ? [value[0], value[1]] : null;
				// Rentang paling panjang 1 bulan: tanggal akhir dipotong ke sana.
				const last = dates && frappe.datetime.add_days(frappe.datetime.add_months(dates[0], 1), -1);
				if (dates && dates[1] > last) {
					dates[1] = last;
					frappe.show_alert({ message: __("Date range is limited to 1 month"), indicator: "orange" });
					this.$dates.set_value(dates);
				}
				if (JSON.stringify(dates) === JSON.stringify(this.dates)) return;
				this.dates = dates;
				this.refresh();
			},
		}, $head);
		// add_field selalu memunculkan baris form, yang kini kosong.
		this.page.hide_form();
	}

	folder_defs() {
		return [
			...this.imap_folders.map((name) => ({
				name,
				label: name === "INBOX" ? __("Inbox") : name,
				icon: name === "INBOX" ? "inbox" : "folder",
			})),
			{ name: "Sent", label: __("Sent"), icon: "send" },
			{ name: "Spam", label: __("Spam"), icon: "shield-alert" },
			{ name: "Trash", label: __("Trash"), icon: "trash-2" },
		];
	}

	render_folders() {
		const esc = frappe.utils.escape_html;
		const accounts = this.is_local
			? [{ value: LAPTOP, label: this.local_cfg.email }]
			: this.accounts.map((a) => ({ value: a.email_account, label: a.email_id }));
		const options = accounts
			.map((a) => `<option value="${esc(a.value)}">${esc(a.label)}</option>`)
			.join("");

		// Pemilih akun hanya kalau memang ada pilihan (Local Mode = satu mailbox).
		this.$folders.html(`
			${accounts.length > 1 ? `<select class="form-control mbx-account">${options}</select>` : ""}
			${this.folder_defs()
				.map((f) =>
					this.side_item(f.label, f.icon || "folder", {
						cls: "mbx-folder",
						attrs: `data-folder="${esc(f.name)}"`,
						active: f.name === this.folder,
						depth: f.depth,
					})
				)
				.join("")}
		`);
		this.$folders.find(".mbx-account").val(this.account);
		this.mount_sidebar();
	}

	// Satu item bermarkup sama dengan item sidebar desk (sidebar_item.html) supaya tampil,
	// menyempit, dan menyala aktif seperti item lain di menu Mail.
	side_item(label, icon, { cls = "", attrs = "", active = false, depth = 0 } = {}) {
		const esc = frappe.utils.escape_html;
		const svg = frappe.utils.icon(icon, "sm", "", "", "text-ink-gray-7 current-color", true);
		return `
			<div class="sidebar-item-container ${cls}" ${attrs} title="${esc(label)}">
				<div class="standard-sidebar-item ${active ? "active-sidebar" : ""}"
					${depth ? `style="padding-left: ${depth * 14}px"` : ""}>
					<a class="item-anchor">
						<span class="sidebar-item-icon text-ink-gray-7">${svg}</span>
						<span class="sidebar-item-label">${esc(label)}</span>
						<span class="mbx-count"></span>
					</a>
				</div>
			</div>`;
	}

	// Folder mailbox menggantikan item menu Mail yang menuju halaman ini (Inbox/Sent) selama
	// halaman ini terbuka; unmount_sidebar mengembalikannya. Dipanggil tiap render_folders
	// dan tiap router "change" (sidebar Mail bisa dirender sesudah halaman tampil).
	mount_sidebar() {
		if (frappe.get_route()[0] !== "mailbox") return; // tarikan latar saat halaman lain terbuka
		const $menu = this.menu_items();
		if (!$menu.length) return;
		if (this.$folders.next()[0] !== $menu[0]) this.$folders.insertBefore($menu.first());
		// Local Mode yang belum masuk Microsoft belum punya folder: menu Inbox/Sent tetap tampil.
		$menu.toggle(!this.$folders.find(".mbx-folder").length);
	}

	unmount_sidebar() {
		this.$folders.detach();
		this.menu_items().show();
	}

	menu_items() {
		return $('.body-sidebar a.item-anchor[href^="/desk/mailbox"]').closest(".sidebar-item-container");
	}

	bind() {
		this.$folders.on("change", ".mbx-account", (e) => {
			const value = $(e.currentTarget).val();
			mode_pref(value);
			this.account = value;
			this.folder = "INBOX";
			this.state = null;
			this.switch_folder();
			this.load_folders();
		});

		this.$folders.on("click", ".mbx-folder", (e) => {
			// attr, bukan .data(): jQuery mengubah nama folder yang mirip angka ("2024")
			// jadi Number, dan filter imap_folder-nya ikut meleset.
			this.folder = $(e.currentTarget).attr("data-folder");
			this.$folders.find(".standard-sidebar-item").removeClass("active-sidebar");
			$(e.currentTarget).children(".standard-sidebar-item").addClass("active-sidebar");
			this.switch_folder();
		});

		this.$list.on("click", ".mbx-item", (e) => this.open($(e.currentTarget).data("name")));
		this.$list.on("click", ".mbx-more button", () => this.load_list(true));
	}

	switch_folder() {
		// Pindah folder = surat terbaru folder itu yang terbuka, seperti panel baca Outlook.
		if (!this.composer) {
			this.current = null;
			this.want_auto_open = true;
		}
		this.refresh();
	}

	refresh() {
		this.start = 0;
		this.mails = [];
		this.load_list();
	}

	// ------------------------------------------------------------ surat baru & Tarik Email

	start_polling() {
		this.poll();
		setInterval(() => {
			if ((frappe.get_route() || [])[0] === "mailbox") this.poll();
		}, POLL_MS);
	}

	poll() {
		if (!this.account) return Promise.resolve();

		return frappe
			.xcall("erpnext_custom.mail_inbox.mailbox_state", { email_account: this.account })
			.then((state) => {
				const changed = this.state && state.latest !== this.state.latest;
				this.state = state;
				if (changed) {
					this.refresh();
					this.load_counts();
				}
				return state;
			});
	}

	sync() {
		// Tombol ini dipasang sebelum pemeriksaan akun di constructor, jadi di halaman
		// tanpa mailbox pun ia ada -- jangan sampai memanggil server dengan akun kosong.
		if (!this.account) {
			frappe.show_alert({ message: __("No mailbox set up for this user yet."), indicator: "orange" });
			return;
		}
		if (this.syncing) return;

		this.syncing = true;
		this.page.btn_secondary.prop("disabled", true);
		const before = this.state ? this.state.total : null;
		const started = Date.now();

		const finish = (state) => {
			clearInterval(timer);
			this.syncing = false;
			this.page.btn_secondary.prop("disabled", false);
			if (!state) return;

			const added = before === null ? 0 : state.total - before;
			frappe.show_alert({
				message: added > 0 ? __("{0} new emails", [added]) : __("No new emails"),
				indicator: added > 0 ? "green" : "gray",
			});
			this.refresh();
			this.load_counts();
		};

		// Penarikan jalan di latar; halaman cukup menanyakan statusnya berkala sampai job
		// tarik untuk akun ini (bawaan atau dari tombol) tidak ada lagi di antrean.
		const timer = setInterval(() => {
			if (Date.now() - started > PULL_GIVE_UP_MS) return finish(null);
			this.poll()
				.then((state) => state && !state.pulling && finish(state))
				.catch(() => finish(null));
		}, PULL_POLL_MS);

		frappe
			.xcall("erpnext_custom.mail_inbox.pull_now", { email_account: this.account })
			.catch(() => finish(null));
	}

	// ------------------------------------------------------------ daftar surat

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
			// Folder IMAP: asal folder dicatat ke imap_folder oleh erpnext_custom.mail_inbox.
			filters.push(["sent_or_received", "=", "Received"]);
			filters.push(["email_account", "=", this.account]);
			filters.push(["imap_folder", "=", this.folder]);
			filters.push(["email_status", "not in", ["Spam", "Trash"]]);
		}

		// "between" pada Datetime dibuka Frappe jadi 00:00:00 s.d. 23:59:59 kedua ujungnya.
		if (this.dates) filters.push(["communication_date", "between", this.dates]);

		return filters;
	}

	get_or_filters() {
		if (!this.search) return null;
		const like = `%${this.search}%`;
		return [
			["subject", "like", like],
			["sender", "like", like],
			["sender_full_name", "like", like],
			["recipients", "like", like],
		];
	}

	load_list(append = false) {
		if (!append) this.start = 0;

		this.fetch_rows().then((rows) => {
			this.mails = append ? this.mails.concat(rows) : rows;
			this.start = this.mails.length;
			this.render_list(rows.length === PAGE_LENGTH);

			// Buka yang terbaru. Tidak ditandai sudah dibaca -- yang dibuka otomatis belum
			// tentu dibaca orangnya.
			if (!append && this.want_auto_open && !this.composer && this.mails.length) {
				this.want_auto_open = false;
				this.open(this.mails[0].name, { auto: true });
			}
		});
	}

	fetch_rows() {
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

		return frappe
			.call({ method: "frappe.client.get_list", args: args })
			.then((r) => r.message || []);
	}

	// Di folder Terkirim yang penting lawan bicaranya, bukan diri sendiri.
	is_sent_folder() {
		return this.folder === "Sent";
	}

	render_list(has_more) {
		if (!this.mails.length) {
			this.$list.html(`<div class="mbx-empty">${__("No emails in this folder")}</div>`);
			return;
		}

		const html = this.mails.map((m) => this.item_html(m)).join("");
		this.$list.html(
			html +
				(has_more
					? `<div class="mbx-more"><button class="btn btn-default btn-sm">${__(
							"Load more"
					  )}</button></div>`
					: "")
		);

		if (this.current) {
			this.$list.find(`[data-name="${this.current.name}"]`).addClass("active");
		}
	}

	item_html(m) {
		const sent = this.is_sent_folder();
		const who = sent ? m.recipients || "" : m.sender_full_name || m.sender || "";
		// Surat kiriman sendiri tidak pernah "belum dibaca", walau Frappe menyimpannya seen=0.
		const unread = !sent && !m.seen;

		return `
			<div class="mbx-item ${unread ? "unread" : ""}" data-name="${frappe.utils.escape_html(m.name)}">
				<div class="mbx-item-top">
					<span class="mbx-from">${frappe.utils.escape_html(who)}</span>
					<span class="mbx-date">${this.format_date(m.communication_date)}</span>
				</div>
				<div class="mbx-subject" ${m.has_attachment ? `title="${__("Has attachments")}"` : ""}>
					${m.has_attachment ? frappe.utils.icon("attachment", "xs") : ""}
					<span>${frappe.utils.escape_html(m.subject || __("(no subject)"))}</span>
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
		const now = frappe.datetime.str_to_obj(frappe.datetime.now_datetime());

		if (d.toDateString() === now.toDateString()) {
			return d.toTimeString().slice(0, 5);
		}
		if (d.getFullYear() === now.getFullYear()) {
			return frappe.datetime.str_to_user(value).slice(0, 5);
		}
		return frappe.datetime.str_to_user(value).split(" ")[0];
	}

	// ------------------------------------------------------------ baca surat

	open(name, opts = {}) {
		if (this.composer && !opts.auto) {
			if (!this.discard_draft(() => this.open(name, opts))) return;
		}

		if (!opts.auto) this.want_auto_open = false;
		this.$list.find(".mbx-item").removeClass("active");
		this.$list.find(`[data-name="${name}"]`).addClass("active");
		this.$reader.html(`<div class="mbx-empty">${__("Loading...")}</div>`);

		// Hanya hasil buka TERAKHIR yang dipakai: klik cepat berpindah-pindah atau buka
		// otomatis yang datang belakangan tidak boleh menimpa email yang dipilih.
		const seq = (this.open_seq = (this.open_seq || 0) + 1);
		this.fetch_doc(name)
			.then((doc) => {
				if (seq !== this.open_seq) return;
				this.current = doc;
				this.render_reader(doc);
				if (!opts.auto) this.mark_seen(doc);
				if (opts.compose) this.compose(opts.compose);
			})
			.catch((e) => {
				if (seq !== this.open_seq) return;
				const why = e instanceof Error ? e.message : "";
				this.$reader.html(
					`<div class="mbx-empty">${__("This email could not be opened.")}<br>${frappe.utils.escape_html(why)}</div>`
				);
			});
	}

	fetch_doc(name) {
		return frappe.db.get_doc("Communication", name);
	}

	mark_seen(doc) {
		if (doc.seen || doc.sent_or_received === "Sent") return;

		this.persist_seen(doc).then(() => {
			doc.seen = 1;
			const row = this.mails.find((m) => m.name === doc.name);
			if (row) row.seen = 1;
			this.$list.find(`[data-name="${doc.name}"]`).removeClass("unread");
			this.load_counts();
		});
	}

	persist_seen(doc) {
		return frappe.db.set_value("Communication", doc.name, "seen", 1);
	}

	render_reader(doc) {
		this.$reader.html(`
			<div class="mbx-head">
				<h4>${frappe.utils.escape_html(doc.subject || __("(no subject)"))}</h4>
				<div class="mbx-meta">
					<div><b>${frappe.utils.escape_html(doc.sender_full_name || doc.sender || "")}</b>
						${doc.sender ? "&lt;" + frappe.utils.escape_html(doc.sender) + "&gt;" : ""}</div>
					<div>${__("To")}: ${frappe.utils.escape_html(doc.recipients || "")}</div>
					${doc.cc ? `<div>Cc: ${frappe.utils.escape_html(doc.cc)}</div>` : ""}
					<div>${frappe.datetime.str_to_user(doc.communication_date)}</div>
				</div>
				<div class="mbx-attachments mbx-tiles"></div>
				<div class="mbx-links hidden">
					<span class="mbx-links-label">${__("Transactions")}:</span>
					<span class="mbx-link-chips mbx-compose-group"></span>
				</div>
				<div class="mbx-actions">
					<button class="btn btn-default btn-sm" data-act="reply">${__("Reply")}</button>
					<button class="btn btn-default btn-sm" data-act="reply-all">${__("Reply All")}</button>
					<button class="btn btn-default btn-sm" data-act="forward">${__("Forward")}</button>
					${
						// Local Mode: email tidak ada di ERP sebagai dokumen; salinan di laptop
						// terenkripsi, jadi .eml polosnya diambil lewat tombol ini.
						this.is_local
							? `<button class="btn btn-default btn-sm" data-act="download">${__("Download .eml")}</button>`
							: `<button class="btn btn-default btn-sm" data-act="doc">${__("Open Document")}</button>`
					}
					<button class="btn btn-default btn-sm mbx-link-btn">${__("Link to")}</button>
				</div>
			</div>
			<iframe class="mbx-body" sandbox="allow-popups allow-popups-to-escape-sandbox"></iframe>
		`);

		this.$reader.find("[data-act]").on("click", (e) => {
			const act = $(e.currentTarget).data("act");
			if (act === "doc") frappe.set_route("Form", "Communication", doc.name);
			else if (act === "download") this.download_eml(doc);
			else this.compose(act);
		});

		this.render_body(doc);
		this.load_attachments(doc).then((files) => this.render_attachments(files));
		this.setup_links(doc);
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
		if (!doc.has_attachment) return Promise.resolve([]);

		return frappe.db.get_list("File", {
			filters: { attached_to_doctype: "Communication", attached_to_name: doc.name },
			fields: ["name", "file_name", "file_url"],
			limit: 50,
		});
	}

	render_attachments(files) {
		this.$reader.find(".mbx-attachments").html((files || []).map((f) => file_tile(f)).join(""));
	}

	// ------------------------------------------------------------ tautan ke transaksi

	setup_links(doc) {
		const $row = this.$reader.find(".mbx-links");
		let current = [];

		const render = (links) => {
			current = links || [];
			// Baris "Transaksi:" cuma tampil kalau memang ada tautannya.
			$row.toggleClass("hidden", !current.length);
			$row.find(".mbx-link-chips").html(
				(links || [])
					.map(
						(l) => `
					<span class="mbx-chip" data-doctype="${frappe.utils.escape_html(l.doctype)}"
						data-name="${frappe.utils.escape_html(l.name)}">
						<a class="mbx-open-link">${frappe.utils.escape_html(__(l.doctype))} ${frappe.utils.escape_html(l.name)}</a>
						<a class="mbx-unlink" title="${__("Remove")}">${frappe.utils.icon("x", "xs")}</a>
					</span>`
					)
					.join("")
			);
		};

		const load = () => this.fetch_links(doc).then(render);
		load();

		this.$reader.find(".mbx-link-btn").on("click", () => {
			this.pick_transactions(current, (picked) => {
				this.save_links(doc, current, picked)
					.then((saved) => {
						if (!saved) return;
						frappe.show_alert({ message: __("Transaction links saved"), indicator: "green" });
						load();
					})
					.catch((e) => {
						this.show_error(e);
						load();
					});
			});
		});

		$row.on("click", ".mbx-open-link", (e) => {
			const $chip = $(e.currentTarget).closest(".mbx-chip");
			frappe.set_route("Form", $chip.attr("data-doctype"), $chip.attr("data-name"));
		});
		$row.on("click", ".mbx-unlink", (e) => {
			const $chip = $(e.currentTarget).closest(".mbx-chip");
			const drop = `${$chip.attr("data-doctype")}::${$chip.attr("data-name")}`;
			const rest = current.filter((l) => `${l.doctype}::${l.name}` !== drop);
			this.save_links(doc, current, rest).then(load, (err) => {
				this.show_error(err);
				load();
			});
		});
	}

	fetch_links(doc) {
		return frappe.xcall("erpnext_custom.mail_inbox.get_links", { communication: doc.name });
	}

	// Jadikan tautan email ini persis `picked`. Hasilnya false kalau tidak ada yang berubah.
	save_links(doc, current, picked) {
		// Yang dikirim ke server cuma selisihnya: yang baru ditautkan, yang dibuang
		// dilepas. Berurutan, karena tiap langkah menyimpan ulang Communication yang
		// sama dan dua simpan serentak ditolak Frappe (TimestampMismatchError).
		const key = (l) => `${l.doctype}::${l.name}`;
		const before = new Set(current.map(key));
		const after = new Set(picked.map(key));
		const call = (method, l) => () =>
			frappe.xcall(`erpnext_custom.mail_inbox.${method}`, {
				communication: doc.name,
				doctype: l.doctype,
				name: l.name,
			});
		const steps = [
			...picked.filter((l) => !before.has(key(l))).map((l) => call("link_transaction", l)),
			...current.filter((l) => !after.has(key(l))).map((l) => call("unlink_transaction", l)),
		];
		if (!steps.length) return Promise.resolve(false);

		return steps.reduce((chain, step) => chain.then(step), Promise.resolve()).then(() => true);
	}

	// Galat dari browser (mode laptop: Microsoft, folder laptop) belum tampil sendiri; galat
	// server sudah ditampilkan frappe.call, jadi tidak dimunculkan dua kali.
	show_error(e) {
		if (e instanceof Error) frappe.msgprint({ title: __("Mailbox"), message: frappe.utils.escape_html(e.message), indicator: "red" });
	}

	// ------------------------------------------------------------ tulis / balas / teruskan

	// Pengganti CommunicationComposer (modal) -- ditulis langsung di panel kanan.
	// mode: new | reply | reply-all | forward
	compose(mode) {
		if (this.composer && !this.discard_draft(() => this.compose(mode))) return;

		const doc = mode === "new" ? null : this.current;
		const clean = ((doc && doc.subject) || "").replace(/^((re|fwd|fw):\s*)+/i, "");
		const draft = {
			mode,
			reply_to: doc && mode !== "forward" ? doc.name : null,
			// email asli yang dibalas/diteruskan (mode laptop: createReply/createForward Microsoft)
			source: doc ? doc.name : null,
			// diisi dari transaksi email aslinya begitu get_links menjawab (di bawah)
			links: [],
			files: [],
		};

		this.$reader.html(`
			<div class="mbx-compose">
				<div class="mbx-compose-head">
					<div class="mbx-c-from"></div>
					<div class="mbx-c-to"></div>
					<div class="mbx-c-cc"></div>
					<div class="mbx-c-subject"></div>
				</div>
				<div class="mbx-compose-split">
					<div class="mbx-compose-half">
						<button class="btn btn-default btn-sm icon-btn mbx-c-add" title="${__("Attach files")}">
							${frappe.utils.icon("paperclip", "sm")}</button>
						<input type="file" multiple class="hidden mbx-c-input">
						<div class="mbx-c-files mbx-scroll-x" data-empty="${__("No attachments")}"></div>
					</div>
					<div class="mbx-compose-half">
						<button class="btn btn-default btn-sm icon-btn mbx-c-link-btn" title="${__("Link to transaction")}">
							${frappe.utils.icon("link", "sm")}</button>
						<div class="mbx-c-links mbx-scroll-x" data-empty="${__("No linked transactions")}"></div>
					</div>
				</div>
				<hr>
				<div class="mbx-c-message"></div>
				<div class="mbx-c-tail"></div>
				<div class="mbx-compose-foot">
					<button class="btn btn-default btn-sm mbx-c-cancel">${__("Cancel")}</button>
					<button class="btn btn-primary btn-sm mbx-c-send">${__("Send")}</button>
				</div>
			</div>
		`);

		const $c = this.$reader.find(".mbx-compose");
		const control = (selector, df) =>
			frappe.ui.form.make_control({ parent: $c.find(selector), df, render_input: true });

		const c = {
			from: control(".mbx-c-from", { fieldtype: "Select", fieldname: "sender", label: __("From"), reqd: 1 }),
			to: control(".mbx-c-to", { fieldtype: "MultiSelect", fieldname: "recipients", label: __("To"), reqd: 1 }),
			cc: new CcControl({
				parent: $c.find(".mbx-c-cc"),
				df: { fieldtype: "MultiSelect", fieldname: "cc", label: __("CC") },
				render_input: true,
			}),
			subject: control(".mbx-c-subject", { fieldtype: "Data", fieldname: "subject", label: __("Subject"), reqd: 1 }),
			message: control(".mbx-c-message", { fieldtype: "Text Editor", fieldname: "content", label: __("Message") }),
		};
		this.composer = { draft, c };

		// Isian penerima: pola yang sama dengan CommunicationComposer bawaan -- kontak
		// dicari dari potongan terakhir setelah koma.
		for (const field of [c.to, c.cc]) {
			field.get_data = () => {
				const txt = ((field.get_value() || "").match(/[^,\s*]*$/) || [""])[0];
				frappe.xcall("frappe.email.get_contact_list", { txt }).then((r) => field.set_data(r));
			};
		}

		this.load_senders(c.from);

		if (doc) {
			const reply_all = mode === "reply-all";
			if (mode !== "forward") {
				// Membalas surat yang KITA kirim = melanjutkan ke penerima yang sama.
				const mine = doc.sent_or_received === "Sent";
				c.to.set_value(mine ? doc.recipients || "" : doc.sender || "");
				if (reply_all) c.cc.set_value(this.reply_all_cc(doc));
			}
			c.subject.set_value((mode === "forward" ? "Fwd: " : "Re: ") + clean);
		}

		// Seperti Outlook: ruang ketik di editor, di bawahnya signature bawaan (satu untuk email
		// baru, satu untuk balasan/terusan) lalu garis pemisah + kutipan. Signature & kutipan
		// DI LUAR editor (render_tail), disambung saat Kirim (final_body).
		draft.quote = doc ? this.quote(doc) : "";
		draft.signature = "";
		if (doc) {
			// Balasan: kursor langsung berkedip di baris pertama. Ditunggu sampai isinya
			// terpasang, kalau tidak posisi kursornya tertimpa.
			c.message.set_value("<p><br></p><p><br></p>").then(() => {
				if (mode !== "forward") setTimeout(() => this.focus_message(c.message), 0);
			});
		}
		this.render_tail();
		this.load_signatures().then((signatures) => {
			if (!this.composer || this.composer.draft !== draft) return;
			const sig = signatures.find((s) => (doc ? s.use_for_reply : s.use_for_new));
			draft.signatures = signatures;
			draft.signature_id = sig ? sig.name : "";
			draft.signature = sig ? sig.content || "" : "";
			this.render_tail();
		});

		// Balasan/terusan tertaut ke SEMUA transaksi email aslinya -- reference utama maupun
		// timeline link (reference utama sering berisi "Communication <induk>", bukan transaksi).
		if (doc) {
			this.fetch_links(doc).then((links) => {
				if (this.composer && this.composer.draft === draft) {
					draft.links = links || [];
					this.render_draft_links();
				}
			});
		}

		if (doc && mode === "forward") {
			this.load_attachments(doc).then((files) => {
				draft.files = (files || []).map((f) => ({ ...f }));
				this.render_draft_files();
			});
		}

		this.render_draft_files();
		this.render_draft_links();

		// Kotak lampiran/transaksi bergulir ke samping; roda mouse biasa ikut menggulirnya.
		$c.on("wheel", ".mbx-scroll-x", (e) => {
			const el = e.currentTarget;
			const dy = e.originalEvent.deltaY;
			if (!dy || el.scrollWidth <= el.clientWidth) return;
			el.scrollLeft += dy;
			e.preventDefault();
		});
		$c.find(".mbx-c-add").on("click", () => $c.find(".mbx-c-input").trigger("click"));
		$c.find(".mbx-c-input").on("change", (e) => this.add_files(e.target.files));
		$c.on("click", ".mbx-c-remove-file", (e) => {
			e.preventDefault(); // di dalam tautan berkas: jangan ikut membuka berkasnya
			draft.files.splice(cint($(e.currentTarget).attr("data-idx")), 1);
			this.render_draft_files();
		});
		$c.find(".mbx-c-link-btn").on("click", () =>
			this.pick_transactions(draft.links, (picked) => {
				draft.links = picked;
				this.render_draft_links();
			})
		);
		$c.on("click", ".mbx-c-unlink", (e) => {
			draft.links.splice(cint($(e.currentTarget).attr("data-idx")), 1);
			this.render_draft_links();
		});

		$c.find(".mbx-c-send").on("click", () => this.send());
		$c.find(".mbx-c-cancel").on("click", () => this.close_composer());

		// Surat baru/teruskan: yang diisi pertama penerimanya. Balasan: pesannya (di atas).
		if ((mode === "new" || mode === "forward") && c.to.$input) c.to.$input.focus();
	}

	focus_message(control) {
		const quill = control.quill;
		if (!quill || !this.composer) return;
		quill.focus();
		quill.setSelection(0, 0);
	}

	// Signature perusahaan (template admin diisi data User ini) + signature milik user sendiri
	// (Mailbox Signature), dimuat sekali per halaman. Tab Signature di Settings mengosongkan
	// this.signatures sesudah menyimpan.
	load_signatures() {
		if (!this.signatures) {
			this.signatures = Promise.all([
				frappe.db
					.get_list("Mailbox Signature", {
						// System Manager bisa membaca semua signature: tetap dibatasi ke miliknya
						filters: { owner: frappe.session.user },
						fields: ["name", "signature_name", "content", "use_for_new", "use_for_reply"],
						order_by: "creation asc",
						limit: 50,
					})
					.catch(() => []),
				frappe
					.xcall("erpnext_custom.erpnext_custom.doctype.mailbox_signature.mailbox_signature.company_signature")
					.catch(() => ""),
			]).then(([own, company]) => {
				if (!company) return own;
				// Signature perusahaan jadi bawaan selama user belum menandai miliknya sendiri.
				const row = {
					name: COMPANY_SIGNATURE,
					signature_name: __("Company Signature"),
					content: company,
					company: 1,
					use_for_new: own.some((s) => s.use_for_new) ? 0 : 1,
					use_for_reply: own.some((s) => s.use_for_reply) ? 0 : 1,
				};
				return [row, ...own];
			});
		}
		return this.signatures;
	}

	// Signature + kutipan di bawah editor, apa adanya. Di luar editor Quill karena Quill membuang
	// tabel, ukuran huruf, dan garis: signature perusahaan dan email lama jadi berantakan.
	// Kutipan = HTML orang luar, jadi dirender di iframe sandbox TANPA skrip; allow-same-origin
	// cuma supaya tingginya bisa diukur dan iframe memanjang mengikuti isinya.
	render_tail() {
		if (!this.composer) return;
		const { draft } = this.composer;
		const esc = frappe.utils.escape_html;
		const signatures = draft.signatures || [];
		const $tail = this.$reader.find(".mbx-c-tail");
		$tail.html(`
			<div class="mbx-c-sigbar ${signatures.length ? "" : "hidden"}">
				<span class="text-muted">${__("Signature")}</span>
				<select class="form-control input-xs mbx-c-sig">
					<option value="">${__("No signature")}</option>
					${signatures
						.map(
							(s) =>
								`<option value="${esc(s.name)}" ${s.name === draft.signature_id ? "selected" : ""}>${esc(
									s.signature_name
								)}</option>`
						)
						.join("")}
				</select>
			</div>
			<iframe class="mbx-c-tailframe" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>
		`);

		const body = draft.signature + draft.quote;
		const frame = $tail.find("iframe")[0];
		frame.classList.toggle("hidden", !body);
		frame.srcdoc = `<!doctype html>
			<html><head><meta charset="utf-8"><base target="_blank">
			<style>
				body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					font-size: 13px; color: #1f272e; margin: 0; word-wrap: break-word; }
				img { max-width: 100%; }
				blockquote { border-left: 2px solid #d1d8dd; margin: 0; padding-left: 12px; color: #6b7580; }
			</style></head>
			<body>${body}</body></html>`;
		const fit = () => {
			const doc = frame.contentDocument;
			if (doc && doc.documentElement) frame.style.height = `${doc.documentElement.scrollHeight}px`;
		};
		frame.onload = () => {
			fit();
			// gambar signature/kutipan menambah tinggi sesudah termuat
			for (const img of frame.contentDocument.images) img.addEventListener("load", fit);
		};

		$tail.find(".mbx-c-sig").on("change", (e) => {
			const s = signatures.find((x) => x.name === e.target.value);
			draft.signature_id = s ? s.name : "";
			draft.signature = s ? s.content || "" : "";
			this.render_tail();
		});
	}

	// Isi email yang dikirim: ketikan user + signature + garis pemisah & kutipan.
	final_body() {
		const { c, draft } = this.composer;
		const typed = c.message.get_value() || "";
		return typed + (draft.signature ? `<div><br></div>${draft.signature}` : "") + draft.quote;
	}

	load_senders(control) {
		frappe.db
			.get_list("Email Account", {
				filters: { enable_outgoing: 1 },
				fields: ["name", "email_id", "default_outgoing"],
				limit: 50,
			})
			.then((rows) => {
				const ids = rows.map((r) => r.email_id).filter(Boolean);
				control.df.options = ids.join("\n");
				control.refresh();
				// Utamakan alamat mailbox yang sedang dibuka, lalu akun default keluar.
				const mine = rows.find((r) => r.name === this.account);
				const fallback = rows.find((r) => r.default_outgoing) || rows[0];
				control.set_value((mine || fallback || {}).email_id || "");
			});
	}

	own_address() {
		return (this.accounts.find((a) => a.email_account === this.account) || {}).email_id;
	}

	reply_all_cc(doc) {
		// Alamat email tidak peka huruf besar: "Budi@..." di header tetap diri sendiri.
		const skip = [this.own_address(), doc.sender].map((s) => (s || "").toLowerCase());
		const parts = `${doc.recipients || ""},${doc.cc || ""}`
			.split(",")
			.map((s) => s.trim())
			.filter((s) => s && !skip.includes(s.toLowerCase()));
		return [...new Set(parts)].join(", ");
	}

	quote(doc) {
		const when = frappe.datetime.str_to_user(doc.communication_date);
		const who = frappe.utils.escape_html(doc.sender_full_name || doc.sender || "");
		// Garis pemisah lalu riwayatnya. Tampil di bawah editor (render_tail), tidak lewat Quill,
		// jadi format email aslinya utuh.
		return `<hr style="${DIVIDER_STYLE}">
			<p>${__("On {0}, {1} wrote:", [when, who])}</p>
			<blockquote>${doc.content || frappe.utils.escape_html(doc.text_content || "")}</blockquote>`;
	}

	// Lampiran langsung tampil begitu ada -- tidak ada tombol Tampilkan.
	render_draft_files() {
		if (!this.composer) return;
		const { draft } = this.composer;
		this.$reader.find(".mbx-c-files").html(
			draft.files
				.map((f, i) =>
					file_tile(
						f,
						// span, bukan <a>: tautan di dalam tautan dipecah browser
						`<span class="mbx-c-remove-file mbx-tile-remove" role="button" data-idx="${i}"
							title="${__("Remove")}">${frappe.utils.icon("x", "xs")}</span>`
					)
				)
				.join("")
		);
	}

	render_draft_links() {
		if (!this.composer) return;
		const { draft } = this.composer;
		this.$reader.find(".mbx-c-links").html(
			draft.links
				.map(
					(l, i) => `
				<span class="mbx-chip">${frappe.utils.escape_html(__(l.doctype))}
					${frappe.utils.escape_html(l.name)}
					<a class="mbx-c-unlink mbx-unlink" data-idx="${i}" title="${__("Remove")}">${frappe.utils.icon("x", "xs")}</a></span>`
				)
				.join("")
		);
	}

	// Modal pilih nomor transaksi -- bisa lebih dari satu. Dipakai panel baca (langsung
	// disimpan ke email) dan komposer (dipakai saat Kirim). Pencariannya quick_search, tanpa
	// ledger/log/pengaturan. `on_save` baru dipanggil saat Simpan; menutup modal membiarkan
	// pilihan lama.
	pick_transactions(initial, on_save) {
		const esc = frappe.utils.escape_html;
		const key = (l) => `${l.doctype}::${l.name}`;
		const picked = (initial || []).map((l) => ({ doctype: l.doctype, name: l.name }));
		// Sebelum mengetik: Packing List terbaru (latest_transactions), supaya modal tidak
		// kosong. Begitu mengetik, hasil pencarian menggantikannya.
		let sample = [];
		let found = [];
		let searched = false;

		const dialog = new frappe.ui.Dialog({
			title: __("Link to Transaction"),
			fields: [
				{
					fieldtype: "Data",
					fieldname: "txt",
					label: __("Search transaction number"),
					description: __("Showing the latest Packing Lists. Type at least 3 characters to search transactions in every module."),
				},
				{ fieldtype: "HTML", fieldname: "results" },
				{ fieldtype: "Section Break", label: __("Selected") },
				{ fieldtype: "HTML", fieldname: "picked" },
			],
			primary_action_label: __("Save"),
			primary_action: () => {
				dialog.hide();
				on_save(picked);
			},
		});

		const render = () => {
			const on = new Set(picked.map(key));
			const rows = searched ? found : sample;
			dialog.fields_dict.results.$wrapper.html(
				rows.length
					? rows
							.map(
								(h) => `
						<label class="mbx-pick">
							<input type="checkbox" data-key="${esc(key(h))}" ${on.has(key(h)) ? "checked" : ""}>
							<span><strong>${esc(h.name)}</strong>
								<span class="text-muted">${esc(__(h.doctype))}</span>
								${h.description ? `<br><small class="text-muted">${esc(h.description)}</small>` : ""}
							</span>
						</label>`
							)
							.join("")
					: `<div class="text-muted">${
							searched ? __("No matching transactions.") : __("Loading latest Packing Lists...")
					  }</div>`
			);
			dialog.fields_dict.picked.$wrapper.html(
				picked.length
					? `<div class="mbx-compose-group">${picked
							.map(
								(l) => `
						<span class="mbx-chip">${esc(__(l.doctype))} ${esc(l.name)}
							<a class="mbx-unlink mbx-pick-remove" data-key="${esc(key(l))}" title="${__("Remove")}">${frappe.utils.icon("x", "xs")}</a></span>`
							)
							.join("")}</div>`
					: `<div class="text-muted">${__("No transactions selected.")}</div>`
			);
		};

		dialog.fields_dict.txt.$input.on(
			"input",
			frappe.utils.debounce(() => {
				const txt = (dialog.fields_dict.txt.$input.val() || "").trim();
				if (txt.length < 3) {
					found = [];
					searched = false;
					return render();
				}
				// find_transactions, bukan find_documents (Ctrl+K): ledger, log dan pengaturan
				// tidak ikut dicari -- itu bukan transaksi yang ditautkan ke email.
				frappe
					.xcall("erpnext_custom.quick_search.find_transactions", { txt, limit: 20 })
					.then((rows) => {
						found = rows || [];
						searched = true;
						render();
					});
			}, 300)
		);

		dialog.$wrapper.on("change", ".mbx-pick input", (e) => {
			const k = e.currentTarget.getAttribute("data-key");
			const at = picked.findIndex((l) => key(l) === k);
			const hit = (searched ? found : sample).find((h) => key(h) === k);
			if (e.currentTarget.checked && at < 0 && hit) picked.push({ doctype: hit.doctype, name: hit.name });
			if (!e.currentTarget.checked && at >= 0) picked.splice(at, 1);
			render();
		});
		dialog.$wrapper.on("click", ".mbx-pick-remove", (e) => {
			const at = picked.findIndex((l) => key(l) === e.currentTarget.getAttribute("data-key"));
			if (at >= 0) picked.splice(at, 1);
			render();
		});

		render();
		dialog.show();
		setTimeout(() => dialog.fields_dict.txt.$input.focus(), 200);

		frappe.xcall("erpnext_custom.quick_search.latest_transactions", { limit: 5 }).then((rows) => {
			sample = rows || [];
			if (!searched) render();
		});
	}

	add_files(files) {
		if (!this.composer || !files || !files.length) return;
		const { draft } = this.composer;

		for (const file of Array.from(files)) {
			const form = new FormData();
			form.append("file", file, file.name);
			form.append("is_private", 1);
			form.append("folder", "Home/Attachments");

			frappe.show_alert({ message: __("Uploading {0}...", [file.name]), indicator: "blue" });
			fetch("/api/method/upload_file", {
				method: "POST",
				body: form,
				headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
			})
				.then((r) => r.json())
				.then((r) => {
					if (!r.message) throw new Error(r.exc || "upload failed");
					draft.files.push({ name: r.message.name, file_name: r.message.file_name, file_url: r.message.file_url });
					this.render_draft_files();
				})
				.catch(() => frappe.msgprint(__("Failed to upload {0}", [file.name])));
		}

		this.$reader.find(".mbx-c-input").val("");
	}

	send() {
		const { draft, c } = this.composer;
		const sender = c.from.get_value();
		const recipients = (c.to.get_value() || "").trim().replace(/,\s*$/, "");
		const subject = (c.subject.get_value() || "").trim();

		const missing = [
			!sender && __("From"),
			!recipients && __("To"),
			!subject && __("Subject"),
		].filter(Boolean);
		if (missing.length) {
			frappe.msgprint(__("Required: {0}", [missing.join(", ")]));
			return;
		}

		const $send = this.$reader.find(".mbx-c-send").prop("disabled", true);

		this.deliver({
			draft,
			sender,
			recipients,
			cc: (c.cc.get_value() || "").trim().replace(/,\s*$/, ""),
			subject,
			content: this.final_body(),
		})
			.then(() => {
				frappe.show_alert({ message: __("Email sent"), indicator: "green" });
				this.close_composer(true);
				if (this.is_sent_folder()) this.refresh();
			})
			.catch((e) => {
				this.show_error(e);
				$send.prop("disabled", false);
			});
	}

	deliver({ draft, sender, recipients, cc, subject, content }) {
		// make() cuma menerima SATU dokumen referensi; transaksi pertama jadi referensinya,
		// sisanya ditautkan sesudah email tercatat.
		const [first, ...rest] = draft.links;

		return (
			frappe
				.xcall("frappe.core.doctype.communication.email.make", {
					doctype: first ? first.doctype : null,
					name: first ? first.name : null,
					sender,
					recipients,
					cc,
					subject,
					content,
					send_email: 1,
					attachments: draft.files.map((f) => f.name),
					in_reply_to: draft.reply_to,
				})
				// Berurutan, bukan Promise.all: tiap tautan menyimpan ulang Communication yang sama,
				// dan dua simpan serentak ditolak Frappe (TimestampMismatchError).
				.then((r) =>
					rest.reduce(
						(chain, l) =>
							chain.then(() =>
								frappe.xcall("erpnext_custom.mail_inbox.link_transaction", {
									communication: r.name,
									doctype: l.doctype,
									name: l.name,
								})
							),
						Promise.resolve()
					)
				)
		);
	}

	has_draft_text() {
		if (!this.composer) return false;
		const { c, draft } = this.composer;
		// Signature dan kutipan ada di luar editor: isi editor = ketikan user saja.
		return Boolean(flat_text(c.message.get_value()) || draft.files.length);
	}

	discard_draft(then) {
		if (!this.has_draft_text()) {
			this.composer = null;
			return true;
		}
		frappe.confirm(__("Discard this draft?"), () => {
			this.composer = null;
			then();
		});
		return false;
	}

	close_composer(sent = false) {
		this.composer = null;
		if (this.current) this.render_reader(this.current);
		else this.$reader.html(`<div class="mbx-empty">${__(sent ? "Email sent" : "Select an email to read")}</div>`);
	}

	// ------------------------------------------------------------ hitungan folder

	load_counts() {
		if (!this.account) return;

		for (const name of this.imap_folders) {
			frappe.db
				.count("Communication", {
					filters: {
						communication_type: "Communication",
						communication_medium: "Email",
						sent_or_received: "Received",
						email_account: this.account,
						imap_folder: name,
						seen: 0,
					},
				})
				.then((count) => this.folder_el(name).find(".mbx-count").text(count || ""));
		}
	}

	// Dicari lewat perbandingan atribut, bukan selector [data-folder="..."]: nama folder
	// bebas diisi pemilik mailbox dan bisa memuat kutip atau spasi.
	folder_el(name) {
		return this.$folders
			.find(".mbx-folder")
			.filter((_i, el) => el.getAttribute("data-folder") === name);
	}

	show_no_account() {
		this.$body.find(".mbx-list, .mbx-reader").html(`
			<div class="mbx-empty">
				${__("No mailbox set up for this user yet.")}<br>
				${__("Add an incoming Email Account, then register it in the Email tab of the User.")}
			</div>
		`);
	}
}

// ================================================================ mode laptop

// Mesinnya (Microsoft Graph, folder laptop, indeks IndexedDB, sinkron otomatis) ada di
// public/js/mailbox_local.js, dimuat di semua halaman desk lewat hooks app_include_js.

// Email user diambil langsung dari Microsoft 365 dan disimpan di folder laptop pilihannya.
// Tampilan, daftar, panel baca, komposer, dan modal tautan tetap milik Mailbox di atas; kelas
// ini cuma mengganti sumber datanya.
class LocalMailbox extends Mailbox {
	get is_local() {
		return true;
	}

	bind() {
		super.bind();
		this.$folders.on("click", ".mbx-settings", () => this.settings());
		this.$list.on("click", ".mbx-older button", () => this.load_older());
		this.$banner.on("click", ".mbx-relogin", () =>
			this.engine.login().then(
				() => this.poll().catch(() => {}),
				(e) => this.show_auth_error(e)
			)
		);
	}

	async boot() {
		this.imap_folders = [];
		this.folder = null;
		this.$list.html(`<div class="mbx-empty">${__("Preparing mailbox...")}</div>`);
		try {
			// Mesin yang sama dengan sinkron otomatis di halaman desk lain (satu per tab).
			this.engine = await LocalMail.shared();
			if (!this.engine) throw new Error(__("Local Mode is turned off in ERPNext Custom Setting."));
			this.engine.on_change = () => this.refresh_soon();
			this.engine.on_status = (e) => this.show_status(e);
		} catch (e) {
			this.$list.html(
				`<div class="mbx-empty">${__("Local mailbox could not be prepared.")}<br>${frappe.utils.escape_html(
					e.message
				)}</div>`
			);
			return;
		}
		this.connect();
	}

	// Dua langkah yang wajib lewat klik user (aturan browser): izin folder laptop, lalu login
	// Microsoft. Keduanya diingat, jadi biasanya cukup sekali.
	connect() {
		const engine = this.engine;
		if (!engine.home) {
			const first = !engine.root_known;
			return this.ask(
				first
					? __(
							"Your email is stored on this laptop, in a folder you choose. Pick or create a folder on drive D or E, for example D:\\Email."
					  )
					: __(
							"The browser needs permission again to open your email folder ({0}). Choose allow on every visit so it stops asking.",
							[engine.root_name || ""]
					  ),
				first ? __("Choose Folder") : __("Open Email Folder"),
				() => engine.open_root(true)
			);
		}
		if (!engine.account) {
			return this.ask(
				__("Sign in with the Microsoft account {0} to fetch email.", [engine.mailbox]),
				__("Sign in to Microsoft"),
				() => engine.login()
			);
		}
		this.ready();
	}

	ask(message, label, action) {
		const esc = frappe.utils.escape_html;
		this.$list.html(
			`<div class="mbx-empty">${esc(message)}<br><button class="btn btn-primary btn-sm">${esc(label)}</button></div>`
		);
		this.$list.find("button").on("click", () =>
			action().then(
				() => this.connect(),
				(e) => this.show_auth_error(e)
			)
		);
	}

	// Batal di dialog pilih folder / popup login bukan galat.
	show_auth_error(e) {
		if (!e || e.name === "AbortError" || e.errorCode === "user_cancelled") return;
		this.show_error(e instanceof Error ? e : new Error(String(e)));
	}

	async ready() {
		try {
			await this.engine.ensure_folders();
		} catch (e) {
			// Folder belum pernah dipilih dan Microsoft belum bisa dihubungi (sesi habis).
			if (e.need === "login") {
				this.engine.account = null;
				return this.connect();
			}
			this.$list.html(`<div class="mbx-empty">${frappe.utils.escape_html(e.message)}</div>`);
			return;
		}

		this.imap_folders = this.engine.folders;
		if (!this.imap_folders.some((f) => f.id === this.folder)) {
			this.folder =
				this.folder_for(this.want_folder) || (this.imap_folders.length ? this.imap_folders[0].id : null);
			this.current = null;
			this.want_auto_open = true;
		}
		this.render_folders();
		this.refresh();
		this.load_counts();
		// Mulai sekarang sinkron otomatis jalan di halaman desk mana pun (juga sesudah browser
		// dibuka lagi); Mailbox dibuka = langsung ambil yang terbaru tanpa menunggu gilirannya.
		LocalMail.mark_ready(true);
		this.engine.start_auto_sync();
		this.poll().catch(() => {});

		this.ready_done = true;
		if (this.pending_open) {
			const route = this.pending_open;
			this.pending_open = null;
			this.open_route(route);
		}
	}

	folder_defs() {
		const icons = {
			inbox: "inbox",
			sentitems: "send",
			drafts: "file-pen",
			junkemail: "shield-alert",
			deleteditems: "trash-2",
		};
		return (this.engine ? this.engine.folders : []).map((f) => ({
			name: f.id,
			label: f.name,
			icon: icons[f.kind],
			depth: f.path.length - 1,
		}));
	}

	render_folders() {
		super.render_folders();
		if (!this.engine || !this.engine.root) return;
		// Letak folder laptop & lama simpan ada di dialog Pengaturan.
		this.$folders.append(this.side_item(__("Settings"), "settings", { cls: "mbx-settings" }));
	}

	// Teguran di atas panel: sesi Microsoft habis / gagal mengambil email baru.
	set_banner(html) {
		this.$banner.html(html || "");
	}

	load_folders() {
		this.render_folders();
		this.load_counts();
	}

	is_sent_folder() {
		const f = this.engine && this.engine.folders.find((x) => x.id === this.folder);
		return Boolean(f && ["sentitems", "drafts"].includes(f.kind));
	}

	// ------------------------------------------------------------ sinkron

	// Tombol Sync dan saat Mailbox dibuka. Putaran rutinnya dijalankan mesin sendiri
	// (start_auto_sync), di halaman desk mana pun.
	poll() {
		if (!this.engine || !this.engine.account) return Promise.resolve(0);
		return this.engine.sync_now().then((changed) => {
			if (changed) this.refresh_soon();
			return changed;
		});
	}

	// Hasil tiap sinkron, termasuk yang otomatis: null = berhasil.
	show_status(e) {
		if (!e) return this.set_banner(null);
		const esc = frappe.utils.escape_html;
		this.set_banner(
			e.need === "login"
				? `<div class="mbx-note mbx-warn">${__(
						"Microsoft session expired. Email on this laptop can still be read; sign in again to fetch new email."
				  )}<br><button class="btn btn-default btn-xs mbx-relogin">${__("Sign in to Microsoft")}</button></div>`
				: `<div class="mbx-note mbx-warn">${__("Failed to fetch new email: {0}", [esc(e.message)])}</div>`
		);
	}

	// Tombol Tarik Email.
	sync() {
		if (this.syncing) return;
		this.syncing = true;
		this.page.btn_secondary.prop("disabled", true);
		this.poll()
			.then((changed) =>
				frappe.show_alert({
					message: changed ? __("Email updated") : __("No new emails"),
					indicator: changed ? "green" : "gray",
				})
			)
			.catch(() => {})
			.finally(() => {
				this.syncing = false;
				this.page.btn_secondary.prop("disabled", false);
			});
	}

	// Sinkron awal membawa perubahan per 100 email: daftar cukup disegarkan tiap beberapa detik,
	// dan tidak sama sekali kalau user sudah memuat halaman berikutnya (posisinya tidak direset).
	refresh_soon() {
		// ...begitu juga kalau user sedang melihat email lama dari Microsoft (load_older).
		if (this.refresh_timer || this.mails.length > PAGE_LENGTH || this.older_next !== undefined) return;
		this.refresh_timer = setTimeout(() => {
			this.refresh_timer = null;
			this.refresh();
			this.load_counts();
		}, 2000);
	}

	load_counts() {
		if (!this.engine) return;
		for (const f of this.engine.folders) {
			if (["sentitems", "drafts"].includes(f.kind)) continue;
			this.engine.unread(f.id).then((n) => this.folder_el(f.id).find(".mbx-count").text(n || ""));
		}
	}

	// ------------------------------------------------------------ baca

	fetch_rows() {
		if (!this.engine || !this.folder) return Promise.resolve([]);
		return this.engine.list({
			folder: this.folder,
			search: this.search,
			dates: this.dates,
			start: this.start,
			limit: PAGE_LENGTH,
		});
	}

	refresh() {
		// undefined = email lama belum dibuka; null = sudah habis
		this.older_next = undefined;
		super.refresh();
	}

	render_list(has_more) {
		super.render_list(has_more);
		if (!this.mails.length && !(this.engine && this.engine.last_sync)) {
			this.$list.find(".mbx-empty").text(__("Fetching email from Microsoft..."));
		}
		// Di ujung daftar laptop: email yang lebih lama dari rentang simpan, dari Microsoft.
		const days = this.engine && this.engine.days;
		if (!has_more && days && this.folder && this.older_next !== null) {
			this.$list.append(`
				<div class="mbx-older">
					<button class="btn btn-default btn-sm">${__("Show email older than {0} days", [days])}</button>
				</div>`);
		}
	}

	load_older() {
		const folder = this.folder;
		this.$list.find(".mbx-older button").prop("disabled", true).text(__("Loading from Microsoft..."));
		this.engine
			.older({ folder, search: this.search, dates: this.dates, next: this.older_next })
			.then(({ rows, next }) => {
				if (folder !== this.folder) return;
				this.older_next = next;
				this.mails = this.mails.concat(rows);
				this.render_list(false);
				if (!rows.length && !next) {
					frappe.show_alert({ message: __("No older emails"), indicator: "gray" });
				}
			})
			.catch((e) => {
				this.show_error(e);
				this.render_list(false);
			});
	}

	fetch_doc(name) {
		return this.engine.get(name);
	}

	// .eml polos (didekripsi dari salinan laptop, atau diambil dari Microsoft) untuk dibuka di
	// Outlook; nama berkasnya dari subjek, yang di laptop sengaja tidak memakainya.
	download_eml(doc) {
		this.engine
			.eml(doc.name)
			.then((blob) => {
				const a = document.createElement("a");
				a.href = URL.createObjectURL(blob);
				const subject = (doc.subject || "email").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 80);
				a.download = `${subject}.eml`;
				a.click();
				setTimeout(() => URL.revokeObjectURL(a.href), 10000);
			})
			.catch((e) => this.show_error(e));
	}

	persist_seen(doc) {
		return this.engine.mark_read(doc.name);
	}

	load_attachments(doc) {
		return Promise.resolve(doc.attachments || []);
	}

	folder_for(want) {
		const kind = want === "Sent" ? "sentitems" : want ? "inbox" : null;
		const f = kind && (this.imap_folders || []).find((x) => x.kind === kind);
		return f ? f.id : null;
	}

	on_show() {
		this.show_requested_folder();
		const route = frappe.route_options || {};
		const open = route.open || frappe.utils.get_url_arg("open");
		if (!open && !route.message_id) return;

		frappe.route_options = null;
		window.history.replaceState(null, "", window.location.pathname);
		const request = { open, message_id: route.message_id, compose: route.compose };
		if (this.ready_done) this.open_route(request);
		else this.pending_open = request;
	}

	// Dari tab Email transaksi / notifikasi: yang dibawa nomor Communication ERP, sedangkan di
	// sini email dicari lewat Message-ID-nya di mailbox Microsoft user.
	async open_route({ open, message_id, compose }) {
		try {
			let mid = message_id;
			if (!mid && open) {
				const r = await frappe.db.get_value("Communication", open, "message_id");
				mid = r && r.message && r.message.message_id;
			}
			const id = mid && (await this.engine.find(mid));
			if (!id) {
				frappe.msgprint(__("This email was not found in your Microsoft mailbox."));
				return;
			}
			this.open(id, { compose });
		} catch (e) {
			this.show_error(e);
		}
	}

	// ------------------------------------------------------------ tautan ke transaksi

	// Email mode laptop belum tentu ada di ERP; dicari lewat Message-ID.
	fetch_links(doc) {
		if (!doc.message_id) return Promise.resolve([]);
		return frappe
			.xcall("erpnext_custom.outlook_addin.lookup", {
				mailbox: this.engine.mailbox,
				message_id: doc.message_id,
			})
			.then((r) => {
				doc.erp_name = r.communication;
				return r.links || [];
			});
	}

	async save_links(doc, current, picked) {
		const key = (l) => `${l.doctype}::${l.name}`;
		if (current.map(key).sort().join() === picked.map(key).sort().join()) return false;
		if (!doc.message_id) throw new Error(__("This email has no Message-ID, so it cannot be linked."));

		const r = await frappe.xcall("erpnext_custom.outlook_addin.save_links", {
			mailbox: this.engine.mailbox,
			message_id: doc.message_id,
			links: picked,
			// Isi lengkap hanya dikirim kalau email ini belum pernah disimpan ke ERP.
			eml_b64: !doc.erp_name && picked.length ? await this.engine.eml_b64(doc.name) : null,
		});
		doc.erp_name = r.communication;
		return true;
	}

	// ------------------------------------------------------------ tulis

	load_senders(control) {
		control.df.options = this.engine.mailbox;
		control.refresh();
		control.set_value(this.engine.mailbox);
	}

	own_address() {
		return this.engine.mailbox;
	}

	// Lampiran tidak diunggah ke ERP: dikirim langsung ke Microsoft saat Kirim.
	add_files(files) {
		if (!this.composer || !files || !files.length) return;
		for (const file of Array.from(files)) {
			this.composer.draft.files.push({
				file_name: file.name,
				blob: file,
				file_url: URL.createObjectURL(file),
			});
		}
		this.render_draft_files();
		this.$reader.find(".mbx-c-input").val("");
	}

	async deliver({ draft, recipients, cc, subject, content }) {
		const sent = await this.engine.send({
			mode: draft.mode,
			source: draft.source,
			to: recipients,
			cc,
			subject,
			html: content,
			files: draft.files,
			want_eml: draft.links.length > 0,
		});

		if (draft.links.length) {
			// Email SUDAH terkirim: gagal menautkan tidak boleh membuat tombol Kirim aktif lagi
			// (user akan mengirim dua kali).
			try {
				if (!sent.message_id) throw new Error("no Message-ID");
				await frappe.xcall("erpnext_custom.outlook_addin.save_links", {
					mailbox: this.engine.mailbox,
					message_id: sent.message_id,
					links: draft.links,
					eml_b64: sent.eml_b64,
				});
			} catch {
				frappe.msgprint(
					__("Email sent, but linking it to the transaction failed. Link it again from the Sent folder.")
				);
			}
		}

		// Kiriman muncul di Terkirim lewat sinkron berikutnya.
		setTimeout(() => this.poll().catch(() => {}), 3000);
	}

	// ------------------------------------------------------------ pengaturan

	// Settings Mailbox: tab Local Email | Signature | Rule. Tiap tab disiapkan saat pertama dibuka
	// (Signature & Rule menghubungi server/Microsoft, jangan dimuat kalau tidak dilihat).
	settings() {
		const engine = this.engine;
		if (!engine || !engine.home) return;

		const dialog = new frappe.ui.Dialog({
			title: __("Mail Settings"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		const $body = dialog.fields_dict.body.$wrapper;
		$body.html(`
			<ul class="nav nav-tabs mbx-set-tabs">
				<li class="nav-item"><a class="nav-link" data-tab="local">${__("Local Email")}</a></li>
				<li class="nav-item"><a class="nav-link" data-tab="signature">${__("Signature")}</a></li>
				<li class="nav-item"><a class="nav-link" data-tab="rule">${__("Rule")}</a></li>
			</ul>
			<div class="mbx-set-pane" data-pane="local"></div>
			<div class="mbx-set-pane" data-pane="signature"></div>
			<div class="mbx-set-pane" data-pane="rule"></div>
		`);

		const build = {
			local: ($pane) => this.settings_local($pane, dialog),
			signature: ($pane) => this.settings_signature($pane),
			rule: ($pane) => this.settings_rule($pane),
		};
		const built = new Set();
		const show = (tab) => {
			$body.find(".mbx-set-tabs .nav-link").each((_i, el) => {
				el.classList.toggle("active", el.getAttribute("data-tab") === tab);
			});
			$body.find(".mbx-set-pane").each((_i, el) => {
				el.classList.toggle("hidden", el.getAttribute("data-pane") !== tab);
			});
			if (!built.has(tab)) {
				built.add(tab);
				build[tab]($body.find(`[data-pane="${tab}"]`));
			}
		};
		$body.on("click", ".mbx-set-tabs .nav-link", (e) => {
			e.preventDefault();
			show(e.currentTarget.getAttribute("data-tab"));
		});

		dialog.show();
		show("local");
	}

	// Tab Local Email: letak penyimpanan di laptop, dan folder Outlook yang disimpan.
	settings_local($pane, dialog) {
		const engine = this.engine;
		const esc = frappe.utils.escape_html;
		let all = [];

		$pane.html(`
			<div>${__("Mailbox")}: <b>${esc(engine.mailbox)}</b></div>
			<div>${__("Storage folder")}: <b>${esc(engine.root_label())}</b></div>
			<div>${__("Kept on laptop")}: <b>${
				engine.days ? __("last {0} days", [engine.days]) : __("all email")
			}</b> <span class="text-muted">(${__("set by admin in ERPNext Custom Setting")})</span></div>
			<div>${__("Auto sync")}: <b>${__("every {0} seconds while ERP is open", [engine.sync_seconds()])}</b></div>
			<div class="text-muted small">${__(
				"Layout: folder {0}, then Outlook folder and month. Each email is one encrypted .enc file; use Download .eml in the reader to open one in Outlook.",
				[esc(engine.mailbox)]
			)}</div>
			<div style="margin-top: 8px; display: flex; gap: 8px;">
				${
					window.showDirectoryPicker
						? `<button class="btn btn-default btn-xs mbx-root">${__("Change Storage Folder")}</button>`
						: ""
				}
				<button class="btn btn-default btn-xs mbx-signout">${__("Sign out of Microsoft")}</button>
				<button class="btn btn-default btn-xs mbx-reset">${__("Reset Mailbox")}</button>
			</div>
			<div class="mbx-set-title">${__("Outlook folders stored on this laptop")}</div>
			<div class="mbx-set-folders"><div class="text-muted">${__("Loading folders from Microsoft...")}</div></div>
			<div class="mbx-set-foot">
				<button class="btn btn-primary btn-sm mbx-set-save-folders">${__("Save")}</button>
			</div>
		`);

		$pane.on("click", ".mbx-root", () =>
			engine.change_root().then(
				() => {
					dialog.hide();
					this.render_folders();
					frappe.show_alert({ message: __("Storage folder changed"), indicator: "green" });
				},
				(e) => this.show_auth_error(e)
			)
		);
		$pane.on("click", ".mbx-signout", () =>
			engine.sign_out().then(() => {
				dialog.hide();
				this.connect();
			})
		);
		// Mis. sudah masuk dengan akun yang salah, atau isi laptop kacau: mulai dari nol.
		$pane.on("click", ".mbx-reset", () =>
			frappe.confirm(
				__(
					"Reset the Mailbox on this laptop? You are signed out of Microsoft and the email copies of {0} on this laptop are deleted. They are downloaded again after you sign in; email in Microsoft is not affected.",
					[esc(engine.mailbox)]
				),
				() =>
					engine.reset().then(
						() => {
							dialog.hide();
							this.current = null;
							this.folder = null;
							this.imap_folders = [];
							this.render_folders();
							this.$reader.html(`<div class="mbx-empty">${__("Select an email to read")}</div>`);
							this.connect();
							frappe.show_alert({ message: __("Mailbox reset"), indicator: "green" });
						},
						(e) => this.show_error(e)
					)
			)
		);
		$pane.on("click", ".mbx-set-save-folders", () => {
			const on = new Set(
				$pane
					.find(".mbx-pick input:checked")
					.map((_i, el) => el.getAttribute("data-id"))
					.get()
			);
			const picked = all.filter((f) => on.has(f.id));
			if (!picked.length) {
				frappe.msgprint(__("Select at least one folder."));
				return;
			}
			engine.set_folders(picked).then(() => {
				dialog.hide();
				this.ready();
			});
		});

		engine.all_folders().then(
			(rows) => {
				all = rows;
				const on = new Set(engine.folders.map((f) => f.id));
				$pane.find(".mbx-set-folders").html(
					rows
						.map(
							(f) => `
						<label class="mbx-pick" style="padding-left: ${4 + (f.path.length - 1) * 18}px">
							<input type="checkbox" data-id="${esc(f.id)}" ${on.has(f.id) ? "checked" : ""}>
							<span>${esc(f.name)}</span>
						</label>`
						)
						.join("")
				);
			},
			(e) =>
				$pane
					.find(".mbx-set-folders")
					.html(`<div class="text-muted">${__("Folders could not be loaded: {0}", [esc(e.message)])}</div>`)
		);
	}

	// Tab Signature: seperti Outlook, beberapa signature (boleh bergambar), satu bawaan untuk
	// email baru dan satu untuk balasan/terusan. Disimpan di ERP per user (Mailbox Signature),
	// jadi ikut ke laptop mana pun.
	settings_signature($pane) {
		const esc = frappe.utils.escape_html;
		let rows = [];
		let current = null;

		$pane.html(`
			<div class="mbx-sig">
				<div class="mbx-sig-list"></div>
				<div class="mbx-sig-edit">
					<div class="mbx-sig-company hidden"></div>
					<div class="mbx-sig-form">
						<div class="mbx-sig-name"></div>
						<div class="mbx-sig-content"></div>
						<div class="mbx-sig-new"></div>
						<div class="mbx-sig-reply"></div>
						<div class="mbx-set-foot">
							<button class="btn btn-default btn-sm mbx-sig-delete">${__("Delete")}</button>
							<button class="btn btn-primary btn-sm mbx-sig-save">${__("Save")}</button>
						</div>
					</div>
				</div>
			</div>
		`);
		const control = (selector, df) =>
			frappe.ui.form.make_control({ parent: $pane.find(selector), df, render_input: true });
		const f = {
			name: control(".mbx-sig-name", { fieldtype: "Data", fieldname: "signature_name", label: __("Signature Name") }),
			content: control(".mbx-sig-content", {
				fieldtype: "Text Editor",
				fieldname: "content",
				label: __("Signature"),
				description: __("Use the image button in the toolbar to add a logo or picture."),
			}),
			use_new: control(".mbx-sig-new", {
				fieldtype: "Check",
				fieldname: "use_for_new",
				label: __("Default for new messages"),
			}),
			use_reply: control(".mbx-sig-reply", {
				fieldtype: "Check",
				fieldname: "use_for_reply",
				label: __("Default for replies and forwards"),
			}),
		};

		const render_list = () => {
			$pane.find(".mbx-sig-list").html(`
				<button class="btn btn-default btn-sm btn-block mbx-sig-add">${__("New Signature")}</button>
				${rows
					.map(
						(r) => `
					<div class="mbx-sig-item ${current && current.name === r.name ? "active" : ""}"
						data-name="${esc(r.name)}">
						<div>${esc(r.signature_name)}</div>
						<div class="text-muted small">${[
							r.use_for_new ? __("New messages") : "",
							r.use_for_reply ? __("Replies and forwards") : "",
						]
							.filter(Boolean)
							.join(", ")}</div>
					</div>`
					)
					.join("")}
			`);
		};
		const edit = (row) => {
			current = row || null;
			// Signature perusahaan: hanya pratinjau. Isinya dari template admin + data User.
			const company = Boolean(row && row.company);
			$pane.find(".mbx-sig-form").toggleClass("hidden", company);
			$pane
				.find(".mbx-sig-company")
				.toggleClass("hidden", !company)
				.html(
					company
						? `<div class="text-muted small" style="margin-bottom: 12px;">${__(
								"Filled automatically from your user profile: name, Job Title, email, Mobile No, and Branch (branch address and phone). It is your default until you mark one of your own signatures as default. The admin edits the template in ERPNext Custom Setting > Mailbox."
						  )}</div>${row.content}`
						: ""
				);
			if (company) return render_list();
			f.name.set_value(row ? row.signature_name : "");
			f.content.set_value(row ? row.content || "" : "");
			f.use_new.set_value(row ? row.use_for_new : 0);
			f.use_reply.set_value(row ? row.use_for_reply : 0);
			$pane.find(".mbx-sig-delete").toggleClass("hidden", !row);
			render_list();
		};
		const load = (select) => {
			// composer ikut memakai daftar yang baru
			this.signatures = null;
			return this.load_signatures().then((list) => {
				rows = list;
				edit(rows.find((r) => r.name === select) || rows[0]);
			});
		};

		$pane.on("click", ".mbx-sig-add", () => edit(null));
		$pane.on("click", ".mbx-sig-item", (e) =>
			edit(rows.find((r) => r.name === e.currentTarget.getAttribute("data-name")))
		);
		$pane.on("click", ".mbx-sig-save", () => {
			const values = {
				signature_name: (f.name.get_value() || "").trim(),
				content: f.content.get_value() || "",
				use_for_new: f.use_new.get_value() ? 1 : 0,
				use_for_reply: f.use_reply.get_value() ? 1 : 0,
			};
			if (!values.signature_name) {
				frappe.msgprint(__("Signature name is required."));
				return;
			}
			const request = current
				? frappe.xcall("frappe.client.set_value", {
						doctype: "Mailbox Signature",
						name: current.name,
						fieldname: values,
				  })
				: frappe.xcall("frappe.client.insert", { doc: { doctype: "Mailbox Signature", ...values } });
			request.then((doc) => {
				frappe.show_alert({ message: __("Signature saved"), indicator: "green" });
				load(doc.name);
			});
		});
		$pane.on("click", ".mbx-sig-delete", () => {
			if (!current) return;
			frappe.confirm(__("Delete signature {0}?", [esc(current.signature_name)]), () =>
				frappe
					.xcall("frappe.client.delete", { doctype: "Mailbox Signature", name: current.name })
					.then(() => load())
			);
		});

		load();
	}

	// Tab Rule: rule Outlook yang asli (Microsoft). Jalan untuk email baru di Inbox walau
	// laptop mati, dan tampil juga di Outlook. Butuh izin MailboxSettings.ReadWrite di Azure.
	settings_rule($pane) {
		const engine = this.engine;
		const esc = frappe.utils.escape_html;
		let rules = [];
		let folders = [];

		const split = (text) =>
			String(text || "")
				.split(/[,;]/)
				.map((s) => s.trim())
				.filter(Boolean);
		const people = (text) => split(text).map((address) => ({ emailAddress: { address } }));
		const addresses = (list) => (list || []).map((p) => p.emailAddress && p.emailAddress.address).join(", ");
		const folder_label = (f) => f.path.join(" / ");
		const folder_name = (id) => {
			const f = folders.find((x) => x.id === id);
			return f ? folder_label(f) : __("another folder");
		};

		const describe = (r) => {
			const c = r.conditions || {};
			const a = r.actions || {};
			const when = [
				c.senderContains && __("from contains {0}", [c.senderContains.join(", ")]),
				c.subjectContains && __("subject contains {0}", [c.subjectContains.join(", ")]),
				c.bodyContains && __("body contains {0}", [c.bodyContains.join(", ")]),
				c.sentToAddresses && __("sent to {0}", [addresses(c.sentToAddresses)]),
				c.hasAttachments && __("has attachment"),
			].filter(Boolean);
			const then = [
				a.moveToFolder && __("move to {0}", [folder_name(a.moveToFolder)]),
				a.markAsRead && __("mark as read"),
				a.delete && __("delete"),
				a.forwardTo && __("forward to {0}", [addresses(a.forwardTo)]),
				a.stopProcessingRules && __("stop processing more rules"),
			].filter(Boolean);
			return `${when.length ? __("If {0}", [when.join(", ")]) : __("All new email")}: ${then.join(", ")}`;
		};

		const list = () => {
			$pane.html(`<div class="text-muted">${__("Loading rules from Microsoft...")}</div>`);
			Promise.all([engine.rules(), engine.all_folders()]).then(
				([r, f]) => {
					rules = r;
					folders = f;
					render();
				},
				(e) =>
					$pane.html(`
						<div class="text-muted">${__("Rules could not be loaded: {0}", [esc(e.message)])}</div>
						<div class="text-muted small">${__(
							"Rules need the Microsoft Graph permission MailboxSettings.ReadWrite (delegated, with admin consent) in Azure."
						)}</div>`)
			);
		};

		const render = () => {
			$pane.html(`
				<div class="text-muted small">${__(
					"Outlook rules run at Microsoft on new email in the Inbox, even when this laptop is off. They also appear in Outlook."
				)}</div>
				<div class="mbx-rule-list">${
					rules.length
						? rules
								.map(
									(r) => `
						<div class="mbx-rule" data-id="${esc(r.id)}">
							<label class="mbx-rule-on">
								<input type="checkbox" class="mbx-rule-enabled" ${r.isEnabled ? "checked" : ""}>
								<b>${esc(r.displayName)}</b>
							</label>
							<div class="text-muted small">${esc(describe(r))}</div>
							<div class="mbx-rule-actions">
								<button class="btn btn-default btn-xs mbx-rule-edit">${__("Edit")}</button>
								<button class="btn btn-default btn-xs mbx-rule-delete">${__("Delete")}</button>
							</div>
						</div>`
								)
								.join("")
						: `<div class="text-muted" style="margin-top: 10px;">${__("No rules yet.")}</div>`
				}</div>
				<div class="mbx-set-foot">
					<button class="btn btn-primary btn-sm mbx-rule-add">${__("New Rule")}</button>
				</div>
			`);
		};

		const edit = (rule) => {
			const c = (rule && rule.conditions) || {};
			const a = (rule && rule.actions) || {};
			$pane.html(`
				<div class="mbx-rule-form"></div>
				<div class="mbx-set-foot">
					<button class="btn btn-default btn-sm mbx-rule-cancel">${__("Cancel")}</button>
					<button class="btn btn-primary btn-sm mbx-rule-save">${__("Save")}</button>
				</div>
			`);
			const form = new frappe.ui.FieldGroup({
				parent: $pane.find(".mbx-rule-form"),
				fields: [
					{ fieldtype: "Data", fieldname: "name", label: __("Rule Name"), reqd: 1 },
					{ fieldtype: "Section Break", label: __("When a new email arrives and") },
					{
						fieldtype: "Data",
						fieldname: "from",
						label: __("From contains"),
						description: __("Name or address. Separate several with commas."),
					},
					{ fieldtype: "Data", fieldname: "subject", label: __("Subject contains") },
					{ fieldtype: "Data", fieldname: "body", label: __("Body contains") },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Data", fieldname: "sent_to", label: __("Sent to") },
					{ fieldtype: "Check", fieldname: "has_attachment", label: __("Has attachment") },
					{ fieldtype: "Section Break", label: __("Do the following") },
					{
						fieldtype: "Select",
						fieldname: "move_to",
						label: __("Move to folder"),
						options: ["", ...folders.map(folder_label)].join("\n"),
					},
					{ fieldtype: "Check", fieldname: "mark_read", label: __("Mark as read") },
					{ fieldtype: "Check", fieldname: "delete", label: __("Delete") },
					{ fieldtype: "Column Break" },
					{ fieldtype: "Data", fieldname: "forward_to", label: __("Forward to") },
					{ fieldtype: "Check", fieldname: "stop", label: __("Stop processing more rules") },
					{ fieldtype: "Check", fieldname: "enabled", label: __("Turn on this rule") },
				],
			});
			form.make();
			const moved = a.moveToFolder && folders.find((f) => f.id === a.moveToFolder);
			form.set_values({
				name: (rule && rule.displayName) || "",
				from: (c.senderContains || []).join(", "),
				subject: (c.subjectContains || []).join(", "),
				body: (c.bodyContains || []).join(", "),
				sent_to: addresses(c.sentToAddresses),
				has_attachment: c.hasAttachments ? 1 : 0,
				move_to: moved ? folder_label(moved) : "",
				mark_read: a.markAsRead ? 1 : 0,
				delete: a.delete ? 1 : 0,
				forward_to: addresses(a.forwardTo),
				stop: a.stopProcessingRules ? 1 : 0,
				enabled: rule ? (rule.isEnabled ? 1 : 0) : 1,
			});

			$pane.find(".mbx-rule-cancel").on("click", render);
			$pane.find(".mbx-rule-save").on("click", () => {
				const v = form.get_values();
				if (!v) return;
				// Mulai dari isi rule lama: kondisi/aksi yang dibuat di Outlook dan tidak ada di
				// form ini (mis. kategori) tetap terbawa.
				const conditions = { ...c };
				const actions = { ...a };
				const put = (target, key, value) => {
					const empty = value === false || value === "" || value == null || (Array.isArray(value) && !value.length);
					if (empty) delete target[key];
					else target[key] = value;
				};
				put(conditions, "senderContains", split(v.from));
				put(conditions, "subjectContains", split(v.subject));
				put(conditions, "bodyContains", split(v.body));
				put(conditions, "sentToAddresses", people(v.sent_to));
				put(conditions, "hasAttachments", Boolean(v.has_attachment));
				const target = folders.find((f) => folder_label(f) === v.move_to);
				put(actions, "moveToFolder", target ? target.id : null);
				put(actions, "markAsRead", Boolean(v.mark_read));
				put(actions, "delete", Boolean(v.delete));
				put(actions, "forwardTo", people(v.forward_to));
				put(actions, "stopProcessingRules", Boolean(v.stop));

				if (!Object.keys(actions).some((k) => k !== "stopProcessingRules")) {
					frappe.msgprint(__("Choose at least one action."));
					return;
				}
				const $save = $pane.find(".mbx-rule-save").prop("disabled", true);
				engine
					.save_rule({
						id: rule ? rule.id : undefined,
						displayName: v.name,
						sequence: rule ? rule.sequence : Math.max(0, ...rules.map((r) => r.sequence || 0)) + 1,
						isEnabled: Boolean(v.enabled),
						conditions,
						actions,
					})
					.then(
						() => {
							frappe.show_alert({ message: __("Rule saved"), indicator: "green" });
							list();
						},
						(e) => {
							$save.prop("disabled", false);
							this.show_auth_error(e);
						}
					);
			});
		};

		const rule_of = (e) => rules.find((r) => r.id === $(e.currentTarget).closest(".mbx-rule").attr("data-id"));
		$pane.on("click", ".mbx-rule-add", () => edit(null));
		$pane.on("click", ".mbx-rule-edit", (e) => edit(rule_of(e)));
		$pane.on("click", ".mbx-rule-delete", (e) => {
			const rule = rule_of(e);
			frappe.confirm(__("Delete rule {0}?", [esc(rule.displayName)]), () =>
				engine.delete_rule(rule.id).then(list, (err) => this.show_auth_error(err))
			);
		});
		$pane.on("change", ".mbx-rule-enabled", (e) => {
			const rule = rule_of(e);
			const on = e.currentTarget.checked;
			engine.save_rule({ id: rule.id, isEnabled: on }).then(
				() => (rule.isEnabled = on),
				(err) => {
					e.currentTarget.checked = !on;
					this.show_auth_error(err);
				}
			);
		});

		list();
	}
}

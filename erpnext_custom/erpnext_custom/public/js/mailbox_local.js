// Mailbox mode laptop: mesin tanpa tampilan untuk halaman Mailbox (page/mailbox, LocalMailbox).
// Dimuat di SEMUA halaman desk (hooks app_include_js, naikkan ?v= di sana tiap berkas ini
// berubah): sinkron otomatis jalan selama ERP terbuka, bukan cuma saat Mailbox dibuka.
//
// Email diambil browser LANGSUNG dari Microsoft 365 (Graph, login MSAL per user) dan disimpan
// sebagai berkas .eml di folder laptop pilihan user (File System Access API, Edge/Chrome;
// browser lain jatuh ke penyimpanan browser/OPFS). Server ERP tidak menyimpan apa pun kecuali
// email yang ditautkan ke transaksi (erpnext_custom.outlook_addin.save_links).
//
// Susunan di disk, relatif ke folder pilihan user:
//   <alamat mailbox>/<folder Outlook>/<yyyy-mm>/<yyyymmdd-hhmm> <tanda>.enc
// Daftar, hitungan, dan pencarian memakai indeks di IndexedDB (dibangun dari Microsoft, bisa
// diulang kapan saja); isi email dibaca dari berkas.
//
// ENKRIPSI: isi berkas dan data sensitif indeks (SECRET_FIELDS: subjek, pengirim, penerima,
// cuplikan, Message-ID) dienkripsi AES-256-GCM dengan kunci per user dari server ERP
// (outlook_addin.mailbox_key), yang dipegang di memori saja: berkas yang disalin keluar, laptop
// yang hilang, atau akun ERP yang dinonaktifkan = salinannya tak terbaca. Nama berkas sengaja
// tanpa subjek. Format berkas, dibaca juga oleh public/mailbox_decrypt.html (alat membuka tanpa
// ERP, memakai kunci dari tombol Export Mailbox Key di form User):
//   "CME1" (4 byte) | IV (12 byte) | ciphertext AES-256-GCM beserta tag 16 byte
// Salinan dari sebelum enkripsi (.eml polos, indeks polos) dienkripsi sekali oleh migrate().
// Karena jalur berkas disimpan relatif, folder yang dipindah user sendiri (mis. D: ke E:) cukup
// dipilih ulang tanpa unduh ulang. Berkas yang hilang diunduh ulang saat dibuka.
//
// Sinkron = delta query Graph per folder, terbaru dulu. Titik lanjutnya disimpan tiap halaman,
// jadi sinkron awal mailbox besar boleh terputus lalu lanjut. Id pesan memakai ImmutableId
// supaya email yang dipindah folder di Outlook tetap satu id (berkasnya ikut dipindah, tidak
// diunduh ulang).
//
// Rentang simpan (ERPNext Custom Setting > Mailbox, "Simpan Email di Laptop (hari)", satu
// angka untuk semua user) bergulir seperti setelan unduh Outlook: yang lebih lama dihapus dari
// laptop (tetap di Microsoft) dan dibaca langsung dari Microsoft lewat older(). Angkanya diubah
// = sinkron diulang dari awal dengan batas baru.
//
// Library disimpan di app (public/vendor), bukan CDN: halaman redirect login menerima token
// langsung dari Microsoft, dan MSAL melarang memuatnya dari pihak ketiga.
//   msal-browser 5.23.0, postal-mime 3.0.0
(function () {
	const GRAPH = "https://graph.microsoft.com/v1.0";
	const SCOPES = ["Mail.ReadWrite", "Mail.Send", "User.Read"];
	// Hanya untuk tab Rule; admin menambahkannya di Azure (delegated + admin consent).
	const RULE_SCOPES = ["MailboxSettings.ReadWrite"];
	const VENDOR = "/assets/erpnext_custom/vendor";
	const REDIRECT = "/assets/erpnext_custom/mailbox_auth.html";
	const FIELDS =
		"subject,from,toRecipients,ccRecipients,receivedDateTime,isRead,hasAttachments,bodyPreview,internetMessageId";
	const PAGE = 100;
	// Graph menolak lebih dari 4 permintaan serentak per mailbox.
	const WORKERS = 3;
	// Di atas ini lampiran dikirim lewat upload session (batas satu permintaan Graph 4 MB).
	const SMALL_ATTACHMENT = 3 * 1024 * 1024;
	// Potongan upload session: kelipatan 320 KiB, di bawah 4 MB.
	const CHUNK = 12 * 320 * 1024;
	// Folder Outlook yang disinkron kalau user belum pernah memilih.
	const DEFAULT_FOLDERS = ["inbox", "sentitems"];
	const WELL_KNOWN = ["inbox", "sentitems", "drafts", "archive", "junkemail", "deleteditems"];
	// Penanda awal berkas terenkripsi (lihat keterangan di atas).
	const MAGIC = new TextEncoder().encode("CME1");
	// Kolom indeks yang disimpan terenkripsi (baris.sec); sisanya dibutuhkan indeks IndexedDB.
	const SECRET_FIELDS = ["subject", "from_name", "from_addr", "to", "cc", "preview", "imid"];

	class NeedAction extends Error {
		constructor(need, message) {
			super(message || need);
			this.need = need;
		}
	}

	class LocalMail {
		constructor(cfg) {
			this.cfg = cfg;
			this.mailbox = cfg.email.toLowerCase();
			// hari yang disimpan di laptop; 0 = semua
			this.days = Math.max(parseInt(cfg.keep_days, 10) || 0, 0);
			this.account = null;
			this.root = null;
			this.home = null;
			this.folders = [];
			this.urls = [];
			this.claimed = new Set();
			// dipanggil tiap satu halaman sinkron membawa perubahan (halaman menyegarkan daftar)
			this.on_change = null;
			// dipanggil sesudah tiap sinkron: null = berhasil, Error = gagal (teguran di Mailbox)
			this.on_status = null;
			this.last_sync = null;
			// kunci AES (CryptoKey non-extractable) dan cache baris indeks yang sudah dibuka
			this.key = null;
			this.opened = new Map();
		}

		async init() {
			this.db = await open_db(`erp-mailbox|${frappe.session.user}`);
			await this.load_key();
			// Email User di ERP diganti (mis. salah ketik lalu dibetulkan admin): isi laptop milik
			// alamat lama tidak dipakai lagi, mulai dari nol untuk alamat yang baru.
			const was = await this.kv_get("mailbox");
			if (was && was !== this.mailbox) await this.forget();
			await this.kv_set("mailbox", this.mailbox);
			// Bukan frappe.require: itu membekukan layar selama memuat, padahal mesin ini juga
			// disiapkan diam-diam di halaman desk mana pun untuk sinkron otomatis.
			if (!window.msal) await load_script(`${VENDOR}/msal-browser/msal-browser.min.js`);
			this.msal = new msal.PublicClientApplication({
				auth: {
					clientId: this.cfg.client_id,
					authority: `https://login.microsoftonline.com/${this.cfg.tenant_id || "organizations"}`,
					redirectUri: location.origin + REDIRECT,
				},
				// localStorage (dienkripsi MSAL): tetap masuk walau browser ditutup.
				cache: { cacheLocation: "localStorage" },
			});
			await this.msal.initialize();

			const saved = await this.kv_get("account");
			this.account = this.msal.getAllAccounts().find((a) => a.homeAccountId === saved) || null;
			this.folders = (await this.kv_get("folders")) || [];
			this.root_known = Boolean(await this.kv_get("root"));
			await this.open_root(false);
		}

		// ------------------------------------------------------------ kunci enkripsi

		// Kunci berganti (mis. situs dipulihkan tanpa site_config lamanya) = indeks lama tak
		// terbaca: dibangun ulang dari Microsoft, berkasnya tertimpa unduhan baru.
		async load_key() {
			const b64 = await frappe.xcall("erpnext_custom.outlook_addin.mailbox_key");
			const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
			this.key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);

			const check = await this.kv_get("key_check");
			const ok = Boolean(check) && (await this.unseal(check).then(() => true, () => false));
			if (check && !ok) await this.reset_index();
			if (!ok) await this.kv_set("key_check", await this.seal(new Uint8Array([1])));
		}

		async reset_index() {
			await done(this.store("messages", "readwrite").clear());
			for (const key of await done(this.store("kv").getAllKeys())) {
				if (String(key).startsWith("delta|")) await done(this.store("kv", "readwrite").delete(key));
			}
			this.opened.clear();
		}

		async seal(bytes) {
			const iv = crypto.getRandomValues(new Uint8Array(12));
			return { iv, data: await crypto.subtle.encrypt({ name: "AES-GCM", iv }, this.key, bytes) };
		}

		unseal({ iv, data }) {
			return crypto.subtle.decrypt({ name: "AES-GCM", iv }, this.key, data);
		}

		// ------------------------------------------------------------ login Microsoft

		// Harus dipanggil dari klik user: membuka popup login.
		async login() {
			const r = await this.msal.loginPopup({
				scopes: SCOPES,
				loginHint: this.mailbox,
				prompt: "select_account",
			});
			// Mailbox harus milik user ERP ini: arah email (masuk/terkirim) dan izin tautan di
			// server dihitung dari alamat itu.
			const me = await this.graph("/me?$select=mail,userPrincipalName", { token: r.accessToken });
			const names = [me.mail, me.userPrincipalName].map((x) => (x || "").toLowerCase());
			if (!names.includes(this.mailbox)) {
				await this.msal.clearCache({ account: r.account });
				throw new Error(
					__("Microsoft account {0} is not mailbox {1}. Sign in with {1}.", [
						me.mail || me.userPrincipalName,
						this.mailbox,
					])
				);
			}
			this.account = r.account;
			await this.kv_set("account", r.account.homeAccountId);
		}

		async sign_out() {
			if (this.account) await this.msal.clearCache({ account: this.account });
			this.account = null;
			await this.kv_set("account", null);
			LocalMail.mark_ready(false);
		}

		// Tombol Reset Mailbox: mulai dari nol di laptop ini. Keluar dari Microsoft, indeks dan
		// titik sinkron dikosongkan, salinan email mailbox ini di folder penyimpanan dihapus;
		// folder penyimpanan yang dipilih tetap. Email di Microsoft tidak tersentuh. Menunggu
		// sinkron/unduhan yang sedang jalan supaya tidak menulis ke indeks yang baru dikosongkan.
		reset() {
			const lock = (name, fn) => navigator.locks.request(`erp-mailbox-${name}|${this.mailbox}`, fn);
			return lock("sync", () =>
				lock("download", async () => {
					await this.sign_out();
					await this.forget();
					await this.kv_set("sealed", true); // folder dikosongkan: tidak ada yang dimigrasi
					if (!this.root) return;
					const name = safe_name(this.mailbox);
					await this.root.removeEntry(name, { recursive: true }).catch((e) => {
						if (e.name !== "NotFoundError") throw e;
					});
					this.home = await this.root.getDirectoryHandle(name, { create: true });
				})
			);
		}

		// Lupakan isi laptop untuk mailbox ini: indeks, titik sinkron, pilihan folder Outlook, akun.
		async forget() {
			await this.reset_index();
			this.folders = [];
			this.known = null;
			await this.kv_set("folders", []);
			await this.kv_set("account", null);
		}

		async token(scopes = SCOPES) {
			if (!this.account) throw new NeedAction("login");
			try {
				return (await this.msal.acquireTokenSilent({ scopes, account: this.account })).accessToken;
			} catch (e) {
				// Sesi Microsoft habis (refresh token SPA berumur 24 jam dan perpanjangan diam-diam
				// ditolak): user perlu klik Masuk lagi. Email di laptop tetap bisa dibaca.
				if (scopes === SCOPES) throw new NeedAction("login", e.message);
				// Izin tambahan (tab Rule) selalu dari klik user: boleh lewat popup.
				return (
					await this.msal.acquireTokenPopup({ scopes, account: this.account, loginHint: this.mailbox })
				).accessToken;
			}
		}

		async graph(path, opts = {}) {
			const url = path.startsWith("https://") ? path : GRAPH + path;
			for (let attempt = 0; ; attempt++) {
				const headers = {
					Authorization: `Bearer ${opts.token || (await this.token(opts.scopes))}`,
					Prefer: [opts.prefer, 'IdType="ImmutableId"'].filter(Boolean).join(", "),
				};
				let body = opts.body;
				if (body && !(body instanceof Blob)) {
					headers["Content-Type"] = "application/json";
					body = JSON.stringify(body);
				}

				const r = await fetch(url, { method: opts.method || "GET", headers, body });
				// Dibatasi Microsoft (throttling): tunggu lalu ulangi.
				if ([429, 503, 504].includes(r.status) && attempt < 6) {
					await sleep((Number(r.headers.get("Retry-After")) || 2 ** attempt) * 1000);
					continue;
				}
				if (!r.ok) {
					const detail = await r.json().catch(() => ({}));
					const err = new Error(
						`Microsoft Graph ${r.status}: ${(detail.error && detail.error.message) || r.statusText}`
					);
					err.status = r.status;
					throw err;
				}
				if (opts.blob) return r.blob();
				return r.status === 202 || r.status === 204 ? null : r.json();
			}
		}

		// ------------------------------------------------------------ folder di laptop

		// interactive = dipanggil dari klik (memilih folder / memberi izin ulang).
		async open_root(interactive) {
			let root = await this.kv_get("root");
			if (!root) {
				if (!window.showDirectoryPicker) {
					// Firefox/Safari tidak bisa memilih folder: simpan di penyimpanan browser.
					root = await navigator.storage.getDirectory();
				} else {
					if (!interactive) return null;
					root = await window.showDirectoryPicker({
						id: "erp-mailbox",
						mode: "readwrite",
						startIn: "documents",
					});
				}
				await this.kv_set("root", root);
				this.root_known = true;
			}
			// Nama folder terbaca walau izinnya belum diberikan (untuk pesan minta izin).
			this.root_name = root.name;

			// Izin folder berlaku per sesi browser, kecuali user memilih "izinkan setiap kunjungan".
			if (root.queryPermission && (await root.queryPermission({ mode: "readwrite" })) !== "granted") {
				if (!interactive || (await root.requestPermission({ mode: "readwrite" })) !== "granted") {
					return null;
				}
			}

			this.root = root;
			this.home = await root.getDirectoryHandle(safe_name(this.mailbox), { create: true });
			// Tanpa ini browser boleh membuang IndexedDB/OPFS saat disk penuh. Hanya dari klik:
			// Firefox menanyakannya ke user, jangan muncul tiba-tiba di halaman lain.
			if (interactive && navigator.storage && navigator.storage.persist) navigator.storage.persist();
			return root;
		}

		// Ganti folder penyimpanan (dari klik). Folder lama yang dipindah user sendiri ke sini
		// langsung terbaca; kalau isinya tidak ada, semua email diunduh ulang di latar.
		async change_root() {
			const root = await window.showDirectoryPicker({ id: "erp-mailbox", mode: "readwrite" });
			await this.kv_set("root", root);
			// folder lain bisa berisi salinan polos lama: periksa ulang (migrate)
			await this.kv_set("sealed", false);
			await this.open_root(true);

			const sample = await this.first_row((r) => r.path);
			if (sample && !(await this.read_file(sample.path).catch(() => null))) {
				await this.each_row((r) => {
					if (!r.path) return null;
					delete r.path;
					r.pending = r.date || "";
					return r;
				});
				this.download_pending();
			}
		}

		root_label() {
			if (!this.root) return "";
			// OPFS tidak bernama: itu penyimpanan internal browser, bukan folder di disk.
			return this.root.name || __("browser storage");
		}

		// Selalu ditulis terenkripsi (MAGIC | IV | ciphertext).
		async write_file(segments, blob) {
			const dir = await this.dir_of(segments, true);
			const file = await dir.getFileHandle(segments[segments.length - 1], { create: true });
			const { iv, data } = await this.seal(await blob.arrayBuffer());
			const w = await file.createWritable();
			await w.write(new Blob([MAGIC, iv, data]));
			await w.close();
		}

		// Isi berkas sebagai .eml biasa. Berkas polos lama (belum dimigrasi) dibaca apa adanya.
		async read_file(segments) {
			const dir = await this.dir_of(segments, false);
			const file = await (await dir.getFileHandle(segments[segments.length - 1])).getFile();
			const buf = await file.arrayBuffer();
			if (!is_sealed(buf)) return file;
			const plain = await this.unseal({ iv: buf.slice(4, 16), data: buf.slice(16) });
			return new Blob([plain], { type: "message/rfc822" });
		}

		async remove_file(segments) {
			try {
				const dir = await this.dir_of(segments, false);
				await dir.removeEntry(segments[segments.length - 1]);
			} catch (e) {
				if (e.name !== "NotFoundError") throw e;
			}
		}

		async dir_of(segments, create) {
			let dir = this.home;
			for (const name of segments.slice(0, -1)) dir = await dir.getDirectoryHandle(name, { create });
			return dir;
		}

		async file_path(row) {
			const folder = this.folders.find((f) => f.id === row.folder);
			const d = new Date(row.date || Date.now());
			const pad = (n) => String(n).padStart(2, "0");
			const month = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
			const stamp = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(
				d.getMinutes()
			)}`;
			// Tanda dari id: dua email di menit yang sama tidak saling menimpa. Subjek sengaja tidak
			// masuk nama berkas: isinya terenkripsi, namanya tidak.
			const tag = (await sha1(row.id)).slice(0, 8);
			const where = folder ? folder.path.map((p) => safe_name(p)) : ["Lainnya"];
			return [...where, month, `${stamp} ${tag}.enc`];
		}

		// ------------------------------------------------------------ folder Outlook

		async well_known() {
			if (!this.known) {
				const rows = await Promise.all(
					WELL_KNOWN.map((n) => this.graph(`/me/mailFolders/${n}?$select=id`).catch(() => null))
				);
				this.known = {};
				rows.forEach((r, i) => r && (this.known[r.id] = WELL_KNOWN[i]));
			}
			return this.known;
		}

		// Semua folder Outlook user, bersarang jadi daftar datar: [{id, name, path, kind}].
		async all_folders() {
			const out = [];
			const select = "$top=100&$select=id,displayName,childFolderCount";
			const walk = async (url, parent) => {
				for (let next = url; next; ) {
					const r = await this.graph(next);
					for (const f of r.value) {
						const path = [...parent, f.displayName];
						out.push({ id: f.id, name: f.displayName, path });
						if (f.childFolderCount) {
							await walk(`/me/mailFolders/${enc(f.id)}/childFolders?${select}`, path);
						}
					}
					next = r["@odata.nextLink"];
				}
			};
			await walk(`/me/mailFolders?${select}`, []);

			const known = await this.well_known();
			for (const f of out) f.kind = known[f.id] || null;
			// Urutan seperti Outlook: Kotak Masuk, Terkirim, Draf, folder lain, lalu Junk/Sampah.
			const rank = (f) => {
				const top = f.path.length === 1 ? f : out.find((x) => x.id && x.path.length === 1 && x.name === f.path[0]);
				const at = ["inbox", "sentitems", "drafts"].indexOf(top && top.kind);
				if (at >= 0) return at;
				return ["junkemail", "deleteditems"].includes(top && top.kind) ? 9 : 5;
			};
			return out
				.map((f, i) => ({ f, i }))
				.sort((a, b) => rank(a.f) - rank(b.f) || a.i - b.i)
				.map((x) => x.f);
		}

		async ensure_folders() {
			if (this.folders.length) return;
			const all = await this.all_folders();
			await this.set_folders(all.filter((f) => DEFAULT_FOLDERS.includes(f.kind)));
		}

		// Folder yang dilepas tidak dihapus dari laptop, cuma berhenti disinkron & disembunyikan.
		async set_folders(folders) {
			this.folders = folders.map(({ id, name, path, kind }) => ({ id, name, path, kind }));
			await this.kv_set("folders", this.folders);
		}

		// ------------------------------------------------------------ sinkron

		sync() {
			// Satu tab saja yang menyinkron; tab lain cukup membaca indeks yang sama.
			return navigator.locks.request(
				`erp-mailbox-sync|${this.mailbox}`,
				{ ifAvailable: true },
				async (lock) => {
					if (!lock) return 0;
					let changed = 0;
					this.fresh = [];
					for (const folder of this.folders) {
						try {
							changed += await this.sync_folder(folder);
						} catch (e) {
							// Folder dihapus di Outlook: lewati, folder lain tetap disinkron.
							if (e.status !== 404) throw e;
						}
					}
					const removed = await this.prune();
					if (removed && this.on_change) this.on_change();
					this.download_pending();
					await this.notify_fresh();
					return changed + removed;
				}
			);
		}

		// Sinkron tiap `sync_seconds` detik (ERPNext Custom Setting > Mailbox, minimal 15, dijaga
		// server) selama tab ERP ini terbuka, di halaman desk mana pun. Tab yang tidak terlihat
		// dibatasi browser sendiri jadi sekitar sekali semenit. Belum bisa (izin folder belum
		// diberikan lagi, sesi Microsoft habis) = dilewati diam-diam; halaman Mailbox yang
		// meminta user bertindak.
		start_auto_sync() {
			if (this.timer) return;
			this.timer = setInterval(() => this.sync_now().catch(() => {}), this.sync_seconds() * 1000);
			this.sync_now().catch(() => {});
		}

		sync_seconds() {
			return Math.max(parseInt(this.cfg.sync_seconds, 10) || 60, 15);
		}

		// Satu putaran sinkron + kabar hasilnya (on_status) untuk teguran di halaman Mailbox.
		async sync_now() {
			if (!this.home || !this.account || !this.folders.length) return 0;
			try {
				const changed = await this.sync();
				this.last_sync = Date.now();
				if (this.on_status) this.on_status(null);
				return changed;
			} catch (e) {
				if (this.on_status) this.on_status(e);
				throw e;
			}
		}

		// Batas bawah email yang disimpan di laptop (ISO UTC), atau null kalau semua disimpan.
		cutoff() {
			if (!this.days) return null;
			return new Date(Date.now() - this.days * 86400000).toISOString().replace(/\.\d+Z$/, "Z");
		}

		async sync_folder(folder) {
			const key = `delta|${folder.id}`;
			const since = this.cutoff();
			const first =
				`/me/mailFolders/${enc(folder.id)}/messages/delta?$select=${FIELDS}` +
				(since ? `&$filter=${encodeURIComponent(`receivedDateTime ge ${since}`)}` : "") +
				"&$orderby=receivedDateTime%20desc";
			// Titik lanjut hanya dipakai kalau dibuat dengan rentang hari yang sama. Rentang
			// diubah admin = mulai dari awal dengan batas baru (email yang sudah ada tidak
			// diunduh ulang, cuma dicocokkan).
			const saved = await this.kv_get(key);
			let link = (saved && saved.days === this.days && saved.link) || first;
			let restarted = false;
			let changed = 0;
			// Notifikasi hanya dari delta LANJUTAN di Kotak Masuk: sinkron awal (atau ulang dari
			// awal) membawa semua email lama rentang simpan, bukan email yang baru datang.
			this.collect = link !== first && folder.kind === "inbox";

			while (link) {
				let page;
				try {
					page = await this.graph(link, { prefer: `odata.maxpagesize=${PAGE}` });
				} catch (e) {
					// Token delta kedaluwarsa (lama tidak dibuka): ulang dari awal. Aman, karena
					// menerapkan perubahan yang sama dua kali hasilnya tetap sama.
					if (e.status === 410 && !restarted) {
						restarted = true;
						link = first;
						this.collect = false;
						continue;
					}
					throw e;
				}

				let here = 0;
				for (const m of page.value) here += await this.apply(folder, m, since);
				link = page["@odata.nextLink"] || null;
				await this.kv_set(key, { link: link || page["@odata.deltaLink"], days: this.days });

				changed += here;
				if (here && this.on_change) this.on_change();
				// Unduhan isi jalan sejak halaman pertama, tidak menunggu sinkron awal selesai.
				if (here) this.download_pending();
			}
			return changed;
		}

		async apply(folder, m, since = null) {
			const row = await this.row(m.id);

			// Delta tetap mengabarkan perubahan email lama (mis. ditandai dibaca di Outlook) walau
			// di luar filter tanggal; email di luar rentang simpan tidak ditambahkan ke laptop.
			if (!row && since && m.receivedDateTime && m.receivedDateTime < since) return 0;

			if (m["@removed"]) {
				// Dihapus ATAU dipindah keluar folder ini. Kalau barisnya sudah tercatat di folder
				// lain, folder tujuannya lebih dulu disinkron: jangan dihapus.
				if (!row || row.folder !== folder.id) return 0;
				if (row.path) await this.remove_file(row.path);
				await this.del_row(m.id);
				return 1;
			}

			const next = merge_row(row, folder, m);
			if (!row && this.collect && !next.seen) this.fresh.push(next);
			if (row && row.path && row.folder !== folder.id) {
				// Dipindah folder di Outlook: berkasnya ikut dipindah, tidak diunduh ulang.
				try {
					next.path = await this.file_path(next);
					await this.write_file(next.path, await this.read_file(row.path));
					await this.remove_file(row.path);
				} catch {
					delete next.path;
					next.pending = next.date || "";
				}
			}
			await this.put_row(next);
			return 1;
		}

		// Email baru di Kotak Masuk -> Notification Log milik user ini, jadi lonceng dan toast
		// (notification_badge.js) sama dengan Server mode. Server cuma menerima pengirim, subjek,
		// dan Message-ID untuk membukanya; isi email tetap di laptop. Yang lebih tua dari sehari
		// (mis. dipindah dari folder yang tidak disinkron) bukan email baru.
		async notify_fresh() {
			const recent = Date.now() - 86400000;
			const mails = (this.fresh || []).filter((r) => new Date(r.date).getTime() > recent).slice(0, 20);
			this.fresh = [];
			if (!mails.length) return;
			await frappe
				.xcall("erpnext_custom.outlook_addin.notify_local_mail", {
					mails: mails.map((r) => ({ sender: r.from_name || r.from_addr, subject: r.subject, message_id: r.imid })),
				})
				.catch((e) => console.warn("mailbox: new-mail notification failed", e));
		}

		download_pending() {
			return navigator.locks.request(
				`erp-mailbox-download|${this.mailbox}`,
				{ ifAvailable: true },
				async (lock) => {
					if (!lock) return;
					await this.migrate().catch((e) => console.warn("mailbox: encryption migration failed", e));
					const worker = async () => {
						for (let row; (row = await this.next_pending()); ) {
							// Gagal (mis. jaringan putus) = dilewati sampai halaman dibuka lagi,
							// bukan diulang terus-menerus.
							await this.download(row).catch((e) => console.warn("mailbox: download failed", row.id, e));
						}
					};
					await Promise.all(Array.from({ length: WORKERS }, worker));
					this.claimed.clear();
				}
			);
		}

		// Sekali per folder penyimpanan: salinan dari sebelum enkripsi (berkas .eml polos bersubjek
		// di namanya, indeks polos) dienkripsi di tempat tanpa unduh ulang. Baris dibaca ulang
		// tepat sebelum ditulis supaya perubahan sinkron yang berjalan bersamaan tidak tertimpa.
		async migrate() {
			if (await this.kv_get("sealed")) return;
			for (const stored of await done(this.store("messages").getAll())) {
				const plain_file = stored.path && stored.path[stored.path.length - 1].endsWith(".eml");
				if (stored.sec && !plain_file) continue;
				const row = await this.row(stored.id);
				if (!row) continue;
				if (plain_file) {
					try {
						const path = await this.file_path(row);
						await this.write_file(path, await this.read_file(row.path));
						await this.remove_file(row.path);
						row.path = path;
					} catch {
						delete row.path;
						row.pending = row.date || "";
					}
				}
				await this.put_row(row);
			}
			await this.kv_set("sealed", true);
		}

		// Baris belum berisi yang terbaru, dan belum dipegang pekerja lain.
		next_pending() {
			const selected = new Set(this.folders.map((f) => f.id));
			return new Promise((resolve, reject) => {
				const req = this.store("messages").index("pending").openCursor(null, "prev");
				req.onsuccess = () => {
					const cursor = req.result;
					if (!cursor) return resolve(null);
					const id = cursor.primaryKey;
					if (this.claimed.has(id) || !selected.has(cursor.value.folder)) {
						this.claimed.add(id);
						return cursor.continue();
					}
					this.claimed.add(id);
					resolve(cursor.value);
				};
				req.onerror = () => reject(req.error);
			});
		}

		async download(row) {
			let blob;
			try {
				blob = await this.graph(`/me/messages/${enc(row.id)}/$value`, { blob: true });
			} catch (e) {
				if (e.status !== 404) throw e;
				await this.del_row(row.id);
				return null;
			}
			const path = await this.file_path(row);
			await this.write_file(path, blob);

			const current = await this.row(row.id);
			if (!current) {
				// dihapus di Outlook selagi diunduh
				await this.remove_file(path);
				return null;
			}
			current.path = path;
			delete current.pending;
			await this.put_row(current);
			return current;
		}

		// Hapus dari laptop email yang sudah lewat rentang simpan (tetap ada di Microsoft).
		async prune() {
			const since = this.cutoff();
			if (!since) return 0;
			const dirs = new Set();
			let removed = 0;
			for (const folder of this.folders) {
				const old = await done(
					this.store("messages")
						.index("folder_date")
						.getAll(IDBKeyRange.bound([folder.id, ""], [folder.id, since], false, true))
				);
				for (const r of old) {
					if (r.path) {
						await this.remove_file(r.path);
						dirs.add(JSON.stringify(r.path.slice(0, -1)));
					}
					await this.del_row(r.id);
					removed++;
				}
			}
			// Folder bulan yang sudah kosong ikut dibuang, supaya folder laptop tetap rapi.
			for (const dir of dirs) await this.remove_if_empty(JSON.parse(dir));
			return removed;
		}

		async remove_if_empty(segments) {
			try {
				const parent = await this.dir_of(segments, false);
				const name = segments[segments.length - 1];
				const dir = await parent.getDirectoryHandle(name);
				for await (const _entry of dir.keys()) return;
				await parent.removeEntry(name);
			} catch (e) {
				if (e.name !== "NotFoundError") throw e;
			}
		}

		// ------------------------------------------------------------ baca

		async list({ folder, search, dates, start = 0, limit = 50 }) {
			const lo = dates ? new Date(`${dates[0]}T00:00:00`).toISOString() : "";
			const hi = dates ? new Date(`${dates[1]}T23:59:59.999`).toISOString() : "￿";
			const q = (search || "").toLowerCase();
			const range = IDBKeyRange.bound([folder, lo], [folder, hi]);
			const index = this.store("messages").index("folder_date");
			const rows = [];

			if (q) {
				// Subjek/pengirim terenkripsi: semua baris di rentang itu dibuka lalu disaring
				// (hasil dekripsi di-cache open_row, pencarian berikutnya cepat).
				for (const stored of (await done(index.getAll(range))).reverse()) {
					const r = await this.open_row(stored);
					if (matches(r, q)) rows.push(r);
					if (rows.length >= start + limit) break;
				}
			} else {
				// Kursor IndexedDB tidak boleh menunggu dekripsi: kumpulkan dulu, buka sesudahnya.
				const page = await new Promise((resolve, reject) => {
					const out = [];
					const req = index.openCursor(range, "prev");
					req.onsuccess = () => {
						const cursor = req.result;
						if (!cursor || out.length >= start + limit) return resolve(out);
						out.push(cursor.value);
						cursor.continue();
					};
					req.onerror = () => reject(req.error);
				});
				for (const stored of page) rows.push(await this.open_row(stored));
			}

			return rows.slice(start).map(list_row);
		}

		// Email yang lebih lama dari rentang simpan, dibaca langsung dari Microsoft (tidak
		// disimpan ke laptop). `next` = lanjutan dari panggilan sebelumnya.
		async older({ folder, search, dates, next }) {
			const since = this.cutoff();
			const lo = dates && new Date(`${dates[0]}T00:00:00`).toISOString();
			const hi = dates && new Date(`${dates[1]}T23:59:59.999`).toISOString();
			let url = next;
			if (!url) {
				const params = [`$select=${FIELDS}`, "$top=50"];
				if (search) {
					// $search Graph tidak bisa digabung $filter/$orderby: tanggal disaring di bawah.
					params.push(`$search=${encodeURIComponent(`"${search.replace(/"/g, "")}"`)}`);
				} else {
					const where = [`receivedDateTime lt ${since}`];
					if (dates) where.push(`receivedDateTime ge ${lo}`, `receivedDateTime le ${hi}`);
					params.push(`$filter=${encodeURIComponent(where.join(" and "))}`, "$orderby=receivedDateTime%20desc");
				}
				url = `/me/mailFolders/${enc(folder)}/messages?${params.join("&")}`;
			}

			const r = await this.graph(url);
			const rows = r.value
				.filter((m) => m.receivedDateTime < since && (!dates || (m.receivedDateTime >= lo && m.receivedDateTime <= hi)))
				.map((m) => list_row(merge_row(undefined, { id: folder }, m)));
			return { rows, next: r["@odata.nextLink"] || null };
		}

		unread(folder) {
			return done(this.store("messages").index("folder_seen").count(IDBKeyRange.only([folder, 0])));
		}

		// Satu email dalam bentuk yang sama dengan dokumen Communication (panel baca & komposer
		// halaman Mailbox dipakai apa adanya).
		async get(id) {
			let row = await this.row(id);
			let raw = null;
			if (row && row.path) raw = await this.read_file(row.path).catch(() => null);
			if (row && !raw) {
				// belum diunduh, atau berkasnya dihapus/dipindah dari luar
				row = await this.download(row);
				if (!row) throw new Error(__("This email was deleted in Outlook."));
				raw = await this.read_file(row.path);
			}
			// Di luar folder yang disinkron (mis. dibuka dari tab Email transaksi): baca langsung.
			if (!row) raw = await this.graph(`/me/messages/${enc(id)}/$value`, { blob: true });

			const { default: PostalMime } = await import(`${VENDOR}/postal-mime/postal-mime.js`);
			const mail = await PostalMime.parse(raw);

			for (const url of this.urls) URL.revokeObjectURL(url);
			this.urls = [];

			let html = mail.html || "";
			const attachments = [];
			for (const a of mail.attachments) {
				const blob = new Blob([a.content], { type: a.mimeType });
				const cid = (a.contentId || "").replace(/^<|>$/g, "");
				// Gambar di dalam badan email (cid:) jadi data URL: iframe baca ber-sandbox tidak
				// bisa memuat blob URL halaman ini.
				if (cid && html.includes(`cid:${cid}`)) {
					html = html.split(`cid:${cid}`).join(await data_url(blob));
					continue;
				}
				const url = URL.createObjectURL(blob);
				this.urls.push(url);
				attachments.push({ file_name: a.filename || __("attachment"), file_url: url, blob, download: 1, original: 1 });
			}

			const folder = row && this.folders.find((f) => f.id === row.folder);
			const sender = ((mail.from && mail.from.address) || "").toLowerCase();
			const sent = (folder && ["sentitems", "drafts"].includes(folder.kind)) || sender === this.mailbox;
			return {
				name: id,
				subject: mail.subject || (row && row.subject) || "",
				sender,
				sender_full_name: (mail.from && mail.from.name) || "",
				recipients: addresses_of(mail.to),
				cc: addresses_of(mail.cc),
				communication_date: to_local(row ? row.date : mail.date),
				content: html || null,
				text_content: mail.text || "",
				sent_or_received: sent ? "Sent" : "Received",
				seen: row ? row.seen : 1,
				has_attachment: attachments.length ? 1 : 0,
				message_id: strip_id(mail.messageId || (row && row.imid)),
				attachments,
			};
		}

		async mark_read(id) {
			await this.graph(`/me/messages/${enc(id)}`, { method: "PATCH", body: { isRead: true } });
			const row = await this.row(id);
			if (row) {
				row.seen = 1;
				await this.put_row(row);
			}
		}

		// Isi lengkap email (.eml polos): disimpan ke ERP saat ditautkan, dan tombol Download .eml.
		async eml(id) {
			const row = await this.row(id);
			return (
				(row && row.path && (await this.read_file(row.path).catch(() => null))) ||
				(await this.graph(`/me/messages/${enc(id)}/$value`, { blob: true }))
			);
		}

		async eml_b64(id) {
			return base64_of(await this.eml(id));
		}

		// Id Graph dari Message-ID (email yang dibuka dari tab Email transaksi / notifikasi).
		async find(message_id) {
			const mid = strip_id(message_id);
			if (!mid) return null;
			// indeks imid berisi hash Message-ID (put_row)
			const row = await done(this.store("messages").index("imid").get(await sha256(mid)));
			if (row) return row.id;
			const filter = encodeURIComponent(`internetMessageId eq '<${mid.replace(/'/g, "''")}>'`);
			const r = await this.graph(`/me/messages?$filter=${filter}&$select=id&$top=1`);
			return (r.value[0] && r.value[0].id) || null;
		}

		// ------------------------------------------------------------ kirim

		// mode: new | reply | reply-all | forward; source = id Graph email aslinya.
		// Dikirim sebagai draf dulu supaya balasan membawa header utas Outlook (createReply) dan
		// isi .eml-nya bisa ikut disimpan ke ERP kalau ditautkan ke transaksi.
		async send({ mode, source, to, cc, subject, html, files, want_eml }) {
			const action = { reply: "createReply", "reply-all": "createReplyAll", forward: "createForward" }[mode];
			const draft =
				action && source
					? await this.graph(`/me/messages/${enc(source)}/${action}`, { method: "POST", body: {} })
					: await this.graph("/me/messages", { method: "POST", body: {} });
			const at = `/me/messages/${enc(draft.id)}`;
			// Gambar signature/tempelan jadi lampiran inline (cid:), bukan data URL atau alamat
			// ERP: Gmail memblokir data URL, dan alamat ERP tidak terbuka dari luar kantor.
			const inline = await inline_images(html);

			const saved = await this.graph(at, {
				method: "PATCH",
				body: {
					subject,
					body: { contentType: "HTML", content: inline.html },
					toRecipients: recipients_of(to),
					ccRecipients: recipients_of(cc),
				},
			});

			if (action === "createForward") {
				// Lampiran surat asli ikut otomatis; yang dibuang user di komposer dihapus dari draf.
				const keep = files.filter((f) => f.original).map((f) => f.file_name);
				const r = await this.graph(`${at}/attachments?$select=id,name,isInline`);
				for (const a of r.value) {
					if (a.isInline) continue;
					const i = keep.indexOf(a.name);
					if (i >= 0) keep.splice(i, 1);
					else await this.graph(`${at}/attachments/${enc(a.id)}`, { method: "DELETE" });
				}
			}
			for (const f of files.filter((f) => !f.original)) await this.attach(at, f);
			for (const f of inline.files) await this.attach(at, f);

			const eml = want_eml ? await this.graph(`${at}/$value`, { blob: true }) : null;
			await this.graph(`${at}/send`, { method: "POST" });
			return {
				message_id: strip_id(saved.internetMessageId),
				eml_b64: eml && (await base64_of(eml)),
			};
		}

		// f.cid terisi = gambar inline yang dirujuk badan email lewat cid:.
		async attach(at, f) {
			const size = f.blob.size;
			const inline = f.cid ? { isInline: true, contentId: f.cid } : {};
			if (size <= SMALL_ATTACHMENT) {
				return this.graph(`${at}/attachments`, {
					method: "POST",
					body: {
						"@odata.type": "#microsoft.graph.fileAttachment",
						name: f.file_name,
						contentType: f.blob.type || "application/octet-stream",
						contentBytes: await base64_of(f.blob),
						...inline,
					},
				});
			}

			const session = await this.graph(`${at}/attachments/createUploadSession`, {
				method: "POST",
				body: { AttachmentItem: { attachmentType: "file", name: f.file_name, size, ...inline } },
			});
			for (let from = 0; from < size; from += CHUNK) {
				const to = Math.min(from + CHUNK, size);
				// uploadUrl sudah membawa izinnya sendiri; header Authorization justru ditolak.
				const r = await fetch(session.uploadUrl, {
					method: "PUT",
					headers: { "Content-Range": `bytes ${from}-${to - 1}/${size}` },
					body: f.blob.slice(from, to),
				});
				if (!r.ok) throw new Error(__("Failed to upload attachment {0} ({1})", [f.file_name, r.status]));
			}
		}

		// ------------------------------------------------------------ rule Outlook

		// Rule Outlook yang asli (Microsoft), bukan aturan buatan ERP: jalan di Microsoft walau
		// laptop mati, dan tampil juga di Outlook. Izinnya (MailboxSettings.ReadWrite) diminta
		// terpisah dari SCOPES, jadi sinkron tetap jalan walau admin belum menambahkannya.
		async rules() {
			const r = await this.graph("/me/mailFolders/inbox/messageRules", { scopes: RULE_SCOPES });
			return r.value.sort((a, b) => a.sequence - b.sequence);
		}

		save_rule(rule) {
			const at = "/me/mailFolders/inbox/messageRules";
			const { id, ...body } = rule;
			return id
				? this.graph(`${at}/${enc(id)}`, { method: "PATCH", body, scopes: RULE_SCOPES })
				: this.graph(at, { method: "POST", body, scopes: RULE_SCOPES });
		}

		delete_rule(id) {
			return this.graph(`/me/mailFolders/inbox/messageRules/${enc(id)}`, {
				method: "DELETE",
				scopes: RULE_SCOPES,
			});
		}

		// ------------------------------------------------------------ IndexedDB

		store(name, mode = "readonly") {
			return this.db.transaction(name, mode).objectStore(name);
		}
		kv_get(key) {
			return done(this.store("kv").get(key));
		}
		kv_set(key, value) {
			return done(this.store("kv", "readwrite").put(value, key));
		}
		async row(id) {
			return this.open_row(await done(this.store("messages").get(id)));
		}
		// Kolom SECRET_FIELDS disegel ke baris.sec; indeks imid menyimpan hash-nya.
		async put_row(row) {
			const stored = { ...row };
			const secret = {};
			for (const f of SECRET_FIELDS) {
				secret[f] = row[f];
				delete stored[f];
			}
			if (row.imid) stored.imid = await sha256(row.imid);
			stored.sec = await this.seal(new TextEncoder().encode(JSON.stringify(secret)));
			return done(this.store("messages", "readwrite").put(stored));
		}
		// Baris tersimpan -> baris utuh. Hasil dekripsi di-cache per IV (IV baru tiap baris ditulis
		// ulang), jadi daftar dan pencarian tidak mendekripsi baris yang sama berulang kali.
		async open_row(stored) {
			if (!stored || !stored.sec) return stored; // tidak ada / indeks polos lama (migrate)
			const tag = `${stored.id}|${hex(stored.sec.iv)}`;
			let secret = this.opened.get(tag);
			if (!secret) {
				secret = JSON.parse(new TextDecoder().decode(await this.unseal(stored.sec)));
				this.opened.set(tag, secret);
			}
			const { sec, ...rest } = stored;
			return { ...rest, ...secret };
		}
		del_row(id) {
			return done(this.store("messages", "readwrite").delete(id));
		}

		first_row(test) {
			return new Promise((resolve, reject) => {
				const req = this.store("messages").openCursor();
				req.onsuccess = () => {
					const cursor = req.result;
					if (!cursor) return resolve(null);
					if (test(cursor.value)) return resolve(cursor.value);
					cursor.continue();
				};
				req.onerror = () => reject(req.error);
			});
		}

		// fn(row) -> baris baru untuk disimpan, atau null kalau tidak berubah.
		each_row(fn) {
			return new Promise((resolve, reject) => {
				const req = this.store("messages", "readwrite").openCursor();
				req.onsuccess = () => {
					const cursor = req.result;
					if (!cursor) return resolve();
					const next = fn(cursor.value);
					if (next) cursor.update(next);
					cursor.continue();
				};
				req.onerror = () => reject(req.error);
			});
		}
	}

	// ---------------------------------------------------------------- fungsi murni

	// Baris indeks dari satu item delta. Item "updated" bisa membawa sebagian properti saja,
	// jadi yang tidak dikirim mempertahankan nilai lama.
	function merge_row(row, folder, m) {
		const next = row ? { ...row } : { id: m.id };
		next.folder = folder.id;
		if ("subject" in m) next.subject = m.subject || "";
		if ("from" in m) {
			const from = (m.from && m.from.emailAddress) || {};
			next.from_name = from.name || "";
			next.from_addr = (from.address || "").toLowerCase();
		}
		if ("toRecipients" in m) next.to = recipient_list(m.toRecipients);
		if ("ccRecipients" in m) next.cc = recipient_list(m.ccRecipients);
		if ("receivedDateTime" in m) next.date = m.receivedDateTime;
		if ("isRead" in m) next.seen = m.isRead ? 1 : 0;
		if ("hasAttachments" in m) next.has_att = m.hasAttachments ? 1 : 0;
		if ("bodyPreview" in m) next.preview = m.bodyPreview || "";
		if ("internetMessageId" in m) next.imid = strip_id(m.internetMessageId);
		if (next.seen === undefined) next.seen = 0;
		// Belum ada berkasnya: antre unduh. Nilainya tanggal supaya yang terbaru diunduh duluan.
		if (!next.path) next.pending = next.date || "";
		return next;
	}

	// Baris daftar dalam bentuk yang sama dengan get_list Communication di halaman Mailbox.
	function list_row(r) {
		return {
			name: r.id,
			subject: r.subject,
			sender: r.from_addr,
			sender_full_name: r.from_name,
			recipients: r.to,
			communication_date: to_local(r.date),
			seen: r.seen,
			has_attachment: r.has_att,
			text_content: r.preview,
		};
	}

	// Nama aman untuk folder/berkas Windows.
	function safe_name(name, max = 80) {
		let s = String(name == null ? "" : name)
			.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
			.replace(/\s+/g, " ")
			.trim()
			.slice(0, max)
			.replace(/[. ]+$/, "");
		if (!s) s = "_";
		if (/^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$/i.test(s)) s = `_${s}`;
		return s;
	}

	// Message-ID tanpa kurung sudut, sama dengan yang disimpan Frappe di Communication.
	function strip_id(id) {
		return String(id || "").trim().replace(/^<|>$/g, "").trim();
	}

	function recipient_list(list) {
		return (list || [])
			.map((r) => (r.emailAddress && r.emailAddress.address) || "")
			.filter(Boolean)
			.join(", ");
	}

	function recipients_of(text) {
		return String(text || "")
			.split(/[,;]/)
			.map((s) => s.trim())
			.filter(Boolean)
			.map((s) => ({ emailAddress: { address: ((s.match(/<([^>]+)>/) || [])[1] || s).trim() } }));
	}

	function addresses_of(list) {
		return (list || [])
			.flatMap((a) => (a.group ? a.group : [a]))
			.map((a) => a.address)
			.filter(Boolean)
			.join(", ");
	}

	function matches(r, q) {
		return [r.subject, r.from_name, r.from_addr, r.to, r.cc].some((v) => (v || "").toLowerCase().includes(q));
	}

	// ---------------------------------------------------------------- pembantu browser

	function open_db(name) {
		const req = indexedDB.open(name, 1);
		req.onupgradeneeded = () => {
			const db = req.result;
			const messages = db.createObjectStore("messages", { keyPath: "id" });
			messages.createIndex("folder_date", ["folder", "date"]);
			messages.createIndex("folder_seen", ["folder", "seen"]);
			messages.createIndex("imid", "imid");
			messages.createIndex("pending", "pending");
			db.createObjectStore("kv");
		};
		return done(req);
	}

	function done(req) {
		return new Promise((resolve, reject) => {
			req.onsuccess = () => resolve(req.result);
			req.onerror = () => reject(req.error);
		});
	}

	function to_local(iso) {
		return iso ? moment(iso).format("YYYY-MM-DD HH:mm:ss") : "";
	}

	function enc(id) {
		return encodeURIComponent(id);
	}

	function sleep(ms) {
		return new Promise((resolve) => setTimeout(resolve, ms));
	}

	async function sha1(text) {
		return hex(await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text)));
	}

	async function sha256(text) {
		return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
	}

	function hex(buf) {
		return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
	}

	// Berkas berawalan MAGIC dan cukup panjang untuk IV + tag.
	function is_sealed(buf) {
		if (buf.byteLength < MAGIC.length + 12 + 16) return false;
		const head = new Uint8Array(buf, 0, MAGIC.length);
		return MAGIC.every((b, i) => head[i] === b);
	}

	function data_url(blob) {
		return new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => resolve(reader.result);
			reader.onerror = () => reject(reader.error);
			reader.readAsDataURL(blob);
		});
	}

	async function base64_of(blob) {
		return (await data_url(blob)).split(",")[1] || "";
	}

	// Gambar di badan email yang ikut dikirim sebagai lampiran inline (cid:): data URL (tempelan,
	// kutipan email lama) dan berkas ERP sendiri (gambar signature). Gambar dari alamat internet
	// lain dibiarkan, dimuat penerima dari sumbernya.
	async function inline_images(html) {
		const doc = new DOMParser().parseFromString(html || "", "text/html");
		const files = [];
		const by_src = new Map();
		for (const img of doc.querySelectorAll("img[src]")) {
			const src = img.getAttribute("src");
			const url = new URL(src, location.origin);
			if (url.protocol !== "data:" && url.origin !== location.origin) continue;
			if (!by_src.has(src)) {
				let blob;
				try {
					blob = await (await fetch(url)).blob();
				} catch {
					continue; // gambar tidak bisa diambil: biarkan apa adanya
				}
				const n = files.length + 1;
				const ext = (blob.type.split("/")[1] || "png").replace(/[^a-z0-9].*$/i, "");
				const base = url.protocol === "data:" ? "" : decodeURIComponent(url.pathname.split("/").pop());
				const cid = `image${n}.${Date.now().toString(36)}@erp`;
				files.push({ file_name: base || `image${n}.${ext}`, blob, cid });
				by_src.set(src, cid);
			}
			img.setAttribute("src", `cid:${by_src.get(src)}`);
		}
		return { html: files.length ? doc.body.innerHTML : html, files };
	}

	function load_script(src) {
		return new Promise((resolve, reject) => {
			const script = document.createElement("script");
			script.src = src;
			script.onload = resolve;
			script.onerror = () => reject(new Error(`Gagal memuat ${src}`));
			document.head.appendChild(script);
		});
	}

	// ---------------------------------------------------------------- sinkron otomatis

	// Satu mesin per tab desk, dipakai bersama halaman Mailbox dan sinkron otomatis.
	let shared = null;
	LocalMail.shared = function () {
		if (!shared) {
			shared = frappe.xcall("erpnext_custom.outlook_addin.mailbox_config").then(async (cfg) => {
				// Local Mode mati / Client ID kosong
				if (!cfg || !cfg.client_id || !cfg.email) return null;
				const engine = new LocalMail(cfg);
				await engine.init();
				return engine;
			});
			// gagal (mis. jaringan putus): panggilan berikutnya mencoba lagi
			shared.catch(() => (shared = null));
		}
		return shared;
	};

	// Penanda "user ini sudah menghubungkan Mailbox laptop di browser ini" (dipasang halaman
	// Mailbox). Tanpa penanda, halaman desk lain tidak memuat MSAL sama sekali.
	function ready_key() {
		return `erp-mailbox-ready|${frappe.session.user}`;
	}
	LocalMail.mark_ready = function (on) {
		try {
			if (on) localStorage.setItem(ready_key(), "1");
			else localStorage.removeItem(ready_key());
		} catch {
			// penyimpanan browser diblokir: sinkron otomatis cuma jalan saat Mailbox dibuka
		}
	};
	function is_ready() {
		try {
			return localStorage.getItem(ready_key()) === "1";
		} catch {
			return false;
		}
	}

	// Berkas ini dimuat di semua halaman desk (hooks app_include_js): begitu desk siap, sinkron
	// otomatis mulai tanpa harus membuka Mailbox.
	if (typeof $ === "function" && typeof frappe === "object") {
		$(document).on("app_ready", () => {
			if (!is_ready()) return;
			LocalMail.shared().then(
				(engine) => engine && engine.start_auto_sync(),
				(e) => console.warn("mailbox: sinkron otomatis tidak jalan", e)
			);
		});
	}

	globalThis.LocalMail = LocalMail;
	// untuk test_mailbox_local.js (node)
	if (typeof module === "object" && module.exports) module.exports = { merge_row, safe_name, strip_id, recipients_of };
})();

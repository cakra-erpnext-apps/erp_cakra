// Aplikasi desktop ERP: jendela sendiri yang membuka ERP di server (bukan salinan ERP),
// hidup di tray seperti Outlook. Ditutup = sembunyi, jadi sinkron Local Mode
// (mailbox_local.js) dan polling notifikasi (notification_badge.js) tetap jalan, dan
// notifikasi baru muncul sebagai popup Windows atas nama aplikasi ini.
// Alamat server ditanam saat build (package.json "erpUrl", lihat README.md).
const { app, BrowserWindow, Tray, Menu, Notification, ipcMain, shell, session } = require("electron");
const { autoUpdater } = require("electron-updater");
const fs = require("fs");
const path = require("path");
const pkg = require("./package.json");

const ORIGIN = new URL(pkg.erpUrl).origin;
const HOME = `${ORIGIN}/desk/mailbox?folder=Inbox`;
const ICON = path.join(__dirname, "build", "icon.png");
// Popup login Microsoft (MSAL loginPopup di mailbox_local.js) harus tetap jendela anak
// supaya MSAL bisa membaca hasil redirect-nya; tautan luar lain dibuka di browser biasa.
const LOGIN_HOSTS = ["login.microsoftonline.com", "login.microsoft.com", "login.live.com"];
// Izin yang benar-benar dipakai halaman ERP; sisanya (mikrofon, notifikasi web, MIDI, dll.)
// ditolak, begitu juga semua izin untuk halaman/iframe dari asal lain.
//   fileSystem: folder penyimpanan email Local Mode   clipboard-sanitized-write: tombol salin
//   fullscreen: GPS Monitoring, penampil gambar        geolocation: absen Meeting CRM
//   media: kamera saja (ambil foto di upload berkas CRM), mikrofon tidak
const PERMISSIONS = new Set(["fileSystem", "clipboard-sanitized-write", "fullscreen", "geolocation", "media"]);
// Update otomatis dari server ERP sendiri (latest.yml + installer di /files, README.md).
const UPDATE_EVERY_MS = 6 * 3600 * 1000;
// Penanda "hidup lagi di tray": dipasang sebelum update terpasang sendiri, dibaca saat mulai.
const START_HIDDEN = path.join(app.getPath("userData"), "start-hidden");
const UPDATE_LOG = path.join(app.getPath("userData"), "update.log");
const STARTED_HIDDEN = fs.existsSync(START_HIDDEN);
// Tampilan per laptop (tombol Display di ERP, Ctrl +/-/0): ukuran = zoom seluruh halaman,
// huruf = hanya dari daftar font bawaan Windows ini (nilainya masuk ke CSS, jadi bukan teks bebas).
const DISPLAY_FILE = path.join(app.getPath("userData"), "display.json");
const ZOOMS = [0.8, 0.9, 1, 1.1, 1.25, 1.5];
const FONTS = ["Segoe UI", "Arial", "Calibri", "Tahoma", "Verdana", "Trebuchet MS", "Georgia", "Times New Roman"];
// Tombol Access on Device di browser membuka aplikasi lewat cakra-erp://open<path ERP>.
const SCHEME = "cakra-erp";

let win = null;
let tray = null;
let quitting = false;
// Notifikasi Windows yang tidak dipegang bisa dibuang GC sebelum diklik.
const shown = new Set();

function parse(url) {
	try {
		return new URL(url);
	} catch {
		return null;
	}
}

// Asal harus sama persis: awalan string saja meloloskan "http://localhost:8080.evil.com".
function is_ours(url) {
	const u = parse(url);
	return !!u && u.origin === ORIGIN;
}

// Aplikasi ini cuma untuk Mail: halaman ERP lain (transaksi yang ditautkan, menu Desktop,
// notifikasi dokumen, dll.) dibuka di browser biasa, bukan di jendela aplikasi.
function in_app(url) {
	const u = parse(url);
	if (!u || u.origin !== ORIGIN) return false;
	const p = u.pathname.replace(/\/+$/, "");
	return p === "/desk/mailbox" || p.startsWith("/desk/mailbox/") || ["/login", "/update-password"].includes(p);
}

// Halaman di server ini (desk, CRM, website); yang bukan cuma berkas, API, dan aset.
function is_page(url) {
	const u = parse(url);
	return !!u && u.origin === ORIGIN && !/^\/(files|private|api|assets)\//.test(u.pathname);
}

// Halaman ERP tujuan dari argumen cakra-erp://open/desk/...; hanya halaman Mail.
function deep_link(argv) {
	const u = parse((argv || []).find((a) => String(a).startsWith(`${SCHEME}://`)));
	if (!u) return null;
	const target = parse(ORIGIN + u.pathname + u.search);
	return target && in_app(target.href) ? target.href : null;
}

function allowed_popup(url) {
	if (url === "about:blank") return true;
	const u = parse(url);
	if (!u) return false;
	// berkas lampiran / unduhan boleh jendela anak; halaman desk lain ke browser
	if (u.origin === ORIGIN) return in_app(url) || !is_page(url);
	return LOGIN_HOSTS.includes(u.hostname);
}

function permitted(perm, url, details = {}) {
	if (!PERMISSIONS.has(perm) || !is_ours(url)) return false;
	if (perm !== "media") return true;
	const types = details.mediaTypes || (details.mediaType ? [details.mediaType] : []);
	return types.length > 0 && types.every((t) => t === "video");
}

// Tampil pertama kali = dimaksimalkan. Bukan di ready-to-show: maximize() ikut menampilkan
// jendela, padahal sesudah update otomatis jendela harus tetap di tray.
let first_show = true;

function show() {
	if (!win) return;
	if (first_show) {
		first_show = false;
		win.maximize();
	}
	if (win.isMinimized()) win.restore();
	win.show();
	win.focus();
}

function read_display() {
	let saved = {};
	try {
		saved = JSON.parse(fs.readFileSync(DISPLAY_FILE, "utf8"));
	} catch {
		// belum pernah diatur / berkas rusak: bawaan
	}
	return {
		zoom: ZOOMS.includes(saved.zoom) ? saved.zoom : 1,
		font: FONTS.includes(saved.font) ? saved.font : "",
	};
}

let display = read_display();
let font_css_key = null;

// Desk memakai var(--font-stack), CRM (frappe-ui) kelas .font-sans. Sengaja bukan selector *:
// ikon FontAwesome di desk ikut berganti huruf dan rusak.
function font_css(font) {
	const stack = `"${font}", "Segoe UI", sans-serif`;
	return `html:root { --font-stack: ${stack} !important; }
		body, .font-sans, input, textarea, select, button, .ql-editor { font-family: ${stack} !important; }`;
}

async function apply_display() {
	const wc = win.webContents;
	wc.setZoomFactor(display.zoom);
	if (font_css_key) await wc.removeInsertedCSS(font_css_key).catch(() => {});
	font_css_key = display.font ? await wc.insertCSS(font_css(display.font)) : null;
}

function set_display(next) {
	display = {
		zoom: ZOOMS.includes(next.zoom) ? next.zoom : display.zoom,
		font: next.font === "" || FONTS.includes(next.font) ? next.font : display.font,
	};
	fs.writeFileSync(DISPLAY_FILE, JSON.stringify(display));
	return apply_display();
}

function step_zoom(dir) {
	const i = ZOOMS.indexOf(display.zoom) + dir;
	if (i >= 0 && i < ZOOMS.length) set_display({ zoom: ZOOMS[i] });
}

function create_window() {
	win = new BrowserWindow({
		width: 1400,
		height: 900,
		show: false,
		icon: ICON,
		title: pkg.productName,
		autoHideMenuBar: true,
		webPreferences: {
			preload: path.join(__dirname, "preload.js"),
			// Jendela tersembunyi di tray tetap menjalankan timer sinkron dengan tempo normal.
			backgroundThrottling: false,
		},
	});
	win.once("ready-to-show", () => {
		// Baru hidup lagi sesudah update otomatis: tetap di tray seperti sebelum update.
		if (STARTED_HIDDEN) return fs.rmSync(START_HIDDEN, { force: true });
		show();
	});
	win.on("close", (e) => {
		if (quitting) return;
		e.preventDefault();
		win.hide();
	});

	win.webContents.setWindowOpenHandler(({ url }) => {
		if (allowed_popup(url)) return { action: "allow" };
		shell.openExternal(url);
		return { action: "deny" };
	});
	win.webContents.on("will-navigate", (e, url) => {
		if (in_app(url) || (is_ours(url) && !is_page(url))) return;
		e.preventDefault();
		// Sesudah login Frappe mengarah ke beranda desk: di aplikasi berarti kembali ke Mail.
		const path = (parse(url) || {}).pathname || "";
		if (is_ours(url) && /^\/(desk|app)?\/?$/.test(path)) win.loadURL(HOME);
		else shell.openExternal(url);
	});
	// Pindah halaman di dalam desk (frappe.set_route, pushState) tidak memicu will-navigate:
	// dicek di sini, halaman lain dibuka di browser dan aplikasi kembali ke Mail.
	win.webContents.on("did-navigate-in-page", (_e, url, main_frame) => {
		if (!main_frame || in_app(url) || !is_page(url)) return;
		shell.openExternal(url);
		const history = win.webContents.navigationHistory;
		if (history.canGoBack()) history.goBack();
		else win.loadURL(HOME);
	});

	// CSS sisipan hilang tiap halaman dimuat penuh; zoom dipasang ulang sekalian.
	win.webContents.on("did-finish-load", () => {
		font_css_key = null;
		apply_display();
	});

	win.loadURL(deep_link(process.argv) || HOME);
}

function create_tray() {
	tray = new Tray(ICON);
	tray.setToolTip(pkg.productName);
	tray.setContextMenu(
		Menu.buildFromTemplate([
			{ label: "Open", click: show },
			{ type: "separator" },
			{
				label: "Quit",
				click: () => {
					quitting = true;
					app.quit();
				},
			},
		])
	);
	tray.on("click", show);
}

// Cek saat mulai lalu tiap UPDATE_EVERY_MS. Update yang sudah terunduh dipasang saat jendela
// di tray (langsung, atau begitu jendela ditutup) lalu aplikasi hidup lagi tetap di tray, jadi
// user tidak terganggu. Keluar lewat tray Quit juga memasangnya (autoInstallOnAppQuit).
// Hanya lewat https: installer belum ditandatangani, jadi keasliannya bergantung pada TLS server.
function setup_updates() {
	const u = new URL(ORIGIN);
	if (!app.isPackaged || (u.protocol !== "https:" && u.hostname !== "localhost")) return;
	// Aplikasi terpasang tidak punya konsol: jejak update ditulis ke %APPDATA%\<nama>\update.log.
	// ponytail: berkas tidak dirotasi, cuma beberapa baris per 6 jam
	const log = (...a) => fs.appendFileSync(UPDATE_LOG, `${new Date().toISOString()} ${a.join(" ")}\n`);
	autoUpdater.logger = { info: log, warn: log, error: log, debug() {} };
	autoUpdater.setFeedURL({ provider: "generic", url: `${ORIGIN}/files/` });
	// Updater mencoba unduh sebagian dulu (blockmap, ~1 MB); kalau gagal cocok ia jatuh sendiri
	// ke unduh penuh (~110 MB). Dua-duanya teruji.
	autoUpdater.disableWebInstaller = true;
	autoUpdater.once("update-downloaded", () => {
		const install = () => {
			fs.writeFileSync(START_HIDDEN, "");
			autoUpdater.quitAndInstall(true, true);
		};
		// Baru dibuka user tapi jendelanya belum sempat tampil (update sering selesai terunduh
		// lebih dulu) = sedang dipakai juga: tunggu ditutup, jangan tiba-tiba hilang.
		const in_use = win.isVisible() || (first_show && !STARTED_HIDDEN);
		if (in_use) win.once("hide", install);
		else install();
	});
	const check = () => autoUpdater.checkForUpdates().catch(() => {});
	check();
	setInterval(check, UPDATE_EVERY_MS);
}

// Dipanggil notification_badge.js lewat preload (window.erpDesktop.notify).
// silent: ERP sudah memutar suara notifikasinya sendiri (ERPNext Custom Setting > Notification).
ipcMain.handle("display:get", () => ({ ...display, zooms: ZOOMS, fonts: FONTS }));
ipcMain.handle("display:set", (_e, next) => set_display(next || {}));

// Menu tersembunyi (Alt): pintasan zoom lewat set_display supaya tersimpan, bukan zoom bawaan.
function create_menu() {
	Menu.setApplicationMenu(
		Menu.buildFromTemplate([
			{
				label: "View",
				submenu: [
					{ label: "Zoom In", accelerator: "CmdOrCtrl+=", click: () => step_zoom(1) },
					{ label: "Zoom In", accelerator: "CmdOrCtrl+Plus", visible: false, click: () => step_zoom(1) },
					{ label: "Zoom Out", accelerator: "CmdOrCtrl+-", click: () => step_zoom(-1) },
					{ label: "Actual Size", accelerator: "CmdOrCtrl+0", click: () => set_display({ zoom: 1 }) },
					{ type: "separator" },
					{ role: "reload" },
					{ role: "toggleDevTools" },
				],
			},
		])
	);
}

ipcMain.on("notify", (_e, { title, body, link, silent }) => {
	if (!Notification.isSupported()) return;
	const n = new Notification({
		title: String(title || pkg.productName),
		body: String(body || ""),
		icon: ICON,
		silent: Boolean(silent),
	});
	shown.add(n);
	n.on("click", () => {
		show();
		if (link) win.webContents.send("open-link", String(link));
		shown.delete(n);
	});
	n.on("close", () => shown.delete(n));
	n.show();
});

if (!app.requestSingleInstanceLock()) {
	app.quit();
} else {
	// Dibuka lagi (ikon, Start Menu, atau cakra-erp:// dari browser) = jendela yang ada dimunculkan.
	app.on("second-instance", (_e, argv) => {
		show();
		const url = deep_link(argv);
		if (url) win.loadURL(url);
	});
	// Sama dengan build.appId di package.json; bagian "build" tidak ikut ke aplikasi terpasang.
	app.setAppUserModelId("com.cakraindo.erp");

	app.whenReady().then(() => {
		// Izin di PERMISSIONS untuk halaman ERP diberikan tanpa bertanya, sisanya ditolak.
		session.defaultSession.setPermissionRequestHandler((_wc, perm, cb, details) =>
			cb(permitted(perm, details.requestingUrl, details))
		);
		session.defaultSession.setPermissionCheckHandler((_wc, perm, origin, details) =>
			permitted(perm, origin, details)
		);

		// Terbuka sendiri saat login Windows. User yang mematikannya di Task Manager tetap
		// mati: Windows menyimpan pilihan itu terpisah dari entri ini.
		if (app.isPackaged) {
			app.setLoginItemSettings({ openAtLogin: true });
			app.setAsDefaultProtocolClient(SCHEME);
		}

		create_menu();
		create_window();
		create_tray();
		setup_updates();
	});

	app.on("before-quit", () => {
		quitting = true;
	});
}

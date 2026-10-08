// Pojok kiri bawah sidebar desk: blok avatar + nama + email user bawaan frappe
// (sidebar.html, .dropdown-navbar-user) fungsinya cuma membuka form User sendiri.
// Diganti dua tombol pintas: Mail (halaman mailbox) dan Assistant (Assistant Center).
// Markup meniru sidebar_item.html supaya hover, ikon & tooltip saat collapse ikut gaya bawaan.
// Tombol hanya muncul kalau user boleh membuka halamannya (frappe.boot.page_info).
// Plus tombol Access on Device di menu Mail, dan tombol Display khusus aplikasi desktop
// (lihat bawah).
(function () {
	const BUTTONS = [
		{ label: "Mail", icon: "mail", page: "mailbox" },
		{ label: "Assistant", icon: "bot", page: "assistant-center" },
	];

	const proto = frappe.ui.Sidebar.prototype;
	const original = proto.make_dom;

	proto.make_dom = function () {
		original.apply(this, arguments);
		const allowed = frappe.boot.page_info || {};
		// Aplikasi desktop cuma untuk Mail (desktop/main.js membuka halaman lain di browser).
		const html = BUTTONS.filter((b) => allowed[b.page] && (!window.erpDesktop || b.page === "mailbox"))
			.map((b) => {
				const label = __(b.label);
				return `<div class="sidebar-item-container" title="${label}"
						data-toggle="tooltip" data-placement="right">
					<div class="standard-sidebar-item">
						<a href="/desk/${b.page}" class="item-anchor">
							<span class="sidebar-item-icon text-ink-gray-7">
								${frappe.utils.icon(b.icon, "sm", "", "", "text-ink-gray-7 current-color", true)}
							</span>
							<span class="sidebar-item-label">${label}</span>
						</a>
					</div>
				</div>`;
			})
			.join("");
		const $footer = $(`<div class="mt-3">${html}</div>`);
		this.wrapper.find(".body-sidebar-bottom .dropdown-navbar-user").replaceWith($footer);
		// Tombol khusus aplikasi desktop; aplikasi versi lama yang belum punya fungsinya dilewati.
		const app_button = (label, icon, action) =>
			$(`<div class="sidebar-item-container" title="${label}" data-toggle="tooltip" data-placement="right">
					<div class="standard-sidebar-item">
						<a class="item-anchor" href="#">
							<span class="sidebar-item-icon text-ink-gray-7">
								${frappe.utils.icon(icon, "sm", "", "", "text-ink-gray-7 current-color", true)}
							</span>
							<span class="sidebar-item-label">${label}</span>
						</a>
					</div>
				</div>`)
				.on("click", (e) => {
					e.preventDefault();
					action();
				})
				.appendTo($footer);
		if (window.erpDesktop && window.erpDesktop.getDisplay) app_button(__("Display"), "type", display_dialog);
		// Alamat server ERP aplikasi ini (halaman Server di desktop/main.js).
		if (window.erpDesktop && window.erpDesktop.openServer) {
			app_button(__("Server"), "server", () => window.erpDesktop.openServer());
		}
	};

	// Aplikasi desktop khusus Mail: pindah ke halaman lain (chip transaksi, link sidebar, notifikasi)
	// dibuka di browser SEBELUM route berganti, jadi transaksinya tidak ikut terbuka di aplikasi.
	// window.open halaman ERP diteruskan desktop/main.js ke browser biasa.
	if (window.erpDesktop && frappe.router) {
		const push_state = frappe.router.push_state;
		frappe.router.push_state = function (path, query_params = "") {
			if (!/^\/desk\/mailbox(\/|$)/.test(path)) {
				window.open(path + query_params, "_blank");
				return;
			}
			return push_state.apply(this, arguments);
		};

		// Jaring pengaman kalau jendela aplikasi tetap sampai di halaman lain (jalur yang tidak lewat
		// push_state): tombol kembali ke Mail, hanya tampil di luar halaman Mailbox.
		$(() => {
			const $back = $(
				`<button class="btn btn-primary btn-sm erp-desktop-back">${frappe.utils.icon("arrow-left", "sm")} ${__(
					"Back to Mail"
				)}</button>`
			)
				.css({ position: "fixed", right: 24, bottom: 24, zIndex: 1040, display: "none" })
				.on("click", () => frappe.set_route("mailbox"))
				.appendTo(document.body);
			const toggle = () => $back.toggle(!/^\/desk\/mailbox(\/|$)/.test(location.pathname));
			frappe.router.on("change", toggle);
			toggle();
		});
	}

	// Menu judul sidebar di aplikasi desktop: tanpa Desktop, Workspaces, Website (pintu ke modul
	// lain). add_navbar_items dipanggil konstruktor sebelum menu digambar.
	const header = frappe.ui.SidebarHeader && frappe.ui.SidebarHeader.prototype;
	if (window.erpDesktop && header) {
		const add_navbar_items = header.add_navbar_items;
		header.add_navbar_items = function () {
			const items = this.dropdown_items.filter((i) => !["desktop", "workspaces", "website"].includes(i.name));
			// garis pemisah yang jadi paling atas ikut dibuang
			while (items.length && items[0].is_divider) items.shift();
			this.dropdown_items = items;
			return add_navbar_items.apply(this, arguments);
		};
	}

	// Ukuran teks dan jenis huruf aplikasi desktop, tersimpan per laptop (desktop/main.js).
	// Tiap pilihan langsung diterapkan supaya user melihat hasilnya sebelum menutup dialog.
	async function display_dialog() {
		const cur = await window.erpDesktop.getDisplay();
		const pct = (z) => `${Math.round(z * 100)}%`;
		const DEFAULT_FONT = __("Default");
		const d = new frappe.ui.Dialog({
			title: __("Display"),
			fields: [
				{
					fieldname: "zoom",
					fieldtype: "Select",
					label: __("Text Size"),
					options: cur.zooms.map(pct).join("\n"),
					default: pct(cur.zoom),
					change: () => apply(),
				},
				{
					fieldname: "font",
					fieldtype: "Select",
					label: __("Font"),
					options: [DEFAULT_FONT, ...cur.fonts].join("\n"),
					default: cur.font || DEFAULT_FONT,
					change: () => apply(),
				},
				{
					fieldtype: "HTML",
					options: `<div class="text-muted small">${__(
						"Saved on this device only. Shortcuts: Ctrl + and Ctrl - change the text size, Ctrl 0 resets it."
					)}</div>`,
				},
			],
			primary_action_label: __("Done"),
			primary_action: () => d.hide(),
			secondary_action_label: __("Reset"),
			secondary_action: () => {
				d.set_value("zoom", pct(1));
				d.set_value("font", DEFAULT_FONT);
			},
		});
		function apply() {
			const v = d.get_values(true) || {};
			const zoom = cur.zooms.find((z) => pct(z) === v.zoom);
			window.erpDesktop.setDisplay({ zoom, font: v.font === DEFAULT_FONT ? "" : v.font });
		}
		d.show();
	}

	// Menu Mail: tombol aplikasi desktop (erpnext_custom/desktop, installer ditaruh di /files
	// site ini saat deploy). Klik pertama di browser ini = unduh installer; sesudahnya = pilihan
	// buka aplikasinya (cakra-erp://, didaftarkan aplikasi ke Windows) atau unduh lagi.
	// Disembunyikan kalau sudah di dalam aplikasinya.
	const INSTALLER = "/files/erp-desktop-setup.exe";
	const SCHEME = "cakra-erp";
	const make_sidebar = proto.make_sidebar;
	proto.make_sidebar = function () {
		make_sidebar.apply(this, arguments);
		const title = String(this.sidebar_title || "").toLowerCase();
		if (title !== "mail" || window.erpDesktop || this.editor.edit_mode) return;
		// standard: tanpa ini TypeLink.make() membuang item yang tidak punya link, lalu
		// konstruktor TypeButton error di wrapper kosong dan tombolnya tidak pernah tampil.
		this.add_item(this.$items_container, {
			standard: true,
			label: __("Access on Device"),
			icon: "download",
			type: "Button",
			onClick: access_desktop,
		});
	};

	// Per browser, bukan per user: yang ditanyakan "sudah terpasang di laptop ini?".
	// Salah (aplikasinya sudah dihapus) cukup diatasi tombol Download Again.
	function installed(value) {
		const key = "erp-desktop-installed";
		try {
			if (value) localStorage.setItem(key, "1");
			return localStorage.getItem(key) === "1";
		} catch {
			return false;
		}
	}

	function access_desktop() {
		if (!navigator.userAgent.includes("Windows")) {
			return frappe.msgprint(__("The desktop app is available for Windows only."));
		}
		if (!installed()) return download();
		const d = new frappe.ui.Dialog({
			title: __("Access on Device"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__(
						"The desktop app is already installed on this device. Open it on this page, or download the installer again if it was removed."
					)}</p>`,
				},
			],
			primary_action_label: __("Open App"),
			primary_action() {
				d.hide();
				window.location.href = `${SCHEME}://open${location.pathname}${location.search}`;
			},
			secondary_action_label: __("Download Again"),
			secondary_action() {
				d.hide();
				download();
			},
		});
		d.show();
	}

	// Installer terbaru = yang ditunjuk latest.yml (ERPNext Custom Setting > Desktop App menyimpannya
	// di /files/desktop/<versi>/); server lama yang belum pernah mengunggah lewat situ = INSTALLER.
	async function installer_url() {
		const yml = await fetch("/files/latest.yml", { cache: "no-store" })
			.then((r) => (r.ok ? r.text() : ""))
			.catch(() => "");
		const m = yml.match(/^path:\s*['"]?([^'"\s]+)/m);
		return m ? `/files/${m[1]}` : INSTALLER;
	}

	async function download() {
		const url = await installer_url();
		const r = await fetch(url, { method: "HEAD" }).catch(() => null);
		if (!r || !r.ok) {
			return frappe.msgprint(__("The desktop app installer is not available on this server yet."));
		}
		window.location.href = url;
		installed(true);
		frappe.msgprint({
			title: __("Access on Device"),
			message: __(
				"Open the downloaded file to install. If Windows shows <b>Windows protected your PC</b>, click <b>More info</b> then <b>Run anyway</b>. The app opens by itself every time you sign in to Windows, and keeps running in the tray when its window is closed."
			),
		});
	}
})();

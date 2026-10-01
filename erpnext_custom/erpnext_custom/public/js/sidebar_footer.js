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
		const html = BUTTONS.filter((b) => allowed[b.page])
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
		// Aplikasi versi lama belum punya getDisplay: tombolnya tidak dipasang.
		if (window.erpDesktop && window.erpDesktop.getDisplay) {
			const label = __("Display");
			$(`<div class="sidebar-item-container" title="${label}" data-toggle="tooltip" data-placement="right">
					<div class="standard-sidebar-item">
						<a class="item-anchor" href="#">
							<span class="sidebar-item-icon text-ink-gray-7">
								${frappe.utils.icon("type", "sm", "", "", "text-ink-gray-7 current-color", true)}
							</span>
							<span class="sidebar-item-label">${label}</span>
						</a>
					</div>
				</div>`)
				.on("click", (e) => {
					e.preventDefault();
					display_dialog();
				})
				.appendTo($footer);
		}
	};

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

	async function download() {
		const r = await fetch(INSTALLER, { method: "HEAD" }).catch(() => null);
		if (!r || !r.ok) {
			return frappe.msgprint(__("The desktop app installer is not available on this server yet."));
		}
		window.location.href = INSTALLER;
		installed(true);
		frappe.msgprint({
			title: __("Access on Device"),
			message: __(
				"Open the downloaded file to install. If Windows shows <b>Windows protected your PC</b>, click <b>More info</b> then <b>Run anyway</b>. The app opens by itself every time you sign in to Windows, and keeps running in the tray when its window is closed."
			),
		});
	}
})();

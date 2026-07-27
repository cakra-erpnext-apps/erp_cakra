// Angka jumlah notifikasi BELUM DIBACA di ikon bel sidebar desk, plus toast pojok
// kanan atas saat notifikasi baru masuk.
//
// Kenapa perlu ditambal: frappe sudah punya CSS penandanya
// (public/scss/desk/notification.scss -> `.sidebar-notification .sidebar-item-icon.indicator`),
// tapi notifications.js mencarinya lewat `this.parent.find(".notifications-icon")` — elemen itu
// milik navbar LAMA dan tidak ada di sidebar baru, jadi `toggle_notification_icon()` selalu
// mengoper ke jQuery kosong dan penandanya tidak pernah muncul.
//
// KENAPA POLLING, BUKAN REALTIME: dua percobaan lewat event gagal senyap —
//   1. `frappe.realtime.on("notification")` membuang listener tanpa bersuara kalau
//      `this.socket` belum terbentuk (socketio_client.js baris 12-15), dan saat `app_ready`
//      socket-nya sering belum jadi;
//   2. membungkus `frappe.ui.Notifications.prototype.update_dropdown` juga tidak memicu apa pun.
// Polling menghapus seluruh kelas kegagalan itu: angka DAN toast tetap jalan walau socket mati.
// Harganya: notifikasi baru tampil paling lama POLL_MS setelah masuk.
//
// ponytail: polling 10 detik, pindah ke event kalau ternyata realtime-nya bisa diandalkan
//
// Tes manual dari console browser: cmi_notif_test()
$(document).on("app_ready", function () {
	if (frappe.session.user === "Guest") return;

	const ITEM = ".sidebar-notification .item-anchor";
	const POLL_MS = 10000;
	const TOAST_MS = 5000;

	$("<style>")
		.text(
			`${ITEM} { position: relative; }
			.cmi-notif-count {
				position: absolute; top: 3px; right: 4px;
				min-width: 16px; height: 16px; padding: 0 4px;
				border-radius: 8px; background: var(--red-500, #e24c4c); color: #fff;
				font-size: 10px; line-height: 16px; text-align: center; font-weight: 600;
			}
			#cmi-toast-container {
				position: fixed; top: 16px; right: 16px; z-index: 2000;
				display: flex; flex-direction: column; gap: 8px;
				max-width: 360px; pointer-events: none;
			}
			.cmi-toast {
				pointer-events: auto; cursor: pointer;
				background: var(--fg-color, #fff); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #e2e6e9);
				border-left: 3px solid var(--blue-500, #2490ef);
				border-radius: 8px; padding: 10px 12px;
				box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16);
				font-size: 12px; line-height: 1.5;
				opacity: 0; transform: translateX(12px);
				transition: opacity 0.2s ease, transform 0.2s ease;
			}
			.cmi-toast.show { opacity: 1; transform: none; }
			.cmi-toast-doc { font-weight: 600; margin-top: 2px; }
			.cmi-toast-hint { color: var(--text-muted, #7c7c7c); margin-top: 2px; }`
		)
		.appendTo(document.head);

	// Toast sendiri, BUKAN frappe.show_alert: build ini setengah bermigrasi UI
	// (lihat catatan ikon bel di atas), jadi jangan bergantung pada wadah/ikon Frappe.
	function show_toast(html, href) {
		let $c = $("#cmi-toast-container");
		if (!$c.length) $c = $('<div id="cmi-toast-container">').appendTo("body");
		const $t = $('<div class="cmi-toast">').html(html).appendTo($c);
		requestAnimationFrame(() => $t.addClass("show"));
		const kill = () => {
			$t.removeClass("show");
			setTimeout(() => $t.remove(), 250);
		};
		// diklik -> buka dokumennya DAN toast langsung hilang
		$t.on("click", () => {
			if (href) frappe.set_route(href);
			kill();
		});
		setTimeout(kill, TOAST_MS);
	}

	// "Mention" -> mention, "Assignment" -> assign; tipe lain dipakai apa adanya (huruf kecil).
	const TYPE_LABEL = { Mention: "mention", Assignment: "assign", Share: "share", Alert: "notifikasi" };

	// Nama saja, bukan email. frappe.boot.user_info biasanya sudah memuat user yang
	// terlibat; kalau tidak, dipakai bagian depan emailnya — tanpa panggilan server tambahan.
	function short_name(uid) {
		if (!uid) return "sistem";
		let n = "";
		try {
			const info = frappe.user_info ? frappe.user_info(uid) : null;
			n = (info && (info.fullname || info.full_name)) || "";
		} catch (e) {
			n = "";
		}
		if (!n || n === uid) n = String(uid).split("@")[0];
		return n;
	}

	function toast_html(row) {
		const label = TYPE_LABEL[row.type] || String(row.type || "notifikasi").toLowerCase();
		const who = frappe.utils.escape_html(short_name(row.from_user));
		const no = row.document_name ? frappe.utils.escape_html(row.document_name) : "";
		return (
			`<div>Anda mendapatkan <strong>${label}</strong> dari <strong>${who}</strong></div>` +
			(no ? `<div class="cmi-toast-doc">${no}</div>` : "") +
			`<div class="cmi-toast-hint">Silahkan klik notifikasi ini</div>`
		);
	}

	// null = belum pernah dihitung; dipakai supaya tumpukan unread yang SUDAH ada
	// saat halaman dibuka tidak ikut memunculkan toast.
	let last = null;
	let busy = false;

	function paint(n) {
		const $item = $(ITEM).first();
		if (!$item.length) return;
		$item.find(".cmi-notif-count").remove();
		if (n > 0) $item.append(`<span class="cmi-notif-count">${n > 99 ? "99+" : n}</span>`);
	}

	function toast() {
		return frappe.db
			.get_list("Notification Log", {
				filters: { read: 0 },
				fields: ["type", "from_user", "document_type", "document_name"],
				order_by: "creation desc",
				limit: 1,
			})
			.then((rows) => {
				const r = rows && rows[0];
				if (!r) return;
				const href =
					r.document_type && r.document_name
						? frappe.utils.get_form_link(r.document_type, r.document_name)
						: null;
				show_toast(toast_html(r), href);
			})
			.catch((e) => console.error("[cmi] toast gagal ambil notifikasi", e));
	}

	function tick() {
		if (busy) return;
		busy = true;
		frappe.db
			.count("Notification Log", { filters: { read: 0 } })
			.then((n) => {
				paint(n);
				if (last !== null && n > last) toast();
				last = n;
			})
			.catch((e) => console.error("[cmi] hitung unread gagal", e))
			.finally(() => {
				busy = false;
			});
	}

	window.cmi_notif_test = toast;
	// tes tampilan murni, tanpa panggilan server sama sekali
	window.cmi_toast_test = () =>
		show_toast(
			toast_html({ type: "Mention", from_user: frappe.session.user, document_name: "TES/0001" }),
			null
		);

	// Sidebar dibangun belakangan; angka baru bisa ditempel setelah elemennya ada.
	// Polling tetap dimulai sekarang supaya baseline `last` langsung terisi.
	let tries = 0;
	(function wait_for_sidebar() {
		if ($(ITEM).length || tries++ >= 20) {
			if (!$(ITEM).length) console.warn("[cmi] item bel sidebar tidak ketemu, angka tidak dipasang");
			return;
		}
		setTimeout(wait_for_sidebar, 500);
	})();

	tick();
	setInterval(() => {
		if (!document.hidden) tick();
	}, POLL_MS);
	// balik ke tab -> jangan menunggu sisa interval
	document.addEventListener("visibilitychange", () => {
		if (!document.hidden) tick();
	});

	console.log("[cmi] notifikasi: angka + toast aktif (polling " + POLL_MS / 1000 + "s)");
});

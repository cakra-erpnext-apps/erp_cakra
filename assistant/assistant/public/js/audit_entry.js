// Pintu masuk halaman Laporan Saya (page/laporan_saya) untuk semua user desk: item di sidebar,
// tepat di bawah Notification, dengan angka temuan yang menunggu keputusan user itu.
// Sidebar digambar ulang tiap pindah workspace, jadi itemnya dipasang ulang tiap ganti route
// dan tiap tick. Angka diambil dari assistant.assistant.audit.my_count.
//
// ponytail: polling 60 detik, cukup karena laporan berubah paling cepat tiap 15 menit
$(document).on("app_ready", function () {
	if (frappe.session.user === "Guest") return;
	const POLL_MS = 60000;
	let count = 0;

	$("<style>")
		.text(`.cmi-audit-entry .item-anchor { position: relative; }`)
		.appendTo(document.head);

	function open_report(e) {
		e.preventDefault();
		frappe.set_route("laporan-saya");
	}

	function ensure() {
		const $notif = $(".sidebar-notification").first();
		if (!$notif.length) return;
		let $item = $(".cmi-audit-entry");
		if (!$item.length) {
			$item = $(`<div class="cmi-audit-entry" title="${__("Laporan Saya")}">
				<div class="standard-sidebar-item">
					<a class="item-anchor" href="/app/laporan-saya">
						<span class="sidebar-item-icon text-ink-gray-7">
							<svg class="icon text-ink-gray-7 current-color icon-sm" stroke="currentColor" aria-hidden="true"><use href="#icon-clipboard-check"></use></svg>
						</span>
						<span class="sidebar-item-label">${__("Laporan Saya")}</span>
					</a>
				</div>
			</div>`);
			$item.find("a").on("click", open_report);
			$notif.after($item);
		}
		const $a = $item.find(".item-anchor");
		$a.find(".cmi-notif-count").remove();
		// kelas angka sama dengan lonceng Notification (gayanya dari notification_badge.js)
		if (count > 0) $a.append(`<span class="cmi-notif-count">${count > 99 ? "99+" : count}</span>`);
	}

	function tick() {
		frappe
			.xcall("assistant.assistant.audit.my_count")
			.then((n) => {
				count = n || 0;
				ensure();
			})
			.catch(() => ensure());
	}

	frappe.router.on("change", () => setTimeout(ensure, 300));
	frappe.realtime.on("orchestrator_update", tick);
	setInterval(tick, POLL_MS);
	tick();
});

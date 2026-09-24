// Pojok kiri bawah sidebar desk: blok avatar + nama + email user bawaan frappe
// (sidebar.html, .dropdown-navbar-user) fungsinya cuma membuka form User sendiri.
// Diganti dua tombol pintas: Mail (halaman mailbox) dan Assistant (Assistant Center).
// Markup meniru sidebar_item.html supaya hover, ikon & tooltip saat collapse ikut gaya bawaan.
// Tombol hanya muncul kalau user boleh membuka halamannya (frappe.boot.page_info).
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
		this.wrapper
			.find(".body-sidebar-bottom .dropdown-navbar-user")
			.replaceWith(`<div class="mt-3">${html}</div>`);
	};
})();

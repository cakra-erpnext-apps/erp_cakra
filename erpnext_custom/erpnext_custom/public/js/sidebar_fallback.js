// Sidebar desk kadang kosong (putih polos) waktu halaman dibuka langsung / di-refresh,
// contoh: /desk/payment-entry/PV%2F0001%2FCMI%2FIX%2F26
//
// Biangnya frappe/public/js/frappe/ui/sidebar/sidebar.js -> set_workspace_sidebar():
// kalau satu link ada di LEBIH DARI SATU Workspace Sidebar (Payment Entry ada di
// "Finance" dan "Payments"), frappe hanya mau memilih kandidat yang kebetulan sama
// dengan workspace default modulnya (Accounts -> "Invoicing"). "Invoicing" bukan
// salah satu kandidat, jadi setup() TIDAK dipanggil sama sekali. Dan karena desk.js
// tidak pernah memanggil setup() saat start, wadah sidebar tinggal kosong.
// Kalau pindah halaman dari dalam app sidebar lama tetap terpasang — itu sebabnya
// bug ini terasa "kadang-kadang".
//
// Per hari ini 61 dari 108 link ganda di site ini kena; jadi ditambal global di sini,
// bukan dengan membuang menu ganda satu per satu (menu ganda itu memang disengaja).
//
// Tambalan: sesudah frappe selesai, kalau sidebar masih kosong, pilih sendiri dari
// daftar kandidat yang sudah dikumpulkan frappe (this.preferred_sidebars).
(function () {
	const proto = frappe.ui.Sidebar.prototype;
	const original = proto.set_workspace_sidebar;

	// Utamakan menu desk kita sendiri (Desktop Icon top-level & tidak disembunyikan)
	// daripada menu bawaan yang sudah dikubur di folder "Default".
	function pick(candidates) {
		const icons = frappe.boot.desktop_icons || [];
		const mine = candidates.filter((label) =>
			icons.some((i) => i.label === label && !i.parent_icon && !i.hidden)
		);
		return (mine.length ? mine : candidates)[0];
	}

	proto.set_workspace_sidebar = function (router) {
		original.call(this, router);
		if (this.workspace_sidebar_items && this.workspace_sidebar_items.length) return;
		const fallback = pick(this.preferred_sidebars || []);
		if (fallback) this.setup(fallback);
	};
})();

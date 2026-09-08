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
// Tambalan: sesudah frappe selesai, kalau sidebar yang tampil BUKAN salah satu kandidat
// (termasuk saat wadahnya kosong), pilih sendiri dari daftar kandidat yang sudah
// dikumpulkan frappe (this.preferred_sidebars).
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
		// Kosongkan dulu: pada jalur route panjang-2 ("Workspaces/Accounting") frappe
		// memanggil setup() lalu return TANPA memperbarui preferred_sidebars, jadi nilai
		// sisa route sebelumnya akan menyesatkan pemilihan di bawah.
		this.preferred_sidebars = [];
		original.call(this, router);

		const candidates = this.preferred_sidebars || [];
		if (!candidates.length) return;
		// Sidebar yang sedang tampil sudah salah satu kandidat -> jangan diganggu.
		if (this.sidebar_title && candidates.includes(this.sidebar_title)) return;

		// Sampai sini frappe memang GAGAL memilih: kandidatnya lebih dari satu dan tidak
		// ada yang sama dengan workspace default modulnya, jadi setup() tak pernah
		// dipanggil. Akibatnya bukan cuma sidebar kosong — kalau sebelumnya ada sidebar
		// lain, sidebar itu yang bertahan dan menu yang diklik TIDAK PERNAH terbuka
		// (mis. menu Accounting: link pertamanya Journal Entry, ada di sidebar
		// "Accounting" dan "Payments", sedangkan workspace default modul Accounts =
		// "Invoicing" yang bukan keduanya).
		const fallback = pick(candidates);
		if (fallback) this.setup(fallback);
	};
})();

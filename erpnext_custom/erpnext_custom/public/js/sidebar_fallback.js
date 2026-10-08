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

	// Menu desk kita = punya Desktop Icon top-level & tidak disembunyikan. Menu bawaan
	// yang dikubur di folder "Default" (Payments, Stock) TIDAK lolos, begitu juga sidebar
	// turunan MODUL yang dibikin frappe otomatis (mis. "FICO") -- yang itu tidak punya
	// Desktop Icon sama sekali, jadi user tak pernah bisa memilihnya dengan sengaja.
	function is_mine(label) {
		return (frappe.boot.desktop_icons || []).some(
			(i) => i.label === label && !i.parent_icon && !i.hidden
		);
	}

	// Menu terakhir yang benar-benar dibuka user, disimpan per-browser. Tanpa ini,
	// refresh di halaman yang dipakai beberapa menu (Pending Cash ada di Finance DAN
	// Accounting) mendarat di menu pertama menurut urutan boot -- tetap terasa "menunya
	// berganti sendiri". localStorage bisa melempar (private mode), jadi dijaga.
	const LAST = "cmi:last_sidebar";

	function remember(label) {
		try {
			localStorage.setItem(LAST, label);
		} catch (e) {
			/* penyimpanan diblokir -> cukup tanpa ingatan */
		}
	}

	function last_used() {
		try {
			return localStorage.getItem(LAST);
		} catch (e) {
			return null;
		}
	}

	// Menu panduan yang memuat ulang doctype milik menu lain (Migration memuat Customer,
	// Item, Account, ...). Hanya dipilih kalau memang menu terakhir yang dibuka; selain
	// itu doctype-nya pulang ke menu kerjanya sendiri.
	const GUIDE_MENUS = ["Migration"];

	function pick(candidates) {
		const mine = candidates.filter(is_mine);
		const previous = last_used();
		if (previous && mine.includes(previous)) return previous;
		const work = mine.filter((label) => !GUIDE_MENUS.includes(label));
		return (work.length ? work : mine.length ? mine : candidates)[0];
	}

	proto.set_workspace_sidebar = function (router) {
		// Kosongkan dulu: pada jalur route panjang-2 ("Workspaces/Accounting") frappe
		// memanggil setup() lalu return TANPA memperbarui preferred_sidebars, jadi nilai
		// sisa route sebelumnya akan menyesatkan pemilihan di bawah.
		this.preferred_sidebars = [];
		original.call(this, router);

		const candidates = this.preferred_sidebars || [];
		if (!candidates.length) {
			// Halaman workspace (route "Workspaces/X") lewat jalur ini: catat menunya, supaya
			// klik item dari sidebar panduan (Migration) dikenali sebagai pilihan user.
			if (this.sidebar_title && is_mine(this.sidebar_title)) remember(this.sidebar_title);
			return;
		}
		// Sidebar yang tampil sudah salah satu MENU KITA -> jangan diganggu; itu memang
		// menu yang dibuka user (mis. lagi menyusuri Accounting, buka Payment Entry).
		// Kalau yang tampil menu bawaan/turunan modul, TIDAK dibiarkan walau ia termasuk
		// kandidat: itu bukan pilihan user, cuma hasil frappe kehabisan opsi.
		const guide_not_chosen =
			GUIDE_MENUS.includes(this.sidebar_title) && last_used() !== this.sidebar_title;
		if (
			this.sidebar_title &&
			candidates.includes(this.sidebar_title) &&
			is_mine(this.sidebar_title) &&
			!guide_not_chosen
		) {
			remember(this.sidebar_title);
			return;
		}

		// Sampai sini frappe memang GAGAL memilih: kandidatnya lebih dari satu dan tidak
		// ada yang sama dengan workspace default modulnya, jadi setup() tak pernah
		// dipanggil. Akibatnya bukan cuma sidebar kosong — kalau sebelumnya ada sidebar
		// lain, sidebar itu yang bertahan dan menu yang diklik TIDAK PERNAH terbuka
		// (mis. menu Accounting: link pertamanya Journal Entry, ada di sidebar
		// "Accounting" dan "Payments", sedangkan workspace default modul Accounts =
		// "Invoicing" yang bukan keduanya).
		const fallback = pick(candidates);
		if (!fallback) return;
		if (is_mine(fallback)) remember(fallback);
		if (fallback !== this.sidebar_title) this.setup(fallback);
	};

	// Beberapa item sidebar menunjuk path yang SAMA dan cuma beda query string (Inbox/Sent =
	// /desk/mailbox?folder=Inbox|Sent, Sales Return = delivery-note?is_return=1).
	// is_route_in_sidebar() frappe membuang query lalu menandai item TERAKHIR yang cocok, jadi
	// menu mana pun yang diklik yang tersorot selalu yang paling bawah. Di sini dipilih ulang:
	// item yang semua parameter query-nya ada di URL, yang parameternya paling banyak menang
	// (Credit Note ?is_return=1 di atas Invoice tanpa query); tak ada yang cocok -> yang pertama.
	const original_match = proto.is_route_in_sidebar;
	proto.is_route_in_sidebar = function () {
		const match = original_match.call(this);
		if (!match || !this.active_item) return match;
		const path_of = (a) => ($(a).attr("href") || "").split("?")[0];
		const path = path_of(this.active_item.children(".item-anchor"));
		const same = $(".item-anchor").filter((_, a) => path_of(a) === path).toArray();
		if (same.length < 2) return match;

		// frappe.set_route menulis query sebagai JSON (?type=%22invoice%22) sedangkan href item
		// polos (?type=invoice); bandingkan setelah kutip JSON-nya dibuang
		const plain = (v) => {
			try {
				return String(JSON.parse(v));
			} catch (e) {
				return v;
			}
		};
		const here = new URLSearchParams(window.location.search);
		const params = (a) => [...new URL($(a).attr("href"), window.location.origin).searchParams];
		const fits = same.filter((a) =>
			params(a).every(([k, v]) => here.has(k) && plain(here.get(k)) === plain(v))
		);
		fits.sort((a, b) => params(b).length - params(a).length);
		this.active_item.removeClass("active-sidebar");
		this.active_item = $(fits[0] || same[0]).parent();
		return match;
	};
})();

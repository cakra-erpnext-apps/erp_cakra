// Panel add-in ERPNext di Outlook: tautkan email yang sedang dibaca ke transaksi.
//
// Berjalan di dalam iframe Outlook (domain lain), jadi:
//   - tidak memakai cookie sesi ERPNext (browser tidak mengirimnya di konteks pihak
//     ketiga) -- semua panggilan pakai `Authorization: token key:secret`;
//   - tidak ada frappe.js di sini; ini halaman polos + Office.js.
// Server: erpnext_custom.outlook_addin (lookup / save_links) dan quick_search yang sama
// dengan modal Tautkan ke di Mailbox (Packing List terbaru, cari tanpa ledger).

const $ = (id) => document.getElementById(id);
const esc = (s) =>
	String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const key = (l) => `${l.doctype}::${l.name}`;

const state = {
	creds: null, // { key, secret }
	mailbox: "",
	message_id: "",
	communication: null,
	picked: [], // [{doctype, name}]
	latest: [],
	found: [],
	searched: false,
};

Office.onReady(() => {
	const rs = Office.context.roamingSettings;
	const k = rs.get("erp_api_key");
	const s = rs.get("erp_api_secret");
	state.creds = k && s ? { key: k, secret: s } : null;
	state.mailbox = Office.context.mailbox.userProfile.emailAddress;

	bind();
	// Panel yang disematkan (pin) tetap terbuka saat pindah email; muat ulang tiap ganti.
	Office.context.mailbox.addHandlerAsync(Office.EventType.ItemChanged, () => start());
	start();
});

function start() {
	const item = Office.context.mailbox.item;
	if (!item) return;
	$("subject").textContent = item.subject || "(tanpa judul)";
	state.message_id = item.internetMessageId || "";

	if (!state.creds) return show("setup");
	show("main");
	load();
}

function show(which) {
	$("setup").classList.toggle("hidden", which !== "setup");
	$("main").classList.toggle("hidden", which !== "main");
}

// ------------------------------------------------------------------ server

async function api(method, args) {
	const r = await fetch(`/api/method/${method}`, {
		method: "POST",
		credentials: "omit",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
			Authorization: `token ${state.creds.key}:${state.creds.secret}`,
		},
		body: JSON.stringify(args || {}),
	});
	const data = await r.json().catch(() => ({}));
	if (!r.ok) throw new Error(server_message(data) || `ERPNext menjawab ${r.status}`);
	return data.message;
}

// Frappe mengirim pesan error di _server_messages: array JSON berisi string JSON.
function server_message(data) {
	try {
		return JSON.parse(data._server_messages || "[]")
			.map((m) => JSON.parse(m).message)
			.join(" ")
			.replace(/<[^>]+>/g, "");
	} catch (e) {
		return data.exception || "";
	}
}

// ------------------------------------------------------------------ muat

async function load() {
	status("Memuat...");
	state.searched = false;
	$("search").value = "";
	try {
		const [info, latest, who] = await Promise.all([
			api("erpnext_custom.outlook_addin.lookup", { mailbox: state.mailbox, message_id: state.message_id }),
			api("erpnext_custom.quick_search.latest_transactions", { limit: 5 }),
			api("frappe.auth.get_logged_user"),
		]);
		state.communication = info.communication;
		state.picked = info.links || [];
		state.latest = latest || [];
		$("who").textContent = `Masuk ERPNext sebagai ${who}.`;
		status("");
	} catch (e) {
		status(e.message, "err");
	}
	render();
}

function render() {
	$("picked").innerHTML = state.picked.length
		? state.picked
				.map(
					(l) => `<span class="chip">${esc(l.doctype)} ${esc(l.name)}
						<a data-remove="${esc(key(l))}">Hapus</a></span>`
				)
				.join("")
		: `<span class="muted">Belum tertaut ke transaksi apa pun.</span>`;

	const rows = state.searched ? state.found : state.latest;
	const on = new Set(state.picked.map(key));
	$("results-label").textContent = state.searched ? "Hasil pencarian" : "Packing List terbaru";
	$("results").innerHTML = rows.length
		? rows
				.map(
					(h) => `<label class="row">
						<input type="checkbox" data-key="${esc(key(h))}" ${on.has(key(h)) ? "checked" : ""}>
						<span><strong>${esc(h.name)}</strong> <span class="muted">${esc(h.doctype)}</span>
						${h.description ? `<br><small>${esc(h.description)}</small>` : ""}</span>
					</label>`
				)
				.join("")
		: `<div class="muted" style="padding:8px 2px">${
				state.searched ? "Tidak ada transaksi yang cocok." : "Belum ada Packing List."
		  }</div>`;
}

// ------------------------------------------------------------------ interaksi

function bind() {
	$("connect").addEventListener("click", connect);
	$("reset").addEventListener("click", () => {
		state.creds = null;
		const rs = Office.context.roamingSettings;
		rs.remove("erp_api_key");
		rs.remove("erp_api_secret");
		rs.saveAsync(() => show("setup"));
	});

	let timer;
	$("search").addEventListener("input", () => {
		clearTimeout(timer);
		timer = setTimeout(search, 300);
	});

	$("results").addEventListener("change", (e) => {
		const k = e.target.getAttribute("data-key");
		if (!k) return;
		const rows = state.searched ? state.found : state.latest;
		const hit = rows.find((h) => key(h) === k);
		const at = state.picked.findIndex((l) => key(l) === k);
		if (e.target.checked && at < 0 && hit) state.picked.push({ doctype: hit.doctype, name: hit.name });
		if (!e.target.checked && at >= 0) state.picked.splice(at, 1);
		render();
	});

	$("picked").addEventListener("click", (e) => {
		const k = e.target.getAttribute("data-remove");
		if (!k) return;
		state.picked = state.picked.filter((l) => key(l) !== k);
		render();
	});

	$("save").addEventListener("click", save);
}

async function connect() {
	const creds = { key: $("key").value.trim(), secret: $("secret").value.trim() };
	if (!creds.key || !creds.secret) return status("Isi API Key dan API Secret.", "err", "setup-status");

	state.creds = creds;
	status("Memeriksa...", "", "setup-status");
	try {
		await api("frappe.auth.get_logged_user");
	} catch (e) {
		state.creds = null;
		return status(`Kunci ditolak ERPNext: ${e.message}`, "err", "setup-status");
	}

	// roamingSettings = pengaturan add-in yang ikut mailbox user ini (tersimpan di Exchange),
	// jadi cukup sekali per user, di perangkat mana pun.
	const rs = Office.context.roamingSettings;
	rs.set("erp_api_key", creds.key);
	rs.set("erp_api_secret", creds.secret);
	rs.saveAsync(() => {
		$("secret").value = "";
		show("main");
		load();
	});
}

async function search() {
	const txt = $("search").value.trim();
	if (txt.length < 3) {
		state.searched = false;
		return render();
	}
	try {
		state.found = (await api("erpnext_custom.quick_search.find_transactions", { txt, limit: 20 })) || [];
		state.searched = true;
		render();
	} catch (e) {
		status(e.message, "err");
	}
}

async function save() {
	$("save").disabled = true;
	status("Menyimpan...");
	try {
		const args = { mailbox: state.mailbox, message_id: state.message_id, links: state.picked };
		// Isi lengkap email hanya dikirim kalau email ini belum pernah disimpan ke ERP.
		if (!state.communication && state.picked.length) args.eml_b64 = await eml();

		const r = await api("erpnext_custom.outlook_addin.save_links", args);
		state.communication = r.communication;
		state.picked = r.links || [];
		render();
		status(state.picked.length ? "Tersimpan. Email tampil di timeline transaksinya." : "Tautan dihapus.", "ok");
	} catch (e) {
		status(e.message, "err");
	} finally {
		$("save").disabled = false;
	}
}

// Seluruh email apa adanya (.eml, base64): isi, lampiran, dan gambar inline sekaligus,
// supaya ERPNext mengolahnya lewat jalur yang sama dengan email yang ditarik IMAP.
function eml() {
	return new Promise((resolve, reject) => {
		const item = Office.context.mailbox.item;
		if (!item.getAsFileAsync) {
			return reject(new Error("Outlook versi ini belum bisa mengirim isi email. Pakai Outlook web atau Outlook baru."));
		}
		item.getAsFileAsync((r) => {
			if (r.status === Office.AsyncResultStatus.Succeeded) resolve(r.value);
			else reject(new Error(r.error ? r.error.message : "Gagal membaca isi email dari Outlook."));
		});
	});
}

function status(text, kind = "", el = "status") {
	const node = $(el);
	node.textContent = text;
	node.className = `status ${kind}`;
}

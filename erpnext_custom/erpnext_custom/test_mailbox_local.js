// Cek logika sinkron Mailbox mode laptop (public/js/mailbox_local.js) tanpa browser.
//   node erpnext_custom/test_mailbox_local.js
// Yang dicek: baris indeks dari item delta Graph, dan email yang dipindah folder di Outlook
// (urutan folder asal/tujuan yang disinkron duluan tidak boleh menghilangkan email).
const assert = require("node:assert");
const { merge_row, safe_name, strip_id, recipients_of } = require("./public/js/mailbox_local.js");

const LocalMail = globalThis.LocalMail;
const INBOX = { id: "IN", name: "Inbox", path: ["Inbox"], kind: "inbox" };
const ARSIP = { id: "AR", name: "Arsip", path: ["Arsip"], kind: null };

// Mesin dengan IndexedDB dan folder laptop di memori.
function engine() {
	const rows = new Map();
	const files = new Map();
	const e = Object.create(LocalMail.prototype);
	Object.assign(e, {
		folders: [INBOX, ARSIP],
		row: async (id) => (rows.has(id) ? { ...rows.get(id) } : undefined),
		put_row: async (r) => rows.set(r.id, { ...r }),
		del_row: async (id) => rows.delete(id),
		write_file: async (path, blob) => files.set(path.join("/"), blob),
		read_file: async (path) => {
			if (!files.has(path.join("/"))) throw Object.assign(new Error("hilang"), { name: "NotFoundError" });
			return files.get(path.join("/"));
		},
		remove_file: async (path) => files.delete(path.join("/")),
	});
	return { e, rows, files };
}

const created = {
	id: "M1",
	subject: "Invoice PL-01",
	from: { emailAddress: { name: "Vendor", address: "Vendor@Luar.com" } },
	toRecipients: [{ emailAddress: { address: "budi@cakraindo.com" } }],
	ccRecipients: [],
	receivedDateTime: "2026-09-24T03:15:00Z",
	isRead: false,
	hasAttachments: true,
	bodyPreview: "Terlampir",
	internetMessageId: "<abc@luar.com>",
};

// Unduhan selesai: berkas ada di folder asal.
async function downloaded(e, files, folder) {
	const row = await e.row("M1");
	row.path = await e.file_path(row);
	delete row.pending;
	await e.put_row(row);
	files.set(row.path.join("/"), "isi-eml");
	assert.strictEqual(row.path[0], folder.name);
	return row;
}

(async () => {
	// baris baru: masuk antrean unduh, alamat pengirim huruf kecil, Message-ID tanpa <>
	const row = merge_row(undefined, INBOX, created);
	assert.strictEqual(row.pending, created.receivedDateTime);
	assert.strictEqual(row.from_addr, "vendor@luar.com");
	assert.strictEqual(row.imid, "abc@luar.com");
	assert.strictEqual(row.seen, 0);

	// perubahan sebagian (cuma isRead) mempertahankan isi lainnya
	const read = merge_row({ ...row, path: ["x.eml"], pending: undefined }, INBOX, { id: "M1", isRead: true });
	assert.strictEqual(read.seen, 1);
	assert.strictEqual(read.subject, "Invoice PL-01");
	assert.strictEqual(read.pending, undefined);

	// dipindah ke Arsip, folder TUJUAN disinkron duluan: berkas ikut pindah, tidak diunduh ulang
	{
		const { e, rows, files } = engine();
		await e.apply(INBOX, created);
		const before = await downloaded(e, files, INBOX);
		await e.apply(ARSIP, created);
		await e.apply(INBOX, { id: "M1", "@removed": { reason: "deleted" } });
		const after = rows.get("M1");
		assert.strictEqual(after.folder, "AR");
		assert.strictEqual(after.path[0], "Arsip");
		assert.strictEqual(after.pending, undefined);
		assert.ok(files.has(after.path.join("/")));
		assert.ok(!files.has(before.path.join("/")));
	}

	// dipindah ke Arsip, folder ASAL disinkron duluan: dihapus lalu masuk lagi sebagai baru
	{
		const { e, rows, files } = engine();
		await e.apply(INBOX, created);
		await downloaded(e, files, INBOX);
		await e.apply(INBOX, { id: "M1", "@removed": { reason: "deleted" } });
		assert.ok(!rows.has("M1"));
		assert.strictEqual(files.size, 0);
		await e.apply(ARSIP, created);
		assert.strictEqual(rows.get("M1").folder, "AR");
		assert.ok(rows.get("M1").pending);
	}

	// rentang simpan: email di luar batas hari tidak ditambahkan, yang sudah ada tetap diperbarui
	{
		const { e, rows } = engine();
		e.days = 30;
		const since = e.cutoff();
		assert.match(since, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
		assert.strictEqual(await e.apply(INBOX, { ...created, receivedDateTime: "2020-01-01T00:00:00Z" }, since), 0);
		assert.ok(!rows.has("M1"));
		const fresh = { ...created, receivedDateTime: new Date().toISOString() };
		assert.strictEqual(await e.apply(INBOX, fresh, since), 1);
		e.days = 0;
		assert.strictEqual(e.cutoff(), null);
	}

	// nama berkas/folder aman untuk Windows
	assert.strictEqual(safe_name('Re: PO 12/2026 "urgent"?'), "Re_ PO 12_2026 _urgent__");
	assert.strictEqual(safe_name("CON"), "_CON");
	assert.strictEqual(safe_name("laporan. "), "laporan");
	assert.strictEqual(safe_name(""), "_");
	assert.strictEqual(safe_name("a".repeat(200), 60).length, 60);

	assert.strictEqual(strip_id(" <x@y> "), "x@y");
	assert.deepStrictEqual(
		recipients_of("Budi <budi@a.com>; ani@b.com,").map((r) => r.emailAddress.address),
		["budi@a.com", "ani@b.com"]
	);

	console.log("mailbox_local OK");
})().catch((e) => {
	console.error(e);
	process.exit(1);
});

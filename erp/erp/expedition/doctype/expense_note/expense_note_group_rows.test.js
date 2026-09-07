// node expense_note_group_rows.test.js
// Cek penyisipan baris judul grup di dropdown Expense Item: satu judul per grup, di
// posisi yang benar, dan nama grup dibuang dari deskripsi baris supaya tidak diulang.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.frappe = { utils: { escape_html: (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;") } };

// Ambil hanya bagian pengelompokan dari expense_note.js (sisanya butuh form Frappe).
const src = fs.readFileSync(path.join(__dirname, "expense_note.js"), "utf8");
const from = src.indexOf("const CMI_GRP_RE");
const to = src.indexOf("function cmi_link_group_headers");
assert.ok(from > 0 && to > from, "blok cmi_link_group_rows tidak ketemu");
eval(src.slice(from, to));

const EST = "Estimation {EST/0001/CMI/26}";
const rows = cmi_link_group_rows([
	{ value: "ADDITIONAL COST", description: `ADDITIONAL COST, [${EST}] sisa budget 600.000,00` },
	{ value: "BIAYA BOOKING CONTAINER", description: `BIAYA BOOKING CONTAINER, [${EST}] sisa budget 100.000,00` },
	{ value: "UANG JALAN 20", description: "UANG JALAN 20, [All]" },
	{ value: "BIAYA LIFT ON F40", description: "BIAYA LIFT ON F40, [All]" },
]);

const heads = rows.filter((r) => r.html);
assert.deepStrictEqual(
	heads.map((r) => r.label),
	[EST, "All"],
	"judul grup harus muncul sekali per grup, urut"
);
assert.strictEqual(rows[0].label, EST, "judul Estimation harus di paling atas");
assert.strictEqual(rows[3].label, "All", "judul All harus tepat sebelum item All pertama");

// Baris judul tidak boleh menjadi nilai field, dan value-nya WAJIB unik: renderer
// link.js mengambil baris lewat get_item(value), jadi value kembar bikin judul kedua
// merender HTML judul pertama (dua judul terbaca "Estimation" semua).
heads.forEach((h) => assert.strictEqual(typeof h.action, "function"));
assert.strictEqual(
	new Set(rows.map((r) => r.value)).size,
	rows.length,
	"semua baris (termasuk judul) harus punya value unik"
);

// Nama grup dibuang dari deskripsi; sisanya tetap utuh.
assert.strictEqual(rows[1].description, "ADDITIONAL COST, sisa budget 600.000,00");
assert.strictEqual(rows[4].description, "UANG JALAN 20");

// Hasil tanpa penanda grup (mis. dropdown Expense Class lama) lewat apa adanya.
const plain = [{ value: "CLS-1", description: "class lama" }];
assert.deepStrictEqual(cmi_link_group_rows(plain), plain);

console.log("ok - " + rows.length + " baris, " + heads.length + " judul grup");

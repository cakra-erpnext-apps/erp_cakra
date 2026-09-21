// node expense_note_sidebar.test.js
// Daftar nomor dokumen untuk blok sidebar: kosong dibuang, kembar sekali saja, terurut.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const src = fs.readFileSync(path.join(__dirname, "expense_note.js"), "utf8");
const from = src.indexOf("function en_sidebar_names");
const to = src.indexOf("function en_sidebar_block");
assert.ok(from > 0 && to > from, "blok en_sidebar_names tidak ketemu");
eval(src.slice(from, to));

// payment_no kosong -> split(",") menghasilkan [""], jangan jadi baris hantu.
assert.deepStrictEqual(en_sidebar_names("".split(",")), []);
assert.deepStrictEqual(en_sidebar_names([null, undefined, "  "]), []);
assert.deepStrictEqual(en_sidebar_names(undefined), []);

// Spasi sesudah koma ikut terbuang, kembar sekali saja, urut naik.
assert.deepStrictEqual(
	en_sidebar_names("PE-002, PE-001, PE-002".split(",")),
	["PE-001", "PE-002"]
);

// Header + baris item yang menunjuk Packing List sama -> satu baris.
assert.deepStrictEqual(
	en_sidebar_names(["PL/A", "PL/A", null, "PL/B"]),
	["PL/A", "PL/B"]
);

console.log("ok - en_sidebar_names");

// node expense_note_smart_input.test.js
// Cek aturan tampilan smart-input di modal Expense Item Edit: angka bulat TIDAK
// ditempeli ",00", angka berdesimal tetap penuh, dan teks yang masih berakhir koma
// (desimal belum selesai diketik) dibiarkan apa adanya.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.frappe = { boot: { sysdefaults: { currency_precision: 2, number_format: "#.###,##" } } };
global.cint = (v) => parseInt(v, 10) || 0;
global.flt = (v, p) => {
	const n = parseFloat(v) || 0;
	return p === undefined ? n : Math.round(n * 10 ** p) / 10 ** p;
};
// Pengganti format_number Frappe untuk gaya "#.###,##" (cukup untuk uji ini).
global.format_number = (n, fmt, dec) => {
	const fixed = Math.abs(n).toFixed(dec);
	const [intp, frac] = fixed.split(".");
	const out = intp.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (frac ? "," + frac : "");
	return (n < 0 ? "-" : "") + out;
};

// Ambil hanya helper angkanya (sisanya butuh form Frappe).
const src = fs.readFileSync(path.join(__dirname, "expense_note.js"), "utf8");
const grab = (start, end) => {
	const from = src.indexOf(start);
	const to = src.indexOf(end);
	assert.ok(from > 0 && to > from, `blok ${start} tidak ketemu`);
	return src.slice(from, to);
};
eval(grab("function en_prec()", "// Format nominal: pakai number_format"));
eval(grab("function en_num_format()", "function en_fmt_nominal"));
eval(grab("function en_to_number(s)", "// \"10%\" -> {pct:10}"));
eval(grab("function en_fmt_money(raw)", "// Format sebuah raw jadi tampilan rapi"));

assert.strictEqual(en_fmt_money("192351222"), "192.351.222", "angka bulat tanpa \",00\"");
assert.strictEqual(en_fmt_money("192.351.222"), "192.351.222", "sudah terformat, tetap sama");
assert.strictEqual(en_fmt_money("1234,5"), "1.234,50", "berdesimal -> tampil penuh");
assert.strictEqual(en_fmt_money("1234,"), "1234,", "koma di ujung = masih diketik");
assert.strictEqual(en_fmt_money(""), "", "kosong tetap kosong");
assert.strictEqual(en_fmt_money(3000000), "3.000.000", "isian otomatis estimasi");
// Desimal titik jangan dibulatkan jadi bilangan bulat.
assert.strictEqual(en_fmt_money("1000.50"), "1.000,50", "desimal titik tetap desimal");

console.log("ok expense_note_smart_input");

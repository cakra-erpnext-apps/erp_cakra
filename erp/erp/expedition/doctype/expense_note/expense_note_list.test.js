// node expense_note_list.test.js
// Cek kolom Invoice & Payment di list Expense Note: nomornya jadi tautan ke modul
// masing-masing, dan kalau nomornya lebih dari satu SEMUANYA ikut terfilter (`in`),
// bukan cuma yang pertama.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.__ = (s) => s;
global.frappe = {
	listview_settings: {},
	router: { slug: (dt) => dt.toLowerCase().replace(/ /g, "-") },
	utils: { escape_html: (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;") },
	user: { full_name: (u) => u },
};

const src = fs.readFileSync(path.join(__dirname, "expense_note_list.js"), "utf8");
eval(src); // mendefinisikan erp_en_doc_links + frappe.listview_settings['Expense Note']

const settings = frappe.listview_settings["Expense Note"];
const fmt = settings.formatters;

function query_of(html) {
	const href = /href="([^"]+)"/.exec(html)[1];
	const q = href.split("?")[1];
	return { path: href.split("?")[0], filter: JSON.parse(decodeURIComponent(q.slice("name=".length))) };
}

// satu nomor
let out = fmt.payment_no("PV/DANAMON/0009/CMI/VIII/26");
let q = query_of(out);
assert.strictEqual(q.path, "/app/payment-entry");
assert.deepStrictEqual(q.filter, ["in", ["PV/DANAMON/0009/CMI/VIII/26"]]);

// tiga nomor -> ketiganya masuk filter, bukan cuma yang pertama
out = fmt.payment_no("PV/A/1, PV/B/2, PV/C/3");
q = query_of(out);
assert.deepStrictEqual(q.filter, ["in", ["PV/A/1", "PV/B/2", "PV/C/3"]]);
assert.ok(out.includes("PV/A/1, PV/B/2, PV/C/3"), "teks tetap menampilkan semua nomor");

// invoice ke modul Sales Invoice
out = fmt.invoice_no("C/E/0037/CMI/26, C/E/0038/CMI/26");
q = query_of(out);
assert.strictEqual(q.path, "/app/sales-invoice");
assert.deepStrictEqual(q.filter, ["in", ["C/E/0037/CMI/26", "C/E/0038/CMI/26"]]);

// kosong / null -> tidak boleh jadi tautan, dan WAJIB diawali "<" (kalau tidak,
// list_view.js memperlakukannya sebagai selector jQuery dan render list mati)
for (const empty of ["", null, undefined, "  ,  "]) {
	const html = fmt.invoice_no(empty);
	assert.ok(html.startsWith("<"), "formatter harus mengembalikan HTML");
	assert.ok(!html.includes("<a "), "nilai kosong tidak boleh jadi tautan");
}

// spasi berlebih dan koma menggantung tidak boleh bikin nama kosong ikut terfilter
q = query_of(fmt.payment_no("  PV/A/1 ,, PV/B/2 , "));
assert.deepStrictEqual(q.filter, ["in", ["PV/A/1", "PV/B/2"]]);

console.log("ok - expense_note_list formatters");

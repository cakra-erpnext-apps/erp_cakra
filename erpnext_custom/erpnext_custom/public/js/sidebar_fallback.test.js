// node sidebar_fallback.test.js
// Cek tambalan sidebar_fallback.js: sidebar kosong -> dipilihkan kandidat, dan yang
// dipilih adalah menu desk kita (top-level) bukan menu bawaan di folder "Default".
const fs = require("fs");
const assert = require("assert");

function run({ items, preferred }) {
	const calls = [];
	global.frappe = {
		boot: {
			desktop_icons: [
				{ label: "Finance", parent_icon: null, hidden: 0 },
				{ label: "Payments", parent_icon: "Default", hidden: 0 },
			],
		},
		ui: {
			Sidebar: class {
				set_workspace_sidebar() {
					this.workspace_sidebar_items = items;
					this.preferred_sidebars = preferred;
				}
				setup(title) {
					calls.push(title);
				}
			},
		},
	};
	eval(fs.readFileSync(__dirname + "/sidebar_fallback.js", "utf8"));
	const s = new frappe.ui.Sidebar();
	s.set_workspace_sidebar({});
	return calls;
}

// kosong + dua kandidat -> ambil menu top-level ("Payments" ada di folder Default)
assert.deepStrictEqual(run({ items: [], preferred: ["Payments", "Finance"] }), ["Finance"]);
// sudah terisi -> jangan diutak-atik
assert.deepStrictEqual(run({ items: [{ label: "x" }], preferred: ["Payments", "Finance"] }), []);
// tidak ada kandidat -> diam saja
assert.deepStrictEqual(run({ items: [], preferred: [] }), []);
console.log("ok");

// Jembatan kecil untuk halaman ERP. Ada-tidaknya window.erpDesktop = penanda halaman sedang
// dibuka di aplikasi desktop (notification_badge.js, tombol Access on Device).
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("erpDesktop", {
	notify: (opts) => ipcRenderer.send("notify", opts),
	// Notifikasi Windows diklik -> link Notification Log dibuka di ERP (tanpa reload).
	onOpen: (cb) => ipcRenderer.on("open-link", (_e, link) => cb(link)),
	// Tombol Display (sidebar_footer.js): ukuran teks + jenis huruf, disimpan per laptop.
	getDisplay: () => ipcRenderer.invoke("display:get"),
	setDisplay: (d) => ipcRenderer.invoke("display:set", d),
	// Halaman Server aplikasi (alamat server ERP per laptop); ditolak dari halaman lain.
	setServer: (url) => ipcRenderer.invoke("server:set", url),
	// Tombol Server di sidebar ERP: buka halaman Server.
	openServer: () => ipcRenderer.send("server:open"),
});

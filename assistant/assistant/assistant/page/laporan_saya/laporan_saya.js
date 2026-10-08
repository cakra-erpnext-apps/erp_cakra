// Laporan Saya (semua user): tampilannya di assistant/public/js/orchestrator_view.js (mode 'user').
// Dimuat sebagai <script> biasa saat halaman dibuka: frappe.require menyimpan isi file di
// localStorage dan menolak path ber-?v=, jadi perubahan tampilan bisa tertahan versi lama.
// Naikkan ?v= di kedua halaman setiap orchestrator_view.js berubah.
frappe.pages['laporan-saya'].on_page_load = function (wrapper) {
	const start = () => cmi_orchestrator_view(wrapper, 'user');
	if (window.cmi_orchestrator_view) return start();
	const s = document.createElement('script');
	s.src = '/assets/assistant/js/orchestrator_view.js?v=7';
	s.onload = start;
	s.onerror = () => frappe.msgprint(__('Tampilan halaman gagal dimuat. Muat ulang halaman (Ctrl+Shift+R).'));
	document.head.appendChild(s);
};

frappe.pages['laporan-saya'].on_page_show = function (wrapper) {
	const page = wrapper.__orc_page;
	if (page && page.__open_from_route) page.__open_from_route();
};

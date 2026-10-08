app_name = "assistant"
app_title = "Assistant"
app_publisher = "CMI"
app_description = "Agent Fleet / Assistant (extracted from erp)"
app_email = "you@cmi.com"
app_license = "mit"

# Installation — seed Role divisi + flow default Agent Fleet.
after_install = "assistant.install.after_install"
after_migrate = "assistant.install.after_migrate"

# Shared "Assistant"/"Email" tabs di form dokumen (PL/SL/Expense Note/Sales Invoice).
# Naikkan ?v= setiap kali berkasnya diubah: nginx menyajikan /assets tanpa Cache-Control,
# jadi browser boleh terus memakai salinan lama walau sudah di-refresh.
app_include_js = [
	"/assets/assistant/js/assistant_tabs.js?v=6",
	# item "Laporan Saya" di sidebar desk untuk semua user (Laporan Pemeriksaan)
	"/assets/assistant/js/audit_entry.js?v=3",
]

# Scheduler — routine pagi/sore + cek (lihat Assistant Settings).
scheduler_events = {
	"cron": {
		"*/15 * * * *": [
			"assistant.assistant.fleet.scheduler_tick",
			"assistant.assistant.orchestrator.tick_slow",
		],
		# Orchestrator: email masuk + eskalasi (batas action dalam menit).
		"* * * * *": ["assistant.assistant.orchestrator.tick"],
		# Laporan pemeriksaan harian (final check), satu per orang.
		"0 7 * * *": ["assistant.assistant.audit.send_digest"],
		# Penasihat: tinjauan bulan lalu, tanggal 1 jam 06.00.
		"0 6 1 * *": ["assistant.assistant.advisor.monthly"],
	},
}

# Inbound email listener — balasan customer (Communication, Received) dicatat ke thread
# Agent Mail + dipicu auto-reply. Butuh Email Account incoming agar benar-benar menerima.
doc_events = {
	"Communication": {
		"after_insert": "assistant.assistant.fleet.on_communication_insert",
	},
	# Rantai antar agent (chain.py): kejadian dokumen -> langkah agent berikutnya.
	"Expense Note": {"on_update": "assistant.assistant.chain.on_expense_note"},
	"Delivery Note": {"on_submit": "assistant.assistant.chain.on_delivery_note"},
	"Sales Invoice": {"on_submit": "assistant.assistant.chain.on_sales_invoice"},
	"Purchase Invoice": {"on_submit": "assistant.assistant.chain.on_purchase_invoice"},
}

# Akses history dibatasi: user non-System-Manager hanya melihat baris Agent History
# yang `user`-nya dia (pernah berhubungan dengan agent itu).
permission_query_conditions = {
	"Agent History": "assistant.assistant.history.history_query_conditions",
	"Agent Task": "assistant.assistant.orchestrator.query_conditions",
}
# Agent Task: pemegang + penerima notifikasi (eskalasi) + Controller/Admin.
has_permission = {
	"Agent Task": "assistant.assistant.orchestrator.has_permission",
}

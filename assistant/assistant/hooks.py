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
app_include_js = "/assets/assistant/js/assistant_tabs.js"

# Scheduler — routine pagi/sore + cek (lihat Assistant Settings).
scheduler_events = {
	"cron": {
		"*/15 * * * *": ["assistant.assistant.fleet.scheduler_tick"],
	},
}

# Inbound email listener — balasan customer (Communication, Received) dicatat ke thread
# Agent Mail + dipicu auto-reply. Butuh Email Account incoming agar benar-benar menerima.
doc_events = {
	"Communication": {
		"after_insert": "assistant.assistant.fleet.on_communication_insert",
	},
}

# Akses history dibatasi: user non-System-Manager hanya melihat baris Agent History
# yang `user`-nya dia (pernah berhubungan dengan agent itu).
permission_query_conditions = {
	"Agent History": "assistant.assistant.history.history_query_conditions",
}

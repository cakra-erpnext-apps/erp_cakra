"""Status quotation lama -> Inquired.

Draft/Sent/Waiting/Approved dihapus dari pilihan; alurnya sekarang
Inquired -> Negotiation (saat dicetak) -> Follow Up (diam 3 hari) -> Win/Lose ->
Converted. Semua status lama berarti "belum beredar ke customer", jadi seluruhnya
turun ke Inquired: yang sudah pernah dikirim akan naik sendiri begitu dicetak lagi.

Win/Lose/Converted tidak disentuh.
"""

import frappe

OLD_STATES = ("Draft", "Sent", "Waiting", "Approved")


def execute():
	frappe.db.sql(
		"""update `tabCRM Quotation` set state = 'Inquired' where state in %(old)s""",
		{"old": OLD_STATES},
	)
	# Kanban/list view yang masih menyaring status lama akan tampil kosong sampai
	# kolomnya diatur ulang -- itu setelan per user, bukan data dokumen.

import frappe
from frappe.model.document import Document


class ERPNextCustomSetting(Document):
	def on_update(self):
		# Sebagian setting ikut dikirim lewat boot (lihat erpnext_custom.item_scope.boot),
		# dan bootinfo di-cache per user. Tanpa dibersihkan, daftar yang baru disimpan —
		# mis. tipe Expense Note yang pakai grid — baru terasa setelah user logout/login.
		frappe.clear_cache()

import frappe
from frappe.model.document import Document


class ERPNextCustomSetting(Document):
	def validate(self):
		from erpnext_custom.outlook_addin import SYNC_SECONDS_MIN

		seconds = self.get("mailbox_sync_seconds")
		if seconds and seconds < SYNC_SECONDS_MIN:
			frappe.throw(
				frappe._("Auto Sync Interval must be at least {0} seconds.").format(SYNC_SECONDS_MIN)
			)

	def on_update(self):
		# Sebagian setting ikut dikirim lewat boot (lihat erpnext_custom.item_scope.boot),
		# dan bootinfo di-cache per user. Tanpa dibersihkan, daftar yang baru disimpan —
		# mis. tipe Expense Note yang pakai grid — baru terasa setelah user logout/login.
		frappe.clear_cache()

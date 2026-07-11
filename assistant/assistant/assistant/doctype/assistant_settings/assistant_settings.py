import frappe
from frappe.model.document import Document


class AssistantSettings(Document):
	def validate(self):
		has_account = any(
			(r.get("enabled") and r.get("api_key")) for r in (self.get("providers") or [])
		)
		if self.enabled and not (has_account or self.api_key or frappe.conf.get("anthropic_api_key")):
			frappe.msgprint(
				frappe._("Agent is enabled but no API key is set — it cannot reply yet."),
				indicator="orange",
				alert=True,
			)

	def on_update(self):
		self._sync_crm_menu()

	def _sync_crm_menu(self):
		"""Baris "CRM" di tab Allowed Module = saklar master menu Assistant di /crm:
		disinkron ke FCRM Settings.enable_crm_assistant (yang dibaca frontend CRM).
		Tanpa baris CRM → tidak menyentuh apa pun (biar FCRM yang pegang)."""
		row = next(
			(r for r in (self.get("allowed_modules") or [])
			 if (r.module_name or "").strip().lower() == "crm"),
			None,
		)
		if row is None or not frappe.db.exists("DocType", "FCRM Settings"):
			return
		val = 1 if row.allowed else 0
		if frappe.db.get_single_value("FCRM Settings", "enable_crm_assistant") != val:
			frappe.db.set_single_value("FCRM Settings", "enable_crm_assistant", val)

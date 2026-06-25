import frappe
from frappe.model.document import Document


class AssistantSettings(Document):
	def validate(self):
		if self.enabled and not (self.api_key or frappe.conf.get("anthropic_api_key")):
			frappe.msgprint(
				frappe._("Agent is enabled but no API key is set — it cannot reply yet."),
				indicator="orange",
				alert=True,
			)

import frappe
from frappe.model.document import Document


class AgentAdministrator(Document):
	def before_insert(self):
		if not self.summary:
			self.summary = f"{self.source or 'Chat'} session"

import frappe
from frappe.model.document import Document


class CMIBranchAccess(Document):
	def on_update(self):
		frappe.cache().delete_value("cmi_branch_access")

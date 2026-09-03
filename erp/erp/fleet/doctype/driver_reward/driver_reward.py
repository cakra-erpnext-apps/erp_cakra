import frappe
from frappe.model.document import Document


class DriverReward(Document):
    def validate(self):
        if self.amount is not None and self.amount <= 0:
            frappe.throw("Nominal reward harus lebih dari 0")

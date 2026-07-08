import frappe
from frappe.model.document import Document


class ExpenseNoteType(Document):
    def validate(self):
        if not self.numbering_code:
            self.numbering_code = self.code
        self.numbering_code = (self.numbering_code or "").strip().upper()

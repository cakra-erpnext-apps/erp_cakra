import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Maintenance(Document):
    def validate(self):
        if self.finish_date and self.finish_date < self.date:
            frappe.throw(_("Tgl Keluar tidak boleh sebelum Tgl Masuk."))

        for row in self.items:
            row.amount = flt(row.qty) * flt(row.rate)
        self.total_amount = sum(flt(r.amount) for r in self.items)

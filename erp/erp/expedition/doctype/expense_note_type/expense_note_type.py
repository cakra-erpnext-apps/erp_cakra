import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from erp.expedition import numbering


class ExpenseNoteType(Document):
    def validate(self):
        if not self.numbering_code:
            self.numbering_code = self.code
        self.numbering_code = (self.numbering_code or "").strip().upper()


def _assert_can_set_counter():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Manager can update Expense Note counters."))


def _counter_info(expense_note_type, company=None, date=None):
    if not expense_note_type:
        frappe.throw(_("Expense Note Type is required."))

    tc, cc, yy, key = numbering.number_parts(
        "EXP", expense_note_type, "Expense Note Type", company=company, date=date
    )
    row = frappe.db.sql("select current from `tabSeries` where name=%s", key)
    current = cint(row[0][0]) if row else 0
    next_number = current + 1
    return {
        "series_key": key,
        "current": current,
        "next": next_number,
        "preview": f"EXP/{tc}/{next_number:05d}/{cc}/{yy}",
    }


@frappe.whitelist()
def get_expense_note_counter(expense_note_type, company=None, date=None):
    _assert_can_set_counter()
    return _counter_info(expense_note_type, company=company, date=date)


@frappe.whitelist()
def set_expense_note_counter(expense_note_type, company=None, date=None, current=0):
    _assert_can_set_counter()
    current = cint(current)
    if current < 0:
        frappe.throw(_("Current counter cannot be negative."))

    info = _counter_info(expense_note_type, company=company, date=date)
    frappe.db.sql(
        """
        insert into `tabSeries` (`name`, `current`)
        values (%s, %s)
        on duplicate key update `current`=%s
        """,
        (info["series_key"], current, current),
    )
    frappe.db.commit()
    return _counter_info(expense_note_type, company=company, date=date)

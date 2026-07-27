import frappe
from frappe.model.document import Document


class CRMMeeting(Document):
    @staticmethod
    def default_list_data():
        columns = [
            {"label": "Subject", "type": "Data", "key": "subject", "width": "18rem"},
            {"label": "Host", "type": "Link", "key": "host", "width": "10rem"},
            {"label": "Status", "type": "Select", "key": "status", "width": "9rem"},
            {"label": "From", "type": "Datetime", "key": "meeting_from", "width": "12rem"},
            {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
        ]
        rows = [
            "name", "subject", "host", "status", "location",
            "organization", "contact", "meeting_from", "meeting_to", "modified",
        ]
        return {"columns": columns, "rows": rows}


def _set_geo(meeting, prefix, latitude, longitude, address=None):
    """Tulis waktu (server, bukan jam klien) + koordinat GPS ke meeting.

    prefix = "checkin" atau "checkout". Cek permission via get_doc.
    """
    doc = frappe.get_doc("CRM Meeting", meeting)
    doc.check_permission("write")
    doc.set(f"{prefix}_time", frappe.utils.now())
    if latitude not in (None, ""):
        doc.set(f"{prefix}_latitude", frappe.utils.flt(latitude))
    if longitude not in (None, ""):
        doc.set(f"{prefix}_longitude", frappe.utils.flt(longitude))
    if prefix == "checkin":
        if address:
            doc.checkin_address = address
        doc.status = "Visited"
    doc.save()
    return doc.as_dict()


@frappe.whitelist()
def check_in(meeting, latitude=None, longitude=None, address=None):
    return _set_geo(meeting, "checkin", latitude, longitude, address)


@frappe.whitelist()
def check_out(meeting, latitude=None, longitude=None):
    return _set_geo(meeting, "checkout", latitude, longitude)

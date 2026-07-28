import frappe
from frappe.model.document import Document


class CRMMeeting(Document):
    @staticmethod
    def default_list_data():
        columns = [
            {"label": "Subject", "type": "Data", "key": "subject", "width": "16rem"},
            {"label": "Date", "type": "Datetime", "key": "meeting_date", "width": "10rem"},
            {"label": "Inquiry", "type": "Link", "key": "inquiry", "width": "10rem"},
            {"label": "Quotation", "type": "Link", "key": "quotation", "width": "10rem"},
            {"label": "Marketing", "type": "Link", "key": "marketing", "width": "10rem"},
            {"label": "From", "type": "Datetime", "key": "meeting_from", "width": "10rem"},
            {"label": "To", "type": "Datetime", "key": "meeting_to", "width": "10rem"},
            {"label": "Location", "type": "Data", "key": "location", "width": "10rem"},
            {"label": "Created By", "type": "Link", "key": "owner", "width": "10rem"},
        ]
        rows = [
            "name", "subject", "meeting_date", "inquiry", "quotation", "marketing",
            "status", "location", "organization", "contact",
            "meeting_from", "meeting_to", "owner", "creation", "modified",
        ]
        return {"columns": columns, "rows": rows}


def _set_geo(meeting, prefix, latitude, longitude, address=None):
    """Tulis waktu (server, bukan jam klien) + koordinat GPS ke meeting.

    prefix = "checkin" atau "checkout". Cek permission via get_doc.
    """
    doc = frappe.get_doc("CRM Meeting", meeting)
    doc.check_permission("write")
    now = frappe.utils.now()
    doc.set(f"{prefix}_time", now)
    if latitude not in (None, ""):
        doc.set(f"{prefix}_latitude", frappe.utils.flt(latitude))
    if longitude not in (None, ""):
        doc.set(f"{prefix}_longitude", frappe.utils.flt(longitude))
    if prefix == "checkin":
        if address:
            doc.checkin_address = address
        doc.status = "Visited"
        # Absen = waktu aktual meeting: check-in mengisi From, check-out mengisi To.
        # Field-nya tetap Datetime biasa — kapan pun bisa dikoreksi manual di form.
        doc.meeting_from = now
    else:
        doc.meeting_to = now
    doc.save()
    return doc.as_dict()


@frappe.whitelist()
def check_in(meeting, latitude=None, longitude=None, address=None):
    return _set_geo(meeting, "checkin", latitude, longitude, address)


@frappe.whitelist()
def check_out(meeting, latitude=None, longitude=None):
    return _set_geo(meeting, "checkout", latitude, longitude)

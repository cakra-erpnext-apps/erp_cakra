import frappe
from frappe.model.document import Document

# Fieldname centang di CRM Menu Access Group, urut sesuai sidebar. Frontend
# (utils/menuAccess.js) memetakan kunci yang sama ke route-nya.
MENUS = (
	"assistant", "dashboard", "leads", "inquiries", "quotations", "procurement",
	"estimations", "tenders", "accounts", "contacts", "cost_types", "cost_components",
	"products", "locations", "notes", "tasks", "meetings", "calendar", "call_logs",
)


class CRMMenuAccess(Document):
	pass


def get_allowed_menus(user: str | None = None) -> list[str] | None:
	"""Menu CRM yang boleh tampil untuk user; None = semua (tidak dibatasi).

	Hanya menyaring tampilan menu, bukan izin data -- itu tetap Sales User /
	Sales Manager + CMI Branch Access.
	"""
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or "System Manager" in roles:
		return None

	groups = [g for g in frappe.get_cached_doc("CRM Menu Access").groups if g.role in roles]
	if not groups:
		return None
	return [m for m in MENUS if any(g.get(m) for g in groups)]

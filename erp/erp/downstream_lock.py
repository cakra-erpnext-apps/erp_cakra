"""Kunci dokumen yang sudah dipakai dokumen lanjutan (modul berikutnya).

Packing List yang sudah ditarik Expense Note tidak bisa diubah lagi; Expense Note yang
sudah ada Payment Entry-nya tidak bisa direvisi (termasuk batal Validate / Void); dst.
Untuk merevisi, lepas/batalkan dulu dokumen lanjutannya.

Hanya doctype NON-submittable (pola validated/void) + Proforma — doctype submittable
bawaan ERPNext (SO/DN/SI/PO/PR/PI/PE) sudah terkunci native sesudah Submit dan
cancel-nya ditolak selama masih ditautkan dokumen lain.

Dokumen lanjutan dihitung selama belum Cancelled (docstatus < 2) / belum Void — draft
pun sudah "mengklaim" dokumen sumbernya.
"""

import frappe
from frappe.core.doctype.version.version import get_diff

# doctype sumber -> [(doctype lanjutan, field penaut, tabel anak | None, field tipe | None)]
# Field tipe = kolom Dynamic Link di tabel anak yang harus bernilai doctype sumber.
REFS = {
	"Shipping List": [
		("Expense Note", "shipping_list", None, None),
		("Sales Invoice", "custom_shipping_list", None, None),
		("Proforma Invoice", "custom_shipping_list", None, None),
		("Sales Invoice", "shipping_list", "Invoice Shipping List Ref", None),
		("Proforma Invoice", "shipping_list", "Invoice Shipping List Ref", None),
	],
	"Packing List": [
		("Expense Note", "packing_list", None, None),
		("Expense Note", "packing_list", "Expense Note Item", None),
		("Sales Invoice", "custom_packing_list", None, None),
		("Proforma Invoice", "custom_packing_list", None, None),
		("Sales Invoice", "packing_list", "Invoice Packing List Ref", None),
		("Proforma Invoice", "packing_list", "Invoice Packing List Ref", None),
	],
	"Expense Note": [
		("Payment Entry", "expense_note", "Payment Entry Expense Note", None),
		("Payment Entry", "custom_expense_note", "Payment Entry Reference", None),
		("Payment Entry", "document_no", "Payment Entry Items", "document_type"),
		("Sales Invoice", "expense_note", "Sales Invoice Reimburse", None),
		("Proforma Invoice", "expense_note", "Sales Invoice Reimburse", None),
		("Expense Refund", "expense_note", "Expense Refund Item", None),
	],
	"Expense Refund": [
		("Payment Entry", "custom_expense_refund", "Payment Entry Reference", None),
		("Payment Entry", "document_no", "Payment Entry Items", "document_type"),
	],
	"Pending Cash": [
		("Payment Entry", "transaction", "Payment Entry Transaction", "reference_doctype"),
		("Pending Cash Refund", "pending_cash", "Pending Cash Refund Allocation", None),
	],
	"APNotes": [("Payment Entry", "document_no", "Payment Entry Items", "document_type")],
	"ARNotes": [("Payment Entry", "document_no", "Payment Entry Items", "document_type")],
	"AR Note": [],  # dibayar lewat jurnalnya (lihat _journal_refs)
	"Proforma Invoice": [("Sales Invoice", "proforma_ref", None, None)],
	"CRM Estimation": [
		("Packing List", "estimation", None, None),
		("Packing List", "agent_estimation", None, None),
		("Packing List", "estimation", "Packing List Item", None),
		("Packing List", "agent_estimation", "Packing List Item", None),
	],
}


def _alive(alias, doctype):
	meta = frappe.get_meta(doctype)
	cond = []
	if meta.is_submittable:
		cond.append(f"{alias}.docstatus < 2")
	if meta.has_field("void"):
		cond.append(f"ifnull({alias}.void, 0) = 0")
	return " and ".join(cond) or "1=1"


def _journal_refs(doc):
	"""Payment Entry yang membayar jurnal dokumen ini lewat References (Get Outstanding)."""
	je = doc.meta.has_field("journal_entry") and doc.get("journal_entry")
	if not je:
		return []
	return [
		("Payment Entry", n)
		for n in frappe.db.sql_list(
			"""select distinct parent from `tabPayment Entry Reference`
			   where parenttype = 'Payment Entry' and reference_doctype = 'Journal Entry'
			     and reference_name = %s and docstatus < 2""",
			je,
		)
	]


def downstream_refs(doc):
	"""[(doctype, name)] dokumen lanjutan yang masih hidup dan menautkan `doc`."""
	out = []
	for dt, field, child, type_field in REFS.get(doc.doctype, []):
		if child and not frappe.db.table_exists(child):
			continue  # tabel milik app lain (mis. erpnext_custom) belum terpasang
		if child:
			sql = f"""select distinct p.name from `tab{child}` c join `tab{dt}` p on p.name = c.parent
				where c.parenttype = %(dt)s and c.`{field}` = %(name)s and {_alive("p", dt)}"""
			if type_field:
				sql += f" and c.`{type_field}` = %(src)s"
		else:
			sql = f"select name from `tab{dt}` p where p.`{field}` = %(name)s and {_alive('p', dt)}"
		out += [(dt, n) for n in frappe.db.sql_list(sql, {"dt": dt, "name": doc.name, "src": doc.doctype})]
	out += _journal_refs(doc)
	return list(dict.fromkeys(out))


def _changed(doc):
	before = doc.get_doc_before_save()
	if not before:
		return False
	d = get_diff(before, doc)
	return bool(d and (d.changed or d.added or d.removed or d.row_changed))


def _throw(doc, refs, action):
	shown = ", ".join(f"{dt} <b>{n}</b>" for dt, n in refs[:10])
	more = f" dan {len(refs) - 10} lainnya" if len(refs) > 10 else ""
	frappe.throw(
		f"{doc.doctype} <b>{doc.name}</b> sudah dipakai di dokumen lanjutan: {shown}{more}. "
		f"Dokumen ini tidak bisa {action} lagi. Lepas/batalkan dulu dari dokumen tersebut.",
		title="Dokumen Terkunci",
	)


def guard(doc, method=None):
	"""validate: tolak perubahan apa pun (isi, Validate/Void, baris) bila sudah ada dokumen lanjutan."""
	if doc.is_new() or doc.flags.get("ignore_downstream_lock") or not _changed(doc):
		return
	refs = downstream_refs(doc)
	if refs:
		_throw(doc, refs, "diubah")


def guard_cancel(doc, method=None):
	"""before_cancel (doctype submittable): tolak cancel bila masih ditautkan dokumen lanjutan."""
	refs = downstream_refs(doc)
	if refs:
		_throw(doc, refs, "dibatalkan")


def set_onload(doc, method=None):
	"""Dikirim ke form (downstream_lock.js) supaya form langsung read-only."""
	if not doc.is_new():
		doc.set_onload("downstream_refs", downstream_refs(doc))

"""Cek email Assign To. Semua perubahan di-rollback, tidak ada email yang terkirim.

    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console
    >>> from erpnext_custom.test_assignment_mail import run; run()
"""

import frappe
from frappe.desk.form import assign_to

from erpnext_custom.assignment_mail import SETTING


def _queued(since):
	return frappe.get_all(
		"Email Queue", filters={"creation": [">=", since]}, fields=["name", "message"], order_by="creation"
	)


def run():
	user = frappe.db.get_value(
		"User", {"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]}
	)
	todo_ref = frappe.get_all("ToDo", fields=["reference_type", "reference_name"], limit=1,
		filters={"reference_type": ["is", "set"], "reference_name": ["is", "set"]})[0]
	args = {"doctype": todo_ref.reference_type, "name": todo_ref.reference_name, "description": "cek assign"}
	frappe.set_user("Administrator")
	try:
		# assign ke user yang sudah punya ToDo Open di dokumen itu dilewati Frappe (duplikat)
		frappe.db.set_value("ToDo", {"reference_type": args["doctype"], "reference_name": args["name"],
			"allocated_to": user, "status": "Open"}, "status", "Cancelled")
		frappe.db.set_single_value(SETTING, "assignment_email_allow", 1)
		start = frappe.utils.now()
		assign_to.add({**args, "assign_to": [user]}, ignore_permissions=True)
		mails = _queued(start)
		assert len(mails) == 1, mails
		assert todo_ref.reference_name in mails[0].message and "cek assign" in mails[0].message

		# Allow dimatikan = tidak ada email
		assign_to.remove(args["doctype"], args["name"], user, ignore_permissions=True)
		frappe.db.set_single_value(SETTING, "assignment_email_allow", 0)
		start = frappe.utils.now()
		assign_to.add({**args, "assign_to": [user]}, ignore_permissions=True)
		assert not _queued(start)

		# email bawaan Frappe untuk Notification Log Assignment tidak ikut terkirim
		start = frappe.utils.now()
		frappe.get_doc({"doctype": "Notification Log", "type": "Assignment", "for_user": user,
			"subject": "x", "document_type": args["doctype"], "document_name": args["name"]}).insert(
			ignore_permissions=True)
		assert not _queued(start)
		print("assignment mail OK")
	finally:
		frappe.db.rollback()

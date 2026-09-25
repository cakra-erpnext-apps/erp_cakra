"""Email ke user yang di-Assign To, dengan template yang bisa diedit.

Diatur di ERPNext Custom Setting > tab Notification:
  - assignment_email_allow     centang = email dikirim, kosong = tidak ada email sama sekali
  - assignment_email_template  Email Template yang dipakai (bawaan TEMPLATE di bawah)

Frappe sendiri sudah mengirim email untuk Notification Log tipe "Assignment", tapi isinya
kalimat baku yang tidak bisa diubah dan tidak bisa dimatikan dari satu tempat (per user di
Notification Settings). Email bawaan itu dimatikan di CMINotificationLog; lonceng tetap.
Konsekuensinya email "assignment dicabut" juga tidak ada lagi -- hanya assign baru.

Variabel template: assignee_name, assigned_by_name, doctype, name, title, description,
date, priority, link, doc (dokumen yang di-assign, bisa {{ doc.customer }} dst).
"""

import frappe
from frappe.desk.doctype.notification_log.notification_log import (
	NotificationLog,
	get_title,
	set_notifications_as_unseen,
)
from frappe.utils import formatdate, get_url, get_url_to_form

SETTING = "ERPNext Custom Setting"
TEMPLATE = "Assignment Notification"

# Dokumen CRM dibuka di aplikasi /crm, bukan form desk.
CRM_ROUTES = {"CRM Lead": "leads", "CRM Inquiry": "inquiries"}

# Tabel + gaya inline (bukan div + kelas): Gmail dan Outlook membuang <style>.
BODY = """<div style="background:#f4f5f6;padding:24px 12px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px">
    <tr>
      <td style="padding:20px 24px 16px;border-bottom:1px solid #f1f2f3">
        <div style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#6b7280">
          New Assignment
        </div>
        <div style="margin-top:6px;font-size:18px;font-weight:600;color:#111827">
          {{ doctype }} {{ name }}
        </div>
      </td>
    </tr>
    <tr>
      <td style="padding:18px 24px 4px">
        <p style="margin:0 0 16px;font-size:14px;line-height:20px;color:#374151">
          Halo {{ assignee_name }}, <b>{{ assigned_by_name }}</b> menugaskan dokumen ini kepada Anda.
        </p>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:14px">
          {% if title != name %}<tr>
            <td style="padding:7px 0;color:#6b7280;width:42%">Judul</td>
            <td style="padding:7px 0;color:#111827;font-weight:600">{{ title }}</td>
          </tr>{% endif %}
          <tr>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#6b7280;width:42%">Tanggal</td>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#111827;font-weight:600">{{ date }}</td>
          </tr>
          <tr>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#6b7280">Prioritas</td>
            <td style="padding:7px 0;border-top:1px solid #f3f4f6;color:#111827;font-weight:600">{{ priority }}</td>
          </tr>
        </table>
        {% if description %}
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px">
          <tr>
            <td style="padding:12px 14px;background:#f9fafb;border-left:3px solid #d1d5db;
                       font-size:14px;line-height:20px;color:#374151">
              {{ description }}
            </td>
          </tr>
        </table>
        {% endif %}
      </td>
    </tr>
    <tr>
      <td style="padding:20px 24px 24px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="background:#2563eb;border-radius:8px">
              <a href="{{ link }}"
                 style="display:inline-block;padding:11px 28px;font-size:14px;font-weight:600;
                        color:#ffffff;text-decoration:none">
                Open Document
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</div>
"""


def ensure_template():
	"""after_migrate. Template yang sudah ada tidak ditimpa (boleh diedit user), setelannya
	hanya diisi kalau masih kosong."""
	if not frappe.db.exists("Email Template", TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "Email Template",
				"name": TEMPLATE,
				"subject": "{{ assigned_by_name }} assigned {{ doctype }} {{ name }} to you",
				"use_html": 1,
				"response_html": BODY,
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_single_value(SETTING, "assignment_email_template"):
		frappe.db.set_single_value(SETTING, "assignment_email_template", TEMPLATE)
	# default "1" di JSON tidak berlaku untuk Single yang sudah ada; pilihan user (0) dihormati.
	if not frappe.db.exists("Singles", {"doctype": SETTING, "field": "assignment_email_allow"}):
		frappe.db.set_single_value(SETTING, "assignment_email_allow", 1)


def _link(doctype, name):
	if route := CRM_ROUTES.get(doctype):
		return get_url(f"/crm/{route}/{name}")
	return get_url_to_form(doctype, name)


def context(todo):
	doc = frappe.get_doc(todo.reference_type, todo.reference_name)
	full_name = lambda user: frappe.get_cached_value("User", user, "full_name") or user  # noqa: E731
	return {
		"assignee_name": full_name(todo.allocated_to),
		"assigned_by_name": full_name(todo.assigned_by),
		"doctype": todo.reference_type,
		"name": todo.reference_name,
		"title": get_title(todo.reference_type, todo.reference_name) or todo.reference_name,
		"description": todo.description,
		"date": formatdate(todo.date),
		"priority": todo.priority,
		"link": _link(todo.reference_type, todo.reference_name),
		"doc": doc,
	}


def on_todo_insert(todo, method=None):
	"""ToDo.after_insert. Satu ToDo = satu assign (frappe.desk.form.assign_to.add, Assignment
	Rule, CRM). Kalau ada yang gagal, assign-nya tetap jalan: kesalahan dicatat di Error Log."""
	if not (todo.reference_type and todo.reference_name and todo.allocated_to):
		return
	if todo.status != "Open" or todo.assigned_by == todo.allocated_to:
		return
	if not frappe.db.get_single_value(SETTING, "assignment_email_allow"):
		return
	template = frappe.db.get_single_value(SETTING, "assignment_email_template")
	user = frappe.db.get_value("User", todo.allocated_to, ["email", "enabled"], as_dict=True)
	if not (template and user and user.enabled and user.email):
		return

	try:
		mail = frappe.get_doc("Email Template", template).get_formatted_email(context(todo))
		frappe.sendmail(
			recipients=[user.email],
			subject=frappe.utils.strip_html(mail["subject"]),
			message=mail["message"],
			reference_doctype=todo.reference_type,
			reference_name=todo.reference_name,
		)
	except Exception:
		frappe.log_error(f"Assignment email {todo.name} gagal", reference_doctype="ToDo", reference_name=todo.name)


class CMINotificationLog(NotificationLog):
	def after_insert(self):
		# Email assignment diurus on_todo_insert; sisanya (lonceng, realtime) tetap bawaan.
		if self.type != "Assignment":
			return super().after_insert()
		frappe.publish_realtime("notification", after_commit=True, user=self.for_user)
		set_notifications_as_unseen(self.for_user)

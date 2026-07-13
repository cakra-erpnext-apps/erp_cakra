"""Tool untuk CRM Assistant.

Batasannya ditegakkan DI SINI, bukan hanya di teks skill. Prompt bisa diabaikan
model; kode tidak. Karena itu:

- Tidak ada satu pun tool yang membuat transaksi. Tool create_* milik Expedition
  sama sekali tidak didaftarkan untuk surface CRM (lihat CRM_TOOL_NAMES di api.py).
- Baca dibatasi ke doctype CRM saja (READ_DOCTYPES). Modul lain -- Shipping List,
  Expense Note, Sales Invoice, dsb. -- tidak bisa disentuh, bahkan bila model
  memintanya.
- Ubah status hanya untuk CRM Inquiry & CRM Quotation, HANYA pada dokumen milik
  user sendiri (owner = session user), dan hanya field status/state.
"""

import frappe
from frappe import _

# Doctype yang boleh DIBACA. Sengaja daftar putih, bukan daftar hitam: doctype baru
# di modul lain tidak otomatis ikut terbuka.
READ_DOCTYPES = {
	"CRM Lead",
	"CRM Inquiry",
	"CRM Quotation",
	"CRM Estimation",
	"CRM Organization",
	"CRM Product",
	"CRM Products",
	"CRM Inquiry Status",
	"CRM Lead Status",
	"CRM Lost Reason",
	"Contact",
}

# Doctype yang statusnya boleh diubah, beserta nama field statusnya.
STATUS_FIELD = {
	"CRM Inquiry": "status",
	"CRM Quotation": "state",
}

MAX_ROWS = 50


def _check_readable(doctype: str):
	if doctype not in READ_DOCTYPES:
		frappe.throw(
			_("Assistant CRM hanya boleh membaca data CRM. Doctype '{0}' di luar jangkauan.").format(
				doctype
			)
		)


def list_records(doctype: str, filters=None, fields=None, order_by=None, limit=20):
	"""Baca daftar dokumen CRM.

	Memakai get_all, bukan get_list: user boleh melihat data cabang lain (sesuai
	permintaan -- assistant untuk memahami sistem, lintas cabang). Pembatasannya ada
	pada daftar putih doctype di atas, bukan pada permission per-baris.
	"""
	_check_readable(doctype)
	limit = min(int(limit or 20), MAX_ROWS)
	return frappe.get_all(
		doctype,
		filters=filters or {},
		fields=fields or ["name"],
		order_by=order_by or "modified desc",
		limit_page_length=limit,
	)


def get_record(doctype: str, name: str):
	"""Baca satu dokumen CRM utuh."""
	_check_readable(doctype)
	if not frappe.db.exists(doctype, name):
		return {"_error": f"{doctype} '{name}' tidak ditemukan."}
	doc = frappe.get_doc(doctype, name)
	return doc.as_dict(no_default_fields=False)


def get_status_options(doctype: str):
	"""Status apa saja yang tersedia untuk doctype ini."""
	if doctype not in STATUS_FIELD:
		return {"_error": f"Status {doctype} tidak bisa diubah lewat assistant."}
	if doctype == "CRM Inquiry":
		return {"options": frappe.get_all("CRM Inquiry Status", pluck="name")}
	field = frappe.get_meta(doctype).get_field(STATUS_FIELD[doctype])
	return {"options": (field.options or "").split("\n") if field else []}


def update_status(doctype: str, name: str, status: str, user_approved=False):
	"""Ubah status CRM Inquiry / CRM Quotation.

	Tiga penjagaan, semuanya di kode:
	  1. hanya doctype di STATUS_FIELD -- tidak bisa menyentuh yang lain;
	  2. hanya dokumen MILIK USER SENDIRI (owner = session user);
	  3. hanya setelah user menyetujui secara eksplisit (user_approved).
	Hanya field status yang disentuh; field lain tidak ikut tersimpan.
	"""
	if doctype not in STATUS_FIELD:
		return {"_error": f"Assistant hanya boleh mengubah status CRM Inquiry & CRM Quotation, bukan {doctype}."}

	if not user_approved:
		return {
			"_error": "Perubahan status butuh persetujuan user. Tanyakan dulu, lalu panggil ulang "
			"dengan user_approved=true setelah user setuju."
		}

	if not frappe.db.exists(doctype, name):
		return {"_error": f"{doctype} '{name}' tidak ditemukan."}

	me = frappe.session.user
	owner = frappe.db.get_value(doctype, name, "owner")
	if owner != me:
		return {
			"_error": f"{name} bukan milik Anda (pemilik: {owner}). Assistant hanya boleh mengubah "
			"status dokumen milik user sendiri."
		}

	field = STATUS_FIELD[doctype]
	valid = get_status_options(doctype).get("options") or []
	if valid and status not in valid:
		return {"_error": f"Status '{status}' tidak sah. Pilihan: {', '.join(valid)}"}

	old = frappe.db.get_value(doctype, name, field)
	if old == status:
		return {"ok": True, "unchanged": True, "name": name, "status": status}

	doc = frappe.get_doc(doctype, name)
	doc.set(field, status)
	# ignore_mandatory: dokumen lama (hasil import) belum punya field wajib yang
	# ditambahkan belakangan; kita hanya menyentuh status.
	doc.flags.ignore_mandatory = True
	doc.save()
	frappe.db.commit()

	return {"ok": True, "doctype": doctype, "name": name, "from": old, "to": status}

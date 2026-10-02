"""Menu Tax: Tax Invoice / Tax Expense / Tax ARAP Note / Tax Purchase.

Satu doctype per menu, satu baris per dokumen sumber yang SUDAH JADI (nama baris = nama
dokumennya). Baris dibuat & disegarkan hook dokumen sumber (doc_events di hooks.py), user
cuma mengisi No Tax:
  - Execution Date/By = saat No Tax pertama kali diisi, Modify Date/By = perubahan terakhir.
    Sengaja bukan creation/owner baris: barisnya dibuat sistem (yang submit SI), bukan
    orang yang mengisi pajaknya.
  - Dokumen sumber cancel/void/un-validate: baris dihapus kalau No Tax masih kosong; kalau
    sudah terisi baris tetap ada dengan Status Batal (fakturnya sudah terbit, perlu diganti).
  - No Tax yang disimpan di sini ikut ditulis ke field Tax No dokumen sumber (SI/PI
    custom_tax_no, AP/AR Note tax_no) supaya print format & Core Tax tetap membacanya.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

# dokumen sumber -> doctype menu + field yang disalin
SOURCES = {
	"Sales Invoice": {"target": "Tax Invoice", "party": "customer_name", "date": "posting_date",
		"tax_field": "custom_tax_no", "ppn": "custom_tax_amount", "pph": "custom_pph_amount"},
	"Purchase Invoice": {"target": "Tax Purchase", "party": "supplier_name", "date": "posting_date",
		"tax_field": "custom_tax_no", "ppn": "custom_tax_amount", "pph": "custom_pph_amount"},
	"Expense Note": {"target": "Tax Expense", "party": "vendor", "date": "date",
		"tax_field": None, "ppn": "tax_amount", "pph": "pph_amount"},
	"ARNotes": {"target": "Tax ARAP Note", "party": "associate", "date": "date",
		"tax_field": "tax_no", "ppn": "tax_amount", "pph": "pph_amount"},
	"APNotes": {"target": "Tax ARAP Note", "party": "associate", "date": "date",
		"tax_field": "tax_no", "ppn": "tax_amount", "pph": "pph_amount"},
}

# field yang diisi sistem (dari dokumen sumber / cap Execution-Modify): user cuma boleh No Tax
PROTECTED = ("reference_doctype", "reference_name", "company", "party", "date", "currency", "ppn", "pph",
	"confidential", "source_owner", "status", "execution_date", "execution_by", "modify_date", "modify_by")


def is_posted(doc):
	"""SI/PI: sudah submit. EN/AP/AR Note: Validated dan tidak Void. Dibaca dari FLAG, bukan
	Status: EN import legacy (OGM) statusnya kosong walau sudah validated/paid atau void."""
	if doc.doctype in ("Sales Invoice", "Purchase Invoice"):
		return doc.docstatus == 1
	return bool(doc.get("validated")) and not doc.get("void")


class TaxRecord(Document):
	def validate(self):
		if not self.flags.from_source:
			if self.is_new():
				frappe.throw(_("Baris {0} dibuat otomatis dari dokumen sumbernya.").format(self.doctype))
			# pakai nilai tersimpan, apa pun yang dikirim form/API
			before = self.get_doc_before_save()
			for f in PROTECTED:
				self.set(f, before.get(f))

		self.tax_no = (self.tax_no or "").strip()
		if self.status != "Batal":
			self.status = "Sudah" if self.tax_no else "Belum"

		# Execution/Modify hanya dicap saat USER mengubah No Tax (bukan saat sinkron dari sumber).
		if not self.flags.from_source and self.has_value_changed("tax_no"):
			now, user = now_datetime(), frappe.session.user
			if self.tax_no and not self.execution_date:
				self.execution_date, self.execution_by = now, user
			self.modify_date, self.modify_by = now, user
			self.flags.push_tax_no = True

	def on_update(self):
		tax_field = SOURCES[self.reference_doctype]["tax_field"]
		if self.flags.push_tax_no and tax_field:
			# dokumen sumber sudah submit/validated: tulis langsung, modified-nya tidak diubah
			frappe.db.set_value(self.reference_doctype, self.reference_name, tax_field, self.tax_no,
				update_modified=False)


def sync(doc, method=None):
	"""doc_events dokumen sumber: buat/segarkan baris saat jadi, lepas saat batal."""
	cfg = SOURCES[doc.doctype]
	target = cfg["target"]
	exists = frappe.db.exists(target, doc.name)

	if not is_posted(doc):
		if exists:
			_release(target, doc.name)
		return

	rec = frappe.get_doc(target, doc.name) if exists else frappe.new_doc(target)
	rec.update({
		"reference_doctype": doc.doctype,
		"reference_name": doc.name,
		"company": doc.get("company"),
		"party": doc.get(cfg["party"]),
		"date": doc.get(cfg["date"]),
		"currency": doc.get("currency"),
		"ppn": flt(doc.get(cfg["ppn"])),
		"pph": flt(doc.get(cfg["pph"])),
		"confidential": doc.get("confidential") or 0,
		"source_owner": doc.owner,
		"status": None,  # dihitung ulang di validate (dokumen yang tadinya Batal jadi lagi)
	})
	# No Tax yang sudah diketik di dokumen sumber (mis. di SI draft) jadi isian awal.
	# ponytail: sumber -> baris hanya selama baris masih kosong; sesudah itu baris yang pegang.
	if not rec.tax_no and cfg["tax_field"] and doc.get(cfg["tax_field"]):
		rec.tax_no = doc.get(cfg["tax_field"])
	rec.flags.from_source = True
	rec.flags.ignore_permissions = True
	rec.save()


def on_trash(doc, method=None):
	"""Dokumen sumber dihapus: barisnya ikut hilang (kalau tidak, Dynamic Link menahan hapus)."""
	target = SOURCES[doc.doctype]["target"]
	if frappe.db.exists(target, doc.name):
		frappe.delete_doc(target, doc.name, ignore_permissions=True, force=True)


def _release(target, name):
	if frappe.db.get_value(target, name, "tax_no"):
		frappe.db.set_value(target, name, "status", "Batal")
	else:
		frappe.delete_doc(target, name, ignore_permissions=True, force=True)


def backfill():
	"""Isi baris untuk semua dokumen sumber yang sudah jadi (patch tax_records_init)."""
	for dt in SOURCES:
		if not frappe.db.table_exists(dt):
			continue
		filters = {"docstatus": 1} if dt in ("Sales Invoice", "Purchase Invoice") else {"validated": 1, "void": 0}
		for name in frappe.get_all(dt, filters=filters, pluck="name"):
			sync(frappe.get_doc(dt, name))


# ---- Confidential AP/AR Note: baris Tax ARAP Note ikut aturan note-nya (erp.fico.notes) ----
def _may_see_confidential(user):
	return bool({"System Manager", "Accounts Manager"} & set(frappe.get_roles(user)))


def permission_query(user=None):
	user = user or frappe.session.user
	if _may_see_confidential(user):
		return ""
	return f"(`tabTax ARAP Note`.confidential = 0 or `tabTax ARAP Note`.source_owner = {frappe.db.escape(user)})"


def has_permission(doc, ptype=None, user=None):
	if not doc.get("confidential"):
		return True
	user = user or frappe.session.user
	return doc.source_owner == user or _may_see_confidential(user)

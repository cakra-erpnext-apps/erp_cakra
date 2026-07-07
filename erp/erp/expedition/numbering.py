"""Transaction numbering: {prefix}/{type}/{number}/{company}/{year}.

Examples:
  Packing List  PL-SO/IJ/00001/CMI/26
  Shipping List SH/IM/00001/CMI/26
  Expense Note  EXP/LOC/CMI/26/00001   (counter di AKHIR — kini native via naming
                series `EXP/.cmi_type_code./.cmi_company_code./.YY./.#####`; lihat
                make_number_suffix + parser di bawah)

The running number is a 5-digit counter that resets per (prefix + type + company
+ year). Type code comes from the Type master's `code` field; company code from
the Company's custom `Code` field (custom_company_code), falling back to abbr.

Catatan: penomoran Sales Invoice TIDAK di sini lagi — sudah pindah ke app
erpnext_custom (autoname Property Setter berbasis field `type`).
"""

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import getdate

TYPE_FALLBACK = "GEN"

# Penomoran ditangguhkan: draft yang dibuat agent diberi nama sementara berawalan
# DRAFT- (TIDAK menghabiskan counter seri). Nomor asli baru diberikan saat user
# Save/Confirm dokumennya (lihat assign_number + autoname tiap doctype).
DRAFT_PREFIX = "DRAFT-"

# Field "nomor" tampak per-doctype (None = nomor = name itu sendiri).
NUMBER_FIELD = {
	"Packing List": "packing_list_no",
	"Shipping List": None,
	"Expense Note": None,
}


def draft_name():
	"""Nama sementara unik untuk draft yang belum bernomor (tanpa pakai seri)."""
	return DRAFT_PREFIX + frappe.generate_hash(length=10)


def is_draft_name(name):
	return bool(name) and str(name).startswith(DRAFT_PREFIX)


def _year2(date=None):
	return (getdate(date) if date else getdate()).strftime("%y")


def type_code(type_value, type_doctype):
	if not type_value:
		return TYPE_FALLBACK
	code_field = "numbering_code" if frappe.get_meta(type_doctype).has_field("numbering_code") else "code"
	code = frappe.db.get_value(type_doctype, type_value, code_field)
	if not code and code_field != "code":
		code = frappe.db.get_value(type_doctype, type_value, "code")
	return code or str(type_value) or TYPE_FALLBACK


def company_code(company=None):
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
	if not company:
		return "NA"
	return (
		frappe.db.get_value("Company", company, "custom_company_code")
		or frappe.db.get_value("Company", company, "abbr")
		or "NA"
	)


def number_parts(prefix, type_value, type_doctype, company=None, date=None):
	tc = type_code(type_value, type_doctype)
	cc = company_code(company)
	yy = _year2(date)
	key = f"{prefix}/{tc}/{cc}/{yy}/"  # counter scope: prefix+type+company+year
	return tc, cc, yy, key


def series_key(prefix, type_value, type_doctype, company=None, date=None):
	return number_parts(prefix, type_value, type_doctype, company=company, date=date)[3]


def make_number(prefix, type_value, type_doctype, company=None, date=None):
	tc, cc, yy, key = number_parts(prefix, type_value, type_doctype, company=company, date=date)
	seq = getseries(key, 5)
	return f"{prefix}/{tc}/{seq}/{cc}/{yy}"


def make_number_suffix(prefix, type_value, type_doctype, company=None, date=None):
	"""Format counter-DI-AKHIR: {prefix}/{type}/{company}/{year}/{counter}.

	Dipakai Expense Note yang penomorannya kini native via naming series
	(`EXP/.cmi_type_code./.cmi_company_code./.YY./.#####`). Fungsi ini hanya dipakai
	jalur "draft confirm" (assign_number) — KEY counter-nya identik dengan yang dipakai
	naming series (`{prefix}/{tc}/{cc}/{yy}/`), jadi draft & dokumen normal berbagi satu
	counter yang sama (tidak ada nomor bolong / tabrakan)."""
	tc, cc, yy, key = number_parts(prefix, type_value, type_doctype, company=company, date=date)
	seq = getseries(key, 5)
	return f"{prefix}/{tc}/{cc}/{yy}/{seq}"


# ---- Parser token naming series (dipakai lewat hook `naming_series_variables`) ----
# Peta doctype -> (field tipe di dokumen, doctype master Type-nya). Hanya doctype yang
# penomorannya native (naming series) yang perlu terdaftar di sini.
TYPE_FIELD_MAP = {
	"Expense Note": ("expense_note_type", "Expense Note Type"),
}


def parse_type_code(doc, e=None):
	"""Token `.cmi_type_code.` → kode tipe dokumen (dari master Type-nya)."""
	field, type_dt = TYPE_FIELD_MAP.get(getattr(doc, "doctype", None), (None, None))
	if not field or not doc:
		return TYPE_FALLBACK
	return type_code(doc.get(field), type_dt)


def parse_company_code(doc, e=None):
	"""Token `.cmi_company_code.` → kode company (custom_company_code / abbr)."""
	return company_code(doc.get("company") if doc else None)


@frappe.whitelist()
def assign_number(doctype, docname):
	"""Beri nomor asli ke draft yang masih bernama sementara (DRAFT-...).

	Dipanggil saat user Save/Confirm. Counter seri baru dipakai DI SINI (bukan saat
	agent membuat draft), lalu dokumen di-rename dari nama sementara ke nomor asli.
	Doctype yang tidak punya penomoran tertangguh dikembalikan apa adanya.
	"""
	if doctype not in NUMBER_FIELD:
		frappe.throw(_("Doctype '{0}' tidak mendukung penomoran tertangguh.").format(doctype))
	if not is_draft_name(docname):
		# Sudah bernomor (atau dibuat manual) — tidak ada yang perlu dilakukan.
		return {"name": docname, "changed": False}

	doc = frappe.get_doc(doctype, docname)
	if not hasattr(doc, "make_real_number"):
		frappe.throw(_("Controller {0} belum punya make_real_number().").format(doctype))

	new_name = doc.make_real_number()
	doc.rename(new_name, force=True)  # mengubah doc.name -> new_name lalu reload

	field = NUMBER_FIELD[doctype]
	if field:
		frappe.db.set_value(doctype, new_name, field, new_name, update_modified=False)

	# Ganti referensi DRAFT-... -> nomor asli di arsip agent (chat/email/event) supaya
	# link & tampilan di Assistant ikut menunjuk dokumen yang sudah bernomor.
	try:
		from assistant.assistant import fleet as _agent_fleet

		_agent_fleet.remap_draft_reference(docname, new_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "assign_number remap agent refs")

	frappe.db.commit()
	return {"name": new_name, "changed": True}

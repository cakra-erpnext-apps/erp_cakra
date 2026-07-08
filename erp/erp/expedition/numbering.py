"""Penomoran dokumen expedition.

Semua via **naming series** (dikelola di Document Naming Settings), counter DI AKHIR,
dan **tahun (YY) diambil dari TANGGAL DOKUMEN** (bukan tanggal dibuat):

  Expense Note   `EXP/.cmi_type_code./.ABBR./.cmi_yy./.#####`  → EXP/IMP/CMI/26/00001
  Shipping List  `SH/.type./.ABBR./.cmi_yy./.#####`           → SH/SA.IMP/CMI/26/00001
  Packing List   `PL-SO/.type./.ABBR./.cmi_yy./.#####`        → PL-SO/PCP.J/CMI/26/00001
  Sales Invoice  DI app erpnext_custom (autoname `format:` — counter di TENGAH via
                 token `cmi_inv_counter`; tahun via `cmi_yy`). Bukan di file ini.

Counter reset per bagian SEBELUM `.#####.` → tahun (`.cmi_yy.`) di depan counter = reset
tahunan. `.ABBR.` = token bawaan ERPNext (abbr company). Token `.cmi_*` di bawah dipakai
lewat hook `naming_series_variables` (lihat hooks.py).

Draft agent diberi nama sementara `DRAFT-...` (tidak memakai counter); nomor asli baru
diberikan saat Save/Confirm lewat `assign_number` → `make_real_number` tiap controller.
"""

import frappe
from frappe import _
from frappe.model.naming import getseries, make_autoname
from frappe.utils import getdate

TYPE_FALLBACK = "GEN"
DRAFT_PREFIX = "DRAFT-"

# Field "nomor" tampak per-doctype (None = nomor = name dokumen itu sendiri).
NUMBER_FIELD = {
	"Packing List": "packing_list_no",
	"Shipping List": None,
	"Expense Note": None,
}

# Peta doctype -> (field tipe di dokumen, doctype master Type-nya) untuk token `.cmi_type_code.`.
TYPE_FIELD_MAP = {
	"Expense Note": ("expense_note_type", "Expense Note Type"),
}


# ---- Draft tertangguh ---------------------------------------------------------------
def draft_name():
	"""Nama sementara unik untuk draft yang belum bernomor (tanpa pakai seri)."""
	return DRAFT_PREFIX + frappe.generate_hash(length=10)


def is_draft_name(name):
	return bool(name) and str(name).startswith(DRAFT_PREFIX)


# ---- Building block ------------------------------------------------------------------
def type_code(type_value, type_doctype):
	"""Kode tipe dari master Type-nya (field `numbering_code`/`code`), fallback ke nilainya."""
	if not type_value:
		return TYPE_FALLBACK
	code_field = "numbering_code" if frappe.get_meta(type_doctype).has_field("numbering_code") else "code"
	code = frappe.db.get_value(type_doctype, type_value, code_field)
	if not code and code_field != "code":
		code = frappe.db.get_value(type_doctype, type_value, "code")
	return code or str(type_value) or TYPE_FALLBACK


def _naming_date(doc):
	"""Tanggal acuan penomoran = field tanggal DOKUMEN (bukan hari ini), supaya tahun di
	nomor ikut tanggal dokumen (Expense/BL/PL: `date`; Invoice: `invoice_date`). Fallback
	ke hari ini kalau tak ada."""
	for f in ("date", "invoice_date", "posting_date", "transaction_date", "posting_datetime"):
		v = doc.get(f) if doc else None
		if v:
			return getdate(v)
	return getdate()


# ---- Parser token naming series (dipakai lewat hook `naming_series_variables`) -------
def parse_type_code(doc, e=None):
	"""Token `.cmi_type_code.` → kode tipe dokumen (dari master Type-nya)."""
	field, type_dt = TYPE_FIELD_MAP.get(getattr(doc, "doctype", None), (None, None))
	if not field or not doc:
		return TYPE_FALLBACK
	return type_code(doc.get(field), type_dt)


def parse_company_abbr(doc, e=None):
	"""Token `.cmi_company_abbr.` → Abbr company dari DB (per-tenant). Fallback ke default
	company kalau dokumen tak punya field company. Dipakai Sales Invoice."""
	company = (doc.get("company") if doc else None) or frappe.defaults.get_global_default("company")
	return (frappe.db.get_value("Company", company, "abbr") if company else None) or "NA"


def parse_yy(doc, e=None):
	"""Token `.cmi_yy.` → tahun 2-digit dari TANGGAL DOKUMEN (bukan hari ini)."""
	return _naming_date(doc).strftime("%y")


def parse_inv_counter(doc, e=None):
	"""Token `{cmi_inv_counter}` (Sales Invoice) → counter 4-digit yang RESET per
	(Invoice Type No + Company Abbr + Tahun invoice), ditaruh DI TENGAH nomor supaya format
	`{type}/{0000}/{abbr}/{yy}` tetap tapi counter reset tahunan. Tahun dari TANGGAL invoice."""
	type_no = (doc.get("custom_invoice_type_no") if doc else None) or TYPE_FALLBACK
	abbr = parse_company_abbr(doc, e)
	yy = _naming_date(doc).strftime("%y")  # selaras dengan {cmi_yy} di autoname SI
	return getseries(f"{type_no}/{abbr}/{yy}/", 4)


# ---- Generator nomor (jalur draft-confirm) ------------------------------------------
def make_from_series(doc):
	"""Nomor asli dari naming series doctype-nya. Dipakai jalur draft-confirm
	(assign_number) agar IDENTIK dengan simpan biasa: pakai string naming series yang
	sama → format & key counter (reset tahunan) pasti sama."""
	fld = doc.meta.get_field("naming_series")
	series = doc.get("naming_series") or (fld.default if fld else None)
	if not series:
		frappe.throw(_("{0} belum punya naming series.").format(doc.doctype))
	return make_autoname(series + ".#####", doc.doctype, doc)


# ---- Utilities ----------------------------------------------------------------------
@frappe.whitelist()
def seed_invoice_counters():
	"""Seed counter tabSeries penomoran Sales Invoice (reset tahunan) dari nomor tertinggi
	yang SUDAH ADA per (type/abbr/tahun). Jalankan SEKALI per site agar nomor baru
	menyambung, tidak tabrakan.

	Nama diurai dari kanan: 3 segmen terakhir = counter/abbr/yy; sisanya (bisa mengandung
	'/', mis. 'C/E') = Invoice Type No. Nama yang tak sesuai pola dilewati."""
	maxc = {}
	for name in frappe.get_all("Sales Invoice", pluck="name"):
		parts = str(name).split("/")
		if len(parts) < 4:
			continue
		counter, abbr, yy = parts[-3], parts[-2], parts[-1]
		if not (counter.isdigit() and yy.isdigit() and len(yy) == 2):
			continue
		key = f"{'/'.join(parts[:-3])}/{abbr}/{yy}/"
		maxc[key] = max(maxc.get(key, 0), int(counter))
	for key, val in maxc.items():
		row = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name=%s", key)
		if row:
			if val > (row[0][0] or 0):
				frappe.db.sql("UPDATE `tabSeries` SET current=%s WHERE name=%s", (val, key))
		else:
			frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)", (key, val))
	frappe.db.commit()
	return maxc


@frappe.whitelist()
def assign_number(doctype, docname):
	"""Beri nomor asli ke draft yang masih bernama sementara (DRAFT-...).

	Dipanggil saat user Save/Confirm. Counter seri baru dipakai DI SINI (bukan saat agent
	membuat draft), lalu dokumen di-rename dari nama sementara ke nomor asli."""
	if doctype not in NUMBER_FIELD:
		frappe.throw(_("Doctype '{0}' tidak mendukung penomoran tertangguh.").format(doctype))
	if not is_draft_name(docname):
		return {"name": docname, "changed": False}  # sudah bernomor / dibuat manual

	doc = frappe.get_doc(doctype, docname)
	if not hasattr(doc, "make_real_number"):
		frappe.throw(_("Controller {0} belum punya make_real_number().").format(doctype))

	new_name = doc.make_real_number()
	doc.rename(new_name, force=True)  # ubah doc.name -> new_name lalu reload

	field = NUMBER_FIELD[doctype]
	if field:
		frappe.db.set_value(doctype, new_name, field, new_name, update_modified=False)

	# Ganti referensi DRAFT-... -> nomor asli di arsip agent (chat/email/event) supaya link
	# & tampilan di Assistant ikut menunjuk dokumen yang sudah bernomor.
	try:
		from assistant.assistant import fleet as _agent_fleet

		_agent_fleet.remap_draft_reference(docname, new_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "assign_number remap agent refs")

	frappe.db.commit()
	return {"name": new_name, "changed": True}

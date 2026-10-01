"""Nomor pajak per dokumen, diisi dari menu Tax (halaman tax-register).

Satu baris per dokumen sumber (name = "<doctype>:<name>", jadi tidak bisa dobel). Kolom
Execution/Modify di halaman = owner/creation dan modified_by/modified baris ini; riwayat
perubahannya ada di Version (track_changes).

Dokumen yang sudah punya field Tax No sendiri (SI/PI custom_tax_no, AP/AR Note tax_no) ikut
diisi, supaya print format dan Core Tax tetap membaca field lamanya.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt

# doctype -> (field party, field tanggal, field Tax No di dokumennya | None, filter dokumen jadi,
#             field PPN, field PPh). Hanya dokumen yang pajaknya tidak nol yang tampil.
SOURCES = {
	"Sales Invoice": ("customer_name", "posting_date", "custom_tax_no", {"docstatus": 1}, "custom_tax_amount", "custom_pph_amount"),
	"Purchase Invoice": ("supplier_name", "posting_date", "custom_tax_no", {"docstatus": 1}, "custom_tax_amount", "custom_pph_amount"),
	"Expense Note": ("vendor", "date", None, {"status": ["not in", ["Draft", "Void"]]}, "tax_amount", "pph_amount"),
	"ARNotes": ("associate", "date", "tax_no", {"status": ["not in", ["Draft", "Void"]]}, "tax_amount", "pph_amount"),
	"APNotes": ("associate", "date", "tax_no", {"status": ["not in", ["Draft", "Void"]]}, "tax_amount", "pph_amount"),
}

# menu -> dokumen sumbernya
TYPES = {
	"invoice": ["Sales Invoice"],
	"expense": ["Expense Note"],
	"arap": ["ARNotes", "APNotes"],
	"purchase": ["Purchase Invoice"],
}


class TaxNumber(Document):
	def autoname(self):
		self.name = f"{self.reference_doctype}:{self.reference_name}"


@frappe.whitelist()
def get_rows(type: str, from_date: str, to_date: str, status: str = "", search: str = "") -> list:
	search = (search or "").strip().lower()
	rows = []
	for dt in TYPES[type]:
		party, date, tax_field, filters, ppn, pph = SOURCES[dt]
		or_filters = {ppn: ["!=", 0], pph: ["!=", 0]}
		if dt in ("Sales Invoice", "Purchase Invoice"):
			# pajak lewat tabel Taxes bawaan (mis. invoice Reimburse) tidak masuk custom_tax_amount
			or_filters["total_taxes_and_charges"] = ["!=", 0]
		fields = ["name", f"{party} as party", f"{date} as date", f"{ppn} as ppn", f"{pph} as pph"]
		if tax_field:
			fields.append(f"{tax_field} as src_tax_no")
		# get_list, bukan SQL mentah: izin dokumen sumber (mis. AP/AR Note confidential) tetap berlaku
		docs = frappe.get_list(
			dt,
			filters={**filters, date: ["between", [from_date, to_date]]},
			or_filters=or_filters,
			fields=fields,
			order_by=f"{date} desc, name desc",
			limit_page_length=0,
		)
		if not docs:
			continue
		records = {
			r.reference_name: r
			for r in frappe.get_all(
				"Tax Number",
				filters={"reference_doctype": dt, "reference_name": ["in", [d.name for d in docs]]},
				fields=["reference_name", "tax_no", "owner", "creation", "modified_by", "modified"],
			)
		}
		for d in docs:
			r = records.get(d.name) or frappe._dict()
			tax_no = r.tax_no or d.get("src_tax_no") or ""
			if (status == "Belum" and tax_no) or (status == "Sudah" and not tax_no):
				continue
			if search and search not in f"{d.name} {d.party or ''} {tax_no}".lower():
				continue
			rows.append(
				{
					"doctype": dt,
					"name": d.name,
					"party": d.party,
					"date": d.date,
					"ppn": flt(d.ppn),
					"pph": flt(d.pph),
					"tax_no": tax_no,
					"execution_date": r.creation,
					"execution_by": r.owner,
					"modify_date": r.modified,
					"modify_by": r.modified_by,
				}
			)
	rows.sort(key=lambda x: (str(x["date"]), x["name"]), reverse=True)
	return rows


@frappe.whitelist(methods=["POST"])
def save(doctype: str, name: str, tax_no: str = "") -> None:
	if doctype not in SOURCES:
		frappe.throw(frappe._("Dokumen {0} tidak didukung").format(doctype))
	# boleh isi Tax No hanya untuk dokumen yang boleh dilihat user ini
	frappe.get_doc(doctype, name).check_permission("read")
	tax_no = (tax_no or "").strip()

	key = f"{doctype}:{name}"
	if frappe.db.exists("Tax Number", key):
		doc = frappe.get_doc("Tax Number", key)
		if doc.tax_no != tax_no:
			doc.tax_no = tax_no
			doc.save()
	else:
		frappe.get_doc(
			{"doctype": "Tax Number", "reference_doctype": doctype, "reference_name": name, "tax_no": tax_no}
		).insert()

	tax_field = SOURCES[doctype][2]
	if tax_field:
		# dokumen sudah submit/validated: tulis langsung, tanpa mengubah modified dokumennya
		frappe.db.set_value(doctype, name, tax_field, tax_no, update_modified=False)

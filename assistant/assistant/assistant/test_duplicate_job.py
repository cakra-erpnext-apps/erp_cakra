"""Cek deteksi nota ganda. Jalankan:

	bench --site erp.localhost execute assistant.assistant.test_duplicate_job.run

Membuat 2 agent + file uji, lalu menghapusnya lagi.
"""

import json

import frappe
from frappe.utils.file_manager import save_file

from assistant.assistant import center

# Bukan PDF sungguhan: yang diuji cuma content_hash milik File, dan Frappe
# memvalidasi isi PDF saat disimpan.
BYTES = b"nota vendor palsu untuk uji duplikat"


def _make(label, made):
	doc = frappe.get_doc({
		"doctype": "Agent Administrator", "agent_name": label,
		"job_label": "nota-uji.txt", "status": "New",
	})
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	# Dicatat sebelum langkah berikutnya: kalau save_file gagal, record tetap terhapus.
	made.append(doc.name)
	f = save_file("nota-uji.txt", BYTES, "Agent Administrator", doc.name, is_private=1)
	doc.db_set("source_files", json.dumps([{"file": f.name, "file_url": f.file_url}]))
	return doc.name


def run():
	meta = frappe.get_meta("Agent Administrator")
	live = None
	for field in center.RESULT_FIELDS:
		doctype = meta.get_field(field).options
		rec = frappe.get_all(doctype, filters={"docstatus": ("in", (0, 1))}, pluck="name", limit=1)
		if rec:
			live = (field, doctype, rec[0])
			break
	if not live:
		print("Lewat: belum ada dokumen hasil (Expense Note / Packing List / dst) untuk diuji.")
		return
	field, doctype, docname = live

	made = []
	try:
		a1 = _make("Uji Duplikat Satu", made)
		a2 = _make("Uji Duplikat Dua", made)

		# Agent pertama belum menghasilkan apa pun -> job kedua tetap harus jalan.
		assert center._previous_result(a2) is None, "tanpa draft hidup, jangan diblokir"

		frappe.db.set_value("Agent Administrator", a1, field, docname)
		hit = center._previous_result(a2)
		assert hit, "file identik dengan draft hidup seharusnya terdeteksi"
		assert hit["agent"] == a1 and hit["doctype"] == doctype and hit["docname"] == docname, hit

		# Agent itu sendiri tidak boleh dianggap duplikat dari dirinya sendiri.
		assert center._previous_result(a1) is None

		print(f"duplicate detection OK ({doctype} {docname})")
	finally:
		for name in made:
			for f in frappe.get_all("File", filters={"attached_to_doctype": "Agent Administrator",
			                                          "attached_to_name": name}, pluck="name"):
				frappe.delete_doc("File", f, force=1, ignore_permissions=True)
			frappe.delete_doc("Agent Administrator", name, force=1, ignore_permissions=True)
		frappe.db.commit()

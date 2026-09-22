"""Cek kotak search desk menemukan dokumen dari nomornya. Tidak mengubah data.

    docker exec -i erp_cakra-backend-1 bench --site erp.localhost console
    >>> from erpnext_custom.test_quick_search import run; run()
"""

import frappe

from erpnext_custom.quick_search import find_documents, global_search, numbered_doctypes


def _sample():
	"""Satu dokumen asli yang ada di site ini, untuk dicari balik lewat nomornya."""
	for doctype in ("Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry"):
		name = frappe.db.get_value(doctype, {}, "name", order_by="creation desc")
		if name:
			return doctype, name
	return None, None


def run():
	assert find_documents("ab") == [], "kurang dari 3 huruf harus kosong"

	doctype, name = _sample()
	assert doctype, "tidak ada dokumen contoh di site ini"
	assert doctype in numbered_doctypes(), f"{doctype} tidak masuk daftar doctype bernomor"

	def found(txt):
		return [h for h in find_documents(txt) if h["doctype"] == doctype and h["name"] == name]

	hit = found(name)
	assert hit, f"nomor penuh {name} tidak ketemu"
	assert find_documents(name)[0]["name"] == name, "nomor penuh harus jadi baris pertama"

	# user jarang mengetik nomor penuh: potongan tengahnya harus ketemu juga
	part = name[2:10] if len(name) >= 10 else name[1:]
	assert found(part), f"potongan {part!r} tidak ketemu"

	_ghost_does_not_crash_global_search()

	print("OK", doctype, name, "| potongan:", part, "| doctype bernomor:", len(numbered_doctypes()))


def _ghost_does_not_crash_global_search():
	"""Baris index yang dokumennya sudah dihapus dulu bikin "Search for ..." balas 500."""
	kata = "ZZHANTUTEST"
	frappe.db.delete("__global_search", {"doctype": "Sales Invoice", "name": "ZZ-HANTU-TEST"})
	frappe.db.sql(
		"""insert into `__global_search` (`doctype`, `name`, `title`, `content`, `published`)
		values ('Sales Invoice', 'ZZ-HANTU-TEST', 'hantu', %s, 0)""",
		(f"Name : {kata}",),
	)

	global_search(kata)  # sebelum ditambal: UnboundLocalError

	tersisa = frappe.db.count("__global_search", {"name": "ZZ-HANTU-TEST"})
	assert tersisa == 0, "baris hantu harus ikut terbuang, bukan cuma error yang ditelan"

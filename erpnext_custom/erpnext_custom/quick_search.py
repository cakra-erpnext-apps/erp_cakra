"""Cari DOKUMEN dari kotak search desk (Ctrl+K), bukan cuma nama menu.

Bawaannya kotak itu hanya menawarkan nama doctype/report/halaman. Dokumennya sendiri baru
muncul lewat langkah kedua "Search for ..." yang membaca tabel `__global_search`, dan di
sana nomor transaksi praktis tidak ketemu: tabel itu MyISAM fulltext dengan
`ft_min_word_len=4`, jadi "C/E/00001/CMI/26" dipecah jadi C / E / 00001 / CMI / 26 dan
semua potongan di bawah 4 huruf DIBUANG. Yang tersisa cuma "00001", sehingga invoice yang
dicari kalah peringkat dari dokumen lain yang kebetulan berakhiran 00001 (sudah diuji:
invoice-nya turun ke urutan ke-9, di bawah tiga Communication dan dua Item).

Di sini dokumen dicari LANGSUNG ke tabel masing-masing lewat `search_link` bawaan frappe —
fungsi yang sama yang dipakai field Link — sehingga ikut dapat:
  - izin baca + User Permission per doctype (tidak perlu filter izin sendiri),
  - kolom `search_fields` tiap doctype, jadi nama customer/supplier, tanggal dan total ikut
    tercari dan ikut tampil sebagai keterangan di bawah nomornya,
  - data selalu terbaru: tidak ada index yang harus disinkronkan scheduler.

Hasilnya disisipkan ke dropdown search oleh public/js/awesomebar_documents.js.
"""

import frappe
from frappe.desk.search import search_link
from frappe.utils import cint

MIN_CHARS = 3
PER_DOCTYPE = 3


@frappe.whitelist()
def find_documents(txt: str, limit: int = 10) -> list[dict]:
	txt = (txt or "").strip()
	if len(txt) < MIN_CHARS:
		return []

	hits = []
	for doctype in numbered_doctypes():
		if not frappe.has_permission(doctype, "read"):
			continue
		try:
			rows = search_link(doctype, txt, page_length=PER_DOCTYPE)
		except Exception:
			# sebagian doctype punya standard_query sendiri yang rewel (butuh filter tertentu);
			# satu doctype gagal jangan menjatuhkan seluruh pencarian
			frappe.clear_messages()
			continue

		hits.extend(
			{"doctype": doctype, "name": r["value"], "description": r.get("description") or ""}
			for r in rows
		)

	hits.sort(key=lambda hit: _rank(hit["name"], txt))
	return hits[: cint(limit) or 10]


def _rank(name: str, txt: str) -> int:
	"""Persis = 0, diawali = 1, sisanya = 2. Nomor yang diketik utuh harus di baris pertama."""
	name, txt = name.lower(), txt.lower()
	return 0 if name == txt else 1 if name.startswith(txt) else 2


def numbered_doctypes() -> list[str]:
	"""Doctype yang dokumennya BERNOMOR: submittable, atau autoname-nya deret (#####).

	Dipakai sebagai batas pencarian supaya tidak semua tabel ikut discan. Bukan hanya yang
	submittable, karena dokumen CMI seperti Expense Note / Shipping List / Packing List /
	Dispatch Order tidak submittable tapi tetap bernomor.

	ponytail: 1 query per doctype (~150 di site ini, ~100 ms saat panas). Kalau di prod
	terasa lambat, pangkas daftarnya jadi daftar tetap doctype yang memang dicari orang.
	"""

	def build():
		return frappe.get_all(
			"DocType",
			filters={"istable": 0, "issingle": 0},
			or_filters=[
				["is_submittable", "=", 1],
				["autoname", "like", "naming_series:%"],
				["autoname", "like", "%#####%"],
			],
			pluck="name",
		)

	# hidup sampai `bench clear-cache` / migrate berikutnya; daftar doctype jarang berubah
	return frappe.cache.get_value("cmi_numbered_doctypes", build)


# --- Tambalan bug upstream: "Search for ..." balas 500 ----------------------------------
# Dipasang lewat override_whitelisted_methods di hooks.py, bukan monkeypatch.

STALE_SCAN_LIMIT = 500


@frappe.whitelist()
def global_search(text: str, start: int = 0, limit: int = 20, doctype: str = "") -> list[dict]:
	"""Pengganti `frappe.utils.global_search.search` yang tidak jatuh karena baris hantu.

	Bug upstream (frappe 16.18.3, frappe/utils/global_search.py:541): kalau `__global_search`
	memuat baris untuk dokumen yang SUDAH DIHAPUS, `frappe.get_lazy_doc()` langsung melempar
	DoesNotExistError, `except` menelannya, lalu baris berikutnya tetap memanggil
	`doc.has_permission()` padahal `doc` tidak pernah terisi -> UnboundLocalError dan SELURUH
	pencarian balas 500. Kalau kebetulan dokumen sebelumnya berhasil dimuat, akibatnya malah
	lebih halus dan lebih buruk: izin diperiksa pada dokumen yang salah.

	Baris hantu itu wajar ada di sini: data legacy sering dihapus lewat SQL/skrip impor yang
	tidak lewat `doc.delete()` (hook pembersihnya tidak jalan), dan `bench rebuild-global-search`
	cuma membangun ulang doctype yang punya field `in_global_search` — sisanya tertinggal.
	Saat ditemukan: 18.722 dari 23.760 baris index menunjuk dokumen yang sudah tidak ada, dan
	satu baris Proforma Invoice tetap lolos meski sudah di-rebuild.

	Jadi baris hantu yang KENA pencarian ini dibuang dulu, baru diteruskan ke upstream:
	error-nya hilang karena penyebabnya hilang, dan index-nya ikut bersih sendiri.
	"""
	from frappe.utils.global_search import search

	_drop_deleted_rows(text)
	return search(text, start=start, limit=limit, doctype=doctype)


def _drop_deleted_rows(text: str) -> None:
	"""Hapus baris `__global_search` yang dokumennya sudah tidak ada.

	ponytail: cuma yang muncul di `STALE_SCAN_LIMIT` hasil teratas per kata — sama dengan
	yang bakal dilihat upstream. Pembersihan menyeluruh tetap `bench rebuild-global-search`.
	"""
	rows = []
	for word in {w.strip() for w in (text or "").split("&")}:  # pemecahan yang sama dgn upstream
		if not word:
			continue
		rows += frappe.db.sql(
			"""select `doctype`, `name` from `__global_search`
			where match(`content`) against (%s) limit %s""",
			(word, STALE_SCAN_LIMIT),
			as_dict=True,
		)

	indexed = {}
	for row in rows:
		indexed.setdefault(row.doctype, set()).add(row.name)

	for doctype, names in indexed.items():
		if not frappe.db.exists("DocType", doctype):
			frappe.db.delete("__global_search", {"doctype": doctype})
			continue

		# ignore_permissions WAJIB: tanpa itu dokumen yang tidak boleh dibaca user ini ikut
		# terhitung "sudah dihapus", dan barisnya kebuang untuk SEMUA orang
		alive = set(
			frappe.get_all(
				doctype, filters={"name": ("in", list(names))}, pluck="name", ignore_permissions=True
			)
		)
		gone = names - alive
		if gone:
			# tabelnya MyISAM (fulltext), tidak transaksional — hapusnya langsung berlaku
			frappe.db.delete("__global_search", {"doctype": doctype, "name": ("in", list(gone))})

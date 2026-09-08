"""Isi tabel voucher Repost Accounting Ledger secara massal.

Form bawaan cuma punya tabel Voucher Type + Voucher No yang harus diketik satu per satu,
jadi repost serentak (mis. Januari sampai bulan ini) praktis tidak bisa dikerjakan manual.
Di sini filternya: rentang tanggal + tipe dokumen + (opsional) party.

CATATAN PENTING: repost hanya MEMBANGUN ULANG GL dari isi dokumen. Akun hutang/piutang
tersimpan di dokumennya (baris Journal Entry, credit_to, debit_to, paid_from/paid_to) dan
TIDAK dibaca ulang dari master. Mengganti akun default supplier/customer lalu repost tidak
akan memindahkan apa pun -- akunnya harus diubah di dokumen lebih dulu.
"""

import frappe
from frappe import _

# Semua tipe yang diizinkan repost memakai posting_date, party-nya di field berbeda.
# Party dicocokkan lewat NAMA saja, bukan party_type: satu pihak yang sama sering terdaftar
# ganda sebagai Supplier dan Customer, dan Payment Entry-nya bisa Pay maupun Receive. Party
# Type di dialog cuma untuk memilih record di kotak Link.
PARTY_FIELD = {
	"Sales Invoice": "customer",
	"Purchase Invoice": "supplier",
	"Purchase Receipt": "supplier",
	"Payment Entry": "party",
}


@frappe.whitelist()
def get_allowed_types():
	from erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger import (
		get_allowed_types_from_settings,
	)

	return get_allowed_types_from_settings()


def _journal_entry_names(company, from_date, to_date, party):
	filters = {"company": company, "docstatus": 1, "posting_date": ["between", [from_date, to_date]]}
	if not party:
		return frappe.get_all("Journal Entry", filters=filters, pluck="name")
	parents = frappe.get_all(
		"Journal Entry Account",
		filters={"party": party, "docstatus": 1},
		distinct=True,
		pluck="parent",
	)
	if not parents:
		return []
	filters["name"] = ["in", parents]
	return frappe.get_all("Journal Entry", filters=filters, pluck="name")


@frappe.whitelist()
def get_vouchers(company, from_date, to_date, voucher_types=None, party_type=None, party=None, limit=2000):
	"""[{voucher_type, voucher_no, posting_date}] untuk diisikan ke tabel repost."""
	frappe.has_permission("Repost Accounting Ledger", "write", throw=True)

	limit = int(limit) if limit is not None else 2000
	types = frappe.parse_json(voucher_types) if isinstance(voucher_types, str) else voucher_types
	allowed = get_allowed_types()
	types = [t for t in (types or allowed) if t in allowed]
	if not types:
		frappe.throw(_("Tidak ada tipe dokumen yang diizinkan repost. Cek <b>Accounts Settings</b>."))

	rows = []
	for dt in types:
		if dt == "Journal Entry":
			names = _journal_entry_names(company, from_date, to_date, party)
			for d in frappe.get_all(
				"Journal Entry", filters={"name": ["in", names]} if names else {"name": ["in", [""]]},
				fields=["name", "posting_date"], order_by="posting_date"
			):
				rows.append({"voucher_type": dt, "voucher_no": d.name, "posting_date": d.posting_date})
			continue

		filters = {"company": company, "docstatus": 1, "posting_date": ["between", [from_date, to_date]]}
		if party:
			filters[PARTY_FIELD[dt]] = party
		for d in frappe.get_all(dt, filters=filters, fields=["name", "posting_date"], order_by="posting_date"):
			rows.append({"voucher_type": dt, "voucher_no": d.name, "posting_date": d.posting_date})

	rows.sort(key=lambda r: (r["posting_date"], r["voucher_type"], r["voucher_no"]))
	if not limit:
		return {"rows": rows, "total": len(rows), "truncated": False}
	return {"rows": rows[:limit], "total": len(rows), "truncated": len(rows) > limit}


# ---------------------------------------------------------------- bulk repost

BATCH_SIZE = 1000


def _make_batch(company, delete_cancelled, chunk):
	doc = frappe.new_doc("Repost Accounting Ledger")
	doc.company = company
	doc.delete_cancelled_entries = 1 if delete_cancelled else 0
	for r in chunk:
		doc.append("vouchers", {"voucher_type": r["voucher_type"], "voucher_no": r["voucher_no"]})
	doc.insert()  # validate() jalan di sini: tipe dokumen & tutup buku ikut dicek
	return doc.name


@frappe.whitelist()
def run_bulk_repost(
	company, from_date, to_date, voucher_types=None, party_type=None, party=None,
	delete_cancelled_entries=1, batch_size=BATCH_SIZE,
):
	"""Ambil semua dokumen di rentang itu, pecah per batch, lalu repost berurutan.

	Di bawah batas batch semuanya masuk satu dokumen. Di atasnya dipecah, karena satu job
	repost berjalan sekali habis dan tidak bisa dilanjutkan dari tengah kalau mati.
	"""
	frappe.has_permission("Repost Accounting Ledger", "submit", throw=True)

	batch_size = int(batch_size or BATCH_SIZE)
	res = get_vouchers(company, from_date, to_date, voucher_types, party_type, party, limit=0)
	rows = res["rows"]
	if not rows:
		frappe.throw(_("Tidak ada dokumen yang cocok."))

	chunks = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
	names = [_make_batch(company, delete_cancelled_entries, c) for c in chunks]

	frappe.enqueue(
		"erpnext_custom.repost_bulk.process_batches",
		queue="long",
		# repost lambat; beri jendela yang jelas lebih lebar dari queue "default" (300 detik)
		timeout=max(1800, 3 * len(rows)),
		job_name="cmi_bulk_repost_" + frappe.generate_hash(length=8),
		enqueue_after_commit=True,
		names=names,
		user=frappe.session.user,
	)
	return {"batches": names, "total": len(rows), "batch_size": batch_size}


def process_batches(names, user=None):
	"""Submit + repost tiap batch berurutan. Satu batch gagal tidak menghentikan sisanya --
	batch itu ditinggal draft supaya jelas mana yang perlu diulang."""
	from erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger import start_repost

	done, failed = [], []
	for i, name in enumerate(names, start=1):
		try:
			# docstatus di-set langsung: on_submit bawaan akan meng-enqueue job KEDUA di queue
			# "default" (timeout 300 detik) untuk dokumen yang sama. Di sini kita yang jalankan,
			# di queue "long", berurutan.
			frappe.db.set_value("Repost Accounting Ledger", name, "docstatus", 1, update_modified=False)
			start_repost(name)
			frappe.db.commit()
			done.append(name)
		except Exception:
			frappe.db.rollback()
			frappe.db.set_value("Repost Accounting Ledger", name, "docstatus", 0, update_modified=False)
			frappe.db.commit()
			frappe.log_error(title="Bulk repost gagal: " + name, message=frappe.get_traceback())
			failed.append(name)
		if user:
			frappe.publish_realtime(
				"cmi_bulk_repost",
				{"done": i, "total": len(names), "batch": name, "failed": failed},
				user=user,
			)
	return {"done": done, "failed": failed}

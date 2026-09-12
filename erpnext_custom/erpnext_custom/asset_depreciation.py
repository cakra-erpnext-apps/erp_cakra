"""Kolom bantu di tabel jadwal penyusutan (Asset Depreciation Schedule).

Dua-duanya turunan, diisi ulang tiap jadwal divalidasi:

`custom_depreciation_each` -- baris pertama jadwal hampir selalu prorata (aset mulai
dipakai di tengah bulan), jadi Depreciation Amount saja tidak menjawab "tiap periode
disusutkan berapa". Angkanya diambil dari nilai yang PALING SERING muncul di jadwal,
bukan dihitung ulang dari umur dan nilai perolehan -- rumusnya tidak perlu diduplikasi
dan metode saldo menurun pun tetap menampilkan angka yang masuk akal.

`custom_schedule_date_text` -- tanggal versi baca manusia ("01 Mar 2026"). Frappe cuma
punya format tanggal numerik (System Settings hanya menawarkan dd-mm-yyyy dan kawannya)
dan formatter Date-nya tidak bisa ditimpa per field, jadi tanggalnya ditulis sebagai
teks di kolom sendiri; kolom Date aslinya disembunyikan dari grid lewat Property Setter.
"""

import statistics

from frappe.utils import flt, formatdate

DATE_FORMAT = "dd MMM yyyy"


def set_display_columns(doc, method=None):
	rows = doc.get("depreciation_schedule") or []
	amounts = [flt(r.depreciation_amount) for r in rows if flt(r.depreciation_amount)]
	each = statistics.mode(amounts) if amounts else 0.0
	for row in rows:
		row.custom_depreciation_each = each
		row.custom_schedule_date_text = formatdate(row.schedule_date, DATE_FORMAT) if row.schedule_date else ""

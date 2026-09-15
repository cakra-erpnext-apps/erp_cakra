"""Journal Entry: pisahkan jurnal adjust buatan user dari jurnal otomatis.

Semua modul yang menghasilkan jurnal (Expense Note, Pending Cash, depresiasi aset,
pelepasan aset, selisih kurs, dst) menulis Journal Entry juga, jadi list JE penuh
dokumen yang tidak pernah diketik siapa pun. Flag bawaan ERPNext `is_system_generated`
dipakai sebagai penandanya, dan list JE menyaring dengan flag itu.

Jalur app sendiri menyetel flagnya langsung di tempat JE dibuat (expense_note.py,
pending_cash.py, pending_cash_refund.py). Yang di bawah ini menangani jurnal buatan
ERPNext core, yang tidak bisa kita sentuh kodenya tapi selalu memakai voucher_type
khusus.
"""

import frappe

# voucher_type yang HANYA lahir dari otomasi core. "Journal Entry" sengaja tidak
# masuk daftar: itu justru tipe yang dipakai user untuk adjust manual.
AUTO_VOUCHER_TYPES = {
	"Depreciation Entry",
	"Asset Disposal",
	"Exchange Gain Or Loss",
	"Exchange Rate Revaluation",
	"Deferred Revenue",
	"Deferred Expense",
	"Periodic Accounting Entry",
}


def mark_system_generated(doc, method=None):
	if doc.voucher_type in AUTO_VOUCHER_TYPES:
		doc.is_system_generated = 1

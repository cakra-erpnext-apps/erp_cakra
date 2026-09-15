"""Tandai Journal Entry lama yang lahir dari dokumen, bukan diketik user.

Flag `is_system_generated` baru dipasang di kode pembuatnya (Expense Note, Pending Cash,
Pending Cash Refund) dan lewat hook untuk jurnal otomatis core. Dokumen yang sudah
terlanjur ada belum punya penanda itu, padahal list Journal Entry menyaringnya --
tanpa backfill ini jurnal otomatis lama tetap muncul di daftar adjust.

Dikenali dari jejak yang ditinggalkan pembuatnya: nama Expense Note dipakai sebagai
nama JE-nya, Pending Cash menulis user_remark berawalan tetap, dan voucher_type otomatis
core memang khusus.
"""

import frappe

from erpnext_custom.journal_entry import AUTO_VOUCHER_TYPES

CONDITION = """is_system_generated = 0 and (
	name like 'EN/%%'
	or user_remark like 'Expense Note %%'
	or user_remark like 'Pending Cash %%'
	or user_remark like 'Refund Pending Cash %%'
	or voucher_type in %(auto_types)s
)"""


def execute():
	args = {"auto_types": tuple(AUTO_VOUCHER_TYPES)}
	names = frappe.db.sql(
		f"select name from `tabJournal Entry` where {CONDITION}", args, pluck=True
	)
	if not names:
		return
	frappe.db.sql(
		f"update `tabJournal Entry` set is_system_generated = 1 where {CONDITION}", args
	)
	print(f"Journal Entry ditandai system generated: {len(names)}")

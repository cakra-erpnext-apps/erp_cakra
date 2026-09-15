"""Hapus tabel Cost Items — datanya duplikat baris Expense Items.

`Expense Note Cost` adalah subset murni `Expense Note Item` (description/qty/price/
account, plus `note` yang cuma dilem ke description), dan _sync_cost_items() dulu
membangun ulang items dari baris cost setiap save. Jadi tiap dokumen menyimpan isi
yang sama dua kali; yang berbeda cuma grid entrinya.

Tipe yang memakainya semuanya juga ber-`no_job`, dan jalur no-job sudah menampilkan
grid Expense Items langsung dengan kolom identik — jadi tabel Cost tidak menambah
apa pun. Baris items untuk dokumen lama sudah lengkap (dibangun ulang tiap save),
maka tidak ada migrasi data.

delete_doc("DocType", ...) hanya membuang metadata — Frappe tidak pernah drop tabel
fisiknya. Drop-nya dilakukan di sini, TAPI hanya kalau setiap baris cost benar-benar
punya pasangan di items; kalau ada yang menggantung, tabel dibiarkan utuh untuk
diperiksa manual daripada menghapus satu-satunya salinan.
"""

import frappe

# frappe.db.table_exists() menambahkan prefix "tab" sendiri — isi nama DOCTYPE.
DOCTYPE = "Expense Note Cost"


def _unmirrored():
    """Baris cost yang tidak punya pasangan di Expense Note Item (parent+nominal+akun+
    description hasil lem 'description - note', persis bentukan _sync_cost_items)."""
    return frappe.db.sql(
        """
        SELECT c.parent, c.idx
        FROM `tabExpense Note Cost` c
        WHERE NOT EXISTS (
            SELECT 1 FROM `tabExpense Note Item` i
            WHERE i.parent = c.parent
              AND i.amount = c.amount
              AND i.expense_account <=> c.account
              AND i.description = CONCAT(
                    COALESCE(c.description, ''),
                    IF(COALESCE(c.note, '') = '', '', CONCAT(' - ', c.note))
              )
        )
        """,
        as_dict=True,
    )


def execute():
    if frappe.db.table_exists(DOCTYPE, cached=False):
        stray = _unmirrored()
        if stray:
            frappe.log_error(
                message="Baris cost tanpa pasangan di items: {0}".format(
                    ", ".join("{0}#{1}".format(r.parent, r.idx) for r in stray)
                ),
                title="Expense Note Cost belum bisa di-drop",
            )
            print(
                "LEWAT drop `tab{0}`: {1} baris belum tercermin di Expense Items "
                "(lihat Error Log).".format(DOCTYPE, len(stray))
            )
        else:
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `tab{0}`".format(DOCTYPE))

    # CMI Expense Note Type Ref SENGAJA dipertahankan: child multiselect-nya dipakai
    # lagi oleh setting "pakai grid Expense Items". Patch ini post_model_sync, jadi
    # menghapusnya di sini akan membuang doctype yang baru saja dibuat sync.
    if frappe.db.exists("DocType", DOCTYPE):
        frappe.delete_doc("DocType", DOCTYPE, ignore_permissions=True, force=True)

    frappe.clear_cache()

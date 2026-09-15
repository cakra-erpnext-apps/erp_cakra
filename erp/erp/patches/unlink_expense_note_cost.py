"""Lepas tabel Cost Items dari Frappe TANPA menghapus datanya.

`Expense Note Cost` adalah subset murni `Expense Note Item` (description/qty/price/
account, plus `note` yang cuma dilem ke description), dan _sync_cost_items() dulu
membangun ulang items dari baris cost tiap save -- jadi isi yang sama tersimpan dua
kali. Entri biaya sekarang lewat grid Expense Items, jadi tabel Cost tidak dipakai
lagi oleh kode mana pun.

Yang dilakukan cuma membuang metadata doctype-nya. Tabel fisik `tabExpense Note Cost`
SENGAJA dibiarkan utuh beserta seluruh isinya sebagai arsip -- frappe.delete_doc()
pada DocType memang tidak pernah melakukan DROP TABLE (lihat frappe/model/delete_doc.py,
tidak ada DROP TABLE di sana), dan itu justru yang diinginkan di sini.

Konsekuensinya tabel itu jadi yatim: datanya masih bisa dibaca lewat SQL langsung,
tapi tidak lagi muncul di UI maupun ORM. Kalau suatu saat mau benar-benar dihapus,
lakukan manual setelah memastikan isinya sudah tidak diperlukan.
"""

import frappe

DOCTYPE = "Expense Note Cost"


def execute():
    if frappe.db.exists("DocType", DOCTYPE):
        frappe.delete_doc("DocType", DOCTYPE, ignore_permissions=True, force=True)
    frappe.clear_cache()

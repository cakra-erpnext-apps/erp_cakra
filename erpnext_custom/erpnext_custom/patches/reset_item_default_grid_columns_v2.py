"""Reset kolom grid Item Defaults sekali lagi, setelah susunannya diubah.

Patch dilacak Frappe per PATH, jadi menjalankan ulang yang lama tidak mungkin — versi
kedua ini cuma memanggil logika yang sama. Perlu karena susunan default berubah
(Discount keluar, Reimbursement masuk, lebar jadi 4) sedangkan __UserSettings milik user
yang sudah pernah membuka Item masih memegang susunan lama dan MENIMPA meta.

Efeknya sama dengan menekan "Reset to default" di dialog Configure Columns.
"""

from erpnext_custom.patches.reset_item_default_grid_columns import execute as _reset


def execute():
	_reset()

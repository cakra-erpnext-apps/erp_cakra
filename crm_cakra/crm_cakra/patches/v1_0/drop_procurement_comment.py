import frappe


def execute():
	"""Buang doctype CRM Procurement Comment beserta datanya.

	Diskusi procurement dulu menempel di quotation; costing sekarang pindah ke
	dokumen CRM Procurement per inquiry dan thread komentarnya tidak ikut. Menghapus
	folder doctype-nya saja tidak cukup -- record DocType dan tabelnya tetap
	tertinggal di DB, dan dengan developer_mode menyala malah bisa ter-export balik
	ke disk lalu ikut ter-import lagi di migrate berikutnya.
	"""
	if frappe.db.exists("DocType", "CRM Procurement Comment"):
		# Notifikasi menaut ke komentar; tanpa dibuang dulu, delete_doc gagal
		# LinkExistsError dan patch-nya menggagalkan seluruh migrate.
		frappe.db.delete("CRM Notification", {"notification_type_doctype": "CRM Procurement Comment"})
		frappe.delete_doc("DocType", "CRM Procurement Comment", force=1, ignore_missing=True)

	# delete_doc tidak selalu ikut membuang tabelnya. Dibuang terpisah (dan di luar
	# cabang di atas) supaya site yang sudah menjalankan versi patch sebelumnya
	# tetap kebagian. sql_ddl: Frappe menolak DROP TABLE lewat db.sql biasa.
	frappe.db.sql_ddl("drop table if exists `tabCRM Procurement Comment`")

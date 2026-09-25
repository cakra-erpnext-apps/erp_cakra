import frappe

from crm_cakra.install import add_default_inquiry_statuses

# Status bawaan Frappe CRM yang diganti alur CMI. Kiri = yang lama, kanan =
# padanannya di alur baru. Dipetakan, bukan dihapus begitu saja: inquiry yang
# sudah berjalan tidak boleh kehilangan statusnya hanya karena masternya diganti.
PEMETAAN = {
	"Qualification": "Created",
	"Demo/Making": "Qualified",
	# Ketiganya menandakan quotation sudah ada di tangan customer; di alur baru
	# itu satu status, sisanya (negosiasi, siap tutup) dibaca dari quotation-nya.
	"Proposal/Quotation": "Quotation",
	"Negotiation": "Quotation",
	"Ready to Close": "Quotation",
}


def execute():
	"""Pasang ladder status inquiry CMI dan pensiunkan status bawaan.

	Dipasang lewat patch, bukan lewat after_install: site yang sudah berjalan
	tidak pernah menjalankan after_install lagi, jadi tanpa ini master status di
	server tidak akan pernah berubah walau kodenya sudah di-deploy.

	Idempoten: aman dijalankan berulang, inquiry yang sudah memakai status baru
	tidak disentuh, dan status lama hanya dihapus setelah benar-benar tidak ada
	yang memakainya.

	Fixture CRM Inquiry Status sudah dicabut dari hooks (lihat hooks.py): selama
	fixture itu masih terpasang, migrate akan terus mengembalikan status bawaan
	dan hasil patch ini batal lagi tiap kali.
	"""
	# enforce=True: bukan cuma membuat yang belum ada, tapi menyamakan warna,
	# tipe, dan urutan status yang sudah ada -- ini yang membuat daftar status di
	# server persis sama dengan yang dipakai di lokal, walau site itu sempat
	# kemasukan status bawaan lewat fixture.
	add_default_inquiry_statuses(enforce=True)

	for lama, baru in PEMETAAN.items():
		if not frappe.db.exists("CRM Inquiry Status", lama):
			continue
		if not frappe.db.exists("CRM Inquiry Status", baru):
			# Status tujuannya gagal dibuat (mis. dihapus manual) -- lebih baik
			# membiarkan status lama daripada mengosongkan status inquiry.
			continue

		# SQL langsung: melewati validate inquiry, yang pada dokumen impor lama
		# sering gagal karena field wajib yang memang tidak pernah terisi.
		frappe.db.sql(
			"update `tabCRM Inquiry` set status = %s where status = %s",
			(baru, lama),
		)
		frappe.db.sql(
			"update `tabCRM Status Change Log` set `to` = %s where `to` = %s",
			(baru, lama),
		)
		frappe.db.sql(
			"update `tabCRM Status Change Log` set `from` = %s where `from` = %s",
			(baru, lama),
		)

	for lama in PEMETAAN:
		if not frappe.db.exists("CRM Inquiry Status", lama):
			continue
		if frappe.db.count("CRM Inquiry", {"status": lama}):
			continue
		frappe.delete_doc("CRM Inquiry Status", lama, force=1, ignore_permissions=True)

	frappe.db.commit()

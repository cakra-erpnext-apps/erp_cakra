import frappe

# Alasan awal, hasil obrolan lapangan. Bukan daftar tertutup: Sales Manager bisa
# menambah lewat Desk, dan patch ini tidak pernah menghapus atau menimpa yang ada.
ALASAN = {
	"Permintaan mendesak dari customer": "Customer minta penawaran hari itu juga, tidak sempat menunggu costing.",
	"Rute rutin, harga sudah standar": "Rute yang sudah sering dikerjakan dan harganya sudah punya acuan.",
	"Nilai kecil": "Nominalnya kecil sehingga tidak sebanding dengan waktu perhitungan procurement.",
	"Penawaran indikatif": "Sekadar gambaran harga awal, belum penawaran final.",
	"Lainnya": "",
}


def execute():
	"""Isi master alasan quotation tanpa costing.

	Lewat patch supaya site yang sudah berjalan ikut mendapat daftarnya saat
	migrate -- isi master itu data, tidak ikut terbawa git pull.
	"""
	for alasan, keterangan in ALASAN.items():
		if frappe.db.exists("CRM No Costing Reason", alasan):
			continue
		frappe.get_doc(
			{
				"doctype": "CRM No Costing Reason",
				"reason": alasan,
				"description": keterangan,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()

"""Data contoh untuk mencoba apps sopir. Bukan bagian dari alur produksi.

	from erp.fleet.api import mobile_contoh as contoh
	contoh.buat()    # bikin unit maintenance + unit yang sedang dipakai
	contoh.hapus()   # buang semuanya lagi

Semua yang dibuat diberi tanda TANDA di bawah supaya `hapus()` tidak pernah
menyentuh data sungguhan -- jangan ganti caranya jadi "hapus yang terbaru".
"""

import frappe
from frappe.utils import add_days, today

TANDA = "CONTOH-APPS"
CABANG = "Jakarta"


def _vehicles(n):
	"""Unit teratas cabang, urutan sama dengan yang dilihat sopir di apps."""
	return frappe.get_all(
		"Vehicle",
		filters={"branch": CABANG, "disabled": 0},
		order_by="no_lambung",
		pluck="name",
		limit=n,
	)


def buat():
	hapus()
	unit = _vehicles(8)
	sopir = [
		d
		for d in frappe.get_all(
			"Driver",
			filters={"branch": CABANG, "disabled": 0},
			fields=["name", "title"],
			order_by="name",
		)
		if d.name != "DRV.11"  # Sugeng yang login; dia tidak boleh "memakai" unit
	]
	if len(unit) < 8 or len(sopir) < 4:
		frappe.throw("Data cabang %s belum cukup untuk contoh." % CABANG)

	hasil = {"maintenance": [], "job": [], "check_in": [], "trail": []}

	# Master Trail masih kosong, dan chasis wajib dipilih saat sopir menerima job --
	# tanpa isi, tidak ada job yang bisa diterima siapa pun.
	ukuran = frappe.get_all("Container Size", pluck="name", limit=2)
	for cabang in ("Jakarta", "Medan"):
		for i in range(1, 4):
			kode = f"CH-{cabang[:3].upper()}-{i:02d}"
			if frappe.db.exists("Trail", kode):
				continue
			frappe.get_doc({
				"doctype": "Trail", "code": kode, "title": f"Chasis {cabang} {i}",
				"branch": cabang, "no_rangka": f"{TANDA}-{kode}",
				"size": ukuran[i % len(ukuran)] if ukuran else None,
			}).insert(ignore_permissions=True)
			hasil["trail"].append(kode)

	# 3 unit masuk bengkel, tanggal mulai berbeda supaya kelihatan di keterangan.
	for i, (v, jenis) in enumerate(zip(unit[:3], ["Servis Rutin", "Ban", "Perbaikan"])):
		m = frappe.get_doc(
			{
				"doctype": "Maintenance",
				"vehicle": v,
				"branch": CABANG,
				"maintenance_type": jenis,
				"date": add_days(today(), -(i + 1)),
				"description": TANDA,
			}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		hasil["maintenance"].append((v, jenis, m.name))

	# 3 unit sedang jalan: job yang sudah berangkat dan belum tiba.
	do = frappe.get_doc({"doctype": "Dispatch Order", "branch": CABANG})
	for i, v in enumerate(unit[3:6]):
		do.append(
			"items",
			{
				"assigned": 1,
				"driver": sopir[i].name,
				"vehicle": v,
				"container_no": f"{TANDA}-{i:02d}",
				"dpo_no": f"{TANDA}/{i:02d}",
				"atd": add_days(today(), -i),
			},
		)
		hasil["job"].append((v, sopir[i].title))
	do.insert(ignore_permissions=True, ignore_mandatory=True)

	# 1 unit ditahan sopir yang sudah check in tapi belum dapat job.
	penahan = sopir[3]
	frappe.get_doc(
		{
			"doctype": "Driver Attendance",
			"driver": penahan.name,
			"type": "Absensi",
			"timestamp": frappe.utils.now_datetime(),
			"unique_key": f"{penahan.name}|{today()}",
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Driver Attendance",
			"driver": penahan.name,
			"type": "Check In",
			"timestamp": frappe.utils.now_datetime(),
			"vehicle": unit[6],
		}
	).insert(ignore_permissions=True)
	hasil["check_in"].append((unit[6], penahan.title))

	frappe.db.commit()
	return hasil


def hapus():
	for parent in set(
		frappe.get_all(
			"Dispatch Order Item",
			filters={"container_no": ["like", f"{TANDA}%"]},
			pluck="parent",
		)
	):
		frappe.delete_doc("Dispatch Order", parent, force=True, ignore_permissions=True)

	for m in frappe.get_all("Maintenance", filters={"description": TANDA}, pluck="name"):
		frappe.delete_doc("Maintenance", m, force=True, ignore_permissions=True)

	for t in frappe.get_all("Trail", filters={"no_rangka": ["like", f"{TANDA}%"]}, pluck="name"):
		frappe.delete_doc("Trail", t, force=True, ignore_permissions=True)

	# Absensi contoh dikenali dari sopir cabang ini yang check in hari ini TANPA
	# job -- tidak ada tanda yang bisa ditempel di Driver Attendance, jadi
	# dibatasi ke sopir yang memang dipakai buat() dan hanya hari ini.
	for d in frappe.get_all("Driver", filters={"branch": CABANG}, pluck="name"):
		if d == "DRV.11":
			continue
		for a in frappe.get_all(
			"Driver Attendance",
			filters={"driver": d, "timestamp": [">=", today()]},
			pluck="name",
		):
			frappe.delete_doc("Driver Attendance", a, force=True, ignore_permissions=True)

	frappe.db.commit()
	return "bersih"

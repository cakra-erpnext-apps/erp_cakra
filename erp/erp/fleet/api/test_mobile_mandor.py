"""Self-check apps mandor. Jalankan lewat bench console (bukan bench execute):

    bench --site erp.localhost console
    >>> from erp.fleet.api import test_mobile_mandor as t; t.run()

Semua data uji berprefix ZZTEST dan dihapus lagi di akhir, apa pun hasilnya.

Yang diperiksa adalah keputusan yang bisa salah DIAM-DIAM: pembatasan cabang
(daftar boleh saja rapi sementara endpoint detail tetap bisa dibuka dengan nama
dokumen tebakan), dan bahwa menyimpan lewat HP benar-benar melewati validate
Dispatch Order -- bukan menulis kolom begitu saja.
"""

import frappe
from frappe.utils import add_days, today

from erp.fleet.api import mobile_mandor as api

OFC_A = "ZZTEST-OFC-A"
OFC_B = "ZZTEST-OFC-B"
DRV_A = "ZZTEST-DRV-A"
DRV_B = "ZZTEST-DRV-B"
DRV_LAIN = "ZZTEST-DRV-LAIN"
VEH_A = "ZZTEST-VEH-A"
VEH_LAIN = "ZZTEST-VEH-LAIN"
TRAIL = "ZZTEST-TRAIL-M"
USER = "zztest-mandor@example.com"
USER_TANPA = "zztest-bukan-mandor@example.com"
TAG = "ZZTEST-MANDOR"
PL_TAG = "ZZTEST-PL-MANDOR"


def _cleanup():
	# DPO dulu, baru PL-nya: PL yang masih ditaut DPO tidak bisa dihapus.
	for parent in set(
		frappe.get_all("Dispatch Order Item", filters={"container_no": ["like", f"{TAG}%"]}, pluck="parent")
	):
		frappe.delete_doc("Dispatch Order", parent, force=True, ignore_permissions=True)
	for pl in frappe.get_all("Packing List", filters={"remark": PL_TAG}, pluck="name"):
		frappe.delete_doc("Packing List", pl, force=True, ignore_permissions=True)
	for d in (DRV_A, DRV_B, DRV_LAIN):
		for a in frappe.get_all("Driver Attendance", filters={"driver": d}, pluck="name"):
			frappe.delete_doc("Driver Attendance", a, force=True, ignore_permissions=True)
	for dt, names in (
		("Driver", (DRV_A, DRV_B, DRV_LAIN)),
		("Vehicle", (VEH_A, VEH_LAIN)),
		("Trail", (TRAIL,)),
		("User", (USER, USER_TANPA)),
		("CMI Office", (OFC_A, OFC_B)),
	):
		for n in names:
			if frappe.db.exists(dt, n):
				frappe.delete_doc(dt, n, force=True, ignore_permissions=True)
	frappe.db.commit()


def _packing_list():
	"""PL seadanya, hanya supaya DPO uji punya induk.

	Dispatch Order mewajibkan `packing_list`, dan kewajiban itu baru menggigit
	saat DOKUMEN DISIMPAN LAGI -- persis yang dilakukan apps mandor. DPO uji yang
	dibuat dengan ignore_mandatory lolos di insert lalu gagal di simpanan
	pertama, dan kegagalan itu bukan bug produk melainkan data uji yang tidak
	menyerupai kenyataan.

	PL tanpa item TIDAK menghasilkan DPO otomatis (lihat sync_from_packing_list),
	jadi tidak ada DPO liar yang ikut terbuat di sini.
	"""
	doc = frappe.get_doc({"doctype": "Packing List", "remark": PL_TAG})
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return doc.name


def _dpo(branch, jumlah, pl):
	doc = frappe.get_doc({"doctype": "Dispatch Order", "branch": branch, "packing_list": pl})
	for i in range(jumlah):
		# packing_list_item WAJIB berbeda per baris: `_no_double_assignment`
		# mengelompokkan per container lewat kolom ini, jadi dua baris yang
		# sama-sama kosong terbaca sebagai satu container dan aturannya tidak
		# pernah menyala. Data uji yang tidak menyerupai kenyataan bikin
		# pemeriksaan lolos padahal produknya tidak diuji.
		doc.append(
			"items",
			{
				"container_no": f"{TAG}-{branch[-1]}{i}",
				"packing_list_item": f"{TAG}-PLI-{branch[-1]}{i}",
			},
		)
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return doc


def _setup():
	_cleanup()
	for ofc in (OFC_A, OFC_B):
		frappe.get_doc({"doctype": "CMI Office", "office_name": ofc}).insert(ignore_permissions=True)

	variant = frappe.get_all("Vehicle Variant", pluck="name", limit=1)[0]
	for code, branch in ((DRV_A, OFC_A), (DRV_B, OFC_A), (DRV_LAIN, OFC_B)):
		frappe.get_doc(
			{"doctype": "Driver", "code": code, "title": code, "branch": branch}
		).insert(ignore_permissions=True)
	for nopol, branch in ((VEH_A, OFC_A), (VEH_LAIN, OFC_B)):
		frappe.get_doc(
			{"doctype": "Vehicle", "title": nopol, "no_lambung": nopol, "branch": branch, "variant": variant}
		).insert(ignore_permissions=True)
	frappe.get_doc(
		{"doctype": "Trail", "code": TRAIL, "title": TRAIL, "branch": OFC_A}
	).insert(ignore_permissions=True)

	u = frappe.get_doc(
		{"doctype": "User", "email": USER, "first_name": "ZZ Mandor", "send_welcome_email": 0}
	)
	u.append("roles", {"role": "System Manager"})
	u.insert(ignore_permissions=True)
	# Cabang mandor. Field-nya Custom Field milik crm_cakra; kalau belum ada,
	# apps memang jatuh ke "semua cabang" dan separuh pemeriksaan di bawah tidak
	# ada artinya -- jadi dihentikan di sini, bukan lolos diam-diam.
	assert frappe.get_meta("User").get_field("branch"), (
		"Custom Field User.branch belum terpasang; pembatasan cabang mandor tidak bisa diuji"
	)
	frappe.db.set_value("User", USER, "branch", OFC_A)

	frappe.get_doc(
		{
			"doctype": "User",
			"email": USER_TANPA,
			"first_name": "ZZ Bukan Mandor",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)

	frappe.db.commit()
	# Satu PL satu DPO -- kolom packing_list di DPO unik, jadi dua DPO uji butuh
	# dua PL.
	return _dpo(OFC_A, 2, _packing_list()), _dpo(OFC_B, 1, _packing_list())


def _throws(fn, needle):
	try:
		fn()
	except Exception as e:
		assert needle.lower() in str(e).lower(), f"pesan salah: {e}"
		return
	raise AssertionError(f"harusnya gagal dengan '{needle}', tapi lolos")


def run():
	dpo_a, dpo_b = _setup()
	item1, item2 = dpo_a.items[0].name, dpo_a.items[1].name
	frappe.set_user(USER)
	try:
		assert api.me()["branch"] == OFC_A

		# Cabang: daftar rapi TIDAK cukup. Nomor DPO berurutan dan gampang
		# ditebak, jadi endpoint detailnya ikut diuji.
		nama_daftar = [r["name"] for r in api.orders()]
		assert dpo_a.name in nama_daftar and dpo_b.name not in nama_daftar
		_throws(lambda: api.order(dpo_b.name), "cabang lain")

		# Menyimpan lewat HP harus melewati validate Dispatch Order, bukan
		# menulis kolom begitu saja.
		hasil = api.simpan_item(item1, driver=DRV_A, vehicle=VEH_A, chasis=TRAIL, atd=today())
		baris = next(i for i in hasil["items"] if i["name"] == item1)
		assert baris["driver"] == DRV_A and baris["vehicle"] == VEH_A and baris["chasis"] == TRAIL
		assert baris["driver_nama"] == DRV_A, "nama sopir untuk dibaca tidak ikut terkirim"

		# Satu sopir satu job berjalan: baris kedua tanpa ATA harus ditolak.
		_throws(
			lambda: api.simpan_item(item2, driver=DRV_A, vehicle=VEH_A, atd=today()),
			"tanpa ATA",
		)
		# ATD wajib begitu barisnya mulai diisi.
		_throws(lambda: api.simpan_item(item2, driver=DRV_B, vehicle=VEH_A), "ATD")

		# Assign parsial: item2 masih kosong, jadi dilaporkan namanya, bukan
		# membatalkan assign item1.
		r = api.assign(dpo_a.name)
		assert r["hasil"]["assigned"] == 1 and r["hasil"]["missing"]
		baris = next(i for i in r["order"]["items"] if i["name"] == item1)
		# Punya trip TIDAK mengunci apa pun -- yang mengunci hanya ATA terisi
		# (`_lock_assigned_items`). Kalau apps memakai aturan lama, mandor
		# diblokir untuk baris yang sebenarnya masih boleh dia perbaiki.
		assert baris["assigned"] == 1 and baris["terkunci"] == 0

		# Halaman detail menggambar Route dan Map dari SATU panggilan ini. Kalau
		# salah satu bagiannya hilang, layarnya cuma kosong tanpa error -- jadi
		# bentuknya ikut dikunci di sini.
		d = r["order"]
		assert set(d) >= {"route", "trips", "armada"}, "payload detail tidak lengkap"
		langkah = d["trips"][item1][0]["steps"]
		assert langkah[0]["step_type"] == "Assign" and langkah[0]["start"], (
			"step Assign trip 1 harus ada dan berjam"
		)
		assert [s["step_type"] for s in langkah][-1] == "Menuju Garasi"

		# Ritase: mandor boleh Tambah / Ubah / Hapus, dan nomor tripnya dihitung
		# doctype -- bukan apps. Nomor itu dipakai menagih, jadi kalau dua tempat
		# menghitungnya sendiri-sendiri yang menyimpang adalah tagihan.
		#
		# Ritase berikutnya baru boleh jalan sesudah yang sebelumnya selesai:
		# satu truk tidak bisa berada di dua tempat (`_no_vehicle_overlap`).
		# Jadi trip 1 ditutup dulu, persis seperti urutan di lapangan.
		besok = add_days(today(), 1)
		api.ubah_trip(item1, 1, driver=DRV_A, vehicle=VEH_A, atd=today(), ata=today())

		r = api.tambah_trip(item1, driver=DRV_A, vehicle=VEH_A, atd=besok)
		assert r["hasil"]["trip"] == 2
		trip = r["order"]["trips"][item1]
		assert [t["trip"] for t in trip] == [1, 2]
		assert trip[1]["steps"], "ritase baru harus punya step, bukan baris kosong"

		r = api.ubah_trip(item1, 2, driver=DRV_B, vehicle=VEH_A, atd=besok)
		assert next(t for t in r["order"]["trips"][item1] if t["trip"] == 2)["driver"] == DRV_B
		# ATA item = ATA ritase TERAKHIR dan hanya kalau semuanya selesai; trip 2
		# masih terbuka, jadi item ikut terbuka lagi.
		assert next(i for i in r["order"]["items"] if i["name"] == item1)["terkunci"] == 0

		r = api.hapus_trip(item1, 2)
		assert [t["trip"] for t in r["order"]["trips"][item1]] == [1]

		# Ritase terhapus DIARSIP, bukan hilang: itu bahan pemeriksaan kalau
		# nanti ada tagihan yang dipersoalkan.
		arsip = frappe.db.sql(
			"select count(*) from history.dispatch_order_history where dpo_item = %s and trip = 2",
			(item1,),
		)[0][0]
		assert arsip, "step ritase terhapus tidak sampai ke history.dispatch_order_history"

		# Tinggal trip 1 yang sudah ber-ATA -> job selesai, driver/vehicle jadi
		# catatan sejarah dan terkunci.
		baris = next(i for i in r["order"]["items"] if i["name"] == item1)
		assert baris["ata"] and baris["terkunci"] == 1
		_throws(
			lambda: api.simpan_item(
				item1, driver=DRV_B, vehicle=VEH_A, chasis=TRAIL, atd=today(), ata=today()
			),
			"terkunci",
		)

		# Pemilih juga dibatasi cabang; kalau tidak, mandor bisa meng-assign unit
		# cabang lain dan baru ketahuan saat unitnya tidak pernah datang.
		# Pemilih Driver: yang belum absen tetap DIKIRIM, tapi tidak boleh dipakai
		# dan alasannya ikut. Kalau `boleh` hilang, layar berhenti memblokir
		# tanpa satu pun error -- dan itu baru ketahuan saat sopir yang izin
		# terlanjur di-assign.
		daftar = {d["name"]: d for d in api.drivers()}
		assert set(daftar) == {DRV_A, DRV_B}
		assert daftar[DRV_B]["boleh"] == 0 and "absen" in daftar[DRV_B]["keterangan"].lower()
		assert [v["name"] for v in api.vehicles()] == [VEH_A]

		# Papan absensi: sopir yang BELUM absen wajib muncul -- itu justru yang
		# dicari mandor pagi-pagi.
		papan = api.absensi()
		urut = [r["driver"] for r in papan["rows"]]
		assert set(urut) == {DRV_A, DRV_B} and papan["ringkas"].get("Belum Absen") == 2

		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "Driver Attendance",
				"driver": DRV_A,
				"type": "Absensi",
				"timestamp": frappe.utils.now_datetime(),
				"unique_key": f"{DRV_A}|{today()}",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)
		papan = api.absensi()
		assert next(r for r in papan["rows"] if r["driver"] == DRV_A)["status"] == "Absensi"
		assert papan["rows"][0]["driver"] == DRV_B, "yang belum absen harus di atas"

		# Potongan halaman: apps memuat 5 dulu lalu menambah saat digulir. `ringkas`
		# dan `total` HARUS tetap menghitung seluruh sopir cabang -- kalau ikut
		# terpotong, angka chip di layar berubah tiap kali mandor menggulir.
		hal = api.absensi(limit=1)
		assert len(hal["rows"]) == 1 and hal["total"] == 2
		assert sum(hal["ringkas"].values()) == 2
		assert api.absensi(start=1, limit=1)["rows"][0]["driver"] == DRV_A

		# Papan absensi dan pemilih Driver membaca sumber yang SAMA. Dulu dua
		# tempat menghitung status sendiri-sendiri dan langsung menyimpang.
		daftar = {d["name"]: d for d in api.drivers()}
		assert daftar[DRV_A]["status"] == "Absensi" and daftar[DRV_A]["boleh"] == 1

		# Sopir yang check in sekalian memilih kendaraan; nopol itulah yang
		# diisikan apps saat sopirnya dipilih.
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "Driver Attendance",
				"driver": DRV_A,
				"type": "Check In",
				"timestamp": frappe.utils.now_datetime(),
				"vehicle": VEH_A,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)
		daftar = {d["name"]: d for d in api.drivers()}
		assert daftar[DRV_A]["status"] == "Ready" and daftar[DRV_A]["vehicle"] == VEH_A

		# Wewenang menempel pada izin Dispatch Order, bukan pada role bernama
		# khusus. User tanpa izin itu harus ditolak di endpoint, bukan sekadar
		# tidak melihat menunya.
		frappe.set_user(USER_TANPA)
		_throws(api.me, "berhak")

		print("OK - semua pemeriksaan apps mandor lolos")
	finally:
		frappe.set_user("Administrator")
		_cleanup()
		frappe.db.commit()

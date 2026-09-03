"""Self-check alur apps sopir. Jalankan:

    bench --site erp.localhost execute erp.fleet.api.test_mobile_driver.run

Membuat data uji berprefix ZZTEST lalu menghapusnya lagi. Yang diperiksa adalah
keputusan yang bisa salah diam-diam: jarak haversine, penolakan di luar radius,
GPS truk basi yang TIDAK boleh menolak sopir, dan urutan absen -> check in.
"""

import base64
import io

import frappe

from erp.fleet.api import mobile_driver as api


def _jpeg():
	"""JPEG asli sekecil mungkin -- Frappe memproses gambar, blob palsu ditolak."""
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (8, 8), (30, 30, 30)).save(buf, "JPEG")
	return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


DRIVER = "ZZTEST-DRV"
VEHICLE = "ZZTEST-VEH"
USER = "zztest-driver@example.com"
JOB_TAG = "ZZTEST-JOB"
TRAIL = "ZZTEST-TRAIL"

# Titik acuan: Tanjung Perak. NEAR ~120 m ke timur (di dalam radius baku 200 m),
# FAR ~11 km ke utara.
LAT, LNG = -7.2050, 112.7300
NEAR = (-7.2050, 112.7311)
FAR = (-7.1050, 112.7300)


def _cleanup():
	vehicles = frappe.get_all("Vehicle", filters={"no_lambung": VEHICLE}, pluck="name")
	for parent in frappe.get_all(
		"Dispatch Order Item", filters={"container_no": JOB_TAG}, pluck="parent"
	):
		frappe.delete_doc("Dispatch Order", parent, force=True, ignore_permissions=True)
	for dt, filters in (
		("Driver Location Log", {"driver": DRIVER}),
		("Driver Attendance", {"driver": DRIVER}),
		("GPS Vehicle", {"device_id": VEHICLE}),
	):
		for row in frappe.get_all(dt, filters=filters, pluck="name"):
			frappe.delete_doc(dt, row, force=True, ignore_permissions=True)
	for name in vehicles:
		frappe.delete_doc("Vehicle", name, force=True, ignore_permissions=True)
	for n in frappe.get_all("Notification Log", filters={"for_user": USER}, pluck="name"):
		frappe.delete_doc("Notification Log", n, force=True, ignore_permissions=True)
	if frappe.db.exists("Trail", TRAIL):
		frappe.delete_doc("Trail", TRAIL, force=True, ignore_permissions=True)
	for dt, name in (("Driver", DRIVER), ("User", USER)):
		if frappe.db.exists(dt, name):
			frappe.delete_doc(dt, name, force=True, ignore_permissions=True)


def _setup():
	_cleanup()
	frappe.get_doc({"doctype": "User", "email": USER, "first_name": "ZZ Test Driver",
	                "send_welcome_email": 0}).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Driver", "code": DRIVER, "title": "ZZ Test Driver",
	                "user": USER}).insert(ignore_permissions=True)
	frappe.get_doc({
		"doctype": "Vehicle", "title": VEHICLE, "no_lambung": VEHICLE,
		"branch": frappe.get_all("CMI Office", pluck="name", limit=1)[0],
		"variant": frappe.get_all("Vehicle Variant", pluck="name", limit=1)[0],
	}).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Trail", "code": TRAIL, "title": "ZZ Test Trail"}).insert(
		ignore_permissions=True)
	veh = frappe.get_all("Vehicle", filters={"no_lambung": VEHICLE}, pluck="name")[0]
	frappe.get_doc({"doctype": "GPS Vehicle", "vehicle": veh, "device_id": VEHICLE,
	                "latitude": LAT, "longitude": LNG,
	                "last_seen": frappe.utils.now_datetime()}).insert(ignore_permissions=True)
	return veh


def _throws(fn, needle):
	try:
		fn()
	except Exception as e:
		assert needle.lower() in str(e).lower(), f"pesan salah: {e}"
		return
	raise AssertionError(f"harusnya gagal dengan '{needle}', tapi lolos")


def run():
	veh = _setup()
	frappe.set_user(USER)
	try:
		# jarak: haversine harus masuk akal, bukan sekadar tidak error
		d = api._distance_m(LAT, LNG, *NEAR)
		assert 100 < d < 150, f"jarak dekat meleset: {d} m"

		# Jarak yang dibaca sopir: meter di bawah 1 km, km di atasnya, dengan titik
		# ribuan dan koma desimal seperti tulisan angka Indonesia.
		assert api._jarak_teks(120) == "120 m"
		assert api._jarak_teks(999) == "999 m"
		assert api._jarak_teks(1000) == "1,0 km"
		assert api._jarak_teks(1419624) == "1.419,6 km"
		assert api._distance_m(LAT, LNG, *FAR) > 10000

		assert api.me()["status"] == "Belum Absen"

		# check in sebelum absen harus ditolak
		_throws(lambda: api.check_in(veh, *NEAR), "Absensi dulu")

		# Absen jauh dari truk harus ditolak, dan menolaknya TIDAK boleh
		# meninggalkan baris absensi -- kalau tertinggal, sopir itu terhitung
		# sudah absen tapi tidak pernah bisa check in seharian.
		_throws(lambda: api.absensi(vehicle=veh, latitude=FAR[0], longitude=FAR[1]), "batas maksimal adalah 200 m")
		assert api.me()["status"] == "Belum Absen"

		# Absen tanpa foto boleh selama setelannya mati (baku), dan sekali tekan
		# sopir langsung siap kerja -- bukan absen dulu lalu check in terpisah.
		res = api.absensi(vehicle=veh, latitude=NEAR[0], longitude=NEAR[1])
		assert res["status"] == "Ready" and 100 < res["distance_m"] < 150

		# Satu kendaraan satu sopir. Yang menjamin bukan pemeriksaan di kode --
		# dua sopir yang menekan bersamaan sama-sama membaca "tersedia" sebelum
		# salah satunya menyimpan. Yang memutuskan indeks unik `vehicle_lock`,
		# jadi keberadaannya ikut dikunci di sini.
		kunci = f"{veh}|{frappe.utils.today()}"
		assert frappe.db.get_value(
			"Driver Attendance", {"driver": DRIVER, "type": "Check In"}, "vehicle_lock"
		) == kunci
		_throws(
			lambda: frappe.get_doc({
				"doctype": "Driver Attendance", "driver": DRIVER, "type": "Check In",
				"timestamp": frappe.utils.now_datetime(), "vehicle": veh,
				"vehicle_lock": kunci,
			}).insert(ignore_permissions=True),
			"vehicle_lock",
		)
		assert api.me()["siap"] is True and api.me()["vehicle"] == veh
		_throws(lambda: api.absensi(vehicle=veh, latitude=NEAR[0], longitude=NEAR[1]), "sudah absen")

		# Pemeriksaan "sudah absen" di atas tidak menangkap dua ketukan yang jalan
		# bersamaan -- keduanya membaca sebelum salah satunya menulis. Yang menahan
		# itu indeks unik di database, jadi keberadaannya ikut dikunci di sini.
		_throws(
			lambda: frappe.get_doc({
				"doctype": "Driver Attendance", "driver": DRIVER, "type": "Absensi",
				"timestamp": frappe.utils.now_datetime(),
				"unique_key": f"{DRIVER}|{frappe.utils.today()}",
			}).insert(ignore_permissions=True),
			"unique",
		)

		# Absensi tadi sudah sekalian check in, jadi check in kedua ditolak.
		_throws(lambda: api.check_in(veh, *NEAR), "sudah check in")

		# GPS truk basi tidak boleh menolak sopir -- cuma ditandai
		gps = frappe.get_all("GPS Vehicle", filters={"vehicle": veh}, pluck="name")[0]
		frappe.db.set_value("GPS Vehicle", gps, "last_seen",
		                    frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-10))
		frappe.clear_document_cache("Fleet Settings")
		prox = api._proximity(veh, *FAR)
		assert prox.stale == 1 and prox.within is None, "GPS basi malah dipakai menghakimi"

		p = api.ping(*NEAR)
		assert p["gps_stale"] == 1

		assert api.check_out(*NEAR)["status"] == "Check Out"

		# Check Out melepas kuncinya -- itulah yang membuat sopir lain baru bisa
		# memakai truk itu setelah pemakainya berhenti menerima job.
		assert not frappe.db.get_value(
			"Driver Attendance", {"driver": DRIVER, "type": "Check In"}, "vehicle_lock"
		), "kunci kendaraan tidak dilepas saat check out"
		assert api.me()["status"] == "Check Out"

		# Izin/sakit diinput kantor lewat Driver Attendance, bukan oleh sopir. Harus
		# ikut terbaca apps -- kalau tidak, sopir yang sedang sakit tetap tampil
		# "Check Out" biasa dan tidak ada yang tahu bedanya dari layar HP-nya.
		frappe.set_user("Administrator")
		izin = frappe.get_doc({"doctype": "Driver Attendance", "driver": DRIVER,
		                       "type": "Sakit", "timestamp": frappe.utils.now_datetime()}
		                      ).insert(ignore_permissions=True)
		frappe.set_user(USER)
		assert api.me()["status"] == "Sakit", "izin/sakit tidak terbaca apps"
		frappe.set_user("Administrator")
		frappe.delete_doc("Driver Attendance", izin.name, force=True, ignore_permissions=True)
		frappe.set_user(USER)

		# Sopir bisa sedang menjalankan job SEKALIGUS belum absen hari ini: job
		# yang berangkat kemarin dan belum tiba. Tombol absennya wajib tetap
		# muncul, jadi ketiga keadaan ini harus berdiri sendiri -- bukan satu
		# status berjenjang di mana "On Job" menimpa "Belum Absen".
		frappe.set_user("Administrator")
		# Tanpa packing_list: kolom itu unik (1 PL = 1 DO) jadi tidak bisa dipinjam,
		# dan tidak diperlukan karena penandaan langkah menulis langsung ke baris
		# anak, bukan menyimpan induknya.
		do = frappe.get_doc({"doctype": "Dispatch Order"})
		do.append("items", {"assigned": 1, "driver": DRIVER, "container_no": JOB_TAG,
		                    "atd": frappe.utils.today()})
		do.insert(ignore_permissions=True, ignore_mandatory=True)
		for a in frappe.get_all("Driver Attendance", filters={"driver": DRIVER}, pluck="name"):
			frappe.delete_doc("Driver Attendance", a, force=True, ignore_permissions=True)

		frappe.set_user(USER)
		me = api.me()
		assert me["on_job"] is True, "job berjalan tidak terbaca"
		assert me["sudah_absen"] is False, "absen hari ini tertimpa status job"
		assert me["siap"] is False
		_throws(lambda: api.check_in(veh, *NEAR), "Absensi dulu")

		# Berhenti menerima job harus ditolak selama job masih berjalan. Selama
		# filter `_active_jobs` rusak, blokir ini tidak pernah aktif sekali pun.
		# Sekalian jalur foto: masih boleh dikirim walau setelannya mati.
		assert api.absensi(
			vehicle=veh, photo=_jpeg(), latitude=NEAR[0], longitude=NEAR[1]
		)["status"] == "Ready"
		_throws(lambda: api.check_out(*NEAR), "job berjalan")

		# Kerangka langkah sudah dibuat saat assign, jadi baris "Accept Job" SELALU
		# ada sejak awal dengan start kosong. Yang menentukan job sudah diterima
		# adalah start-nya. Kalau yang diperiksa keberadaan barisnya, setiap job
		# dijawab "sudah diterima" dan tidak ada sopir yang bisa menerima apa pun.
		frappe.set_user("Administrator")
		dpo = frappe.get_doc("Dispatch Order", do.name)
		# `atd` wajib ada di baris trip yang punya driver -- validasi Dispatch Order
		# memeriksanya di baris trip, bukan di item.
		hari = frappe.utils.today()
		dpo.append("trip_log", {"dpo_item": dpo.items[0].name, "trip": 1, "driver": DRIVER,
		                        "step": 1, "step_type": "Accept Job", "atd": hari})
		dpo.append("trip_log", {"dpo_item": dpo.items[0].name, "trip": 1, "driver": DRIVER,
		                        "step": 2, "step_type": "Lanjut Job", "atd": hari})
		# ATD dipasang ulang: validasi Dispatch Order mewajibkannya untuk tiap trip,
		# dan langkah sebelumnya di uji ini sempat menutup item.
		dpo.items[0].atd = frappe.utils.today()
		dpo.items[0].ata = None
		dpo.flags.ignore_mandatory = True  # DO uji sengaja tanpa packing_list
		dpo.save(ignore_permissions=True)

		frappe.set_user(USER)
		item = dpo.items[0].name
		_throws(lambda: api.accept_job(item), "Pilih chasis")

		# Tengah malam: absensi kemarin tidak berlaku lagi, jadi job BARU ditolak
		# sampai sopir absen lagi. Ditiru dengan memundurkan absensi hari ini ke
		# kemarin -- persis keadaan sopir yang apps-nya menyala melewati jam 00:00.
		absen = frappe.get_all("Driver Attendance",
		                       filters={"driver": DRIVER, "type": "Absensi"}, pluck="name")
		kemarin = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-1)
		for a in absen:
			frappe.db.set_value("Driver Attendance", a, "timestamp", kemarin,
			                    update_modified=False)
		assert api.me()["sudah_absen"] is False, "absensi kemarin masih dianggap hari ini"
		_throws(lambda: api.accept_job(item, trail=TRAIL), "Absensi dulu hari ini")
		for a in absen:
			frappe.db.set_value("Driver Attendance", a, "timestamp",
			                    frappe.utils.now_datetime(), update_modified=False)
		assert api.accept_job(item, trail=TRAIL)["ok"], 			"job dengan kerangka langkah tidak bisa diterima"
		_throws(lambda: api.accept_job(item, trail=TRAIL), "sudah Anda terima")
		assert frappe.db.get_value("Dispatch Order Route",
		                           {"dpo_item": item, "step_type": "Accept Job"}, "start")

		# Job tidak boleh ditutup selama nomor kontainernya belum dibenarkan sopir.
		# Ditolak DI SERVER, bukan cuma disembunyikan tombolnya.
		_throws(lambda: api.mark_step(item, "Lanjut Job"), "Konfirmasi nomor")

		# Nomor kontainer: format wajib 4 huruf + 7 angka, dan nomor dari kantor
		# tidak boleh tertimpa.
		_throws(lambda: api.confirm_container(item, "-"), "4 huruf")
		_throws(lambda: api.confirm_container(item, "TCLU123456"), "4 huruf")
		api.confirm_container(item, " tclu-123-456-7 ")
		row = frappe.db.get_value("Dispatch Order Item", item,
		                          ["container_no", "container_tms"], as_dict=True)
		assert row.container_tms == "TCLU1234567", row
		assert row.container_no == JOB_TAG, "nomor dari kantor ikut tertimpa"

		assert api.mark_step(item, "Lanjut Job")["ok"]
		_throws(lambda: api.mark_step(item, "Lanjut Job"), "sudah ditandai")
		_throws(lambda: api.mark_step(item, "Assign"), "tidak dikenal")

		# Ritase kedua: `add_trip` mengulang seluruh langkah dari nomor 1 lagi.
		# Kalau langkahnya tidak disaring per ritase, baris Accept Job ritase
		# PERTAMA yang sudah berisi waktu terbaca duluan dan job ritase kedua
		# dijawab "sudah Anda terima" -- selamanya tidak bisa diterima. Langkah
		# yang tampil pun berselang-seling antar ritase, terlihat ganda.
		# Barisnya disisipkan langsung, bukan lewat save() induk: menyimpan Dispatch
		# Order menjalankan validasi ATD/assign yang tidak ada hubungannya dengan
		# yang sedang diuji di sini.
		frappe.set_user("Administrator")
		for i, tipe in enumerate(("Assign", "Accept Job", "Lanjut Job"), 1):
			frappe.db.sql(
				"""insert into `tabDispatch Order Route`
				   (name, parent, parenttype, parentfield, idx, creation, modified,
				    owner, modified_by, dpo_item, trip, driver, step, step_type, atd)
				   values (%s, %s, 'Dispatch Order', 'trip_log', %s, now(), now(),
				           'Administrator', 'Administrator', %s, 2, %s, %s, %s, %s)""",
				(f"ZZTRIP2-{i}", do.name, 100 + i, item, DRIVER, i, tipe,
				 frappe.utils.today()),
			)
		frappe.db.commit()

		frappe.set_user(USER)
		langkah = api.job_detail(item)["steps"]
		assert {r["trip"] for r in langkah} == {2}, "langkah ritase lama ikut tampil"
		assert len(langkah) == 3, langkah
		assert api.accept_job(item, trail=TRAIL)["ok"], "ritase kedua tidak bisa diterima"
		assert api.mark_step(item, "Lanjut Job")["ok"]

		# Akun login diturunkan dari Driver, dan harus gugur saat sopir keluar.
		frappe.set_user("Administrator")
		d = frappe.get_doc("Driver", DRIVER)
		assert d.username_apps, "username apps tidak ter-generate"
		assert frappe.db.get_value("User", d.user, "username") == d.username_apps
		assert frappe.db.get_value("User", d.user, "user_type") == "Website User", \
			"sopir jangan diberi akses desk"

		# Password yang tertulis di form Driver harus benar-benar bisa dipakai
		# login. Kalau keduanya menyimpang tidak ada error apa pun -- ketahuannya
		# baru saat sopir gagal masuk di lapangan.
		from erp.expedition.doctype.driver.driver import password_matches

		assert password_matches(d.user, d.get_password("password_apps")), \
			"password di form Driver tidak sama dengan password login"
		d.quit_date = "2026-01-01"
		d.save(ignore_permissions=True)
		assert frappe.db.get_value("User", d.user, "enabled") == 0, \
			"sopir sudah keluar tapi akunnya masih hidup"

		# Sesi yang sudah telanjur berjalan di HP juga harus ditolak, bukan hanya
		# login berikutnya -- mematikan User tidak membunuh sesi yang aktif.
		frappe.set_user(USER)
		_throws(api.me, "aktif")

		# Nomor kontainer: "-" dan nomor setengah jadi harus dianggap kosong,
		# bukan sekadar berbeda -- itu yang membuka jalan job ditutup tanpa nomor.
		assert api._container_bersih("cmio-213-312-1") == "CMIO2133121"
		assert api._container_bersih("CMIO2133121") == "CMIO2133121"
		for salah in ("-", "", None, "CMIO213312", "CMIO21331211", "CMI21331211"):
			assert api._container_bersih(salah) == "", f"nomor tidak sah lolos: {salah!r}"

		print("OK - semua pemeriksaan alur sopir lolos")
	finally:
		frappe.set_user("Administrator")
		_cleanup()
		frappe.db.commit()

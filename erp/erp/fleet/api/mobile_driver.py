"""API apps sopir Android (/driver). Modul mobile.

Identitas sopir SELALU diambil dari sesi, tidak pernah dari parameter client --
sopir tidak bisa mengaku jadi sopir lain hanya dengan mengubah request. Login
memakai Frappe User biasa (role "Driver"); tidak ada mekanisme auth sendiri.

Alur: Absensi (selfie) -> Check In (pilih vehicle, cek radius) -> Accept Job
-> cek posisi berkala -> Check Out.
"""

import re
from math import asin, cos, radians, sin, sqrt

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, now_datetime, today

MAX_PHOTO_BYTES = 3 * 1024 * 1024

# Nomor kontainer/isotank ISO: 4 huruf lalu 7 angka. Kantor kadang mengisi "-"
# atau nomor setengah jadi; semua itu dianggap belum terisi, bukan sekadar beda.
CONTAINER_RE = re.compile(r"^[A-Z]{4}[0-9]{7}$")


def _container_bersih(v):
	"""Nomor tanpa strip/spasi dan huruf besar. String kosong kalau tidak sah."""
	v = re.sub(r"[^A-Za-z0-9]", "", str(v or "")).upper()
	return v if CONTAINER_RE.match(v) else ""


# ---------------------------------------------------------------- dasar


def _driver():
	"""Driver milik user yang sedang login. Throw kalau tidak tertaut.

	Syarat aktif diperiksa lagi di sini, bukan hanya lewat User.enabled: sopir
	yang di-disable atau sudah `quit_date` bisa saja masih punya sesi berjalan
	di HP-nya, dan mematikan User tidak otomatis membunuh sesi itu.
	"""
	d = frappe.db.get_value(
		"Driver",
		{"user": frappe.session.user, "disabled": 0, "quit_date": ["in", [None, ""]]},
		["name", "title", "code", "branch", "image", "phone_number"],
		as_dict=True,
	)
	if not d:
		frappe.throw(_("Akun ini tidak tertaut ke data Driver yang aktif."), frappe.PermissionError)
	return d


def _config():
	s = frappe.get_cached_doc("Fleet Settings")
	return frappe._dict(
		radius_m=cint(s.driver_radius_m) or 200,
		stale_minutes=cint(s.gps_stale_minutes) or 60,
		# Setelan foto tinggal di ERPNext Custom Setting > tab Driver, bukan di
		# Fleet Settings: itu tombol kebijakan HRD, bukan ambang teknis GPS.
		absen_foto=cint(
			frappe.db.get_single_value("ERPNext Custom Setting", "driver_absen_pakai_foto")
		),
		check_minutes=cint(s.driver_check_minutes) or 60,
		silent_multiplier=cint(s.driver_silent_multiplier) or 2,
		block_without_gps=cint(s.block_without_gps),
	)


def _jarak_teks(meter):
	"""Jarak yang bisa dibaca sopir: meter di bawah 1 km, di atas itu km.

	"1419624 m" itu angka yang benar dan sama sekali tidak terbaca -- sopir harus
	menghitung digit dulu untuk tahu itu jauh. Yang perlu dia tahu cuma "1.419,6
	km", dan angka sebenarnya tetap tersimpan di Driver Location Log.
	"""
	meter = cint(meter)
	if meter < 1000:
		return f"{meter} m"
	# Format Indonesia: titik ribuan, koma desimal. Python menulisnya terbalik,
	# jadi ditukar lewat penanda sementara.
	return f"{meter / 1000:,.1f}".replace(",", "#").replace(".", ",").replace("#", ".") + " km"


def _distance_m(lat1, lon1, lat2, lon2):
	"""Haversine. Cukup akurat untuk jarak ratusan meter, tanpa dependensi."""
	dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
	a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
	return int(2 * 6371000 * asin(sqrt(a)))


def _proximity(vehicle, lat, lng):
	"""Jarak sopir ke truknya menurut GPS Vehicle.

	GPS truk yang basi TIDAK dipakai menolak sopir -- truk yang parkir semalam
	dengan GPS mati menghasilkan jarak yang tidak bisa dipercaya. Kasus itu
	ditandai `stale` supaya kelihatan di monitor, bukan bikin sopir tidak kerja.
	"""
	out = frappe._dict(distance_m=None, within=None, stale=0, vlat=None, vlng=None, reason=None)
	if not vehicle or lat in (None, "") or lng in (None, ""):
		out.reason = "no_position"
		return out

	gps = frappe.db.get_value(
		"GPS Vehicle",
		{"vehicle": vehicle},
		["latitude", "longitude", "last_seen"],
		as_dict=True,
		order_by="last_seen desc",
	)
	if not gps or not flt(gps.latitude):
		out.reason = "no_gps"
		return out

	cfg = _config()
	out.vlat, out.vlng = flt(gps.latitude), flt(gps.longitude)
	out.distance_m = _distance_m(flt(lat), flt(lng), out.vlat, out.vlng)
	if not gps.last_seen or gps.last_seen < add_to_date(now_datetime(), minutes=-cfg.stale_minutes):
		out.stale = 1
		out.reason = "stale"
		return out
	out.within = out.distance_m <= cfg.radius_m
	return out


def _log(driver, source, lat, lng, vehicle=None, prox=None, item=None):
	prox = prox or frappe._dict()
	frappe.get_doc(
		{
			"doctype": "Driver Location Log",
			"driver": driver,
			"timestamp": now_datetime(),
			"source": source,
			"vehicle": vehicle,
			"latitude": lat,
			"longitude": lng,
			"vehicle_latitude": prox.get("vlat"),
			"vehicle_longitude": prox.get("vlng"),
			"distance_m": prox.get("distance_m"),
			"within_radius": 1 if prox.get("within") else 0,
			"gps_stale": prox.get("stale") or 0,
			"dispatch_order_item": item,
		}
	).insert(ignore_permissions=True)


def _lock(driver):
	"""Kunci baris Driver sampai transaksi ini selesai.

	Tanpa ini, dua ketukan beruntun dari HP yang sama berjalan bersamaan: dua-duanya
	membaca "belum absen" sebelum salah satunya sempat menyimpan, lalu dua-duanya
	menyimpan. Pemeriksaan "sudah absen hari ini" tidak akan pernah menangkap itu
	karena keduanya membaca sebelum ada yang menulis. Sudah pernah terjadi.
	"""
	frappe.db.get_value("Driver", driver, "name", for_update=True)


def _today_attendance(driver):
	return frappe.get_all(
		"Driver Attendance",
		filters={"driver": driver, "timestamp": [">=", today()]},
		fields=["name", "type", "timestamp", "vehicle", "trail"],
		order_by="timestamp asc",
	)


def _active_jobs(driver):
	"""Job yang sudah berangkat dan belum tiba.

	Pakai `is set` / `is not set`, BUKAN `in [None, ""]`: di SQL apa pun yang
	dibandingkan dengan NULL menghasilkan NULL, bukan true, jadi `atd not in
	(NULL, '')` tidak pernah cocok satu baris pun -- diam-diam selalu kosong.
	"""
	return frappe.get_all(
		"Dispatch Order Item",
		filters={
			"driver": driver,
			"assigned": 1,
			"ata": ["is", "not set"],
			"atd": ["is", "set"],
		},
		fields=["name", "parent", "container_no", "dpo_no", "customer", "vehicle"],
	)


# ---------------------------------------------------------------- endpoint


def satu_sesi_sopir(login_manager=None):
	"""Satu akun sopir hanya boleh hidup di satu HP: login baru membunuh yang lama.

	Sopir bergantian memegang HP, dan akun yang tertinggal login di HP lain tetap
	bisa menerima job atas namanya -- absensinya pun tercatat dari lokasi HP yang
	salah. Dipasang di hook `on_login`, yang jalan SEBELUM sesi baru dibuat: jadi
	semua sesi lama boleh dihapus tanpa perlu mengecualikan sesi yang sedang
	dibuat. Hanya berlaku untuk akun yang punya Driver -- user kantor tetap boleh
	membuka beberapa perangkat.
	"""
	from frappe.sessions import clear_sessions

	user = getattr(login_manager, "user", None)
	if not user or not frappe.db.exists("Driver", {"user": user}):
		return
	clear_sessions(user)


@frappe.whitelist()
def csrf():
	"""Token CSRF untuk sesi ini. GET, jadi tidak kena cek CSRF itu sendiri."""
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def me():
	d = _driver()
	rows = _today_attendance(d.name)
	last = rows[-1] if rows else None
	running = _active_jobs(d.name)

	if not last:
		status = "Belum Absen"
	elif last.type in ("Izin", "Sakit"):
		# Izin dan sakit diinput kantor lewat Driver Attendance, bukan oleh sopir.
		# Yang terakhir hari ini menang: sopir yang izin lalu dibatalkan izinnya
		# tinggal diberi baris berikutnya, tidak perlu menghapus apa pun.
		status = last.type
	elif last.type == "Check Out":
		status = "Check Out"
	elif running:
		status = "On Job"
	elif last.type == "Check In":
		status = "Ready"
	else:
		status = "Absensi"

	# Tiga keadaan ini berdiri sendiri, bukan satu tangga. Sopir bisa sedang
	# menjalankan job SEKALIGUS belum absen hari ini -- job yang mulai kemarin
	# dan belum tiba. Kalau apps memakai satu status berjenjang, tombol absennya
	# tertimpa status "On Job" dan sopir itu tidak pernah bisa absen.
	sudah_absen = any(a.type == "Absensi" for a in rows)

	kendaraan = last.vehicle if last and last.type == "Check In" else None
	cfg = _config()
	return {
		"driver": d,
		"status": status,
		"sudah_absen": sudah_absen,
		"siap": bool(last and last.type == "Check In"),
		"on_job": bool(running),
		"attendance": rows,
		"vehicle": kendaraan,
		# Nopol terakhir yang dipakai sopir ini, untuk mengisi sendiri pilihan
		# kendaraan saat dia absen lalu langsung menyatakan siap lagi. Hanya
		# dihitung saat dia memang belum check in -- selebihnya jawabannya sudah
		# ada di `vehicle` dan query union-nya percuma.
		"last_vehicle": kendaraan or _last_vehicle(d.name),
		"active_jobs": len(running),
		# Job yang sedang dikerjakan, untuk kartu status di layar absen. Yang
		# pertama saja: sopir yang menarik dua job sekaligus tetap membawa satu
		# truk, dan kartu itu memang cuma sebaris.
		"job": {"customer": running[0].customer, "vehicle": running[0].vehicle} if running else None,
		"check_minutes": cfg.check_minutes,
		"radius_m": cfg.radius_m,
		"absen_foto": cfg.absen_foto,
		"notif_baru": _unread(),
	}


def _availability(names, kecuali_driver=None):
	"""Kendaraan yang TIDAK tersedia: {nopol: {status, oleh, keterangan}}.

	Dua sebab, dan urutannya penting: kendaraan yang masuk bengkel tidak bisa
	dipakai walaupun ada sopir yang terlanjur check in ke sana, jadi Maintenance
	dinilai lebih dulu.

	`kecuali_driver` mengecualikan sopir yang sedang bertanya -- kalau tidak, sopir
	yang check out lalu mau check in lagi ke truk yang sama akan melihat truknya
	sendiri sebagai "sedang dipakai orang lain".
	"""
	if not names:
		return {}

	out = {}

	# Dipakai: sopir yang sedang check in (belum check out) ATAU job yang sudah
	# berangkat dan belum tiba. Yang pertama menahan truk sejak sopir menyatakan
	# siap, sebelum ada job sama sekali -- tanpa itu dua sopir bisa check in ke
	# truk yang sama di pagi yang sama.
	for r in frappe.db.sql(
		"""
		select a.vehicle, d.name as driver, d.title as driver_name, null as dpo_no
		from `tabDriver Attendance` a
		join `tabDriver` d on d.name = a.driver
		where a.type = 'Check In' and a.timestamp >= %(day)s
		  and ifnull(a.vehicle, '') != '' and a.vehicle in %(names)s
		  and not exists (
		        select 1 from `tabDriver Attendance` o
		        where o.driver = a.driver and o.type = 'Check Out' and o.timestamp > a.timestamp)

		union all

		select i.vehicle, d.name as driver, d.title as driver_name, i.dpo_no
		from `tabDispatch Order Item` i
		join `tabDriver` d on d.name = i.driver
		where i.assigned = 1 and ifnull(i.atd, '') != '' and ifnull(i.ata, '') = ''
		  and ifnull(i.vehicle, '') != '' and i.vehicle in %(names)s
		""",
		{"day": today(), "names": tuple(names)},
		as_dict=True,
	):
		if r.driver == kecuali_driver or r.vehicle in out:
			continue
		out[r.vehicle] = {
			"status": "Dipakai",
			"oleh": r.driver_name,
			"keterangan": _("Sedang dipakai {0}{1}.").format(
				r.driver_name, _(" untuk job {0}").format(r.dpo_no) if r.dpo_no else ""
			),
		}

	# Maintenance: kartu servis yang sudah mulai dan belum ditutup.
	for r in frappe.db.sql(
		"""
		select vehicle, maintenance_type, date
		from `tabMaintenance`
		where ifnull(void, 0) = 0 and vehicle in %(names)s
		  and ifnull(date, %(day)s) <= %(day)s
		  and (finish_date is null or finish_date >= %(day)s)
		""",
		{"day": today(), "names": tuple(names)},
		as_dict=True,
	):
		out[r.vehicle] = {
			"status": "Maintenance",
			"oleh": None,
			"keterangan": _("Sedang di bengkel ({0}) sejak {1}.").format(
				r.maintenance_type or _("perawatan"), frappe.utils.formatdate(r.date)
			),
		}

	return out


# Seluruh armada satu cabang dikirim sekaligus. Cabang terbesar saat ini 113 unit
# (~15 KB), jadi memotongnya per halaman hanya menambah satu cara untuk kehilangan
# unit tanpa disadari. Batas ini murni pengaman kalau armada tumbuh jauh.
VEHICLE_LIMIT = 300

URUTAN_STATUS = {"Tersedia": 0, "Dipakai": 1, "Maintenance": 2}


def _last_vehicle(driver):
	"""Kendaraan terakhir yang benar-benar dipakai sopir ini.

	Dua sumber digabung: check in di apps DAN kendaraan di job yang pernah
	diberikan. Kalau hanya membaca check in, fitur ini diam selama berminggu-minggu
	setelah rilis karena belum ada seorang pun yang punya riwayat di apps.
	"""
	rows = frappe.db.sql(
		"""
		select vehicle from (
			select a.vehicle, a.timestamp as waktu
			from `tabDriver Attendance` a
			where a.driver = %(d)s and a.type = 'Check In' and ifnull(a.vehicle, '') != ''

			union all

			select i.vehicle, cast(ifnull(i.atd, i.creation) as datetime) as waktu
			from `tabDispatch Order Item` i
			where i.driver = %(d)s and ifnull(i.vehicle, '') != ''
		) x
		order by waktu desc
		limit 1
		""",
		{"d": driver},
		as_dict=True,
	)
	return rows[0].vehicle if rows else None


@frappe.whitelist()
def vehicles(q=None):
	"""Kendaraan yang boleh dipilih sopir: cabang sama, aktif, yang tersedia dulu.

	Diurutkan di server, bukan di layar: kalau daftarnya dipotong dulu lalu
	disortir, unit tersedia yang secara abjad ada di urutan ke-90 tidak akan
	pernah muncul -- padahal justru itu yang dicari sopir. Dan yang sibuk tetap
	ikut terkirim, hanya turun ke bawah, supaya sopir yang mencari truknya sendiri
	tahu truk itu ada dan kenapa belum bisa dipakai.

	Kendaraan yang terakhir dipakai sopir ini selalu di baris pertama, apa pun
	statusnya -- itu unit yang paling mungkin dia cari, dan kalau sedang tidak
	tersedia dia justru perlu tahu kenapa.

	Yang ditampilkan dan diurutkan adalah NOPOL, bukan `no_lambung`. Kolom itu di
	data sekarang berisi IMEI (182 dari 258 unit) dan nomor rangka yang sama untuk
	banyak unit -- tidak satu pun nomor lambung asli. Kalau kolom itu sudah dibersihkan,
	tampilkan lagi di depan nopol.
	"""
	d = _driver()
	filters = {"disabled": 0}
	if d.branch:
		filters["branch"] = d.branch
	rows = frappe.get_all(
		"Vehicle",
		filters=filters,
		or_filters=({"name": ["like", f"%{q}%"]}, {"title": ["like", f"%{q}%"]}) if q else None,
		fields=["name", "title", "merk"],
		order_by="name",
		limit=VEHICLE_LIMIT,
	)

	sibuk = _availability([r.name for r in rows], kecuali_driver=d.name)
	terakhir = _last_vehicle(d.name)
	for r in rows:
		r.update(sibuk.get(r.name) or {"status": "Tersedia", "oleh": None, "keterangan": None})
		r["terakhir"] = 1 if r.name == terakhir else 0

	rows.sort(key=lambda r: (0 if r["terakhir"] else 1, URUTAN_STATUS.get(r["status"], 9), r["name"]))
	return rows


@frappe.whitelist()
def trails(q=None):
	d = _driver()
	filters = {"disabled": 0}
	if d.branch:
		filters["branch"] = d.branch
	return frappe.get_all(
		"Trail",
		filters=filters,
		or_filters=({"name": ["like", f"%{q}%"]}, {"title": ["like", f"%{q}%"]}) if q else None,
		fields=["name", "title", "size"],
		order_by="name",
		limit=50,
	)


def _cek_kendaraan(d, vehicle, latitude, longitude):
	"""Kendaraan boleh dipakai sopir ini DAN sopirnya benar-benar ada di sebelahnya.

	Dipakai absensi dan check in dengan aturan yang sama persis. Diperiksa di
	server, bukan cuma dimatikan tombolnya: daftar yang dilihat sopir bisa sudah
	basi beberapa menit, dan sopir lain mungkin baru saja mengambil truk itu.
	"""
	if not vehicle:
		frappe.throw(_("Pilih kendaraan dulu."))

	sibuk = _availability([vehicle], kecuali_driver=d.name).get(vehicle)
	if sibuk:
		# Kalimat sendiri, bukan `keterangan` milik daftar kendaraan: yang di daftar
		# itu penjelasan yang berdiri di samping nama truknya, sedangkan ini jawaban
		# atas satu tombol yang baru saja ditekan -- nopolnya harus ikut disebut.
		# Yang di bengkel tidak punya pemakai, jadi tetap memakai keterangannya.
		if sibuk["oleh"]:
			frappe.throw(_("Ditolak : {0} sedang di pakai {1}").format(vehicle, sibuk["oleh"]))
		frappe.throw(sibuk["keterangan"])

	cfg = _config()
	prox = _proximity(vehicle, latitude, longitude)
	# Semua penolakan di sini memakai bentuk yang sama, "Ditolak : ...", supaya
	# sopir mengenali sebabnya sebelum membaca kalimatnya sampai habis.
	if prox.reason == "no_position":
		frappe.throw(_("Ditolak : lokasi HP tidak terbaca. Nyalakan GPS lalu coba lagi."))
	if prox.reason == "no_gps" and cfg.block_without_gps:
		frappe.throw(_("Ditolak : {0} tidak punya data GPS, posisinya tidak bisa dicek.").format(vehicle))
	if prox.within is False:
		frappe.throw(
			_(
				"Ditolak : Anda {0} jauh dari Kendaraan {1}. Silahkan mendekat ke kendaraan"
				" tersebut karena batas maksimal adalah {2} m."
			).format(_jarak_teks(prox.distance_m), vehicle, cfg.radius_m)
		)
	return prox


@frappe.whitelist()
def absensi(vehicle=None, photo=None, latitude=None, longitude=None):
	"""Absensi masuk DI SAMPING KENDARAAN, langsung diikuti check in.

	Absensi dan check in dulunya dua ketukan terpisah, padahal selalu terjadi di
	tempat dan menit yang sama -- sopir mengerjakan hal yang sama dua kali dan
	sebagian berhenti di tengah, tercatat absen tapi tidak pernah siap kerja.
	Digabung: satu tombol, satu pemeriksaan jarak, dua baris kehadiran.

	Foto selfie hanya wajib kalau ERPNext Custom Setting > Driver menyalakannya.
	Stempel lokasi/waktu di foto itu untuk mata manusia; yang diperiksa sistem
	adalah field latitude/longitude, bukan tulisan di gambar.
	"""
	d = _driver()
	if _config().absen_foto and not photo:
		frappe.throw(_("Foto selfie wajib diambil."))
	_lock(d.name)
	if [a for a in _today_attendance(d.name) if a.type == "Absensi"]:
		frappe.throw(_("Anda sudah absen hari ini."))

	# Jarak diperiksa SEBELUM ada baris tersimpan: kalau sopirnya ternyata jauh
	# dari truk, absensinya memang tidak sah juga, dan tidak boleh tertinggal
	# sebagai baris absen tanpa check in.
	prox = _cek_kendaraan(d, vehicle, latitude, longitude)

	# Pemeriksaan "sudah absen" di atas menangkap kasus biasa, tapi TIDAK dua
	# ketukan yang berjalan bersamaan: dengan isolasi REPEATABLE READ, transaksi
	# kedua sudah membentuk snapshot sebelum yang pertama commit, jadi SELECT-nya
	# tetap melihat "belum ada" -- dan kunci baris pun tidak mengubah itu. Yang
	# bisa memutuskan hanya database. `unique_key` diisi HANYA untuk baris
	# Absensi, jadi check in/out tetap boleh berulang dalam sehari. Sudah pernah
	# terjadi: satu sopir menekan dua kali dan dapat dua absensi untuk hari sama.
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Driver Attendance",
				"driver": d.name,
				"type": "Absensi",
				"timestamp": now_datetime(),
				"vehicle": vehicle,
				"latitude": latitude,
				"longitude": longitude,
				"distance_m": prox.distance_m,
				"gps_stale": prox.stale,
				"unique_key": f"{d.name}|{today()}",
			}
		).insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		# Frappe sudah mengantre "Kunci Unik must be unique" sebelum melempar.
		# Itu nama kolom, bukan kalimat untuk sopir; dibuang dulu.
		frappe.clear_messages()
		frappe.throw(_("Anda sudah absen hari ini."))

	if photo:
		doc.db_set("image", _save_photo(photo, doc.name), update_modified=False)
	_log(d.name, "Absensi", latitude, longitude, vehicle, prox)

	# Check in menyusul lewat pintu yang sama seperti tombolnya sendiri, bukan
	# insert kedua yang ditulis di sini -- aturannya cuma boleh hidup di satu
	# tempat, kalau tidak yang satu ini akan ketinggalan saat aturannya berubah.
	hasil = check_in(vehicle, latitude, longitude)
	return {"name": doc.name, "status": "Ready", **hasil}


def _save_photo(data_url, attendance):
	"""Simpan selfie (data URL base64) sebagai File privat yang menempel ke absensi."""
	if "," in data_url:
		data_url = data_url.split(",", 1)[1]
	if len(data_url) * 3 / 4 > MAX_PHOTO_BYTES:
		frappe.throw(_("Foto terlalu besar."))
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": "selfie-%s.jpg" % attendance,
			"attached_to_doctype": "Driver Attendance",
			"attached_to_name": attendance,
			"attached_to_field": "image",
			"is_private": 1,
			"content": data_url,
			"decode": True,
		}
	).insert(ignore_permissions=True)
	return f.file_url


@frappe.whitelist()
def check_in(vehicle, latitude=None, longitude=None):
	"""Sopir menyatakan siap menerima job, terikat ke satu kendaraan."""
	d = _driver()
	_lock(d.name)
	rows = _today_attendance(d.name)
	if not [a for a in rows if a.type == "Absensi"]:
		frappe.throw(_("Absensi dulu sebelum check in."))
	if rows and rows[-1].type == "Check In":
		frappe.throw(_("Anda sudah check in dengan kendaraan {0}.").format(rows[-1].vehicle))

	prox = _cek_kendaraan(d, vehicle, latitude, longitude)

	# Pemeriksaan `_availability` di atas menangkap kasus biasa, TIDAK menangkap dua
	# sopir yang menekan bersamaan: keduanya membaca "tersedia" sebelum salah
	# satunya menyimpan. Indeks unik `vehicle_lock` yang memutuskan, dan kuncinya
	# dilepas saat Check Out -- itulah sebabnya sopir lain harus menunggu sopir
	# pertama berhenti menerima job.
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Driver Attendance",
				"driver": d.name,
				"type": "Check In",
				"timestamp": now_datetime(),
				"vehicle": vehicle,
				"latitude": latitude,
				"longitude": longitude,
				"distance_m": prox.distance_m,
				"gps_stale": prox.stale,
				"vehicle_lock": f"{vehicle}|{today()}",
			}
		).insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		# Frappe mengantre "Kunci Kendaraan must be unique" sebelum melempar; itu
		# nama kolom, bukan kalimat untuk sopir.
		frappe.clear_messages()
		# `for update` supaya yang terbaca versi TERAKHIR yang sudah commit, bukan
		# snapshot transaksi ini -- snapshot itu terbentuk sebelum sopir lain
		# menyimpan, jadi namanya tidak akan pernah ketemu dan pesannya berhenti
		# di "sopir lain" persis saat sopir butuh tahu harus menghubungi siapa.
		pemakai = frappe.db.sql(
			"""select d.title from `tabDriver Attendance` a join `tabDriver` d on d.name = a.driver
			   where a.vehicle_lock = %s limit 1 for update""",
			f"{vehicle}|{today()}",
		)
		frappe.throw(
			_("Kendaraan {0} baru saja diambil {1}.").format(
				vehicle, pemakai[0][0] if pemakai else _("sopir lain")
			)
		)

	_log(d.name, "Check In", latitude, longitude, vehicle, prox)
	return {
		"name": doc.name,
		"status": "Ready",
		"distance_m": prox.distance_m,
		"gps_stale": prox.stale,
	}


@frappe.whitelist()
def check_out(latitude=None, longitude=None):
	"""Berhenti menerima job. Ditolak selama masih ada job berjalan."""
	d = _driver()
	_lock(d.name)
	rows = _today_attendance(d.name)
	if not rows or rows[-1].type == "Check Out":
		frappe.throw(_("Anda belum check in."))

	running = _active_jobs(d.name)
	if running:
		frappe.throw(
			_("Masih ada {0} job berjalan ({1}). Selesaikan dulu sebelum check out.").format(
				len(running), ", ".join(r.dpo_no or r.container_no or r.name for r in running)
			)
		)

	vehicle = rows[-1].vehicle
	doc = frappe.get_doc(
		{
			"doctype": "Driver Attendance",
			"driver": d.name,
			"type": "Check Out",
			"timestamp": now_datetime(),
			"vehicle": vehicle,
			"latitude": latitude,
			"longitude": longitude,
		}
	).insert(ignore_permissions=True)

	# Kunci kendaraan dilepas DI SINI, bukan saat job selesai: selama sopir masih
	# menyatakan diri siap, truk itu memang masih miliknya.
	for n in frappe.get_all(
		"Driver Attendance",
		filters={"driver": d.name, "vehicle_lock": ["is", "set"]},
		pluck="name",
	):
		frappe.db.set_value("Driver Attendance", n, "vehicle_lock", None, update_modified=False)

	_log(d.name, "Check Out", latitude, longitude, vehicle)
	return {"name": doc.name, "status": "Check Out"}


@frappe.whitelist()
def jobs():
	"""Tugas sopir yang belum tiba, lengkap dengan langkah trip yang tercatat."""
	d = _driver()
	rows = frappe.db.sql(
		"""
		select i.name, i.parent as dispatch_order, i.container_no, i.container_size,
		       i.chasis, i.vehicle, i.customer, i.dpo_no, i.atd, i.ata,
		       o.packing_list, o.origin_location, o.destination_location, o.etd, o.eta
		from `tabDispatch Order Item` i
		join `tabDispatch Order` o on o.name = i.parent
		where i.driver = %(driver)s and i.assigned = 1 and ifnull(i.ata, '') = ''
		order by ifnull(o.etd, o.creation)
		""",
		{"driver": d.name},
		as_dict=True,
	)
	for r in rows:
		# Ritase terakhir saja: kalau digabung, ritase kedua yang belum diterima
		# tetap terbaca "sudah diterima" karena baris Accept Job ritase pertama
		# masih berisi waktu -- tombol Terima Job-nya lalu tidak pernah muncul.
		r["steps"] = _langkah(r.dispatch_order, r.name)
		r["accepted"] = any(s.step_type == "Accept Job" and s.start for s in r["steps"])
	return rows


@frappe.whitelist()
def history(limit=5, start=0, q=None):
	"""Riwayat job sopir, dimuat sepotong-sepotong sambil di-scroll.

	Query-nya dipakai bersama tab Riwayat di form desk. `limit` dibatasi supaya
	client tidak bisa menarik seluruh riwayat sekaligus lewat satu permintaan.
	"""
	from erp.expedition.doctype.driver.driver import job_history

	d = _driver()
	return job_history(d.name, min(cint(limit) or 5, 50), cint(start), q)


def _langkah(parent, dpo_item):
	"""Langkah ritase TERAKHIR item ini, bukan gabungan semua ritase.

	Satu item bisa punya beberapa ritase (`add_trip` di Dispatch Order), dan tiap
	ritase mengulang seluruh langkah dari nomor 1 lagi. Kalau tidak disaring:

	- delapan langkah trip 1 dan delapan langkah trip 2 tersaji berselang-seling
	  karena diurutkan `by step` -- di layar terlihat seperti langkah ganda;
	- penandaan langkah mendarat di baris trip yang SUDAH LEWAT, karena baris
	  "Lanjut Job" trip 1 yang tidak pernah ditekan masih kosong dan terpilih
	  duluan;
	- `accept_job` melihat baris Accept Job trip 1 yang sudah berisi waktu, lalu
	  menjawab "sudah Anda terima" -- ritase kedua tidak pernah bisa diterima.
	"""
	rows = frappe.get_all(
		"Dispatch Order Route",
		filters={"parent": parent, "dpo_item": dpo_item},
		fields=["name", "trip", "step", "step_type", "point", "point_type", "start", "end"],
		order_by="trip, step",
	)
	if not rows:
		return []
	akhir = max(r.trip or 1 for r in rows)
	return [r for r in rows if (r.trip or 1) == akhir]


def _my_item(item):
	"""Baris Dispatch Order Item milik sopir yang login. Throw kalau bukan miliknya."""
	d = _driver()
	row = frappe.db.get_value(
		"Dispatch Order Item",
		{"name": item, "driver": d.name, "assigned": 1},
		["name", "parent", "vehicle", "chasis", "container_no", "container_tms",
		 "container_tms_at", "container_size", "dpo_no", "atd", "ata"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Tugas ini bukan milik Anda."), frappe.PermissionError)
	return d, row


@frappe.whitelist()
def job_detail(item):
	"""Satu job lengkap: identitas, catatan assigner, dan riwayat langkahnya."""
	d, row = _my_item(item)
	order = frappe.db.get_value(
		"Dispatch Order",
		row.parent,
		["name", "customer", "origin_location", "destination_location", "notes",
		 "packing_list", "etd", "eta"],
		as_dict=True,
	)
	row["order"] = order
	row["steps"] = _langkah(row.parent, row.name)
	return row


@frappe.whitelist()
def confirm_container(item, container, latitude=None, longitude=None):
	"""Sopir membenarkan atau meralat nomor kontainer yang di-assign.

	Nomor yang diketik di kantor sering beda dengan yang benar-benar tertempel di
	kontainer. Yang dari kantor TIDAK ditimpa -- ditulis ke kolom terpisah supaya
	selisihnya tetap terlihat dan bisa ditelusuri, bukan hilang diam-diam.
	"""
	d, row = _my_item(item)
	container = _container_bersih(container)
	if not container:
		frappe.throw(
			_("Nomor kontainer/isotank harus 4 huruf lalu 7 angka, contoh CMIO2133121.")
		)

	frappe.db.set_value(
		"Dispatch Order Item",
		row.name,
		{"container_tms": container, "container_tms_at": now_datetime()},
		update_modified=False,
	)
	prox = _proximity(row.vehicle, latitude, longitude)
	_log(d.name, "Konfirmasi Kontainer", latitude, longitude, row.vehicle, prox, item=row.name)
	return {"container_tms": container, "berbeda": container != (row.container_no or "").upper()}


@frappe.whitelist()
def mark_step(item, step_type, latitude=None, longitude=None):
	"""Tandai satu langkah trip sudah dimulai.

	Yang ditandai adalah langkah TERAWAL bertipe itu yang belum dimulai, bukan
	baris yang ditunjuk client -- kalau tidak, urutan trip bisa dilompati hanya
	dengan mengubah request.
	"""
	if step_type not in ("Route", "Lanjut Job", "Menuju Garasi"):
		frappe.throw(_("Langkah tidak dikenal."))

	d, row = _my_item(item)
	mine = _langkah(row.parent, row.name)

	# Job harus diterima dulu. Tombolnya memang disembunyikan di HP, tapi menyembunyikan
	# tombol bukan aturan -- request yang dibuat sendiri tetap bisa menutup job yang
	# tidak pernah diterima siapa pun.
	if not any(r.step_type == "Accept Job" and r.start for r in mine):
		frappe.throw(_("Terima job ini dulu sebelum menandai langkah."))

	# Job tidak boleh ditutup selama nomor kontainernya belum dibenarkan sopir di
	# lapangan. Diperiksa di sini, bukan cuma dengan menyembunyikan tombol: nomor
	# yang salah baru ketahuan berminggu-minggu kemudian saat penagihan.
	if step_type in ("Lanjut Job", "Menuju Garasi") and not _container_bersih(row.container_tms):
		frappe.throw(
			_("Konfirmasi nomor kontainer/isotank dulu (4 huruf lalu 7 angka) sebelum menutup job.")
		)

	target = next((r for r in mine if r.step_type == step_type and not r.start), None)
	if not target:
		frappe.throw(_("Langkah {0} sudah ditandai atau tidak ada.").format(step_type))

	frappe.db.set_value(
		"Dispatch Order Route", target.name, "start", now_datetime(), update_modified=False
	)

	# Lanjut Job dan Menuju Garasi sama-sama mengakhiri trip ini -- aturan yang
	# sama dipakai job_history untuk menandai job selesai.
	if step_type in ("Lanjut Job", "Menuju Garasi"):
		frappe.db.set_value("Dispatch Order Item", row.name, "ata", today(), update_modified=False)

	prox = _proximity(row.vehicle, latitude, longitude)
	_log(d.name, "Langkah Trip", latitude, longitude, row.vehicle, prox, item=row.name)
	return {"ok": True, "step": target.step}


@frappe.whitelist()
def accept_job(item, trail=None, latitude=None, longitude=None):
	"""Terima job dari Dispatch Order. Chasis WAJIB dipilih.

	Chasis menempel pada trip, bukan pada kendaraan: satu truk memakai chasis
	berbeda tiap job. Kalau boleh kosong, yang terjadi adalah kolomnya kosong
	untuk sebagian besar job dan tidak ada yang bisa menelusuri chasis mana yang
	dibawa ke mana.
	"""
	if not trail:
		frappe.throw(_("Pilih chasis dulu sebelum menerima job."))
	d = _driver()

	# Absensi berlaku per hari kalender, jadi tengah malam menghapus kesiapan
	# semua sopir dengan sendirinya: `_today_attendance` hanya melihat baris hari
	# ini. Job BARU cuma boleh diambil sopir yang sudah absen hari ini -- job yang
	# sudah berjalan sengaja tidak ikut terkunci, kalau tidak sopir yang menyeberang
	# tengah malam terjebak dengan muatan di atas truk dan tidak bisa menutupnya.
	if not [a for a in _today_attendance(d.name) if a.type == "Absensi"]:
		frappe.throw(_("Absensi dulu hari ini sebelum menerima job baru."))
	row = frappe.db.get_value(
		"Dispatch Order Item",
		{"name": item, "driver": d.name, "assigned": 1},
		["name", "parent", "vehicle"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Tugas ini bukan milik Anda."), frappe.PermissionError)

	_lock(d.name)
	mine = _langkah(row.parent, row.name)

	# Kerangka langkah SUDAH dibuat `_ensure_trip_rows()` saat assign, jadi baris
	# "Accept Job" selalu ada -- yang menentukan sudah diterima atau belum adalah
	# `start`-nya, bukan keberadaan barisnya. Memeriksa keberadaan baris membuat
	# setiap job dijawab "sudah diterima" dan tidak ada sopir yang bisa menerima
	# apa pun.
	target = next((r for r in mine if r.step_type == "Accept Job"), None)
	if target and target.start:
		frappe.throw(_("Job ini sudah Anda terima."))

	if trail:
		frappe.db.set_value("Dispatch Order Item", row.name, "chasis", trail, update_modified=False)

	if not target:
		frappe.throw(_("Job ini belum punya langkah trip. Hubungi kantor."))

	# Satu stempel waktu di baris anak ditulis langsung, TIDAK lewat save() induk:
	# menyimpan Dispatch Order menjalankan seluruh validasinya (dan penguncian item
	# yang sudah assigned) hanya untuk mengisi satu kolom tanggal.
	frappe.db.set_value(
		"Dispatch Order Route",
		target.name,
		{"start": now_datetime(), "chasis": trail},
		update_modified=False,
	)

	prox = _proximity(row.vehicle, latitude, longitude)
	_log(d.name, "Accept Job", latitude, longitude, row.vehicle, prox, item=row.name)
	return {"ok": True}


@frappe.whitelist()
def ping(latitude, longitude):
	"""Setoran posisi berkala dari HP sopir saat sedang bertugas."""
	d = _driver()
	rows = _today_attendance(d.name)
	vehicle = rows[-1].vehicle if rows and rows[-1].type != "Check Out" else None
	prox = _proximity(vehicle, latitude, longitude)
	_log(d.name, "Berkala", latitude, longitude, vehicle, prox)
	return {
		"distance_m": prox.distance_m,
		"within_radius": prox.within,
		"gps_stale": prox.stale,
		"next_minutes": _config().check_minutes,
	}


@frappe.whitelist()
def silent_drivers():
	"""Sopir yang sedang bertugas tapi berhenti mengirim posisi.

	HP pribadi dimatikan pembatas baterainya oleh pabrikan (Xiaomi/Oppo/Vivo) dan
	apps-nya ikut mati. Data yang berhenti masuk tidak memunculkan error apa pun --
	terlihat sama persis dengan sopir yang baik-baik saja. Jadi kesunyiannya yang
	dihitung di sini, bukan dipercaya begitu saja.
	"""
	cfg = _config()
	cutoff = add_to_date(now_datetime(), minutes=-cfg.check_minutes * cfg.silent_multiplier)
	return frappe.db.sql(
		"""
		select a.driver, d.title as driver_name, d.branch, a.vehicle,
		       max(a.timestamp) as checked_in_at,
		       (select max(l.timestamp) from `tabDriver Location Log` l
		         where l.driver = a.driver and l.timestamp >= %(day)s) as last_seen
		from `tabDriver Attendance` a
		join `tabDriver` d on d.name = a.driver
		where a.timestamp >= %(day)s and a.type = 'Check In'
		  and not exists (
		        select 1 from `tabDriver Attendance` o
		        where o.driver = a.driver and o.type = 'Check Out'
		          and o.timestamp > a.timestamp)
		group by a.driver, d.title, d.branch, a.vehicle
		having ifnull(last_seen, '1900-01-01') < %(cutoff)s
		""",
		{"day": today(), "cutoff": cutoff},
		as_dict=True,
	)


# ---------------------------------------------- notifikasi job (dipanggil desk)


def notify_job_assigned(order, rows):
	"""Beri tahu sopir bahwa job baru masuk untuknya.

	Memakai `Notification Log` bawaan Frappe, bukan doctype baru: sudah punya
	per-user, penanda sudah/belum dibaca, dan tautan ke dokumennya.

	Dikelompokkan per sopir -- lima kontainer yang di-assign sekaligus jadi SATU
	notifikasi, bukan lima. Sopir yang HP-nya berbunyi lima kali untuk satu
	perintah kerja akan berhenti membacanya.
	"""
	per_sopir = {}
	for row in rows:
		if row.driver:
			per_sopir.setdefault(row.driver, []).append(row)

	for sopir, punya in per_sopir.items():
		user = frappe.db.get_value("Driver", sopir, "user")
		if not user:
			# Sopir belum punya akun apps. Bukan error -- job tetap sah, cuma tidak
			# ada yang bisa diberi tahu.
			continue

		judul = punya[0].dpo_no or punya[0].container_no or order.name
		subject = (
			_("Job baru untuk Anda: {0}").format(judul)
			if len(punya) == 1
			else _("{0} job baru untuk Anda, termasuk {1}").format(len(punya), judul)
		)
		# Teks biasa, BUKAN HTML: isinya memuat nomor kontainer yang diketik orang,
		# dan apps merendernya sebagai teks supaya tidak ada jalan masuk skrip.
		isi = "\n".join(
			_("{0} ke {1}").format(
				r.container_no or r.dpo_no or "-", order.destination_location or "-"
			)
			for r in punya
		)

		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"email_content": isi,
				"document_type": "Dispatch Order",
				"document_name": order.name,
			}
		).insert(ignore_permissions=True)


# ------------------------------------------------------- notifikasi (sisi baca)


def _unread():
	return frappe.db.count("Notification Log", {"for_user": frappe.session.user, "read": 0})


@frappe.whitelist()
def unread():
	"""Jumlah notifikasi belum dibaca. Sengaja dipisah dari `me()`.

	Dipanggil berkala oleh apps yang sedang terbuka, jadi harus murah: `me()`
	ikut menghitung absensi, job berjalan, dan ketersediaan kendaraan --
	terlalu mahal ditembak tiap menit hanya demi satu angka di badge.
	"""
	_driver()
	return _unread()


@frappe.whitelist()
def notifications(limit=20):
	"""Notifikasi milik sopir yang sedang login. Selalu disaring ke user sesi ini."""
	_driver()
	return frappe.get_all(
		"Notification Log",
		filters={"for_user": frappe.session.user},
		fields=["name", "subject", "email_content", "read", "creation", "document_name"],
		order_by="creation desc",
		limit=min(cint(limit) or 20, 100),
	)


@frappe.whitelist()
def mark_read(name=None):
	"""Tandai satu notifikasi, atau semuanya kalau `name` kosong.

	Filternya WAJIB menyertakan `for_user`: tanpa itu sopir bisa menandai
	notifikasi milik orang lain hanya dengan menebak namanya.
	"""
	_driver()
	filters = {"for_user": frappe.session.user, "read": 0}
	if name:
		filters["name"] = name
	for n in frappe.get_all("Notification Log", filters=filters, pluck="name"):
		frappe.db.set_value("Notification Log", n, "read", 1, update_modified=False)
	return _unread()


# ------------------------------------------------------- reward & slip gaji


@frappe.whitelist()
def rewards(limit=20, start=0):
	"""Reward sopir yang login. Hanya yang sudah di-submit.

	Draft sengaja disembunyikan: reward yang masih diketik admin tidak boleh
	terlanjur terbaca sopir lalu dianggap janji.
	"""
	d = _driver()
	rows = frappe.get_all(
		"Driver Reward",
		filters={"driver": d.name, "docstatus": 1},
		fields=["name", "reward_date", "reward_type", "amount", "note"],
		order_by="reward_date desc, creation desc",
		limit=min(cint(limit) or 20, 100),
		limit_start=cint(start),
	)
	total = frappe.db.sql(
		"""select ifnull(sum(amount), 0) from `tabDriver Reward`
		   where driver = %s and docstatus = 1""",
		(d.name,),
	)[0][0]
	return {"rows": rows, "total": total}


@frappe.whitelist()
def slipgaji(limit=12, start=0):
	"""Slip gaji sopir yang login, lengkap dengan rinciannya.

	Rincian ikut dikirim sekalian, bukan lewat panggilan kedua per slip: satu
	sopir paling banyak 12 slip setahun, jadi lebih murah sekali angkut
	daripada satu permintaan tiap kali baris dibuka di HP.
	"""
	d = _driver()
	rows = frappe.get_all(
		"Driver Slipgaji",
		filters={"driver": d.name, "docstatus": 1},
		fields=[
			"name", "periode", "from_date", "to_date",
			"total_pendapatan", "total_potongan", "gaji_bersih", "note",
		],
		order_by="from_date desc",
		limit=min(cint(limit) or 12, 60),
		limit_start=cint(start),
	)
	if rows:
		rincian = frappe.get_all(
			"Driver Slipgaji Item",
			filters={"parent": ("in", [r.name for r in rows])},
			fields=["parent", "component", "type", "amount", "note"],
			order_by="idx",
		)
		per_slip = {}
		for i in rincian:
			per_slip.setdefault(i.parent, []).append(i)
		for r in rows:
			r["items"] = per_slip.get(r.name, [])
	return rows

"""API apps mandor (/mandor). Modul mobile.

Mandor = pengawas lapangan cabang. Tiga layar, dan hanya satu yang menulis:

    Absensi Driver  -- lihat saja, siapa sudah absen / check in / jalan
    Dispatch Order  -- isi ATD/Driver/Vehicle/Chasis lalu Assign, dari HP
    Peta            -- posisi seluruh armada cabang

Wewenang TIDAK memakai role baru: yang boleh masuk adalah user yang memang boleh
menulis Dispatch Order di desk. Satu tempat pengaturan izin, bukan dua yang
diam-diam menyimpang. Cabang diambil dari `User.branch` (Custom Field milik
crm_cakra) -- kalau field itu belum terpasang atau kosong, mandor melihat semua
cabang, bukan tidak melihat apa-apa.

Dispatch Order tidak bisa DIBUAT dari sini: DPO lahir otomatis dari Packing List
(`sync_from_packing_list`). Yang dikerjakan mandor adalah mengisi dan meng-assign
DPO yang sudah ada.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from erp.fleet.api.mobile_driver import _availability

LIMIT = 300


# ---------------------------------------------------------------- dasar


def _branch():
	"""Cabang mandor. None = semua cabang.

	`User.branch` adalah Custom Field, jadi keberadaannya diperiksa dulu: site
	tanpa crm_cakra terpasang tidak boleh membuat seluruh apps ini melempar error
	di panggilan pertama.
	"""
	if not frappe.get_meta("User").get_field("branch"):
		return None
	return frappe.db.get_value("User", frappe.session.user, "branch") or None


def _mandor():
	"""Mandor yang sedang login. Throw kalau tidak berhak.

	Izinnya diuji ke Dispatch Order karena itulah yang dikerjakannya; layar
	Absensi dan Peta menguji doctype-nya sendiri di tempat masing-masing.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Silakan login dulu."), frappe.PermissionError)
	if not frappe.has_permission("Dispatch Order", "write"):
		frappe.throw(
			_("Akun ini tidak berhak mengatur Dispatch Order. Hubungi kantor."),
			frappe.PermissionError,
		)
	u = frappe.db.get_value(
		"User", frappe.session.user, ["full_name", "user_image"], as_dict=True
	)
	return frappe._dict(
		user=frappe.session.user,
		nama=(u and u.full_name) or frappe.session.user,
		image=(u and u.user_image) or None,
		branch=_branch(),
	)


def _cek_cabang(m, branch):
	"""DPO cabang lain tidak boleh disentuh mandor bercabang.

	Filter di daftar saja tidak cukup -- nomor DPO gampang ditebak, dan endpoint
	detail/simpan menerima nama dokumen langsung dari client.
	"""
	if m.branch and branch and branch != m.branch:
		frappe.throw(_("Dokumen ini milik cabang lain."), frappe.PermissionError)


def _running_drivers(names):
	"""Sopir yang job-nya sedang berjalan: {driver: dpo_no}."""
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select driver, dpo_no from `tabDispatch Order Item`
		   where assigned = 1 and ifnull(atd, '') != '' and ifnull(ata, '') = ''
		     and driver in %(n)s""",
		{"n": tuple(names)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.driver, r.dpo_no or "")
	return out


# Sopir yang boleh dipasang ke job hari ini. Sopir yang sudah absen tapi belum
# memilih kendaraan ("Absensi") tetap boleh -- dia ada di kantor, kendaraannya
# saja yang belum, dan mandor memang kadang menetapkan unitnya duluan.
BOLEH_DIPILIH = ("Ready", "Absensi")

# Alasan penolakan ditulis SEKALI di server, bukan di layar: apps sopir, papan
# absensi, dan pemilih ini harus menyebut sebab yang sama persis.
ALASAN = {
	"Belum Absen": "Belum absen hari ini.",
	"Check Out": "Sudah check out hari ini.",
	"Izin": "Sedang izin hari ini.",
	"Sakit": "Sedang sakit hari ini.",
}


def _absen_hari(names, hari):
	"""Keadaan absensi satu hari per sopir: {driver: {...}}.

	SATU sumber untuk papan Absensi dan pemilih Driver. Dulu keduanya menghitung
	status sendiri-sendiri dan langsung menyimpang -- papan bilang "Ready",
	pemilih bilang "Belum Absen", untuk sopir yang sama di menit yang sama.
	"""
	if not names:
		return {}

	baris = {}
	for a in frappe.db.sql(
		"""select driver, type, timestamp, vehicle, trail, image, remark,
		          distance_m, gps_stale
		   from `tabDriver Attendance`
		   where date(timestamp) = %(d)s and driver in %(n)s
		   order by timestamp""",
		{"d": hari, "n": tuple(names)},
		as_dict=True,
	):
		baris.setdefault(a.driver, []).append(a)

	jalan = _running_drivers(names)

	out = {}
	for d in names:
		rs = baris.get(d) or []
		last = rs[-1] if rs else None
		absen = next((r for r in rs if r.type == "Absensi"), None)
		masuk = next((r for r in reversed(rs) if r.type == "Check In"), None)

		# Urutannya sama dengan `me()` di apps sopir. On Job menang atas Ready,
		# tapi TIDAK menutupi "Belum Absen": sopir bisa sedang menjalankan job
		# yang berangkat kemarin sekaligus belum absen hari ini.
		if not rs:
			status = "Belum Absen"
		elif last.type == "Check Out":
			status = "Check Out"
		elif d in jalan:
			status = "On Job"
		elif last.type == "Check In":
			status = "Ready"
		else:
			status = last.type  # Absensi / Izin / Sakit

		job = jalan.get(d) or ""
		out[d] = {
			"status": status,
			"job": job,
			"boleh": 1 if status in BOLEH_DIPILIH else 0,
			"alasan": (
				_("Sedang mengerjakan job {0}.").format(job)
				if status == "On Job"
				else _(ALASAN.get(status, ""))
			),
			"absen_jam": str(absen.timestamp) if absen else None,
			"absen_foto": absen.image if absen else None,
			"check_in_jam": str(masuk.timestamp) if masuk else None,
			"vehicle": masuk.vehicle if masuk else None,
			"trail": masuk.trail if masuk else None,
			"jarak_m": masuk.distance_m if masuk else None,
			"gps_stale": cint(masuk.gps_stale) if masuk else 0,
			"keluar_jam": str(last.timestamp) if last and last.type == "Check Out" else None,
			"remark": (last.remark if last else None) or "",
		}
	return out


@frappe.whitelist()
def csrf():
	"""Token CSRF untuk sesi ini. GET, jadi tidak kena cek CSRF itu sendiri."""
	return frappe.sessions.get_csrf_token()


@frappe.whitelist()
def me():
	m = _mandor()
	return {
		"user": m.user,
		"nama": m.nama,
		"image": m.image,
		"branch": m.branch,
		# Cabang kosong artinya SEMUA cabang. Itu perbedaan besar dan harus
		# terbaca di layar, bukan disimpulkan dari daftar yang kepanjangan.
		"cabang_label": m.branch or "Semua Cabang",
	}


# ---------------------------------------------------------------- dispatch order


@frappe.whitelist()
def orders(q=None, start=0, limit=10, saring=None):
	"""Daftar DPO cabang mandor, terbaru dulu.

	`saring="belum"` menyisakan DPO yang masih punya item belum di-assign -- itu
	yang dicari mandor saat membuka apps, dan tanpa saringan ini DPO yang sudah
	beres ikut menumpuk di baris pertama tiap hari.
	"""
	m = _mandor()
	cond = ["1 = 1"]
	vals = {"lim": cint(limit), "off": cint(start)}

	if m.branch:
		cond.append("do.branch = %(b)s")
		vals["b"] = m.branch
	if saring == "belum":
		cond.append(
			"exists (select 1 from `tabDispatch Order Item` i"
			" where i.parent = do.name and ifnull(i.assigned, 0) = 0)"
		)
	if q:
		vals["q"] = f"%{q.strip()}%"
		cond.append(
			"(do.name like %(q)s or do.packing_list like %(q)s or do.customer_list like %(q)s"
			" or do.dpo_list like %(q)s or do.driver_list like %(q)s or do.vehicle_list like %(q)s"
			" or do.origin_location like %(q)s or do.destination_location like %(q)s)"
		)

	return frappe.db.sql(
		f"""select do.name, do.packing_list, do.branch, do.customer_list,
		           do.origin_location, do.destination_location, do.etd, do.eta,
		           do.assign_progress,
		           (select count(*) from `tabDispatch Order Item` i where i.parent = do.name) total,
		           (select count(*) from `tabDispatch Order Item` i
		             where i.parent = do.name and i.assigned = 1) assigned
		    from `tabDispatch Order` do
		    where {" and ".join(cond)}
		    order by do.creation desc
		    limit %(lim)s offset %(off)s""",
		vals,
		as_dict=True,
	)


def _route(doc):
	"""Titik rute yang terisi saja, urut slot, LENGKAP dengan koordinatnya.

	Koordinat ikut di sini supaya apps tidak perlu satu panggilan lagi hanya
	untuk menggambar peta -- titiknya paling banyak delapan dan sudah pasti
	dibutuhkan begitu halaman detail dibuka.
	"""
	slot = []
	for n in range(1, 9):
		titik = doc.get(f"route_{n}")
		if not titik:
			continue
		slot.append(
			{
				"no": n,
				"jenis": doc.get(f"route_type_{n}") or "Route",
				"titik": titik,
				"langsir": cint(doc.get(f"route_langsir_{n}")),
				"origin": cint(doc.get(f"route_origin_{n}")),
				"dest": cint(doc.get(f"route_dest_{n}")),
			}
		)
	if not slot:
		return []

	lokasi = {
		r.name: r
		for r in frappe.get_all(
			"Fleet Location",
			filters={"name": ["in", [s["titik"] for s in slot]]},
			fields=["name", "latitude", "longitude", "alamat", "jenis"],
		)
	}
	for s in slot:
		p = lokasi.get(s["titik"]) or {}
		s["latitude"] = p.get("latitude")
		s["longitude"] = p.get("longitude")
		s["alamat"] = p.get("alamat")
	return slot


def _armada(doc, nama_driver):
	"""Posisi GPS kendaraan yang dipakai DPO ini, untuk ikon truk di peta."""
	vehs = {r.vehicle for r in doc.items if r.vehicle}
	if not vehs:
		return []
	# Satu unit bisa punya lebih dari satu baris GPS Vehicle; yang terbaru menang,
	# sama seperti monitor desk.
	posisi = {}
	for g in frappe.get_all(
		"GPS Vehicle",
		filters={"vehicle": ["in", list(vehs)]},
		fields=["vehicle", "latitude", "longitude", "last_seen", "speed"],
		order_by="modified asc",
	):
		posisi[g.vehicle] = g

	sopir = {r.vehicle: r.driver for r in doc.items if r.vehicle and r.driver}
	out = []
	for v in sorted(vehs):
		g = posisi.get(v)
		if not g or not (g.latitude or g.longitude):
			continue
		d = sopir.get(v)
		out.append(
			{
				"vehicle": v,
				"driver": d,
				"driver_nama": nama_driver.get(d) or d,
				"latitude": g.latitude,
				"longitude": g.longitude,
				"last_seen": str(g.last_seen) if g.last_seen else None,
				"speed": g.speed,
			}
		)
	return out


def _trips(doc, nama_driver):
	"""Matriks ritase versi HP: {dpo_item: [{trip, driver, vehicle, steps[]}]}.

	Ini isi section Route di desk. Dibaca saja di sini -- jam masuk/keluar titik
	datang dari geofence apps sopir, bukan diketik mandor.
	"""
	out = {}
	for r in sorted(doc.trip_log, key=lambda r: (r.dpo_item or "", cint(r.trip), cint(r.step))):
		daftar = out.setdefault(r.dpo_item, [])
		trip = next((t for t in daftar if t["trip"] == cint(r.trip)), None)
		if not trip:
			trip = {
				"trip": cint(r.trip),
				"driver": r.driver,
				"driver_nama": nama_driver.get(r.driver) or r.driver,
				"vehicle": r.vehicle,
				"chasis": r.chasis,
				"atd": r.atd,
				"ata": r.ata,
				"steps": [],
			}
			daftar.append(trip)
		trip["steps"].append(
			{
				"step": cint(r.step),
				"step_type": r.step_type,
				"point": r.point,
				"point_type": r.point_type,
				"start": str(r.start) if r.start else None,
				"end": str(r.end) if r.end else None,
			}
		)
	return out


def _order_doc(name, ptype="read"):
	doc = frappe.get_doc("Dispatch Order", name)
	doc.check_permission(ptype)
	_cek_cabang(_mandor(), doc.branch)
	return doc


@frappe.whitelist()
def order(name):
	"""Satu DPO UTUH: header, item, rute (berkoordinat), ritase, dan posisi armada.

	Semuanya dalam SATU panggilan. Halaman detail di HP menampilkan keempatnya
	sekaligus, dan memecahnya jadi empat endpoint berarti empat kali menunggu di
	sinyal lapangan yang justru paling lambat.
	"""
	doc = _order_doc(name)


	sopir = {r.driver for r in doc.items if r.driver} | {r.driver for r in doc.trip_log if r.driver}
	nama_driver = {
		d.name: d.title
		for d in frappe.get_all(
			"Driver", filters={"name": ["in", list(sopir) or [""]]}, fields=["name", "title"]
		)
	}

	return {
		"name": doc.name,
		"packing_list": doc.packing_list,
		"branch": doc.branch,
		"customer": doc.customer,
		"packing_list_date": doc.packing_list_date,
		"created_by_user": doc.created_by_user,
		"created_on": doc.created_on,
		"assign_progress": doc.assign_progress,
		"origin_location": doc.origin_location,
		"destination_location": doc.destination_location,
		"etd": doc.etd,
		"eta": doc.eta,
		"etb": doc.etb,
		"notes": doc.notes,
		"customer_list": doc.customer_list,
		"dpo_list": doc.dpo_list,
		"driver_list": doc.driver_list,
		"vehicle_list": doc.vehicle_list,
		"route": _route(doc),
		"trips": _trips(doc, nama_driver),
		"armada": _armada(doc, nama_driver),
		"items": [
			{
				"name": r.name,
				"idx": r.idx,
				"dpo_no": r.dpo_no,
				"container_no": r.container_no,
				"container_tms": r.container_tms,
				"container_tms_at": str(r.container_tms_at) if r.container_tms_at else None,
				"container_size": r.container_size,
				"customer": r.customer,
				"atd": r.atd,
				"ata": r.ata,
				"driver": r.driver,
				"driver_nama": nama_driver.get(r.driver) or r.driver,
				"vehicle": r.vehicle,
				"chasis": r.chasis,
				"packing_list_item": r.packing_list_item,
				"assigned": cint(r.assigned),
				# Terkunci = ATA terisi (aturan `_lock_assigned_items`): job sudah
				# selesai, driver/vehicle/chasis-nya jadi catatan sejarah. Dikirim
				# sebagai flag supaya apps menampilkannya baca-saja, bukan
				# membiarkan mandor mengisi form yang pasti ditolak saat disimpan.
				"terkunci": 1 if r.ata else 0,
			}
			for r in doc.items
		],
	}


@frappe.whitelist()
def simpan_item(item, driver=None, vehicle=None, chasis=None, atd=None, ata=None):
	"""Tulis satu baris DPO Item, lalu kembalikan DPO-nya utuh.

	Disimpan lewat `doc.save()` biasa, BUKAN db_set: seluruh aturan Dispatch
	Order (double assignment, tabrakan jadwal vehicle, kunci item bertrip, tulis
	balik ke Packing List Item) harus tetap jalan. Pesannya sudah berbahasa
	manusia dan langsung dipakai apa adanya di layar HP.

	Nilai kosong dikirim sebagai None, bukan "": kolom Date menolak string kosong.
	"""
	doc = _item_doc(item)
	row = next((r for r in doc.items if r.name == item), None)
	if not row:
		frappe.throw(_("Item ini sudah tidak ada. Muat ulang daftarnya."))

	row.driver = driver or None
	row.vehicle = vehicle or None
	row.chasis = chasis or None
	row.atd = atd or None
	row.ata = ata or None
	doc.save()
	return order(doc.name)


def _item_doc(item):
	"""DPO induk satu baris item, sudah lolos izin dan cabang."""
	m = _mandor()
	parent = frappe.db.get_value("Dispatch Order Item", item, "parent")
	if not parent:
		frappe.throw(_("Item ini sudah tidak ada. Muat ulang daftarnya."))
	doc = frappe.get_doc("Dispatch Order", parent)
	doc.check_permission("write")
	_cek_cabang(m, doc.branch)
	return doc


@frappe.whitelist()
def tambah_trip(item, driver=None, vehicle=None, chasis=None, atd=None, ata=None):
	"""Ritase tambahan. Membungkus `Dispatch Order.add_trip` apa adanya.

	Ketiga endpoint ritase di bawah sengaja TIDAK menghitung nomor trip, mengarsip
	step, atau menurunkan tanggal sendiri: semuanya sudah ada di doctype dan
	dipakai tombol desk. Menyalinnya ke sini berarti dua aturan yang pasti
	menyimpang, dan yang menyimpang diam-diam adalah nomor ritase -- kolom yang
	dipakai menagih.
	"""
	doc = _item_doc(item)
	hasil = doc.add_trip(item, driver=driver, vehicle=vehicle, chasis=chasis, atd=atd, ata=ata)
	return {"hasil": hasil, "order": order(doc.name)}


@frappe.whitelist()
def ubah_trip(item, trip, driver=None, vehicle=None, chasis=None, atd=None, ata=None):
	doc = _item_doc(item)
	doc.edit_trip(item, trip, driver=driver, vehicle=vehicle, chasis=chasis, atd=atd, ata=ata)
	return {"order": order(doc.name)}


@frappe.whitelist()
def hapus_trip(item, trip):
	"""Hapus satu ritase. Step-nya diarsip dulu ke `history.dispatch_order_history`
	oleh doctype -- jadi ini bukan penghapusan yang hilang tanpa jejak."""
	doc = _item_doc(item)
	doc.delete_trip(item, trip)
	return {"order": order(doc.name)}


@frappe.whitelist()
def assign(name):
	"""Tombol Assign, sama persis dengan yang di desk (termasuk notifikasi sopir)."""
	doc = _order_doc(name, "write")
	hasil = doc.assign()
	return {"hasil": hasil, "order": order(name)}


# ---------------------------------------------------------------- pemilih


@frappe.whitelist()
def drivers(q=None):
	"""Sopir cabang untuk pemilih di layar Dispatch.

	Yang boleh dipasang ke job HANYA sopir yang sudah absen hari ini dan sedang
	tidak jalan (`boleh`). Sisanya tetap DIKIRIM lengkap dengan alasannya --
	mandor yang tidak menemukan nama yang dicarinya akan mengira daftarnya rusak;
	yang dia butuh adalah tahu orangnya ada, dan kenapa belum bisa dipakai.

	`vehicle` ikut dikirim: sopir yang absen sudah sekalian memilih kendaraan,
	jadi apps bisa mengisinya sendiri begitu sopirnya dipilih.
	"""
	m = _mandor()
	filters = {"disabled": 0, "quit_date": ["is", "not set"]}
	if m.branch:
		filters["branch"] = m.branch
	rows = frappe.get_all(
		"Driver",
		filters=filters,
		or_filters=({"name": ["like", f"%{q}%"]}, {"title": ["like", f"%{q}%"]}) if q else None,
		fields=["name", "title", "code", "phone_number"],
		order_by="title",
		limit=LIMIT,
	)

	keadaan = _absen_hari([r.name for r in rows], getdate(today()))
	for r in rows:
		k = keadaan.get(r.name) or {}
		r["label"] = r.title or r.name
		r["status"] = k.get("status") or "Belum Absen"
		r["boleh"] = cint(k.get("boleh"))
		r["keterangan"] = k.get("alasan") or ""
		r["vehicle"] = k.get("vehicle")
		r["trail"] = k.get("trail")
		# Baris kedua di daftar: nopol yang sudah dipegangnya hari ini lebih
		# berguna daripada kode sopir yang tidak pernah dihafal siapa pun.
		r["ket"] = r["vehicle"] or r.code or ""

	rows.sort(key=lambda r: (0 if r["boleh"] else 1, r["label"]))
	return rows


@frappe.whitelist()
def vehicles(q=None):
	"""Kendaraan cabang, yang tersedia dulu. Status memakai `_availability`
	milik apps sopir supaya kedua apps tidak pernah menjawab beda."""
	m = _mandor()
	filters = {"disabled": 0}
	if m.branch:
		filters["branch"] = m.branch
	rows = frappe.get_all(
		"Vehicle",
		filters=filters,
		or_filters=({"name": ["like", f"%{q}%"]}, {"title": ["like", f"%{q}%"]}) if q else None,
		fields=["name", "title", "merk"],
		order_by="name",
		limit=LIMIT,
	)

	sibuk = _availability([r.name for r in rows])
	for r in rows:
		r.update(sibuk.get(r.name) or {"status": "Tersedia", "oleh": None, "keterangan": None})
		r["label"] = r.name
		r["ket"] = r.merk or ""
		if r.get("oleh"):
			r["ket"] = _("Dipakai {0}").format(r["oleh"])

	urut = {"Tersedia": 0, "Dipakai": 1, "Maintenance": 2}
	rows.sort(key=lambda r: (urut.get(r["status"], 9), r["name"]))
	return rows


# ---------------------------------------------------------------- absensi (lihat saja)


STATUS_URUT = {"Belum Absen": 0, "Absensi": 1, "Ready": 2, "On Job": 3, "Check Out": 4}


@frappe.whitelist()
def absensi(tanggal=None, q=None, start=0, limit=5):
	"""Papan absensi satu hari: SATU baris per sopir, bukan per record.

	Sopir yang belum absen ikut ditampilkan dan ditaruh paling atas. Justru
	merekalah yang dicari mandor pagi-pagi; daftar yang hanya berisi record yang
	sudah masuk tidak pernah bisa menjawab "siapa yang belum datang".

	Rows dipotong `start`/`limit` (apps menambah sendiri saat digulir), TAPI
	urutan dan `ringkas` tetap dihitung dari seluruh sopir cabang: potongan yang
	menghitung ringkasannya sendiri akan memberi angka yang berubah-ubah tiap
	kali mandor menggulir.
	"""
	m = _mandor()
	frappe.has_permission("Driver Attendance", "read", throw=True)
	hari = getdate(tanggal or today())

	# "is not set", BUKAN ["in", [None, ""]]: di query builder frappe.get_all,
	# `in` dengan None menghasilkan `quit_date in (NULL, '')` yang TIDAK pernah
	# cocok dengan NULL -- daftarnya lalu kosong tanpa satu pun error.
	filters = {"disabled": 0, "quit_date": ["is", "not set"]}
	if m.branch:
		filters["branch"] = m.branch
	sopir = frappe.get_all(
		"Driver",
		filters=filters,
		or_filters=({"name": ["like", f"%{q}%"]}, {"title": ["like", f"%{q}%"]}) if q else None,
		fields=["name", "title", "code", "image", "phone_number"],
		order_by="title",
		limit=LIMIT,
	)
	if not sopir:
		return {"tanggal": str(hari), "ringkas": {}, "rows": [], "total": 0}

	keadaan = _absen_hari([s.name for s in sopir], hari)
	rows = [
		dict(
			keadaan[s.name],
			driver=s.name,
			nama=s.title or s.name,
			code=s.code,
			image=s.image,
			phone=s.phone_number,
		)
		for s in sopir
	]
	rows.sort(key=lambda r: (STATUS_URUT.get(r["status"], 5), r["nama"]))

	ringkas = {}
	for r in rows:
		ringkas[r["status"]] = ringkas.get(r["status"], 0) + 1

	off = cint(start)
	return {
		"tanggal": str(hari),
		"ringkas": ringkas,
		"total": len(rows),
		"rows": rows[off : off + cint(limit)],
	}


# ---------------------------------------------------------------- peta


@frappe.whitelist()
def peta():
	"""Posisi armada. Memanggil ULANG data monitor GPS desk, bukan menyalin
	aturannya -- status/warna/ikon harus sama dengan yang dilihat kantor."""
	m = _mandor()
	from erp.fleet.page.gps_monitor.gps_monitor import get_rows

	data = get_rows()
	if m.branch:
		data["rows"] = [r for r in data["rows"] if r.get("branch") == m.branch]
	return data

import re
import secrets

import frappe
from frappe.model.document import Document
from frappe.utils.password import update_password

from erp.fleet.vehicle_status import job_duration

# tanpa karakter rancu (0/O, 1/l/I) supaya gampang diketik driver
PW_LETTERS = "abcdefghjkmnpqrstuvwxyz"
PW_DIGITS = "23456789"

USERNAME_LENGTH = 7
PASSWORD_LENGTH = 5

# Domain reserved (RFC 2606): akun sopir tidak pernah bisa mengirim/menerima email
# ke alamat sungguhan, walau Frappe mewajibkan setiap User punya alamat.
LOGIN_DOMAIN = "driver.invalid"


class Driver(Document):
    def validate(self):
    	if not self.username_apps:
    		self.username_apps = self.generate_username()
    	elif self.is_username_taken(self.username_apps):
    		bentrok = self.username_apps
    		self.username_apps = self.generate_username()
    		frappe.msgprint(
    			f"Username {bentrok} sudah dipakai driver lain, diganti otomatis jadi {self.username_apps}",
    			alert=True,
    		)

    	if not self.password_apps:
    		self.password_apps = generate_password()

    def on_update(self):
    	self.sync_login()

    def is_username_taken(self, username):
    	return bool(
    		frappe.db.exists("Driver", {"username_apps": username, "name": ("!=", self.name or "")})
    	)

    def generate_username(self):
    	base = re.sub(r"[^a-z0-9]", "", (self.title or "").lower())[:4] or "drv"
    	for i in range(50):
    		# kalau nama ini sudah padat, jatuh ke prefix generik yang ruang angkanya lebih lebar
    		prefix = base if i < 25 else "drv"
    		username = prefix + "".join(
    			secrets.choice("0123456789") for _ in range(USERNAME_LENGTH - len(prefix))
    		)
    		if not self.is_username_taken(username):
    			return username

    	frappe.throw(f"Gagal membuat username unik untuk {self.title}")

    # ------------------------------------------------------------------ login

    def sync_login(self):
    	"""Salurkan username/password apps ke User Frappe.

    	Sopir login dengan username & password yang tampil di form ini, tapi yang
    	memeriksa tetap mesin login Frappe -- hashing, rate limit anti tebak
    	password, sesi, logout. Menulis auth sendiri berarti menulis ulang semua
    	itu dengan lebih buruk, dan `password_apps` hanya sepanjang 5 karakter.
    	"""
    	if not self.username_apps:
    		return

    	email = self.user or f"{self.username_apps}@{LOGIN_DOMAIN}"
    	aktif = not self.disabled and not self.quit_date

    	if frappe.db.exists("User", email):
    		user = frappe.get_doc("User", email)
    	else:
    		user = frappe.new_doc("User")
    		user.email = email
    		user.send_welcome_email = 0

    	user.first_name = self.title or self.name
    	user.username = self.username_apps
    	user.user_type = "Website User"
    	user.enabled = 1 if aktif else 0
    	user.flags.ignore_permissions = True
    	user.save(ignore_permissions=True)

    	if self.user != user.name:
    		self.db_set("user", user.name, update_modified=False)

    	# Kebijakan kekuatan password Frappe menolak 5 karakter, jadi hash-nya
    	# ditulis langsung. Tetap ter-hash, hanya lewat validasi doc User.
    	# Field-nya Data (sengaja terbaca admin), jadi dibaca langsung --
    	# get_password() cuma berlaku untuk fieldtype Password.
    	pwd = self.password_apps
    	if not pwd:
    		frappe.throw(f"Password apps {self.name} tidak terbaca, akun login tidak dibuat.")

    	# Nilai bertopeng berarti kolomnya pernah bertipe Password dan isi aslinya
    	# ada di tabel __Auth, bukan di kolom ini. Menyimpannya apa adanya akan
    	# menetapkan password login sopir menjadi harfiah "*****" -- tanpa error,
    	# dan baru ketahuan saat sopir tidak bisa masuk di lapangan.
    	if set(pwd) == {"*"}:
    		frappe.throw(
    			f"Password apps {self.name} masih bertopeng. Ketik ulang passwordnya "
    			"sebelum menyimpan, atau jalankan pulihkan_password_apps()."
    		)

    	update_password(user.name, pwd)

    	# Password yang tersimpan di Driver dan yang dipakai login WAJIB sama.
    	# Kalau keduanya menyimpang, tidak ada error apa pun -- yang terjadi
    	# adalah sopir berdiri di lapangan dengan password yang ditolak. Jadi
    	# dicocokkan di sini, saat masih ada yang bisa memperbaikinya.
    	if not password_matches(user.name, pwd):
    		frappe.throw(f"Password login {self.username_apps} gagal disinkronkan.")

    def on_trash(self):
    	# User ikut mati, bukan ikut terhapus: Driver Attendance dan log lokasi
    	# masih menunjuk ke sana dan harus tetap terbaca.
    	if self.user and frappe.db.exists("User", self.user):
    		frappe.db.set_value("User", self.user, "enabled", 0)


def generate_password():
    chars = PW_LETTERS + PW_DIGITS
    # minimal 1 huruf + 1 angka
    pw = [secrets.choice(PW_LETTERS), secrets.choice(PW_DIGITS)]
    pw += [secrets.choice(chars) for _ in range(PASSWORD_LENGTH - 2)]
    secrets.SystemRandom().shuffle(pw)
    return "".join(pw)


def password_matches(user, pwd):
    from frappe.utils.password import check_password

    try:
    	check_password(user, pwd, delete_tracker_cache=False)
    	return True
    except frappe.AuthenticationError:
    	return False


@frappe.whitelist()
def pulihkan_password_apps():
    """Tarik password asli dari __Auth kembali ke kolom `password_apps`.

    Dipakai sekali setelah fieldtype diubah Password -> Data: kolomnya berisi
    "*****" sementara nilai sungguhannya masih tersimpan terenkripsi di __Auth.
    """
    from frappe.utils.password import get_decrypted_password

    pulih, lewat = [], 0
    for name in frappe.get_all("Driver", pluck="name"):
        kini = frappe.db.get_value("Driver", name, "password_apps")
        if kini and set(kini) != {"*"}:
            lewat += 1
            continue
        asli = get_decrypted_password("Driver", name, "password_apps", raise_exception=False)
        if not asli:
            continue
        frappe.db.set_value("Driver", name, "password_apps", asli, update_modified=False)
        pulih.append(name)
    frappe.db.commit()
    return {"dipulihkan": len(pulih), "sudah_benar": lewat}



@frappe.whitelist()
def sync_all_logins():
    """Perbaiki akun login sopir yang belum ada atau sudah menyimpang.

    Aman dijalankan berulang: sopir yang password Driver-nya sudah cocok dengan
    password login-nya dilewati, jadi tidak ada password yang berubah percuma
    dan tidak ada sopir yang tiba-tiba tidak bisa masuk.
    """
    dibuat, diperbaiki, utuh = [], [], 0
    for name in frappe.get_all("Driver", pluck="name"):
    	doc = frappe.get_doc("Driver", name)
    	pwd = doc.password_apps if doc.username_apps else None

    	if not doc.username_apps or not doc.user or not pwd:
    		doc.save(ignore_permissions=True)
    		dibuat.append(doc.username_apps)
    	elif not password_matches(doc.user, pwd):
    		doc.sync_login()
    		diperbaiki.append(doc.username_apps)
    	else:
    		utuh += 1

    frappe.db.commit()
    return {"dibuat": dibuat, "diperbaiki": diperbaiki, "sudah_benar": utuh}


@frappe.whitelist()
def get_job_history(driver, limit=100):
    """Riwayat job satu driver, untuk tab di form desk."""
    frappe.has_permission("Driver", "read", throw=True)
    return job_history(driver, limit)


def job_history(driver, limit=100, start=0, q=None):
    """Riwayat job driver -- versi Monitoring Board yang disaring 1 driver saja.

    Job dianggap selesai kalau langkah Lanjut Job / Menuju Garasi sudah ditekan,
    aturan yang sama dengan yang dipakai Monitoring Board menentukan job aktif.

    Tanpa cek permission: pemanggilnya yang menentukan siapa boleh melihat driver
    mana. Apps sopir menurunkan `driver` dari sesi, form desk dari permission.

    `q` mencari di nomor DPO, nomor kontainer, customer, dan nopol sekaligus --
    sopir mengingat job dari salah satu dari itu, bukan dari nomor dokumen saja.
    """
    rows = frappe.db.sql(
    	"""select i.dpo_no, i.container_no, i.container_size, i.vehicle, i.customer,
                  i.atd, i.ata, do.name dpo, do.packing_list, do.branch, do.creation,
                  do.origin_location, do.destination_location,
                  exists(select 1 from `tabDispatch Order Route` t
                         where t.dpo_item = i.name
                           and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                           and t.start is not null) selesai,
                  (select min(t.start) from `tabDispatch Order Route` t
                   where t.dpo_item = i.name and t.step_type = 'Assign') assign,
                  (select min(t.start) from `tabDispatch Order Route` t
                   where t.dpo_item = i.name and t.step_type = 'Accept Job') accept,
                  (select min(t.start) from `tabDispatch Order Route` t
                   where t.dpo_item = i.name and t.step_type in ('Lanjut Job', 'Menuju Garasi')
                     and t.start is not null) finish,
                  (select t.point from `tabDispatch Order Route` t
                   where t.dpo_item = i.name and t.step_type = 'Route'
                     and (t.start is not null or t.end is not null)
                   order by t.step desc limit 1) checkpoint
           from `tabDispatch Order Item` i
           join `tabDispatch Order` do on i.parent = do.name
           where i.driver = %(driver)s and i.assigned = 1
             and (%(q)s = '' or i.dpo_no like %(like)s or i.container_no like %(like)s
                  or i.customer like %(like)s or i.vehicle like %(like)s)
           order by ifnull(i.atd, do.creation) desc
           limit %(limit)s offset %(start)s""",
    	{
    		"driver": driver,
    		"q": (q or "").strip(),
    		"like": "%" + (q or "").strip() + "%",
    		"limit": int(limit),
    		"start": int(start),
    	},
    	as_dict=True,
    )
    for r in rows:
        r.durasi = job_duration(r.assign, r.finish)
    return rows

"""Database tambahan di server MariaDB yang sama dengan site: `history` (Fleet) dan `mail_db`
(arsip email, lihat mail_archive.py).

User database site hanya berhak atas database-nya sendiri. ensure() mencoba sebagai user site
dulu (jalan kalau haknya sudah pernah diberikan). Kalau ditolak dan root MariaDB ada di
konfigurasi server (`mariadb_root_password` di sites/common_site_config.json, tidak masuk git),
database dibuat dan haknya diberikan lewat koneksi root -- jadi migrate pertama di server baru
menyiapkannya sendiri. Tanpa keduanya, GRANT manual sekali sebagai root:
	GRANT ALL PRIVILEGES ON `<nama>`.* TO '<db user site>'@'%'; FLUSH PRIVILEGES;
"""

import frappe


def ensure(name: str) -> bool:
	"""Database `name` ada dan bisa dipakai user site. False = belum bisa (alasan di Error Log)."""
	create = f"create database if not exists `{name}` character set utf8mb4 collate utf8mb4_unicode_ci"
	try:
		frappe.db.sql_ddl(create)
		return True
	except Exception:
		if not (frappe.conf.get("mariadb_root_password") or frappe.conf.get("root_password")):
			frappe.log_error(
				title=f"extra_db.ensure: {name}",
				message=f"Database `{name}` belum bisa dibuat: user site tidak punya hak dan root MariaDB tidak ada "
				"di common_site_config.json. Isi mariadb_root_password lalu migrate ulang, atau GRANT manual "
				"(lihat erpnext_custom/extra_db.py).",
			)
			return False

	from frappe.database.mariadb.setup_db import get_root_connection

	user, host = frappe.db.sql("select current_user()")[0][0].rsplit("@", 1)
	root = get_root_connection()
	root.sql(create)
	root.sql(f"grant all privileges on `{name}`.* to %s@%s", (user, host))
	root.sql("flush privileges")
	# Hak tingkat database baru terbaca koneksi yang sudah terbuka sesudah USE.
	frappe.db.sql(f"use `{name}`")
	frappe.db.sql(f"use `{frappe.conf.db_name}`")
	return True

"""Uji salin-lalu-alihkan lampiran di folder sementara (site asli tidak disentuh).

Jalankan: bench --site <site> execute erpnext_custom.test_attachment_storage.run
"""

import os
import shutil
import subprocess
import tempfile

from erpnext_custom import attachment_storage as a


def _write(path, text):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		f.write(text)


def _read(path):
	with open(path) as f:
		return f.read()


def run():
	tmp = tempfile.mkdtemp()
	site, root = os.path.join(tmp, "site"), os.path.join(tmp, "root")
	orig_site = a._site
	a._site = lambda part: os.path.join(site, part)
	try:
		_write(f"{site}/private/files/A.pdf", "upper")
		_write(f"{site}/private/files/a.pdf", "lower")  # beda kapital saja, harus tetap dua berkas
		_write(f"{site}/public/files/logo.png", "logo")

		# bawaan -> folder lain
		lines, renamed = [], []
		a.migrate_files(f"{root}/x", "s1", lines, renamed)
		assert os.path.realpath(f"{site}/private") == f"{root}/x/private"
		assert _read(f"{site}/private/files/A.pdf") == "upper"
		assert _read(f"{site}/private/files/a.pdf") == "lower"
		assert _read(f"{site}/public/files/logo.png") == "logo"
		assert renamed == [f"{site}/private.old-s1", f"{site}/public.old-s1"]
		assert _read(f"{site}/private.old-s1/files/A.pdf") == "upper"  # asal utuh

		# backup bawaan Frappe (tar pada <site>/private/files) harus berisi berkas, bukan cuma link
		tar = subprocess.run(["tar", "cf", "-", "private/files"], cwd=site, capture_output=True, check=True).stdout
		assert b"A.pdf" in tar and b"lower" in tar

		# folder lain -> folder lain: asal tidak disentuh sama sekali
		_write(f"{site}/private/files/new.pdf", "new")
		lines, renamed = [], []
		a.migrate_files(f"{root}/y", "s2", lines, renamed)
		assert os.path.realpath(f"{site}/private") == f"{root}/y/private"
		assert _read(f"{site}/private/files/new.pdf") == "new"
		assert renamed == [] and os.path.exists(f"{root}/x/private/files/new.pdf")

		# kembali ke bawaan: folder biasa lagi, bukan symlink
		lines, renamed = [], []
		a.migrate_files("", "s3", lines, renamed)
		assert not os.path.islink(f"{site}/private") and os.path.isdir(f"{site}/private/files")
		assert _read(f"{site}/private/files/a.pdf") == "lower"
		assert not os.path.exists(f"{site}/private.copying")
		assert os.path.exists(f"{root}/y/private/files/new.pdf")
		print("attachment_storage OK")
	finally:
		a._site = orig_site
		shutil.rmtree(tmp)

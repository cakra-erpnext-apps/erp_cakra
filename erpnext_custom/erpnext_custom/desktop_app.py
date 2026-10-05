"""Installer aplikasi desktop (folder desktop/ di app ini) di server ini, diunggah dari
ERPNext Custom Setting > Desktop App. Tidak lewat git: installer ~110 MB per versi.

Susunan di folder publik situs (feed update aplikasi = <origin>/files/):
  files/latest.yml                               versi terbaru; url/path menunjuk ke foldernya
  files/desktop/<versi>/erp-desktop-setup.exe    + .blockmap
Hanya KEEP versi terakhir yang disimpan; yang lebih lama dihapus tiap unggah. Folder per
versi juga yang membuat update cukup mengunduh bagian yang berubah: electron-updater mencari
blockmap versi lama di URL versi baru dengan nomor versinya diganti.

Unggah per potongan karena installer melebihi batas request Frappe (25 MB) dan nginx (50 MB).
Potongan ditampung di private/desktop_upload/<id>/, lalu installer dicek sha512-nya terhadap
latest.yml sebelum diterbitkan. latest.yml ditulis PALING AKHIR, jadi aplikasi tidak pernah
membaca versi yang berkasnya belum ada.
"""

import base64
import hashlib
import os
import re
import shutil
import time
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import convert_utc_to_system_timezone

KEEP = 3
EXE = "erp-desktop-setup.exe"
NAMES = (EXE, EXE + ".blockmap", "latest.yml")
MAX_CHUNK = 8 * 1024 * 1024
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
# Sisa unggahan yang terputus dibuang sesudah sekian detik.
STALE_SECONDS = 86400


def _public(*parts) -> str:
	return frappe.get_site_path("public", "files", *parts)


def _staging(*parts) -> str:
	return frappe.get_site_path("private", "desktop_upload", *parts)


def _key(version: str) -> tuple:
	return tuple(int(x) for x in version.split("."))


def _check_id(upload_id: str):
	if not re.fullmatch(r"[a-z0-9]{10,40}", upload_id or ""):
		frappe.throw(_("Invalid upload id."))


def _versions() -> list[str]:
	"""Versi yang ada di server, terbaru dulu."""
	root = _public("desktop")
	if not os.path.isdir(root):
		return []
	return sorted((v for v in os.listdir(root) if VERSION.match(v)), key=_key, reverse=True)


def _latest() -> str | None:
	try:
		with open(_public("latest.yml"), encoding="utf-8") as f:
			m = re.search(r"^version:\s*['\"]?([0-9.]+)", f.read(), re.M)
		return m and m[1]
	except FileNotFoundError:
		return None


@frappe.whitelist()
def status() -> dict:
	frappe.only_for("System Manager")
	rows = []
	for v in _versions():
		exe = _public("desktop", v, EXE)
		rows.append(
			{
				"version": v,
				"size": os.path.getsize(exe) if os.path.exists(exe) else 0,
				"uploaded": _local(os.path.getmtime(_public("desktop", v))),
			}
		)
	return {"latest": _latest(), "versions": rows, "keep": KEEP}


def _local(mtime: float) -> str:
	# jam server (kontainer) = UTC; tampilkan dalam zona waktu sistem ERP
	utc = datetime.fromtimestamp(mtime, timezone.utc).replace(tzinfo=None)
	return convert_utc_to_system_timezone(utc).strftime("%Y-%m-%d %H:%M")


@frappe.whitelist(methods=["POST"])
def upload_chunk(upload_id: str, name: str, offset: int) -> int:
	"""Satu potongan berkas (multipart field `chunk`), berurutan dari offset 0."""
	frappe.only_for("System Manager")
	_check_id(upload_id)
	if name not in NAMES:
		frappe.throw(_("Unexpected file {0}.").format(name))
	data = frappe.request.files["chunk"].read()
	if len(data) > MAX_CHUNK:
		frappe.throw(_("Chunk too large."))

	offset = int(offset)
	folder = _staging(upload_id)
	if offset == 0 and name == NAMES[0]:
		_drop_stale()
	os.makedirs(folder, exist_ok=True)
	target = os.path.join(folder, name)
	have = os.path.getsize(target) if os.path.exists(target) else 0
	if have != offset:
		frappe.throw(_("Upload of {0} is out of order (server has {1} bytes, got offset {2}).").format(name, have, offset))
	with open(target, "ab" if offset else "wb") as f:
		f.write(data)
	return offset + len(data)


def _drop_stale():
	root = _staging()
	if not os.path.isdir(root):
		return
	for d in os.listdir(root):
		path = os.path.join(root, d)
		if time.time() - os.path.getmtime(path) > STALE_SECONDS:
			shutil.rmtree(path, ignore_errors=True)


@frappe.whitelist(methods=["POST"])
def publish(upload_id: str) -> dict:
	"""Cek berkas yang sudah terunggah lalu terbitkan sebagai versi terbaru."""
	frappe.only_for("System Manager")
	_check_id(upload_id)
	src = _staging(upload_id)
	try:
		for n in NAMES:
			if not os.path.exists(os.path.join(src, n)):
				frappe.throw(_("{0} was not uploaded.").format(n))

		with open(os.path.join(src, "latest.yml"), encoding="utf-8") as f:
			yml = f.read()
		version = re.search(r"^version:\s*['\"]?([0-9.]+)['\"]?\s*$", yml, re.M)
		sha512 = re.search(r"^sha512:\s*['\"]?([A-Za-z0-9+/=]+)", yml, re.M)
		if not version or not VERSION.match(version[1]) or not sha512:
			frappe.throw(_("latest.yml is not from the desktop app build (desktop/dist)."))
		version = version[1]

		digest = hashlib.sha512()
		with open(os.path.join(src, EXE), "rb") as f:
			for block in iter(lambda: f.read(1024 * 1024), b""):
				digest.update(block)
		if base64.b64encode(digest.digest()).decode() != sha512[1]:
			frappe.throw(_("{0} does not match latest.yml. Upload the three files from the same build.").format(EXE))

		newest = _versions()[:1]
		if newest and _key(version) < _key(newest[0]):
			frappe.throw(_("Version {0} is older than the published version {1}.").format(version, newest[0]))

		dst = _public("desktop", version)
		os.makedirs(dst, exist_ok=True)
		for n in (EXE, EXE + ".blockmap"):
			os.replace(os.path.join(src, n), os.path.join(dst, n))

		rel = f"desktop/{version}/{EXE}"
		yml = re.sub(
			rf"^(\s*-?\s*(?:url|path):\s*)['\"]?{re.escape(EXE)}['\"]?\s*$", lambda m: m[1] + rel, yml, flags=re.M
		)
		tmp = _public("latest.yml.tmp")
		with open(tmp, "w", encoding="utf-8") as f:
			f.write(yml)
		os.replace(tmp, _public("latest.yml"))

		removed = _prune()
		# Susunan lama (installer langsung di /files) tidak dipakai lagi.
		for n in (EXE, EXE + ".blockmap"):
			if os.path.exists(_public(n)):
				os.remove(_public(n))
	finally:
		shutil.rmtree(src, ignore_errors=True)

	out = status()
	out["published"] = version
	out["removed"] = removed
	return out


def _prune() -> list[str]:
	removed = _versions()[KEEP:]
	for v in removed:
		shutil.rmtree(_public("desktop", v), ignore_errors=True)
	return removed

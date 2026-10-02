"""Lokasi fisik lampiran site ini, diatur di ERPNext Custom Setting > Attachment.

Frappe selalu menulis ke sites/<site>/{private,public}/files. Lokasi lain = folder `private` dan
`public` milik site diganti symlink ke <folder>/private dan <folder>/public. URL di tabel File
tidak berubah, jadi tidak ada record yang perlu disentuh.

Folder pilihan harus di bawah ROOT: hanya folder yang di-mount compose (ATTACHMENT_ROOT di .env)
yang terlihat container. Setting kosong = lokasi bawaan (folder site), seperti sebelum fitur ini.

Pindah lokasi = SALIN lalu alihkan, berkas asal tidak dihapus. Satu-satunya yang diubah di asal:
folder site yang masih folder biasa diganti nama jadi <nama>.old-<waktu> (tempatnya dipakai symlink).
Hapus asal hanya lewat tombol Delete Old Folders.

Yang disymlink `private`/`public`, BUKAN `files`: bench backup menjalankan
`tar cf - ./<site>/private/files`, dan tar menyimpan symlink yang disebut langsung sebagai link
saja (backup berkas kosong tanpa galat). Symlink di folder induk ditembus biasa.
"""

import os
import shutil

import frappe
from frappe import _
from frappe.utils import now_datetime

ROOT = "/mnt/attachments"
PARTS = ("private", "public")
SETTING = "ERPNext Custom Setting"


def _site(part: str) -> str:
	return os.path.abspath(frappe.get_site_path(part))


def active_folder() -> str:
	"""Folder induk private/public yang dipakai sekarang; "" = lokasi bawaan (folder site)."""
	link = _site("private")
	return os.path.dirname(os.path.realpath(link)) if os.path.islink(link) else ""


def _job_id() -> str:
	return f"attachment_storage::{frappe.local.site}"


def _walk(path: str):
	for dirpath, _dirs, files in os.walk(path):
		for name in files:
			yield os.path.join(dirpath, name)


def _usage(path: str) -> tuple[int, int]:
	count = size = 0
	for f in _walk(path):
		count += 1
		size += os.path.getsize(f)
	return count, size


def _human(size: float) -> str:
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024:
			return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
		size /= 1024
	return f"{size:.1f} TB"


def check_target(folder: str) -> str:
	"""Rapikan + validasi folder tujuan. Kembalian "" = kembali ke lokasi bawaan."""
	folder = (folder or "").strip()
	if not folder:
		return ""

	target = os.path.normpath(folder)
	if not os.path.isabs(target) or os.path.commonpath([target, ROOT]) != ROOT:
		frappe.throw(_("Attachment Folder must be inside {0}, e.g. {0}/{1}.").format(ROOT, frappe.local.site))
	if not os.path.ismount(ROOT):
		frappe.throw(
			_("{0} is not mounted in this container. Set ATTACHMENT_ROOT in .env and recreate the containers first.").format(ROOT)
		)

	if target == active_folder():
		return target

	for part in PARTS:
		dst = os.path.join(target, part)
		if os.path.isdir(dst) and os.listdir(dst):
			frappe.throw(_("{0} already contains files. Choose an empty folder.").format(dst))
		src = os.path.realpath(_site(part))
		if os.path.commonpath([target, src]) == src:
			frappe.throw(_("Attachment Folder cannot be inside the current attachment folder."))

	try:
		os.makedirs(target, exist_ok=True)
		probe = os.path.join(target, ".Write-Test")
		with open(probe, "w") as f:
			f.write("ok")
		# Folder Windows (D:\ lewat Docker Desktop) tidak membedakan kapital: "A.pdf" dan "a.pdf"
		# yang sama-sama ada di Frappe akan saling timpa.
		case_blind = os.path.exists(os.path.join(target, ".write-test"))
		os.remove(probe)
	except OSError as e:
		frappe.throw(_("Cannot write to {0}: {1}").format(target, e))
	if case_blind:
		frappe.throw(
			_("{0} is not case-sensitive (Windows folder). Files whose names differ only in capitals would overwrite each other. On the host run: fsutil file setCaseSensitiveInfo <folder> enable").format(target)
		)

	need = sum(_usage(os.path.realpath(_site(p)))[1] for p in PARTS)
	free = shutil.disk_usage(target).free
	if free < need * 1.1:
		frappe.throw(_("Not enough space in {0}: need {1}, free {2}.").format(target, _human(need), _human(free)))
	return target


@frappe.whitelist()
def status():
	frappe.only_for("System Manager")
	parts = {}
	for part in PARTS:
		path = os.path.realpath(_site(part))
		count, size = _usage(os.path.join(path, "files"))
		parts[part] = {"path": path, "count": count, "size": _human(size)}

	disk = shutil.disk_usage(os.path.realpath(_site("private")))
	from frappe.utils.background_jobs import is_job_enqueued

	return {
		"active": active_folder(),
		"site_folder": os.path.abspath(frappe.get_site_path()),
		"root": ROOT,
		"root_mounted": os.path.ismount(ROOT),
		"parts": parts,
		"disk_free": _human(disk.free),
		"disk_total": _human(disk.total),
		"running": is_job_enqueued(_job_id()),
	}


@frappe.whitelist()
def migrate():
	"""Salin lampiran ke folder di setting (sudah tersimpan) lalu alihkan ke sana."""
	frappe.only_for("System Manager")
	target = check_target(frappe.db.get_single_value(SETTING, "attachment_folder"))
	if target == active_folder():
		frappe.throw(_("Attachments are already stored in this folder."))
	_enqueue(_migrate_job, target=target)
	return _("Copying attachments in the background. You will get a message when it is done.")


@frappe.whitelist()
def delete_old():
	frappe.only_for("System Manager")
	if not _old_paths():
		frappe.throw(_("There are no old folders to delete."))
	_enqueue(_delete_old_job)
	return _("Deleting old folders in the background.")


def _enqueue(method, **kwargs):
	from frappe.utils.background_jobs import is_job_enqueued

	# Satu job_id untuk migrasi dan hapus: keduanya tidak boleh jalan bersamaan.
	if is_job_enqueued(_job_id()):
		frappe.throw(_("Another attachment job is still running."))
	frappe.enqueue(
		method, queue="long", timeout=6 * 3600, job_id=_job_id(), user=frappe.session.user, **kwargs
	)


def _copy(src: str, dst: str):
	"""Salin isi src ke dst, lewati berkas yang sudah sama (ukuran + waktu ubah)."""
	for a in _walk(src):
		b = os.path.join(dst, os.path.relpath(a, src))
		sa = os.stat(a)
		if os.path.exists(b):
			sb = os.stat(b)
			if sb.st_size == sa.st_size and int(sb.st_mtime) == int(sa.st_mtime):
				continue
		os.makedirs(os.path.dirname(b), exist_ok=True)
		shutil.copy2(a, b)


def _verify(src: str, dst: str):
	for a in _walk(src):
		b = os.path.join(dst, os.path.relpath(a, src))
		if not os.path.exists(b) or os.path.getsize(b) != os.path.getsize(a):
			raise Exception(f"Copy check failed: {b}")


def _switch(link: str, dst: str, stamp: str) -> str | None:
	"""Arahkan sites/<site>/<part> ke dst. Kembalian: folder asal yang diganti nama (kalau ada)."""
	if os.path.islink(link):
		# symlink -> folder lain / kembali ke bawaan: ganti atomik, asal tidak disentuh
		if dst == link + ".copying":
			# rename folder tidak bisa menimpa symlink (ENOTDIR): lepas dulu, jedanya sekejap
			os.unlink(link)
			os.rename(dst, link)
		else:
			tmp = f"{link}.link-{stamp}"
			os.symlink(dst, tmp)
			os.replace(tmp, link)
		return None
	# Folder biasa (lokasi bawaan): tempatnya dipakai symlink, isinya disimpan dengan nama lain.
	old = f"{link}.old-{stamp}"
	os.rename(link, old)
	os.symlink(dst, link)
	return old


def migrate_files(target: str, stamp: str, lines: list, renamed: list):
	for part in PARTS:
		link = _site(part)
		src = os.path.realpath(link)
		# Kembali ke bawaan: salin ke folder sementara di folder site, lalu rename menimpa symlink.
		dst = os.path.join(target, part) if target else link + ".copying"
		_copy(src, dst)
		_copy(src, dst)  # berkas yang masuk selama salinan pertama
		_verify(src, dst)
		old = _switch(link, dst, stamp)
		src_now = old or src
		_copy(src_now, os.path.realpath(link))  # berkas yang masuk di sela salinan dan pengalihan
		_verify(src_now, os.path.realpath(link))
		if old:
			renamed.append(old)
		count, size = _usage(os.path.join(os.path.realpath(link), "files"))
		lines.append(f"{part}: {count} files, {_human(size)} -> {os.path.realpath(link)} (source kept: {src_now})")


def _migrate_job(target: str, user: str):
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	lines, renamed = [], []
	try:
		migrate_files(target, stamp, lines, renamed)
	except Exception:
		lines.append("FAILED: " + frappe.get_traceback(with_context=False).strip().splitlines()[-1])
		frappe.log_error("Attachment migrate failed")

	ok = not lines or not lines[-1].startswith("FAILED")
	result = f"{now_datetime():%Y-%m-%d %H:%M:%S} migrate to {target or 'default (site folder)'}\n" + "\n".join(lines)
	values = {"attachment_last_result": result}
	if renamed:
		values["attachment_old_paths"] = "\n".join(_old_paths() + renamed)
	if not ok:
		values["attachment_folder"] = active_folder()  # setting kembali menunjuk lokasi yang dipakai
	frappe.db.set_single_value(SETTING, values)
	frappe.db.commit()
	_notify(user, _("Attachment migration finished.") if ok else _("Attachment migration failed."), result)


def _old_paths() -> list[str]:
	return [p for p in (frappe.db.get_single_value(SETTING, "attachment_old_paths") or "").splitlines() if p]


def _delete_old_job(user: str):
	lines, keep = [], []
	site = os.path.abspath(frappe.get_site_path())
	for path in _old_paths():
		name = os.path.basename(path)
		# Hanya folder yang dibuat _switch: <site>/private.old-* atau <site>/public.old-*
		if os.path.dirname(path) != site or not name.startswith(tuple(f"{p}.old-" for p in PARTS)):
			lines.append(f"skipped (not an old attachment folder): {path}")
			continue
		try:
			shutil.rmtree(path)
			lines.append(f"deleted: {path}")
		except FileNotFoundError:
			lines.append(f"already gone: {path}")
		except OSError as e:
			keep.append(path)
			lines.append(f"FAILED {path}: {e}")

	result = f"{now_datetime():%Y-%m-%d %H:%M:%S} delete old folders\n" + "\n".join(lines)
	frappe.db.set_single_value(
		SETTING, {"attachment_old_paths": "\n".join(keep), "attachment_last_result": result}
	)
	frappe.db.commit()
	_notify(user, _("Old attachment folders deleted."), result)


def _notify(user: str, title: str, body: str):
	frappe.publish_realtime(
		"msgprint", {"title": title, "message": f"<pre>{frappe.utils.escape_html(body)}</pre>"}, user=user
	)

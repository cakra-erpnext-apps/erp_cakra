import frappe
from frappe.model.document import Document


SOUND_EXTENSIONS = ("mp3", "wav", "ogg", "m4a")
SOUND_MAX_BYTES = 1024 * 1024


class ERPNextCustomSetting(Document):
	def validate(self):
		from erpnext_custom.outlook_addin import SYNC_SECONDS_MIN

		seconds = self.get("mailbox_sync_seconds")
		if seconds and seconds < SYNC_SECONDS_MIN:
			frappe.throw(
				frappe._("Auto Sync Interval must be at least {0} seconds.").format(SYNC_SECONDS_MIN)
			)
		self.validate_notification_sound()
		if self.has_value_changed("attachment_folder"):
			from erpnext_custom.attachment_storage import check_target

			self.attachment_folder = check_target(self.attachment_folder)

	def validate_notification_sound(self):
		url = self.get("notification_sound")
		if not url:
			return
		if url.rsplit(".", 1)[-1].lower() not in SOUND_EXTENSIONS:
			frappe.throw(frappe._("Sound File must be MP3, WAV, OGG, or M4A."))
		size = frappe.db.get_value("File", {"file_url": url}, "file_size") or 0
		if size > SOUND_MAX_BYTES:
			frappe.throw(frappe._("Sound File must be 1 MB or smaller."))

	def on_update(self):
		# Sebagian setting ikut dikirim lewat boot (lihat erpnext_custom.item_scope.boot),
		# dan bootinfo di-cache per user. Tanpa dibersihkan, daftar yang baru disimpan —
		# mis. tipe Expense Note yang pakai grid — baru terasa setelah user logout/login.
		self.publish_notification_sound()
		frappe.clear_cache()

	def publish_notification_sound(self):
		# Diputar di browser SEMUA user (notification_badge.js), padahal berkas privat hanya
		# boleh diunduh pemegang izin dokumen ini. File.is_private=0 memindahkan berkasnya ke
		# /files; field ini ditulis ulang di sini karena File hanya melakukannya kalau
		# attached_to_field terisi.
		url = self.get("notification_sound")
		if not url or not url.startswith("/private/"):
			return
		name = frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": self.doctype})
		if not name:
			return
		file = frappe.get_doc("File", name)
		file.is_private = 0
		file.save(ignore_permissions=True)
		self.notification_sound = file.file_url
		frappe.db.set_single_value(self.doctype, "notification_sound", file.file_url)

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_custom import bin_layout


class BinLocation(Document):
	def autoname(self):
		# gudang diturunkan dari rak (fetch_from belum tentu terisi saat penamaan).
		self.gudang = frappe.db.get_value("Rack", self.rack, "gudang")
		self.bin_code = (self.bin_code or "").strip()
		self.name = "{0} - {1}".format(self.bin_code, self.gudang)

	def validate(self):
		self.gudang = frappe.db.get_value("Rack", self.rack, "gudang")
		self.bin_code = (self.bin_code or "").strip()
		bin_layout.set_position_from_name(self)
		kind = frappe.get_cached_value("Rack", self.rack, "kind")
		if kind not in ("Rak", "Staging"):
			frappe.throw(_("{0} jenisnya {1}, bukan tempat yang bisa diisi bin.").format(self.rack, kind))
		self._check_merge()

	def _check_merge(self):
		"""Gabung bin = bin ini menyerahkan kapasitasnya ke bin induk dan berhenti
		dipakai sendiri. Cuma satu tingkat, sesama rak, dan bin harus kosong dulu."""
		if not self.merged_into:
			return
		if self.merged_into == self.name:
			frappe.throw(_("Bin tidak bisa digabung ke dirinya sendiri."))
		target = frappe.db.get_value(
			"Bin Location", self.merged_into, ["rack", "merged_into"], as_dict=True
		)
		if target.rack != self.rack:
			frappe.throw(
				_("Bin {0} ada di rak lain. Gabung hanya boleh sesama bin satu rak.").format(
					self.merged_into
				)
			)
		if target.merged_into:
			frappe.throw(
				_("Bin {0} sendiri sudah digabung ke {1}, gabungkan langsung ke bin induknya.").format(
					self.merged_into, target.merged_into
				)
			)
		if frappe.db.exists("Bin Location", {"merged_into": self.name}):
			frappe.throw(
				_("Bin {0} sudah menampung gabungan bin lain, jadi tidak bisa ikut digabung.").format(
					self.name
				)
			)
		if frappe.db.exists("Item Bin Qty", {"bin_location": self.name, "qty": [">", 0]}):
			frappe.throw(
				_("Bin {0} masih berisi barang, kosongkan dulu sebelum digabung.").format(self.name)
			)

	def on_trash(self):
		if frappe.db.exists("Item Bin Qty", {"bin_location": self.name, "qty": [">", 0]}):
			frappe.throw(_("Bin {0} masih berisi barang, kosongkan dulu lewat Goods Receive.").format(self.name))

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Rack(Document):
	def validate(self):
		if frappe.get_cached_value("Warehouse", self.gudang, "is_group"):
			frappe.throw(_("{0} adalah group warehouse, tidak bisa dipakai sebagai gudang rak.").format(self.gudang))
		self.rack_code = (self.rack_code or "").strip()
		# Volume DITURUNKAN, tidak pernah diketik: kalau diisi tangan ia langsung
		# berbeda dari kotak yang digambar di denah, dan tidak ada cara tahu mana
		# yang benar. Semua satuannya meter.
		self.volume = flt(self.panjang) * flt(self.lebar) * flt(self.tinggi)
		self.rack_zone = (self.rack_zone or "").strip().upper() or None
		# Pintu dan Kantor cuma kotak di denah -- tidak pernah memegang barang.
		if self.kind not in ("Rak", "Staging") and frappe.db.exists("Bin Location", {"rack": self.name}):
			frappe.throw(
				_("{0} masih punya bin, jadi tidak bisa dijadikan {1}.").format(self.name, self.kind)
			)

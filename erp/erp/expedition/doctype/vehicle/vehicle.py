from frappe.model.document import Document


class Vehicle(Document):
    def before_naming(self):
        # nama dokumen = nopol; kalau nopol belum ada, pakai Nama Kendaraan/Nopol
        if not self.code:
            self.code = self.title

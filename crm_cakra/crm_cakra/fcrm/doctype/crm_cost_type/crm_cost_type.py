from frappe.model.document import Document

from crm_cakra.utils import apply_rename, capture_rename


class CRMCostType(Document):
	"""Tipe komponen biaya, boleh ditambah sendiri oleh user.

	Namanya bebas ("Biaya Jalan", "Overhead Kantor", "Handling"), tapi tiap tipe
	wajib memilih behavior: rumus harga cuma mengenal dua peran, biaya tetap per
	hari atau biaya variabel yang disalin ke quotation.
	"""

	def before_validate(self):
		capture_rename(self, "type_name")

	def on_update(self):
		apply_rename(self)

	@staticmethod
	def default_list_data():
		columns = [
			{"label": "Type", "type": "Data", "key": "name", "width": "16rem"},
			{"label": "Behavior", "type": "Select", "key": "behavior", "width": "12rem"},
			{"label": "Description", "type": "Data", "key": "description", "width": "22rem"},
			{"label": "Disabled", "type": "Check", "key": "disabled", "width": "6rem"},
			{"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
		]
		rows = ["name", "type_name", "behavior", "description", "disabled", "modified"]
		return {"columns": columns, "rows": rows}

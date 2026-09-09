# Copyright (c) 2026, Cakra ERPNext Apps and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CMIConnectionModuleRef(Document):
	"""Baris Table MultiSelect berisi satu doctype yang boleh ditaut di section Connection.

	Pilihannya dibatasi link_filters ke doctype yang peta party-nya memang ada di
	erp.fico.doctype.pending_cash.pending_cash.CONNECTION_PARTY_FIELD — di luar itu kolom
	Customer / Vendor tidak akan terisi.
	"""

	pass

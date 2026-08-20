# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class CRMEstimationQuotation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		currency: DF.Link | None
		customer: DF.Data | None
		loading: DF.Data | None
		net_total: DF.Currency
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		quotation: DF.Link
		quotation_date: DF.Date | None
		status: DF.Data | None
		subject: DF.Data | None
		unloading: DF.Data | None
	# end: auto-generated types

	pass

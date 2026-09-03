import frappe
from frappe.model.document import Document


class CRMEstimationDetail(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        amount: DF.Currency
        area_id: DF.Data | None
        by_qty: DF.Check
        csize: DF.Link
        currency: DF.Link | None
        dest_id: DF.Data | None
        is_expense: DF.Check
        jalur: DF.Data | None
        jenis_karantina: DF.Data | None
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        per_doc: DF.Check
        port_id: DF.Data | None
        product_id: DF.Link | None
        qty: DF.Float
        remarks: DF.SmallText | None
        sandaran_id: DF.Data | None
        shipping_line_id: DF.Data | None
        supplier_id: DF.Data | None
        type_id: DF.Link
        uom: DF.Data | None
    # end: auto-generated types

    pass
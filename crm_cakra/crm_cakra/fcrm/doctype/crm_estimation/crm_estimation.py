import frappe
from frappe import _
from frappe.model.document import Document


class CRMEstimation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from crm_cakra.fcrm.doctype.crm_estimation_detail.crm_estimation_detail import CRMEstimationDetail
        from crm_cakra.fcrm.doctype.crm_estimation_quotation.crm_estimation_quotation import CRMEstimationQuotation
        from frappe.types import DF

        branch_office: DF.Link | None
        customer_id: DF.Data | None
        disabled: DF.Check
        disabled_fleet: DF.Check
        effective_date: DF.Date | None
        est_km: DF.Float
        est_profit: DF.Currency
        estimation_no: DF.Data | None
        estimation_type: DF.Literal["Expedition", "Trading"]
        expense_items: DF.Table[CRMEstimationDetail]
        expired_date: DF.Date | None
        loading: DF.Link | None
        purpose: DF.Literal["Customer", "Agent", "Quotation"]
        quo_no: DF.Link | None
        quotation_links: DF.Table[CRMEstimationQuotation]
        remarks: DF.Text | None
        rev_inc_tax: DF.Currency
        revenue_items: DF.Table[CRMEstimationDetail]
        route1: DF.Link | None
        route2: DF.Link | None
        route3: DF.Link | None
        route4: DF.Link | None
        route5: DF.Link | None
        route6: DF.Link | None
        route7: DF.Link | None
        route8: DF.Link | None
        unloading: DF.Link | None
    # end: auto-generated types

    def autoname(self):
        from frappe.model.naming import make_autoname

        # Format: EST/0001/CMI/26 — counter reset tahunan (kunci seri memuat tahun).
        # Kunci seri "EST/CMI/{yy}/" tercatat di tabSeries sehingga nomor berjalan
        # bisa dilihat/diubah lewat Document Naming Settings > Update Current Value.
        yy = frappe.utils.now_datetime().strftime("%y")
        counter = make_autoname(f"EST/CMI/{yy}/.####.").split("/")[-1]
        name = f"EST/{counter}/CMI/{yy}"
        self.name = name
        self.estimation_no = name

    def validate(self):
        # Purpose wajib Customer/Agent saat disimpan manual.
        # Dikecualikan saat dibuat lewat convert dari quotation (flag from_convert),
        # di mana purpose sengaja diset "Quotation" sebagai penanda.
        if not self.flags.get("from_convert") and self.purpose not in ("Customer", "Agent"):
            frappe.throw(_("Purpose harus dipilih: Customer atau Agent."))

    def before_save(self):
        # Tandai kategori tiap baris (1 child doctype dipakai 2 tabel).
        for d in self.revenue_items:
            d.is_expense = 0
        for d in self.expense_items:
            d.is_expense = 1

        income = sum((d.amount or 0) for d in self.revenue_items)
        expense = sum((d.amount or 0) for d in self.expense_items)
        self.rev_inc_tax = income
        self.est_profit = income - expense

    @staticmethod
    def default_list_data():
        columns = [
            # "Name" (bukan "Number") -- seragam dengan list Inquiry & Quotation.
            {"label": "Name", "type": "Data", "key": "name", "width": "12rem"},
            {"label": "Customer", "type": "Data", "key": "customer_id", "width": "16rem"},
            {"label": "Type", "type": "Data", "key": "estimation_type", "width": "8rem"},
            {"label": "Purpose", "type": "Select", "key": "purpose", "width": "8rem"},
            {"label": "Expired Date", "type": "Date", "key": "expired_date", "width": "9rem"},
            {"label": "Est. Profit", "type": "Currency", "key": "est_profit", "width": "10rem"},
            {"label": "Created By", "type": "Link", "key": "owner", "width": "10rem"},
            {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
        ]
        rows = [
            "name",
            "estimation_no",
            "customer_id",
            "estimation_type",
            "purpose",
            "expired_date",
            "est_profit",
            "owner",
            "modified",
        ]
        return {"columns": columns, "rows": rows}

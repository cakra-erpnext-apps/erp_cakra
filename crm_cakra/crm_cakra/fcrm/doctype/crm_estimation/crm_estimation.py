import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CRMEstimation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from crm_cakra.fcrm.doctype.crm_estimation_detail.crm_estimation_detail import CRMEstimationDetail
        from crm_cakra.fcrm.doctype.crm_estimation_quotation.crm_estimation_quotation import CRMEstimationQuotation
        from frappe.types import DF

        branch_office: DF.Link | None
        customer_id: DF.Link | None
        disabled: DF.Check
        validated: DF.Check
        validated_by: DF.Link | None
        validated_date: DF.Datetime | None
        disabled_fleet: DF.Check
        effective_date: DF.Date | None
        est_km: DF.Float
        est_profit: DF.Currency
        estimation_no: DF.Data | None
        estimation_type: DF.Literal["Expedition", "Trading"]
        expense_items: DF.Table[CRMEstimationDetail]
        expired_date: DF.Date | None
        loading: DF.Link | None
        purpose: DF.Literal["", "Customer", "Agent"]
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
        # Purpose tidak lagi dijaga di sini: opsinya kini hanya Customer/Agent dengan
        # default kosong dan `reqd`, jadi cek bawaan Frappe sudah melakukan hal yang sama.
        # Estimasi hasil convert dari quotation lolos saat insert lewat ignore_mandatory,
        # lalu wajib dipilih orang saat dokumen itu disimpan/divalidasi berikutnya.
        self._require_expense_status()
        self._sync_state()

    def _require_expense_status(self):
        """Status wajib untuk baris Expense saja (Revenue tidak memakai kolom itu).

        Dicek di sini, bukan cukup lewat `mandatory_depends_on` di doctype: properti itu
        HANYA berlaku di sisi client (lihat grid_row.js & save.js) -- server sama sekali
        tidak menegakkannya, sehingga simpan lewat API/import/convert akan lolos begitu saja.
        Yang di doctype dibiarkan tetap ada karena dialah yang menyalakan penanda wajib
        di grid; yang di sini yang benar-benar menjaga.

        ignore_mandatory dihormati supaya perilakunya sama dengan field wajib bawaan --
        convert dari quotation memang sengaja menyimpan dokumen yang belum lengkap.
        """
        if self.flags.ignore_mandatory:
            return
        kosong = [str(d.idx) for d in self.expense_items if not d.status]
        if kosong:
            frappe.throw(
                _("Status wajib dipilih pada baris Expense: {0}").format(", ".join(kosong)),
                frappe.MandatoryError,
            )

    def _sync_state(self):
        """Cap siapa & kapan yang memvalidasi. Dipanggil dari validate() sehingga jalur
        mana pun (tombol form, aksi bulk di list, atau save biasa) menghasilkan cap yang
        sama -- pola identik dengan Maintenance._sync_state."""
        if self.validated:
            if not self.validated_by:
                self.validated_by = frappe.session.user
                self.validated_date = frappe.utils.now_datetime()
        else:
            self.validated_by = None
            self.validated_date = None

    def before_save(self):
        # Tandai kategori tiap baris (1 child doctype dipakai 2 tabel).
        for d in self.revenue_items:
            d.is_expense = 0
        for d in self.expense_items:
            d.is_expense = 1

        default_currency = frappe.defaults.get_global_default("currency")
        for d in self.revenue_items + self.expense_items:
            # Jaring pengaman: default currency & rate dipasang di sisi client saat baris
            # baru ditambah (crm_estimation.js). Baris yang masuk lewat jalur lain --
            # convert dari quotation, import, API -- tetap harus punya keduanya.
            if not d.currency:
                d.currency = default_currency
            # `or 1` bukan sekadar default: kolom rate baru, jadi baris LAMA di database
            # bernilai 0. Tanpa ini seluruh estimasi lama akan berjumlah nol saat disimpan.
            d.rate = flt(d.rate) or 1

        income = sum(flt(d.amount) * flt(d.rate) for d in self.revenue_items)
        expense = sum(flt(d.amount) * flt(d.rate) for d in self.expense_items)
        self.rev_inc_tax = income
        self.est_profit = income - expense

    @staticmethod
    def default_list_data():
        columns = [
            # "Name" (bukan "Number") -- seragam dengan list Inquiry & Quotation.
            {"label": "Name", "type": "Data", "key": "name", "width": "12rem"},
            {"label": "Customer", "type": "Link", "key": "customer_id", "width": "16rem"},
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

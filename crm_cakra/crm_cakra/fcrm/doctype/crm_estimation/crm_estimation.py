import frappe
from frappe import _
from frappe.model.base_document import BaseDocument
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

# Approval 3 level. Procurement & Finance bebas urutan; Marketing = approval akhir,
# baru boleh setelah dua lainnya, dan dialah yang menyalakan `validated` (yang
# dibaca list, sinkron Ascend, dan dokumen hilir).
APPROVAL_ROLES = {
    "procurement": "Estimation Approve Procurement",
    "finance": "Estimation Approve Finance",
    "marketing": "Estimation Approve Marketing",
}


@frappe.whitelist()
def approve(name, level):
    role = APPROVAL_ROLES.get(level)
    if not role:
        frappe.throw(_("Level approval tidak dikenal: {0}").format(level))
    if role not in frappe.get_roles():
        frappe.throw(_("Hanya user dengan role <b>{0}</b> yang boleh approve.").format(role), frappe.PermissionError)

    doc = frappe.get_doc("CRM Estimation", name)
    doc.check_permission("read")
    if doc.disabled:
        frappe.throw(_("Estimation ini Disabled."))
    if doc.get(f"approved_{level}"):
        frappe.throw(_("Sudah di-approve {0}.").format(_(level.title())))
    if level == "marketing" and not (doc.approved_procurement and doc.approved_finance):
        frappe.throw(_("Approval Marketing menunggu approval Procurement dan Finance."))

    doc.set(f"approved_{level}", 1)
    doc.set(f"approved_{level}_by", frappe.session.user)
    doc.set(f"approved_{level}_date", now_datetime())
    if level == "marketing":
        doc.validated = 1
    # Role approval sudah dicek di atas; approver (mis. Finance) belum tentu punya izin write.
    doc.flags.approval_ok = True
    doc.save(ignore_permissions=True)
    return doc.as_dict()


class CRMEstimation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from crm_cakra.fcrm.doctype.crm_estimation_detail.crm_estimation_detail import CRMEstimationDetail
        from crm_cakra.fcrm.doctype.crm_estimation_quotation.crm_estimation_quotation import CRMEstimationQuotation
        from frappe.types import DF

        approved_finance: DF.Check
        approved_finance_by: DF.Link | None
        approved_finance_date: DF.Datetime | None
        approved_marketing: DF.Check
        approved_marketing_by: DF.Link | None
        approved_marketing_date: DF.Datetime | None
        approved_procurement: DF.Check
        approved_procurement_by: DF.Link | None
        approved_procurement_date: DF.Datetime | None
        ascend_approved_by: DF.Data | None
        ascend_estimation_id: DF.Int
        ascend_estimation_no: DF.Data | None
        assigned_to: DF.Data | None
        branch_office: DF.Link | None
        created_by: DF.Data | None
        created_date: DF.Data | None
        customer_id: DF.Link
        disabled: DF.Check
        effective_date: DF.Date | None
        erp_customer: DF.Link
        est_km: DF.Float
        est_profit: DF.Currency
        estimation_no: DF.Data | None
        estimation_type: DF.Literal["Expedition", "Trading"]
        expense_items: DF.Table[CRMEstimationDetail]
        expired_date: DF.Date
        internal_remark: DF.Text | None
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
        validated: DF.Check
        validated_by: DF.Link | None
        validated_date: DF.Datetime | None
    # end: auto-generated types

    # Estimasi Ascend (nama ASC-<EstimationID>) tidak disimpan di ERPNext: dibaca dan ditulis
    # langsung ke SQL Server (crm_cakra/integrations/ascend.py), form CRM dipakai apa adanya.
    def load_from_db(self):
        from crm_cakra.integrations import ascend

        if not ascend.is_ascend_name(self.name):
            return super().load_from_db()
        doc, children = ascend.load_doc(self.name)
        BaseDocument.__init__(self, doc)
        for field, rows in children.items():
            self.set(field, rows)
        return self

    def save(self, *args, **kwargs):
        from crm_cakra.integrations import ascend

        if not ascend.is_ascend_name(self.name):
            return super().save(*args, **kwargs)
        self.check_permission("write")
        ascend.save_doc(self)
        return self.load_from_db()

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
        self.sync_route_slots()
        self._require_row_fields()
        self._guard_approvals()
        self._sync_state()
        self._validate_quotation_link()

    def sync_route_slots(self):
        """Tabel Routes -> Loading/Unloading, KM, dan Route 1..8 (yang dikirim ke Ascend).

        Satu estimasi bisa punya beberapa destination; slot Route diisi urutan
        titik unik origin/destination tiap baris, maksimal 8.
        """
        from crm_cakra.api.route import sync_route_header

        rows = sync_route_header(self, "loading", "unloading")
        if not rows:
            return
        if any(flt(r.est_km) for r in rows):
            self.est_km = sum(flt(r.est_km) for r in rows)
        stops = list(dict.fromkeys(p for r in rows for p in (r.origin, r.destination)))[:8]
        for i in range(1, 9):
            self.set(f"route{i}", stops[i - 1] if i <= len(stops) else None)

    def _validate_quotation_link(self):
        """Estimasi yang lahir dari sebuah quotation harus lolos syarat convert.

        Sejak alur convert berubah (user memeriksa dulu di form New Estimation,
        baru menekan Save), dokumennya lahir dari halaman New biasa -- bukan lagi
        dari satu panggilan server yang sudah memeriksa semuanya. Jadi syaratnya
        diperiksa di sini: quotation harus Win, belum dikonversi, tidak void, dan
        belum punya estimasi lain.
        """
        if not self.is_new() or not self.quo_no:
            return
        from crm_cakra.fcrm.doctype.crm_quotation.crm_quotation import _assert_convertible

        _assert_convertible(frappe.get_doc("CRM Quotation", self.quo_no))

    def after_insert(self):
        """Kunci quotation asalnya begitu estimasinya benar-benar tersimpan.

        Satu tempat untuk dua jalur (form New Estimation dan convert_to_estimation
        lewat API): selama estimasinya belum tersimpan, quotation tetap bisa
        diubah dan tidak berubah status.
        """
        if not self.quo_no:
            return
        from crm_cakra.fcrm.doctype.crm_quotation.crm_quotation import _copy_assignees

        frappe.db.set_value("CRM Quotation", self.quo_no, "state", "Converted")
        # Warisi assignee quotation -> estimasi (kontrol akses transaksi ikut terbawa).
        _copy_assignees("CRM Quotation", self.quo_no, "CRM Estimation", self.name)

    def on_trash(self):
        # Estimasi berpasangan 1:1 dengan Ascend; menghapus di sini meninggalkan yatim di sana.
        # Hak delete juga sudah dicabut dari semua role -- ini menjaga Administrator & API.
        frappe.throw(_("Estimation tidak bisa dihapus. Centang Disabled untuk menonaktifkan."))

    def _guard_approvals(self):
        """Approval hanya lewat approve(); save biasa/API tidak boleh mengubahnya.

        `validated` juga tidak boleh menyala tanpa approval Marketing -- termasuk lewat
        tombol Validate workflow CMI (CRM Estimation terdaftar di CHECKBOX). Invalidate
        (validated 1 -> 0) mereset ketiga level supaya diulang dari awal.
        """
        before = self.get_doc_before_save()
        was_validated = before and before.validated
        if was_validated and not self.validated:
            for level in APPROVAL_ROLES:
                self.set(f"approved_{level}", 0)
                self.set(f"approved_{level}_by", None)
                self.set(f"approved_{level}_date", None)
            return
        if self.flags.approval_ok:
            return
        for level in APPROVAL_ROLES:
            if cint(self.get(f"approved_{level}")) != cint(before.get(f"approved_{level}") if before else 0):
                frappe.throw(_("Approval hanya bisa lewat tombol Approve."), frappe.PermissionError)
        if self.validated and not was_validated and not self.approved_marketing:
            frappe.throw(_("Estimation tervalidasi lewat approval Procurement, Finance, lalu Marketing."))

    def _require_row_fields(self):
        """Wajib isi per sisi: Revenue = ERP Product (type_id) + ERP Customer,
        Expense = Item (type_id) + Status.

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
        for rows, side, fields in (
            (self.revenue_items, "Revenue", (("type_id", "ERP Product"),)),
            (self.expense_items, "Expense", (("status", "Status"), ("type_id", "Item"))),
        ):
            for field, label in fields:
                kosong = [str(d.idx) for d in rows if not d.get(field)]
                if kosong:
                    frappe.throw(
                        _("{0} wajib diisi pada baris {1}: {2}").format(label, side, ", ".join(kosong)),
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
    def merge_list_data(data, rows, filters, search, order_by, page_length):
        # Estimasi Ascend dibaca langsung dari SQL Server (EXP_Estimation), tidak disalin ke sini.
        from crm_cakra.integrations.ascend import merge_list

        return merge_list(data, rows, filters, search, order_by, page_length)

    @staticmethod
    def default_list_data():
        columns = [
            # "Name" (bukan "Number") -- seragam dengan list Inquiry & Quotation.
            {"label": "Name", "type": "Data", "key": "name", "width": "12rem"},
            {"label": "Customer", "type": "Link", "key": "customer_id", "width": "16rem"},
            # Ascend No terisi = baris dibaca langsung dari Ascend (EXP_Estimation).
            {"label": "Ascend No", "type": "Data", "key": "ascend_estimation_no", "width": "8rem"},
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
            "ascend_estimation_no",
            "estimation_type",
            "purpose",
            "expired_date",
            "est_profit",
            "owner",
            "modified",
        ]
        return {"columns": columns, "rows": rows}

import frappe
from frappe.model.document import Document
from frappe.desk.form.assign_to import add as assign_to_add
from frappe import _


def _copy_assignees(src_dt, src_name, tgt_dt, tgt_name):
    """Salin daftar assignee (ToDo) dari satu dokumen ke dokumen lain.

    Dipakai untuk meneruskan kontrol akses: inquiry -> quotation -> estimation.
    """
    if not src_name or not tgt_name:
        return
    users = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": src_dt,
            "reference_name": src_name,
            "status": ("!=", "Cancelled"),
        },
        pluck="allocated_to",
    )
    for u in {x for x in users if x}:
        assign_to_add(
            {"assign_to": [u], "doctype": tgt_dt, "name": tgt_name},
            ignore_permissions=True,
        )


class CRMQuotation(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from crm_cakra.fcrm.doctype.crm_products.crm_products import CRMProducts
        from frappe.types import DF

        account: DF.Link | None
        account_name: DF.Data | None
        additional1_amount: DF.Text | None
        additional1_item: DF.SmallText | None
        additional1_title: DF.Data | None
        additional2_amount: DF.Text | None
        additional2_item: DF.SmallText | None
        additional2_title: DF.Data | None
        attention: DF.Data | None
        branch: DF.Data | None
        branch_office: DF.Link | None
        cargo: DF.Data | None
        company: DF.Link | None
        contact_name: DF.Link | None
        cost_center: DF.Link | None
        currency: DF.Link | None
        date: DF.Date | None
        disabled: DF.Check
        inquiry: DF.Link | None
        is_void: DF.Check
        loading: DF.SmallText | None
        net_total: DF.Currency
        number: DF.Data | None
        packaging: DF.Data | None
        payterm: DF.SmallText | None
        printed_by: DF.Link | None
        products: DF.Table[CRMProducts]
        rate: DF.Float
        rate_exclude: DF.Text | None
        rate_exclude_amount: DF.Text | None
        rate_include: DF.Text | None
        rate_include_amount: DF.Text | None
        remark: DF.SmallText | None
        state: DF.Literal["Draft", "Created", "Sent", "Approved", "Rejected", "Expired", "Converted"]
        subject: DF.Data | None
        tac: DF.Data | None
        tac_detail: DF.Text | None
        term_detail: DF.Text | None
        unloading: DF.SmallText | None
        validity: DF.SmallText | None
        void_at: DF.Datetime | None
        void_by: DF.Link | None
        void_reason: DF.SmallText | None
    # end: auto-generated types

    def autoname(self):
        from frappe.model.naming import make_autoname

        # Nomor QT reset per tahun: seri "QT-{YYYY}-" -> QT/{counter}/CMI/{YYYY}.
        yyyy = frappe.utils.now_datetime().strftime("%Y")
        counter = make_autoname(f"QT-{yyyy}-.####.").split("-")[-1]
        self.name = f"QT/{counter}/CMI/{yyyy}"

    @staticmethod
    def default_list_data():
        columns = [
            {
                'label': 'Number',
                'type': 'Data',
                'key': 'name',
                'width': '12rem',
            },
            {
                'label': 'Subject',
                'type': 'Data',
                'key': 'subject',
                'width': '16rem',
            },
            {
                'label': 'Account',
                'type': 'Link',
                'key': 'account',
                'width': '14rem',
            },
            {
                'label': 'Inquiry',
                'type': 'Link',
                'key': 'inquiry',
                'width': '12rem',
            },
            {
                'label': 'Date',
                'type': 'Date',
                'key': 'date',
                'width': '8rem',
            },
            {
                'label': 'Net Total',
                'type': 'Currency',
                'key': 'net_total',
                'width': '10rem',
            },
            {
                'label': 'Created By',
                'type': 'Link',
                'key': 'owner',
                'width': '10rem',
            },
            {
                'label': 'Last Modified',
                'type': 'Datetime',
                'key': 'modified',
                'width': '8rem',
            },
        ]
        rows = [
            'name',
            'subject',
            'account',
            'account_name',
            'inquiry',
            'date',
            'net_total',
            'owner',
            'modified',
        ]
        return {'columns': columns, 'rows': rows}   

    def validate(self):
        # 1 inquiry hanya boleh dipakai oleh 1 quotation.
        if self.inquiry:
            dup = frappe.db.exists(
                "CRM Quotation",
                {"inquiry": self.inquiry, "name": ["!=", self.name]},
            )
            if dup:
                frappe.throw(
                    _("Inquiry {0} is already used in quotation {1}").format(self.inquiry, dup)
                )

        # Quotation yang sudah dikonversi ke estimasi bersifat final (tidak bisa diubah).
        if not self.is_new():
            db_state = frappe.db.get_value("CRM Quotation", self.name, "state")
            if db_state == "Converted":
                frappe.throw(
                    _("Quotation {0} sudah dikonversi ke estimasi dan tidak bisa diubah.").format(
                        self.name
                    )
                )

    def before_save(self):
        # Hitung amount tiap produk (qty * price), lalu net total.
        for p in self.products:
            p.amount = (p.qty or 0) * (p.price or 0)
        self.net_total = sum((p.amount or 0) for p in self.products)

        # Default "Printed By" = user pembuat quotation
        if not self.printed_by:
            self.printed_by = self.owner or frappe.session.user

    def after_insert(self):
        # Quotation baru dari inquiry → warisi assignee inquiry (kontrol akses).
        if self.inquiry:
            _copy_assignees("CRM Inquiry", self.inquiry, "CRM Quotation", self.name)


@frappe.whitelist()
def convert_to_estimation(quotation: str):
    """Konversi Quotation -> Estimation.

    - Salin tiap produk quotation (type/item, qty, amount, remark) ke tabel Revenue estimasi.
    - Kolom estimasi yang tidak ada padanannya di quotation dibiarkan kosong.
    - Quotation menjadi final: state -> 'Converted' (terkunci, tidak bisa diubah).
    Mengembalikan nama estimasi baru.
    """
    if not frappe.has_permission("CRM Quotation", "write", quotation):
        frappe.throw(_("Not allowed to convert this Quotation"), frappe.PermissionError)

    quo = frappe.get_doc("CRM Quotation", quotation)

    # Row-lock untuk cegah konversi ganda yang berbarengan (double click / retry).
    locked_state = frappe.db.get_value("CRM Quotation", quotation, "state", for_update=True)
    if locked_state == "Converted" or quo.state == "Converted":
        frappe.throw(_("Quotation {0} is already converted").format(quo.name))
    if quo.is_void:
        frappe.throw(_("Voided quotation cannot be converted"))
    if frappe.db.exists("CRM Estimation", {"quo_no": quo.name}):
        frappe.throw(_("Quotation {0} already has an estimation").format(quo.name))

    est = frappe.new_doc("CRM Estimation")
    est.customer_id = quo.account_name or quo.account
    est.quo_no = quo.name
    est.quo_date = quo.date
    est.effective_date = frappe.utils.today()
    est.purpose = "Quotation"
    est.remarks = quo.remark

    # Produk quotation -> baris Revenue (sisa kolom estimasi dibiarkan kosong).
    for p in quo.products:
        if not p.product or not frappe.db.exists("Item", p.product):
            frappe.throw(
                _("Produk baris {0} ({1}) bukan Item yang valid. Pilih ulang produk lalu simpan quotation sebelum convert.").format(
                    p.idx, p.product or "-"
                )
            )
        est.append(
            "revenue_items",
            {
                "type_id": p.product,
                "qty": p.qty,
                "amount": p.amount or 0,
                "remarks": p.remark,
                "currency": quo.currency or "IDR",
            },
        )

    # Flag agar validate() estimasi melewati cek purpose (purpose sengaja "Quotation").
    est.flags.from_convert = True
    est.insert(ignore_permissions=True)

    # Kunci quotation sebagai final.
    quo.db_set("state", "Converted")

    # Warisi assignee quotation -> estimasi (kontrol akses transaksi ikut terbawa).
    _copy_assignees("CRM Quotation", quo.name, "CRM Estimation", est.name)

    return est.name
        
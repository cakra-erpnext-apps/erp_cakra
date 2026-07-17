import frappe
from frappe.model.document import Document
from frappe.desk.form.assign_to import add as assign_to_add
from frappe import _


_ID_MONTHS_SHORT = (
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Ags", "Sep", "Okt", "Nov", "Des",
)


def _fmt_id_date(d):
    return f"{d.day:02d} {_ID_MONTHS_SHORT[d.month - 1]} {d.year}"


def format_validity_range(start, end=None):
    """Rentang validity untuk print: "27 Jun 2026", "27 Jun - 25 Ags 2026",
    atau "27 Des 2026 - 01 Jan 2027" kalau tahunnya beda.
    """
    if not start:
        return ""
    start = frappe.utils.getdate(start)
    end = frappe.utils.getdate(end) if end else None

    if not end or end == start:
        return _fmt_id_date(start)
    if start.year != end.year:
        return f"{_fmt_id_date(start)} - {_fmt_id_date(end)}"
    # Tahun sama -> cukup ditulis sekali, di ujung kanan.
    return f"{start.day:02d} {_ID_MONTHS_SHORT[start.month - 1]} - {_fmt_id_date(end)}"


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


# Status Quotation -> status CRM Inquiry. Nama status quotation (Win/Lose) sengaja
# berbeda dari status inquiry (Won/Lost), jadi pemetaannya eksplisit di sini.
# State yang tidak ada di sini (Draft, Sent, Waiting, Converted) berarti quotation
# masih berjalan: inquiry didorong ke IN_PROGRESS.
INQUIRY_STATUS_BY_STATE = {"Win": "Won", "Lose": "Lost"}
INQUIRY_STATUS_IN_PROGRESS = "Proposal/Quotation"
INQUIRY_FINAL_STATUSES = ("Won", "Lost")


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
        additional1_item: DF.Text | None
        additional1_title: DF.Data | None
        additional2_amount: DF.Text | None
        additional2_item: DF.Text | None
        additional2_title: DF.Data | None
        attention: DF.Data
        branch: DF.Data | None
        branch_office: DF.Link
        cargo: DF.Data
        company: DF.Link | None
        contact_name: DF.Link | None
        cost_center: DF.Link | None
        currency: DF.Link | None
        date: DF.Date
        disabled: DF.Check
        inquiry: DF.Link
        is_void: DF.Check
        loading: DF.SmallText
        net_total: DF.Currency
        number: DF.Data | None
        packaging: DF.Data
        payterm: DF.SmallText | None
        print_full_page: DF.Check
        printed_by: DF.Link | None
        products: DF.Table[CRMProducts]
        rate: DF.Float
        rate_exclude: DF.Text | None
        rate_exclude_amount: DF.Text | None
        rate_include: DF.Text | None
        rate_include_amount: DF.Text | None
        remark: DF.SmallText | None
        state: DF.Literal["Draft", "Sent", "Waiting", "Win", "Lose", "Converted"]
        subject: DF.Data
        tac: DF.Data | None
        tac_detail: DF.Text | None
        term_detail: DF.Text | None
        unloading: DF.SmallText
        validity: DF.SmallText | None
        validity_date: DF.Date | None
        validity_date_to: DF.Date | None
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
        # Hitung amount tiap produk (qty * price * kurs), lalu net total.
        # rate = kurs currency baris -> currency dasar; amount dalam currency dasar.
        for p in self.products:
            p.amount = (p.qty or 0) * (p.price or 0) * (p.rate or 1)
        self.net_total = sum((p.amount or 0) for p in self.products)

        # Default "Printed By" = user pembuat quotation
        if not self.printed_by:
            self.printed_by = self.owner or frappe.session.user

        self.set_default_validity_date()
        self.validate_validity_range()

    def validate_validity_range(self):
        """validity_date_to opsional: kosong berarti validity cuma satu hari.

        Dipanggil setelah set_default_validity_date supaya validity_date yang
        terisi otomatis ikut terhitung sebagai awal rentang.
        """
        if not self.validity_date_to:
            return
        if not self.validity_date:
            frappe.throw(_("Validity Date To terisi tapi Validity Date kosong."))

        start = frappe.utils.getdate(self.validity_date)
        end = frappe.utils.getdate(self.validity_date_to)
        if end < start:
            frappe.throw(_("Validity Date To tidak boleh lebih awal dari Validity Date."))
        if end == start:
            # Rentang satu hari sama saja dengan tanggal tunggal.
            self.validity_date_to = None

    def get_validity_display(self):
        return format_validity_range(self.validity_date, self.validity_date_to)

    def set_default_validity_date(self):
        """Isi validity_date = date + CRM Settings.default_valid_till (hari).

        Di server, bukan di frontend, supaya quotation yang dibuat lewat Desk atau
        API ikut terisi. validity_date inilah yang dibaca print format dan dashboard;
        field `validity` (teks bebas) hanya keterangan dan tidak bisa dihitung.
        """
        if self.validity_date or not self.date:
            return
        days = frappe.utils.cint(
            frappe.db.get_single_value("CRM Settings", "default_valid_till")
        )
        if days > 0:
            self.validity_date = frappe.utils.add_days(self.date, days)

    def after_insert(self):
        # Quotation baru dari inquiry → warisi assignee inquiry (kontrol akses).
        if self.inquiry:
            _copy_assignees("CRM Inquiry", self.inquiry, "CRM Quotation", self.name)

    def on_update(self):
        self.sync_inquiry_status()

    def sync_inquiry_status(self):
        """Dorong status inquiry mengikuti status quotation.

        Arah tulis hanya satu: quotation -> inquiry. Inquiry yang sudah final
        (Won/Lost) tidak diturunkan lagi kembali ke Proposal/Quotation.
        """
        if not self.inquiry:
            return

        current = frappe.db.get_value("CRM Inquiry", self.inquiry, "status")
        target = INQUIRY_STATUS_BY_STATE.get(self.state)
        if not target:
            if current in INQUIRY_FINAL_STATUSES:
                return
            target = INQUIRY_STATUS_IN_PROGRESS
        if current == target:
            return

        inquiry = frappe.get_doc("CRM Inquiry", self.inquiry)

        # CRM Inquiry.validate_lost_reason() menolak status Lost tanpa alasan.
        # Ditangkap di sini supaya pesannya menunjuk ke akar masalah, bukan
        # melempar ValidationError dari dokumen lain saat user menyimpan quotation.
        if target == "Lost" and not inquiry.lost_reason:
            frappe.throw(
                _("Isi dulu Lost Reason di inquiry {0} sebelum menandai quotation ini Lose.").format(
                    self.inquiry
                )
            )

        inquiry.status = target
        # ignore_permissions: Sales User boleh menutup quotation-nya sendiri walau
        # tidak punya hak tulis ke inquiry milik rekan sebranch.
        # ignore_mandatory: inquiry lama (hasil import) belum punya field wajib yang
        # ditambahkan belakangan. Kita hanya mengubah status, jangan sampai kelengkapan
        # dokumen lain menggagalkan penyimpanan quotation. validate() tetap berjalan,
        # sehingga status_change_log dan closed_date tetap terisi.
        inquiry.flags.ignore_mandatory = True
        inquiry.save(ignore_permissions=True)


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
    # products.product_code menunjuk CRM Product; kode produknya sama dengan
    # kode Item (C-xxxxx), sedangkan revenue_items.type_id menunjuk Item.
    for p in quo.products:
        if not p.product_code or not frappe.db.exists("Item", p.product_code):
            frappe.throw(
                _("Produk baris {0} ({1}) tidak punya Item padanan. Pilih ulang produk lalu simpan quotation sebelum convert.").format(
                    p.idx, p.product_code or "-"
                )
            )
        est.append(
            "revenue_items",
            {
                "type_id": p.product_code,
                "qty": p.qty,
                "amount": p.amount or 0,
                "remarks": p.notes,
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
        
import hashlib

import frappe
from frappe.model.document import Document
from frappe.desk.form.assign_to import add as assign_to_add
from frappe import _
from frappe.utils import cint, flt

from crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component import VARIABLE, resolve_for_product
from crm_cakra.fcrm.doctype.crm_cost_item.crm_cost_item import compute_amount, copy_row


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


# Status yang boleh dicetak saat penguncian cetak dinyalakan.
PRINTABLE_STATES = ("Approved", "Win")


# Tingkat persetujuan margin, dari longgar ke ketat. Memakai role yang SUDAH ada di
# site ini -- menambah role baru berarti tidak ada yang memegangnya di hari pertama,
# dan penawaran macet tanpa ada yang bisa menyetujui.
APPROVAL_TIERS = ("Sales Manager", "Sales Master Manager")


def margin_approval_settings():
    """(aktif, ambang manager, ambang eskalasi). Ambang dibaca sebagai persen."""
    if not frappe.db.get_single_value("FCRM Settings", "enable_margin_approval"):
        return False, 0.0, 0.0
    return (
        True,
        flt(frappe.db.get_single_value("FCRM Settings", "margin_approval_percent")),
        flt(frappe.db.get_single_value("FCRM Settings", "margin_escalation_percent")),
    )


def print_locked_to_approved() -> bool:
    """Nilai flag "Disabled Print When Status Is Not Approved and Win".

    Setelannya milik app erpnext_custom. Ketiadaannya bukan error: CRM harus tetap
    jalan di site yang tidak memasang app itu, dan tanpa setelan artinya tidak ada
    penguncian.
    """
    if not frappe.db.exists("DocType", "ERPNext Custom Setting"):
        return False
    return bool(
        frappe.db.get_single_value("ERPNext Custom Setting", "disable_print_unless_approved")
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
                # "Name", bukan "Number": kolom ini berisi nama dokumen (QT/.../CMI/YYYY),
                # sedangkan field `number` isinya lain (nomor inquiry pada data legacy).
                'label': 'Name',
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
        self.validate_route()
        self.validate_distance()
        self.validate_costing_locked()

        # Satu inquiry BOLEH dipakai banyak quotation (revisi harga, opsi rute, dsb.)
        # -- dashboard/funnel sudah menghitung per inquiry unik, jadi tidak dobel.

        # Quotation yang sudah dikonversi ke estimasi bersifat final (tidak bisa diubah).
        if not self.is_new():
            db_state = frappe.db.get_value("CRM Quotation", self.name, "state")
            if db_state == "Converted":
                frappe.throw(
                    _("Quotation {0} sudah dikonversi ke estimasi dan tidak bisa diubah.").format(
                        self.name
                    )
                )

    def validate_route(self):
        """Loading & Unloading wajib, KECUALI kalau memang sudah kosong dari dulu.

        reqd=1 di doctype sengaja dilepas. Ribuan quotation hasil import Zoho
        rutenya cuma teks bebas ("TG. PRIOK PORT, JAKARTA", "-") yang tidak bisa
        dipetakan ke master lokasi; tulisan aslinya disimpan di loading_text /
        unloading_text. Dengan reqd=1 seluruh arsip itu terkunci: satu field
        wajib yang kosong menolak SEMUA penyimpanan, bukan cuma field itu.

        Jadi aturannya digeser: yang dilarang bukan "kosong", tapi "dikosongkan".
        Dokumen baru tetap wajib mengisi, dan rute yang sudah terisi tidak boleh
        dihapus -- sementara arsip lama yang lahir kosong tetap bisa dibuka dan
        diperbaiki field lainnya.
        """
        if self.is_new():
            before = {}
        else:
            before = (
                frappe.db.get_value(
                    "CRM Quotation", self.name, ["loading", "unloading"], as_dict=True
                )
                or {}
            )

        for fieldname, label in (("loading", _("Loading")), ("unloading", _("Unloading"))):
            if self.get(fieldname):
                continue
            if self.is_new() or before.get(fieldname):
                frappe.throw(_("{0} wajib diisi.").format(label), frappe.MandatoryError)

    def validate_costing_locked(self):
        """Costing yang sudah Approved tidak boleh diubah.

        Yang dikunci hanya isi tab Procurement -- baris produk dan komponen
        biayanya. Field lain (subject, validity, remark) tetap boleh disunting,
        karena yang dinyatakan final oleh Approve adalah harganya, bukan seluruh
        dokumennya.

        Dijaga di server, bukan cukup dengan mengunci tampilan: tab yang sudah
        terbuka sebelum status berubah tetap bisa mengirim perubahan.
        Untuk membukanya kembali, tekan Edit di tab Procurement (statusnya
        kembali ke Waiting).
        """
        if self.is_new():
            return
        if frappe.db.get_value("CRM Quotation", self.name, "state") != "Approved":
            return

        before = self.get_doc_before_save()
        if not before:
            return

        def signature(doc):
            return (
                [
                    (
                        p.product_code,
                        flt(p.qty),
                        cint(p.duration),
                        flt(p.margin_percent),
                        flt(p.price),
                        flt(p.rate),
                    )
                    for p in doc.products
                ],
                [
                    (c.cost_key, c.item_name, flt(c.qty), flt(c.rate))
                    for c in doc.cost_items
                ],
            )

        if signature(self) != signature(before):
            frappe.throw(
                _(
                    "Costing quotation ini sudah Approved. Tekan Edit di tab Procurement dulu untuk mengubahnya."
                )
            )

    def validate_distance(self):
        """KM wajib > 0 -- dengan pengecualian yang sama seperti validate_route.

        Hampir seluruh arsip Zoho (4.795 dari 4.796 quotation) lahir dengan KM 0
        karena rutenya cuma teks bebas. Aturan "> 0" tanpa syarat mengunci semua
        dokumen itu: satu field yang tidak bisa diisi menolak SELURUH penyimpanan,
        termasuk perbaikan field lain. Jadi yang dilarang bukan "kosong", tapi
        "dikosongkan" -- dokumen baru wajib mengisi, KM yang sudah terisi tidak
        boleh dinolkan, arsip lama tetap bisa dibuka dan dibetulkan.
        """
        if (self.distance_km or 0) > 0:
            return

        before = 0
        if not self.is_new():
            before = frappe.db.get_value("CRM Quotation", self.name, "distance_km") or 0

        if self.is_new() or before > 0:
            frappe.throw(
                _("KM wajib diisi dan harus lebih dari 0."), frappe.MandatoryError
            )

    def before_print(self, settings=None):
        """Cetak quotation dikunci status, kalau flag-nya dinyalakan.

        Flag ada di ERPNext Custom Setting > tab CRM ("Disabled Print When Status
        Is Not Approved and Win"). Dimatikan = semua status boleh dicetak, seperti
        sebelumnya.

        Dipasang di before_print, bukan sekadar menyembunyikan tombol: /printview
        adalah URL biasa yang bisa dibuka langsung, dan penawaran yang belum
        disetujui tidak boleh terlanjur beredar sebagai dokumen resmi.
        """
        self.validate_price_floor()
        self.validate_margin_approved()
        if not print_locked_to_approved():
            return
        if self.state not in PRINTABLE_STATES:
            frappe.throw(
                _("Quotation {0} berstatus {1}. Hanya status {2} yang bisa dicetak.").format(
                    self.name, _(self.state), ", ".join(PRINTABLE_STATES)
                )
            )

    def before_save(self):
        self.calculate_costing()

        # Hitung amount tiap produk (qty * price * kurs), lalu net total.
        # rate = kurs currency baris -> currency dasar; amount dalam currency dasar.
        for p in self.products:
            # flt(): angka dari grid datang sebagai string ("2"), dan aritmetika
            # langsung di atasnya meledak (TypeError) atau -- lebih buruk lagi --
            # diam-diam mengulang stringnya.
            p.amount = flt(p.qty) * flt(p.price) * (flt(p.rate) or 1)
        self.net_total = sum(flt(p.amount) for p in self.products)

        # Sesudah harga & costing final, baru tingkat persetujuannya bisa ditentukan.
        self.set_approval_requirement()

    def validate_price_floor(self):
        """Price tidak boleh di bawah Base Price hasil costing -- diperiksa saat CETAK.

        Bukan saat simpan: menyimpan quotation adalah pekerjaan setengah jadi yang
        wajar (harga sedang ditawar, costing baru masuk sebagian), dan menolak
        simpan membuat orang kehilangan pekerjaannya. Yang tidak boleh beredar
        adalah dokumen resminya, jadi lantainya berlaku di before_print.

        Baris tanpa costing (base 0) dilewati -- harganya memang diketik manual,
        dan aturan ini tidak punya dasar untuk menilainya.
        """
        for p in self.products:
            base = flt(p.procurement_price)
            if base <= 0:
                continue
            if flt(p.price) < base:
                frappe.throw(
                    _("Baris {0} ({1}): Price {2} di bawah Base Price {3}.").format(
                        p.idx,
                        p.product_code or "-",
                        frappe.utils.fmt_money(flt(p.price), currency=p.currency or self.currency),
                        frappe.utils.fmt_money(base, currency=p.currency or self.currency),
                    )
                )

    def realized_margin(self):
        """Margin nyata dokumen dalam persen, atau None kalau tidak bisa dinilai.

            margin % = (jual - biaya) / jual x 100

        Biaya = fixed + variable, BUKAN Base Price -- Base Price sudah memuat margin
        rencana, memakainya berarti mengukur margin terhadap dirinya sendiri.

        Baris tanpa costing dilewati, alasan yang sama dengan validate_price_floor:
        harganya diketik manual dan aturan ini tidak punya dasar menilainya. Kalau
        SELURUH baris begitu, hasilnya None -- dokumen tidak dinilai sama sekali,
        bukan dinilai nol.
        """
        jual = biaya = 0.0
        for p in self.products:
            if flt(p.procurement_price) <= 0:
                continue
            qty = flt(p.qty) or 1
            jual += qty * flt(p.price)
            biaya += qty * (flt(p.fixed_cost) + flt(p.variable_cost))
        if jual <= 0:
            return None
        return (jual - biaya) / jual * 100

    def pricing_signature(self):
        """Cap keadaan harga. Berubah = persetujuan atas angka lama tidak berlaku lagi."""
        raw = repr(
            [
                (p.product_code, flt(p.qty), flt(p.price), flt(p.fixed_cost), flt(p.variable_cost))
                for p in self.products
            ]
        )
        # hashlib, bukan hash() bawaan: hash() diacak per proses (PYTHONHASHSEED), jadi
        # cap yang ditulis satu worker tidak akan pernah cocok dibaca worker lain dan
        # setiap persetujuan hangus dengan sendirinya.
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def set_approval_requirement(self):
        """Tentukan tingkat persetujuan yang dibutuhkan, dan hanguskan yang basi.

        Dijalankan tiap simpan supaya angkanya selalu mengikuti harga terakhir --
        termasuk saat saklarnya baru dinyalakan atau ambangnya diubah.
        """
        enabled, manager_at, escalate_at = margin_approval_settings()
        margin = self.realized_margin() if enabled else None

        if margin is None:
            self.approval_required = None
        elif margin < escalate_at:
            self.approval_required = APPROVAL_TIERS[1]
        elif margin < manager_at:
            self.approval_required = APPROVAL_TIERS[0]
        else:
            self.approval_required = None

        # Pengajuan ulang menghapus tanda tangan: setuju atas angka lama bukan setuju
        # atas angka baru. Dicek lewat cap harga, bukan `modified` -- menyunting remark
        # tidak boleh menghanguskan persetujuan yang sah.
        if self.approved_by and self.approval_signature != self.pricing_signature():
            self.approved_by = None
            self.approved_on = None
            self.approval_signature = None

    def validate_margin_approved(self):
        """Penawaran bermargin tipis tidak boleh beredar sebelum disetujui.

        Di before_print, sama seperti validate_price_floor -- menyimpan dokumen
        setengah jadi itu wajar, yang tidak boleh adalah dokumen resminya keluar.
        """
        if not self.approval_required:
            return
        if self.approved_by and self.approval_signature == self.pricing_signature():
            return
        margin = self.realized_margin()
        frappe.throw(
            _("Margin penawaran ini {0} dan butuh persetujuan {1} sebelum bisa dicetak.").format(
                f"{flt(margin):.1f}%" if margin is not None else "-",
                _(self.approval_required),
            )
        )

    def calculate_costing(self):
        """Costing engine: Base Price tiap baris produk dihitung dari biayanya.

            Base Price = (Fixed Cost/Day x Duration) + Variable Cost + Margin
            Margin     = (Fixed Cost + Variable Cost) x Margin %

        Hanya Fixed Cost yang dikali Duration -- variable cost yang diisi
        Procurement sudah berupa total sekali jalan, bukan per hari. Margin tetap
        dihitung dari akumulasi keduanya.

        Fixed cost datang dari master CRM Product (jarang berubah), variable cost
        dari cost_items yang diisi Procurement per baris produk. Baris tanpa data
        biaya sama sekali TIDAK disentuh -- ribuan quotation lama harganya diketik
        manual, jangan sampai dinolkan oleh engine ini.
        """
        # cost_key: kunci stabil per baris produk. Dibuat di server supaya tetap ada
        # walau baris dibuat lewat Desk/API, dan tidak berubah saat baris digeser.
        for p in self.products:
            if not p.cost_key:
                p.cost_key = frappe.generate_hash(length=10)

        self.seed_cost_defaults()

        # Biaya milik baris produk yang sudah dihapus ikut dibuang.
        keys = {p.cost_key for p in self.products}
        self.set("cost_items", [c for c in self.cost_items if c.cost_key in keys])
        compute_amount(self.cost_items)

        variable = {}
        for c in self.cost_items:
            variable[c.cost_key] = variable.get(c.cost_key, 0) + flt(c.amount)

        for p in self.products:
            per_day = flt(
                frappe.get_cached_value("CRM Product", p.product_code, "fixed_cost_per_day")
                if p.product_code
                else 0
            )
            dur = cint(p.duration) or 1
            p.fixed_cost = per_day * dur
            p.variable_cost = flt(variable.get(p.cost_key, 0))

            if not per_day and not p.variable_cost:
                # Belum ada costing untuk baris ini -> biarkan Base Price apa adanya.
                p.margin_amount = 0
                continue
            p.margin_amount = (p.fixed_cost + p.variable_cost) * flt(p.margin_percent) / 100
            p.procurement_price = p.fixed_cost + p.variable_cost + p.margin_amount

    def seed_cost_defaults(self):
        """Salin rincian komponen Variable Cost produk ke costing baris produk ini.

        cost_seeded menyimpan produk yang komponennya sudah dimuat. Jadi:
        - jalan sekali saja, baris yang biayanya sengaja dikosongkan Procurement
          tidak terisi ulang tiap save;
        - ganti produk = biaya produk lama dibuang, komponen produk baru dimuat.
        """
        for p in self.products:
            if not p.product_code or p.cost_seeded == p.product_code:
                continue

            if p.cost_seeded:
                # Produknya diganti: biaya produk lama tidak berlaku lagi.
                self.set("cost_items", [c for c in self.cost_items if c.cost_key != p.cost_key])
            p.cost_seeded = p.product_code

            for comp in resolve_for_product(p.product_code, VARIABLE):
                for row in comp.items:
                    self.append(
                        "cost_items",
                        copy_row(row, cost_key=p.cost_key, source_component=comp.name),
                    )

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
        #
        # Tapi hanya saat state-nya BARU diubah ke Lose. Kalau tidak, quotation
        # yang sudah lama berstatus Lose ikut terkunci selamanya: tiap save --
        # termasuk yang tidak ada hubungannya dengan status, misal membetulkan
        # rute atau harga -- ditolak sampai ada yang mengisi alasan di dokumen
        # lain. Menuntut alasan itu wajar saat orang menyatakan kalah, bukan
        # setahun kemudian saat orang sekadar merapikan datanya.
        before = self.get_doc_before_save()
        state_changed = not before or before.state != self.state

        if target == "Lost" and not inquiry.lost_reason:
            if not state_changed:
                return
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


def _assert_convertible(quo):
	"""Syarat yang sama untuk pratinjau maupun pembuatan estimasi."""
	if not frappe.has_permission("CRM Quotation", "write", quo.name):
		frappe.throw(_("Not allowed to convert this Quotation"), frappe.PermissionError)
	if quo.state == "Converted":
		frappe.throw(_("Quotation {0} is already converted").format(quo.name))
	if quo.is_void:
		frappe.throw(_("Voided quotation cannot be converted"))
	# Estimasi hanya dibuat dari quotation yang menang. Tombolnya memang cuma
	# muncul saat status Win, tapi tombol yang disembunyikan bukan aturan --
	# pemanggilan langsung ke endpoint ini harus ditolak juga.
	if quo.state != "Win":
		frappe.throw(
			_("Quotation {0} berstatus {1}. Ubah statusnya ke Win dulu sebelum convert.").format(
				quo.name, _(quo.state)
			)
		)
	if frappe.db.exists("CRM Estimation", {"quo_no": quo.name}):
		frappe.throw(_("Quotation {0} already has an estimation").format(quo.name))


def _customer_of(quo):
	"""Customer (master ERPNext) untuk estimasi -- dicocokkan lewat nama.

	Quotation menyimpan CRM Organization, estimasi menunjuk Customer: dua master
	yang berbeda. Menyalin nama organisasi mentah-mentah ke field Link Customer cuma
	menghasilkan "Could not find Customer" saat estimasinya disimpan, jadi kalau tidak
	ada padanannya field itu dibiarkan kosong -- orangnya yang memilih di form.
	"""
	nama = quo.account_name or quo.account
	if not nama:
		return None
	if frappe.db.exists("Customer", nama):
		return nama
	return frappe.db.get_value("Customer", {"customer_name": nama}, "name")


def _build_estimation(quo):
	"""Estimasi hasil terjemahan satu quotation -- BELUM disimpan.

	Dipakai dua jalur: pratinjau di layar (build_estimation) dan pembuatan langsung
	lewat API (convert_to_estimation). Satu tempat, supaya isi keduanya tidak pernah
	berbeda.
	"""
	est = frappe.new_doc("CRM Estimation")
	est.customer_id = _customer_of(quo)
	est.quo_no = quo.name
	est.quo_date = quo.date
	est.effective_date = frappe.utils.today()
	# Purpose sengaja dibiarkan kosong: pilihannya (Customer/Assistant) adalah
	# keputusan orang, dan "Quotation" bukan lagi salah satu opsinya.
	est.remarks = quo.remark

	# Rute ikut pindah: estimasi dihitung untuk rute yang sama, dan mengetik ulang
	# Loading/Unloading/KM di sini cuma membuka peluang salah ketik yang baru.
	est.loading = quo.loading
	est.unloading = quo.unloading
	est.est_km = flt(quo.distance_km)

	# Office quotation & ujung Validity ikut pindah -- dua hal yang sebelumnya harus
	# diketik ulang. Expired Date estimasi cuma satu tanggal, jadi yang diambil ujung
	# terakhir rentangnya.
	est.branch_office = quo.branch_office
	est.expired_date = quo.validity_date_to or quo.validity_date

	# Produk quotation -> baris Revenue (sisa kolom estimasi dibiarkan kosong).
	# products.product_code menunjuk CRM Product, dan itulah yang dibawa ke
	# revenue_items.product_id. type_id (Item) hanya ikut kalau kebetulan ada Item
	# berkode sama -- katalog CRM Product berdiri sendiri, mayoritas kodenya tidak
	# punya Item, dan convert tidak boleh gagal cuma karena kebetulan itu tidak ada.
	for p in quo.products:
		est.append(
			"revenue_items",
			{
				"product_id": p.product_code,
				"type_id": p.product_code if frappe.db.exists("Item", p.product_code) else None,
				"qty": flt(p.qty),
				"uom": p.uom,
				"amount": flt(p.amount),
				"remarks": p.notes,
				"currency": quo.currency or "IDR",
			},
		)

	# Variable Cost dari tab Procurement -> baris Expense. Item yang sama wajar muncul
	# di beberapa baris produk (mis. "Biaya Cleaning"), dan menyalin semuanya bikin
	# expense estimasi menggelembung -- jadi satu baris per Item, rate TERENDAH yang
	# dipakai. `rate` di baris estimasi adalah kurs, bukan tarif, jadi tarifnya masuk
	# lewat amount = qty x rate.
	murah = {}
	for c in quo.cost_items:
		if not c.item_name:
			continue
		ada = murah.get(c.item_name)
		if ada is None or flt(c.rate) < flt(ada.rate):
			murah[c.item_name] = c

	for c in murah.values():
		est.append(
			"expense_items",
			{
				"type_id": c.item_name,
				"qty": flt(c.qty),
				"uom": c.uom,
				"amount": flt(c.qty) * flt(c.rate),
				"remarks": c.remarks,
				"currency": quo.currency or "IDR",
				# Angkanya memang qty x tarif; tanpa ini Status kosong dan estimasinya
				# tidak bisa disimpan lagi oleh orang yang membukanya.
				"status": "By Qty",
			},
		)
	return est


@frappe.whitelist()
def approve_pricing(quotation: str):
	"""Setujui margin penawaran ini.

	Yang boleh: pemegang role tingkat yang diminta ATAU tingkat yang lebih ketat --
	Sales Master Manager bisa menyetujui yang cuma butuh Sales Manager, tidak sebaliknya.
	System Manager ikut lolos, pola yang sama dengan gerbang Procurement Costing.

	Capnya diambil dari keadaan harga TERSIMPAN, bukan dari kiriman browser: kalau
	tidak, layar yang sudah usang bisa menandatangani angka yang bukan angka dokumen.
	"""
	# READ, bukan write: yang menyetujui margin tidak perlu hak menyunting dokumen.
	# Wewenangnya datang dari role di bawah, dan role eskalasi memang sengaja hanya
	# diberi read supaya persetujuan tidak sekalian membuka pintu mengubah harga.
	if not frappe.has_permission("CRM Quotation", "read", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("CRM Quotation", quotation)
	if not doc.approval_required:
		frappe.throw(_("Quotation {0} tidak butuh persetujuan margin.").format(quotation))

	roles = set(frappe.get_roles())
	needed = APPROVAL_TIERS[APPROVAL_TIERS.index(doc.approval_required) :]
	if "System Manager" not in roles and not roles.intersection(needed):
		frappe.throw(
			_("Butuh role {0} untuk menyetujui margin ini.").format(_(doc.approval_required)),
			frappe.PermissionError,
		)

	stamp = frappe.utils.now_datetime()
	frappe.db.set_value(
		"CRM Quotation",
		quotation,
		{
			"approved_by": frappe.session.user,
			"approved_on": stamp,
			"approval_signature": doc.pricing_signature(),
		},
		update_modified=False,
	)
	return {"approved_by": frappe.session.user, "approved_on": stamp}


@frappe.whitelist()
def revoke_pricing_approval(quotation: str):
	"""Cabut persetujuan. Gerbangnya sama dengan memberi -- yang bisa menyetujui
	adalah yang bisa menarik kembali."""
	if not frappe.has_permission("CRM Quotation", "read", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	roles = set(frappe.get_roles())
	if "System Manager" not in roles and not roles.intersection(APPROVAL_TIERS):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	frappe.db.set_value(
		"CRM Quotation",
		quotation,
		{"approved_by": None, "approved_on": None, "approval_signature": None},
		update_modified=False,
	)
	return True


@frappe.whitelist()
def build_estimation(quotation: str):
	"""Isi estimasi hasil convert, untuk ditampilkan di form New Estimation.

	TIDAK menyimpan apa pun. Dokumennya baru lahir saat user menekan Save di form
	itu, dan di situlah quotation-nya dikunci (lihat CRM Estimation.after_insert).
	Syarat convert tetap diperiksa di sini supaya penolakan muncul sebelum orang
	terlanjur mengisi form.
	"""
	quo = frappe.get_doc("CRM Quotation", quotation)
	_assert_convertible(quo)
	return _build_estimation(quo).as_dict(no_default_fields=True)


@frappe.whitelist()
def convert_to_estimation(quotation: str):
	"""Konversi Quotation -> Estimation dalam satu langkah (API/tes).

	Alur di layar memakai build_estimation: user memeriksa dulu, lalu menyimpan
	sendiri. Yang mengunci quotation tetap satu tempat: after_insert milik
	CRM Estimation, jadi kedua jalur berakhir sama.
	"""
	quo = frappe.get_doc("CRM Quotation", quotation)

	# Row-lock untuk cegah konversi ganda yang berbarengan (double click / retry).
	frappe.db.get_value("CRM Quotation", quotation, "state", for_update=True)
	_assert_convertible(quo)

	est = _build_estimation(quo)
	# Purpose wajib tapi memang belum diisi di jalur API ini; sama seperti
	# sebelumnya, kelengkapannya ditagih saat dokumen itu disimpan berikutnya.
	est.flags.ignore_mandatory = True
	est.insert(ignore_permissions=True)
	return est.name



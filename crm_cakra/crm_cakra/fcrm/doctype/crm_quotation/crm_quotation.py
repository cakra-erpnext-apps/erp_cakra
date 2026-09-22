import hashlib

import frappe
from frappe.model.document import Document
from frappe.desk.form.assign_to import add as assign_to_add
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime

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
# State yang tidak ada di sini (Inquired, Negotiation, Follow Up, Converted) berarti
# quotation masih berjalan: inquiry didorong ke IN_PROGRESS.
INQUIRY_STATUS_BY_STATE = {"Win": "Won", "Lose": "Lost"}
INQUIRY_STATUS_IN_PROGRESS = "Quotation"
INQUIRY_FINAL_STATUSES = ("Won", "Lost")


# Urusannya sudah selesai: isinya dibekukan (lihat validate_final_state).
FINAL_STATES = ("Win", "Lose", "Converted")

# Status yang dinaikkan ke Negotiation begitu quotation dicetak. Win/Lose/Converted
# tidak ikut -- keputusannya sudah jatuh, mencetak ulang bukan negosiasi baru.
PRINT_PROMOTES_FROM = ("Inquired", "Follow Up")


def promote_idle_to_follow_up():
    """Negotiation yang diam N hari -> Follow Up. Dipanggil scheduler `daily`.

    Ambang harinya sama dengan pengingat harian (FCRM Settings.quotation_idle_days,
    default 3), supaya status di layar dan notifikasi tidak berbeda pendapat.

    `update_modified=False`: `modified` itulah jam diam yang dibaca aturan ini dan
    api/reminders.py. Menaikkannya di sini berarti status Follow Up menghapus sebab
    dirinya sendiri dan menunda pengingatnya 3 hari lagi.
    """
    idle_days = cint(frappe.db.get_single_value("FCRM Settings", "quotation_idle_days")) or 3
    names = frappe.get_all(
        "CRM Quotation",
        filters={
            "state": "Negotiation",
            "is_void": 0,
            "modified": ["<", add_days(now_datetime(), -idle_days)],
        },
        pluck="name",
    )
    for name in names:
        frappe.db.set_value("CRM Quotation", name, "state", "Follow Up", update_modified=False)
    if names:
        frappe.db.commit()
    return len(names)


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
        negative_margin_reason: DF.SmallText | None
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
        state: DF.Literal["Inquired", "Negotiation", "Follow Up", "Win", "Lose", "Converted"]
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
        self.validate_final_state()

        # Satu inquiry BOLEH dipakai banyak quotation (revisi harga, opsi rute, dsb.)
        # -- dashboard/funnel sudah menghitung per inquiry unik, jadi tidak dobel.

    def validate_final_state(self):
        """Quotation yang urusannya selesai tidak bisa disunting lagi.

        Win/Lose = keputusan customer sudah jatuh, Converted = sudah jadi estimasi.
        Isinya dibekukan supaya dokumen yang jadi dasar pekerjaan berikutnya tidak
        berubah di belakang layar. Tab Data ikut dikunci di layar, tapi yang
        mengikat tetap di sini: form yang sudah terbuka sebelum statusnya berubah
        masih bisa mengirim perubahan.

        Win/Lose punya jalan keluar -- simpan yang MENGUBAH status tetap diterima,
        jadi salah tekan bisa dibatalkan. Converted tidak: yang melepasnya adalah
        menghapus estimasinya.

        ponytail: yang diperiksa cuma "statusnya ikut berubah atau tidak", bukan
        diff per field. Satu simpan yang mengubah status sekaligus menyunting field
        lain masih lolos; kalau itu jadi masalah nyata, bandingkan
        get_doc_before_save() seperti validate_costing_locked dulu.
        """
        if self.is_new():
            return
        db_state = frappe.db.get_value("CRM Quotation", self.name, "state")
        if db_state not in FINAL_STATES:
            return
        if db_state == "Converted":
            frappe.throw(
                _("Quotation {0} sudah dikonversi ke estimasi dan tidak bisa diubah.").format(
                    self.name
                )
            )
        if self.state == db_state:
            frappe.throw(
                _(
                    "Quotation {0} berstatus {1} dan isinya sudah dikunci. Ubah statusnya dulu kalau memang masih perlu disunting."
                ).format(self.name, _(db_state))
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

    def before_print(self, settings=None):
        """Yang menaikkan status ke Negotiation saat quotation dicetak.

        Dipasang di before_print, bukan di tombol: /printview adalah URL biasa yang
        bisa dibuka langsung, jadi cetak lewat URL pun tetap menggerakkan status.

        Satu-satunya syarat cetak: margin minus harus ada alasannya. Lantai harga
        (validate_price_floor) tidak dipanggil karena Base Price per baris produk
        sudah tidak diisi sejak costing pindah ke tabel Expense Fixed/Variable Cost
        -- angkanya basi dan memblokir dokumen yang sebenarnya sah; metodenya
        sengaja dibiarkan ada, tinggal dipanggil lagi kalau Base Price dihidupkan
        kembali.
        """
        self.validate_negative_margin()

        if self.state in PRINT_PROMOTES_FROM:
            # Sengaja menaikkan `modified`: hitungan 3 hari menuju Follow Up memang
            # mulai berjalan sejak penawaran dicetak.
            frappe.db.set_value("CRM Quotation", self.name, "state", "Negotiation")
            self.state = "Negotiation"

    def validate_negative_margin(self):
        """Margin minus boleh dicetak, asal ada alasannya.

        Margin = Net Total - Estimation Costing (lihat calculate_margin). Diperiksa
        saat cetak, bukan saat simpan: menawar harga sampai sementara minus itu
        pekerjaan setengah jadi yang wajar; yang tidak boleh beredar tanpa
        keterangan adalah dokumen resminya.
        """
        if flt(self.margin) >= 0:
            return
        if (self.negative_margin_reason or "").strip():
            return
        frappe.throw(
            _(
                "Margin quotation ini {0}. Tulis dulu alasannya sebelum dicetak."
            ).format(frappe.utils.fmt_money(flt(self.margin), currency=self.currency)),
            title=_("Margin minus"),
        )

    def calculate_margin(self):
        """Estimation Costing disalin dari inquiry, lalu margin = Net Total - biaya itu.

        Disalin sekali (saat inquiry dipilih / dokumen lahir), bukan dibaca live:
        quotation adalah penawaran yang beredar, jadi angka pembandingnya harus
        beku pada saat itu. Inquiry yang costing-nya berubah kemudian tidak
        menggeser margin penawaran yang sudah terkirim.
        """
        if self.inquiry and not flt(self.estimation_costing):
            # "Estimation Cost" di CRM Inquiry: fieldnya warisan (annual_revenue),
            # labelnya saja yang diganti.
            self.estimation_costing = flt(
                frappe.db.get_value("CRM Inquiry", self.inquiry, "annual_revenue")
            )

        self.margin = flt(self.net_total) - flt(self.estimation_costing)

        # Margin sudah sehat lagi -> alasannya tidak punya arti dan malah menutupi
        # margin minus berikutnya kalau dibiarkan menempel.
        if flt(self.margin) >= 0:
            self.negative_margin_reason = None

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

        self.calculate_cost_summary()
        self.calculate_margin()

    def validate_price_floor(self):
        """Price tidak boleh di bawah Base Price hasil costing -- diperiksa saat CETAK.

        Bukan saat simpan: menyimpan quotation adalah pekerjaan setengah jadi yang
        wajar (harga sedang ditawar, costing baru masuk sebagian), dan menolak
        simpan membuat orang kehilangan pekerjaannya. Yang tidak boleh beredar
        adalah dokumen resminya, jadi lantainya berlaku di before_print.

        Baris tanpa costing (base 0) dilewati -- harganya memang diketik manual,
        dan aturan ini tidak punya dasar untuk menilainya.
        """
        # Semua baris dikumpulkan dulu, baru dilempar sekali: kalau berhenti di baris
        # pertama, orang memperbaiki satu harga lalu ditolak lagi oleh baris berikutnya.
        bad = []
        for p in self.products:
            base = flt(p.procurement_price)
            if base <= 0:
                continue
            if flt(p.price) < base:
                bad.append(
                    _("Baris {0} ({1}): Price {2} di bawah Base Price {3}.").format(
                        p.idx,
                        p.product_code or "-",
                        frappe.utils.fmt_money(flt(p.price), currency=p.currency or self.currency),
                        frappe.utils.fmt_money(base, currency=p.currency or self.currency),
                    )
                )
        if bad:
            frappe.throw("<br>".join(bad), title=_("Harga di bawah Base Price"))

    def pull_cost_from_procurement(self):
        """Ambil Fixed/Variable cost dari dokumen CRM Procurement inquiry ini.

        Costing dikerjakan di CRM Procurement (satu dokumen per inquiry), bukan
        lagi di quotation. Quotation tetap butuh angkanya sendiri: kotak Summary
        membacanya, dan Convert to Estimation membaca dua tabel ini jadi baris
        Expense.

        Disalin, bukan dibaca live: quotation adalah penawaran yang beredar, jadi
        costingnya harus beku pada angka saat itu. Penyalinan berhenti begitu
        tabelnya terisi -- biaya yang sudah masuk quotation tidak ikut berubah
        waktu Procurement menyunting dokumennya lagi. Mau menarik angka terbaru:
        kosongkan dua tabel ini lalu simpan.
        """
        if not self.inquiry or self.fixed_cost_items or self.variable_cost_items:
            return

        source = frappe.db.get_value("CRM Procurement", {"inquiry": self.inquiry})
        if not source:
            return

        doc = frappe.get_doc("CRM Procurement", source)
        for fieldname in ("fixed_cost_items", "variable_cost_items"):
            for row in doc.get(fieldname):
                self.append(fieldname, copy_row(row, source_component=row.source_component))

    def calculate_cost_summary(self):
        """Rekap costing: Fixed, Variable, dan marginnya.

        Tabel datar per quotation (bukan per baris produk seperti cost_items),
        jadi totalnya cukup jumlah amount tiap tabel. Marketing Cost tidak
        disimpan terpisah -- angkanya net_total, yaitu harga jual yang diisi
        Marketing di tabel Products.
        """
        self.pull_cost_from_procurement()
        self.total_fixed_cost = compute_amount(self.fixed_cost_items)
        self.total_variable_cost = compute_amount(self.variable_cost_items)
        self.summary_margin = flt(self.net_total) - (
            flt(self.total_fixed_cost) + flt(self.total_variable_cost)
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
        (Won/Lost) tidak diturunkan lagi kembali ke Quotation.
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
	# Quotation asal langsung terdaftar di tab Connection: estimasi ini memang
	# sudah terpakai di sana, dan barisnya jadi titik awal daftar quotation lain.
	est.append("quotation_links", {"quotation": quo.name})
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

	# Fixed Cost + Variable Cost dari tab Procurement -> baris Expense, Fixed dulu baru
	# Variable. Dua tabel itu datar: satu baris = satu pos biaya yang diketik Procurement
	# sekali untuk seluruh quotation, jadi Item yang muncul dua kali di sana memang dua
	# pos biaya yang berbeda. Menggabungkannya akan menghapus uang dari estimasi tanpa
	# ada yang sadar, maka semua baris dibawa apa adanya -- tidak ada dedupe di sini.
	for c in list(quo.fixed_cost_items) + list(quo.variable_cost_items):
		# type_id itu Link ke Item: baris tanpa Item sama sekali tidak bisa disimpan.
		if not c.item_name:
			continue
		est.append(
			"expense_items",
			{
				"type_id": c.item_name,
				"qty": flt(c.qty),
				"uom": c.uom,
				# amount tersimpan yang dipakai lebih dulu supaya total expense estimasi
				# cocok dengan kotak Summary quotation -- keduanya sama-sama hasil
				# compute_amount(). qty x rate cuma cadangan untuk baris lama yang
				# kolom amount-nya belum pernah terisi.
				"amount": flt(c.amount) or flt(c.qty) * flt(c.rate),
				"remarks": c.remarks,
				"currency": quo.currency or "IDR",
				# `rate` di baris estimasi adalah kurs, bukan tarif, jadi tarifnya masuk
				# lewat amount. Tanpa status ini kolomnya kosong dan estimasinya tidak
				# bisa disimpan lagi oleh orang yang membukanya.
				"status": "By Qty",
			},
		)
	return est


@frappe.whitelist()
def submit_negative_margin_reason(quotation: str, reason: str):
	"""Simpan alasan margin minus supaya quotationnya bisa dicetak.

	Ditulis lewat db.set_value, bukan doc.save(): dokumen yang statusnya sudah final
	dibekukan validate_final_state, dan menjelaskan margin bukan menyunting isi
	penawaran.
	"""
	if not frappe.has_permission("CRM Quotation", "write", quotation):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Alasannya wajib diisi."))
	frappe.db.set_value("CRM Quotation", quotation, "negative_margin_reason", reason)
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



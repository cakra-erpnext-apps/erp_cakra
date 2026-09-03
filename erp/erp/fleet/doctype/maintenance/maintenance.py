"""Maintenance kendaraan (kartu servis) — mengakui PEMAKAIAN sparepart dari gudang.

Tiga jalur sparepart di sistem ini, dan Maintenance hanya memegang yang ketiga:

  1. Baris ber-Vehicle di PR atau di PI ber-update_stock -> langsung beban (Material
     Issue otomatis, lihat erpnext_custom.sparepart). Barangnya TIDAK pernah jadi stok.
  2. Baris tanpa Vehicle         -> masuk stok gudang.
  3. Maintenance                  -> mengeluarkan stok gudang itu jadi beban.

Karena barang jalur 1 tidak pernah bersaldo, tidak ada yang bisa dikeluarkan dua
kali — pemisahannya terjadi dengan sendirinya, bukan lewat penjagaan tambahan.

Jalur 1 tetap MELAHIRKAN Maintenance otomatis (`purchase_receipt`/`purchase_invoice`
terisi) supaya
riwayat pemakaian sebuah kendaraan lengkap di satu tempat. Maintenance turunan itu
CERMIN, bukan pemilik jurnal: Stock Entry-nya milik PR, jadi dokumen ini tidak
membuat maupun membatalkan Stock Entry sendiri, dan status­nya hanya bisa diubah
dari PR-nya.

Status ikut mesin state CMI (erpnext_custom.workflow, jalur checkbox seperti
Expense Note / Pending Cash): Draft -> Validate/Invalidate -> Void/Unvoid.
PENGAKUAN USAGE TERJADI SAAT VALIDATE, bukan saat Save — Save masih dokumen
kerja yang boleh diutak-atik. Invalidate/Void membatalkan Stock Entry-nya.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from erpnext_custom.sparepart import expense_account

# Field yang masih boleh berubah saat dokumen sudah Validated/Void: jejak status itu
# sendiri + angka yang memang ditulis ulang server sesudah Stock Entry terbit.
STATE_FIELDS = {
    "validated",
    "validated_by",
    "validated_date",
    "void",
    "void_by",
    "void_datetime",
    "void_reason",
    "stock_entry",
    "total_amount",
}

# Catatan lapangan yang boleh dilengkapi SESUDAH kartu divalidasi. Semuanya tidak
# menyentuh stok maupun jurnal, jadi tidak ada yang bisa jadi tidak sinkron dengan Stock
# Entry-nya — dan yang mengisinya orang bengkel/fleet, bukan yang menerbitkan dokumennya.
# Kartu turunan PI TIDAK punya jalan lain: field ini tidak ada padanannya di faktur.
FIELD_NOTES = {
    "odometer",
    "next_service_date",
    "next_service_km",
    "finish_date",
    "description",
}


def _rows(doc):
    return [(r.item, r.description, flt(r.qty), r.warehouse) for r in doc.items]


class Maintenance(Document):
    def validate(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default(
                "company"
            )
        if self.finish_date and self.finish_date < self.date:
            frappe.throw(_("Tgl Keluar tidak boleh sebelum Tgl Masuk."))

        # Kartu turunan PI tidak punya gudang asal: sparepart-nya langsung jadi biaya di
        # faktur, tidak pernah mengendap di stok (lihat erpnext_custom.sparepart).
        needs_warehouse = not self.source_document()
        for row in self.items:
            if row.is_stock_item and not row.warehouse and needs_warehouse:
                frappe.throw(
                    _("Baris {0}: {1} adalah item stock, gudang asalnya wajib diisi.").format(
                        row.idx, row.item
                    )
                )
            if not row.is_stock_item:
                row.warehouse = None
            if flt(row.qty) <= 0:
                frappe.throw(_("Baris {0}: Qty harus lebih dari 0.").format(row.idx))
            row.amount = flt(row.qty) * flt(row.rate)

        self.total_amount = sum(flt(r.amount) for r in self.items)
        self._sync_state()
        self._guard_locked()
        self._guard_pr_owned()

    def _guard_pr_owned(self):
        """Maintenance turunan PR tidak boleh di-Validate/Void sendiri.

        Stock Entry-nya milik PR. Membiarkan dokumen ini di-invalidate akan membuat
        statusnya bilang 'belum dipakai' padahal barangnya sudah jadi beban di PR —
        dan sebaliknya, Void di sini tidak akan mengembalikan stok apa pun.
        """
        before = self.get_doc_before_save()
        if not (self.source_document() and before) or self.flags.get("pr_sync"):
            return
        if before.validated != self.validated or before.void != self.void:
            frappe.throw(
                _("Status Maintenance {0} mengikuti {1}. Ubah lewat dokumen itu.").format(
                    self.name, self.source_document()
                )
            )

    def source_document(self):
        """Nomor dokumen pembelian yang melahirkan kartu ini (PR atau PI), kalau ada.

        Kartu turunan itu CERMIN: jurnalnya milik dokumen sumber, jadi kartu ini tidak
        pernah membuat/membatalkan Stock Entry sendiri dan statusnya ikut sana."""
        return self.purchase_receipt or self.purchase_invoice

    def on_update(self):
        self._sync_issue()

    def on_trash(self):
        if self.stock_entry and not self.source_document():
            frappe.throw(
                _("Maintenance ini punya Stock Entry {0}. Jalankan Invalidate/Void dulu.").format(
                    self.stock_entry
                )
            )

    # ---- status ------------------------------------------------------------
    def _sync_state(self):
        now = now_datetime()
        if self.validated:
            if not self.validated_by:
                self.validated_by = frappe.session.user
                self.validated_date = now
        else:
            self.validated_by = None
            self.validated_date = None

        if self.void:
            if not self.void_datetime:
                self.void_by = frappe.session.user
                self.void_datetime = now
        else:
            self.void_by = None
            self.void_datetime = None
            self.void_reason = None

    def _guard_locked(self):
        """Isi dokumen tidak boleh diubah dari sini. Dua sebab, dua-duanya server-side
        (bukan sekadar read-only di form, supaya API dan bulk edit ikut tertutup):

        1. Kartu sudah Validated/Void -> stoknya sudah keluar dan nilainya sudah jadi
           beban, jadi mengubah qty/item bikin dokumen tidak cocok dengan Stock Entry-nya.
        2. Kartu turunan PR/PI -> isinya CERMIN dokumen pembelian, ditulis ulang tiap kali
           dokumen itu divalidasi. Perubahan di sini akan hilang tanpa jejak pada revisi
           berikutnya, jadi ditolak sejak awal: perbaikannya di PI/PR-nya.

        FIELD_NOTES (odometer, jadwal servis, dst) tetap boleh diisi — itu catatan lapangan
        yang tidak punya padanan di dokumen pembelian.
        """
        before = self.get_doc_before_save()
        if not before or self.flags.get("pr_sync"):
            return
        if not (before.validated or before.void or self.source_document()):
            return
        changed = [
            df.label or df.fieldname
            for df in self.meta.fields
            if df.fieldtype not in no_value_fields
            and df.fieldname not in STATE_FIELDS
            and df.fieldname not in FIELD_NOTES
            and self.get(df.fieldname) != before.get(df.fieldname)
        ]
        # Fieldtype Table ada di no_value_fields, jadi TIDAK ikut terbandingkan di atas —
        # tanpa baris ini, qty/item di grid masih bisa diubah setelah stoknya keluar.
        # rate & amount sengaja tidak dibandingkan: keduanya ditulis server dari valuation.
        if _rows(self) != _rows(before):
            changed.append(_("Pekerjaan & Sparepart"))
        if changed:
            state = "Void" if before.void else "Validated"
            frappe.throw(
                _("Maintenance {0} sudah {1}, isinya tidak bisa diubah. Field berubah: {2}.").format(
                    self.name, state, ", ".join(changed)
                )
            )

    # ---- pemakaian stok ----------------------------------------------------
    def _sync_issue(self):
        if self.source_document():
            return  # cermin PR/PI — Stock Entry-nya dibuat & dibatalkan di sana
        should_issue = bool(self.validated) and not bool(self.void)
        if should_issue and not self.stock_entry:
            se = self._make_material_issue()
            if se:
                self.db_set("stock_entry", se, update_modified=False)
                self._pull_valuation(se)
        elif (not should_issue) and self.stock_entry:
            se_name = self.stock_entry
            self.db_set("stock_entry", None, update_modified=False)
            self._cancel_material_issue(se_name)

    def _stock_rows(self):
        return [r for r in self.items if r.item and r.is_stock_item]

    def _make_material_issue(self):
        rows = self._stock_rows()
        if not rows:
            return None

        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Issue"
        se.company = self.company
        se.set_posting_time = 1
        se.posting_date = self.finish_date or self.date
        # Akhir hari, bukan 00:00 (bawaan) dan bukan jam sekarang: pemakaian sparepart
        # harus jatuh SESUDAH penerimaan barang di tanggal yang sama, dan jam penerimaan
        # itu tidak selalu lebih awal dari jam server (posting time dokumen beli bisa
        # diketik manual). Kalau tidak, stok yang jelas ada dibaca 0.
        se.posting_time = "23:59:59"
        se.remarks = _("Maintenance {0} - kendaraan {1}").format(self.name, self.vehicle)
        for row in rows:
            se.append(
                "items",
                {
                    "item_code": row.item,
                    "qty": row.qty,
                    "s_warehouse": row.warehouse,
                    "expense_account": expense_account(row.item, self.company),
                },
            )
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        return se.name

    def _pull_valuation(self, se_name):
        """Harga sparepart = nilai buku gudang, bukan ketikan user.

        Barang yang keluar gudang dinilai dengan valuation rate-nya; membiarkan user
        mengetik harga sendiri membuat Total Biaya di dokumen ini berbeda dari jurnal
        yang barusan terbentuk.
        """
        rates = {
            (d.item_code, d.s_warehouse): flt(d.basic_rate)
            for d in frappe.get_all(
                "Stock Entry Detail",
                filters={"parent": se_name},
                fields=["item_code", "s_warehouse", "basic_rate"],
            )
        }
        total = 0.0
        for row in self.items:
            if row.item and row.is_stock_item:
                rate = rates.get((row.item, row.warehouse), flt(row.rate))
                frappe.db.set_value("Maintenance Item", row.name, "rate", rate, update_modified=False)
                frappe.db.set_value(
                    "Maintenance Item", row.name, "amount", flt(row.qty) * rate, update_modified=False
                )
                row.rate, row.amount = rate, flt(row.qty) * rate
            total += flt(row.amount)
        self.db_set("total_amount", total, update_modified=False)

    def _cancel_material_issue(self, se_name):
        if not frappe.db.exists("Stock Entry", se_name):
            return
        se = frappe.get_doc("Stock Entry", se_name)
        if se.docstatus == 1:
            se.flags.ignore_permissions = True
            se.flags.owner_doc_ok = True  # jalur sah, lihat sparepart.guard_issue_cancel
            se.cancel()


# Dropdown grid: hanya yang benar-benar bisa dikeluarkan. Barang bersaldo 0 (atau nol
# di gudang yang dipilih) tidak boleh terlihat — memilihnya cuma berujung penolakan
# saat Validate.
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sparepart_query(doctype, txt, searchfield, start, page_len, filters):
    warehouse = (filters or {}).get("warehouse")
    return frappe.db.sql(
        """
        select i.name, i.item_name
        from tabItem i
        where i.item_category = 'Sparepart' and i.disabled = 0
            and (i.name like %(txt)s or i.item_name like %(txt)s)
            and exists (
                select 1 from tabBin b
                where b.item_code = i.name and b.actual_qty > 0
                    and (%(warehouse)s is null or b.warehouse = %(warehouse)s)
            )
        order by i.name
        limit %(start)s, %(page_len)s
        """,
        {
            "txt": "%%%s%%" % txt,
            "warehouse": warehouse,
            "start": start,
            "page_len": page_len,
        },
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouse_query(doctype, txt, searchfield, start, page_len, filters):
    f = filters or {}
    item = f.get("item")
    # Belum pilih item: belum ada saldo yang bisa disaring, tampilkan gudang biasa.
    join = "inner join tabBin b on b.warehouse = w.name" if item else ""
    cond = "and b.item_code = %(item)s and b.actual_qty > 0" if item else ""
    qty = ", b.actual_qty" if item else ""
    return frappe.db.sql(
        f"""
        select w.name {qty}
        from tabWarehouse w {join}
        where w.is_group = 0 and w.disabled = 0 and w.name like %(txt)s
            and (%(company)s is null or w.company = %(company)s) {cond}
        order by w.name
        limit %(start)s, %(page_len)s
        """,
        {
            "txt": "%%%s%%" % txt,
            "item": item,
            "company": f.get("company"),
            "start": start,
            "page_len": page_len,
        },
    )

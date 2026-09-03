"""Server-side customizations untuk core Purchase Order & Purchase Invoice (erpnext_custom).

Mirror pola Sales Invoice (lihat overrides/sales_invoice.py): Discount/Tax(PPN)/PPh/
Materai dari field gabungan (Data, "10%" / "50000") disuntik ke NATIVE Purchase Taxes
and Charges supaya grand_total -> GL benar.

  Discount : additional_discount (Apply on Net Total)  -- % atau nominal
  Tax (PPN Masukan) : baris pajak positif (asset / pajak masukan dikreditkan)
  PPh      : baris pajak NEGATIF (CMI memotong PPh dari vendor -> utang pajak)
  Materai  : baris pajak Actual (nominal)

PENTING — akun PEMBELIAN beda dari penjualan. Set di ERPNext Custom Setting (tab Invoice Setting, bagian
Purchase): `purchase_tax_account` (PPN Masukan, asset), `purchase_pph_account`
(PPh terutang dipotong, liability), `purchase_materai_account`. Draft aman tanpa akun;
saat akun dipakai (ada nilai Tax/PPh/Materai) `_need()` mewajibkan akun ter-set.

Purchase Order TIDAK posting GL (dokumen order) -> injeksi hanya mempengaruhi
grand_total PO. Purchase Invoice posting GL; `dont_post_to_gl` -> skip make_gl_entries.
Audit: validated_by saat submit, voided_by saat cancel.
"""

import frappe
from frappe import _
from frappe.utils import flt
from erpnext.buying.doctype.purchase_order.purchase_order import PurchaseOrder
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

from erpnext_custom.overrides import fill_cost_center

# Pakai ulang parser field gabungan milik Sales Invoice (field-name & locale identik).
from erpnext_custom.overrides.sales_invoice import _apply_smart_inputs

TAX_DESC = "CMI: Tax"
PPH_DESC = "CMI: PPh"
MATERAI_DESC = "CMI: Materai"
_CMI_DESCS = (TAX_DESC, PPH_DESC, MATERAI_DESC)


def _settings():
    return frappe.get_cached_doc("ERPNext Custom Setting")


def _need(account, label):
    if not account:
        frappe.throw(_("Set akun '{0}' (bagian Purchase) di ERPNext Custom Setting.").format(label))
    return account


def _inject_amounts(doc):
    """Suntik Discount/PPN/PPh/Materai ke native Purchase Taxes and Charges."""
    _apply_smart_inputs(doc)  # field gabungan "10%"/"50000" -> percent/amount tersembunyi

    # Discount -> native (Apply on Net Total). % menang kalau diisi, else nominal.
    doc.apply_discount_on = "Net Total"
    if flt(doc.get("custom_discount_percent")):
        doc.additional_discount_percentage = flt(doc.custom_discount_percent)
        doc.discount_amount = 0
    else:
        doc.additional_discount_percentage = 0
        doc.discount_amount = flt(doc.get("custom_discount_amount"))

    # Bangun ulang baris pajak CMI (pertahankan baris lain yang dibuat manual).
    s = _settings()
    kept = [t for t in (doc.get("taxes") or []) if (t.get("description") or "") not in _CMI_DESCS]
    doc.set("taxes", kept)

    def add_pct(account, desc, pct, sign=1):
        doc.append("taxes", {
            "category": "Total",
            "add_deduct_tax": "Add" if sign > 0 else "Deduct",
            "charge_type": "On Net Total",
            "account_head": account,
            "description": desc,
            "rate": abs(flt(pct)),
        })

    def add_amt(account, desc, amt, sign=1):
        doc.append("taxes", {
            "category": "Total",
            "add_deduct_tax": "Add" if sign > 0 else "Deduct",
            "charge_type": "Actual",
            "account_head": account,
            "description": desc,
            "rate": 0,
            "tax_amount": abs(flt(amt)),
        })

    # Tax (PPN Masukan) — % menang; di-skip kalau Ignore Tax.
    if not doc.get("custom_ignore_tax"):
        if flt(doc.get("custom_tax_percent")):
            add_pct(_need(s.get("purchase_tax_account"), "Tax (PPN Masukan)"), TAX_DESC, doc.custom_tax_percent, 1)
        elif flt(doc.get("custom_tax_amount")):
            add_amt(_need(s.get("purchase_tax_account"), "Tax (PPN Masukan)"), TAX_DESC, doc.custom_tax_amount, 1)
    # PPh — potongan (negatif): mengurangi yang dibayar ke vendor.
    if flt(doc.get("custom_pph_percent")):
        add_pct(_need(s.get("purchase_pph_account"), "PPh terutang dipotong"), PPH_DESC, doc.custom_pph_percent, -1)
    elif flt(doc.get("custom_pph_amount")):
        add_amt(_need(s.get("purchase_pph_account"), "PPh terutang dipotong"), PPH_DESC, doc.custom_pph_amount, -1)
    # Materai — nominal tetap.
    if flt(doc.get("custom_materai")):
        add_amt(_need(s.get("purchase_materai_account"), "Materai"), MATERAI_DESC, doc.custom_materai, 1)


def _compute_display(doc):
    """Mirror Amount dari % (supaya field Amount menampilkan Rp) + AmountTotal/NetTotal."""
    total = flt(doc.get("total"))
    if flt(doc.get("custom_discount_percent")):
        doc.custom_discount_amount = total * flt(doc.custom_discount_percent) / 100.0
    discount = flt(doc.get("custom_discount_amount"))
    dpp = total - discount
    if doc.get("custom_ignore_tax"):
        doc.custom_tax_amount = 0
    elif flt(doc.get("custom_tax_percent")):
        doc.custom_tax_amount = dpp * flt(doc.custom_tax_percent) / 100.0
    if flt(doc.get("custom_pph_percent")):
        doc.custom_pph_amount = dpp * flt(doc.custom_pph_percent) / 100.0
    doc.custom_amount_total = total
    # grand_total sudah memperhitungkan diskon + baris pajak CMI -> net = grand_total + adjustment.
    doc.custom_net_total = flt(doc.get("grand_total")) + flt(doc.get("custom_adjustment"))


def _auto_update_stock(doc):
    """Stok naik saat PI divalidasi -> user tidak perlu mencentang Update Stock.

    Nyala hanya kalau ada item stok. Mati kalau barangnya sudah masuk lewat Purchase
    Receipt (stoknya naik di sana) dan untuk retur (pengurangan stok tetap manual).
    """
    if doc.get("is_return"):
        return
    items = doc.get("items") or []
    if any(d.get("purchase_receipt") for d in items):
        doc.update_stock = 0
        return
    # Baris ber-Vehicle = sparepart langsung pakai: sengaja tanpa gudang, tidak pernah
    # jadi stok (lihat CMIPurchaseInvoice.validate_warehouse), jadi tidak ikut menghitung.
    doc.update_stock = 1 if any(
        d.item_code and d.warehouse and frappe.get_cached_value("Item", d.item_code, "is_stock_item")
        for d in items
    ) else 0


def _refresh_purchase_order_invoices(purchase_order):
    names = frappe.get_all(
        "Purchase Invoice Item",
        filters={"purchase_order": purchase_order, "docstatus": ["<", 2]},
        distinct=True,
        pluck="parent",
        order_by="parent",
    )
    value = ", ".join(names)
    if frappe.db.get_value("Purchase Order", purchase_order, "custom_purchases") != value:
        # update_modified=False: kolom ini turunan, jangan mengotori "Last Modified" PO.
        frappe.db.set_value(
            "Purchase Order", purchase_order, "custom_purchases", value, update_modified=False
        )


def sync_purchase_order_invoices(doc, method=None):
    """Kolom "Purchases" di list PO = daftar Purchase Invoice yang menunjuk PO tersebut."""
    # ponytail: hanya PO yang MASIH tertaut di dokumen ini yang dihitung ulang. Kalau user
    # menghapus baris ber-PO dari PI draft, kolom PO lama baru ikut bersih saat migrate
    # berikutnya (_backfill_purchase_order_purchases). Simpan `before_save` kalau kasus itu
    # jadi sering.
    for name in {d.get("purchase_order") for d in (doc.get("items") or []) if d.get("purchase_order")}:
        _refresh_purchase_order_invoices(name)


# --- doc_events (PO & PI berbagi logika yang sama) ------------------------------
def before_validate(doc, method=None):
    if doc.doctype == "Purchase Order":
        # "Required By" (schedule_date) tidak lagi tampil di form tapi tetap wajib bagi
        # BuyingController.validate_schedule_date -> samakan dengan tanggal dokumen.
        doc.schedule_date = doc.schedule_date or doc.transaction_date
        # Branch OTORITATIF dari Type (fetch_from di form cuma untuk tampilan) — juga
        # DIKOSONGKAN kalau Type-nya tidak punya branch, supaya field mandatory-nya
        # menolak save alih-alih menyimpan sisa isian dari branch pembuat.
        doc.branch_office = (
            frappe.db.get_value("Purchase Order Type", doc.custom_type, "branch")
            if doc.custom_type
            else None
        )
    else:
        _auto_update_stock(doc)
    _inject_amounts(doc)


def validate(doc, method=None):
    _compute_display(doc)


class CMIPurchaseOrder(PurchaseOrder):
    """Override controller core Purchase Order (audit)."""

    def autoname(self):
        from erpnext_custom.purchase_order.naming import make_purchase_order_name

        self.name = make_purchase_order_name(self)

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)
        self.db_set("custom_validated_date", frappe.utils.now())

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)


def _direct_expense_rows(doc):
    """Baris sparepart yang langsung jadi biaya = baris ber-Vehicle.

    Dua kondisi baris item sparepart:
      Vehicle terisi   -> langsung BIAYA (gudangnya dikosongkan, tidak pernah jadi stok)
      Warehouse saja   -> masuk PERSEDIAAN seperti item stok biasa
    """
    return [d for d in doc.get("items") or [] if d.get("custom_vehicle")]


class CMIPurchaseInvoice(PurchaseInvoice):
    """Override controller core Purchase Invoice (dont_post_to_gl + audit)."""

    def set_missing_values(self, for_validate=False):
        """Kosongkan lagi gudang baris ber-Vehicle sesudah ERPNext mengisinya.

        get_item_details SELALU menambal `warehouse` yang kosong dari Default Warehouse
        Item, jadi baris sparepart langsung pakai tidak akan pernah bertahan kosong kalau
        dibersihkan lebih awal. Titik ini dipilih karena masih SEBELUM validate_warehouse
        dan set_expense_account — dua-duanya membaca ada/tidaknya gudang untuk memutuskan
        baris ini stok atau biaya.
        """
        super().set_missing_values(for_validate)
        for row in self.get("items") or []:
            if row.get("custom_vehicle"):
                row.warehouse = None
                # Pintu keluar milik ERPNext sendiri untuk "barang stok yang tidak masuk
                # gudang kita" (buying/utils.validate_stock_item_warehouse). Tanpa ini
                # BuyingController menolak baris item stok tanpa gudang, jauh sebelum
                # validate_warehouse di bawah sempat mengecualikannya.
                row.delivered_by_supplier = 1

    def validate_warehouse(self, for_validate=True):
        """Sama seperti bawaan, kecuali baris ber-Vehicle dikecualikan.

        ERPNext mewajibkan gudang untuk SETIAP baris item stok begitu update_stock menyala.
        Baris sparepart langsung pakai memang tidak punya gudang — dan tanpa gudang ERPNext
        sendiri tidak membuat Stock Ledger Entry untuknya (buying_controller.update_stock_ledger
        melewati baris tanpa gudang), jadi baris itu murni biaya.
        """
        from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import WarehouseMissingError

        if self.update_stock and for_validate:
            stock_items = self.get_stock_items()
            for d in self.get("items"):
                if d.item_code in stock_items and not d.warehouse and not d.get("custom_vehicle"):
                    frappe.throw(
                        _("Baris {0}: Gudang wajib diisi. Set Default Warehouse untuk item {1} "
                          "di company {2}, atau isi Vehicle kalau sparepart ini langsung dipakai.")
                        .format(d.idx, d.item_code, self.company),
                        exc=WarehouseMissingError,
                    )
        # Lewati validate_warehouse milik PurchaseInvoice (sudah digantikan di atas),
        # pemeriksaan gudang-vs-company milik StockController tetap jalan.
        super(PurchaseInvoice, self).validate_warehouse()

    def set_expense_account(self, for_validate=False):
        """Baris langsung-biaya dibukukan ke akun beban item, bukan Hutang Usaha Sementara.

        Bawaannya memaksa SEMUA item stok tanpa gudang ke akun 'Stock Received But Not
        Billed' (menunggu Purchase Receipt) — untuk sparepart yang langsung dipakai tidak
        ada barang yang ditunggu, jadi akunnya ditimpa balik sesudah super().
        """
        # Pesan "Expense Head Changed" milik bawaan DIBUNGKAM: kolom Expense Head tidak
        # pernah diisi user (disembunyikan dari edit-row), jadi pemberitahuan bahwa sistem
        # menggantinya cuma kebisingan -- dan untuk baris ber-Vehicle pesannya malah keliru,
        # karena akunnya dikembalikan lagi tepat di bawah ini.
        muted = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            super().set_expense_account(for_validate)
        finally:
            frappe.flags.mute_messages = muted

        from erpnext_custom.sparepart import expense_account

        for row in _direct_expense_rows(self):
            row.expense_account = expense_account(row.item_code, self.company)

    def make_gl_entries(self, *args, **kwargs):
        if self.get("dont_post_to_gl"):
            return
        return super().make_gl_entries(*args, **kwargs)

    def get_gl_dict(self, args, account_currency=None, item=None):
        """Satu baris item = satu baris jurnal, lengkap dengan nama itemnya.

        Bawaannya menggabungkan baris yang seakun (merge_similar_entries) sehingga 3 baris
        sparepart jadi satu angka gelondongan yang tidak bisa dicocokkan ke fakturnya.
        `_skip_merge` adalah pintu yang disediakan ERPNext sendiri untuk itu.
        """
        gl = fill_cost_center(self, super().get_gl_dict(args, account_currency, item), item)
        if item and item.get("item_code"):
            gl["_skip_merge"] = 1
            label = item.get("item_name") or item.item_code
            if item.get("custom_vehicle"):
                label = "{0} ({1})".format(label, item.custom_vehicle)
            gl["remarks"] = "{0}: {1}".format(item.idx, label)
        return gl

    def on_submit(self):
        super().on_submit()
        self.db_set("custom_validated_by", frappe.session.user)
        self.db_set("custom_validated_date", frappe.utils.now())

    def on_cancel(self):
        super().on_cancel()
        self.db_set("custom_voided_by", frappe.session.user)

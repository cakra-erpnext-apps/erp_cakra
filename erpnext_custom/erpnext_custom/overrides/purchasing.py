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


NO_TAX_TEMPLATE_TITLE = "CMI No Tax"


def _no_tax_template(company, tax_account):
    """Item Tax Template bertarif 0 untuk akun PPN — dibuat sekali per company.

    JANGAN diganti dengan mengisi `item.item_tax_rate` langsung: taxes_and_totals
    .update_item_tax_map() MENIMPA field itu dari item_tax_template setiap kali
    menghitung, jadi nilai yang kita tulis sendiri selalu hilang. Template inilah
    satu-satunya jalur native untuk tarif per baris.

    Template ini plumbing; user tidak pernah memilihnya sendiri (cukup centang No Tax).
    """
    name = frappe.db.get_value(
        "Item Tax Template", {"title": NO_TAX_TEMPLATE_TITLE, "company": company}, "name"
    )
    if name:
        return name
    # Item Tax Template menolak akun yang account_type-nya bukan Tax/Income/Expense/
    # Chargeable. Akun PPN Masukan biasanya Asset dengan account_type kosong -> diisi
    # "Tax" (klasifikasi, root_type tetap Asset jadi neraca tidak berubah). Pilihan
    # eksplisit user tidak ditimpa.
    if not frappe.db.get_value("Account", tax_account, "account_type"):
        frappe.db.set_value("Account", tax_account, "account_type", "Tax")
        frappe.clear_cache(doctype="Account")
    return frappe.get_doc({
        "doctype": "Item Tax Template",
        "title": NO_TAX_TEMPLATE_TITLE,
        "company": company,
        "taxes": [{"tax_type": tax_account, "tax_rate": 0}],
    }).insert(ignore_permissions=True).name


def _apply_no_tax_rows(doc):
    """Baris ber-centang "No Tax" dikeluarkan dari basis PPN.

    Centangnya diterjemahkan ke Item Tax Template bertarif 0, yang dibaca ERPNext
    sebagai tarif PER BARIS -> baris itu tidak menambah basis pajak, baris lain tetap
    kena 11%.
    """
    rows = doc.get("items") or []
    if not any(r.get("custom_no_tax") for r in rows) and not any(
        r.get("item_tax_template") for r in rows
    ):
        return  # tidak ada yang perlu diatur; jangan sentuh master apa pun

    template = None
    if any(r.get("custom_no_tax") for r in rows):
        template = _no_tax_template(
            doc.company, _need(_settings().get("purchase_tax_account"), "Tax (PPN Masukan)")
        )
    for row in rows:
        if row.get("custom_no_tax"):
            row.item_tax_template = template
        elif row.get("item_tax_template") == NO_TAX_TEMPLATE_TITLE or (
            template and row.get("item_tax_template") == template
        ):
            # Centang dilepas -> buang templatenya. Template pilihan user sendiri
            # (bukan milik kita) JANGAN disentuh.
            row.item_tax_template = None


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
    _apply_no_tax_rows(doc)
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
    # Angka pajak dibaca dari baris yang SUDAH dihitung ERPNext, bukan total x persen:
    # dengan centang "No Tax" per baris, basisnya bukan lagi seluruh dokumen.
    # _compute_display dipanggil di hook `validate`, jadi calculate_taxes_and_totals
    # milik controller sudah selesai dan tax_amount-nya final.
    def row_total(description):
        return sum(
            flt(t.tax_amount) for t in (doc.get("taxes") or [])
            if (t.get("description") or "") == description
        )

    doc.custom_tax_amount = 0 if doc.get("custom_ignore_tax") else row_total(TAX_DESC)
    doc.custom_pph_amount = row_total(PPH_DESC)
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
    # Baris aset (is_fixed_asset) juga menyalakannya: ERPNext hanya membuat record Asset
    # dari PI kalau update_stock nyala (BuyingController.process_fixed_asset). Item aset
    # non-stok, jadi tidak ada dampak ke stok.
    doc.update_stock = 1 if any(
        d.item_code and (
            frappe.get_cached_value("Item", d.item_code, "is_fixed_asset")
            # `not custom_vehicle` WAJIB diperiksa di sini: gudang baris ber-Vehicle baru
            # dikosongkan di set_missing_values, yaitu SESUDAH before_validate ini. Tanpa
            # pemeriksaan itu, baris yang dikirim dengan gudang DAN vehicle sekaligus
            # (impor/API) menyalakan update_stock untuk gudang yang sebentar lagi hilang.
            or (
                d.warehouse
                and not d.get("custom_vehicle")
                and frappe.get_cached_value("Item", d.item_code, "is_stock_item")
            )
        )
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
        # Branch: default dari Type, TAPI pilihan user menang (field-nya editable).
        # Cermin fetch_if_empty di form, untuk dokumen yang dibuat lewat API/import.
        if not doc.branch_office and doc.custom_type:
            doc.branch_office = frappe.db.get_value(
                "Purchase Order Type", doc.custom_type, "branch"
            )
    else:
        _auto_update_stock(doc)
    # Pembulatan dipusatkan di Payment Entry (_apply_rounding di overrides/payment_entry.py):
    # dokumen menyimpan angkanya apa adanya, tanpa baris Company.round_off_account. Centang
    # di Global Defaults tidak cukup -- itu hanya default untuk dokumen baru, sedangkan tiap
    # dokumen menyimpan salinan flag-nya sendiri.
    if doc.meta.has_field("disable_rounded_total"):
        doc.disable_rounded_total = 1
    _inject_amounts(doc)


def _require_item_warehouse(doc):
    """Warehouse WAJIB untuk baris item stok & aset; item jasa/beban tidak pernah diminta.

    Bawaan ERPNext cuma memeriksanya kalau `update_stock` menyala (lihat
    PurchaseInvoice.set_expense_account), sementara update_stock CMI justru DITURUNKAN
    dari ada/tidaknya gudang (_auto_update_stock) — jadi baris item stok tanpa gudang
    dulu lolos diam-diam dan nilainya jatuh ke beban, bukan persediaan.

    Dipanggil dari doc_event `validate`, yaitu SESUDAH controller `set_missing_values`
    menambal gudang dari Default Warehouse item; kalau diperiksa di before_validate,
    baris yang sebenarnya akan terisi otomatis ikut tertolak.

    Baris ber-Vehicle dikecualikan: sparepart langsung pakai memang tidak masuk gudang
    (lihat CMIPurchaseInvoice.set_missing_values).
    """
    from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import WarehouseMissingError

    for d in doc.get("items") or []:
        if not d.item_code or d.warehouse or d.get("custom_vehicle"):
            continue
        is_stock, is_asset = frappe.get_cached_value(
            "Item", d.item_code, ["is_stock_item", "is_fixed_asset"]
        )
        if not (is_stock or is_asset):
            continue
        frappe.throw(
            _("Baris {0}: Warehouse wajib diisi untuk item {1} (item stok/aset). Set "
              "Default Warehouse untuk item ini di company {2}, atau isi Vehicle kalau "
              "sparepart ini langsung dipakai.").format(d.idx, d.item_code, doc.company),
            exc=WarehouseMissingError,
        )


def validate(doc, method=None):
    if doc.doctype == "Purchase Invoice":
        _require_item_warehouse(doc)
    _compute_display(doc)


def refresh_display_after_submit(doc, method=None):
    """Segarkan SubTotal/Amount Tax/Net Total sesudah dokumen submit diubah.

    "Update Items" pada PO/PI yang sudah submit menghitung ulang total NATIVE lewat
    update_child_qty_rate, tapi TIDAK lewat hook `validate` — jadi tanpa ini field
    tampilan CMI membeku di angka sebelum perubahan (mis. PO qty 1 -> 10: total jadi
    100jt sementara Net Total tetap 10jt). Selain salah di layar dan di cetakan, selisih
    itu membuat form terdeteksi "unsaved" oleh perhitungan sisi client.
    """
    _compute_display(doc)
    for fieldname in ("custom_amount_total", "custom_tax_amount", "custom_net_total"):
        frappe.db.set_value(
            doc.doctype, doc.name, fieldname, doc.get(fieldname), update_modified=False
        )


class CMIPurchaseOrder(PurchaseOrder):
    """Override controller core Purchase Order (audit)."""

    def autoname(self):
        from erpnext_custom.purchase_order.naming import make_purchase_order_name

        self.name = make_purchase_order_name(self)

    def set_total_advance_paid(self):
        """Satu rumus yang memiliki field Advance Paid.

        Core menghitungnya HANYA dari Payment Ledger, sehingga uang muka lewat Pending Cash
        dan tab Advance Payable — yang memang tidak pernah membuat Payment Ledger Entry —
        terbuang setiap kali ada Payment Entry ber-reference PO native (core dipanggil
        belakangan, jadi core yang menang). Dibelokkan ke _recalc_po_advance yang menjumlah
        ketiga sumbernya sekaligus, sehingga siapa pun pemanggilnya hasilnya sama.
        """
        _recalc_po_advance(self.name)

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
            # LANGSUNG DIPAKAI (tipe pembelian #3: BBM/ATK/jasa) = item NON-STOK & bukan aset.
            # Barangnya tidak pernah masuk gudang, jadi gudangnya WAJIB kosong — kalau
            # dibiarkan terisi (get_item_details menambalnya dari Default Warehouse Item),
            # baris ini terbaca seperti pembelian stok.
            if row.item_code and not row.get("custom_vehicle"):
                is_stock, is_asset = frappe.get_cached_value(
                    "Item", row.item_code, ["is_stock_item", "is_fixed_asset"]
                )
                if not is_stock and not is_asset:
                    row.warehouse = None
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


# ============================================================================
# Advance Paid di Purchase Order
# ----------------------------------------------------------------------------
# ERPNext bawaan mengisi field ini dari tabel References native Payment Entry —
# jalur yang tidak kita pakai: uang muka CMI dicatat di Pending Cash (Modul =
# Purchase Order) dan di tab Advance Payable, dua-duanya tabel sendiri. Akibatnya
# Advance Paid di form PO diam di 0 dan user tidak tahu PO-nya sudah diberi uang
# muka berapa.
#
# Dihitung ULANG dari nol setiap kali, bukan ditambah/dikurangi. Dengan begitu
# void, unvoid, Undo Paid, ubah nomor PO, sampai hapus dokumen semuanya benar
# tanpa penanganan khusus — cukup panggil ulang.
#
# Core tidak akan menimpanya: set_total_advance_paid hanya dipanggil dari
# update_voucher_outstanding saat ada Payment Ledger Entry yang menunjuk PO, dan
# uang muka kita tidak pernah membuat PLE (akun uang muka bukan Receivable/Payable
# dan tidak ada baris References).
# ============================================================================


def _recalc_po_advance(po_name):
    po = frappe.db.get_value(
        "Purchase Order", po_name, ["docstatus", "conversion_rate"], as_dict=True
    )
    if not po or po.docstatus == 2:  # PO void: biarkan angkanya apa adanya
        return
    po_rate = flt(po.conversion_rate) or 1

    # Sumber 1: Pending Cash yang sudah PAID dan belum void. Yang masih draft/validated
    # belum mengeluarkan uang (jurnalnya baru terbentuk saat Paid), jadi tidak dihitung.
    # Uang yang SUDAH DIKEMBALIKAN supplier dipotong: refund = uang muka batal, beda
    # dengan pemotongan ke PI (itu tidak mengurangi — semantik Advance Paid di sini gross).
    # refunded_total() dipakai, bukan field `refunded_amount`, supaya refund yang di-void
    # tidak ikut mengurangi.
    from erp.fico.doctype.pending_cash.pending_cash import refunded_total

    base = 0.0
    for r in frappe.get_all(
        "Pending Cash",
        filters={"modul": "Purchase Order", "number": po_name, "paid": 1, "void": 0},
        fields=["name", "total", "exchange_rate"],
        ignore_permissions=True,
    ):
        net = flt(r.total) - flt(refunded_total(r.name))
        base += net * (flt(r.exchange_rate) or 1)

    # Sumber 2: baris tab Advance Payable di Payment Entry TERVALIDASI (docstatus 1).
    for r in frappe.get_all(
        "Payment Entry Transaction",
        parent_doctype="Payment Entry",
        filters={
            "parenttype": "Payment Entry", "parentfield": "custom_advance_items",
            "reference_doctype": "Purchase Order", "transaction": po_name, "docstatus": 1,
        },
        fields=["allocated", "parent"],
        ignore_permissions=True,
    ):
        pe_rate = flt(frappe.db.get_value("Payment Entry", r.parent, "source_exchange_rate")) or 1
        base += flt(r.allocated) * pe_rate

    # Sumber 3: baris References NATIVE di Payment Entry tervalidasi (tombol Get Outstanding
    # Orders bawaan). Inilah satu-satunya sumber yang dilihat core; kalau tidak ikut dihitung
    # di sini, hasil rumus ini berbeda dari hasil core dan keduanya saling menimpa.
    # Ketiga sumber saling lepas: baris Pending Cash dan tab Advance Payable TIDAK pernah
    # menjadi References, jadi tidak ada yang terhitung dua kali.
    for r in frappe.get_all(
        "Payment Entry Reference",
        parent_doctype="Payment Entry",
        filters={
            "parenttype": "Payment Entry", "reference_doctype": "Purchase Order",
            "reference_name": po_name, "docstatus": 1,
        },
        fields=["allocated_amount", "parent"],
        ignore_permissions=True,
    ):
        pe = frappe.db.get_value(
            "Payment Entry", r.parent,
            ["payment_type", "source_exchange_rate", "target_exchange_rate"], as_dict=True,
        )
        # allocated_amount ada dalam mata uang AKUN PARTY: sisi paid_to untuk Pay,
        # sisi paid_from untuk Receive.
        party_rate = flt(
            pe.source_exchange_rate if pe and pe.payment_type == "Receive"
            else (pe.target_exchange_rate if pe else 1)
        ) or 1
        base += flt(r.allocated_amount) * party_rate

    # base = mata uang company; Advance Paid disimpan dalam mata uang PO.
    frappe.db.set_value(
        "Purchase Order", po_name, "advance_paid", flt(base / po_rate, 2),
        update_modified=False,
    )


def _refresh_po_pending_cash(po_name):
    """Kolom "PC" di list PO = daftar kasbon yang menunjuk PO ini.

    Yang belum Paid ikut ditampilkan (pertanyaannya "PC apa saja yang sudah dibuat"),
    tapi yang VOID tidak — kasbon itu dibatalkan, bukan sekadar belum cair.
    """
    names = frappe.get_all(
        "Pending Cash",
        filters={"modul": "Purchase Order", "number": po_name, "void": 0},
        pluck="name",
        order_by="name",
        ignore_permissions=True,
    )
    value = ", ".join(names)
    if frappe.db.get_value("Purchase Order", po_name, "custom_pending_cash") != value:
        # update_modified=False: kolom turunan, jangan mengotori "Last Modified" PO.
        frappe.db.set_value(
            "Purchase Order", po_name, "custom_pending_cash", value, update_modified=False
        )


def sync_po_advance_paid(doc, method=None):
    """doc_event Pending Cash / Pending Cash Refund / Payment Entry -> segarkan Advance Paid PO."""
    targets = set()
    if doc.doctype == "Pending Cash":
        if doc.get("modul") == "Purchase Order" and doc.get("number"):
            targets.add(doc.number)
        # Nomor PO-nya dipindah? PO yang LAMA juga harus dihitung ulang, kalau tidak
        # uang muka itu menempel selamanya di PO yang sudah tidak menunjuknya.
        before = doc.get_doc_before_save() if method != "on_trash" else None
        if before and before.get("modul") == "Purchase Order" and before.get("number"):
            targets.add(before.number)
    elif doc.doctype == "Pending Cash Refund":
        # Refund disimpan lewat frappe.db.set_value ke induknya (sync_refunded), yang
        # MELEWATI on_update Pending Cash — jadi PO-nya harus dicari dari sini sendiri.
        for pc in {r.pending_cash for r in (doc.get("allocations") or []) if r.pending_cash}:
            row = frappe.db.get_value("Pending Cash", pc, ["modul", "number"], as_dict=True)
            if row and row.modul == "Purchase Order" and row.number:
                targets.add(row.number)
    else:  # Payment Entry
        targets |= {r.transaction for r in (doc.get("custom_advance_items") or []) if r.transaction}

    for po in targets:
        if frappe.db.exists("Purchase Order", po):
            _recalc_po_advance(po)
            _refresh_po_pending_cash(po)

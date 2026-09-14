"""Cek layout Purchase Order CMI.

Jalankan:  bench --site erp.localhost run-tests --module erpnext_custom.test_purchase_order_form

Yang dijaga: "Required By" (schedule_date) sudah TIDAK ada di form, jadi kalau
purchasing.before_validate berhenti mengisinya PO baru gagal disimpan; dan urutan
header (field_order) tetap seperti spesifikasi CMI.
"""

import json
import unittest

import frappe
from frappe.utils import today

from erpnext_custom.install import PO_HEADER_ORDER, PO_LIST_COLUMNS, PO_STANDARD_FILTERS


def _sample_masters():
    """Supplier eksternal + item pembelian + gudang untuk dokumen uji.

    Warehouse WAJIB ikut: query item tidak berurut, jadi yang terpilih bisa item stok —
    dan ERPNext menolak baris item stok tanpa gudang.
    """
    supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 0, "disabled": 0}, "name")
    item = frappe.db.get_value(
        "Item", {"is_purchase_item": 1, "has_variants": 0, "disabled": 0}, "name"
    )
    company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
    warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
    return supplier, item, warehouse


class TestPurchaseOrderForm(unittest.TestCase):
    def test_header_order(self):
        order = [df.fieldname for df in frappe.get_meta("Purchase Order").fields]
        seen = [fn for fn in order if fn in PO_HEADER_ORDER]
        self.assertEqual(seen, PO_HEADER_ORDER)
        self.assertEqual(frappe.get_meta("Purchase Order").get_field("conversion_rate").label,
                         "Exchange Rate")

    def test_hidden_fields(self):
        meta = frappe.get_meta("Purchase Order")
        for fieldname in ("company", "schedule_date", "custom_row_in_sb", "shipping_rule"):
            df = meta.get_field(fieldname)
            self.assertTrue(df is None or df.hidden, fieldname)
        # "Required By" tidak boleh menuntut isian user (server yang mengisinya).
        self.assertFalse(frappe.get_meta("Purchase Order Item").get_field("schedule_date").reqd)
        # Voyage No / Adjustment dibuang total dari PO.
        for fieldname in ("custom_voyage_no", "custom_adjustment"):
            self.assertIsNone(meta.get_field(fieldname), fieldname)

    def test_branch_editable_and_mandatory(self):
        df = frappe.get_meta("Purchase Order").get_field("branch_office")
        self.assertFalse(df.read_only, "Branch harus bisa diedit user")
        self.assertTrue(df.reqd, "Branch harus mandatory")
        # fetch_if_empty: terisi dari Type saat kosong, tapi tidak menimpa pilihan user.
        self.assertEqual(df.fetch_from, "custom_type.branch")
        self.assertTrue(df.fetch_if_empty)

    def test_advance_paid_follows_doc_currency(self):
        df = frappe.get_meta("Purchase Order").get_field("advance_paid")
        self.assertEqual(df.options, "currency")

    def test_list_view_columns(self):
        """Urutan kolom list + syaratnya: in_list_view=1, dan Subject = ID."""
        import json

        settings = frappe.get_doc("List View Settings", "Purchase Order")
        self.assertEqual([f["fieldname"] for f in json.loads(settings.fields)],
                         [fn for fn, _ in PO_LIST_COLUMNS])
        meta = frappe.get_meta("Purchase Order")
        # Tanpa in_list_view=1 sebuah field TIDAK pernah jadi kolom, seurut apa pun
        # List View Settings-nya (list_view.reorder_listview_fields cuma mengurutkan).
        for fieldname, _label in PO_LIST_COLUMNS:
            # "title" = kolom Subject, "status_field" = indikator; keduanya bukan docfield biasa.
            if fieldname in ("title", "status_field"):
                continue
            self.assertTrue(meta.get_field(fieldname).in_list_view, fieldname)
        self.assertEqual(meta.title_field, "title")
        self.assertEqual(meta.get_field("title").options, "{name} - {supplier_name}")

    def test_purchases_column_tracks_invoices(self):
        """Kolom "Purchases" ikut bertambah saat PI dibuat dan bersih saat PI di-cancel."""
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

        supplier, item, warehouse = _sample_masters()
        po_type = frappe.db.get_value("Purchase Order Type", {"branch": ["is", "set"]}, "name")
        if not (supplier and item and warehouse and po_type):
            self.skipTest("butuh Supplier eksternal, Item pembelian, Warehouse & PO Type ber-Branch")

        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "items": [{"item_code": item, "qty": 4, "rate": 1000000, "warehouse": warehouse}],
        })
        po.insert(ignore_permissions=True)
        po.flags.cmi_action_ok = True
        po.submit()

        def column():
            return frappe.db.get_value("Purchase Order", po.name, "custom_purchases") or ""

        invoices = []
        for idx in range(2):
            pi = make_purchase_invoice(po.name)
            for row in pi.items:
                row.qty = 1
            pi.bill_no = "BILL-%s" % idx
            pi.bill_date = today()
            pi.custom_type = po_type
            pi.insert(ignore_permissions=True)
            pi.flags.cmi_action_ok = True
            pi.submit()
            invoices.append(pi)
            self.assertIn(pi.name, column())

        # Cancel TIDAK lewat on_update (Frappe hanya memanggil on_cancel di jalur itu).
        invoices[0].flags.cmi_action_ok = True
        invoices[0].cancel()
        self.assertNotIn(invoices[0].name, column())
        self.assertIn(invoices[1].name, column())
        frappe.db.rollback()

    def test_no_tax_row_excluded_from_ppn(self):
        """Centang "No Tax" per baris: baris itu keluar dari basis PPN, di PO dan PI."""
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

        supplier, _item, warehouse = _sample_masters()
        po_type = frappe.db.get_value("Purchase Order Type", {"branch": ["is", "set"]}, "name")
        items = frappe.db.sql(
            """select name from `tabItem` where is_purchase_item=1 and has_variants=0
               and disabled=0 order by name limit 2"""
        )
        if not (supplier and warehouse and po_type and len(items) >= 2):
            self.skipTest("butuh Supplier eksternal, 2 Item pembelian, Warehouse & PO Type ber-Branch")

        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "custom_tax_input": "11%",
            "items": [
                {"item_code": items[0][0], "qty": 1, "rate": 1000000, "warehouse": warehouse},
                {"item_code": items[1][0], "qty": 1, "rate": 2000000, "warehouse": warehouse,
                 "custom_no_tax": 1},
            ],
        })
        po.insert(ignore_permissions=True)
        # 11% hanya atas baris pertama (1.000.000), bukan seluruh 3.000.000.
        self.assertEqual(po.total, 3000000)
        self.assertEqual(po.custom_tax_amount, 110000)
        self.assertEqual(po.grand_total, 3110000)

        po.flags.cmi_action_ok = True
        po.submit()
        pi = make_purchase_invoice(po.name)
        pi.bill_no = "NO-TAX-TEST"
        pi.bill_date = today()
        pi.custom_type = po_type
        pi.insert(ignore_permissions=True)
        self.assertEqual([int(d.custom_no_tax or 0) for d in pi.items], [0, 1])
        self.assertEqual(pi.custom_tax_amount, 110000)
        self.assertEqual(pi.grand_total, 3110000)
        frappe.db.rollback()

    def test_display_fields_follow_update_items(self):
        """Ubah qty PO yang SUDAH submit -> SubTotal/Net Total ikut, tidak membeku.

        Kalau membeku, nilai tersimpan beda dari hitungan sisi client; cmi_amounts lalu
        menulis ulang lewat frm.set_value, form jadi __unsaved, dan setiap tombol
        "Create >" ditolak open_mapped_doc ("You have unsaved changes").
        """
        from erpnext.controllers.accounts_controller import update_child_qty_rate

        supplier, item, warehouse = _sample_masters()
        po_type = frappe.db.get_value("Purchase Order Type", {"branch": ["is", "set"]}, "name")
        if not (supplier and item and warehouse and po_type):
            self.skipTest("butuh Supplier eksternal, Item pembelian, Warehouse & PO Type ber-Branch")

        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "items": [{"item_code": item, "qty": 1, "rate": 10000000, "warehouse": warehouse}],
        })
        po.insert(ignore_permissions=True)
        po.flags.cmi_action_ok = True
        po.submit()
        self.assertEqual(po.custom_net_total, 10000000)

        update_child_qty_rate(
            "Purchase Order",
            json.dumps([{
                "docname": po.items[0].name,
                "name": po.items[0].name,
                "item_code": item,
                "qty": 10,
                "rate": 10000000,
            }]),
            po.name,
        )
        stored = frappe.db.get_value(
            "Purchase Order", po.name, ["total", "custom_amount_total", "custom_net_total"],
            as_dict=True,
        )
        self.assertEqual(stored.total, 100000000)
        self.assertEqual(stored.custom_amount_total, 100000000)
        self.assertEqual(stored.custom_net_total, 100000000)
        frappe.db.rollback()

    def test_quick_filters(self):
        """Quick filter default; daftar di install.py otoritatif (bawaan lain dimatikan)."""
        meta = frappe.get_meta("Purchase Order")
        active = [df.fieldname for df in meta.fields if df.in_standard_filter]
        self.assertEqual(set(active), set(PO_STANDARD_FILTERS))
        # Urutan quick filter mengikuti urutan field di doctype, bukan PO_STANDARD_FILTERS.
        self.assertEqual(active, PO_STANDARD_FILTERS)

    def test_item_grid_columns(self):
        """Item | Qty | UOM | Price | Warehouse | Amount, dengan lebar default CMI."""
        meta = frappe.get_meta("Purchase Order Item")
        shown = [(df.fieldname, df.columns) for df in meta.fields if df.in_list_view]
        self.assertEqual(shown, [("item_code", 3), ("qty", 2), ("uom", 1),
                                 ("rate", 3), ("warehouse", 3), ("amount", 4),
                                 ("custom_no_tax", 1)])
        self.assertEqual(meta.get_field("item_code").label, "Item")
        self.assertEqual(meta.get_field("warehouse").label, "Warehouse")

    def test_save_without_required_by(self):
        supplier, item, warehouse = _sample_masters()
        # Branch mandatory & diturunkan dari Type -> pasang branch sementara (di-rollback).
        po_type = frappe.db.get_value("Purchase Order Type", {}, "name")
        office = frappe.db.get_value("CMI Office", {}, "name")
        if not (supplier and item and warehouse and po_type and office):
            self.skipTest("butuh Supplier eksternal, Item pembelian, Warehouse, PO Type & CMI Office")
        frappe.db.set_value("Purchase Order Type", po_type, "branch", office)
        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "custom_tax_input": "11%",
            "items": [{"item_code": item, "qty": 2, "rate": 100000, "warehouse": warehouse}],
        })
        po.insert(ignore_permissions=True)
        self.assertEqual(po.schedule_date, po.transaction_date)
        self.assertEqual(po.custom_amount_total, 200000)
        self.assertEqual(po.custom_tax_amount, 22000)
        self.assertEqual(po.custom_net_total, 222000)
        self.assertEqual(po.branch_office, office)
        frappe.db.rollback()

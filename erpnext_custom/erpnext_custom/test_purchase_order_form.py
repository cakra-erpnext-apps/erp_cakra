"""Cek layout Purchase Order CMI.

Jalankan:  bench --site erp.localhost run-tests --module erpnext_custom.test_purchase_order_form

Yang dijaga: "Required By" (schedule_date) sudah TIDAK ada di form, jadi kalau
purchasing.before_validate berhenti mengisinya PO baru gagal disimpan; dan urutan
header (field_order) tetap seperti spesifikasi CMI.
"""

import unittest

import frappe
from frappe.utils import today

from erpnext_custom.install import PO_HEADER_ORDER, PO_LIST_COLUMNS, PO_STANDARD_FILTERS


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

    def test_branch_read_only_mandatory(self):
        df = frappe.get_meta("Purchase Order").get_field("branch_office")
        self.assertTrue(df.read_only, "Branch harus read-only")
        self.assertTrue(df.reqd, "Branch harus mandatory")
        self.assertEqual(df.fetch_from, "custom_type.branch")

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

        supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 0, "disabled": 0}, "name")
        item = frappe.db.get_value("Item", {"is_purchase_item": 1, "has_variants": 0, "disabled": 0}, "name")
        po_type = frappe.db.get_value("Purchase Order Type", {"branch": ["is", "set"]}, "name")
        if not (supplier and item and po_type):
            self.skipTest("butuh Supplier eksternal, Item pembelian & Purchase Order Type ber-Branch")

        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "items": [{"item_code": item, "qty": 4, "rate": 1000000}],
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
                                 ("rate", 3), ("warehouse", 3), ("amount", 4)])
        self.assertEqual(meta.get_field("item_code").label, "Item")
        self.assertEqual(meta.get_field("warehouse").label, "Warehouse")

    def test_save_without_required_by(self):
        supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 0, "disabled": 0}, "name")
        item = frappe.db.get_value("Item", {"is_purchase_item": 1, "has_variants": 0, "disabled": 0}, "name")
        # Branch mandatory & diturunkan dari Type -> pasang branch sementara (di-rollback).
        po_type = frappe.db.get_value("Purchase Order Type", {}, "name")
        office = frappe.db.get_value("CMI Office", {}, "name")
        if not (supplier and item and po_type and office):
            self.skipTest("butuh Supplier eksternal, Item pembelian, Purchase Order Type & CMI Office")
        frappe.db.set_value("Purchase Order Type", po_type, "branch", office)
        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "custom_tax_input": "11%",
            "items": [{"item_code": item, "qty": 2, "rate": 100000}],
        })
        po.insert(ignore_permissions=True)
        self.assertEqual(po.schedule_date, po.transaction_date)
        self.assertEqual(po.custom_amount_total, 200000)
        self.assertEqual(po.custom_tax_amount, 22000)
        self.assertEqual(po.custom_net_total, 222000)
        self.assertEqual(po.branch_office, office)
        frappe.db.rollback()

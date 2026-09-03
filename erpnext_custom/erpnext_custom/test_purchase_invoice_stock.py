"""Cek Update Stock otomatis di Purchase Invoice.

Jalankan:  bench --site erp.localhost run-tests --module erpnext_custom.test_purchase_invoice_stock
"""

import unittest
from unittest.mock import patch

import frappe

from erpnext_custom.overrides.purchasing import _auto_update_stock

STOCK = {"BARANG": 1, "JASA": 0}


def _doc(codes, **kw):
    d = frappe._dict(items=[frappe._dict(item_code=c, purchase_receipt=None) for c in codes])
    d.update(kw)
    return d


class TestAutoUpdateStock(unittest.TestCase):
    def run_case(self, doc):
        with patch("frappe.get_cached_value", side_effect=lambda dt, name, f: STOCK[name]):
            _auto_update_stock(doc)
        return doc.get("update_stock")

    def test_stock_item_on(self):
        self.assertEqual(self.run_case(_doc(["BARANG"])), 1)
        self.assertEqual(self.run_case(_doc(["JASA", "BARANG"])), 1)

    def test_non_stock_off(self):
        self.assertEqual(self.run_case(_doc(["JASA"])), 0)
        self.assertEqual(self.run_case(_doc([])), 0)

    def test_from_purchase_receipt_off(self):
        doc = _doc(["BARANG"])
        doc["items"][0].purchase_receipt = "MAT-PRE-0001"
        self.assertEqual(self.run_case(doc), 0)

    def test_return_untouched(self):
        doc = _doc(["BARANG"], is_return=1, update_stock=0)
        self.assertEqual(self.run_case(doc), 0)

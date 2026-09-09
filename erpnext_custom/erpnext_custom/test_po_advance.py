"""Advance Paid Purchase Order: uang muka lewat Pending Cash dan pengembaliannya.

Jalankan:  bench --site erp.localhost run-tests --module erpnext_custom.test_po_advance

Yang dijaga: refund kasbon uang muka HARUS menurunkan Advance Paid di PO. Dua hal yang
gampang lepas — rumusnya (dulu hanya menjumlah total, tanpa mengurangi refund) dan
pemicunya (sync_refunded menulis ke induk lewat frappe.db.set_value, jadi on_update
Pending Cash tidak pernah jalan; hook-nya harus menempel di Pending Cash Refund).
"""

import unittest

import frappe
from frappe.utils import today


class TestPurchaseOrderAdvance(unittest.TestCase):
    def _masters(self):
        supplier = frappe.db.get_value("Supplier", {"is_internal_supplier": 0, "disabled": 0}, "name")
        item = frappe.db.get_value(
            "Item", {"is_purchase_item": 1, "has_variants": 0, "disabled": 0}, "name"
        )
        company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
        warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
        po_type = frappe.db.get_value("Purchase Order Type", {"branch": ["is", "set"]}, "name")
        # UMP = Uang Muka Pembelian; yang relevan arahnya Cash Outflow.
        pc_type = frappe.db.get_value(
            "Pending Cash Type", {"direction": "Cash Outflow", "enabled": 1}, "name"
        )
        bank = frappe.db.get_value("Bank Account", {"company": company}, "name")
        cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
        return supplier, item, warehouse, company, po_type, pc_type, bank, cost_center

    def test_refund_lowers_advance_paid(self):
        from erp.fico.doctype.pending_cash.pending_cash import bulk_refund
        from erp.fico.doctype.pending_cash_refund.pending_cash_refund import bulk_validate
        from erpnext_custom.workflow import validate_doc, mark_paid

        supplier, item, warehouse, company, po_type, pc_type, bank, cost_center = self._masters()
        if not all((supplier, item, warehouse, company, po_type, pc_type, bank, cost_center)):
            self.skipTest("butuh Supplier, Item, Warehouse, PO Type ber-Branch, Pending Cash Type, Bank Account & Cost Center")

        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "company": company,
            "supplier": supplier,
            "custom_type": po_type,
            "transaction_date": today(),
            "items": [{"item_code": item, "qty": 1, "rate": 10000000, "warehouse": warehouse}],
        })
        po.insert(ignore_permissions=True)
        po.flags.cmi_action_ok = True
        po.submit()

        def advance():
            return frappe.db.get_value("Purchase Order", po.name, "advance_paid")

        self.assertEqual(advance(), 0)

        pc = frappe.get_doc({
            "doctype": "Pending Cash",
            "company": company,
            "pending_cash_type": pc_type,
            "currency": "IDR",
            "exchange_rate": 1,
            "date": today(),
            "cost_center": cost_center,
            "total": 2000000,
            "bank_account": bank,
            "pay_to": supplier,
            "modul": "Purchase Order",
            "number": po.name,
        })
        pc.insert(ignore_permissions=True)
        validate_doc("Pending Cash", pc.name)
        mark_paid(pc.name, paid_date=today(), notes="test")
        self.assertEqual(advance(), 2000000, "Paid harus menaikkan Advance Paid")

        # Refund SEBAGIAN dulu: uang muka tinggal separuh.
        # Refund punya alur Validate sendiri (bulk_validate), bukan workflow CMI umum.
        bulk_validate(_refund_names(bulk_refund(
            [pc.name], refund_date=today(), amount=500000, remark="uji")))
        self.assertEqual(advance(), 1500000, "refund sebagian harus mengurangi Advance Paid")

        # Sisanya dikembalikan -> uang muka habis.
        bulk_validate(_refund_names(bulk_refund(
            [pc.name], refund_date=today(), remark="uji sisa")))
        self.assertEqual(advance(), 0, "refund penuh harus membuat Advance Paid nol")

        frappe.db.rollback()


def _refund_names(result):
    """bulk_refund boleh mengembalikan daftar nama, daftar dict, atau dict berisi daftar."""
    if isinstance(result, dict):
        result = result.get("refunds") or result.get("names") or list(result.values())[0]
    names = []
    for row in result or []:
        names.append(row if isinstance(row, str) else (row.get("name") or row.get("refund")))
    return [n for n in names if n]

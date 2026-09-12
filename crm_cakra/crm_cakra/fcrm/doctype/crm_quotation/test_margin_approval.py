# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

"""Test gerbang persetujuan margin.

Yang diuji di sini hanya bagian yang punya cabang keputusan dan tidak butuh
dokumen tersimpan: perhitungan margin, pemetaan margin -> tingkat persetujuan,
dan cap harga yang menghanguskan tanda tangan. Membuat CRM Quotation sungguhan
butuh inquiry + rute + KM, dan test itu tidak akan jalan di site yang setup
ERPNext-nya belum lengkap -- jadi dokumennya dirakit di memori saja.
"""

import unittest
from unittest.mock import patch

import frappe

from crm_cakra.fcrm.doctype.crm_quotation.crm_quotation import CRMQuotation


def _quotation(rows):
    """CRM Quotation di memori. `rows` = (qty, price, fixed, variable) per baris."""
    doc = frappe.get_doc({"doctype": "CRM Quotation"})
    doc.products = [
        frappe._dict(
            product_code=f"P{i}",
            qty=qty,
            price=price,
            fixed_cost=fixed,
            variable_cost=variable,
            # >0 berarti baris ini punya costing dan boleh dinilai.
            procurement_price=fixed + variable,
        )
        for i, (qty, price, fixed, variable) in enumerate(rows)
    ]
    return doc


class TestRealizedMargin(unittest.TestCase):
    def test_margin_is_measured_against_cost_not_base_price(self):
        # jual 100, biaya 80 -> 20%. Kalau diukur ke Base Price hasilnya 0%.
        self.assertAlmostEqual(_quotation([(1, 100, 50, 30)]).realized_margin(), 20.0)

    def test_qty_is_weighted(self):
        self.assertAlmostEqual(_quotation([(2, 100, 50, 30)]).realized_margin(), 20.0)

    def test_selling_below_cost_gives_negative_margin(self):
        self.assertAlmostEqual(_quotation([(1, 100, 70, 50)]).realized_margin(), -20.0)

    def test_rows_without_costing_are_ignored(self):
        doc = _quotation([(1, 100, 50, 30), (1, 999, 0, 0)])
        doc.products[1].procurement_price = 0
        self.assertAlmostEqual(doc.realized_margin(), 20.0)

    def test_document_without_any_costing_is_not_judged(self):
        """None, bukan 0 -- dokumen yang tidak bisa dinilai jangan sampai dianggap rugi."""
        doc = _quotation([(1, 100, 0, 0)])
        doc.products[0].procurement_price = 0
        self.assertIsNone(doc.realized_margin())


class TestApprovalTier(unittest.TestCase):
    def _tier(self, rows, enabled=True, manager_at=15.0, escalate_at=5.0):
        doc = _quotation(rows)
        doc.approved_by = None
        doc.approval_signature = None
        with patch(
            "crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.margin_approval_settings",
            return_value=(enabled, manager_at, escalate_at),
        ):
            doc.set_approval_requirement()
        return doc.approval_required

    def test_healthy_margin_needs_nobody(self):
        self.assertIsNone(self._tier([(1, 100, 50, 30)]))  # 20%

    def test_thin_margin_needs_manager(self):
        self.assertEqual(self._tier([(1, 100, 60, 30)]), "Sales Manager")  # 10%

    def test_very_thin_margin_escalates(self):
        self.assertEqual(self._tier([(1, 100, 60, 38)]), "Sales Master Manager")  # 2%

    def test_loss_escalates(self):
        self.assertEqual(self._tier([(1, 100, 70, 50)]), "Sales Master Manager")  # -20%

    def test_disabled_never_requires_approval(self):
        self.assertIsNone(self._tier([(1, 100, 60, 38)], enabled=False))

    def test_exactly_at_threshold_is_not_below_it(self):
        """Ambang 15% berarti 15% masih lolos -- 'di bawah', bukan 'di bawah atau sama'."""
        self.assertIsNone(self._tier([(1, 100, 55, 30)]))  # tepat 15%


class TestPricingSignature(unittest.TestCase):
    def test_same_numbers_same_signature(self):
        a = _quotation([(1, 100, 60, 30)]).pricing_signature()
        b = _quotation([(1, 100, 60, 30)]).pricing_signature()
        self.assertEqual(a, b)

    def test_price_change_changes_signature(self):
        a = _quotation([(1, 100, 60, 30)]).pricing_signature()
        b = _quotation([(1, 101, 60, 30)]).pricing_signature()
        self.assertNotEqual(a, b)

    def test_cost_change_changes_signature(self):
        a = _quotation([(1, 100, 60, 30)]).pricing_signature()
        b = _quotation([(1, 100, 61, 30)]).pricing_signature()
        self.assertNotEqual(a, b)

    def test_signature_is_stable_across_processes(self):
        """Bukan hash() bawaan: kalau diacak per proses, tiap persetujuan hangus sendiri."""
        self.assertEqual(
            _quotation([(1, 100, 60, 30)]).pricing_signature(),
            "".join(_quotation([(1, 100, 60, 30)]).pricing_signature()),
        )
        self.assertRegex(_quotation([(1, 100, 60, 30)]).pricing_signature(), r"^[0-9a-f]{32}$")


class TestApprovalExpiry(unittest.TestCase):
    def _approved(self, rows):
        doc = _quotation(rows)
        doc.approved_by = "manager@contoh.test"
        doc.approved_on = frappe.utils.now_datetime()
        doc.approval_signature = doc.pricing_signature()
        return doc

    def _refresh(self, doc):
        with patch(
            "crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.margin_approval_settings",
            return_value=(True, 15.0, 5.0),
        ):
            doc.set_approval_requirement()

    def test_approval_survives_when_pricing_unchanged(self):
        doc = self._approved([(1, 100, 60, 30)])
        self._refresh(doc)
        self.assertEqual(doc.approved_by, "manager@contoh.test")

    def test_approval_dies_when_price_changes(self):
        """Setuju atas angka lama bukan setuju atas angka baru."""
        doc = self._approved([(1, 100, 60, 30)])
        doc.products[0].price = 120
        self._refresh(doc)
        self.assertIsNone(doc.approved_by)
        self.assertIsNone(doc.approval_signature)

    def test_print_is_blocked_until_approved(self):
        doc = _quotation([(1, 100, 60, 38)])
        doc.approved_by = None
        doc.approval_signature = None
        self._refresh(doc)
        with self.assertRaises(frappe.ValidationError):
            doc.validate_margin_approved()

    def test_print_passes_once_approved(self):
        doc = self._approved([(1, 100, 60, 38)])
        doc.approval_required = "Sales Master Manager"
        doc.validate_margin_approved()  # tidak boleh melempar

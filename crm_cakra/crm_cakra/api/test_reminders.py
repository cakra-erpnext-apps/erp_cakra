# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

"""Test dua fungsi keputusan pengingat.

Sengaja hanya bagian yang murni logika: siapa yang diingatkan, dan kapan boleh
diingatkan lagi. Keduanya tidak menyentuh DB, jadi test ini jalan tanpa perlu
data contoh -- beda dengan test_crm_inquiry yang butuh setup ERPNext lengkap.
"""

import unittest

from frappe.utils import add_days, now_datetime

from crm_cakra.api.reminders import _due, _recipients


class TestReminderRecipients(unittest.TestCase):
	def test_assignee_wins_over_owner(self):
		row = {"_assign": '["sari@contoh.test"]', "owner": "budi@contoh.test"}
		self.assertEqual(_recipients(row), ["sari@contoh.test"])

	def test_falls_back_to_owner_field_then_owner(self):
		row = {"_assign": None, "inquiry_owner": "sari@contoh.test", "owner": "budi@contoh.test"}
		self.assertEqual(_recipients(row, "inquiry_owner"), ["sari@contoh.test"])

		row = {"_assign": None, "inquiry_owner": None, "owner": "budi@contoh.test"}
		self.assertEqual(_recipients(row, "inquiry_owner"), ["budi@contoh.test"])

	def test_administrator_is_never_a_recipient(self):
		"""Administrator bukan orang yang menindaklanjuti apa pun."""
		row = {"_assign": '["Administrator"]', "owner": "Administrator"}
		self.assertEqual(_recipients(row), [])

	def test_duplicate_assignees_collapse(self):
		row = {"_assign": '["sari@contoh.test", "sari@contoh.test"]', "owner": "budi@contoh.test"}
		self.assertEqual(_recipients(row), ["sari@contoh.test"])

	def test_broken_assign_json_falls_back(self):
		"""_assign yang rusak tidak boleh menelan pengingatnya."""
		row = {"_assign": "bukan json", "owner": "budi@contoh.test"}
		self.assertEqual(_recipients(row), ["budi@contoh.test"])


class TestReminderDue(unittest.TestCase):
	def test_never_reminded_is_due(self):
		self.assertTrue(_due(None, 7))

	def test_within_gap_is_not_due(self):
		self.assertFalse(_due(add_days(now_datetime(), -2), 7))

	def test_past_gap_is_due(self):
		self.assertTrue(_due(add_days(now_datetime(), -8), 7))

	def test_zero_gap_allows_daily(self):
		self.assertTrue(_due(add_days(now_datetime(), -1), 0))

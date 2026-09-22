# Copyright (c) 2026, Cakra Mandiri Indonesia and contributors
# For license information, please see license.txt

"""Test jabatan CRM.

Yang diuji cuma bagian yang berakibat izin: tiap jabatan punya role dasar, dan
gerbang Procurement menerima tim Procurement tapi menolak Marketing. Role-nya
di-mock, jadi test ini tidak butuh user sungguhan di site.
"""

import unittest
from unittest.mock import patch

from crm_cakra.roles import (
	BASE_ROLE,
	JOB_ROLES,
	MARKETING_ROLES,
	PROCUREMENT_ROLES,
	has_procurement_access,
)


def _with_roles(roles):
	return patch("crm_cakra.roles.frappe.get_roles", return_value=list(roles))


class TestRoles(unittest.TestCase):
	def test_every_job_role_has_a_base_role(self):
		# Jabatan tanpa role dasar = user tanpa permission doctype sama sekali.
		self.assertEqual(set(JOB_ROLES), set(BASE_ROLE))
		self.assertTrue(set(BASE_ROLE.values()) <= {"Sales Manager", "Sales User"})

	def test_procurement_passes(self):
		for role in PROCUREMENT_ROLES + ("Procurement Costing", "System Manager"):
			with _with_roles(["Sales User", role]):
				self.assertTrue(has_procurement_access("a@b.c"), role)

	def test_marketing_blocked(self):
		for role in MARKETING_ROLES:
			with _with_roles(["Sales Manager", "Sales User", role]):
				self.assertFalse(has_procurement_access("a@b.c"), role)

	def test_base_roles_alone_are_not_procurement(self):
		# Inti pembagiannya: Sales Manager/Sales User polos bukan tiket masuk.
		with _with_roles(["Sales Manager", "Sales User"]):
			self.assertFalse(has_procurement_access("a@b.c"))


if __name__ == "__main__":
	unittest.main()

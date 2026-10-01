import frappe
from frappe.tests.utils import FrappeTestCase

from erp.downstream_lock import REFS, downstream_refs


class TestDownstreamLock(FrappeTestCase):
	def test_refs_point_to_real_fields(self):
		# Field penaut yang di-rename diam-diam = kunci bocor tanpa error; tangkap di sini.
		for src, refs in REFS.items():
			self.assertTrue(frappe.db.exists("DocType", src), src)
			for dt, field, child, type_field in refs:
				meta = frappe.get_meta(child or dt)
				self.assertTrue(meta.has_field(field), f"{src}: {child or dt}.{field}")
				if type_field:
					self.assertTrue(meta.has_field(type_field), f"{src}: {child}.{type_field}")
			for name in frappe.get_all(src, pluck="name", limit=3):
				downstream_refs(frappe.get_doc(src, name))  # SQL-nya valid

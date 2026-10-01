import datetime
from decimal import Decimal

from frappe.tests import UnitTestCase

from crm_cakra.integrations import ascend


class FakeCursor:
	"""Cursor pymssql palsu: setiap SELECT master mengembalikan baris dari ROWS[tabel]."""

	ROWS = {
		"AR_Customers": [
			{"id": 1, "name": "PT Satu", "active": 1},
			{"id": 2, "name": "PT Kembar", "active": 1},
			{"id": 3, "name": "pt kembar ", "active": 1},
			{"id": 4, "name": "PT Lama", "active": 0},
		],
	}

	def execute(self, sql, args=None):
		self.last = next((v for k, v in self.ROWS.items() if f"FROM {k}" in sql), [])

	def fetchall(self):
		return self.last


class TestAscend(UnitTestCase):
	def test_hash_ignores_type_noise_but_not_values(self):
		h = {"EstimationNo": "E1 ", "EffectiveDate": datetime.datetime(2026, 9, 7), "RevIncTax": Decimal("100.0000")}
		d = [{"IsExpense": False, "Amount": Decimal("5.5"), "Remarks": "x"}]
		same = ({**h, "EstimationNo": "E1", "EffectiveDate": datetime.date(2026, 9, 7), "RevIncTax": 100.0}, [{**d[0], "IsExpense": 0, "Amount": 5.5}])
		self.assertEqual(ascend._hash(h, d), ascend._hash(*same))
		self.assertNotEqual(ascend._hash(h, d), ascend._hash(h, [{**d[0], "Amount": 5.6}]))
		# approval ikut hash penuh, tapi tidak ikut perbandingan "perlu tulis data?"
		approved = {**h, "ApprovedDateTime": datetime.datetime(2026, 9, 8)}
		self.assertNotEqual(ascend._hash(h, d), ascend._hash(approved, d))
		self.assertEqual(ascend._snapshot(h, d, False), ascend._snapshot(approved, d, False))

	def test_xml_escapes_attributes(self):
		xml = ascend._xml([{"Remarks": 'a "b" <c> & d', "TypeID": 7}])
		self.assertEqual(xml, '<Items><Item Remarks=\'a "b" &lt;c&gt; &amp; d\' TypeID="7"/></Items>')

	def test_master_lookup_refuses_missing_duplicate_and_disabled(self):
		m = ascend.Masters(FakeCursor())
		self.assertEqual(m.id("customer", " pt satu", "Customer"), 1)
		self.assertEqual(m.id("customer", "", "Customer"), 0)
		self.assertEqual(m.errors, [])
		for name in ("PT Kembar", "PT Lama", "PT Hilang"):
			self.assertEqual(m.id("customer", name, "Customer"), 0)
		self.assertEqual(len(m.errors), 3)
		self.assertIn("ada 2 kali", m.errors[0])
		self.assertRaises(ascend.SyncError, m.raise_errors)
		self.assertEqual(m.name("customer", 4), "PT Lama")  # disabled tetap terbaca untuk arah tarik

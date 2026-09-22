"""Cek Bin Adjustment: kurangi qty, kosongkan item, ganti item -- dan dampak stoknya.

    bench --site erp.localhost run-tests --module erpnext_custom.test_bin_adjust

Gudang uji dibuat sendiri lalu di-rollback, tapi ITEM-nya sengaja item yang sudah
bertransaksi: dengan enable_item_wise_inventory_account, item yang Item Group-nya
belum dipetakan akan ditolak dokumen stok dan yang gagal bukan yang sedang diuji
(lihat catatan di bin_ledger.py).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, get_datetime, nowdate

from erpnext_custom import bin_ledger


class TestBinAdjust(FrappeTestCase):
	def setUp(self):
		self.company, self.item, self.item2 = _dua_item_bertransaksi()
		self.gudang = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "ZZ Uji Adjustment",
				"company": self.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		self.rak = frappe.get_doc(
			{"doctype": "Rack", "gudang": self.gudang.name, "rack_code": "ZJ"}
		).insert(ignore_permissions=True)
		self.bin = frappe.get_doc(
			{"doctype": "Bin Location", "rack": self.rak.name, "bin_code": "ZJ0101A"}
		).insert(ignore_permissions=True)
		# Stok betulan: adjustment memang mengubah stok, jadi tidak bisa diuji di atas
		# buku besar bin yang dikarang sendiri.
		self._terima(10)
		self.umur = get_datetime(add_days(nowdate(), -30))
		frappe.db.set_value(
			"Bin Ledger Entry",
			{"item_code": self.item, "gudang": self.gudang.name},
			"received_on",
			self.umur,
			update_modified=False,
		)
		bin_ledger.move(
			self.item, bin_ledger.staging_bin(self.gudang.name), self.bin.name, 10, None
		)

	def tearDown(self):
		frappe.db.rollback()

	# ------------------------------------------------------------- bantu

	def _terima(self, qty):
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": self.company,
				"items": [
					{
						"item_code": self.item,
						"qty": qty,
						"t_warehouse": self.gudang.name,
						"basic_rate": 1000,
					}
				],
			}
		)
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		return se

	def _adj(self, **row):
		baris = {"bin_location": self.bin.name, "item_code": self.item, "reason": "Salah Hitung"}
		baris.update(row)
		return frappe.get_doc(
			{"doctype": "Bin Adjustment", "gudang": self.gudang.name, "items": [baris]}
		).insert(ignore_permissions=True)

	def _di_bin(self, item_code, bin_location=None):
		return flt(bin_ledger.bin_qty(item_code, bin_location or self.bin.name))

	def _di_gudang(self, item_code):
		return flt(
			frappe.db.get_value(
				"Bin", {"item_code": item_code, "warehouse": self.gudang.name}, "actual_qty"
			)
		)

	# ------------------------------------------------------------- kurangi

	def test_kurangi_qty_menurunkan_bin_dan_stok(self):
		doc = self._adj(qty_after=7)
		doc.submit()
		self.assertEqual(self._di_bin(self.item), 7)
		self.assertEqual(self._di_gudang(self.item), 7)
		self.assertTrue(doc.reload().stock_reconciliation)

	def test_koreksi_tetap_di_bin_yang_dikoreksi(self):
		"""Jaring untuk jebakan urutan hook.

		SLE disubmit sebelum tabBin ikut naik, jadi kalau `sle_hook` tidak dimatikan
		selama Stock Reconciliation-nya jalan, dia akan membaca saldo lama, MEMBATALKAN
		koreksi ini, lalu doc_hook menaruh selisihnya di staging. Isi rak jadi bohong
		walaupun totalnya kebetulan benar -- persis yang paling mahal di gudang.
		"""
		self._adj(qty_after=7).submit()
		self.assertEqual(self._di_bin(self.item), 7)
		self.assertEqual(self._di_bin(self.item, bin_ledger.staging_bin(self.gudang.name)), 0)
		self.assertEqual(bin_ledger.audit(self.gudang.name), [])

	def test_qty_after_nol_mengosongkan_item_dari_bin(self):
		self._adj(qty_after=0).submit()
		self.assertEqual(self._di_bin(self.item), 0)
		self.assertEqual(self._di_gudang(self.item), 0)
		self.assertFalse(
			frappe.db.exists("Item Bin Qty", {"item_code": self.item, "bin_location": self.bin.name})
		)

	# ------------------------------------------------------------- ganti item

	def test_ganti_item_memindahkan_isi_bin_dan_stok(self):
		self._adj(new_item_code=self.item2, qty_after=10, reason="Salah Item").submit()
		self.assertEqual(self._di_bin(self.item), 0)
		self.assertEqual(self._di_bin(self.item2), 10)
		self.assertEqual(self._di_gudang(self.item), 0)
		self.assertEqual(self._di_gudang(self.item2), 10)

	def test_umur_barang_ikut_saat_ganti_item(self):
		"""Yang salah cuma labelnya, bukan kapan barangnya datang -- FIFO tidak boleh direset."""
		self._adj(new_item_code=self.item2, qty_after=10, reason="Salah Item").submit()
		lapisan = bin_ledger.fifo_layers(self.item2, self.gudang.name, self.bin.name)
		self.assertEqual(get_datetime(lapisan[0].received_on), self.umur)

	# ------------------------------------------------------------- batal

	def test_batal_mengembalikan_bin_stok_dan_umurnya(self):
		doc = self._adj(qty_after=7)
		doc.submit()
		doc.cancel()
		self.assertEqual(self._di_bin(self.item), 10)
		self.assertEqual(self._di_gudang(self.item), 10)
		self.assertEqual(bin_ledger.audit(self.gudang.name), [])
		self.assertEqual(
			frappe.db.get_value("Stock Reconciliation", doc.stock_reconciliation, "docstatus"), 2
		)
		lapisan = bin_ledger.fifo_layers(self.item, self.gudang.name, self.bin.name)
		self.assertEqual(get_datetime(lapisan[0].received_on), self.umur)

	# ------------------------------------------------------------- penjaga

	def test_qty_before_dihitung_ulang_bukan_dari_form(self):
		doc = self._adj(qty_before=999, qty_after=7)
		self.assertEqual(flt(doc.items[0].qty_before), 10)

	def test_menambah_qty_ditolak(self):
		self.assertRaises(frappe.ValidationError, self._adj, qty_after=12)

	def test_baris_tanpa_perubahan_ditolak(self):
		self.assertRaises(frappe.ValidationError, self._adj, qty_after=10)

	def test_item_yang_tidak_ada_di_bin_ditolak(self):
		self.assertRaises(frappe.ValidationError, self._adj, item_code=self.item2, qty_after=0)

	def test_bin_terkunci_replan_ditolak(self):
		frappe.get_doc(
			{
				"doctype": "Bin Replan",
				"gudang": self.gudang.name,
				"items": [
					{
						"item_code": self.item,
						"from_bin_location": self.bin.name,
						"bin_location": self.bin.name,
						"qty": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
		self.assertRaises(frappe.ValidationError, self._adj, qty_after=7)

	def test_dua_baris_item_dan_bin_yang_sama_ditolak(self):
		doc = frappe.get_doc(
			{
				"doctype": "Bin Adjustment",
				"gudang": self.gudang.name,
				"items": [
					{
						"bin_location": self.bin.name,
						"item_code": self.item,
						"qty_after": 7,
						"reason": "Salah Hitung",
					},
					{
						"bin_location": self.bin.name,
						"item_code": self.item,
						"qty_after": 5,
						"reason": "Salah Hitung",
					},
				],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)


def _dua_item_bertransaksi():
	"""(company, item, item lain) yang sudah punya stock ledger dan akun persediaannya jelas."""
	rows = frappe.db.sql(
		"""
		select distinct s.company, s.item_code
		from `tabStock Ledger Entry` s
		join `tabItem` i on i.name = s.item_code
		join `tabCompany` c on c.name = s.company
		where s.is_cancelled = 0 and i.is_stock_item = 1 and i.disabled = 0
		  and i.has_batch_no = 0 and i.has_serial_no = 0
		  and ifnull(c.stock_adjustment_account, '') != ''
		order by s.company, s.item_code
		""",
		as_dict=True,
	)
	per_company = {}
	for r in rows:
		per_company.setdefault(r.company, []).append(r.item_code)
	for company, items in per_company.items():
		if len(items) >= 2:
			return company, items[0], items[1]
	raise frappe.ValidationError("Butuh 2 item yang sudah bertransaksi untuk menguji adjustment.")

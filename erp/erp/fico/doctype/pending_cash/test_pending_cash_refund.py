"""Cek refund Pending Cash (per party, FIFO lintas kasbon, void, penomoran). Jalankan:

	bench --site erp.localhost execute erp.fico.doctype.pending_cash.test_pending_cash_refund.run

Yang dijaga:
  - refund adalah DOKUMEN sendiri bernomor seri RF/<abbr>/<yy>/####
  - satu refund boleh memotong BEBERAPA kasbon: alokasinya FIFO (tertua dulu), dan
    jurnalnya satu — sebaris uang muka per kasbon + SATU baris bank sejumlah totalnya
  - Outstanding = sisa seluruh kasbon party, refund melebihi itu ditolak
  - jurnalnya BARU, bertanggal refund, sisinya terbalik dari jurnal Paid — jurnal Paid
    tidak disentuh (inti fiturnya: refund beda bulan tidak mengusik bulan yang sudah tutup)
  - tombol Refund di kasbonnya memaku alokasi ke kasbon itu (bukan FIFO)
  - Unpaid ditolak selama ada refund aktif
  - Void mengembalikan sisa, jurnalnya di-cancel tapi TETAP ada
"""

import frappe
from frappe.utils import add_days, flt, getdate

from erp.fico.doctype.pending_cash import pending_cash as pc
from erp.fico.doctype.pending_cash.test_pending_cash_direction import (
	TOTAL, _bank, _cleanup, _je_rows, _make_doc, _make_type,
)


def _refunds(name):
	return sorted({r.parent for r in pc._refund_rows(name)})


def _drop_refunds(names):
	# Lewat tabel alokasi langsung, BUKAN _refunds(): yang itu menyaring void=0, dan
	# refund void justru yang paling mudah tertinggal jadi sampah di site uji.
	rows = frappe.db.sql(
		"""select distinct parent from `tabPending Cash Refund Allocation`
		   where pending_cash in %s""",
		(list(names) or [""],),
		pluck=True,
	)
	for r in rows:
		try:
			frappe.delete_doc("Pending Cash Refund", r, force=1, ignore_permissions=True)
		except Exception as e:
			print("bersih-bersih refund:", e)


def _make_refund(party, bank, company, rows, refund_date=None, remark=None,
                 party_type="Supplier", validate=True, **extra):
	"""`rows` = [(nomor Pending Cash, nominal), ...]. Refund Amount TIDAK diisi —
	memang harus muncul sendiri dari jumlah barisnya."""
	doc = frappe.get_doc({
		"doctype": "Pending Cash Refund",
		"party_type": party_type,
		"party": party,
		"company": company,
		"bank_account": bank,
		"refund_date": refund_date or getdate(),
		"remark": remark,
		"allocations": [{"pending_cash": n, "amount": a} for n, a in rows],
		**extra,
	})
	doc.insert(ignore_permissions=True)
	if validate:
		res = pcr_module().bulk_validate([doc.name])
		assert not res["failed"], res["failed"]
		doc.reload()
	return doc


def pcr_module():
	from erp.fico.doctype.pending_cash_refund import pending_cash_refund as pcr

	return pcr


def run():
	company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	bank = _bank(company)
	assert bank, f"Tidak ada Bank Account company untuk {company}"
	# Supplier SENDIRI: alokasinya FIFO ke seluruh kasbon party, jadi supplier yang
	# sudah punya kasbon lain di site ini membuat hasilnya tidak bisa ditebak.
	supplier = "UJI-REFUND-SUPPLIER"
	if not frappe.db.exists("Supplier", supplier):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier}).insert(ignore_permissions=True)
	account = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "root_type": "Asset",
		         "name": ("like", "%Uang Muka Pembelian%")},
		pluck="name", limit=1,
	)
	assert account, "Tidak ada akun Uang Muka Pembelian untuk diuji"
	account = account[0]

	docs, types = [], []
	try:
		t = _make_type("RFN", "Cash Outflow", account)
		types.append(t)
		# DUA kasbon supplier yang sama — inti ujinya: refund tidak lagi terikat satu kasbon.
		for _ in range(2):
			docs.append(_make_doc(t, company, bank["name"], pay_to=supplier))
		first, second = docs
		# Sengaja dibayar dari DRAFT (tanpa Validate lebih dulu): Pay ikut memvalidasi.
		res = pc.bulk_pay([d.name for d in docs])
		assert not res["failed"], res["failed"]
		for d in docs:
			d.reload()
			assert d.validated and d.validated_by, f"{d.name} tidak ikut ter-Validate saat Pay"
		paid_je = first.journal_entry

		from erp.fico.doctype.pending_cash_refund import pending_cash_refund as pcr

		# Sisa yang dipakai form mengisi baris = sisa yang dipakai validate menolak.
		info = pcr.row_info(first.name)
		assert flt(info["available"]) == TOTAL, info

		def _dropdown(chosen=None, exclude=""):
			"""Isi dropdown Pending Cash di tabel refund."""
			rows = pcr.open_pending_cash_query(
				"Pending Cash", "", "name", 0, 20,
				{"party_type": "Supplier", "party": supplier, "company": company,
				 "currency": None, "exclude": exclude, "chosen": chosen or []},
			)
			return [r[0] for r in rows]

		# Yang ditawarkan = kasbon Paid milik party ini yang sisanya masih ada.
		assert _dropdown() == [first.name, second.name], _dropdown()
		# Yang sudah dipilih di baris lain tidak ditawarkan lagi.
		assert _dropdown(chosen=[first.name]) == [second.name], _dropdown(chosen=[first.name])

		# --- satu refund menutup DUA kasbon, tanggal beda bulan --------------
		later = add_days(getdate(), 40)
		amount = TOTAL + TOTAL / 2  # kasbon pertama penuh, kasbon kedua separuh
		# Simpan dulu sebagai DRAFT: jurnalnya belum boleh ada.
		rf = _make_refund(
			supplier, bank["name"], company,
			[(first.name, TOTAL), (second.name, TOTAL / 2)], later, "kembalian", validate=False,
		)
		assert rf.name.startswith("RF/"), rf.name
		assert not rf.journal_entry, "draft seharusnya belum punya jurnal"
		assert not rf.validated, rf.validated
		print(f"Draft tanpa jurnal OK: {rf.name}")

		assert not pcr.bulk_validate([rf.name])["failed"]
		rf.reload()
		assert rf.journal_entry and rf.validated and rf.validated_by, rf.as_dict()
		# Refund Amount TURUNAN baris, bukan ketikan.
		assert flt(rf.amount) == amount, rf.amount

		alloc = {r.pending_cash: flt(r.amount) for r in rf.allocations}
		assert alloc.get(first.name) == TOTAL, alloc
		assert alloc.get(second.name) == TOTAL / 2, alloc
		print(f"Lintas kasbon OK: {rf.name} — Amount {rf.amount:,.0f} dari {alloc}")

		for d, expect in ((first, TOTAL), (second, TOTAL / 2)):
			d.reload()
			assert flt(d.refunded_amount) == expect, (d.name, d.refunded_amount)
		# Jurnal Paid TIDAK boleh ikut berubah/dibatalkan.
		assert first.journal_entry == paid_je, first.journal_entry
		assert frappe.db.get_value("Journal Entry", paid_je, "docstatus") == 1, "jurnal Paid ikut dibatalkan"

		# --- satu jurnal: baris uang muka per kasbon + SATU baris bank -------
		assert rf.journal_entry and rf.journal_entry != paid_je
		je = frappe.db.get_value("Journal Entry", rf.journal_entry, ["posting_date", "docstatus"], as_dict=True)
		assert getdate(je.posting_date) == getdate(later), je.posting_date
		assert je.docstatus == 1, "jurnal refund belum submit"
		rows = frappe.get_all(
			"Journal Entry Account",
			filters={"parent": rf.journal_entry},
			fields=["account", "debit", "credit", "party", "user_remark"],
		)
		bank_rows = [r for r in rows if r.account == bank["account"]]
		adv_rows = [r for r in rows if r.account == account]
		assert len(bank_rows) == 1, bank_rows
		# Kebalikan Cash Outflow: Dr Bank / Cr uang muka.
		assert flt(bank_rows[0].debit) == amount, bank_rows[0]
		assert len(adv_rows) == 2, adv_rows
		assert flt(sum(flt(r.credit) for r in adv_rows)) == amount, adv_rows
		assert {r.user_remark for r in adv_rows} == {first.name, second.name}, adv_rows
		assert {r.party for r in adv_rows} == {supplier}, adv_rows
		print(f"Jurnal OK: Dr {bank['account']} {amount:,.0f} / Cr {account} (2 baris) @ {later}")

		# --- Unpaid ditolak selama refund masih aktif ------------------------
		res = pc.bulk_unpaid([first.name])
		assert res["failed"], "Unpaid seharusnya ditolak selama ada refund aktif"
		print("guard unpaid OK")

		# --- tombol Refund di kasbonnya: alokasi DIPAKU ke kasbon itu --------
		res = pc.bulk_refund([second.name])
		assert not res["failed"], res["failed"]
		second.reload()
		assert flt(second.refunded_amount) == TOTAL, second.refunded_amount
		assert flt(pc.refund_available(second)) == 0, pc.refund_available(second)
		pinned = [r for r in _refunds(second.name) if r != rf.name]
		assert len(pinned) == 1, pinned
		pinned = frappe.get_doc("Pending Cash Refund", pinned[0])
		assert [r.pending_cash for r in pinned.allocations] == [second.name], pinned.allocations
		# Tombol Refund di kasbon membuat DRAFT — jurnalnya menyusul saat Validate.
		assert not pinned.journal_entry, "tombol Refund seharusnya tidak menerbitkan jurnal"
		assert not pcr.bulk_validate([pinned.name])["failed"]
		pinned.reload()
		print("Refund dari kasbon OK: " + pinned.name)

		# --- Void: sisa kembali, jurnal di-cancel TAPI tetap ada -------------
		pinned_je = pinned.journal_entry
		res = pcr.bulk_void([pinned.name])
		assert not res["failed"], res["failed"]
		second.reload()
		assert flt(second.refunded_amount) == TOTAL / 2, second.refunded_amount
		assert frappe.db.exists("Journal Entry", pinned_je), "jurnal refund void seharusnya disimpan"
		assert frappe.db.get_value("Journal Entry", pinned_je, "docstatus") == 2, "jurnal refund belum di-cancel"
		# Void tetap TAMPIL di tabel refund kasbonnya (dicoret) — jejaknya jangan hilang,
		# walau uangnya tidak lagi dihitung di refunded_amount.
		shown = {r.parent: r.void for r in pc.refund_rows(second.name)}
		assert shown.get(pinned.name) == 1, shown
		assert shown.get(rf.name) == 0, shown
		print("Void OK: " + pinned.name)

		# --- Invalidate: jurnalnya di-cancel LALU dihapus, balik ke Draft ----
		inv = _make_refund(supplier, bank["name"], company, [(second.name, TOTAL / 4)])
		inv_je = inv.journal_entry
		assert inv_je, "Validated seharusnya punya jurnal"
		assert not pcr.bulk_invalidate([inv.name])["failed"]
		inv.reload()
		assert not inv.journal_entry and not inv.validated, inv.as_dict()
		assert not frappe.db.exists("Journal Entry", inv_je), "jurnal Invalidate seharusnya DIHAPUS"
		second.reload()
		# Draft tetap memesan sisanya — dua draft tidak boleh mengklaim uang yang sama.
		assert flt(second.refunded_amount) == TOTAL / 2 + TOTAL / 4, second.refunded_amount
		frappe.delete_doc("Pending Cash Refund", inv.name, force=1, ignore_permissions=True)
		second.reload()
		assert flt(second.refunded_amount) == TOTAL / 2, second.refunded_amount
		print("Invalidate OK: jurnal dihapus, dokumen balik ke Draft")

		# --- refund sebagian, Amount tetap ikut baris ------------------------
		manual = _make_refund(supplier, bank["name"], company, [(second.name, TOTAL / 4)])
		assert flt(manual.amount) == TOTAL / 4, manual.amount
		# Kolom Outstanding di baris = sisa kasbon itu SEBELUM refund ini.
		assert flt(manual.allocations[0].outstanding) == TOTAL / 2, manual.allocations[0].outstanding
		second.reload()
		assert flt(second.refunded_amount) == TOTAL / 2 + TOTAL / 4, second.refunded_amount
		print(f"Refund sebagian OK: {manual.name} — Amount ikut baris {manual.amount:,.0f}")

		# Kasbon yang sisanya SUDAH HABIS hilang dari dropdown, bukan ditawarkan lalu ditolak.
		assert flt(pc.refund_available(first)) == 0, pc.refund_available(first)
		assert first.name not in _dropdown(), _dropdown()
		print("Dropdown OK: kasbon habis tidak ditawarkan lagi")

		# Melebihi sisa kasbonnya ditolak.
		try:
			_make_refund(supplier, bank["name"], company, [(second.name, TOTAL)])
			raise AssertionError("alokasi melebihi sisa kasbon seharusnya ditolak")
		except frappe.ValidationError:
			print("guard sisa per kasbon OK")

		# Refund bertanggal SEBELUM kasbonnya dibayar ditolak.
		try:
			_make_refund(supplier, bank["name"], company, [(second.name, TOTAL / 4)],
			             refund_date=add_days(getdate(), -30))
			raise AssertionError("refund mendahului Paid Date seharusnya ditolak")
		except frappe.ValidationError:
			print("guard refund date OK")

		# Tabel kosong ditolak: tidak ada lagi jalur "isi Amount saja".
		try:
			_make_refund(supplier, bank["name"], company, [])
			raise AssertionError("refund tanpa baris seharusnya ditolak")
		except frappe.ValidationError:
			print("guard tabel kosong OK")

		# --- arah kedua: refund kasbon Cash Inflow (party Customer) ----------
		# Sisinya HARUS terbalik dari refund Supplier: uang muka yang kita terima
		# dikembalikan, jadi bank berkurang.
		customer = frappe.get_all("Customer", pluck="name", limit=1)
		jaminan = frappe.get_all(
			"Account",
			filters={"company": company, "is_group": 0, "root_type": "Liability",
			         "name": ("like", "%Jaminan%")},
			pluck="name", limit=1,
		)
		if customer and jaminan:
			t_in = _make_type("RFNIN", "Cash Inflow", jaminan[0])
			types.append(t_in)
			d_in = _make_doc(t_in, company, bank["name"], receive_from=customer[0])
			docs.append(d_in)
			frappe.db.set_value("Pending Cash", d_in.name, "validated", 1)
			d_in.reload()
			assert not pc.bulk_pay([d_in.name])["failed"]
			d_in.reload()
			# Kasbon Inflow lain milik customer ini bisa saja sudah ada; yang diuji
			# arah jurnalnya, jadi refund-nya sebesar sisa kasbon INI saja lewat
			# tombol kasbonnya (alokasi dipaku).
			assert not pc.bulk_refund([d_in.name])["failed"]
			rf_in = frappe.get_doc("Pending Cash Refund", _refunds(d_in.name)[0])
			assert not pcr.bulk_validate([rf_in.name])["failed"]
			rf_in.reload()
			rows_in = _je_rows(rf_in.journal_entry)
			assert flt(rows_in[bank["account"]].credit) == TOTAL, rows_in[bank["account"]]
			assert flt(rows_in[jaminan[0]].debit) == TOTAL, rows_in[jaminan[0]]
			assert rf_in.party_type == "Customer" and rf_in.party == customer[0], rf_in.party
			print(f"Refund Cash Inflow OK: {rf_in.name} — Dr {jaminan[0]} / Cr {bank['account']}")
		else:
			print("LEWAT: tidak ada Customer / akun Jaminan untuk menguji arah Cash Inflow")

		# --- valas: uang muka dihapus di kurs BUKU, bank di kurs REFUND ------
		# Selisihnya untung/rugi kurs, dan tanpa barisnya jurnal tidak akan seimbang.
		fx_account = frappe.db.get_value("Company", company, "exchange_gain_loss_account")
		if fx_account and frappe.db.exists("Currency", "USD"):
			usd = _make_doc(t, company, bank["name"], pay_to=supplier,
			                currency="USD", exchange_rate=15000, total=1000)
			docs.append(usd)
			frappe.db.set_value("Pending Cash", usd.name, "validated", 1)
			usd.reload()
			assert not pc.bulk_pay([usd.name])["failed"]
			usd.reload()
			rf_fx = _make_refund(supplier, bank["name"], company, [(usd.name, 1000)],
			                     currency="USD", exchange_rate=16000)
			rows_fx = _je_rows(rf_fx.journal_entry)
			assert flt(rows_fx[bank["account"]].debit) == 16_000_000, rows_fx[bank["account"]]
			assert flt(rows_fx[account].credit) == 15_000_000, rows_fx[account]
			# Bank masuk lebih besar dari uang muka yang dihapus = untung kurs (dikredit).
			assert flt(rows_fx[fx_account].credit) == 1_000_000, rows_fx[fx_account]
			print(f"Selisih kurs OK: {rf_fx.name} — Dr Bank 16jt / Cr UM 15jt / Cr {fx_account} 1jt")
		else:
			print("LEWAT: Exchange Gain/Loss Account atau mata uang USD belum ada")

		print("PENDING CASH REFUND OK")
	finally:
		_drop_refunds([d.name for d in docs])
		_cleanup(docs, types)
		try:
			frappe.delete_doc("Supplier", supplier, force=1, ignore_permissions=True)
		except Exception as e:
			print("bersih-bersih supplier:", e)
		frappe.db.commit()

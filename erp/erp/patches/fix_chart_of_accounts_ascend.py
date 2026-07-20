"""Rapikan Chart of Accounts hasil migrasi dari Ascend (tabel AC_Accounts).

Sumber kebenaran = dump `ac_account.csv` dari Ascend AS_CIMI. Patch ini tidak membaca
CSV-nya (file itu tidak ikut ke server); daftar perubahannya sudah diturunkan jadi data
eksplisit di bawah supaya bisa direview dan hasilnya sama persis di semua site.

Empat masalah yang diperbaiki:

1. PARENT MENGGANTUNG. Abbr company pernah berubah, tapi sebagian baris di cabang Biaya
   masih menunjuk nama record lama ("5000.000 - Biaya - Biaya - PC") yang tidak pernah ada.
   Akibatnya ~157 akun biaya HILANG dari Chart of Accounts. Nested set (lft/rgt) sendiri
   masih benar, jadi laporan tetap jalan — yang rusak cuma link parent_account, dan itu
   yang dipakai UI untuk menggambar pohon. Karena lft/rgt utuh, perbaikannya cukup
   db.set_value tanpa perlu rebuild tree. Tidak semua site kena; yang tidak kena dilewati.

2. GRUP NON-PAJAK NYANGKUT DI "UANG MUKA PAJAK". Biaya Dibayar Dimuka, Asuransi Dibayar
   Dimuka, Uang Muka Pembelian, dan Klaim Dibayar Dimuka semuanya aktiva lancar biasa,
   bukan uang muka pajak. Cacat ini warisan Ascend, jadi muncul di semua site turunannya.
   Dipindah lewat doc.save() (BUKAN db.set_value) supaya nested set ikut dihitung ulang.

3. AKUN HILANG. Ada akun yang ada di Ascend tapi belum ada di ERPNext. account_type
   sengaja diambil dari saudara kandung, bukan dihardcode, supaya rekening bank otomatis
   dapat "Bank" dan ikut aturan ERPNext yang menempel di tipe itu.

4. NAMA SALAH / KEMBAR. Termasuk dua duplikat pajak (dua "PPN Masukan", dua "PPN Keluaran")
   dan pasangan Operasional/Admin Umum yang namanya identik sehingga tidak bisa dibedakan
   di dropdown.

PEMISAHAN PER ENTITAS — INI YANG PALING PENTING. Struktur CoA-nya dipakai bersama semua
badan usaha (semuanya clone template Ascend yang sama), TAPI daftar rekening bank itu milik
PT CMI. Site lain memakai CoA yang sama dengan rekening bank sendiri — mis. PT Oak Global
Maritim punya 1120.001/1120.002 dengan bank yang berbeda. Menyalin daftar bank CIMI ke sana
berarti menaruh rekening perusahaan lain di pembukuan mereka, dan rename 1120.002 akan
menimpa nama rekening asli mereka. Karena itu apa pun yang menyebut rekening bank tertentu
dibatasi ke COMPANY_WITH_CIMI_BANKS; sisanya jalan di semua company.

PENGAMAN LAIN: rename dan perubahan flag disabled DILEWATI kalau akunnya sudah punya GL
Entry — nomor akun yang sama bisa saja sudah dipakai untuk hal berbeda. Rename juga
dilewati kalau nama sekarang tidak cocok dengan nama yang diharapkan, supaya patch tidak
menimpa perubahan yang sudah dilakukan orang lain. Yang dilewati dicetak ke log, bukan
didiamkan.

TIDAK diperbaiki di sini, sengaja:
- 1180.000 "Piutang Hubungan Istimewa" is_group=0 padahal di Ascend grup. Mengubahnya
  menyentuh nested set dan tidak ada anaknya, jadi tidak mendesak.
- 1200.001 di sebagian site account_type-nya "Expense Account" padahal root_type Asset.
  Mengubah account_type mengubah perilaku posting, jadi perlu keputusan manual.
- Sufiks nama dokumen yang campur ("- PC" vs abbr sekarang). Kosmetik, dan menyentuh
  semua akun termasuk yang sudah ada GL-nya.

Idempoten: aman dijalankan berkali-kali, dan aman di site yang sebagian sudah beres.
"""

import frappe

from erpnext.accounts.doctype.account.account import update_account_number

# Company yang rekening banknya memang berasal dari Ascend AS_CIMI. Company lain memakai
# struktur CoA yang sama tapi rekening bank sendiri, jadi TIDAK boleh kebagian daftar ini.
# Kalau company-nya di-rename, blok bank cuma dilewati — itu memang mode gagal yang aman.
COMPANY_WITH_CIMI_BANKS = {"PT CMI"}

# Grup yang salah tempat: (nomor grup, nomor induk lama, nomor induk yang benar)
REPARENT = [
	("1210.000", "1200.000", "1100.000"),
	("1220.000", "1200.000", "1100.000"),
	("1230.000", "1200.000", "1100.000"),
	("1240.000", "1200.000", "1100.000"),
]

# Akun struktural yang ada di Ascend tapi belum ada di ERPNext. Bukan milik entitas
# tertentu, jadi aman untuk semua company.
# (nomor, nama, nomor induk, disabled, is_group)
MISSING_COMMON = [
	("1130.007", "Penyesuaian Persediaan", "1130.000", 1, 0),
	("1200.007", "PPh Ps 4 (2)", "1200.000", 1, 0),
	("1410.002", "Gedung", "1410.000", 1, 0),
	("3210.999", "Laba Ditahan TA", "3210.000", 1, 0),
	("4110.004", "Diskon Penjualan Oleo", "4110.000", 1, 0),
	("4140.003", "HPP Palm Kernel Shell", "4140.000", 1, 0),
	("5110.027", "Bi. Inap Supir", "5110.000", 0, 0),
	("5110.031", "Bi. Reimbursement", "5110.000", 1, 0),
	("5210.013", "Bi. Penyusutan - Mesin / Alat Berat", "5210.000", 1, 0),
	("5210.038", "Bi. STNK/BPKB (kantor)", "5210.000", 1, 0),
	("6110.005", "Lebih Bayar", "6110.000", 1, 0),
]

# Rekening bank milik PT CMI. HANYA untuk company di COMPANY_WITH_CIMI_BANKS.
MISSING_CIMI_BANKS = [
	("1120.004", "HSBC- 918 043324-074 (IDR)", "1120.000", 1, 0),
	("1120.005", "HSBC - 800 107492-117 (USD)", "1120.000", 1, 0),
	("1120.006", "DANAMON - 003 6131563 (IDR)", "1120.000", 0, 0),
	("1120.007", "MAYBANK - 2.208.551696", "1120.000", 0, 0),
	("1120.008", "BCA - 0222511851 (Surabaya)", "1120.000", 0, 0),
	("1120.009", "BCA - 0222426888 (USD)", "1120.000", 0, 0),
	("1120.010", "BCA - 0222416688 (IDR)", "1120.000", 1, 0),
	("1120.011", "HSBC - 800-065872-075 (IDR) (DML)", "1120.000", 1, 0),
	("1120.012", "HSBC - 800-065872-117 (USD) (DML)", "1120.000", 1, 0),
	("1120.013", "HSBC - 918.043324-117 (USD)", "1120.000", 1, 0),
	("1120.014", "HSBC - 918.043324-900 (IDR)", "1120.000", 1, 0),
	("1120.015", "DEPOSITO (BTPN IDR)", "1120.000", 0, 0),
	("1120.016", "BCA - 806-0303810 (IDR)", "1120.000", 0, 0),
	("1120.017", "BCA - 0224270808 (IDR - RH)-pulsa", "1120.000", 0, 0),
	("1120.018", "HSBC - 918.043324-901 (IDR)", "1120.000", 1, 0),
	("1120.019", "HSBC - 918 043324-075 (IDR)", "1120.000", 1, 0),
	("1120.020", "MDR - 1680001650850 (IDR) (Master)", "1120.000", 0, 0),
	("1120.021", "MDR - 1680091650851 (IDR) (JKT)", "1120.000", 0, 0),
	("1120.022", "MDR - 1680019690856 (IDR) (Pengurus)", "1120.000", 0, 0),
	("1120.023", "MDR - 1680081650853 (IDR) (SBY)", "1120.000", 0, 0),
	("1120.024", "MDR - 1680012340855 (IDR) (MDN)", "1120.000", 0, 0),
	("1120.025", "MDR - 1680034560852 (IDR) (Pengurus)", "1120.000", 0, 0),
	("1120.026", "BCA - 1958688899 IDR PT (Kredit)", "1120.000", 0, 0),
	("1120.027", "BCA - 1951959885 PT Medan", "1120.000", 0, 0),
	("1120.028", "BCA - 1958098889 PT", "1120.000", 1, 0),
	("1120.029", "BCA - 806-0303801 PT (IDR)", "1120.000", 0, 0),
	("1120.030", "BTPN - 04513001539 (IDR)", "1120.000", 0, 0),
	("1120.031", "BTPN - 00263007603  (IDR)", "1120.000", 0, 0),
]

# (nomor, nama sekarang yang diharapkan, nama baru, alasan)
# Nama lama ikut dicocokkan supaya patch tidak menimpa perubahan orang lain.
RENAMES_COMMON = [
	("1200.001", "PPN Masukan", "PPh Ps 21 karyawan", "duplikat 1200.005 PPN Masukan"),
	("2120.011", "PPN Keluaran", "PPh Ps 15", "duplikat 2120.006 PPN Keluaran"),
	("5210.043", "Bi. Pemeliharaan & Perbaikan Alat Lapang", "Bi. Pemeliharaan & Perbaikan Alat Lapangan", "nama terpotong"),
	("5110.018", "Bi. Gaji Freelance", "Bi. Gaji Freelance (Operasional)", "kembar dengan 5210.060"),
	("5210.060", "Bi. Gaji Freelance", "Bi. Gaji Freelance (Admin Umum)", "kembar dengan 5110.018"),
	("5110.050", "Bi. Pulsa/Voucher", "Bi. Pulsa/Voucher (Operasional)", "kembar dengan 5210.023"),
	("5210.023", "Bi. Pulsa/Voucher", "Bi. Pulsa/Voucher (Admin Umum)", "kembar dengan 5110.050"),
]

# Rename yang menyebut rekening bank tertentu. Nomor 1120.002/1120.003 dipakai company lain
# untuk bank yang BERBEDA, jadi ini HANYA untuk COMPANY_WITH_CIMI_BANKS.
RENAMES_CIMI_BANKS = [
	("1120.002", "BCA 5212569623", "BCA - Indah- 022140038 (USD)", "nama tidak sesuai Ascend"),
	("1120.003", "MDR 167-00-0792787-3", "BCA - Rusman - 8280070808 (IDR)", "kembar dengan 1120.001"),
]

# Akun yang di Ascend sudah tidak dipakai. (nomor, nama yang diharapkan)
TO_DISABLE = [
	("5110.066", "Bi. Pengiriman Barang"),
	("5110.069", "Bi. Materai"),
	("5110.070", "Bi. Kesehatan"),
	("5110.073", "Bi. Inap Supir"),
	("5110.074", "Bi. Perjalanan Dinas Teknisi"),
	("5210.020", "Bi. Kirim Dokumen"),
	("5210.025", "Bi. BBM Kendaraan (Admin Umum)"),
	("5210.029", "Bi. Perjalanan Dinas"),
	("5210.069", "Bi. Parkir & Tol (Admin Umum)"),
	("6210.004", "Selisih Pembayaran Customer"),
]


def execute():
	for company in frappe.get_all("Company", pluck="name"):
		_fix_company(company)
	frappe.db.commit()


def _fix_company(company):
	log = lambda msg: print("[coa:%s] %s" % (company, msg))

	# nomor akun unik per company, jadi peta ini cukup untuk semua lookup di bawah
	num2name = dict(
		frappe.get_all(
			"Account",
			filters={"company": company, "account_number": ["!=", ""]},
			fields=["account_number", "name"],
			as_list=True,
		)
	)
	if not num2name:
		return

	gl_count = dict(
		frappe.db.sql(
			"""select account, count(*) from `tabGL Entry`
			   where company = %s and is_cancelled = 0 group by account""",
			company,
		)
	)

	cimi_banks = company in COMPANY_WITH_CIMI_BANKS
	if not cimi_banks:
		log("bukan pemilik rekening Ascend CIMI - blok bank dilewati")

	missing = MISSING_COMMON + (MISSING_CIMI_BANKS if cimi_banks else [])
	renames = RENAMES_COMMON + (RENAMES_CIMI_BANKS if cimi_banks else [])

	_fix_dangling_parents(company, log)
	_reparent_groups(company, num2name, log)
	_add_missing(company, num2name, missing, log)
	_rename(company, num2name, gl_count, renames, log)
	_disable(company, num2name, gl_count, log)


def _fix_dangling_parents(company, log):
	"""parent_account menunjuk record yang tidak ada -> arahkan ke root yang benar."""
	rows = frappe.get_all(
		"Account", filters={"company": company}, fields=["name", "parent_account"]
	)
	existing = {r.name for r in rows}
	for r in rows:
		if not r.parent_account or r.parent_account in existing:
			continue
		# nama record berpola "<nomor> - <nama> - <abbr>", jadi nomornya ada di depan
		num = r.parent_account.split(" - ")[0].strip()
		target = frappe.db.get_value(
			"Account", {"company": company, "account_number": num}, "name"
		)
		if not target:
			log("LEWAT parent menggantung %s -> %s (induk tidak ketemu)" % (r.name, r.parent_account))
			continue
		# lft/rgt sudah benar, cuma link-nya yang basi -> set_value cukup
		frappe.db.set_value("Account", r.name, "parent_account", target, update_modified=False)
		log("parent diperbaiki: %s -> %s" % (r.name, target))


def _reparent_groups(company, num2name, log):
	for num, old_parent_num, new_parent_num in REPARENT:
		name = num2name.get(num)
		new_parent = num2name.get(new_parent_num)
		if not name or not new_parent:
			continue
		doc = frappe.get_doc("Account", name)
		if doc.parent_account == new_parent:
			continue
		if doc.parent_account != num2name.get(old_parent_num):
			log("LEWAT pindah %s (induknya %s, bukan yang diharapkan)" % (num, doc.parent_account))
			continue
		doc.parent_account = new_parent
		doc.save(ignore_permissions=True)  # save() -> nested set ikut dihitung ulang
		log("pindah %s %s -> %s" % (num, doc.account_name, new_parent))


def _add_missing(company, num2name, missing, log):
	for num, acc_name, parent_num, disabled, is_group in missing:
		if num in num2name:
			continue
		parent = num2name.get(parent_num)
		if not parent:
			log("LEWAT tambah %s %s (induk %s tidak ada)" % (num, acc_name, parent_num))
			continue
		parent_doc = frappe.db.get_value("Account", parent, ["root_type"], as_dict=True)
		# tipe diambil dari saudara kandung supaya rekening bank dapat "Bank" dsb
		sibling_type = frappe.db.get_value(
			"Account",
			{"parent_account": parent, "is_group": 0, "account_type": ["!=", ""]},
			"account_type",
		)
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": acc_name,
				"account_number": num,
				"parent_account": parent,
				"company": company,
				"is_group": is_group,
				"root_type": parent_doc.root_type,
				"account_type": sibling_type or None,
				"disabled": disabled,
			}
		)
		doc.insert(ignore_permissions=True)
		num2name[num] = doc.name
		log("tambah %s %s (induk %s, tipe %s)" % (num, acc_name, parent_num, sibling_type or "-"))


def _rename(company, num2name, gl_count, renames, log):
	for num, expected, new_name, reason in renames:
		name = num2name.get(num)
		if not name:
			continue
		current = frappe.db.get_value("Account", name, "account_name")
		if current == new_name:
			continue
		if current != expected:
			log("LEWAT rename %s: nama sekarang %r, diharapkan %r" % (num, current, expected))
			continue
		if gl_count.get(name):
			log("LEWAT rename %s: sudah punya %d GL Entry" % (num, gl_count[name]))
			continue
		update_account_number(name, new_name, account_number=num)
		num2name[num] = frappe.db.get_value(
			"Account", {"company": company, "account_number": num}, "name"
		)
		log("rename %s: %s -> %s (%s)" % (num, current, new_name, reason))


def _disable(company, num2name, gl_count, log):
	for num, expected in TO_DISABLE:
		name = num2name.get(num)
		if not name:
			continue
		row = frappe.db.get_value("Account", name, ["account_name", "disabled"], as_dict=True)
		if row.disabled:
			continue
		if row.account_name != expected:
			log("LEWAT disable %s: nama sekarang %r, diharapkan %r" % (num, row.account_name, expected))
			continue
		if gl_count.get(name):
			log("LEWAT disable %s: sudah punya %d GL Entry" % (num, gl_count[name]))
			continue
		frappe.db.set_value("Account", name, "disabled", 1, update_modified=False)
		log("disable %s %s" % (num, row.account_name))

"""Alur Validate / Invalidate / Void / Unvoid untuk transaksi CMI.

Satu mesin state untuk enam doctype, supaya aturannya tidak tersebar dan tidak
saling berbeda:

    Sales Invoice, Purchase Invoice, Purchase Order, Purchase Receipt,
    Payment Entry                                                  -> docstatus
    Expense Note, Pending Cash                                      -> checkbox

KENAPA DUA JALUR
----------------
Keempat doctype pertama adalah doctype INTI ERPNext, yang memakai `docstatus` dan
sifatnya SATU ARAH: draft(0) -> submitted(1) -> cancelled(2). Frappe tidak
menyediakan jalan kembali. Padahal alur yang diminta menuntut Invalidate
(submitted -> draft) dan Unvoid (cancelled -> draft).

Karena itu kembalinya DIPAKSA: dokumen di-cancel lewat jalur resmi (supaya GL
benar-benar dibalik), lalu docstatus dikembalikan ke 0 dan sisa GL/Payment Ledger
dibersihkan sehingga dokumen kembali seperti draft. Nomor dokumen tetap.

Ini melawan asumsi framework, jadi PENJAGAANNYA KETAT (lihat _assert_no_dependents):
dokumen yang sudah dirujuk Payment Entry, retur, atau dokumen lain TIDAK boleh
di-invalidate/unvoid. Membiarkannya lewat akan meninggalkan referensi menggantung
dan angka AR/AP yang salah -- kerusakan yang jauh lebih mahal daripada memaksa
user membatalkan dokumen perujuknya dulu.

Expense Note dan Pending Cash tidak punya masalah itu: keduanya doctype custom
yang memakai checkbox, jadi bebas bolak-balik dan jurnalnya dikelola sendiri.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, today

# ---------------------------------------------------------------- roles

ROLE_VALIDATE = "Transaction Validate"
ROLE_INVALIDATE = "Transaction Invalidate"
ROLE_VOID = "Transaction Void"
ROLE_UNVOID = "Transaction Unvoid"
# Close/Open hanya untuk modul utama (CLOSABLE): menutup dokumen dari tarikan transaksi
# berikutnya tanpa membatalkannya -- angkanya tetap dihitung, beda dengan Void.
ROLE_CLOSE = "Transaction Close"
ROLE_OPEN = "Transaction Open"

WORKFLOW_ROLES = (ROLE_VALIDATE, ROLE_INVALIDATE, ROLE_VOID, ROLE_UNVOID, ROLE_CLOSE, ROLE_OPEN)

# Role lama khusus invoice tetap dihormati supaya user yang sudah punya izin tidak
# kehilangan akses saat fitur ini dipasang.
LEGACY_EQUIVALENT = {
	ROLE_VALIDATE: ("Invoice Validate",),
	ROLE_VOID: ("Invoice Void",),
}


def _has_role(role):
	allowed = {role, "System Manager"} | set(LEGACY_EQUIVALENT.get(role, ()))
	return bool(set(frappe.get_roles()) & allowed)


# ---------------------------------------------------------------- izin per doctype

# Doctype di bawah ini izinnya diatur PER DOCTYPE lewat Role Permission Manager,
# bukan lewat role global. Dua kolom native dipakai apa adanya karena artinya memang
# sama persis dengan sepasang aksi di sini:
#
#     kolom Submit  ->  boleh Validate  dan  Invalidate
#     kolom Cancel  ->  boleh Void      dan  Unvoid
#
# Kolom baru bernama "Validate"/"Void" tidak mungkin ditambahkan: daftar hak akses
# itu kolom tetap di doctype DocPerm milik Frappe. Menumpang pada Submit/Cancel
# membuat pengaturannya tetap di satu tempat yang sudah dikenal admin, dan otomatis
# bisa berbeda antara Purchase Order, Purchase Receipt, dan Purchase Invoice.
PERM_GATED = ("Purchase Order", "Purchase Receipt", "Purchase Invoice")

_PTYPE = {
	ROLE_VALIDATE: "submit",
	ROLE_INVALIDATE: "submit",
	ROLE_VOID: "cancel",
	ROLE_UNVOID: "cancel",
}


# ---------------------------------------------------------------- izin per doctype + role

# ERPNext Custom Setting > Workflow Access: baris (doctype, role, centang per aksi).
ACCESS_DOCTYPE = "CMI Workflow Access"

ACTION_ROLE = {
	"validate": ROLE_VALIDATE,
	"invalidate": ROLE_INVALIDATE,
	"void": ROLE_VOID,
	"unvoid": ROLE_UNVOID,
	"close": ROLE_CLOSE,
	"open": ROLE_OPEN,
}
ROLE_ACTION = {v: k for k, v in ACTION_ROLE.items()}


def _access_rows(doctype):
	cache = getattr(frappe.local, "cmi_wf_access", None)
	if cache is None:
		cache = frappe.local.cmi_wf_access = {}
		if frappe.db.table_exists(ACCESS_DOCTYPE):
			for r in frappe.get_all(
				ACCESS_DOCTYPE,
				filters={"parenttype": "ERPNext Custom Setting"},
				fields=["document_type", "role", *(f"can_{a}" for a in ACTION_ROLE)],
			):
				cache.setdefault(r.document_type, []).append(r)
	return cache.get(doctype)


def can(doctype, action):
	"""Boleh user ini melakukan `action` (validate/invalidate/void/unvoid/close/open) di doctype ini?

	1. Doctype punya baris di Workflow Access -> salah satu role user harus dicentang di aksi itu.
	2. Belum punya baris -> aturan lama: PO/PR/PI kolom Submit/Cancel Role Permission Manager,
	   doctype lain role global Transaction *. Dengan begitu memasang tabel ini tidak mengunci
	   siapa pun sampai admin mulai mengisinya per doctype.
	System Manager selalu boleh.
	"""
	roles = set(frappe.get_roles())
	if "System Manager" in roles:
		return True
	rows = _access_rows(doctype)
	if rows:
		return any(r.role in roles and r.get(f"can_{action}") for r in rows)
	role = ACTION_ROLE[action]
	if doctype in PERM_GATED and role in _PTYPE:
		return bool(frappe.has_permission(doctype, _PTYPE[role]))
	return _has_role(role)


def _assert_action(doctype, role, action):
	"""Gerbang semua aksi workflow (lihat can())."""
	if can(doctype, ROLE_ACTION[role]):
		return
	frappe.throw(
		_("Anda tidak punya izin <b>{0}</b> di {1}, jadi tidak boleh {2}. "
		  "Atur di ERPNext Custom Setting > Workflow Access.").format(
			_(ROLE_ACTION[role].title()), _(doctype), action),
		frappe.PermissionError,
	)


# ---------------------------------------------------------------- doctypes

# Doctype berbasis docstatus yang submit/cancel bawaannya DITOLAK TOTAL: harus lewat
# tombol CMI (guard_submit/guard_cancel).
STRICT = (
	"Sales Invoice",
	"Purchase Invoice",
	"Purchase Order",
	"Purchase Receipt",
	"Payment Entry",
	"Sales Order",
)

# Doctype berbasis docstatus yang JUGA dibuat & di-submit oleh kode (Stock Entry milik
# sparepart, Stock Reconciliation milik Bin Adjustment, jurnal Expense Note/Pending Cash,
# ...). Penjaga ketat di atas akan mematikan jalur otomatis itu, jadi di sini yang ditolak
# hanya submit/cancel yang diklik user di desk untuk dokumen itu sendiri (guard_native).
NATIVE = (
	"Delivery Note",
	"Stock Entry",
	"Stock Reconciliation",
	"Pick List",
	"Goods Receive",
	"Bin Replan",
	"Bin Adjustment",
	"Journal Entry",
	"Mutation",
	"Tire On Off",
	"Vulkanisir Request",
	"Driver Reward",
	"Driver Slipgaji",
)

SUBMITTABLE = STRICT + NATIVE

# Dokumen stok: TIDAK ada Invalidate/Unvoid. Memaksa dokumen kembali ke draft berarti
# menghapus Stock Ledger-nya, padahal valuasi FIFO transaksi sesudahnya dihitung di atas
# baris itu -- nilai persediaan jadi salah tanpa pesan apa pun. Revisi = Void lalu buat baru.
NO_REVERT = (
	"Delivery Note",
	"Stock Entry",
	"Stock Reconciliation",
	"Pick List",
	"Goods Receive",
	"Bin Replan",
	"Bin Adjustment",
)

# Doctype berbasis checkbox (custom, app erp).
CHECKBOX = ("Expense Note", "Pending Cash", "Maintenance", "CRM Estimation")

# Master Job: TANPA Validate. Begitu dibuat langsung boleh ditarik transaksi berikutnya
# selama tidak Closed dan tidak Void (lihat pull_guard).
MASTER_JOB = ("Shipping List", "Packing List")

# Modul utama yang punya Close/Open. Sales Order memakai status Closed bawaan ERPNext.
CLOSABLE = ("Sales Order",) + MASTER_JOB

SUPPORTED = SUBMITTABLE + CHECKBOX + MASTER_JOB

# Doctype yang TIDAK menghasilkan jurnal sama sekali.
NO_JOURNAL = ("Purchase Order", "Sales Order")

# Sudah punya tombol/list action sendiri (file JS per doctype). Sisanya dipasang generik
# oleh workflow_auto.js dari konfigurasi boot().
WIRED = (
	"Sales Invoice",
	"Purchase Invoice",
	"Purchase Order",
	"Purchase Receipt",
	"Payment Entry",
	"Expense Note",
	"Pending Cash",
	"Maintenance",
	"CRM Estimation",
)


def _assert_supported(doctype):
	if doctype not in SUPPORTED:
		frappe.throw(_("Alur Validate/Void tidak berlaku untuk {0}.").format(doctype))


def _get(doctype, name):
	_assert_supported(doctype)
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} tidak ditemukan.").format(doctype, name))
	if not frappe.has_permission(doctype, "write", name):
		frappe.throw(_("Tidak boleh mengubah {0} ini.").format(doctype), frappe.PermissionError)
	doc = frappe.get_doc(doctype, name)
	# Jurnal otomatis (Expense Note, Pending Cash, depresiasi, ...) milik dokumen sumbernya:
	# membatalkannya langsung membuat sumbernya mengira jurnalnya masih ada.
	if doctype == "Journal Entry" and doc.get("is_system_generated"):
		frappe.throw(_("{0} adalah jurnal otomatis. Kelola lewat dokumen sumbernya.").format(name))
	# Gerbangnya sudah dijaga dua lapis di atas: _assert_action (role global, atau
	# izin Submit/Cancel per doctype untuk PERM_GATED) + izin write dokumen. Flag ini
	# perlu karena di Sales Invoice izin submit/cancel DICABUT dari semua role
	# (_revoke_submit_cancel) supaya tombol bawaannya hilang — tanpa flag,
	# doc.submit() di sana jatuh ke izin yang barusan dicabut dan hanya Administrator
	# yang bisa Validate.
	doc.flags.ignore_permissions = True
	return doc


# ---------------------------------------------------------------- guards


def _assert_no_dependents(doc):
	"""Tolak invalidate/unvoid bila dokumen masih dirujuk dokumen lain.

	Tanpa ini, memaksa docstatus kembali ke draft akan meninggalkan Payment Entry
	(atau retur) yang menunjuk dokumen yang secara akuntansi sudah tidak ada --
	saldo AR/AP jadi salah dan tidak ada pesan error apa pun.
	"""
	dt, name = doc.doctype, doc.name

	if dt in ("Sales Invoice", "Purchase Invoice"):
		refs = frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": dt, "reference_name": name, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)
		if refs:
			frappe.throw(
				_("Batalkan dulu Payment Entry yang merujuk dokumen ini: {0}").format(", ".join(refs))
			)

		returns = frappe.get_all(
			dt, filters={"return_against": name, "docstatus": ["!=", 2]}, pluck="name"
		)
		if returns:
			frappe.throw(_("Batalkan dulu retur terkait: {0}").format(", ".join(returns)))

	if dt == "Purchase Order":
		bills = frappe.get_all(
			"Purchase Invoice Item",
			filters={"purchase_order": name, "docstatus": ["!=", 2]},
			pluck="parent",
			distinct=True,
		)
		if bills:
			frappe.throw(_("Batalkan dulu Purchase Invoice terkait: {0}").format(", ".join(bills)))

	if dt == "Purchase Receipt":
		bills = frappe.get_all(
			"Purchase Invoice Item",
			filters={"purchase_receipt": name, "docstatus": ["!=", 2]},
			pluck="parent",
			distinct=True,
		)
		if bills:
			frappe.throw(_("Batalkan dulu Purchase Invoice terkait: {0}").format(", ".join(bills)))

		returns = frappe.get_all(
			"Purchase Receipt",
			filters={"return_against": name, "docstatus": ["!=", 2]},
			pluck="name",
		)
		if returns:
			frappe.throw(_("Batalkan dulu Purchase Return terkait: {0}").format(", ".join(returns)))

	if dt == "Sales Order":
		# Cancel bawaan memang menolak dokumen turunan yang SUDAH submit, tapi draft lolos --
		# dan Invalidate memasang ignore_links. Draft DN/SI/Pick List/Pending Cash pun sudah
		# "mengklaim" SO ini, jadi semuanya dicek di sini.
		refs = []
		for child, field in (
			("Delivery Note Item", "against_sales_order"),
			("Sales Invoice Item", "sales_order"),
			("Pick List Item", "sales_order"),
		):
			refs += frappe.get_all(
				child, filters={field: name, "docstatus": ["!=", 2]}, pluck="parent", distinct=True
			)
		refs += frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": dt, "reference_name": name, "docstatus": ["!=", 2]},
			pluck="parent",
			distinct=True,
		)
		refs += frappe.get_all(
			"Pending Cash", filters={"modul": dt, "number": name, "void": 0}, pluck="name"
		)
		if refs:
			frappe.throw(_("Batalkan dulu dokumen turunan Sales Order ini: {0}").format(
				", ".join(sorted(set(refs)))))

	if dt == "Sales Invoice":
		# Expense Note reimburse yang sudah ditarik ke invoice ini.
		ens = frappe.get_all(
			"Expense Note", filters={"reimburse_invoice": name}, pluck="name"
		) if frappe.get_meta("Expense Note").has_field("reimburse_invoice") else []
		if ens:
			frappe.throw(_("Lepaskan dulu Expense Note reimburse terkait: {0}").format(", ".join(ens)))


def _assert_revalidatable(doc):
	"""Tolak Invalidate/Unvoid bila dokumen tidak akan bisa divalidasi ulang.

	Dokumen lama dibuat di bawah aturan validasi LAMA. Aturan hari ini bisa lebih
	ketat (field yang dulu opsional kini wajib). Kalau kita paksa dokumen seperti itu
	kembali ke draft, jurnalnya terhapus tapi ia TIDAK BISA divalidasi ulang -- dan
	tidak ada jalan memulihkannya lewat UI. Nilainya hilang dari pembukuan diam-diam.

	Terbukti nyata saat pengujian: sebuah invoice Rp 4,9 juta terjebak sebagai draft
	tanpa jurnal karena field custom_customer_address baru diwajibkan belakangan.

	Jadi validasi dijalankan DULU pada salinan di memori. Kalau gagal, batalkan aksi
	dan sampaikan apa yang kurang -- dokumen aslinya tidak disentuh sama sekali.
	"""
	# Beberapa controller ERPNext tidak murni saat `validate()`. Payment Entry,
	# misalnya, memanggil set_status() -> db_set(update_modified=True). Tanpa isolasi,
	# probe ini mengubah timestamp dokumen asli lalu doc.cancel() di bawahnya gagal
	# dengan TimestampMismatchError. Savepoint memastikan SEMUA write dari probe
	# dibatalkan, baik validasinya berhasil maupun gagal.
	savepoint = "cmi_revalidatable_probe"
	frappe.db.savepoint(savepoint)
	try:
		probe = frappe.get_doc(doc.doctype, doc.name)
		probe.docstatus = 0  # tiru keadaan draft
		probe._action = "save"
		# Untuk Payment Entry, outstanding reference saat ini sudah dikurangi oleh
		# Payment Ledger milik PE ITU SENDIRI. Hapus ledger-nya hanya di dalam
		# savepoint agar probe melihat keadaan nyata SESUDAH Invalidate; rollback
		# di bawah akan mengembalikan ledger asli sebelum aksi sesungguhnya dimulai.
		if doc.doctype == "Payment Entry":
			for ledger in ("GL Entry", "Payment Ledger Entry"):
				if frappe.db.exists("DocType", ledger):
					frappe.db.delete(
						ledger,
						{"voucher_type": doc.doctype, "voucher_no": doc.name},
					)
			# Sisa Purchase/Sales Order TIDAK berasal dari ledger, melainkan field tersimpan
			# `advance_paid` di dokumen order -- dan field itu baru dihitung ulang oleh
			# set_total_advance_paid() saat submit/cancel SUNGGUHAN. Kalau tidak ikut
			# dinetralkan di sini, order terlihat "uang mukanya sudah lunas oleh PE ini
			# sendiri" dan probe SELALU gagal dengan "Allocated Amount cannot be greater
			# than outstanding amount" -- alarm palsu yang memblokir setiap PE pembayar
			# uang muka order. Perubahan ini ikut di-rollback bersama savepoint.
			for ref in doc.get("references") or []:
				if ref.reference_doctype in ("Purchase Order", "Sales Order") and ref.reference_name:
					paid = flt(frappe.db.get_value(
						ref.reference_doctype, ref.reference_name, "advance_paid"
					))
					frappe.db.set_value(
						ref.reference_doctype, ref.reference_name, "advance_paid",
						max(paid - flt(ref.allocated_amount), 0), update_modified=False,
					)
		probe.run_method("validate")
		probe._validate_mandatory()
	except Exception as e:
		frappe.db.rollback(save_point=savepoint)
		frappe.throw(
			_(
				"{0} tidak bisa dikembalikan ke draft: dokumen ini tidak lolos aturan validasi "
				"yang berlaku sekarang, sehingga tidak akan bisa divalidasi ulang.<br><br>"
				"Penyebab: {1}<br><br>"
				"Perbaiki dulu datanya, atau biarkan dokumen ini sebagaimana adanya."
			).format(doc.name, str(e)[:300])
		)
	else:
		frappe.db.rollback(save_point=savepoint)


def _clear_ledgers(doc):
	"""Bersihkan jejak buku besar supaya dokumen benar-benar kembali seperti draft.

	doc.cancel() sudah membalik GL (entri reversal), jadi secara akuntansi sudah nol.
	Tapi baris-barisnya tetap ada dan membuat dokumen 'draft' ini tetap muncul di
	laporan. Karena Invalidate/Unvoid memang bermaksud mengembalikan dokumen ke
	keadaan belum pernah diposting, jejaknya dihapus.
	"""
	if doc.doctype in NO_JOURNAL:
		return
	for ledger in ("GL Entry", "Payment Ledger Entry"):
		if frappe.db.exists("DocType", ledger):
			frappe.db.delete(ledger, {"voucher_type": doc.doctype, "voucher_no": doc.name})
	if doc.doctype == "Purchase Receipt" and frappe.db.exists("DocType", "Stock Ledger Entry"):
		frappe.db.delete(
			"Stock Ledger Entry",
			{"voucher_type": doc.doctype, "voucher_no": doc.name},
		)


def _force_to_draft(doc):
	"""Kembalikan parent dan seluruh child row ke Draft tanpa API framework.

	Cancel mengubah parent DAN child menjadi docstatus 2 serta status Payment Entry
	menjadi "Cancelled". Mengubah parent saja menghasilkan dokumen setengah Draft:
	badge/status masih Cancelled dan child table masih cancelled.
	"""
	values = {"docstatus": 0}
	if frappe.get_meta(doc.doctype).has_field("status"):
		values["status"] = "Draft"
	frappe.db.set_value(doc.doctype, doc.name, values, update_modified=False)

	for table_field in frappe.get_meta(doc.doctype).get_table_fields():
		child = frappe.qb.DocType(table_field.options)
		(
			frappe.qb.update(child)
			.set(child.docstatus, 0)
			.where(child.parent == doc.name)
			.where(child.parenttype == doc.doctype)
		).run()

	_clear_ledgers(doc)
	frappe.db.commit()


def _force_to_cancelled(doc):
	"""Kebalikan _force_to_draft: parent + seluruh child row jadi docstatus 2.

	Dipakai untuk Void dokumen yang MASIH DRAFT. `cancel()` menolak dokumen yang belum
	submit, dan submit-lalu-cancel akan membuat lalu membalik jurnal yang seharusnya tidak
	pernah ada. Draft belum pernah diposting, jadi tidak ada ledger yang perlu dibersihkan --
	yang berubah cuma penanda batalnya.
	"""
	values = {"docstatus": 2}
	if frappe.get_meta(doc.doctype).has_field("status"):
		values["status"] = "Cancelled"
	frappe.db.set_value(doc.doctype, doc.name, values, update_modified=False)

	for table_field in frappe.get_meta(doc.doctype).get_table_fields():
		child = frappe.qb.DocType(table_field.options)
		(
			frappe.qb.update(child)
			.set(child.docstatus, 2)
			.where(child.parent == doc.name)
			.where(child.parenttype == doc.doctype)
		).run()
	frappe.db.commit()


def _audit(doc, **values):
	"""Isi field audit bila doctype-nya punya (tidak semua doctype punya semuanya)."""
	meta = frappe.get_meta(doc.doctype)
	payload = {k: v for k, v in values.items() if meta.has_field(k)}
	if payload:
		doc.db_set(payload, update_modified=False)


# ---------------------------------------------------------------- actions


@frappe.whitelist()
def validate_doc(doctype, name):
	"""Validate: dokumen diposting. Untuk doctype ber-docstatus = submit (jurnal
	terbentuk); untuk Expense Note / Pending Cash = centang `validated`.

	Pending Cash SENGAJA belum membuat jurnal saat validate -- jurnalnya baru
	terbentuk saat Paid (lihat mark_paid).
	"""
	_assert_action(doctype, ROLE_VALIDATE, _("memvalidasi dokumen"))
	_assert_has_validate(doctype)
	doc = _get(doctype, name)

	if doctype in SUBMITTABLE:
		if doc.docstatus == 1:
			frappe.throw(_("{0} sudah tervalidasi.").format(name))
		if doc.docstatus == 2:
			frappe.throw(_("{0} sudah di-void. Pakai Unvoid dulu.").format(name))
		doc.flags.cmi_action_ok = True
		doc.submit()
		_audit(doc, custom_validated_by=frappe.session.user)
		return {"ok": True, "status": "Validated"}

	# checkbox (Expense Note / Pending Cash)
	if doc.get("void"):
		frappe.throw(_("{0} sedang void. Pakai Unvoid dulu.").format(name))
	if doc.get("validated"):
		frappe.throw(_("{0} sudah tervalidasi.").format(name))
	doc.validated = 1
	doc.flags.cmi_action_ok = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "status": "Validated"}


@frappe.whitelist()
def invalidate_doc(doctype, name):
	"""Invalidate: kembalikan dokumen tervalidasi ke draft, jurnalnya dihapus."""
	_assert_action(doctype, ROLE_INVALIDATE, _("membatalkan validasi"))
	_assert_has_validate(doctype)
	_assert_revertible(doctype)
	doc = _get(doctype, name)

	if doctype in SUBMITTABLE:
		if doc.docstatus != 1:
			frappe.throw(_("Hanya dokumen tervalidasi yang bisa di-invalidate."))
		_assert_no_dependents(doc)
		_assert_revalidatable(doc)
		doc.flags.cmi_action_ok = True
		# Penanda untuk handler before_cancel: ini Invalidate, BUKAN Void. Dokumen
		# turunan yang ikut mundur boleh kembali ke keadaan belum divalidasi, bukan
		# ditandai batal (lihat sparepart.cancel_issue_before_cancel).
		doc.flags.cmi_invalidate = True
		# Hanya STRICT yang punya _assert_no_dependents lengkap (termasuk draft). Doctype
		# NATIVE mengandalkan cek tautan bawaan cancel, jadi jangan dimatikan.
		doc.flags.ignore_links = doctype in STRICT
		doc.cancel()  # jalur resmi -> GL dibalik dengan benar
		_force_to_draft(doc)
		_audit(doc, custom_validated_by=None, custom_voided_by=None)
		doc.add_comment("Comment", _("INVALIDATE oleh {0}").format(frappe.session.user))
		return {"ok": True, "status": "Draft"}

	if not doc.get("validated"):
		frappe.throw(_("{0} belum tervalidasi.").format(name))
	if doc.get("paid"):
		frappe.throw(_("{0} sudah Paid. Batalkan status Paid dulu.").format(name))
	doc.validated = 0
	doc.flags.cmi_action_ok = True
	doc.save(ignore_permissions=True)  # _sync_journal membatalkan JE-nya
	frappe.db.commit()
	return {"ok": True, "status": "Draft"}


@frappe.whitelist()
def void_doc(doctype, name, reason=None):
	"""Void: dokumen dibatalkan, jurnalnya dibalik. Alasan dicatat sebagai komentar."""
	_assert_action(doctype, ROLE_VOID, _("mem-void dokumen"))
	doc = _get(doctype, name)

	if doctype in MASTER_JOB:
		if doc.get("void"):
			frappe.throw(_("{0} sudah di-void.").format(name))
		from erp.downstream_lock import downstream_refs

		refs = downstream_refs(doc)
		if refs:
			frappe.throw(_("{0} masih dipakai: {1}. Lepas/batalkan dulu dokumen tersebut.").format(
				name, ", ".join(f"{dt} {n}" for dt, n in refs[:10])))
		_stamp(doc, "void", True, reason)
	elif doctype in SUBMITTABLE:
		if doc.docstatus == 2:
			frappe.throw(_("{0} sudah di-void.").format(name))
		_assert_no_dependents(doc)
		if doc.docstatus == 0:
			# Draft: belum ada jurnal, jadi tidak ada yang dibalik -- cukup ditandai batal.
			# Nomornya tetap terpakai (itu gunanya Void, bukan Delete), dan jatah yang
			# ditahannya (mis. sisa Pending Cash / uang muka PO, yang dihitung dari baris
			# ber-docstatus < 2) otomatis kembali bebas.
			_force_to_cancelled(doc)
			_audit(doc, custom_voided_by=frappe.session.user)
			# Kolom Payment di list Sales/Purchase Invoice & Expense Note ikut dari PV draft,
			# jadi harus disegarkan -- db_set langsung tidak memicu doc_events.
			if doctype == "Payment Entry":
				from erpnext_custom.overrides.payment_entry import sync_payment_links
				sync_payment_links(frappe.get_doc(doctype, name))
		else:
			doc.flags.cmi_action_ok = True
			doc.cancel()
			_audit(doc, custom_voided_by=frappe.session.user)
	else:
		if doc.get("void"):
			frappe.throw(_("{0} sudah di-void.").format(name))
		doc.void = 1
		doc.flags.cmi_action_ok = True
		doc.save(ignore_permissions=True)  # _sync_journal membatalkan JE-nya

	if reason:
		doc.add_comment("Comment", _("VOID oleh {0}: {1}").format(frappe.session.user, reason))
	frappe.db.commit()
	return {"ok": True, "status": "Void"}


@frappe.whitelist()
def unvoid_doc(doctype, name):
	"""Unvoid: kembalikan dokumen void ke draft. User perlu Validate lagi.

	Sengaja TIDAK langsung kembali ke tervalidasi: jurnalnya sudah dibalik, dan
	memasangnya kembali diam-diam menyembunyikan bahwa dokumen ini pernah dibatalkan.
	Kembali ke draft memaksa Validate ulang, sehingga jejaknya jelas.
	"""
	_assert_action(doctype, ROLE_UNVOID, _("meng-unvoid dokumen"))
	_assert_revertible(doctype)
	doc = _get(doctype, name)

	if doctype in MASTER_JOB:
		if not doc.get("void"):
			frappe.throw(_("{0} tidak sedang void.").format(name))
		if doctype == "Packing List":
			# Selama void, estimation-nya bebas dipakai PL lain. Kalau sudah diambil,
			# menghidupkan PL ini membuat satu estimation dipakai dua kali.
			doc.void = 0
			doc.check_estimation_unused()
		_stamp(doc, "void", False)
		doc.add_comment("Comment", _("UNVOID oleh {0}").format(frappe.session.user))
		frappe.db.commit()
		return {"ok": True, "status": "Open"}

	if doctype in SUBMITTABLE:
		if doc.docstatus != 2:
			frappe.throw(_("Hanya dokumen void yang bisa di-unvoid."))
		if doc.get("amended_from") or frappe.db.exists(doctype, {"amended_from": name}):
			frappe.throw(_("Dokumen ini sudah di-amend. Unvoid tidak berlaku."))
		_assert_revalidatable(doc)
		_force_to_draft(doc)
		_audit(doc, custom_voided_by=None, custom_validated_by=None)
		doc.add_comment("Comment", _("UNVOID oleh {0}").format(frappe.session.user))
		return {"ok": True, "status": "Draft"}

	if not doc.get("void"):
		frappe.throw(_("{0} tidak sedang void.").format(name))
	doc.void = 0
	doc.validated = 0  # kembali ke draft, bukan langsung tervalidasi
	doc.flags.cmi_action_ok = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "status": "Draft"}


def _assert_has_validate(doctype):
	if doctype in MASTER_JOB:
		frappe.throw(_("{0} tidak memakai Validate: langsung bisa ditarik selama tidak Closed/Void.").format(
			_(doctype)))


def _assert_revertible(doctype):
	if doctype in NO_REVERT:
		frappe.throw(_("{0} tidak bisa dikembalikan ke draft (Stock Ledger-nya dipakai valuasi "
			"transaksi sesudahnya). Void lalu buat dokumen baru.").format(_(doctype)))


def _stamp(doc, field, on, reason=None):
	"""Master Job: pasang/lepas `closed`/`void` beserta jejaknya (*_by, *_datetime, *_reason).

	Lewat db_set, BUKAN save: Master Job yang sudah ditarik dokumen lanjutan terkunci oleh
	downstream_lock.guard, padahal justru dokumen seperti itulah yang paling sering di-Close.
	"""
	doc.db_set({
		field: 1 if on else 0,
		f"{field}_by": frappe.session.user if on else None,
		f"{field}_datetime": now_datetime() if on else None,
		f"{field}_reason": reason if on else None,
	})


@frappe.whitelist()
def close_doc(doctype, name, reason=None):
	"""Close: dokumen tidak bisa ditarik transaksi berikutnya lagi, tapi TIDAK batal --
	angkanya tetap dihitung dan dokumen turunan yang sudah ada tetap jalan."""
	_assert_action(doctype, ROLE_CLOSE, _("menutup dokumen"))
	if doctype not in CLOSABLE:
		frappe.throw(_("Close/Open tidak berlaku untuk {0}.").format(_(doctype)))
	doc = _get(doctype, name)

	if doctype == "Sales Order":
		if doc.docstatus != 1:
			frappe.throw(_("Hanya Sales Order tervalidasi yang bisa di-Close."))
		if doc.status == "Closed":
			frappe.throw(_("{0} sudah Closed.").format(name))
		doc.update_status("Closed")
	else:
		if doc.get("void"):
			frappe.throw(_("{0} sedang void.").format(name))
		if doc.get("closed"):
			frappe.throw(_("{0} sudah Closed.").format(name))
		_stamp(doc, "closed", True, reason)

	doc.add_comment("Comment", _("CLOSE oleh {0}{1}").format(
		frappe.session.user, f": {reason}" if reason else ""))
	frappe.db.commit()
	return {"ok": True, "status": "Closed"}


@frappe.whitelist()
def open_doc(doctype, name):
	"""Open: buka lagi dokumen Closed supaya bisa ditarik transaksi berikutnya."""
	_assert_action(doctype, ROLE_OPEN, _("membuka dokumen"))
	if doctype not in CLOSABLE:
		frappe.throw(_("Close/Open tidak berlaku untuk {0}.").format(_(doctype)))
	doc = _get(doctype, name)

	if doctype == "Sales Order":
		if doc.status != "Closed":
			frappe.throw(_("{0} tidak sedang Closed.").format(name))
		doc.update_status("Draft")  # cara ERPNext me-Re-open: status dihitung ulang
	else:
		if not doc.get("closed"):
			frappe.throw(_("{0} tidak sedang Closed.").format(name))
		_stamp(doc, "closed", False)

	doc.add_comment("Comment", _("OPEN oleh {0}").format(frappe.session.user))
	frappe.db.commit()
	return {"ok": True, "status": "Open"}


@frappe.whitelist()
def so_update_status(status, name):
	"""Pengganti erpnext...sales_order.update_status (tombol Status bawaan form SO).

	Close/Re-open bawaan dibelokkan ke close_doc/open_doc supaya role-nya sama; Hold/Resume
	tetap jalur ERPNext apa adanya.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import update_status

	if status == "Closed":
		return close_doc("Sales Order", name)
	if status == "Draft" and frappe.db.get_value("Sales Order", name, "status") == "Closed":
		return open_doc("Sales Order", name)
	return update_status(status, name)


_BULK_ACTIONS = {
	"validate": validate_doc,
	"invalidate": invalidate_doc,
	"void": void_doc,
	"unvoid": unvoid_doc,
	"close": close_doc,
	"open": open_doc,
}


@frappe.whitelist()
def bulk_set_state(doctype, names, action, reason=None):
	"""Aksi Validate / Invalidate / Void / Unvoid untuk BANYAK dokumen (menu Actions di list).

	Memanggil fungsi satu-dokumen di atas apa adanya, jadi role, guard dependensi, dan cek
	revalidatable persis sama dengan aksi satuan -- tidak ada jalur longgar lewat list view.

	Satu dokumen gagal TIDAK menjatuhkan yang lain (mis. satu Payment Entry masih dirujuk
	dokumen lain): kegagalannya di-rollback, sisanya tetap jalan, lalu semuanya dilaporkan
	balik supaya user tahu persis mana yang tidak jadi. Return {ok: [...], failed: [{name, error}]}.
	"""
	fn = _BULK_ACTIONS.get(action)
	if not fn:
		frappe.throw(_("Aksi tidak dikenal: {0}").format(action))

	names = frappe.parse_json(names) if isinstance(names, str) else names
	ok, failed = [], []
	for name in names or []:
		try:
			if action in ("void", "close"):
				fn(doctype, name, reason=reason)
			else:
				fn(doctype, name)
			frappe.db.commit()
			ok.append(name)
		except Exception as e:
			frappe.db.rollback()
			failed.append({"name": name, "error": str(e)[:200]})
	return {"ok": ok, "failed": failed}


@frappe.whitelist()
def bulk_set_disabled(doctype, names, disabled):
	"""Enable / Disable massal dari list view, untuk doctype yang punya field `disabled`.

	Terpisah dari mesin Validate/Void di atas karena artinya memang lain: ini penanda
	MASTER masih boleh dipakai atau tidak, tidak menyentuh jurnal sama sekali.

	Sengaja pakai db_set, bukan doc.save(): satu-satunya yang berubah adalah flag ini,
	sedangkan dokumen lama bisa saja tidak lolos aturan validasi yang berlaku sekarang.
	Memaksanya lewat save() akan membuat dokumen lama tidak bisa di-disable sama sekali.

	Return {ok: [...], failed: [{name, error}]} -- sama bentuknya dengan bulk_set_state.
	"""
	if not frappe.get_meta(doctype).has_field("disabled"):
		frappe.throw(_("{0} tidak punya field Disabled.").format(_(doctype)))

	names = frappe.parse_json(names) if isinstance(names, str) else names
	disabled = 1 if int(disabled) else 0

	ok, failed = [], []
	for name in names or []:
		try:
			if not frappe.db.exists(doctype, name):
				frappe.throw(_("{0} {1} tidak ditemukan.").format(_(doctype), name))
			if not frappe.has_permission(doctype, "write", name):
				frappe.throw(_("Tidak boleh mengubah {0} ini.").format(name), frappe.PermissionError)
			doc = frappe.get_doc(doctype, name)
			if int(doc.get("disabled") or 0) == disabled:
				continue  # sudah pada keadaan itu -- bukan error, bukan pula "berhasil"
			doc.db_set("disabled", disabled)
			doc.add_comment("Comment", _("{0} oleh {1}").format(
				_("DISABLE") if disabled else _("ENABLE"), frappe.session.user))
			frappe.db.commit()
			ok.append(name)
		except Exception as e:
			frappe.db.rollback()
			failed.append({"name": name, "error": str(e)[:200]})
	return {"ok": ok, "failed": failed}


@frappe.whitelist()
def mark_paid(name, paid_date=None, notes=None):
	"""Pending Cash -> Paid. DI SINI jurnalnya terbentuk, bukan saat validate.

	Hanya dokumen yang sudah tervalidasi yang bisa di-Paid.
	"""
	_assert_action("Pending Cash", ROLE_VALIDATE, _("menandai Paid"))
	doc = _get("Pending Cash", name)

	if not doc.get("validated"):
		frappe.throw(_("Validate dulu sebelum menandai Paid."))
	if doc.get("void"):
		frappe.throw(_("{0} sedang void.").format(name))
	if doc.get("paid"):
		frappe.throw(_("{0} sudah Paid.").format(name))

	doc.paid = 1
	doc.paid_date = paid_date or today()
	if notes:
		doc.paid_notes = notes
	doc.flags.cmi_action_ok = True
	doc.save(ignore_permissions=True)  # journal dibuat di Pending Cash._sync_journal
	frappe.db.commit()
	return {"ok": True, "status": "Paid", "paid_date": str(doc.paid_date)}


@frappe.whitelist()
def unmark_paid(name):
	"""Batalkan status Paid Pending Cash -> jurnalnya ikut dibatalkan."""
	_assert_action("Pending Cash", ROLE_INVALIDATE, _("membatalkan status Paid"))
	doc = _get("Pending Cash", name)
	if not doc.get("paid"):
		frappe.throw(_("{0} belum Paid.").format(name))
	doc.paid = 0
	doc.paid_date = None
	doc.flags.cmi_action_ok = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "status": "Validated"}


# ---------------------------------------------------------------- guards on core

def guard_submit(doc, method=None):
	"""Cegah submit lewat tombol bawaan -- harus lewat Validate (supaya role terjaga)."""
	if doc.flags.get("cmi_action_ok"):
		return
	frappe.throw(
		_("Gunakan tombol <b>Validate</b> pada workflow CMI, bukan Submit bawaan ERPNext."),
		frappe.PermissionError,
	)


def guard_cancel(doc, method=None):
	"""Cegah cancel lewat tombol bawaan -- harus lewat Void/Invalidate."""
	if doc.flags.get("cmi_action_ok"):
		return
	frappe.throw(
		_("Gunakan tombol <b>Invalidate</b> atau <b>Void</b> pada workflow CMI, bukan Cancel bawaan ERPNext."),
		frappe.PermissionError,
	)


# Endpoint desk yang men-submit/cancel dokumen atas klik user.
_DESK_CMDS = {
	"frappe.desk.form.save.savedocs",
	"frappe.desk.form.save.cancel",
	"frappe.client.submit",
	"frappe.client.cancel",
	"frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs",
}


def guard_native(doc, method=None):
	"""before_submit/before_cancel doctype NATIVE: tolak hanya klik Submit/Cancel bawaan di
	desk atas dokumen INI. Submit/cancel oleh kode (dokumen turunan yang ikut di-submit di
	dalam request yang sama, job latar) dibiarkan: dokumen itu bukan sasaran request-nya."""
	if doc.flags.get("cmi_action_ok"):
		return
	fd = frappe.form_dict or {}
	if fd.get("cmd") not in _DESK_CMDS:
		return
	target = frappe.parse_json(fd.doc) if fd.get("doc") else fd
	if target.get("doctype") != doc.doctype:
		return
	if target.get("name") and target.get("name") != doc.name:
		return
	if method == "before_cancel":
		return guard_cancel(doc)
	return guard_submit(doc)


# ---------------------------------------------------------------- auto validate

# Flag di ERPNext Custom Setting (tab Flag) per doctype.
AUTO_VALIDATE_FLAG = {
	"Expense Note": "expense_note_reimburse_auto_validate",
	"Sales Invoice": "invoice_type_reimburse_auto_validate",
}


def auto_validate(doc, method=None):
	"""Dokumen langsung tervalidasi saat disimpan, kalau flag-nya di setting dicentang.

	Expense Note  -> dipasang di `before_validate`: cukup centang `validated`, sisanya
	                 (cek akun + jurnal) jalan di save yang sama.
	Sales Invoice -> dipasang di `on_update`: dokumen harus sudah tersimpan sebelum
	                 bisa di-submit. Submit menyimpan ulang dokumen sehingga on_update
	                 jalan lagi -- saat itu docstatus sudah 1 dan fungsi ini keluar.

	Role Validate SENGAJA tidak dicek: ini "auto validate BY SYSTEM"; yang menahannya
	adalah flag di setting, bukan role si penyimpan.
	"""
	if doc.flags.get("skip_auto_validate"):
		return

	if doc.doctype == "Expense Note":
		if doc.get("validated") or doc.get("void"):
			return
		# Perintah user menang atas auto validate: dokumen yang TERSIMPAN tervalidasi lalu
		# dikirim dengan validated=0 sedang di-Invalidate / di-Unvoid. Kalau di-set 1 lagi
		# di save yang sama, _guard_locked menolak simpanannya ("sudah Tervalidasi dan
		# terkunci") -- Batalkan Validasi jadi mustahil selama syarat auto validate terpenuhi.
		if not doc.is_new() and frappe.db.get_value(doc.doctype, doc.name, "validated"):
			return
		if doc.get("is_reimburse") and frappe.db.get_single_value(
			"ERPNext Custom Setting", AUTO_VALIDATE_FLAG[doc.doctype]
		):
			doc.validated = 1
			doc.flags.cmi_action_ok = True  # oleh sistem: lolos guard_checkbox
			return
		# Aturan kedua: semua Expense Item masih di dalam budget estimation Packing List-nya.
		# Dihitung di app erp (di sana budget/realisasinya hidup), dipanggil di sini supaya
		# semua jalur auto validate tetap di satu tempat.
		if frappe.db.get_single_value(
			"ERPNext Custom Setting", "expense_note_estimation_auto_validate"
		):
			from erp.expedition.doctype.expense_note.expense_note import items_fit_estimation

			if items_fit_estimation(doc):
				doc.validated = 1
				doc.flags.cmi_action_ok = True
		return

	# Sales Invoice
	if doc.docstatus != 0 or doc.get("custom_invoice_behavior") != "Reimburse":
		return
	if not frappe.db.get_single_value("ERPNext Custom Setting", AUTO_VALIDATE_FLAG[doc.doctype]):
		return
	doc.flags.cmi_action_ok = True  # lolos guard_submit -- auto validate = jalur resmi
	doc.flags.ignore_permissions = True
	doc.submit()
	_audit(doc, custom_validated_by=frappe.session.user)


@frappe.whitelist()
def get_permissions(doctype=None):
	"""Aksi apa yang boleh user ini -- untuk menampilkan/menyembunyikan tombol.
	Tanpa doctype = role global saja (pemanggil lama)."""
	if doctype:
		return {a: can(doctype, a) for a in ACTION_ROLE}
	return {a: _has_role(r) for a, r in ACTION_ROLE.items()}


# Centang yang sama dengan aksi workflow di doctype checkbox (lihat guard_checkbox).
CHECKBOX_ACTIONS = (("validated", "validate", "invalidate"), ("void", "void", "unvoid"), ("closed", "close", "open"))


def guard_checkbox(doc, method=None):
	"""validate ("*"): doctype checkbox (Expense Note, Pending Cash, AP/AR Note, ...) bisa di-Validate/
	Void/Close cukup dengan mencentang lalu Save -- tombol form dan bulk action-nya memang begitu.
	Jadi tabel Workflow Access ditegakkan di sini, saat centangnya berubah.

	Hanya doctype yang SUDAH punya baris di tabel: sebelum itu jalur ini memang tidak pernah
	dicek role, dan tiba-tiba mewajibkan role global akan mengunci user yang selama ini bekerja.
	"""
	if doc.flags.get("cmi_action_ok") or doc.meta.is_submittable or frappe.flags.in_migrate:
		return
	if not _access_rows(doc.doctype):
		return
	before = doc.get_doc_before_save()
	for field, on, off in CHECKBOX_ACTIONS:
		if not doc.meta.has_field(field):
			continue
		old = cint(before.get(field)) if before else 0
		new = cint(doc.get(field))
		if old != new and not can(doc.doctype, on if new else off):
			_assert_action(doc.doctype, ACTION_ROLE[on if new else off], _(on if new else off))


def validate_access_rows(doc, method=None):
	"""ERPNext Custom Setting: baris Workflow Access hanya untuk doctype yang memakai alur ini."""
	for r in doc.get("workflow_access") or []:
		if r.document_type not in SUPPORTED:
			frappe.throw(_("Workflow Access baris {0}: {1} tidak memakai alur Validate/Void. Pilihan: {2}").format(
				r.idx, r.document_type, ", ".join(SUPPORTED)))
		if r.document_type in MASTER_JOB and (r.can_validate or r.can_invalidate):
			frappe.throw(_("Workflow Access baris {0}: {1} tidak memakai Validate/Invalidate.").format(
				r.idx, r.document_type))
		if r.document_type not in CLOSABLE and (r.can_close or r.can_open):
			frappe.throw(_("Workflow Access baris {0}: Close/Open hanya untuk {1}.").format(
				r.idx, ", ".join(CLOSABLE)))


def boot(bootinfo):
	"""Konfigurasi untuk workflow_auto.js: doctype mana dipasangi menu apa.

	mode   : docstatus | master_job
	revert : Invalidate/Unvoid tersedia (False untuk dokumen stok)
	close  : Close/Open tersedia
	"""
	if frappe.session.user == "Guest":
		return
	doctypes = {}
	for dt in SUPPORTED:
		if dt in WIRED or dt in CHECKBOX:
			continue
		doctypes[dt] = {
			"mode": "master_job" if dt in MASTER_JOB else "docstatus",
			"revert": dt not in NO_REVERT,
			"close": dt in CLOSABLE,
		}
	bootinfo.cmi_workflow = {
		"doctypes": doctypes,
		"can": get_permissions(),
		# izin efektif per doctype (tabel Workflow Access, atau aturan lama bila belum diisi)
		"can_by_doctype": {dt: get_permissions(dt) for dt in SUPPORTED},
		"supported": list(SUPPORTED),
	}

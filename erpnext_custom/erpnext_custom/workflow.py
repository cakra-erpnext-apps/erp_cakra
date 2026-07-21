"""Alur Validate / Invalidate / Void / Unvoid untuk transaksi CMI.

Satu mesin state untuk enam doctype, supaya aturannya tidak tersebar dan tidak
saling berbeda:

    Sales Invoice, Purchase Invoice, Purchase Order, Payment Entry  -> docstatus
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
from frappe.utils import now_datetime, today

# ---------------------------------------------------------------- roles

ROLE_VALIDATE = "Transaction Validate"
ROLE_INVALIDATE = "Transaction Invalidate"
ROLE_VOID = "Transaction Void"
ROLE_UNVOID = "Transaction Unvoid"

WORKFLOW_ROLES = (ROLE_VALIDATE, ROLE_INVALIDATE, ROLE_VOID, ROLE_UNVOID)

# Role lama khusus invoice tetap dihormati supaya user yang sudah punya izin tidak
# kehilangan akses saat fitur ini dipasang.
LEGACY_EQUIVALENT = {
	ROLE_VALIDATE: ("Invoice Validate",),
	ROLE_VOID: ("Invoice Void",),
}


def _has_role(role):
	allowed = {role, "System Manager"} | set(LEGACY_EQUIVALENT.get(role, ()))
	return bool(set(frappe.get_roles()) & allowed)


def _assert_role(role, action):
	if not _has_role(role):
		frappe.throw(
			_("Hanya user dengan role <b>{0}</b> yang boleh {1}.").format(role, action),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------- doctypes

# Doctype berbasis docstatus (inti ERPNext).
SUBMITTABLE = ("Sales Invoice", "Purchase Invoice", "Purchase Order", "Payment Entry")

# Doctype berbasis checkbox (custom, app erp).
CHECKBOX = ("Expense Note", "Pending Cash")

SUPPORTED = SUBMITTABLE + CHECKBOX

# Doctype yang TIDAK menghasilkan jurnal sama sekali.
NO_JOURNAL = ("Purchase Order",)


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
	# Izin submit & cancel SENGAJA dicabut dari semua role (_revoke_submit_cancel di
	# install.py) supaya tombol bawaan Submit/Cancel hilang — satu-satunya jalan adalah
	# Validate/Void di sini. Gerbangnya sudah dijaga dua lapis di atas: role aksi
	# (_assert_role) + izin write dokumen. Tanpa flag ini, doc.submit()/doc.cancel()
	# jatuh ke izin submit/cancel yang barusan dicabut, jadi HANYA Administrator yang
	# bisa Validate — user ber-role Transaction Validate pun ditolak.
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
	probe = frappe.get_doc(doc.doctype, doc.name)
	probe.docstatus = 0  # tiru keadaan draft, tanpa menyentuh DB
	try:
		probe.run_method("validate")
		probe._validate_mandatory()
	except Exception as e:
		frappe.throw(
			_(
				"{0} tidak bisa dikembalikan ke draft: dokumen ini tidak lolos aturan validasi "
				"yang berlaku sekarang, sehingga tidak akan bisa divalidasi ulang.<br><br>"
				"Penyebab: {1}<br><br>"
				"Perbaiki dulu datanya, atau biarkan dokumen ini sebagaimana adanya."
			).format(doc.name, str(e)[:300])
		)


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


def _force_to_draft(doc):
	"""Kembalikan docstatus ke 0 tanpa lewat framework (tidak ada API resminya)."""
	frappe.db.set_value(doc.doctype, doc.name, "docstatus", 0, update_modified=False)
	_clear_ledgers(doc)
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
	_assert_role(ROLE_VALIDATE, _("memvalidasi dokumen"))
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
	_assert_role(ROLE_INVALIDATE, _("membatalkan validasi"))
	doc = _get(doctype, name)

	if doctype in SUBMITTABLE:
		if doc.docstatus != 1:
			frappe.throw(_("Hanya dokumen tervalidasi yang bisa di-invalidate."))
		_assert_no_dependents(doc)
		_assert_revalidatable(doc)
		doc.flags.cmi_action_ok = True
		doc.flags.ignore_links = True
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
	_assert_role(ROLE_VOID, _("mem-void dokumen"))
	doc = _get(doctype, name)

	if doctype in SUBMITTABLE:
		if doc.docstatus == 2:
			frappe.throw(_("{0} sudah di-void.").format(name))
		if doc.docstatus != 1:
			frappe.throw(_("Hanya dokumen tervalidasi yang bisa di-void."))
		_assert_no_dependents(doc)
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
	_assert_role(ROLE_UNVOID, _("meng-unvoid dokumen"))
	doc = _get(doctype, name)

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


_BULK_ACTIONS = {
	"validate": validate_doc,
	"invalidate": invalidate_doc,
	"void": void_doc,
	"unvoid": unvoid_doc,
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
			if action == "void":
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
def mark_paid(name, paid_date=None, notes=None):
	"""Pending Cash -> Paid. DI SINI jurnalnya terbentuk, bukan saat validate.

	Hanya dokumen yang sudah tervalidasi yang bisa di-Paid.
	"""
	_assert_role(ROLE_VALIDATE, _("menandai Paid"))
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
	_assert_role(ROLE_INVALIDATE, _("membatalkan status Paid"))
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
	_assert_role(ROLE_VALIDATE, _("memvalidasi dokumen"))


def guard_cancel(doc, method=None):
	"""Cegah cancel lewat tombol bawaan -- harus lewat Void/Invalidate."""
	if doc.flags.get("cmi_action_ok"):
		return
	_assert_role(ROLE_VOID, _("mem-void dokumen"))


@frappe.whitelist()
def get_permissions():
	"""Role apa yang dipunya user ini -- untuk menampilkan/menyembunyikan tombol."""
	return {
		"validate": _has_role(ROLE_VALIDATE),
		"invalidate": _has_role(ROLE_INVALIDATE),
		"void": _has_role(ROLE_VOID),
		"unvoid": _has_role(ROLE_UNVOID),
	}

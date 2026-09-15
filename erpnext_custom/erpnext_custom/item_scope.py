"""Lingkup Item Group per konteks — dikonfigurasi di ERPNext Custom Setting.

Dulu hard-coded ke Item Category ("Stock"/"Asset"/"Sparepart"/"Service"): daftar tertutup
di JS, dan menambah satu jenis barang berarti mengubah kode. Sekarang basisnya Item Group
dan bisa dipilih lebih dari satu lewat UI.

Tiga lingkup:
  purchase  -> Item Group yang muncul di picker item Purchase Order
  vehicle   -> Item Group yang memunculkan field Vehicle (dipakai langsung ke kendaraan)
  per tipe invoice -> lihat invoice_types.item_groups_of

KOSONG BERARTI SEMUA. Itu disengaja supaya site yang belum mengatur apa pun tidak tiba-tiba
kehilangan seluruh pilihan item.
"""

import frappe

SETTING_DT = "ERPNext Custom Setting"
_FIELDS = {
    "purchase": "purchase_item_groups",
    "vehicle": "vehicle_item_groups",
    # Estimation di CRM (tab Expedition). "expense" juga dipakai tabel Items Cost Component
    # — dulu field sendiri FCRM Settings.use_items_group, sekarang satu sumber di sini.
    "revenue": "revenue_item_groups",
    "expense": "expense_item_groups",
    # Modal "Expense Items" di Expense Note (tab Expense Note) — daftar Item yang boleh
    # dipilih sebagai baris biaya. Sengaja terpisah dari "expense" (Estimation).
    "expense_note": "expense_note_item_groups",
}


def item_groups(scope):
    """[str] Item Group untuk lingkup ini. [] = tanpa batasan."""
    fieldname = _FIELDS[scope]
    try:
        # get_single, BUKAN get_cached_doc: cache dokumen Single bisa datang tanpa child
        # table (gotcha yang sama dengan invoice_types._config).
        doc = frappe.get_single(SETTING_DT)
    except Exception:
        return []
    return [r.item_group for r in (doc.get(fieldname) or []) if r.get("item_group")]


def item_account(item_code, company, fieldname):
    """Akun default milik Item untuk `company`: Item Default item -> Item Default Item Group.

    Satu pola yang sama dipakai HPP (delivery_note), pendapatan (sales_invoice), beban
    sparepart, dan baris Expense Note. None kalau item/grup belum punya akunnya.
    """
    if not item_code:
        return None
    return frappe.db.get_value(
        "Item Default", {"parent": item_code, "company": company}, fieldname
    ) or frappe.db.get_value(
        "Item Default",
        {"parent": frappe.db.get_value("Item", item_code, "item_group"), "company": company},
        fieldname,
    )


@frappe.whitelist()
def get_item_groups(scope):
    if scope not in _FIELDS:
        frappe.throw("scope tidak dikenal: {0}".format(scope))
    return item_groups(scope)


def boot(bootinfo):
    """Dipakai depends_on field Vehicle di baris PI/PR — depends_on dievaluasi di client
    dan tak bisa memanggil server, jadi daftarnya ikut boot."""
    bootinfo.cmi_vehicle_item_groups = item_groups("vehicle")
    bootinfo.cmi_purchase_item_groups = item_groups("purchase")
    # dipakai set_query kolom Item grid Revenue/Expense di form desk CRM Estimation
    bootinfo.cmi_revenue_item_groups = item_groups("revenue")
    bootinfo.cmi_expense_item_groups = item_groups("expense")
    # dipakai get_query field Expense Item di modal Expense Items (Expense Note)
    bootinfo.cmi_expense_note_item_groups = item_groups("expense_note")
    # Daftar lengkap Item Group: dipakai kolom Item Groups di tabel Invoice Type
    # (ERPNext Custom Setting) sebagai pilihan dropdown. Ikut boot, bukan dipanggil saat
    # form dibuka, supaya sudah ada SEBELUM grid menyalin docfield-nya — kalau menyusul
    # lewat panggilan async, salinan baris terlanjur dibuat tanpa options dan kolomnya
    # kembali jadi ketik manual.
    bootinfo.cmi_item_groups = frappe.get_all("Item Group", pluck="name", order_by="name")
    # Filter default list Journal Entry (ERPNext Custom Setting > tab Journal Entry).
    # Ikut boot karena listview_settings.filters dibaca List View secara sinkron saat
    # halaman dibuka -- panggilan async menyusul terlambat, filternya tidak terpasang.
    bootinfo.cmi_je_hide_system_generated = frappe.db.get_single_value(
        "ERPNext Custom Setting", "je_hide_system_generated"
    )
    # Expense Note Type "Tanpa Job" — dibaca depends_on section Reimbursement And
    # Connection di form Expense Note, dan en_has_conn() di JS-nya.
    bootinfo.cmi_no_job_expense_note_types = frappe.get_all(
        "Expense Note Type", filters={"no_job": 1}, pluck="name"
    )
    # Expense Note Type yang memakai entri GRID Expense Items (tombol/panel disembunyikan).
    # Barisnya tetap masuk tabel Expense Note Item — ini murni saklar tampilan. Ikut boot
    # karena en_is_grid_mode() di JS dibaca saat form render, sebelum sempat tanya server.
    bootinfo.cmi_grid_expense_note_types = [
        r.expense_note_type
        for r in (
            frappe.get_single("ERPNext Custom Setting").get("grid_expense_note_types") or []
        )
        if r.expense_note_type
    ]
    # Pending Cash Type yang wajib menaut dokumen lain — dibaca depends_on section Connection
    # + mandatory_depends_on Modul/Number di form Pending Cash.
    from erp.fico.doctype.pending_cash.pending_cash import connection_types

    bootinfo.cmi_pc_connection_types = connection_types()

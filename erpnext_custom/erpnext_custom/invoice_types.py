"""Invoice Type dinamis — dikonfigurasi di Selling Settings (tabel custom_invoice_types).

Tiap baris: nama tipe, Behavior (Normal / Reimburse / Debit Note), daftar Type No, Role
yang boleh memakai, dan flag Disabled. Ini menggantikan daftar hard-coded lama
(INVOICE_TYPE_OPT / INVOICE_TYPE_NO_OPT / CMI_TYPE_NO di JS).

Kenapa BEHAVIOR, bukan nama tipe: perilaku khusus (tabel Get Expense Notes, Input Mode
Debit Note, tunda GL) dulu di-hardcode ke nama "Reimburse"/"Debit Note". Sekarang nama tipe
bebas dibuat user; yang memicu perilaku adalah field Behavior. Jadi Sales Invoice menyimpan
`custom_invoice_behavior` (diturunkan dari tipe) dan SEMUA depends_on/logika membaca itu,
bukan nama tipe.

Select `custom_invoice_type` / `custom_invoice_type_no` tetap Select NATIVE: opsinya
(Property Setter) disinkronkan dari config ini tiap Selling Settings disimpan & tiap migrate
(sync_invoice_type_options). Server Select-validation ERPNext karena itu selalu lolos untuk
tipe yang terdaftar (termasuk yang sudah disabled — supaya invoice LAMA tak ditolak). Filter
"hanya tipe yang enabled & sesuai role" dilakukan di JS (dropdown) + validate_invoice_type
(tolak saat Save).
"""

import frappe
from frappe import _

BEHAVIORS = ("Normal", "Reimburse", "Debit Note")
_CACHE_KEY = "cmi_invoice_types"


def _split_csv(text):
    """"C/E, C/EA, T/E" -> ["C/E", "C/EA", "T/E"] (toleran newline & spasi)."""
    if not text:
        return []
    out = []
    for part in str(text).replace("\n", ",").split(","):
        p = part.strip()
        if p and p not in out:
            out.append(p)
    return out


def _config():
    """[{invoice_type, behavior, type_no:[...], roles:[...], disabled}], urut sesuai grid.
    Di-cache; dibersihkan saat Selling Settings disimpan (clear_cache) & saat migrate."""
    cached = frappe.cache().get_value(_CACHE_KEY)
    if cached is not None:
        return cached
    rows = []
    try:
        ss = frappe.get_cached_doc("Selling Settings")
        for r in ss.get("custom_invoice_types") or []:
            if not r.get("invoice_type"):
                continue
            rows.append({
                "invoice_type": r.invoice_type,
                "behavior": r.behavior or "Normal",
                "income_account": r.get("income_account") or None,
                "type_no": _split_csv(r.get("type_no")),
                "roles": _split_csv(r.get("roles")),
                "disabled": bool(r.get("disabled")),
            })
    except Exception:
        pass
    frappe.cache().set_value(_CACHE_KEY, rows)
    return rows


def clear_cache(doc=None, method=None):
    frappe.cache().delete_value(_CACHE_KEY)


def behavior_of(invoice_type):
    """Behavior tipe (Normal/Reimburse/Debit Note). Default Normal kalau tak ketemu."""
    for r in _config():
        if r["invoice_type"] == invoice_type:
            return r["behavior"]
    return "Normal"


def income_account_of(invoice_type):
    """Akun pendapatan (Cr) default tipe, atau None kalau tak diset/tak ketemu."""
    for r in _config():
        if r["invoice_type"] == invoice_type:
            return r.get("income_account")
    return None


@frappe.whitelist()
def get_income_account(invoice_type):
    """Dipakai client (before_save) untuk mengisi income_account item dari akun tipe."""
    return income_account_of(invoice_type)


def _visible_to(row, user):
    """True kalau baris tipe boleh dilihat user. roles kosong = semua. Administrator/System
    Manager selalu boleh (supaya tak terkunci dari tipe apa pun)."""
    if not row["roles"]:
        return True
    if user == "Administrator":
        return True
    user_roles = set(frappe.get_roles(user))
    if "System Manager" in user_roles:
        return True
    return bool(user_roles & set(row["roles"]))


@frappe.whitelist()
def get_invoice_types(user=None):
    """Tipe yang ENABLED dan boleh dilihat user — untuk dropdown Invoice Type di JS.
    Kembali: [{invoice_type, behavior, type_no:[...]}]."""
    user = user or frappe.session.user
    return [
        {"invoice_type": r["invoice_type"], "behavior": r["behavior"], "type_no": r["type_no"]}
        for r in _config()
        if not r["disabled"] and _visible_to(r, user)
    ]


def _row(invoice_type):
    for r in _config():
        if r["invoice_type"] == invoice_type:
            return r
    return None


def validate_invoice_type(doc, method=None):
    """Set behavior + tegakkan aturan tipe SAAT tipe dipilih/diubah (bukan tiap simpan,
    supaya invoice LAMA dengan tipe yang kini disabled tetap bisa diedit).

    Ditolak kalau: tipe tak dikenal, tipe disabled, tipe di luar hak role user, atau
    Type No bukan milik tipe itu."""
    itype = doc.get("custom_invoice_type")
    # Behavior selalu disinkronkan (dipakai semua depends_on & logika server).
    doc.custom_invoice_behavior = behavior_of(itype) if itype else ""

    if not itype:
        return

    changed = doc.is_new() or doc.has_value_changed("custom_invoice_type") \
        or doc.has_value_changed("custom_invoice_type_no")
    if not changed:
        return

    row = _row(itype)
    if not row:
        frappe.throw(_("Invoice Type <b>{0}</b> tidak terdaftar di Selling Settings.").format(itype))
    if row["disabled"]:
        frappe.throw(_("Invoice Type <b>{0}</b> sedang dinonaktifkan.").format(itype))
    if not _visible_to(row, frappe.session.user):
        frappe.throw(_("Anda tidak punya akses ke Invoice Type <b>{0}</b>.").format(itype))

    type_no = doc.get("custom_invoice_type_no")
    if type_no and row["type_no"] and type_no not in row["type_no"]:
        frappe.throw(_("Invoice Type No <b>{0}</b> tidak tersedia untuk tipe <b>{1}</b>.").format(type_no, itype))


def sync_invoice_type_options(doc=None, method=None):
    """Sinkronkan opsi Select `custom_invoice_type` & `custom_invoice_type_no` dari config
    ke Property Setter, supaya Select-validation server lolos untuk semua tipe terdaftar
    (termasuk disabled -> invoice lama aman). Dipanggil on_update Selling Settings + migrate.
    """
    clear_cache()
    cfg = _config()
    types = "\n".join([""] + [r["invoice_type"] for r in cfg])
    nos = []
    for r in cfg:
        for n in r["type_no"]:
            if n not in nos:
                nos.append(n)
    type_nos = "\n".join([""] + nos)
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    make_property_setter("Sales Invoice", "custom_invoice_type", "options", types, "Small Text",
                         for_doctype=False, validate_fields_for_doctype=False)
    make_property_setter("Sales Invoice", "custom_invoice_type_no", "options", type_nos, "Small Text",
                         for_doctype=False, validate_fields_for_doctype=False)
    frappe.clear_cache(doctype="Sales Invoice")


# Akun pendapatan (Cr) default per tipe, DIRUJUK LEWAT account_number supaya tahan abbr
# (nama akun = "4120.001 - ... - PC", suffix beda antar company). Dipakai untuk seed awal
# & backfill baris lama yang belum punya Default Account. User bisa mengubahnya di
# Selling Settings kapan saja — backfill hanya mengisi yang MASIH KOSONG.
TYPE_ACCOUNT_NO = {
    "Expedition": "4120.001",  # Pendapatan Jasa Trucking
    "Depo": "4120.001",        # Pendapatan Jasa Trucking (sama, Normal expedisi)
    "Trading": "4110.001",     # Penjualan Barang Dagang
    "Reimburse": "1510.001",   # Reimbursement (Asset) — Reimburse belum posting GL
    "Debit Note": "4120.012",  # Pendapatan Jasa Lainnya (generik)
}


def _default_company():
    return (frappe.defaults.get_global_default("company")
            or frappe.db.get_single_value("Global Defaults", "default_company"))


def _resolve_account(account_number, company=None):
    """Nama Account dari account_number untuk company (default company kalau None)."""
    company = company or _default_company()
    if not (account_number and company):
        return None
    return frappe.db.get_value(
        "Account", {"account_number": account_number, "company": company, "is_group": 0}, "name"
    )


# Konfigurasi default: dipakai saat tabel di Selling Settings masih kosong (fresh install /
# migrate pertama) supaya invoice tidak kehilangan tipe lamanya. Idempoten.
DEFAULT_TYPES = [
    {"invoice_type": "Expedition", "behavior": "Normal", "type_no": "C/E, C/EA, T/E"},
    {"invoice_type": "Depo", "behavior": "Normal", "type_no": "C/E, C/EA, T/E"},
    {"invoice_type": "Trading", "behavior": "Normal", "type_no": "C/T"},
    {"invoice_type": "Reimburse", "behavior": "Reimburse", "type_no": "IR"},
    {"invoice_type": "Debit Note", "behavior": "Debit Note", "type_no": "DN"},
]


def ensure_default_types():
    """Isi tabel Invoice Type di Selling Settings dengan default kalau MASIH KOSONG."""
    ss = frappe.get_single("Selling Settings")
    if ss.get("custom_invoice_types"):
        return
    for t in DEFAULT_TYPES:
        row = dict(t)
        row["income_account"] = _resolve_account(TYPE_ACCOUNT_NO.get(t["invoice_type"]))
        ss.append("custom_invoice_types", row)
    ss.flags.ignore_permissions = True
    # income_account mandatory tapi COA bisa belum ada saat fresh install -> jangan blokir
    # seeding; user melengkapi lewat UI (mandatory tetap berlaku di sana).
    ss.flags.ignore_mandatory = True
    ss.save()
    frappe.db.commit()


def ensure_type_accounts():
    """Backfill Default Account (income_account) baris tipe yang MASIH KOSONG dari
    TYPE_ACCOUNT_NO. Idempoten; tidak menimpa akun yang sudah diisi user. Perlu karena
    field-nya baru + mandatory: tabel lama punya baris tanpa akun, kalau tidak diisi user
    tak bisa menyimpan Selling Settings."""
    # Guard-nya cek KOLOM CHILD, bukan has_column("Selling Settings", "custom_invoice_types"):
    # field bertipe Table tak pernah punya kolom di tabel induk, jadi cek itu selalu False.
    if not frappe.db.has_column("CMI Invoice Type", "income_account"):
        return
    ss = frappe.get_single("Selling Settings")
    changed = False
    for r in ss.get("custom_invoice_types") or []:
        if r.get("income_account"):
            continue
        acc = _resolve_account(TYPE_ACCOUNT_NO.get(r.invoice_type))
        if acc:
            r.income_account = acc
            changed = True
    if changed:
        ss.flags.ignore_permissions = True
        # Field mandatory -> lewati validasi mandatory saat backfill program (baris tipe
        # custom yang tak ada di map & belum diisi user tak boleh memblokir backfill ini).
        ss.flags.ignore_mandatory = True
        ss.save(ignore_permissions=True)
        clear_cache()
        frappe.db.commit()


def backfill_invoice_behavior():
    """Isi custom_invoice_behavior invoice LAMA dari tipe-nya (via config), supaya section
    Reimburse/Debit Note tetap muncul saat dibuka. SQL langsung: tak menyentuh docstatus,
    tak memvalidasi ulang. Idempoten — hanya baris yang behavior-nya masih kosong."""
    if not frappe.db.has_column("Sales Invoice", "custom_invoice_behavior"):
        return
    for r in _config():
        frappe.db.sql(
            """UPDATE `tabSales Invoice` SET custom_invoice_behavior = %s
               WHERE custom_invoice_type = %s
                 AND (custom_invoice_behavior IS NULL OR custom_invoice_behavior = '')""",
            (r["behavior"], r["invoice_type"]),
        )
    frappe.db.commit()

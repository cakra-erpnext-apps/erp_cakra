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
        ss.append("custom_invoice_types", t)
    ss.flags.ignore_permissions = True
    ss.save()
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

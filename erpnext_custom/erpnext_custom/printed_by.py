"""Printed By dinamis — dikonfigurasi di Selling Settings (tabel custom_printed_by_options).

Tiap baris: teks bebas yang tampil di blok tanda tangan Invoice Print Out, plus flag
Default dan Disabled. Menggantikan Link ke User: nama penandatangan sering bukan user
sistem (mis. "COMPUTER GENERATED DOCUMENT - NO SIGNATURE / NO STAMP NEEDED", atau nama
lengkap dengan jabatan), jadi teks bebas lebih tepat daripada Link.

Cara defaultnya bekerja — SENGAJA tanpa fetch tambahan dari client:
opsi Select disusun dengan baris Default di URUTAN PERTAMA (tanpa opsi kosong di depan).
Kontrol Select yang nilainya kosong otomatis menampilkan opsi pertama, jadi invoice yang
belum punya pilihan sendiri langsung memperlihatkan default di sidebar print, dan nilainya
ikut tersimpan begitu tombol Print ditekan. Untuk render TANPA sidebar (PDF/email) template
memanggil default_label() lewat frappe.get_all — lihat print format Invoice Print Out.

Penyimpanan di Sales Invoice (`custom_printed_by`) sengaja bertipe DATA, bukan Select:
invoice LAMA menyimpan user id (field ini dulunya Link User) dan Select-validation akan
menolaknya saat save. Template tetap menerjemahkan user id lama jadi full name.
"""

import frappe

_CACHE_KEY = "cmi_printed_by_options"
PARENT = "Selling Settings"
FIELD = "custom_printed_by_options"

# Dipakai saat tabel masih kosong (fresh install / migrate pertama). Teks ini sebelumnya
# di-hardcode di print format sebagai fallback kalau Printed By kosong.
DEFAULT_LABEL = "COMPUTER GENERATED DOCUMENT - NO SIGNATURE / NO STAMP NEEDED"


def _config():
    """[{label, is_default, disabled}] urut sesuai grid. Di-cache; dibersihkan saat
    Selling Settings disimpan & saat migrate."""
    cached = frappe.cache().get_value(_CACHE_KEY)
    if cached is not None:
        return cached
    rows = []
    try:
        ss = frappe.get_cached_doc(PARENT)
        for r in ss.get(FIELD) or []:
            label = (r.get("label") or "").strip()
            if not label:
                continue
            rows.append({
                "label": label,
                "is_default": bool(r.get("is_default")),
                "disabled": bool(r.get("disabled")),
            })
    except Exception:
        pass
    frappe.cache().set_value(_CACHE_KEY, rows)
    return rows


def clear_cache(doc=None, method=None):
    frappe.cache().delete_value(_CACHE_KEY)


def default_label():
    """Teks Default yang aktif, atau None."""
    for r in _config():
        if r["is_default"] and not r["disabled"]:
            return r["label"]
    return None


def options():
    """Daftar opsi Select, baris Default di depan.

    Baris disabled TETAP ikut (di belakang) supaya invoice lama yang memakainya tidak
    ditolak Select-validation — sama seperti perlakuan Invoice Type.
    """
    cfg = _config()
    default = default_label()
    enabled = [r["label"] for r in cfg if not r["disabled"] and r["label"] != default]
    disabled = [r["label"] for r in cfg if r["disabled"] and r["label"] != default]
    out = ([default] if default else [""]) + enabled + disabled
    # Tanpa default, opsi kosong di depan supaya field bisa benar-benar kosong.
    return out


def sync_printed_by_options(doc=None, method=None):
    """Sinkronkan opsi Select `printed_by` (Print Settings) dari config ke Property Setter.
    Dipanggil on_update Selling Settings + tiap migrate."""
    clear_cache()
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    make_property_setter("Print Settings", "printed_by", "options", "\n".join(options()),
                         "Small Text", for_doctype=False, validate_fields_for_doctype=False)
    frappe.clear_cache(doctype="Print Settings")


def validate_single_default(doc=None, method=None):
    """Hanya satu baris boleh Default — baris terakhir yang dicentang yang menang.

    Sengaja TIDAK throw: user mencentang baris baru tanpa lebih dulu meng-uncheck yang lama
    adalah alur yang wajar; melemparnya cuma bikin form macet.
    """
    if doc is None:
        return
    rows = [r for r in (doc.get(FIELD) or []) if r.get("is_default")]
    for r in rows[:-1]:
        r.is_default = 0


def ensure_defaults():
    """Isi tabel dengan satu baris default kalau MASIH KOSONG. Idempoten."""
    ss = frappe.get_single(PARENT)
    if ss.get(FIELD):
        return
    ss.append(FIELD, {"label": DEFAULT_LABEL, "is_default": 1})
    ss.flags.ignore_permissions = True
    ss.save(ignore_permissions=True)
    clear_cache()

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

# kategori ban -> pasangan kolom di Tire KM Setting
KM_FIELDS = {
    "Radial": ("radial_min_km", "radial_std_km"),
    "Bias": ("bias_min_km", "bias_std_km"),
}
KM_VULKANISIR = ("vulkanisir_min_km", "vulkanisir_std_km")


def next_emboss(branch):
    """Nomor emboss = kode_lokasi + YYYY + MM + 5 digit, counter di-reset tiap bulan.

    Sama seperti TMS lama (TireEmbossCode): satu counter per cabang, disimpan di
    Tire Numbering. Cabang tanpa setting -> emboss diisi manual.
    """
    if not branch or not frappe.db.exists("Tire Numbering", branch):
        return None
    doc = frappe.get_doc("Tire Numbering", branch)
    today = getdate(nowdate())
    if doc.tahun != today.year or doc.bulan != today.month:
        doc.tahun, doc.bulan, doc.nomor_terakhir = today.year, today.month, 0
    doc.nomor_terakhir = (doc.nomor_terakhir or 0) + 1
    doc.save(ignore_permissions=True)
    return f"{doc.kode_lokasi}{today.year}{today.month:02d}{doc.nomor_terakhir:05d}"


class Tire(Document):
    def autoname(self):
        if not self.emboss_no:
            self.emboss_no = next_emboss(self.branch)
        if not self.emboss_no:
            frappe.throw(_("No Emboss wajib diisi (cabang ini belum punya setting Tire Numbering)."))
        self.name = self.emboss_no

    def validate(self):
        # KM minimal/standard mengikuti kategori ban (vulkanisir punya patokan sendiri)
        keys = KM_VULKANISIR if self.is_vulkanisir else KM_FIELDS.get(self.tire_category, KM_FIELDS["Radial"])
        setting = self.branch and frappe.db.get_value("Tire KM Setting", self.branch, keys, as_dict=True)
        self.km_minimal = (setting or {}).get(keys[0]) or 0
        self.km_standard = (setting or {}).get(keys[1]) or 0
        terpakai = self.total_km_tempuh or self.tire_last_km_gps or self.tire_last_km or 0
        self.sisa_km = (self.km_standard or 0) - terpakai
        if not self.vehicle:
            self.position = None
            self.vehicle_tire = None

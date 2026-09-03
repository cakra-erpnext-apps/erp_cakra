import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate

BULAN = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


class DriverSlipgaji(Document):
    def validate(self):
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw("Sampai Tanggal tidak boleh sebelum Dari Tanggal")

        self.periode = _periode(self.from_date, self.to_date)
        self.total_pendapatan = sum(flt(i.amount) for i in self.items if i.type == "Pendapatan")
        self.total_potongan = sum(flt(i.amount) for i in self.items if i.type == "Potongan")
        self.gaji_bersih = self.total_pendapatan - self.total_potongan

        if self.gaji_bersih < 0:
            frappe.throw("Potongan melebihi pendapatan, gaji bersih jadi minus")


def _periode(dari, sampai):
    """"Agustus 2026" kalau satu bulan penuh, selain itu rentang tanggalnya ditulis.

    Slip biasanya bulanan, tapi ada juga yang mingguan/borongan; jangan memaksa
    semuanya jadi nama bulan lalu menyesatkan sopir yang menerima slip mingguan.
    """
    a, b = getdate(dari), getdate(sampai)
    if (a.year, a.month) == (b.year, b.month):
        return f"{BULAN[a.month - 1]} {a.year}"
    return f"{a.strftime('%d-%m-%Y')} s/d {b.strftime('%d-%m-%Y')}"

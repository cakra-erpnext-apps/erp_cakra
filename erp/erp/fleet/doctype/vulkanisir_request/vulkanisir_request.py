import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class VulkanisirRequest(Document):
    def validate(self):
        self.total_price = sum((r.price_jasa or 0) for r in self.items)
        self.total_price_plan = sum((r.price_plan or 0) for r in self.items)
        seen = set()
        for r in self.items:
            if r.tire in seen:
                frappe.throw(_("Ban {0} dobel di baris {1}.").format(r.tire, r.idx))
            seen.add(r.tire)
            status = frappe.db.get_value("Tire", r.tire, "tire_status")
            if self.docstatus == 0 and status == "Terpasang":
                frappe.throw(_("Ban {0} masih terpasang di kendaraan — lepas dulu sebelum divulkanisir.").format(r.tire))

    def on_submit(self):
        """Approve: ban dikirim ke vendor -> status Vulkanisir (tidak bisa dipasang)."""
        self.db_set("date_approve", now_datetime(), update_modified=False)
        for r in self.items:
            frappe.db.set_value("Tire", r.tire, "tire_status", "Vulkanisir", update_modified=False)

    def on_cancel(self):
        if self.received:
            frappe.throw(_("Sudah diterima dari vendor — tidak bisa dibatalkan."))
        for r in self.items:
            frappe.db.set_value("Tire", r.tire, "tire_status", "Available", update_modified=False)

    @frappe.whitelist()
    def receive(self):
        """Terima dari vendor: emboss TETAP, vulkanisir_count +1, KM di-reset, siap dipasang lagi."""
        if self.docstatus != 1:
            frappe.throw(_("Approve (submit) dulu sebelum menerima hasil vulkanisir."))
        if self.received:
            frappe.throw(_("Dokumen ini sudah diterima."))
        for r in self.items:
            tire = frappe.get_doc("Tire", r.tire)
            tire.is_vulkanisir = 1
            tire.vulkanisir_count = (tire.vulkanisir_count or 0) + 1
            tire.tire_status = "Available"
            tire.tire_last_km = 0
            tire.tire_last_km_gps = 0
            tire.total_km_tempuh = 0
            tire.save(ignore_permissions=True)
        self.db_set("received", 1, update_modified=False)
        self.db_set("date_receive", now_datetime(), update_modified=False)
        return {"count": len(self.items)}

import frappe
from frappe import _
from frappe.model.document import Document


class VehicleJoint(Document):
    def validate(self):
        self.tires = len(self.details)
        names = [r.position_name for r in self.details]
        if len(names) != len(set(names)):
            frappe.throw(_("Nama posisi tidak boleh dobel."))


@frappe.whitelist()
def generate_vehicle_tires(vehicle=None):
    """Bikin slot posisi ban (Vehicle Tire) dari layout variant kendaraan.

    Slot yang sudah ada tidak disentuh (ban terpasang tetap aman); posisi yang hilang
    dari layout hanya dihapus kalau kosong.
    """
    filters = {"name": vehicle} if vehicle else {"disabled": 0}
    made = 0
    for v in frappe.get_all("Vehicle", filters=filters, fields=["name", "variant"]):
        joint = v.variant and frappe.db.get_value("Vehicle Variant", v.variant, "vehicle_joint")
        if not joint:
            continue
        layout = frappe.get_doc("Vehicle Joint", joint)
        wanted = {r.position_name: r for r in layout.details}
        existing = {
            r.position: r
            for r in frappe.get_all("Vehicle Tire", filters={"vehicle": v.name},
                                    fields=["name", "position", "ban_luar"])
        }
        for pos, row in wanted.items():
            if pos in existing:
                continue
            frappe.get_doc({
                "doctype": "Vehicle Tire", "vehicle": v.name, "position": pos,
                "joint_detail": row.name, "km_ganti": row.km_ganti,
            }).insert(ignore_permissions=True)
            made += 1
        for pos, row in existing.items():
            if pos not in wanted and not row.ban_luar:
                frappe.delete_doc("Vehicle Tire", row.name, ignore_permissions=True, force=True)
    return {"created": made}

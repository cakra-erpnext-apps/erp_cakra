import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

SLOTS = (("ban_luar", "ban_luar_lama"), ("ban_dalam", "ban_dalam_lama"), ("marset", "marset_lama"))


class TireOnOff(Document):
    def validate(self):
        self.total_biaya_jasa = sum((r.biaya_jasa or 0) for r in self.items)
        for r in self.items:
            if not r.vehicle_tire:
                continue
            slot = frappe.db.get_value("Vehicle Tire", r.vehicle_tire,
                                       ["vehicle", "position", "ban_luar", "ban_dalam", "marset"], as_dict=True)
            if slot.vehicle != r.vehicle:
                frappe.throw(_("Baris {0}: posisi {1} bukan milik vehicle {2}.").format(r.idx, r.position or slot.position, r.vehicle))
            r.position = slot.position
            # ban lama = apa yang SEKARANG menempel di slot itu (bukan ketikan user)
            for new_f, old_f in SLOTS:
                r.set(old_f, slot.get(new_f))
            if self.category == "Pasang" and not r.ban_luar:
                frappe.throw(_("Baris {0}: pilih Ban Luar yang dipasang.").format(r.idx))
            if self.category == "Lepas" and not slot.ban_luar:
                frappe.throw(_("Baris {0}: posisi {1} sudah kosong.").format(r.idx, r.position))
            if self.category == "Rotasi" and not r.vehicle_tire_to:
                frappe.throw(_("Baris {0}: pilih posisi tujuan rotasi.").format(r.idx))
            if self.category != "Pasang":
                r.ban_luar = r.ban_dalam = r.marset = None

    def on_submit(self):
        self.approve_date = now_datetime()
        self.approved_by = frappe.session.user
        self.db_set("approve_date", self.approve_date, update_modified=False)
        self.db_set("approved_by", self.approved_by, update_modified=False)
        for r in self.items:
            if self.category == "Rotasi":
                self._move(r.vehicle_tire, r.vehicle_tire_to, r)
            else:
                self._turun(r.vehicle_tire, r, status=r.status_lepas or "Available")
                if self.category == "Pasang":
                    self._naik(r.vehicle_tire, r, {f: r.get(f) for f, _o in SLOTS})

    def on_cancel(self):
        """Rollback: kembalikan posisi ban seperti sebelum dokumen ini di-approve."""
        for r in self.items:
            if self.category == "Rotasi":
                self._move(r.vehicle_tire_to, r.vehicle_tire, r)
                continue
            if self.category == "Pasang":
                self._turun(r.vehicle_tire, r, status="Available")
            # pasang lagi ban yang tadi diturunkan
            self._naik(r.vehicle_tire, r, {f: r.get(o) for f, o in SLOTS})

    # --- helper posisi -------------------------------------------------
    def _turun(self, slot_name, row, status="Available"):
        if not slot_name:
            return
        slot = frappe.get_doc("Vehicle Tire", slot_name)
        for f, _o in SLOTS:
            tire = slot.get(f)
            if tire and frappe.db.exists("Tire", tire):
                frappe.db.set_value("Tire", tire, {
                    "tire_status": status, "vehicle": None, "position": None, "vehicle_tire": None,
                    "tire_last_km": row.km_saat_pasang or frappe.db.get_value("Tire", tire, "tire_last_km"),
                }, update_modified=False)
            slot.set(f, None)
        slot.date_mutation = None
        slot.tire_on_off = None
        slot.save(ignore_permissions=True)

    def _naik(self, slot_name, row, tires):
        if not slot_name or not any(tires.values()):
            return
        slot = frappe.get_doc("Vehicle Tire", slot_name)
        for f, tire in tires.items():
            slot.set(f, tire)
            if tire and frappe.db.exists("Tire", tire):
                frappe.db.set_value("Tire", tire, {
                    "tire_status": "Terpasang", "vehicle": slot.vehicle,
                    "position": slot.position, "vehicle_tire": slot.name,
                }, update_modified=False)
        slot.date_mutation = self.request_date
        slot.tire_on_off = self.name
        slot.save(ignore_permissions=True)

    def _move(self, from_slot, to_slot, row):
        if not from_slot or not to_slot:
            return
        src = frappe.db.get_value("Vehicle Tire", from_slot, ["ban_luar", "ban_dalam", "marset"], as_dict=True)
        self._turun(from_slot, row, status="Available")
        self._naik(to_slot, row, dict(src))


@frappe.whitelist()
def slot_query(doctype, txt, searchfield, start, page_len, filters):
    """Link query posisi: hanya slot milik vehicle yang dipilih di baris itu."""
    vehicle = (filters or {}).get("vehicle")
    return frappe.db.sql(
        """select name, position, ifnull(ban_luar, '') from `tabVehicle Tire`
           where vehicle = %(vehicle)s and (position like %(txt)s or name like %(txt)s)
           order by position limit %(start)s, %(page_len)s""",
        {"vehicle": vehicle, "txt": f"%{txt}%", "start": start, "page_len": page_len},
    )

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# field DO Item -> field Packing List Item. Nilai fleet diinput lewat DO, lalu ditulis
# balik ke PL Item supaya report/flow lama yang membaca kolom itu tetap konsisten.
PLI_SYNC = {"driver": "driver", "vehicle": "vehicle", "atd": "atd", "ata": "driver_selesai"}


class DeliveryOrder(Document):
    def validate(self):
        for i, row in enumerate(self.items, 1):
            row.do_no = f"{self.name}-{i:02d}"
        assigned = sum(1 for r in self.items if r.assigned)
        total = len(self.items)
        pct = round(assigned * 100 / total) if total else 0
        self.assign_progress = f"{assigned}/{total} ({pct}%)"
        join = lambda vals: ", ".join(dict.fromkeys(v for v in vals if v))  # distinct, jaga urutan
        self.customer_list = join(r.customer for r in self.items)
        self.do_list = join(r.do_no for r in self.items)
        self.driver_list = join(r.driver for r in self.items)
        self.vehicle_list = join(r.vehicle for r in self.items)

    def on_update(self):
        if self.flags.from_pl_sync:
            return  # nilai baru saja di-seed DARI PL Item, tidak perlu ditulis balik
        for row in self.items:
            if row.packing_list_item and frappe.db.exists("Packing List Item", row.packing_list_item):
                frappe.db.set_value(
                    "Packing List Item",
                    row.packing_list_item,
                    # "" dari grid harus jadi NULL, kolom datetime menolak string kosong
                    {pli: row.get(do) or None for do, pli in PLI_SYNC.items()},
                    update_modified=False,
                )

    @frappe.whitelist()
    def assign(self):
        """Tandai item lengkap (driver+vehicle) sebagai assigned. Push ke aplikasi supir menyusul."""
        newly, missing = 0, []
        for row in self.items:
            if row.assigned:
                continue
            if row.atd and row.driver and row.vehicle:
                row.assigned = 1
                newly += 1
            else:
                missing.append(row.do_no or row.container_no or f"baris {row.idx}")
        if not newly:
            frappe.throw(_("Tidak ada item baru untuk di-assign. Lengkapi ATD, Driver & Vehicle dulu: {0}").format(", ".join(missing) or "-"))
        self._ensure_trip_rows()
        self.save()
        return {"assigned": newly, "missing": missing}

    def _ensure_trip_rows(self):
        """Trip log per item yang assigned: Assign -> Accept Job -> titik terisi -> Lanjut Job -> Menuju Garasi.

        Hanya item yang belum punya baris yang di-generate — baris lama (apalagi yang sudah
        berisi waktu dari aplikasi driver/GPS) tidak pernah disentuh.
        """
        # ponytail: slot route diedit setelah assign -> trip lama tidak di-regenerate; hapus baris kosong manual kalau perlu
        has_rows = {r.do_item for r in self.trip_log}
        for it in self.items:
            if not it.assigned or it.name in has_rows:
                continue
            steps = [{"step_type": "Assign", "start": now_datetime()}, {"step_type": "Accept Job"}]
            for n in range(1, 9):
                point = self.get(f"route_{n}")
                if point:
                    steps.append({"step_type": "Route", "point": point, "point_type": self.get(f"route_type_{n}") or "Route"})
            steps.append({"step_type": "Lanjut Job"})
            steps.append({"step_type": "Menuju Garasi", "point_type": "Garasi"})
            for i, s in enumerate(steps, 1):
                self.append("trip_log", {"do_item": it.name, "step": i, **s})


@frappe.whitelist()
def get_route_history(do_item):
    """Breadcrumb GPS satu job (database terpisah `history`), urut waktu, untuk playback."""
    frappe.has_permission("Delivery Order", "read", throw=True)
    return frappe.db.sql(
        """select delivery_order, driver, vehicle, latitude, longitude, recorded_at
           from history.route_history where do_item = %s order by recorded_at limit 10000""",
        (do_item,),
        as_dict=True,
    )


def sync_from_packing_list(pl, method=None):
    """Hook Packing List on_update: 1 PL = 1 Delivery Order, item DO = PL Item.

    Item PL baru -> baris DO ditambah (seed driver/vehicle/atd dari nilai lama di item),
    item dihapus -> baris DO ikut hilang, header (date/origin/dest/ETA/ETD/ETB) di-refresh.
    """
    name = frappe.db.get_value("Delivery Order", {"packing_list": pl.name}, "name")
    if not name and (pl.void or pl.closed or not pl.items):
        return
    doc = frappe.get_doc("Delivery Order", name) if name else frappe.new_doc("Delivery Order")
    doc.packing_list = pl.name
    for f in ("date", "origin_location", "destination_location", "eta", "etd", "etb"):
        doc.set(f, pl.get(f))
    by_pli = {r.packing_list_item: r for r in doc.items}
    doc.items = []
    for it in pl.items:
        row = by_pli.get(it.name)
        if row is None:
            row = doc.append("items", {
                "packing_list_item": it.name,
                "driver": it.driver,
                "vehicle": it.vehicle,
                "atd": it.atd,
                "ata": it.driver_selesai,
            })
        else:
            doc.append("items", row)
        row.container_no = it.container_no
        row.container_size = it.container_size
        row.customer = it.customer
    live_rows = {r.name for r in doc.items if r.name}
    doc.trip_log = [t for t in (doc.trip_log or []) if t.do_item in live_rows]
    doc.flags.from_pl_sync = True
    doc.save(ignore_permissions=True)


def delete_with_packing_list(pl, method=None):
    """Hook Packing List on_trash: hapus DO-nya agar PL tidak terblokir link integrity."""
    name = frappe.db.get_value("Delivery Order", {"packing_list": pl.name}, "name")
    if name:
        frappe.delete_doc("Delivery Order", name, ignore_permissions=True, force=True)

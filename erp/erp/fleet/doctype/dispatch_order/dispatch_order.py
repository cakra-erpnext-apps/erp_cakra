import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# field DPO Item -> field Packing List Item. Nilai fleet diinput lewat DPO, lalu ditulis
# balik ke PL Item supaya report/flow lama yang membaca kolom itu tetap konsisten.
PLI_SYNC = {"driver": "driver", "vehicle": "vehicle", "atd": "atd", "ata": "driver_selesai"}


class DispatchOrder(Document):
    def validate(self):
        self._lock_assigned_items()
        for i, row in enumerate(self.items, 1):
            row.dpo_no = f"{self.name}-{i:02d}"
        assigned = sum(1 for r in self.items if r.assigned)
        total = len(self.items)
        pct = round(assigned * 100 / total) if total else 0
        self.assign_progress = f"{assigned}/{total} ({pct}%)"
        join = lambda vals: ", ".join(dict.fromkeys(v for v in vals if v))  # distinct, jaga urutan
        self.customer_list = join(r.customer for r in self.items)
        self.dpo_list = join(r.dpo_no for r in self.items)
        self.driver_list = join(r.driver for r in self.items)
        self.vehicle_list = join(r.vehicle for r in self.items)

    def _lock_assigned_items(self):
        """Driver/vehicle item TERKUNCI selama masih punya trip — ganti lewat Edit Trip,
        atau hapus semua trip item itu dulu. Tombol Tambah/Edit Trip lolos via flags.trip_edit."""
        if self.is_new() or self.flags.trip_edit:
            return
        locked = {r.dpo_item for r in self.trip_log}
        if not locked:
            return
        old = {
            d.name: d
            for d in frappe.get_all(
                "Dispatch Order Item", filters={"parent": self.name}, fields=["name", "driver", "vehicle", "chasis"]
            )
        }
        for it in self.items:
            o = old.get(it.name)
            if not o or it.name not in locked:
                continue
            if (
                (it.driver or None) != (o.driver or None)
                or (it.vehicle or None) != (o.vehicle or None)
                or (it.chasis or None) != (o.chasis or None)
            ):
                frappe.throw(
                    _("Driver/Vehicle/Chasis {0} terkunci karena sudah di-assign dan punya trip. "
                      "Ubah lewat tombol Edit Trip, atau hapus semua trip item itu dulu.").format(it.dpo_no or it.container_no)
                )

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
                missing.append(row.dpo_no or row.container_no or f"baris {row.idx}")
        if not newly:
            frappe.throw(_("Tidak ada item baru untuk di-assign. Lengkapi ATD, Driver & Vehicle dulu: {0}").format(", ".join(missing) or "-"))
        self._ensure_trip_rows()
        self.save()
        return {"assigned": newly, "missing": missing}

    def _trip_steps(self):
        """Urutan step satu trip: Assign -> Accept Job -> titik terisi -> Lanjut Job -> Menuju Garasi.
        Berlaku SAMA untuk semua trip (langsir maupun bukan) — centang Langsir per titik hanya
        penanda concern, bukan pemangkas step."""
        steps = [{"step_type": "Assign", "start": now_datetime()}, {"step_type": "Accept Job"}]
        for n in range(1, 9):
            point = self.get(f"route_{n}")
            if point:
                steps.append({"step_type": "Route", "point": point, "point_type": self.get(f"route_type_{n}") or "Route"})
        steps.append({"step_type": "Lanjut Job"})
        steps.append({"step_type": "Menuju Garasi", "point_type": "Garasi"})
        return steps

    def _append_trip(self, dpo_item, trip, driver, vehicle, chasis=None):
        for i, s in enumerate(self._trip_steps(), 1):
            self.append("trip_log", {"dpo_item": dpo_item, "trip": trip, "driver": driver, "vehicle": vehicle,
                                     "chasis": chasis, "step": i, **s})

    def _ensure_trip_rows(self):
        """Trip 1 per item yang assigned (selalu rute penuh dari posisi awal). Hanya item tanpa
        baris yang di-generate — baris lama (berisi waktu dari driver/GPS) tidak disentuh."""
        # ponytail: slot route diedit setelah assign -> trip lama tidak di-regenerate; hapus baris kosong manual kalau perlu
        has_rows = {r.dpo_item for r in self.trip_log}
        for it in self.items:
            if not it.assigned or it.name in has_rows:
                continue
            self._append_trip(it.name, 1, it.driver, it.vehicle, it.chasis)

    @frappe.whitelist()
    def add_trip(self, dpo_item, driver=None, vehicle=None, chasis=None):
        """Ritase tambahan: SELALU mengulang seluruh step titik yang sama (termasuk PL langsir);
        driver/nopol/chasis boleh beda per trip. Laporan trip dari driver dicatat mandor/CS
        lewat tombol ini, nanti otomatis dari aplikasi driver."""
        it = next((r for r in self.items if r.name == dpo_item), None)
        if not it or not it.assigned:
            frappe.throw(_("Item belum di-assign — assign dulu sebelum menambah trip."))
        last = max((r.trip or 1 for r in self.trip_log if r.dpo_item == dpo_item), default=0)
        self._append_trip(dpo_item, last + 1, driver or it.driver, vehicle or it.vehicle, chasis or it.chasis)
        # ritase baru: data item di-reset kecuali ATD — ATA dikosongkan (belum selesai lagi),
        # driver/vehicle/chasis mengikuti trip baru (ikut tersinkron balik ke PL Item saat save)
        it.ata = None
        it.driver = driver or it.driver
        it.vehicle = vehicle or it.vehicle
        it.chasis = chasis or it.chasis
        self.flags.trip_edit = True
        self.save()
        self.flags.trip_edit = False
        return {"trip": last + 1}

    @frappe.whitelist()
    def edit_trip(self, dpo_item, trip, driver=None, vehicle=None, chasis=None):
        """Ganti driver/vehicle/chasis satu trip. Tercatat di Activity via track_changes (row_changed)."""
        trip = int(trip)
        rows = [r for r in self.trip_log if r.dpo_item == dpo_item and (r.trip or 1) == trip]
        if not rows:
            frappe.throw(_("Trip {0} tidak ditemukan.").format(trip))
        for r in rows:
            r.driver = driver
            r.vehicle = vehicle
            r.chasis = chasis
        it = next((r for r in self.items if r.name == dpo_item), None)
        if it and trip == max((r.trip or 1) for r in self.trip_log if r.dpo_item == dpo_item):
            it.driver = driver  # trip terakhir = kondisi berjalan -> item (dan PL Item) ikut
            it.vehicle = vehicle
            it.chasis = chasis
        self.flags.trip_edit = True
        self.save()
        self.flags.trip_edit = False

    @frappe.whitelist()
    def delete_trip(self, dpo_item, trip):
        """Hapus satu trip (semua step-nya). Tercatat di Activity via track_changes (row removed),
        dan seluruh step-nya DIARSIP dulu ke history.dispatch_order_history (bahan pemeriksaan).
        Nomor trip lain TIDAK digeser supaya tetap nyambung dengan jejak di history.route_history."""
        trip = int(trip)
        removed = [r for r in self.trip_log if r.dpo_item == dpo_item and (r.trip or 1) == trip]
        if not removed:
            frappe.throw(_("Trip {0} tidak ditemukan.").format(trip))
        it = next((r for r in self.items if r.name == dpo_item), None)
        now = now_datetime()
        for r in removed:
            frappe.db.sql(
                """insert into history.dispatch_order_history
                   (dispatch_order, dpo_no, dpo_item, trip, driver, vehicle, chasis, step, step_type,
                    point_type, point, start, end, deleted_by, deleted_at)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (self.name, it and it.dpo_no, r.dpo_item, r.trip or 1, r.driver, r.vehicle, r.chasis, r.step,
                 r.step_type, r.point_type, r.point, r.start, r.end, frappe.session.user, now),
            )
        self.trip_log = [r for r in self.trip_log if not (r.dpo_item == dpo_item and (r.trip or 1) == trip)]
        self.save()


@frappe.whitelist()
def get_route_history(dpo_item, trip=1):
    """Breadcrumb GPS satu trip (database terpisah `history`), urut waktu, untuk playback."""
    frappe.has_permission("Dispatch Order", "read", throw=True)
    return frappe.db.sql(
        """select dispatch_order, driver, vehicle, latitude, longitude, recorded_at
           from history.route_history where dpo_item = %s and trip = %s
           order by recorded_at limit 10000""",
        (dpo_item, int(trip or 1)),
        as_dict=True,
    )


def sync_from_packing_list(pl, method=None):
    """Hook Packing List on_update: 1 PL = 1 Dispatch Order, item DPO = PL Item.

    Item PL baru -> baris DPO ditambah (seed driver/vehicle/atd dari nilai lama di item),
    item dihapus -> baris DPO ikut hilang, header (date/origin/dest/ETA/ETD/ETB) di-refresh.
    """
    name = frappe.db.get_value("Dispatch Order", {"packing_list": pl.name}, "name")
    if not name and (pl.void or pl.closed or not pl.items):
        return
    doc = frappe.get_doc("Dispatch Order", name) if name else frappe.new_doc("Dispatch Order")
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
    doc.trip_log = [t for t in (doc.trip_log or []) if t.dpo_item in live_rows]
    doc.flags.from_pl_sync = True
    doc.save(ignore_permissions=True)


def delete_with_packing_list(pl, method=None):
    """Hook Packing List on_trash: hapus DPO-nya agar PL tidak terblokir link integrity."""
    name = frappe.db.get_value("Dispatch Order", {"packing_list": pl.name}, "name")
    if name:
        frappe.delete_doc("Dispatch Order", name, ignore_permissions=True, force=True)

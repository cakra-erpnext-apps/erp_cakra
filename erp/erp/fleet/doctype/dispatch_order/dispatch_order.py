import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, getdate, now_datetime, nowdate

# field DPO Item -> field Packing List Item. Nilai fleet diinput lewat DPO, lalu ditulis
# balik ke PL Item supaya report/flow lama yang membaca kolom itu tetap konsisten.
PLI_SYNC = {"driver": "driver", "vehicle": "vehicle", "atd": "atd", "ata": "driver_selesai"}


class DispatchOrder(Document):
    def before_insert(self):
        # owner/creation bawaan Frappe tidak bisa dijadikan kolom list view (bukan bagian
        # meta.fields), jadi disalin ke field sendiri sekali saat dibuat
        self.created_by_user = frappe.session.user
        self.created_on = now_datetime()

    def validate(self):
        self._restore_trip_log()
        self._lock_assigned_items()
        for i, row in enumerate(self.items, 1):
            row.dpo_no = f"{self.name}-{i:02d}"
        self._ensure_trip_rows()
        self._rollup_trip_dates()
        self._require_atd()
        self._check_date_order()
        self._no_double_assignment()
        self._no_vehicle_overlap()
        self._sync_open_trips()
        assigned = sum(1 for r in self.items if r.assigned)
        total = len(self.items)
        pct = round(assigned * 100 / total) if total else 0
        self.assign_progress = f"{assigned}/{total} ({pct}%)"
        join = lambda vals: ", ".join(dict.fromkeys(v for v in vals if v))  # distinct, jaga urutan
        self.customer_list = join(r.customer for r in self.items)
        self.dpo_list = join(r.dpo_no for r in self.items)
        self.driver_list = join(r.driver for r in self.items)
        self.vehicle_list = join(r.vehicle for r in self.items)

    def _trips(self, dpo_item=None):
        """Ritase sebagai satu kesatuan: (dpo_item, trip) -> baris-baris step miliknya."""
        out = {}
        for t in self.trip_log:
            if dpo_item and t.dpo_item != dpo_item:
                continue
            out.setdefault((t.dpo_item, t.trip or 1), []).append(t)
        return out

    def _rollup_trip_dates(self):
        """ATD/ATA sumbernya RITASE (Dispatch Order Route); nilai di baris Items adalah
        turunannya: ATD paling awal, ATA paling akhir dan hanya kalau SEMUA ritase selesai.

        Tapi user mengetiknya di grid Items, bukan di dialog trip. Jadi arahnya dua langkah:
        kalau nilai di grid BERUBAH dari yang tersimpan, perubahan itu diturunkan dulu ke
        ritase — ATD ke ritase PERTAMA, ATA ke ritase TERAKHIR, sejalan dengan definisi
        turunannya — baru sesudah itu dihitung ulang. Tanpa ini, revisi tanggal lewat grid
        (yang pasti terjadi tiap tutup bulan) akan ditimpa balik tanpa pesan apa pun."""
        lama = (
            {}
            if self.is_new()
            else {
                d.name: d
                for d in frappe.get_all(
                    "Dispatch Order Item", filters={"parent": self.name}, fields=["name", "atd", "ata"]
                )
            }
        )
        norm = lambda v: getdate(v) if v else None
        for it in self.items:
            rows = self._trips(it.name)
            if not rows:
                continue  # belum ada ritase -> isian grid dipakai apa adanya
            urut = sorted(rows.items(), key=lambda kv: kv[0][1])
            o = lama.get(it.name)
            if o and norm(it.atd) != norm(o.atd):
                for t in urut[0][1]:  # ritase pertama
                    t.atd = it.atd or None
            if o and norm(it.ata) != norm(o.ata):
                for t in urut[-1][1]:  # ritase terakhir
                    t.ata = it.ata or None
            heads = [r[0] for _k, r in urut]
            atds = [getdate(h.atd) for h in heads if h.atd]
            atas = [getdate(h.ata) for h in heads if h.ata]
            it.atd = min(atds) if atds else None
            it.ata = max(atas) if atas and len(atas) == len(heads) else None

    def _row_label(self, row):
        return row.dpo_no or row.container_no or f"baris {row.idx}"

    def _require_atd(self):
        """ATD adalah dasar semua pengecekan tanggal, jadi tidak boleh kosong begitu barisnya
        sudah diisi ATA / Driver / Vehicle."""
        if self.flags.from_pl_sync:
            return
        label = {r.name: self._row_label(r) for r in self.items}
        missing = [self._row_label(r) for r in self.items if not r.atd and (r.ata or r.driver or r.vehicle)]
        missing += [
            f"{label.get(dpo_item, dpo_item)} trip {trip}"
            for (dpo_item, trip), rows in self._trips().items()
            if not rows[0].atd and (rows[0].ata or rows[0].driver or rows[0].vehicle)
        ]
        if missing:
            frappe.throw(_("ATD harus diisi: {0}").format(", ".join(dict.fromkeys(missing))))

    def _check_date_order(self):
        """ATA tidak boleh mendahului ATD. Gampang terjadi saat revisi tanggal borongan di
        grid: ATD digeser maju melewati ATA ritase yang sudah tercatat."""
        if self.flags.from_pl_sync:
            return
        label = {r.name: self._row_label(r) for r in self.items}
        salah = [
            f"{label.get(dpo_item, dpo_item)} trip {trip}"
            for (dpo_item, trip), rows in self._trips().items()
            if rows[0].atd and rows[0].ata and getdate(rows[0].ata) < getdate(rows[0].atd)
        ]
        salah += [
            self._row_label(r)
            for r in self.items
            if not self._trips(r.name) and r.atd and r.ata and getdate(r.ata) < getdate(r.atd)
        ]
        if salah:
            frappe.throw(_("ATA tidak boleh lebih awal dari ATD: {0}").format(", ".join(dict.fromkeys(salah))))

    def _no_double_assignment(self):
        """1 vehicle = 1 job berjalan. Boleh muncul di beberapa baris ASAL baris lamanya
        sudah ber-ATA (job selesai); dua baris tanpa ATA berarti truknya disuruh jalan dua
        kali sekaligus. Driver TIDAK ikut diperiksa di sini.

        Dilewati saat sync dari Packing List: sync tidak mengubah driver/vehicle, dan kalau
        data lama sudah telanjur double, error di sini akan ikut memblokir penyimpanan PL-nya."""
        if self.flags.from_pl_sync:
            return
        # SENGAJA vehicle saja: satu truk tidak bisa berada di dua tempat, sedangkan driver
        # bisa berganti kendaraan atau tugas tanpa melanggar apa pun secara fisik
        for field, doctype, label in (("vehicle", "Vehicle", _("Vehicle")),):
            # dikelompokkan per CONTAINER: beberapa ritase dari container yang sama itu wajar
            # (berurutan, bukan barengan); yang dilarang adalah dua container berbeda sekaligus
            combo_of = {
                dpo_item: rows[0].combo
                for (dpo_item, _t), rows in self._trips().items()
                if rows[0].combo and not rows[0].ata
            }
            open_rows = {}
            for row in self.items:
                if row.get(field) and not row.ata:
                    # 1 truk bawa 2 container sekaligus (combo) = satu pekerjaan, bukan dua
                    kunci = combo_of.get(row.name) or row.packing_list_item
                    open_rows.setdefault(row.get(field), {}).setdefault(kunci, self._row_label(row))
            dupes = [(v, list(r.values())) for v, r in open_rows.items() if len(r) > 1]
            if dupes:
                frappe.throw(
                    "<br>".join(
                        _("{0} {1} dipakai di {2} tanpa ATA.").format(
                            label, frappe.db.get_value(doctype, v, "title") or v, ", ".join(rows)
                        )
                        for v, rows in dupes
                    )
                    + "<br><br>"
                    + _("Satu {0} hanya boleh punya satu job berjalan. Isi ATA job sebelumnya dulu, atau ganti {0}-nya.").format(
                        label.lower()
                    )
                )

    def _vehicle_jobs(self):
        """Ritase vehicle dari DPO LAIN, diambil SEKALI per save. Yang dibandingkan rentang
        ATD-ATA per RITASE (Dispatch Order Route), bukan rentang container, karena satu
        container bisa punya beberapa ritase dengan tanggal dan nopol berbeda.

        Dibatasi jendela tanggal ATD dokumen ini: ritase yang bisa bertabrakan pasti
        ATA >= ATD paling awal DAN ATD <= ATD paling akhir. Riwayat lama tidak ikut ditarik."""
        dates = [getdate(r.atd) for r in self._trip_heads() if r.atd]
        vehs = {r.vehicle for r in self._trip_heads() if r.vehicle and r.atd}
        if not vehs or not dates:
            return {}
        out = {}
        for r in frappe.db.sql(
            """select t.vehicle, i.dpo_no, t.trip, t.atd, t.ata, t.combo
               from `tabDispatch Order Route` t
               join `tabDispatch Order Item` i on i.name = t.dpo_item
               where t.vehicle in %(v)s and t.parent != %(p)s and t.step = 1 and t.atd is not null
                 and ifnull(t.ata, '2999-12-31') >= %(lo)s and t.atd <= %(hi)s""",
            {"v": list(vehs), "p": self.name, "lo": min(dates), "hi": max(dates)},
            as_dict=True,
        ):
            out.setdefault(r.vehicle, []).append(r)
        return out

    def _trip_heads(self):
        """Satu wakil per ritase (step 1), pembawa driver/vehicle/ATD/ATA ritase itu."""
        return [rows[0] for rows in self._trips().values()]

    def _no_vehicle_overlap(self):
        """Satu vehicle tidak boleh mengerjakan dua ritase yang waktunya beririsan — truknya
        tidak bisa berada di dua tempat sekaligus.

        Irisan diuji DUA ARAH: max(ATD) < min(ATA). Dengan begitu tidak peduli mana yang
        diisi lebih dulu, 1-10 lawan 2-3 tetap ketahuan — pemeriksaan lama hanya menguji ATD
        yang baru diketik terhadap rentang orang lain, jadi urutan terbalik bisa lolos.

        Ritase tanpa ATA dianggap masih berjalan (rentangnya terbuka), sedangkan sentuhan di
        batas dibiarkan lolos: ATD/ATA tanpa jam, jadi selesai satu ritase lalu mulai ritase
        lain di hari yang sama itu wajar, termasuk ritase yang ATD dan ATA-nya sehari."""
        if self.flags.from_pl_sync:
            return
        AKHIR = getdate("2999-12-31")  # ritase belum ber-ATA = masih jalan
        other = self._vehicle_jobs()
        label = {r.name: self._row_label(r) for r in self.items}
        nama = lambda r: f"{label.get(r.dpo_item, r.dpo_item)} trip {r.trip or 1}" if r.get("dpo_item") else             f"{r.dpo_no} trip {r.trip or 1}"
        heads = self._trip_heads()
        for row in heads:
            if not (row.vehicle and row.atd):
                continue
            a1, b1 = getdate(row.atd), getdate(row.ata) if row.ata else AKHIR
            pool = [r for r in heads if r is not row and r.vehicle == row.vehicle and r.atd] + other.get(row.vehicle, [])
            for c in pool:
                if row.combo and row.combo == c.combo:
                    continue  # satu combo = satu perjalanan truk yang sama
                a2, b2 = getdate(c.atd), getdate(c.ata) if c.ata else AKHIR
                if max(a1, a2) >= min(b1, b2):  # bersentuhan di batas = bukan bentrok
                    continue
                b = lambda v: f"<b>{frappe.utils.escape_html(str(v))}</b>"
                tgl = lambda x: formatdate(x, "dd-MM-yyyy") if x else _("belum selesai")
                job = b(nama(c))
                frappe.throw(
                    _("{v} ini tidak bisa di assign pada tanggal {t} karena sedang mengerjakan job {j} - {r}.").format(
                        v=b(row.vehicle), t=b(tgl(row.atd)), j=job, r=b(f"{tgl(c.atd)} - {tgl(c.ata)}")
                    )
                    + "<br><br>"
                    + _("Jika {v} memang melakukan pekerjaan di tanggal {t} maka revisi tanggal ATD dan ATA {j}").format(
                        v=b(row.vehicle), t=b(tgl(row.atd)), j=job
                    )
                )

    def _restore_trip_log(self):
        """Field trip_log sengaja hidden, jadi payload save dari form bisa datang TANPA isi
        tabelnya — kalau dituruti, satu save biasa menghapus semua trip (dan bikin
        _lock_assigned_items ikut buta). Selain lewat tombol trip, trip yang sudah ada di DB
        selalu dipakai ulang."""
        if self.is_new() or self.flags.trip_edit or self.trip_log:
            return
        for r in frappe.get_all(
            "Dispatch Order Route", filters={"parent": self.name}, fields=["*"], order_by="idx"
        ):
            self.append("trip_log", r)

    def _lock_assigned_items(self):
        """Driver/Vehicle/Chasis terkunci begitu ATA terisi — job sudah selesai, isinya jadi
        catatan sejarah. Selama ATA masih kosong baris boleh direvisi langsung di grid walau
        sudah di-assign; trip yang sedang berjalan ikut disesuaikan (lihat _sync_open_trips)."""
        if self.is_new() or self.flags.trip_edit:
            return
        old = {
            d.name: d
            for d in frappe.get_all(
                "Dispatch Order Item",
                filters={"parent": self.name},
                fields=["name", "driver", "vehicle", "chasis", "ata"],
            )
        }
        for it in self.items:
            o = old.get(it.name)
            if not o or not o.ata:  # ATA belum terisi di DB -> masih boleh diubah
                continue
            if (
                (it.driver or None) != (o.driver or None)
                or (it.vehicle or None) != (o.vehicle or None)
                or (it.chasis or None) != (o.chasis or None)
            ):
                frappe.throw(
                    _("Driver/Vehicle/Chasis {0} terkunci karena ATA-nya sudah terisi (job selesai). "
                      "Kosongkan ATA dulu kalau memang perlu diperbaiki.").format(it.dpo_no or it.container_no)
                )

    def _sync_open_trips(self):
        """Baris yang belum ber-ATA masih boleh diubah di grid; trip miliknya ikut supaya
        matriks Route tidak menampilkan driver/nopol yang sudah basi."""
        for it in self.items:
            if it.ata:
                continue
            rows = [t for t in self.trip_log if t.dpo_item == it.name]
            if not rows:
                continue
            akhir = max(t.trip or 1 for t in rows)
            for t in rows:
                if (t.trip or 1) == akhir:  # ritase lama menyimpan nopol/driver-nya sendiri
                    t.driver, t.vehicle, t.chasis = it.driver, it.vehicle, it.chasis

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
        """Tandai item lengkap (driver+vehicle) sebagai assigned, lalu beri tahu supirnya."""
        newly, missing, baru = 0, [], []
        has_trip = {r.dpo_item for r in self.trip_log}
        for row in self.items:
            # assigned tapi tripnya sudah habis dihapus = anggap belum, biar bisa di-assign ulang
            if row.assigned and row.name in has_trip:
                continue
            if row.atd and row.driver and row.vehicle:
                row.assigned = 1
                newly += 1
                baru.append(row)
            else:
                missing.append(row.dpo_no or row.container_no or f"baris {row.idx}")
        if not newly:
            frappe.throw(
                _("Lengkapi ATD, Driver & Vehicle dulu: {0}").format(", ".join(missing))
                if missing
                else _("Semua item sudah di-assign.")
            )
        self._ensure_trip_rows()
        self.save()

        # Setelah save, bukan sebelum: kalau save gagal, notifikasinya sudah
        # terkirim dan supir menunggu job yang tidak pernah ada.
        from erp.fleet.api.mobile_driver import notify_job_assigned

        notify_job_assigned(self, baru)
        return {"assigned": newly, "missing": missing}

    def _trip_steps(self, assign_start=None):
        """Urutan step satu trip: Assign -> Accept Job -> titik terisi -> Lanjut Job -> Menuju Garasi.
        Berlaku SAMA untuk semua trip (langsir maupun bukan) — centang Langsir per titik hanya
        penanda concern, bukan pemangkas step."""
        steps = [{"step_type": "Assign", "start": assign_start}, {"step_type": "Accept Job"}]
        for n in range(1, 9):
            point = self.get(f"route_{n}")
            if point:
                steps.append({"step_type": "Route", "point": point, "point_type": self.get(f"route_type_{n}") or "Route"})
        steps.append({"step_type": "Lanjut Job"})
        steps.append({"step_type": "Menuju Garasi", "point_type": "Garasi"})
        return steps

    def _append_trip(self, dpo_item, trip, driver, vehicle, chasis=None, atd=None, ata=None, combo=None,
                     assign_start=None):
        for i, s in enumerate(self._trip_steps(assign_start), 1):
            self.append("trip_log", {"dpo_item": dpo_item, "trip": trip, "driver": driver, "vehicle": vehicle,
                                     "chasis": chasis, "atd": atd, "ata": ata, "combo": combo, "step": i, **s})

    def _ensure_trip_rows(self):
        """Setiap container (Packing List Item) langsung punya ritase 1, terisi atau belum.

        Dengan begitu tabel Trip menampilkan seluruh container sejak awal dan tinggal diklik
        untuk mengisi driver/nopol/ATD — tidak perlu menekan Tambah Trip dulu untuk ritase
        pertama. Step Assign SENGAJA tanpa stempel waktu sampai ritasenya benar-benar
        diserahkan, supaya kolom Job Diberikan tidak berbohong."""
        # ponytail: slot route diedit setelah assign -> trip lama tidak di-regenerate; hapus baris kosong manual kalau perlu
        has_rows = {r.dpo_item for r in self.trip_log}
        for it in self.items:
            if it.name in has_rows:
                continue
            self._append_trip(
                it.name, 1, it.driver, it.vehicle, it.chasis, it.atd, it.ata,
                assign_start=now_datetime() if it.assigned else None,
            )

    def _combo_join(self, driver, vehicle, atd, kecuali=None):
        """Nomor combo untuk ritase yang menempel pada perjalanan yang SEDANG berjalan milik
        driver+nopol ini. Syaratnya ketat: driver, nopol, DAN tanggal berangkat harus sama —
        kalau ATD-nya beda berarti itu perjalanan lain, bukan satu truk membawa dua container.

        Satu truk maksimal dua container, jadi perjalanan yang sudah bernomor combo ditolak."""
        jalan = [
            r for r in self.trip_log
            if r.step == 1 and not r.ata and r.driver == driver and r.vehicle == vehicle
            and r.atd and getdate(r.atd) == getdate(atd)
            and (not kecuali or (r.dpo_item, r.trip or 1) != kecuali)
        ]
        if not jalan:
            frappe.throw(
                _("Tidak ada ritase berjalan milik {0} dengan nopol {1} dan ATD {2} untuk digabung combo.").format(
                    frappe.db.get_value("Driver", driver, "title") or driver,
                    vehicle,
                    formatdate(atd, "dd-MM-yyyy"),
                )
            )
        if jalan[0].combo:
            frappe.throw(
                _("{0} sudah combo di perjalanan ini — satu truk hanya boleh membawa dua container.").format(
                    frappe.db.get_value("Driver", driver, "title") or driver
                )
            )
        combo = frappe.generate_hash(length=8)
        pasangan = {(j.dpo_item, j.trip or 1) for j in jalan}
        for r in self.trip_log:
            if (r.dpo_item, r.trip or 1) in pasangan:
                r.combo = combo
        return combo

    @frappe.whitelist()
    def add_trip(self, dpo_item=None, driver=None, vehicle=None, chasis=None, atd=None, ata=None,
                 dpo_items=None, combo_join=0):
        """Ritase baru: baris step di Dispatch Order Route dengan nomor trip berikutnya.
        Baris Items TIDAK bertambah — tetap 1:1 dengan Packing List Item.

        Hanya SATU container per pemanggilan — gunanya untuk langsir atau kasus khusus.
        Combo (1 truk 2 container) dibuat lewat centang Combo di Edit Trip, bukan dari sini.

        Ritase pertama sekaligus menandai barisnya assigned."""
        target = frappe.parse_json(dpo_items) if dpo_items else ([dpo_item] if dpo_item else [])
        target = [t for t in dict.fromkeys(target) if t]
        if not target:
            frappe.throw(_("Pilih container dulu."))
        # Tambah Trip = ritase tambahan untuk SATU container (langsir / kasus khusus).
        # Combo tidak dibuat dari sini, melainkan lewat centang Combo di Edit Trip.
        if len(target) > 1:
            frappe.throw(_("Tambah Trip hanya untuk satu container."))
        if not atd:
            frappe.throw(_("ATD wajib diisi."))
        combo = self._combo_join(driver, vehicle, atd) if cint(combo_join) else None

        hasil = []
        for name in target:
            it = next((r for r in self.items if r.name == name), None)
            if not it:
                frappe.throw(_("Baris item tidak ditemukan."))
            trips = [r.trip or 1 for r in self.trip_log if r.dpo_item == name]
            trip = max(trips) + 1 if trips else 1
            it.assigned = 1 if (driver and vehicle) else it.assigned
            self._append_trip(name, trip, driver, vehicle, chasis or it.chasis, atd, ata or None, combo,
                              assign_start=now_datetime() if (driver and vehicle) else None)
            if driver:
                it.driver = driver
            if vehicle:
                it.vehicle = vehicle
            if chasis:
                it.chasis = chasis
            hasil.append({"container": it.container_no, "trip": trip})
        self.flags.trip_edit = True
        self.save()
        self.flags.trip_edit = False
        return {"combo": combo, "trip": hasil[0]["trip"], "rows": hasil}

    @frappe.whitelist()
    def edit_trip(self, dpo_item, trip, driver=None, vehicle=None, chasis=None, atd=None, ata=None,
                  combo_join=0):
        """Ganti driver/vehicle/chasis satu trip, plus ATD/ATA item-nya. Tercatat di Activity
        via track_changes (row_changed).

        ATD/ATA milik RITASE ini; nilai di baris Items diturunkan ulang saat save
        (lihat _rollup_trip_dates). Driver/vehicle/chasis ikut ke Items hanya kalau ini
        ritase terakhir, karena itulah kondisi yang sedang berjalan."""
        trip = int(trip)
        rows = [r for r in self.trip_log if r.dpo_item == dpo_item and (r.trip or 1) == trip]
        if not rows:
            frappe.throw(_("Trip {0} tidak ditemukan.").format(trip))
        # combo = satu truk, jadi ganti driver/nopol/chasis berlaku untuk semua anggotanya
        combo = rows[0].combo
        if combo:
            rows = [r for r in self.trip_log if r.combo == combo]
        for r in rows:
            r.driver = driver
            r.vehicle = vehicle
            r.chasis = chasis
        for r in rows:
            r.atd = atd or None  # "" dari dialog harus jadi NULL, kolom tanggal menolak string kosong
            r.ata = ata or None
        if cint(combo_join) and not rows[0].combo:
            gabung = self._combo_join(driver, vehicle, atd, kecuali=(dpo_item, trip))
            for r in rows:
                r.combo = gabung
        # ritase yang baru lengkap (driver+nopol+ATD) = baru diserahkan: stempel waktunya diisi
        for r in rows:
            if r.step_type == "Assign" and not r.start and r.driver and r.vehicle and r.atd:
                r.start = now_datetime()
        for r in rows:
            baris = next((x for x in self.items if x.name == r.dpo_item), None)
            if baris and r.driver and r.vehicle and r.atd:
                baris.assigned = 1
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
        combo = removed[0].combo
        if combo:  # satu perjalanan dihapus utuh, tidak menyisakan separuh combo
            removed = [r for r in self.trip_log if r.combo == combo]
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
        buang = {id(r) for r in removed}
        self.trip_log = [r for r in self.trip_log if id(r) not in buang]
        for r in removed:  # tiap container yang ritasenya habis kembali belum-assigned
            baris = next((x for x in self.items if x.name == r.dpo_item), None)
            if baris and not any(t.dpo_item == baris.name for t in self.trip_log):
                baris.assigned = 0
        self.flags.trip_edit = True
        self.save()
        self.flags.trip_edit = False


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


@frappe.whitelist()
def available_drivers(branch=None, include_busy=0):
    """Driver yang boleh dipilih di DPO -> nopol check-in terakhirnya hari ini.

    Syarat, semuanya harus terpenuhi:
    1. sudah Check In HARI INI (check-in kemarin tidak terbawa, query difilter per tanggal);
    2. branch-nya sama dengan branch DPO (ikut Branch Office di Packing List);
    3. tidak sedang jalan — tidak ada job assigned yang ATA-nya masih kosong. Kewajiban
       check in ulang tiap selesai job sudah dijamin syarat 1, karena check-in kemarin
       tidak terbawa ke hari ini;
    4. driver baru yang belum pernah punya job lolos syarat 3 dengan sendirinya.
    """
    frappe.has_permission("Dispatch Order", "read", throw=True)
    checkin = {}
    for r in frappe.db.sql(
        """select driver, timestamp, vehicle from `tabDriver Attendance`
           where type = 'Check In' and date(timestamp) = %s order by timestamp""",
        (nowdate(),),
        as_dict=True,
    ):
        checkin[r.driver] = r  # check-in TERAKHIR hari ini yang dipakai
    if not checkin:
        return {}

    filters = {"name": ("in", list(checkin)), "disabled": 0}
    if branch:
        filters["branch"] = branch
    names = frappe.get_all("Driver", filters=filters, pluck="name")
    if not names:
        return {}

    # driver yang masih punya job BELUM SELESAI (ATA kosong) tidak boleh dipakai lagi
    sibuk = {
        r.driver
        for r in frappe.db.sql(
            """select distinct driver from `tabDispatch Order Item`
               where assigned = 1 and ata is null and driver in %(d)s""",
            {"d": names},
            as_dict=True,
        )
    }
    # Syarat "check in lagi setelah selesai job" sudah terpenuhi dengan sendirinya oleh
    # syarat 1 (check in HARI INI). Membandingkan check-in dengan tanggal ATA justru salah:
    # ATA boleh berupa rencana di masa depan, dan itu bikin semua driver hilang dari daftar.
    # include_busy dipakai mode COMBO: driver yang sedang menarik container lain boleh
    # dipilih lagi, karena truknya memang membawa keduanya dalam satu perjalanan
    if not cint(include_busy):
        return {d: checkin[d].vehicle or "" for d in names if d not in sibuk}

    # Mode COMBO: driver yang sedang menarik container lain boleh dipilih lagi, TAPI hanya
    # sekali — begitu ritase berjalannya sudah punya nomor combo, truknya sudah penuh.
    sudah_combo = {
        r.driver
        for r in frappe.db.sql(
            """select distinct t.driver from `tabDispatch Order Route` t
               where t.step = 1 and t.ata is null and ifnull(t.combo, '') != ''
                 and t.driver in %(d)s""",
            {"d": names},
            as_dict=True,
        )
    }
    return {d: checkin[d].vehicle or "" for d in names if d not in sudah_combo}


ROUTE_SLOTS = 8


def _seed_routes(doc, pl):
    """Route DPO = salinan grid Route di PL. Jenis Langsir jadi centang Langsir (jenisnya
    tetap Route), origin/dest ditandai dari header PL. Berhenti menyalin begitu trip pertama
    dibuat supaya urutan step trip yang sudah jalan tidak ikut berubah."""
    if doc.trip_log:
        return
    points = [r for r in (pl.routes or []) if r.location][:ROUTE_SLOTS]
    for n in range(1, ROUTE_SLOTS + 1):
        r = points[n - 1] if n <= len(points) else None
        doc.set(f"route_type_{n}", ("Depo" if r.jenis == "Depo" else "Route") if r else None)
        doc.set(f"route_{n}", r.location if r else None)
        doc.set(f"route_langsir_{n}", 1 if r and r.jenis == "Langsir" else 0)
        doc.set(f"route_origin_{n}", 0)
        doc.set(f"route_dest_{n}", 0)
    if not points:
        return
    locs = [r.location for r in points]
    origin = locs.index(pl.origin_location) if pl.origin_location in locs else 0
    dest = (len(locs) - 1 - locs[::-1].index(pl.destination_location)
            if pl.destination_location in locs else len(locs) - 1)
    doc.set(f"route_origin_{origin + 1}", 1)
    doc.set(f"route_dest_{dest + 1}", 1)


def sync_from_packing_list(pl, method=None):
    """Hook Packing List on_update: 1 PL = 1 Dispatch Order, item DPO = PL Item.

    Item PL baru -> baris DPO ditambah (seed driver/vehicle/atd dari nilai lama di item),
    item dihapus -> baris DPO ikut hilang, header (date/origin/dest/ETA/ETD/ETB) + route di-refresh.
    """
    name = frappe.db.get_value("Dispatch Order", {"packing_list": pl.name}, "name")
    if not name and (pl.void or pl.closed or not pl.items):
        return
    doc = frappe.get_doc("Dispatch Order", name) if name else frappe.new_doc("Dispatch Order")
    doc.packing_list = pl.name
    doc.branch = pl.branch_office
    doc.customer = pl.customer
    doc.packing_list_date = pl.date
    for f in ("origin_location", "destination_location", "eta", "etd", "etb"):
        doc.set(f, pl.get(f))
    _seed_routes(doc, pl)
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

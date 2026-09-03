# Modul Fleet

Blueprint modul Fleet: dari Packing List sampai Maintenance kendaraan. Berisi alur,
daftar field tiap doctype, aturan yang berlaku di server, dan jurnal yang terbentuk.

App `erp`, module `Fleet` (`erp/erp/fleet/`). Master kendaraan dan driver tinggal di
module `Expedition` karena dipakai bersama modul lain.

---

## 1. Peta modul

```
Packing List (Expedition)
      |  hook on_update: 1 PL = 1 DPO
      v
Dispatch Order (DPO)  --Assign-->  Trip Log (matriks ritase)
      |                                   |
      |                                   +--> route_history (breadcrumb GPS per menit)
      |                                   +--> dispatch_order_history (arsip trip dihapus)
      v
Monitoring: GPS Vehicle (peta) | Driver Monitor (absensi) | Monitoring Board | Monitoring Notes

Kendaraan (Vehicle)
      +--> Maintenance   (servis + pemakaian sparepart)
      +--> Mutation      (pindah cabang)
      +--> Incident      (NCR / LAKA)
      +--> TyMS          (manajemen ban)
```

Menu desk: workspace **Fleet** (sequence 3 di module Expedition) + Workspace Sidebar
**Fleet**: Dashboard, Driver Monitor, Dispatch Order, GPS Vehicle, Monitoring,
Maintenance, Mutation, Incident, TyMS, lalu grup Master (Vehicle, Driver, Fleet Location).

---

## 2. Master data

### 2.1 Vehicle (module Expedition, autoname `field:title`)

Nopol (field `title`) jadi nama dokumen. Dipakai hampir semua doctype Fleet.

| Field | Label | Tipe | Catatan |
|---|---|---|---|
| branch | Branch | Link CMI Office | wajib, dasar filter cabang |
| title | Nopol | Data | wajib, jadi nama dokumen |
| no_lambung | No. Lambung | Data | |
| variant | Model/Varian | Link Vehicle Variant | wajib |
| no_rangka, no_mesin | | Data | |
| merk | Merk | Data | ambil dari variant.merk |
| warna, no_imei | | Data | |
| kapasitas_bbm | Kapasitas BBM | Float | liter |
| rasio_bbm | Rasio Penggunaan BBM | Float | km per liter |
| internal | Internal | Check | default 1 |
| vehicle_owner | Vehicle Owner | Link Vehicle Owner | muncul kalau bukan internal |
| ownership | Vehicle Ownership | Select | Milik Sendiri / Sewa / Leasing |
| tahun_pembuatan | Tahun Pembuatan | Int | |
| tgl_mulai_operasi | Tgl. Mulai Operasi | Date | |
| disabled | Disabled | Check | kebalikan dari aktif |
| no_stnk, nama_stnk, masa_berlaku_stnk, alamat_stnk, no_bpkb | legal | Data/Date | |
| tgl_kir_terakhir, kode_uji_kir, lokasi_uji_kir | KIR | Date/Data | |
| kapasitas_ban_serep | Kapasitas Ban Serep | Int | |
| setting_km | Setting KM | Select | GPS / Manual |
| jarak_tempuh_harian | Jarak Tempuh Harian | Float | dipakai kalau setting_km = Manual |
| no_gsm_gps | No. GSM GPS | Data | |
| commodities | Commodities | Table MultiSelect Vehicle Commodity | muatan yang boleh dibawa |

Pendukung: **Vehicle Variant** (code, title, merk, disabled), **Vehicle Owner**
(code, title, phone, address, disabled), **Vehicle Commodity** (child, link ke Cargo).

### 2.2 Driver (module Expedition, autoname `field:code`)

| Field | Label | Tipe |
|---|---|---|
| image | Foto | Attach Image |
| code | Code | Data, wajib, jadi nama dokumen |
| title | Name | Data, wajib |
| branch | Branch | Link CMI Office |
| address, id_card, kartu_keluarga | | Small Text / Data |
| religion | Religion | Select |
| phone_number, emergency_contact | | Data |

### 2.3 Fleet Location (module Fleet, autoname `field:code`)

Master titik GABUNGAN. Doctype Route dan Depo lama sudah dihapus total; satu lokasi
boleh punya banyak peran sekaligus.

| Field | Label | Tipe | Catatan |
|---|---|---|---|
| code | Name | Data | wajib, jadi nama dokumen |
| alamat | Alamat | Small Text | |
| jenis | Jenis | Data | read-only, ringkasan peran |
| latitude, longitude | | Float | bisa diklik langsung di peta form |
| radius_km | Radius (KM) | Float | default 5, dasar geofence |
| is_depo | Depo | Check | dipakai Packing List (4 field depo) dan Mutation |
| is_route | Route | Check | dipakai slot titik DPO |
| is_garasi | Garasi | Check | tujuan step Menuju Garasi; juga penentu status Moving No Job |
| is_danger | Danger | Check | unit yang diam 5 menit di radius ini berstatus Suspect |
| disabled | Disabled | Check | |

Peta pemilih koordinat: `erp/public/js/geo_point_form.js` (dimuat lewat app_include_js).

### 2.4 GPS Vehicle (module Fleet, autoname `GPS/.####.`)

| Field | Tipe | Catatan |
|---|---|---|
| vehicle | Link Vehicle | wajib |
| device_id | Data | id perangkat vendor |
| latitude, longitude | Float | posisi terakhir |
| last_seen | Datetime | read-only, terakhir perangkat mengirim data |
| moved_at | Datetime | read-only, terakhir posisinya benar-benar berubah |

Default view = Map. Halaman monitor GPS memakai data ini, bukan list-nya.

`last_seen` dan `moved_at` HANYA ditulis `erp.fleet.vehicle_status.push_position()`:

```python
push_position(vehicle, latitude, longitude, device_id=None)
```

Itu jalur yang akan dipakai cron / API vendor. `moved_at` digeser hanya kalau posisinya
berpindah minimal 20 meter, karena GPS selalu bergoyang beberapa meter walau kendaraan
diam. Tanpa ambang itu tidak akan pernah ada unit yang terhitung "diam 5 menit".
Dokumen lama yang belum pernah lewat sana memakai `modified` sebagai perkiraan.

---

## 3. Alur operasional: Packing List sampai selesai job

### 3.1 Packing List (module Expedition) — sumber pekerjaan

Bukan bagian Fleet, tapi pemicunya. Field yang dipakai Fleet:

| Field | Dipakai untuk |
|---|---|
| date, origin_location, destination_location | header DPO (read-only, ikut PL) |
| etd, eta, etb | header DPO |
| depo_origin, depo_kereta_origin, depo_destination, depo_kereta_destination | Link Fleet Location |
| items (Packing List Item) | jadi baris Dispatch Order Item |
| void, closed | PL void/closed/tanpa item tidak dibuatkan DPO |

Packing List Item yang relevan: `container_no`, `container_size`, `customer`,
`driver`, `vehicle`, `atd`, `driver_selesai`, `status`. Empat yang terakhir
read-only di PL karena diisi dari DPO (lihat 3.3).

### 3.2 Dispatch Order (DPO) — 1 PL = 1 DPO

Autoname `DPO/.YYYY./.#####.`. Dibuat dan disegarkan otomatis oleh hook
`Packing List.on_update -> sync_from_packing_list`; ikut terhapus lewat
`on_trash -> delete_with_packing_list`.

**Header**

| Field | Tipe | Catatan |
|---|---|---|
| packing_list | Link Packing List | wajib, read-only |
| date, origin_location, destination_location, eta, etd, etb | | read-only, disalin dari PL |
| assign_progress | Data | read-only, "2/3 (67%)", dihitung di validate |
| customer_list, dpo_list, driver_list, vehicle_list | Small Text | read-only, ringkasan untuk list view |
| items | Table Dispatch Order Item | wajib |
| trip_log | Table Dispatch Order Route | matriks ritase |
| route_type_1..8 | Select Route/Depo | jenis titik per slot |
| route_1..8 | Link Fleet Location | titik rute, boleh kosong |
| route_langsir_1..8 | Check | penanda langsir, BUKAN pemangkas step |

**Dispatch Order Item** (1 baris = 1 Packing List Item)

| Field | Tipe | Catatan |
|---|---|---|
| assigned | Check | read-only, dinyalakan tombol Assign |
| container_no, container_size, customer | | read-only, ikut PL Item |
| atd | Date | diisi user |
| ata | Date | "ATA (Selesai Bongkar)" |
| driver | Link Driver | diisi user, terkunci setelah punya trip |
| vehicle | Link Vehicle | idem |
| chasis | Data | idem |
| dpo_no | Data | read-only, `{DPO}-01`, `-02`, dst, dihitung di validate |
| packing_list_item | Data | read-only, penghubung ke PL Item |

**Dispatch Order Route (trip_log)** — 1 baris = 1 step dari 1 trip

| Field | Tipe | Catatan |
|---|---|---|
| dpo_item | Data | wajib, name row DPO Item |
| trip | Int | nomor ritase, default 1 |
| driver, vehicle | Link | boleh beda per trip |
| chasis | Data | |
| step | Int | urutan step dalam trip |
| step_type | Select | Assign / Accept Job / Route / Lanjut Job / Menuju Garasi |
| point_type | Select | Route / Depo / Garasi |
| point | Link Fleet Location | |
| start, end | Datetime | jam masuk/keluar titik (geofence) |

### 3.3 Sinkronisasi dua arah PL dan DPO

- **PL ke DPO** (`sync_from_packing_list`): header disegarkan tiap PL disimpan; PL Item
  baru menambah baris DPO (driver/vehicle/atd di-seed dari nilai lama), PL Item dihapus
  menghapus barisnya, dan trip_log milik baris yang hilang ikut dibuang.
- **DPO ke PL** (`on_update`, konstanta `PLI_SYNC`): user mengisi Driver / Vehicle / ATD /
  ATA di grid DPO, saat Save nilainya ditulis balik ke Packing List Item
  (`ata` menjadi `driver_selesai`). Tujuannya supaya report dan alur lama yang membaca
  kolom di PL tetap konsisten. Saat sync dari PL, flag `from_pl_sync` mencegah tulis balik.

### 3.4 Assign

Tombol **Assign** (`assign()`) menandai item yang **ATD + Driver + Vehicle** terisi.

- Parsial diperbolehkan: item yang belum lengkap dilaporkan namanya dan bisa di-assign menyusul.
- Save biasa TIDAK meng-assign.
- Item yang baru assigned langsung dibuatkan **trip 1** oleh `_ensure_trip_rows()`.
- Item yang sudah punya baris trip tidak pernah di-generate ulang, jadi mengubah slot
  route setelah assign tidak mengacak trip yang sudah jalan.

Urutan step satu trip (`_trip_steps`), sama untuk semua trip termasuk langsir:

```
1 Assign (start = saat tombol ditekan)
2 Accept Job
3..n Route  (satu step per slot route_1..8 yang terisi)
n+1 Lanjut Job
n+2 Menuju Garasi (point kosong, diisi aplikasi driver)
```

### 3.5 Ritase (trip 2 dan seterusnya)

Jumlah trip tidak diketahui di depan; driver melapor, mandor/CS mencatat.

| Tombol | Method | Yang terjadi |
|---|---|---|
| Tambah Trip | `add_trip` | mengulang SELURUH step dengan titik yang sama, nomor trip +1, driver/vehicle/chasis boleh beda, item di-reset kecuali ATD (ATA dikosongkan) |
| Edit Trip | `edit_trip` | ganti driver/vehicle/chasis satu trip; kalau trip terakhir, item ikut berubah |
| Hapus Trip | `delete_trip` | step-nya diarsip ke `history.dispatch_order_history` lalu dihapus; nomor trip lain TIDAK digeser agar tetap nyambung dengan route_history |

Ketiganya tercatat di Activity karena doctype-nya `track_changes`.

**Kunci `_lock_assigned_items`**: begitu sebuah item punya baris trip, Driver / Vehicle /
Chasis di grid tidak bisa diedit langsung (dibandingkan dengan nilai di DB). User harus
lewat Edit Trip, atau menghapus semua trip item itu dulu. Tombol Tambah/Edit Trip lolos
lewat `flags.trip_edit`.

### 3.6 Langsir

Langsir adalah sifat SELURUH Packing List: kalau PL langsir, semua party dan semua rutenya
langsir. Checkbox `route_langsir_1..8` hanya PENANDA (badge oranye di UI), bukan pemangkas
step. Semua trip tetap menghasilkan rute penuh yang sama.

### 3.7 UI Dispatch Order

- Section **Route**: matriks scroll-x (`trip_html`). Baris 1 = pemilihan jenis titik per slot
  (None / Route / Depo), baris 2 = input titik ber-datalist. Baris berikutnya = per driver,
  tiap sel berisi IN/OUT datetime-local plus durasi tampil ("2j 15m"), disimpan lewat Save biasa.
- Section **Map**: peta Leaflet full-width (bawaan desk, global `L`, tile OSM). Pin biru = titik
  route, pin oranye = posisi vehicle dari GPS Vehicle. Garis antar titik = garis lurus bernomor
  dan berpanah. Route engine (OSRM/ORS) sudah DITOLAK user, jangan ditawarkan lagi.
- Link **Playback** per driver: dialog peta polyline + marker S/E + Play/Pause + slider,
  datanya dari `get_route_history(dpo_item, trip)`.

---

## 4. Monitoring

### 4.1 GPS Vehicle (Page `gps-monitor`)

Menu "GPS Vehicle" mengarah ke halaman ini, bukan list doctype.

- Peta 62vh di atas, di bawahnya 5 tabel satu kolom: Branch, Nopol, Status, Job, Notifikasi.
- Branch berisi semua CMI Office plus baris "All" dan jumlah unit; diklik memfilter peta dan
  keempat tabel lain.
- Baris = SEMUA Vehicle aktif, bukan hanya yang punya GPS. Nopol dengan sub-baris driver
  (dari Driver Attendance Check In TERAKHIR HARI INI, bukan dari job).
- Status memakai resolver bersama (lihat 4.5). Job = `dpo_no` + origin/destination satu baris.
- Auto-refresh 60 detik tanpa me-reset zoom/pan.
- Marker `/assets/erp/images/truck.png` 50px. Tile CARTO Voyager plus opsi Satelit Esri.
  Google Maps ditolak karena butuh API key berbayar.

### 4.2 Driver Monitor (virtual doctype)

Tanpa tabel; barisnya dihitung saat list dibuka, supaya dapat filter/sort/export bawaan desk.

| Field | Tipe | Isi |
|---|---|---|
| branch | Link CMI Office | dari PL job aktif |
| driver, driver_name | Link Driver / Data | |
| status | Select | Belum Absen / Absensi / Ready / On Job |
| nopol | Link Vehicle | vehicle check-in terakhir atau dari job |
| absensi | Datetime | absen PERTAMA hari ini |
| checkin | Datetime | check-in TERAKHIR hari ini |
| packing_list, dpo_no | | tampil selama job aktif |
| checkpoint | Data | step Route terakhir yang sudah ada waktunya |

Urutan status: **On Job** (punya item assigned yang belum ditekan Lanjut Job / Menuju Garasi)
lebih dulu, lalu **Ready** (sudah check-in hari ini), **Absensi** (baru absen), **Belum Absen**.
Reset harian lewat filter tanggal, bukan penghapusan data. Auto-refresh 60 detik.

### 4.3 Driver Attendance (autoname `DAB/.YYYY./.#####.`)

Event mentah yang menyuplai Driver Monitor dan GPS Monitor. Diisi aplikasi driver nanti.

| Field | Tipe |
|---|---|
| driver | Link Driver, wajib |
| type | Select Absensi / Check In, wajib |
| timestamp | Datetime, wajib |
| vehicle | Link Vehicle |

### 4.4 Monitoring Board (Page) dan Monitoring Notes

Board: 1 baris per kendaraan aktif, memakai aturan job aktif yang sama dengan halaman GPS.
Kolom Note diisi Monitoring Notes terakhir unit itu; kolom Notifikasi masih dihitung ad-hoc
(checkpoint / GPS diam / Standby) sampai doctype notifikasi vehicle dibuat.

**Monitoring Notes** (`MN/.YYYY./.#####.`): note, note_date, **suspend**, dpo_no, nopol,
driver, vehicle, latitude, longitude, status, notification. Status kosong berarti note
dibuat dari pin peta, bukan dari unit. Centang **Suspend** membuat unit berstatus Suspend
di monitor sampai ada note baru untuk unit itu tanpa centang.

**Monitoring** (`MON/.YYYY./.####.`) masih skeleton: date, vehicle, notes.

### 4.5 Status kendaraan (resolver bersama)

`erp/fleet/vehicle_status.py`. Aturannya pernah tersebar di dua halaman dan langsung
menyimpang, jadi sekarang satu tempat: halaman baru cukup memanggil `status_map(jobs)`,
jangan menyalin aturannya. Palet warna badge ikut dikirim ke JS (`status_colors`) supaya
status baru tidak perlu didaftarkan ulang di sisi klien.

Yang cocok pertama menang, jadi urutan daftar ini adalah aturannya:

| # | Status | Syarat |
|---|---|---|
| 1 | Suspect | diam >= 5 menit di dalam radius Fleet Location bercentang Danger, perangkat masih online |
| 2 | Suspend | note terakhir unit dicentang Suspend |
| 3 | Moving No Job | bergerak (posisi berubah <= 5 menit lalu), tidak punya job, dan berada di luar radius garasi |
| 4 | Offline Active | punya job aktif tapi perangkat tidak mengirim data > 15 menit |
| 5 | Incident | ada Incident yang `finish_date`-nya kosong |
| 6 | Maintenance | ada Maintenance non-void yang `finish_date`-nya kosong |
| 7 | Not Active | tidak pernah kirim data, atau diam/hilang > 30 hari |
| 8 | On Job | punya job aktif dan tidak ada isu apa pun |
| - | Idle | default: tidak ada job, tidak ada isu (mis. parkir di garasi) |

Idle bukan permintaan awal, tapi wajib ada: tanpa itu truk yang parkir tenang di garasi
akan dilabeli "On Job" padahal tidak sedang bekerja.

Ambang waktunya konstanta di puncak file, ubah di satu tempat kalau lapangan bicara lain:
`STOP_MINUTES = 5`, `OFFLINE_MINUTES = 15`, `NOT_ACTIVE_DAYS = 30`, `MOVING_MINUTES = 5`.

Geofence memakai jarak haversine terhadap `radius_km` Fleet Location (default 5 km).

Cek: `erp/fleet/test_vehicle_status.py` -> `run()` di bench console. Menguji kedelapan
status, dua kasus prioritas (Suspect menang atas job aktif, garasi membatalkan Moving No
Job), pelepasan suspend lewat note baru, dan ambang 20 meter `push_position`. Semua
di-rollback.

---

## 5. Maintenance kendaraan

Autoname `MTC/.YYYY./.####.`. Dua peran sekaligus: kartu servis, dan tempat PEMAKAIAN
sparepart diakui.

### 5.1 Tiga jalur sparepart

| Jalur | Dokumen | Efek stok | Jurnal terbit di |
|---|---|---|---|
| 1 | PO -> PR baris berisi Vehicle | diterima lalu langsung dikeluarkan, tidak pernah bersaldo | Purchase Receipt (Material Issue otomatis) |
| 2 | PO -> PR tanpa Vehicle | masuk stok gudang | Purchase Receipt |
| 3 | Maintenance pilih item + gudang | keluar dari stok | Maintenance (saat Validate) |

Karena barang jalur 1 tidak pernah bersaldo, dobel-pakai mustahil. Pemisahannya terjadi
sendiri, bukan lewat penjagaan tambahan.

Jalur 1 tetap MELAHIRKAN kartu Maintenance otomatis supaya riwayat satu nopol lengkap di
satu tempat (`erpnext_custom/sparepart.py -> _make_maintenance`): satu Maintenance per
kendaraan, langsung `validated = 1`, `purchase_receipt` dan `stock_entry` terisi, harga
memakai harga beli.

### 5.2 Field

| Field | Label | Tipe | Catatan |
|---|---|---|---|
| vehicle | Vehicle | Link Vehicle | wajib |
| branch | Branch | Link CMI Office | read-only, ikut vehicle.branch |
| maintenance_type | Jenis | Select | Servis Rutin / Perbaikan / Ban / KIR & Perizinan / Body / Lain-lain |
| date | Tgl Masuk | Date | wajib, default hari ini |
| finish_date | Tgl Keluar | Date | kosong = kendaraan masih di bengkel |
| company | Company | Link Company | wajib, dasar akun dan Stock Entry |
| odometer | Odometer (Km) | Float | |
| supplier | Bengkel | Link Supplier | |
| next_service_date, next_service_km | Servis Berikutnya | Date / Float | pengingat sederhana, tanpa doctype jadwal terpisah |
| items | | Table Maintenance Item | |
| total_amount | Nilai Sparepart Terpakai | Currency | read-only |
| description | Keterangan | Small Text | |
| validated, validated_by, validated_date | | Check / Link User / Datetime | read-only |
| void, void_by, void_datetime, void_reason | | Check / Link / Datetime / Small Text | read-only |
| stock_entry | Stock Entry (Pemakaian) | Link Stock Entry | read-only |
| purchase_receipt | Dari Purchase Receipt | Link Purchase Receipt | read-only, terisi = kartu turunan |

**Maintenance Item**

| Field | Label | Tipe | Catatan |
|---|---|---|---|
| item | Item | Link Item | wajib; dropdown difilter Item Group "Sparepart" beserta sub-grupnya |
| warehouse | Gudang | Link Warehouse | wajib untuk item stock |
| qty | Quantity | Float | wajib, harus lebih dari 0 |
| uom | UOM | Link UOM | read-only, ikut item.stock_uom |
| description | Remark | Data | catatan bebas |
| is_stock_item | | Check | read-only, tersembunyi, ikut item.is_stock_item |
| rate | Nilai Satuan | Currency | read-only, diisi sistem dari valuation gudang |
| amount | Nilai | Currency | read-only |

Harga tidak pernah diketik user: barang yang keluar gudang dinilai dengan nilai bukunya.
Saat gudang dipilih, form menarik `Bin.valuation_rate` sebagai tampilan awal; angka final
ditulis ulang dari Stock Entry yang benar-benar terbit saat Validate.

### 5.3 Status dan pengakuan usage

Memakai mesin state CMI `erpnext_custom/workflow.py` jalur checkbox, sebaris dengan
Expense Note dan Pending Cash ("Maintenance" terdaftar di tuple `CHECKBOX`).

```
Draft --Validate--> Validated --Void--> Void
   <--Invalidate--          <--Unvoid-- (kembali ke Draft, bukan ke Validated)
```

- **Validate**: Stock Entry Material Issue terbit untuk semua baris item stock, lalu harga
  dan total ditarik dari Stock Entry itu.
- **Invalidate / Void**: Stock Entry-nya di-cancel, link dilepas, stok kembali.
- Setelah Validated atau Void, isi dokumen TERKUNCI di server (`_guard_locked`), termasuk
  perubahan di grid. Perbandingan child table dilakukan terpisah karena fieldtype Table
  masuk `no_value_fields` sehingga terlewat dari perbandingan field biasa.
- Kartu turunan PR (`purchase_receipt` terisi) tidak membuat maupun membatalkan Stock Entry
  sendiri, dan tidak bisa di-Validate/Void manual (`_guard_pr_owned`). Pembatalannya lewat PR:
  `cancel_issue_before_cancel -> _void_maintenance` menyalakan void beserta alasannya.

Role: Transaction Validate / Invalidate / Void / Unvoid (System Manager selalu boleh).

### 5.4 Jurnal

| Kejadian | Debit | Kredit |
|---|---|---|
| PR barang diterima | Persediaan (per Item Group) | Hutang Usaha Sementara |
| PR baris berisi Vehicle, Material Issue otomatis | Beban sparepart | Persediaan |
| Maintenance Validate | Beban sparepart | Persediaan |
| Purchase Invoice | Hutang Usaha Sementara | Hutang Usaha |
| Payment Entry | Hutang Usaha | Bank |

Contoh nyata di erp.localhost: `PO/NON-JOB/CMI/2026/0002 -> MAT-PRE-2026-00009 ->
PI/00006/CMI/26 -> PV/MDR/0001/CMI/VIII/26`, dengan `MTC/2026/0001` (turunan PR, kampas rem)
dan `MTC/2026/0002` (manual, oli dari gudang).

### 5.5 Asal akun

- **Akun beban** diambil `erpnext_custom.sparepart.expense_account()`: Item Default dulu,
  lalu Item Group. Tidak ketemu keduanya berarti dokumen ditolak dengan pesan jelas, bukan
  menebak akun.
- **Akun persediaan** mengikuti mode item-wise (`Company.enable_item_wise_inventory_account`,
  menyala di PT CMI): Item Default -> Item Group -> Brand. Mode ini TIDAK punya cadangan,
  jadi setiap Item Group yang berisi item stock wajib punya Default Inventory Account.
  Pemetaan sekarang: Sparepart ke 1140.006, Flexibag ke 1130.001, Oleo Chemicals ke 1130.002,
  sisanya ke 1130.003 Persediaan Umum.

### 5.6 Biaya yang bukan barang

Maintenance hanya mencatat pemakaian barang. Jasa bengkel dan biaya tak terduga tidak boleh
diketik di sini karena tidak akan pernah masuk jurnal. Pilih menurut cara bayarnya: Purchase
Invoice ke bengkel (ada nota), Expense Note (biaya operasional lewat vendor), atau Pending
Cash (uang jalan supir).

### 5.7 Cek

`erp/fleet/doctype/maintenance/test_maintenance.py`:

```
bench --site erp.localhost console
>>> from erp.fleet.doctype.maintenance.test_maintenance import run; run()
```

Menguji ketiga jalur, penguncian dokumen tervalidasi, dan guard kartu turunan PR.
Semua perubahan di-rollback.

---

## 6. Doctype pendukung

### 6.1 Mutation (`MUT/.YYYY./.####.`)

Perpindahan kendaraan atau driver antar cabang.

| Field | Tipe | Catatan |
|---|---|---|
| date | Date | wajib, default hari ini |
| mutation_type | Select Vehicle / Driver | wajib |
| vehicle / driver | Link | sesuai jenis |
| from_branch | Link CMI Office | read-only, diambil dari objeknya |
| to_branch | Link CMI Office | wajib |
| remark | Small Text | |

### 6.2 Incident (`INC/.YYYY./.####.`)

| Field | Tipe | Catatan |
|---|---|---|
| report_type | Select | NCR (non-conformance) / LAKA (kecelakaan), wajib |
| date | Date | wajib |
| finish_date | Date | Tgl Selesai Perbaikan; kosong = kasus terbuka, unit berstatus Incident |
| vehicle, driver | Link | |
| location, issue_area, latitude, longitude | | lokasi kejadian, bisa diklik di peta |
| issue_title, case_description, root_cause, corrective_action, preventive_action, remarks | | isi kasus |

### 6.3 TyMS (autoname `field:serial_no`)

Manajemen ban, masih skeleton: serial_no (wajib), vehicle, position.

---

## 7. Database `history` (terpisah dari site)

MariaDB `history` di server yang sama (container `erp_cakra-mariadb-1`). User site sudah
di-GRANT ALL, diakses lewat `frappe.db.sql` lintas schema.

### 7.1 `route_history` — breadcrumb GPS

Kolom: id, dispatch_order, dpo_item, trip, driver, vehicle, latitude, longitude, recorded_at.
Index: (dpo_item, recorded_at), (dispatch_order, recorded_at), (vehicle, recorded_at).

Aturan perekaman yang disepakati (cron dan API vendor BELUM dibangun):

- Mulai saat item DPO di-assign ke driver.
- Interval 1 menit, koordinat diambil dari GET API vendor GPS.
- Berhenti saat driver menekan **Lanjut Job** atau **Menuju Garasi**, atau saat user mengisi
  **ATA** di item DPO (penjaga ukuran database).

### 7.2 `dispatch_order_history` — arsip trip terhapus

Diisi `delete_trip`: seluruh step trip yang dihapus disimpan lengkap beserta `deleted_by`
dan `deleted_at`, sebagai bahan pemeriksaan.

---

## 8. Yang belum dibangun

- **Aplikasi driver**. Step Accept Job, Lanjut Job, Menuju Garasi, serta jam masuk/keluar
  geofence tiap titik sekarang diisi manual; semuanya tugas aplikasi driver nanti.
- **Cron dan API vendor GPS**. Pintu masuknya sudah ada (`push_position`), yang belum ada
  penjadwal dan adaptor vendornya, termasuk pengisian `route_history` per menit. Selama itu
  belum jalan, `last_seen`/`moved_at` tidak pernah bergerak sehingga status Suspect,
  Moving No Job, dan Offline Active tidak akan pernah muncul dari data nyata.
- **Garasi per vehicle** untuk step Menuju Garasi belum diputuskan (sementara ambil dari
  `is_garasi` di Fleet Location).
- **Report Biaya Kendaraan** yang menggabungkan pemakaian sparepart dengan jasa dari
  Purchase Invoice / Expense Note. Field Vehicle di Purchase Invoice Item dan Expense Note
  Item juga belum ada (baru Purchase Receipt Item yang punya).
- **Monitoring** dan **TyMS** masih skeleton.

---

## 9. Peta file

```
erp/erp/fleet/
  doctype/
    dispatch_order/          controller + JS matriks trip, peta, playback
    dispatch_order_item/
    dispatch_order_route/    child trip_log
    fleet_location/
    gps_vehicle/
    driver_attendance/
    driver_monitor/          virtual doctype (list dihitung on the fly)
    maintenance/             + test_maintenance.py
    maintenance_item/
    monitoring/  monitoring_notes/  mutation/  incident/  tyms/
  vehicle_status.py        resolver status + push_position (dipakai kedua halaman monitor)
  test_vehicle_status.py   cek urutan prioritas status
  page/
    gps_monitor/             peta + 5 tabel
    monitoring_board/        board per unit + notifikasi
erp/erp/public/js/geo_point_form.js     peta pemilih koordinat Fleet Location
erp/erp/expedition/workspace/fleet/     workspace Fleet
erp/erp/workspace_sidebar/fleet.json    menu kiri Fleet
erpnext_custom/erpnext_custom/sparepart.py   jalur PR ber-Vehicle + kartu Maintenance otomatis
erpnext_custom/erpnext_custom/workflow.py    mesin state Validate/Invalidate/Void/Unvoid
```

---

## 10. Gotcha yang sudah pernah menggigit

- **Peta Leaflet di form desk** dibuat saat kontainer masih 0px sehingga tile abu-abu. Satu
  setTimeout tidak cukup; wajib ResizeObserver, lalu `invalidateSize()` dan fitBounds sekali
  begitu `offsetWidth > 0`.
- **Autoname `format:XX/{####}`** memakai satu counter global berkunci kosong sehingga nomor
  melompat lintas doctype. Pakai gaya klasik `XX/.YYYY./.####.` yang counter-nya per prefix.
- **Module baru di modules.txt** tidak ter-sync oleh `bench migrate` biasa (cache app_modules)
  dan doctype-nya dilewati diam-diam. Jalankan `bench clear-cache` dulu.
- **Workspace di-skip** kalau `modified` di file lebih kecil atau sama dengan yang di DB.
- **Penguncian dokumen lewat perbandingan `meta.fields`** melewatkan child table, karena
  fieldtype Table ada di `no_value_fields`. Bandingkan barisnya terpisah.
- **`rename_doc` vs `rename_field`**: rename doctype dilakukan SELAGI folder di disk masih
  bernama lama; `rename_field` justru butuh JSON sudah diganti lalu migrate, dan hanya
  menyalin data, kolom lama tetap ada dan harus di-drop manual.

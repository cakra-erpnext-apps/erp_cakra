# CRM Cakra — Referensi Lengkap (untuk Build Ulang)

Dokumen ini adalah potret utuh app `crm_cakra` (fork Frappe CRM untuk CMI / Cakraindo):
seluruh doctype beserta setiap field, seluruh method dan endpoint, serta alur bisnis
yang menghubungkannya. Tujuannya satu: cukup dokumen ini untuk membangun ulang CRM
yang sama di app lain, tanpa perlu membuka source aslinya.

Sumber: `ERPCakra/crm_cakra` (backend `crm_cakra/`, frontend Vue `frontend/`).

Daftar isi:

1. [Identitas app dan arsitektur](#1-identitas-app-dan-arsitektur)
2. [Dependensi ke app lain](#2-dependensi-ke-app-lain)
3. [Alur bisnis end-to-end](#3-alur-bisnis-end-to-end)
4. [Peta doctype](#4-peta-doctype)
5. [Referensi field seluruh doctype](#5-referensi-field-seluruh-doctype)
6. [Logika controller per doctype](#6-logika-controller-per-doctype)
7. [Referensi endpoint whitelisted](#7-referensi-endpoint-whitelisted)
8. [Mesin konfigurasi UI](#8-mesin-konfigurasi-ui)
9. [Permission berbasis branch](#9-permission-berbasis-branch)
10. [Dashboard](#10-dashboard)
11. [Notifikasi, aktivitas, dan SLA](#11-notifikasi-aktivitas-dan-sla)
12. [Integrasi eksternal](#12-integrasi-eksternal)
13. [Frontend](#13-frontend)
14. [Wiring hooks.py](#14-wiring-hookspy)
15. [Install, migrate, patch, fixture](#15-install-migrate-patch-fixture)
16. [Penomoran dan print format](#16-penomoran-dan-print-format)
17. [Checklist build ulang](#17-checklist-build-ulang)

---

## 1. Identitas app dan arsitektur

| Item | Nilai |
|---|---|
| `app_name` | `crm_cakra` (hasil rename in-place dari `crm`) |
| Module utama | `FCRM` (semua doctype CRM), plus `Lead Syncing` |
| Route web | `/crm` (`website_route_rules`: `/crm/<path:app_path>` ke template `crm`) |
| Entry point | `crm_cakra/www/crm.py` + `crm.html`; boot dikirim lewat `get_boot()` |
| Frontend | Vue 3 + vue-router (history base `/crm`) + frappe-ui, build Vite |
| Lisensi asal | AGPLv3 (fork Frappe CRM) |

Bentuk arsitekturnya: **backend Frappe biasa (doctype + controller + whitelisted method)
yang dikonsumsi SPA Vue lewat REST**. Desk Frappe tidak dipakai sebagai UI utama; semua
tampilan CRM dirender oleh SPA. Akibatnya beberapa hal yang di Desk otomatis, di sini
dibuat sendiri:

- layout form disimpan di doctype `CRM Fields Layout` (bukan dari urutan field doctype),
- kolom/urutan list view di `CRM View Settings` + `default_list_data()` per controller,
- client script di `CRM Form Script` (DB) **dan** file `frontend/src/doctypes/<slug>/form.js`,
- filter cepat dan sidebar item di `CRM Global Settings`.

Isi `get_boot()` (dipakai SPA saat start): `frappe_version`, `default_route` (`/crm`),
`site_name`, `read_only_mode`, `csrf_token`, `setup_complete`, `sysdefaults`,
`is_demo_site`, `demo_data_created`, `is_fc_site`, `show_sales_hierarchy_banner`
(true bila ada CRM Lead), `translated_doctypes`, `translated_messages`, `timezone`.

Catatan operasional: `csrf_token` yang rusak membuat SPA melempar ke `/crm/not-permitted`.

---

## 2. Dependensi ke app lain

CRM ini **tidak berdiri sendiri**. Yang dipanggil dari luar:

| App | Dipakai untuk | Titik sentuh |
|---|---|---|
| `frappe` | doctype dasar: `User`, `Contact`, `Comment`, `Communication`, `ToDo`, `DocShare`, `Version`, `File`, `Email Account`, `Email Template`, `Assignment Rule`, `Data Import`, `Translation`, `Property Setter`, `Custom Field` | seluruh app |
| `erp` (app internal) | master lokasi dan jarak rute | `Fleet Location` (Link di Inquiry/Quotation/Estimation), `erp.fleet.doctype.fleet_route.fleet_route.get_distance`, `...gmap_url`, `erp.fleet.geocode.search_address` |
| `assistant` (app internal) | chat asisten di menu CRM | `assistant.assistant.crm.chat` / `.session` / `.sessions` / `.session_messages` / `.clear_session`; digerbangi `FCRM Settings.enable_crm_assistant` |
| `erpnext` (opsional) | buat Customer/Prospect/Quotation dari Inquiry | doctype `ERPNext CRM Settings`, `Company`, `Cost Center`, `Currency`, `UOM`, `Item` |
| `frappe_whatsapp` (opsional) | tab WhatsApp | doctype `WhatsApp Message`, `WhatsApp Templates` |
| Twilio / Exotel (opsional) | telephony | `CRM Twilio Settings`, `CRM Exotel Settings` |

Kalau dibangun ulang di app lain, Link ke `Fleet Location` (`CRM Inquiry.origin`,
`.destination`, `CRM Quotation.loading`, `.unloading`, `CRM Estimation.route1..route8`
plus `loading`/`unloading`) dan tombol Get KM adalah bagian yang **wajib disiapkan
padanannya**, karena validasi Quotation menolak simpan kalau rute/KM kosong pada
dokumen baru.

---

## 3. Alur bisnis end-to-end

Alur utama (urutan menu sidebar sengaja mengikuti alur ini):

```
Lead  ->  Inquiry  ->  Quotation  ->  (Procurement costing)  ->  Estimation
 |          |             |                                        |
 |          |             +-- Print Out (PDF Jinja)                +-- Revenue/Expense -> Est. Profit
 |          +-- SLA, status log, kanban
 +-- konversi membuat Contact + CRM Organization (Account)
```

### 3.1 Lead

- Dibuat manual, dari Call Log, dari email masuk (`create_lead_from_incoming_email`,
  aktif kalau `Email Account.create_lead_from_incoming_email` dicentang), atau dari
  sinkronisasi Facebook Lead Ads.
- Nama dokumen: `LD/0001/CMI/26` (counter reset per tahun, kunci seri `LD-YY-`).
- Status default `New`; master statusnya `CRM Lead Status` dengan `type` =
  Open/Ongoing/On Hold/Won/Lost dan `position` (urutan kanban).
- Setiap perubahan status menulis baris ke `status_change_log`
  (`CRM Status Change Log`: from/to, from_date/to_date, duration, from_type/to_type).
- `lead_owner` yang berubah = otomatis `DocShare` write + assignment (ToDo) ke user itu,
  dan mencabut share user lain.
- **Konversi** (`convert_to_inquiry`):
  1. cek permission write; tolak kalau `converted` sudah 1;
  2. status lead jadi `Converted` (fallback `Qualified`), `converted = 1`,
     `communication_status` jadi `Replied` bila punya SLA;
  3. `create_contact()` memakai Contact yang sudah ada bila email/phone/mobile cocok,
     kalau tidak membuat `Contact` baru beserta child email/phone;
  4. `create_organization()` memakai `CRM Organization` yang namanya sama, kalau tidak
     membuat baru (organization_name, website, territory, industry, annual_revenue);
  5. `create_inquiry()` menyalin **semua** field Lead yang punya nama sama di Inquiry,
     kecuali daftar terlarang (`name`, `naming_series`, `creation`, `owner`, `modified`,
     `modified_by`, `idx`, `docstatus`, `status`, `email`, `mobile_no`, `phone`, `sla`,
     `sla_status`, `response_by`, `first_response_time`, `first_responded_on`,
     `communication_status`, `sla_creation`, `status_change_log`) dan kecuali fieldtype
     layout (`Tab/Section/Column Break`, `HTML`, `Button`, `Attach`). Pemetaan khusus:
     `lead_owner` menjadi `inquiry_owner`. Data SLA disalin hanya bila lead sudah pernah
     direspons. Insert memakai `ignore_mandatory` karena field wajib Inquiry (Type of
     Inquiry, Job Service, Cargo, dst.) memang belum diketahui saat kualifikasi;
     kewajibannya berlaku lagi saat Inquiry disimpan berikutnya lewat form.
  6. assignee lead diteruskan ke inquiry.
- **Deteksi duplikat account** (`find_similar_accounts`): nama account dinormalkan
  (lowercase, buang tanda baca/spasi, buang bentuk badan hukum PT/CV/UD/Tbk dst., juga
  yang menempel seperti `ptcakraindo`), lalu dibandingkan: sama persis = 1.0, prefix
  (minimal 5 karakter) = 0.95, sisanya `SequenceMatcher` dengan ambang 0.87. Hasil
  mencakup `CRM Organization` dan `CRM Lead`; Organization didahulukan pada skor sama.

### 3.2 Inquiry

- Nama dokumen: `INQ/0001/CMI/26` (kunci seri `INQ-YY-`, reset tahunan). Field
  `naming_series` masih ada (`INQ/.####./CMI/.YY.`) tapi `autoname()` yang menang.
- Status default `Qualification`; master `CRM Inquiry Status` punya `probability` yang
  otomatis mengisi field `probability` bila masih 0.
- Ini **inti data ekspedisi**: Type of Inquiry (multi-select), Transportation Mode,
  Incoterms, Job Service, Business Unit, Service Type, Origin/Destination (Fleet Location),
  Cargo (commodity, weight, packaging, qty/volume, status), Date of Shipment,
  Shipper/Consignee, plus tiga kolom harga (`estimasi_tarif` = Fixed Cost,
  `costing_procurement` = Variable Cost, `reimburse_cost`).
- Kontak: child `contacts` (`CRM Contacts`), tepat satu `is_primary`; email/mobile/phone
  di header selalu diturunkan dari kontak primary (dikosongkan bila tidak ada).
- Status `Won` mengisi `closed_date`; status bertipe `Lost` **wajib** `lost_reason`
  (dan `lost_notes` bila alasannya `Other`). Section Lost Reason di sidebar
  muncul/hilang otomatis lewat `add_or_remove_lost_reason_section_in_sidepanel`.
- `exchange_rate` diperbarui via `db_set` saat currency berubah.
- Forecasting (opsional, `FCRM Settings.enable_forecasting`) mewajibkan
  `expected_inquiry_value` dan `expected_closure_date`.
- Hook `on_update` memanggil `create_customer_in_erpnext` (ERPNext CRM Settings).

### 3.3 Quotation

- Nama dokumen: `QT/0001/CMI/2026` (kunci seri `QT-YYYY-`, reset tahunan).
- Wajib menaut satu `inquiry`. **Satu inquiry boleh punya banyak quotation** (revisi
  harga / opsi rute) sehingga picker tidak menyembunyikan inquiry yang sudah dipakai.
- Picker inquiry (`get_available_inquiries`) sengaja lebih ketat daripada aturan lihat:
  yang bisa dipilih hanya milik sendiri atau yang di-assign ke user (kecuali level
  See All). Query dipisah dua (milik saya lalu milik orang lain, 10 slot dicadangkan
  untuk orang lain) supaya inquiry sendiri pasti muncul walau `modified`-nya kalah baru.
- Saat `inquiry` dipilih (form script), field turunan diisi: `number`, `subject`,
  `account`, `account_name`, `loading`/`unloading` (hanya kalau teks origin/destination
  benar-benar ada di master `Fleet Location`; kalau tidak dibiarkan kosong supaya
  dokumen tidak lahir dalam keadaan gagal-simpan), lalu `contact_name` dari Contact
  pertama milik account.
- **Validasi rute dan KM** dibuat "tidak boleh dikosongkan", bukan "tidak boleh kosong":
  dokumen baru wajib mengisi Loading/Unloading/KM(>0); dokumen lama yang memang lahir
  kosong (arsip import Zoho, 4.795 dari 4.796 quotation ber-KM 0) tetap bisa dibuka
  dan diperbaiki field lain. Teks rute asli disimpan di `loading_text`/`unloading_text`.
- **Costing engine** (`calculate_costing`, jalan di `before_save`):

  ```
  Base Price = (Fixed Cost/hari + Variable Cost/hari + Margin/hari) x Duration
  ```

  - `cost_key` = kunci stabil per baris produk (hash 10 karakter, dibuat server supaya
    tetap ada walau baris dibuat lewat Desk/API dan tidak berubah saat baris digeser).
  - `seed_cost_defaults()` menyalin rincian komponen **Variable Cost** milik produk ke
    `cost_items` sekali saja; `cost_seeded` menyimpan produk yang sudah dimuat, jadi
    baris yang sengaja dikosongkan Procurement tidak terisi ulang tiap save; ganti
    produk berarti biaya produk lama dibuang dan komponen produk baru dimuat.
  - `cost_items` milik baris produk yang sudah dihapus ikut dibuang.
  - Fixed cost per hari dibaca dari `CRM Product.fixed_cost_per_day` (angka simpanan).
  - **Baris tanpa data biaya sama sekali tidak disentuh**, karena ribuan quotation lama
    harganya diketik manual dan tidak boleh dinolkan engine.
- `net_total` = jumlah (`qty` x `price` x `rate`) tiap baris produk.
- `validity_date` diisi otomatis = `date` + `CRM Settings.default_valid_till` (hari).
  `validity_date_to` opsional; kalau sama dengan `validity_date`, dikosongkan.
  Format cetak: `27 Jun 2026`, `27 Jun - 25 Ags 2026`, `27 Des 2026 - 01 Jan 2027`.
- **Sinkronisasi status ke inquiry** (`on_update`), searah quotation ke inquiry:

  | State quotation | Status inquiry |
  |---|---|
  | `Win` | `Won` |
  | `Lose` | `Lost` |
  | `Draft` / `Sent` / `Waiting` / `Converted` | `Proposal/Quotation`, kecuali inquiry sudah final (Won/Lost) |

  Status `Lose` menuntut `lost_reason` di inquiry, tapi hanya saat state **baru** diubah
  ke Lose, supaya quotation lama tidak terkunci selamanya tiap kali disimpan. Save
  inquiry memakai `ignore_permissions` + `ignore_mandatory`.
- `mark_quotation_lost()` menggabungkan "isi lost reason di inquiry" + "set state Lose"
  dalam satu panggilan supaya tidak ada keadaan setengah jadi.
- **Konversi ke Estimation** (`convert_to_estimation`): row-lock `state` (cegah double
  click), tolak bila sudah `Converted` / void / sudah punya estimasi; salin customer,
  quo_no, quo_date, remarks, rute (loading/unloading/est_km); tiap baris produk menjadi
  baris `revenue_items` (`type_id` = product_code yang **harus punya padanan `Item`**,
  qty, uom, amount, remarks, currency); quotation dikunci `state = Converted`
  (validate menolak segala perubahan berikutnya); assignee ikut disalin.

### 3.4 Procurement

Bukan doctype tersendiri, melainkan **tab di halaman Quotation** plus menu daftar diskusi.

- **Diskusi**: `CRM Procurement Comment` (quotation, reply_to, content). Thread urut
  lama ke baru, mendukung reply satu tingkat dan `@mention`. Notifikasi dua lapis:
  user yang di-mention, lalu semua **peserta thread** (pernah komentar di quotation itu),
  bukan semua user, dan tidak ke penulisnya sendiri. Hapus komentar memakai `force=1`
  (reply yang kehilangan induk ditampilkan sebagai "komentar dihapus" ala WA) dan
  membersihkan `CRM Notification` yang menunjuk komentar itu.
- **Costing panel**: rincian Fixed/Variable per produk. Digerbangi role
  **`Procurement Costing`** (System Manager ikut lolos). Tanpa role,
  `get_cost_defaults` mengembalikan `{}` sehingga panel tetap hidup tapi rinciannya
  tidak pernah sampai ke browser, dan frontend tidak menulis ulang Base Price (supaya
  harga yang sudah benar tidak diturunkan oleh data yang tidak lengkap).
- Frontend menghitung ulang Base Price secara live dengan rumus yang sama seperti server,
  dan hanya menulis kalau angkanya berubah (supaya form tidak jadi "Not Saved" hanya
  karena tab dibuka). Server tetap menghitung ulang saat save.

### 3.5 Estimation

- Nama dokumen: `EST/0001/CMI/26`, kunci seri `EST/CMI/{yy}/` (terlihat di
  Document Naming Settings > Update Current Value). `estimation_no` = nama dokumen.
- `purpose` wajib `Customer` atau `Agent` saat dibuat manual; nilai `Quotation` hanya
  boleh lahir dari konversi (flag `from_convert`).
- Dua tabel memakai **satu child doctype** `CRM Estimation Detail`; pembedanya field
  `is_expense` yang diisi otomatis di `before_save` (0 untuk revenue, 1 untuk expense).
- `rev_inc_tax` = jumlah revenue; `est_profit` = jumlah revenue dikurangi jumlah expense.
- Rute: `route1..route8` + `loading`/`unloading` (semua Link `Fleet Location`),
  `est_km`, `est_days`, plus field HTML `route_map` (komponen `Estimation/RouteMap.vue`).

### 3.6 Modul pendamping

| Modul | Doctype | Inti |
|---|---|---|
| Meeting | `CRM Meeting` | jadwal visit + **absen GPS**. `check_in` mengisi waktu server, lat/long, address, set status `Visited` dan `meeting_from`; `check_out` mengisi `meeting_to` + lat/long. Halaman absen terpisah (`/meetings/attendance`) memakai `navigator.geolocation` |
| Task | `CRM Task` | autoincrement; `assigned_to` berubah berarti unassign user lama, assign user baru (ToDo) + notifikasi |
| Note | `FCRM Note` | catatan bebas, bisa ditaut ke dokumen apa pun (reference_doctype/docname) |
| Call Log | `CRM Call Log` | log panggilan Twilio/Exotel/manual, bisa dijadikan Lead |
| Product / Costing | `CRM Product`, `CRM Cost Type`, `CRM Cost Component`, `CRM Cost Item`, `CRM Cost Component Link` | master harga |
| Void | field di Lead/Inquiry/Quotation | soft-cancel reversible: `is_void`, `void_reason`, `void_at`, `void_by` |

### 3.7 Master costing (penting untuk harga)

```
CRM Cost Type  (behavior: Fixed Cost | Variable Cost)
      ^
      |  type
CRM Cost Component  (status Draft/Validated/Invalidated, items: CRM Cost Item, total_amount)
      ^
      |  CRM Cost Component Link (Table MultiSelect)
CRM Product  (fixed_cost_per_day = jumlah total_amount komponen behavior Fixed yang Validated)
      ^
      |  product_code
CRM Products (baris produk di Lead / Inquiry / Quotation)
```

Aturan yang menentukan:

- Yang menentukan peran sebuah tipe bukan namanya, melainkan field `behavior` di
  `CRM Cost Type`. Tipe yang sudah terhapus dianggap `Variable Cost`.
- **Hanya komponen berstatus `Validated` dan tidak `disabled` yang masuk perhitungan.**
- Komponen `Validated` **terkunci dari edit** (harus Invalidate dulu). Kalau tidak,
  "Validated" cuma stempel sekali seumur hidup dan quotation bisa memakai angka yang
  tidak pernah disetujui. Status dibaca dari kondisi tersimpan, bukan dari payload client.
- Tombol Validate/Invalidate (`set_validation`) memakai `db_set` sehingga melewati
  `validate()`; Validate menolak komponen tanpa item.
- Setiap perubahan komponen memanggil `refresh_linked_products()`: cache dokumen
  dibersihkan lalu `CRM Product.fixed_cost_per_day` dihitung ulang untuk semua produk
  yang menautnya. Tanpa ini, validate atau ubah harga tidak terasa apa-apa sampai
  produknya kebetulan disimpan ulang.

---

## 4. Peta doctype

Semua di module **FCRM** kecuali yang ditandai.

**Transaksi utama**

| Doctype | Child table | Peran |
|---|---|---|
| `CRM Lead` | `CRM Products`, `CRM Status Change Log`, `CRM Rolling Response Time` | prospek awal |
| `CRM Inquiry` | `CRM Contacts`, `CRM Inquiry Type Inquiry`, `CRM Products`, `CRM Status Change Log`, `CRM Rolling Response Time` | permintaan yang sudah terkualifikasi |
| `CRM Quotation` | `CRM Products`, `CRM Cost Item` (`cost_items`, hidden) | penawaran harga |
| `CRM Estimation` | `CRM Estimation Detail` x2 (`revenue_items`, `expense_items`) | estimasi laba |
| `CRM Meeting` | - | jadwal + absen GPS |
| `CRM Task` | - | tugas |
| `FCRM Note` | - | catatan |
| `CRM Call Log` | `Dynamic Link` | log telepon |
| `CRM Procurement Comment` | - | thread diskusi procurement |
| `CRM Notification` | - | notifikasi in-app |

**Master / referensi**

`CRM Organization` (Account), `CRM Product`, `CRM Cost Type`, `CRM Cost Component`
(+`CRM Cost Item`, `CRM Cost Component Link`), `CRM Industry`, `CRM Territory` (tree),
`CRM Lead Source`, `CRM Lead Status`, `CRM Inquiry Status`, `CRM Lost Reason`,
`CRM Communication Status`, `CRM Type Inquiry`, `CRM Transportation Mode`, `CMI Office`.

**Konfigurasi / sistem**

`FCRM Settings` (single), `CRM Global Settings`, `CRM Fields Layout`, `CRM View Settings`,
`CRM Form Script`, `CRM Dashboard`, `CRM Dropdown Item`, `CRM Invitation`,
`CMI Branch Access` (single) + `CMI Branch Access Role`, `CMI User Branch`,
`CRM Service Level Agreement` (+`CRM Service Level Priority`, `CRM Service Day`),
`CRM Holiday List` (+`CRM Holiday`), `ERPNext CRM Settings` (single),
`CRM Twilio Settings` (single), `CRM Exotel Settings` (single), `CRM Telephony Agent`
(+`CRM Telephony Phone`).

**Module Lead Syncing**

`Lead Sync Source`, `Facebook Page`, `Facebook Lead Form`, `Facebook Lead Form Question`,
`Failed Lead Sync Log`.

---


## 5. Referensi field seluruh doctype

Setiap doctype beserta seluruh field-nya. Section/Column/Tab Break dibuang
karena tidak menyimpan data (urutan tampilannya diatur `CRM Fields Layout`,
lihat bab 8). Kolom Keterangan memuat flag: wajib, read-only, hidden, unique,
list (`in_list_view`), filter (`in_standard_filter`), default, fetch, depends-on.


#### `CMI Branch Access`
jenis: **single**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `intro` | HTML |  | <div class='text-muted' style='padding:4px 0'>Akses visibilitas dokumen per <b>Role</b>. Berlaku OTOMATIS ke setiap doctype yang punya field <code>branch_office</code> (Link CMI Office) - semua modul.<br><b>See All</b... |  |
| `default_access` | Select | Default Access (role tak terdaftar) | See All / Branch + Owner / Owner Only | wajib; default `Branch + Owner` |
| `blank_branch` | Select | Dokumen tanpa Branch | Terlihat semua / Tersembunyi | wajib; default `Terlihat semua` |
| `role_access` | Table | Role Access | CMI Branch Access Role |  |

Permission: System Manager (read, write, create, delete, share, print, email)

#### `CMI Branch Access Role`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `role` | Link | Role | Role | wajib; list |
| `access_level` | Select | Access Level | See All / Branch + Owner / Owner Only | wajib; list; default `Branch + Owner` |

#### `CMI Office`
jenis: **doctype** - autoname: `field:office_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `office_name` | Data | Office Name |  | wajib; unique; list |
| `city` | Data | City |  | list |
| `address` | Small Text | Address |  |  |
| `phone` | Data | Phone |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CMI User Branch`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `branch` | Link | Branch | CMI Office | wajib; list |

#### `CRM Call Log`
jenis: **doctype** - autoname: `field:id`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `id` | Data | ID |  | unique |
| `from` | Data | From Number |  | wajib; list; filter |
| `status` | Select | Status | Initiated / Ringing / In Progress / Completed / Failed / Busy / No Answer / Queued / Canceled | wajib; filter |
| `start_time` | Datetime | Start Time |  |  |
| `medium` | Data | Medium |  |  |
| `type` | Select | Type | Incoming / Outgoing | wajib; list; filter |
| `to` | Data | To Number |  | wajib; list; filter |
| `duration` | Duration | Duration |  | list |
| `recording_url` | Small Text | Recording URL |  |  |
| `end_time` | Datetime | End Time |  |  |
| `note` | Link | Note | FCRM Note |  |
| `receiver` | Link | Call Received By | User | tampil bila `eval:doc.type == 'Incoming'` |
| `caller` | Link | Caller | User | tampil bila `eval:doc.type == 'Outgoing'` |
| `reference_doctype` | Link | Reference Document Type | DocType | default `CRM Lead` |
| `reference_docname` | Dynamic Link | Reference Name | reference_doctype |  |
| `links` | Table | Links | Dynamic Link |  |
| `telephony_medium` | Select | Telephony Medium |  / Manual / Twilio / Exotel | read-only; list; filter |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Communication Status`
jenis: **doctype** - autoname: `field:status`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `status` | Data | Status |  | wajib; unique; list |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Contacts`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `contact` | Link | Contact | Contact | list |
| `full_name` | Data | Full Name |  | read-only; list; fetch `contact.full_name` |
| `email` | Data | Email |  | read-only; list; fetch `contact.email_id` |
| `mobile_no` | Data | Mobile No. | Phone | read-only; list; fetch `contact.mobile_no` |
| `phone` | Data | Phone | Phone | read-only; fetch `contact.phone` |
| `gender` | Link | Gender | Gender | read-only; fetch `contact.gender` |
| `is_primary` | Check | Is Primary |  | list; default `0` |

#### `CRM Cost Component`
jenis: **doctype** - autoname: `field:component_name` - title: `component_name` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `component_name` | Data | Component Name |  | wajib; unique; list |
| `date` | Date | Date |  | list; default `Today` |
| `validity_date` | Date | Validity Date |  |  |
| `type` | Link | Type | CRM Cost Type | wajib; list; default `Variable Cost` |
| `description` | Small Text | Description |  |  |
| `disabled` | Check | Disabled |  | default `0` |
| `status` | Select | Status | Draft / Validated / Invalidated | read-only; list; default `Draft` |
| `validated_by` | Link | Validated By | User | read-only |
| `validated_at` | Datetime | Validated At |  | read-only |
| `items` | Table | Items | CRM Cost Item |  |
| `total_amount` | Currency | Total |  | read-only; bold |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Cost Component Link`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `cost_component` | Link | Cost Component | CRM Cost Component | wajib; list |

#### `CRM Cost Item`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `cost_key` | Data | Cost Key |  | read-only; hidden |
| `source_component` | Link | From Component | CRM Cost Component | read-only |
| `item_name` | Data | Item |  | wajib; list; bold |
| `qty` | Float | Qty |  | list; default `1` |
| `uom` | Data | UOM |  | list |
| `rate` | Currency | Rate |  | list; default `0` |
| `amount` | Currency | Amount |  | read-only; list; bold |
| `remarks` | Small Text | Remarks |  |  |

#### `CRM Cost Type`
jenis: **doctype** - autoname: `field:type_name` - title: `type_name` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type_name` | Data | Type Name |  | wajib; unique; list |
| `behavior` | Select | Behavior | Variable Cost / Fixed Cost | wajib; list; default `Variable Cost` |
| `disabled` | Check | Disabled |  | default `0` |
| `description` | Small Text | Description |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Dashboard`
jenis: **doctype** - autoname: `field:title` - title: `title`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `layout` | Code | Layout | JSON | default `[]` |
| `title` | Data | Name |  | unique |
| `user` | Link | User | User | tampil bila `private` |
| `private` | Check | Private |  | default `0` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Dropdown Item`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `label` | Data | Label |  | list |
| `type` | Select | Type | Route / Separator | list |
| `route` | Data | Route |  | list; tampil bila `eval:doc.type == 'Route'` |
| `hidden` | Check | Hidden |  | list; default `0` |
| `is_standard` | Check | Is Standard |  | read-only; default `0` |
| `icon` | Code | Icon |  |  |
| `open_in_new_window` | Check | Open in new window |  | default `1`; tampil bila `eval:doc.type == 'Route'` |
| `name1` | Data | Name |  | read-only; unique; tampil bila `eval:doc.is_standard` |

#### `CRM Estimation`
jenis: **doctype** - title: `estimation_no` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `estimation_no` | Data | Number |  | read-only; unique; list |
| `customer_id` | Data | Customer |  | list |
| `effective_date` | Date | Effective Date |  | list |
| `expired_date` | Date | Expired Date |  |  |
| `quo_date` | Date | Quotation Date |  |  |
| `quo_no` | Link | Quotation No | CRM Quotation |  |
| `purpose` | Select | Purpose | Customer / Agent / Quotation |  |
| `estimation_type` | Select | Estimation Type | Expedition / Trading |  |
| `job_type` | Data | Job Type |  |  |
| `size` | Data | Size |  |  |
| `estimation_counter` | Int | Estimation Counter |  |  |
| `disabled` | Check | Disabled |  | filter; default `0` |
| `disabled_date` | Datetime | Disabled Date |  | tampil bila `disabled` |
| `disabled_reason` | Small Text | Disabled Reason |  | tampil bila `disabled` |
| `disabled_fleet` | Data | Disabled Fleet |  |  |
| `remarks` | Text | Remarks |  |  |
| `revenue_items` | Table | Revenue | CRM Estimation Detail |  |
| `expense_items` | Table | Expense | CRM Estimation Detail |  |
| `req_approval` | Check | Request Approval |  | default `0` |
| `approved_by` | Link | Approved By | User |  |
| `approved_datetime` | Datetime | Approved Datetime |  |  |
| `rev_inc_tax` | Currency | Revenue Including Tax | IDR |  |
| `est_profit` | Currency | Estimated Profit | IDR |  |
| `est_profit_date` | Datetime | Est. Profit Date |  |  |
| `est_profit_by` | Link | Est. Profit By | User |  |
| `acc_manager` | Data | Account Manager |  |  |
| `kam_type` | Data | KAM Type |  |  |
| `cs` | Data | CS |  |  |
| `cs2` | Data | CS 2 |  |  |
| `kam_remarks` | Small Text | KAM Remarks |  |  |
| `e_department` | Data | E-Department |  |  |
| `route1` | Link | Route 1 | Fleet Location |  |
| `route2` | Link | Route 2 | Fleet Location |  |
| `route3` | Link | Route 3 | Fleet Location |  |
| `route4` | Link | Route 4 | Fleet Location |  |
| `route5` | Link | Route 5 | Fleet Location |  |
| `route6` | Link | Route 6 | Fleet Location |  |
| `route7` | Link | Route 7 | Fleet Location |  |
| `route8` | Link | Route 8 | Fleet Location |  |
| `loading` | Link | Loading | Fleet Location |  |
| `unloading` | Link | Unloading | Fleet Location |  |
| `est_km` | Float | KM |  |  |
| `est_days` | Int | Estimated Days |  |  |
| `branch_office` | Link | Branch Office | CMI Office |  |
| `route_map` | HTML | Map |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Estimation Detail`
jenis: **child table** - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type_id` | Link | Type | Item | wajib; list |
| `qty` | Float | Qty |  | list; default `1` |
| `jalur` | Data | Jalur |  | list |
| `csize` | Data | Cont. Size |  | list |
| `area_id` | Data | Area |  | list |
| `jenis_karantina` | Data | Karantina |  | list |
| `dest_id` | Data | Destination |  | list |
| `amount` | Currency | Amount | currency | wajib; list |
| `per_doc` | Check | Per Doc |  | default `0` |
| `by_qty` | Check | By Qty |  | default `0` |
| `uom` | Data | UOM |  | list |
| `remarks` | Small Text | Remarks |  | list |
| `currency` | Link | Currency | Currency | list; default `IDR` |
| `is_expense` | Check | Is Expense |  | read-only; default `0` |
| `supplier_id` | Data | Supplier |  |  |
| `shipping_line_id` | Data | Shipping Line |  |  |
| `port_id` | Data | Port |  |  |
| `sandaran_id` | Data | Sandaran |  |  |

#### `CRM Exotel Settings`
jenis: **single**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `enabled` | Check | Enabled |  | default `0` |
| `account_sid` | Data | Account SID |  | tampil bila `enabled` |
| `api_key` | Data | API Key |  | list; tampil bila `enabled` |
| `api_token` | Password | API Token |  | list; tampil bila `enabled` |
| `record_call` | Check | Record Outgoing Calls |  | default `0`; tampil bila `enabled` |
| `webhook_verify_token` | Data | Webhook Verify Token |  | tampil bila `enabled` |
| `subdomain` | Data | Subdomain |  | tampil bila `enabled` |

Permission: System Manager (read, write, create, delete, share, print, email) - Sales Manager (read, write, create, delete, share, print, email)

#### `CRM Fields Layout`
jenis: **doctype** - autoname: `format:{dt}-{type}`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `dt` | Link | Document Type | DocType | list; filter |
| `type` | Select | Type | Quick Entry / Side Panel / Data Fields / Grid Row / Required Fields | list; filter |
| `layout` | Code | Layout | JSON |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Form Script`
jenis: **doctype** - autoname: `prompt`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `dt` | Link | DocType | DocType | wajib; list |
| `enabled` | Check | Enabled |  | hidden; default `0` |
| `script` | Code | Script | JS | default `function setupForm({ doc }) {     return` |
| `view` | Select | Apply To | Form / List | list; set-once; default `Form` |
| `is_standard` | Check | Is Standard |  | no-copy; default `0` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Global Settings`
jenis: **doctype** - autoname: `hash`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `dt` | Link | DocType | DocType | wajib; list; default `DocType` |
| `type` | Select | Type | Quick Filters / Sidebar Items | wajib; list |
| `json` | JSON | JSON |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Holiday`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `date` | Date | Date |  | wajib; list |
| `weekly_off` | Check | Weekly Off |  | default `0` |
| `description` | Text Editor | Description |  | wajib; list |

#### `CRM Holiday List`
jenis: **doctype** - autoname: `field:holiday_list_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `holiday_list_name` | Data | Holiday List Name |  | wajib; unique; list |
| `from_date` | Date | From Date |  | wajib; list |
| `to_date` | Date | To Date |  | wajib; list |
| `total_holidays` | Int | Total Holidays |  |  |
| `weekly_off` | Select | Weekly Off |  / Monday / Tuesday / Wednesday / Thursday / Friday / Saturday / Sunday |  |
| `add_to_holidays` | Button | Add to Holidays | add_to_holidays |  |
| `clear_table` | Button | Clear Table | clear_table |  |
| `holidays` | Table | Holidays | CRM Holiday |  |

Permission: Sales User (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)

#### `CRM Industry`
jenis: **doctype** - autoname: `field:industry`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `industry` | Data | Industry |  | unique |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Inquiry`
jenis: **doctype** - autoname: `naming_series:` - title: `subject` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `organization` | Link | Account | CRM Organization | wajib; filter |
| `probability` | Percent | Probability |  |  |
| `annual_revenue` | Currency | Estimation Cost | currency | fetch `.annual_revenue` |
| `website` | Data | Website |  | fetch `.website` |
| `next_step` | Data | Next Step |  |  |
| `lead` | Link | Lead | CRM Lead |  |
| `inquiry_owner` | Link | Inquiry Owner | User | default `__user` |
| `naming_series` | Select | Naming Series | INQ/.####./CMI/.YY. | default `INQ/.####./CMI/.YY.` |
| `email` | Data | Primary email | Email | filter |
| `mobile_no` | Data | Primary mobile no | Phone |  |
| `status` | Link | Status | CRM Inquiry Status | wajib; list; filter; index |
| `contacts` | Table | Contacts | CRM Contacts |  |
| `sla` | Link | SLA | CRM Service Level Agreement |  |
| `response_by` | Datetime | Response By |  | read-only |
| `sla_status` | Select | SLA Status |  / First Response Due / Rolling Response Due / Failed / Fulfilled | read-only |
| `sla_creation` | Datetime | SLA Creation |  | read-only |
| `first_response_time` | Duration | First Response Time |  | read-only |
| `first_responded_on` | Datetime | First Responded On |  | read-only |
| `communication_status` | Link | Communication Status | CRM Communication Status | default `Open` |
| `territory` | Data | Territory |  | fetch `.territory` |
| `source` | Link | Source | CRM Lead Source |  |
| `no_of_employees` | Select | No. of Employees | 1-10 / 11-50 / 51-200 / 201-500 / 501-1000 / 1000+ |  |
| `job_title` | Data | Job Title |  |  |
| `phone` | Data | Primary phone | Phone |  |
| `status_change_log` | Table | Status Change Log | CRM Status Change Log |  |
| `lead_name` | Data | Lead Name |  |  |
| `organization_name` | Data | Account Name |  | wajib; fetch `organization.organization_name` |
| `industry` | Link | Industry | CRM Industry |  |
| `salutation` | Link | Salutation | Salutation |  |
| `first_name` | Data | First name |  |  |
| `last_name` | Data | Last name |  |  |
| `gender` | Link | Gender | Gender |  |
| `contact` | Link | Contact | Contact |  |
| `currency` | Link | Currency | Currency |  |
| `inquiry_value` | Currency | Inquiry Value | currency |  |
| `lost_reason` | Link | Lost Reason | CRM Lost Reason |  |
| `lost_notes` | Text | Lost Notes |  |  |
| `exchange_rate` | Float | Exchange Rate |  | default `1` |
| `expected_inquiry_value` | Currency | Expected Inquiry Value | currency |  |
| `expected_closure_date` | Date | Expected Closure Date |  |  |
| `closed_date` | Date | Closed Date |  |  |
| `rolling_responses` | Table | Rolling Responses | CRM Rolling Response Time |  |
| `last_response_time` | Duration | Last Response Time |  | read-only |
| `last_responded_on` | Datetime | Last Responded On |  | read-only |
| `type_inquiry` | Table MultiSelect | Type of Inquiry | CRM Inquiry Type Inquiry | wajib |
| `shipper_consignee` | Small Text | Shipper/Consignee |  | wajib |
| `transportation_mode` | Select | Transportation Mode |  / Ocean COC / Ocean SOC / Inland Truck SOC / Inland Truck COC / Railway COC / Air Freight COC / Air Freight SOC / Railway SOC | wajib |
| `incoterms` | Select | Incoterms |  / EXW (EX WOKRS) / FCA (FREE CARRIER) / FAS (FREE ALONGSIDE SHIP) / FOB (FREE ON BOARD) / CFR (COST & FREIGHT) / CIF (COST, INSURANCE & FREIGHT) / CPT (COST PAID TO) / CIP (CARRIER, INSURANCE PAID TO) / DPU (DELIVERE... |  |
| `date_shipment` | Date | Date of Shipment |  | wajib |
| `qty_volume` | Data | Quantity/Volume |  |  |
| `port_pol_destination_detail_address` | Small Text | Port/POL/Destination Detail Address |  |  |
| `cargo_commodity` | Small Text | Cargo Commodity / Type / HS Code |  |  |
| `cargo_weight` | Data | Cargo Weight (KG) / Volume / Packaging |  | wajib |
| `status_cargo` | Data | Status of Cargo |  |  |
| `job_service` | Autocomplete | Job Service |  / Container - Container 40 Dry / EMKL & Trucking - Isotank / Door To Door Isotank / Export Service Isotank 25kl / Trucking Container 20ft / Trucking Isotank 25kl / Import Door To Door / Container - Container 20 & 40 ... | wajib |
| `service_type` | Select | Service Type |  / New Customer / New Job Service / New Product / Existing Job Service / Existing Product |  |
| `business_unit` | Select | Business Unit |  / ISO (LOCAL/ DOMESTIK ISOTANK) / EMKL  (TRUCKING DOMESTIK NON ISOTANK) / PCP (EXPORT ISOTANK) / FF (EXPORT/IMPORT CONTAINER DRY) / PKGOLEO (PRODUCT) / LOG (CONTRACT LOGISTICS) | wajib |
| `remarks` | Text | Remarks |  |  |
| `inquiry_date` | Date | Inquiry Date |  | wajib; default `Today` |
| `cargo_packaging` | Data | Cargo Packaging |  | wajib |
| `origin` | Link | Origin | Fleet Location |  |
| `destination` | Link | Destination | Fleet Location |  |
| `origin_text` | Small Text | Origin (Teks Asli) |  | read-only; hidden; no-copy |
| `destination_text` | Small Text | Destination (Teks Asli) |  | read-only; hidden; no-copy |
| `qty` | Float | Quantity |  |  |
| `rate` | Currency | Rate | currency |  |
| `estimasi_tarif` | Currency | Fixed Cost | currency | read-only |
| `costing_procurement` | Currency | Variable Cost | currency |  |
| `reimburse_cost` | Currency | Reimburse Cost | currency |  |
| `subject` | Data | Subject |  | wajib |
| `is_void` | Check | Void |  | read-only; filter; default `0` |
| `void_reason` | Small Text | Void Reason |  | read-only |
| `void_at` | Datetime | Voided At |  | read-only |
| `void_by` | Link | Voided By | User | read-only |
| `products` | Table | Products | CRM Products |  |
| `net_total` | Currency | Net Total | currency |  |
| `total` | Currency | Total | currency |  |
| `branch_office` | Link | Branch | CMI Office |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Inquiry Status`
jenis: **doctype** - autoname: `field:inquiry_status`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `color` | Select | Color | black / gray / blue / green / red / pink / orange / amber / yellow / cyan / teal / violet / purple | list; default `gray` |
| `inquiry_status` | Data | Status |  | wajib; unique; list |
| `position` | Int | Position |  | list |
| `probability` | Percent | Probability |  | list |
| `type` | Select | Type | Open / Ongoing / On Hold / Won / Lost | list; default `Open` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Inquiry Transportation Mode`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `mode` | Link | Transportation Mode | CRM Transportation Mode | wajib; list |

#### `CRM Inquiry Type Inquiry`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type` | Link | Type of Inquiry | CRM Type Inquiry |  |

#### `CRM Invitation`
jenis: **doctype**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `email` | Data | Email |  | wajib; list |
| `role` | Select | Role |  / Sales User / Sales Manager / System Manager | wajib; list |
| `key` | Data | Key |  |  |
| `invited_by` | Link | Invited By | User | list |
| `status` | Select | Status |  / Pending / Accepted / Expired | list |
| `email_sent_at` | Datetime | Email Sent At |  |  |
| `accepted_at` | Datetime | Accepted At |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Lead`
jenis: **doctype** - title: `lead_name` - image: `image` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `naming_series` | Select | Series | CRM-LEAD-.YYYY.- | default `CRM-LEAD-.YYYY.-` |
| `salutation` | Link | Salutation | Salutation |  |
| `first_name` | Data | First Name |  | wajib |
| `middle_name` | Data | Middle Name |  |  |
| `last_name` | Data | Last Name |  |  |
| `gender` | Link | Gender | Gender |  |
| `status` | Link | Status | CRM Lead Status | wajib; list; filter; index |
| `email` | Data | Email | Email | filter; index |
| `website` | Data | Website |  |  |
| `mobile_no` | Data | Mobile No. | Phone |  |
| `phone` | Data | Phone | Phone |  |
| `no_of_employees` | Select | No. of Employees | 1-10 / 11-50 / 51-200 / 201-500 / 501-1000 / 1000+ |  |
| `annual_revenue` | Currency | Annual Revenue |  |  |
| `lead_owner` | Link | Lead Owner | User |  |
| `source` | Link | Source | CRM Lead Source |  |
| `industry` | Link | Industry | CRM Industry |  |
| `image` | Attach Image | Image |  | hidden |
| `lead_name` | Data | Full Name |  | filter; index |
| `job_title` | Data | Job Title |  |  |
| `organization` | Data | Account |  | filter |
| `converted` | Check | Converted |  | list; filter; default `0` |
| `sla` | Link | SLA | CRM Service Level Agreement |  |
| `sla_creation` | Datetime | SLA Creation |  | read-only |
| `sla_status` | Select | SLA Status |  / First Response Due / Rolling Response Due / Failed / Fulfilled | read-only |
| `response_by` | Datetime | Response By |  | read-only |
| `first_response_time` | Duration | First Response Time |  | read-only |
| `first_responded_on` | Datetime | First Responded On |  | read-only |
| `communication_status` | Link | Communication Status | CRM Communication Status | default `Open` |
| `territory` | Link | Territory | CRM Territory |  |
| `status_change_log` | Table | Status Change Log | CRM Status Change Log |  |
| `products` | Table | Products | CRM Products |  |
| `total` | Currency | Total | currency | read-only |
| `net_total` | Currency | Net Total | currency | read-only |
| `facebook_lead_id` | Data | Facebook Lead ID |  | unique |
| `facebook_form_id` | Data | Facebook Form ID |  |  |
| `rolling_responses` | Table | Rolling Responses | CRM Rolling Response Time |  |
| `last_response_time` | Duration | Last Response Time |  | read-only |
| `last_responded_on` | Datetime | Last Responded On |  | read-only |
| `lost_reason` | Link | Lost Reason | CRM Lost Reason |  |
| `lost_notes` | Text | Lost Notes |  |  |
| `nib` | Data | NIB |  |  |
| `npwp` | Data | NPWP |  |  |
| `type_industry` | Data | Type Industry |  |  |
| `target_goals` | Small Text | Target Goals |  |  |
| `address` | Small Text | Address |  |  |
| `village` | Data | Village |  |  |
| `sub_district` | Data | Sub-District |  |  |
| `regency` | Data | Regency |  |  |
| `city` | Data | City |  |  |
| `postal_code` | Data | Postal Code |  |  |
| `is_void` | Check | Void |  | read-only; filter; default `0` |
| `void_reason` | Small Text | Void Reason |  | read-only |
| `void_at` | Datetime | Voided At |  | read-only |
| `void_by` | Link | Voided By | User | read-only |
| `branch_office` | Link | Branch | CMI Office |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Lead Source`
jenis: **doctype** - autoname: `field:source_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `source_name` | Data | Source Name |  | wajib; unique; list |
| `details` | Text Editor | Details |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Lead Status`
jenis: **doctype** - autoname: `field:lead_status`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `color` | Select | Color | black / gray / blue / green / red / pink / orange / amber / yellow / cyan / teal / violet / purple | list; default `gray` |
| `lead_status` | Data | Status |  | wajib; unique; list |
| `position` | Int | Position |  | list; default `1` |
| `type` | Select | Type | Open / Ongoing / On Hold / Won / Lost | list; default `Open` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Lost Reason`
jenis: **doctype** - autoname: `field:lost_reason`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `lost_reason` | Data | Lost Reason |  | wajib; unique; list |
| `description` | Text Editor | Description |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Meeting`
jenis: **doctype** - autoname: `MTG-.#####.` - title: `subject` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `subject` | Data | Subject |  | wajib; list |
| `status` | Select | Status | Scheduled / Visited / Cancelled | list; filter; default `Scheduled` |
| `location` | Data | Location |  |  |
| `organization` | Link | Related To | CRM Organization |  |
| `contact` | Link | Contact | Contact |  |
| `marketing` | Link | Marketing | User | wajib; list; default `__user` |
| `lead` | Link | Lead | CRM Lead |  |
| `inquiry` | Link | Inquiry | CRM Inquiry |  |
| `quotation` | Link | Quotation | CRM Quotation |  |
| `meeting_date` | Datetime | Meeting Date |  | wajib; list |
| `meeting_from` | Datetime | From |  |  |
| `meeting_to` | Datetime | To |  |  |
| `purpose` | Small Text | Tujuan Visit |  |  |
| `venue` | Data | Meeting Venue |  |  |
| `provider` | Data | Provider |  |  |
| `nominal` | Currency | Nominal |  |  |
| `checkin_time` | Datetime | Check-In Time |  | read-only |
| `checkin_latitude` | Float | Check-In Latitude |  | read-only |
| `checkin_longitude` | Float | Check-In Longitude |  | read-only |
| `checkin_address` | Small Text | Check-In Address |  |  |
| `checkout_time` | Datetime | Check-Out Time |  | read-only |
| `checkout_latitude` | Float | Check-Out Latitude |  | read-only |
| `summary` | Text | Summary Meeting |  |  |
| `checkout_longitude` | Float | Check-Out Longitude |  | read-only |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, report, export, share, print, email) - Sales User (read, write, create, report, export, share, print, email)

#### `CRM Notification`
jenis: **doctype**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `from_user` | Link | From User | User |  |
| `type` | Select | Type | Mention / Task / Assignment / WhatsApp | wajib; list |
| `to_user` | Link | To User | User | wajib; list |
| `comment` | Link | Comment | Comment | hidden |
| `read` | Check | Read |  | default `0` |
| `message` | HTML Editor | Message |  | list |
| `reference_name` | Dynamic Link | Reference Doc | reference_doctype |  |
| `reference_doctype` | Link | Reference Doctype | DocType |  |
| `notification_type_doctype` | Link | Notification Type Doctype | DocType |  |
| `notification_type_doc` | Dynamic Link | Notification Type Doc | notification_type_doctype |  |
| `notification_text` | Text | Notification Text |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Organization`
jenis: **doctype** - autoname: `field:organization_name` - image: `organization_logo`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `organization_name` | Data | Account Name |  | unique; filter |
| `website` | Data | Website |  |  |
| `organization_logo` | Attach Image | Account Logo |  |  |
| `annual_revenue` | Currency | Annual Revenue | currency |  |
| `industry` | Data | Industry | CRM Industry | filter |
| `territory` | Link | Territory | CRM Territory | filter |
| `address` | Small Text | Address | Address |  |
| `phone` | Data | Phone |  |  |
| `billing_city` | Data | Billing City |  |  |
| `nib` | Data | NIB |  |  |
| `npwp` | Data | NPWP |  |  |
| `regency` | Data | Regency |  |  |
| `regency_city` | Data | Regency City |  |  |
| `postal_code_office` | Data | Postal Code Office |  |  |
| `pic_name` | Data | PIC Name |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Procurement Comment`
jenis: **doctype** - autoname: `hash`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `quotation` | Link | Quotation | CRM Quotation | wajib; list; index |
| `reply_to` | Link | Reply To | CRM Procurement Comment |  |
| `content` | Long Text | Content |  | wajib; list |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, create, report, export, share, print, email) - Sales User (read, write, delete)

#### `CRM Product`
jenis: **doctype** - autoname: `field:product_code` - title: `product_name` - image: `image` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `naming_series` | Select | Naming Series | CRM-PROD-.YYYY.- |  |
| `product_code` | Data | Product Code |  | wajib; unique; list |
| `product_name` | Data | Product Name |  |  |
| `disabled` | Check | Disabled |  | default `0` |
| `image` | Attach Image | Image |  |  |
| `description` | Text Editor | Description |  |  |
| `standard_rate` | Currency | Standard Selling Rate |  |  |
| `cost_components` | Table MultiSelect | Cost Components | CRM Cost Component Link |  |
| `fixed_cost_per_day` | Currency | Fixed Cost / Day |  | read-only; bold |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Products`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `product_code` | Link | Product | CRM Product | list; bold |
| `notes` | Small Text | Notes |  | list |
| `currency` | Link | Currency | Currency | list; default `IDR` |
| `qty` | Float | Quantity |  | bold; default `1` |
| `uom` | Link | UOM | UOM | list |
| `duration` | Int | Duration (Day) |  | list; default `1` |
| `price` | Currency | Price | currency | list; default `0` |
| `rate` | Float | Ex. Rate |  | list; bold; default `1` |
| `procurement_price` | Currency | Base Price | currency | read-only; list; default `0` |
| `competitor_price` | Currency | Competitor Price | currency | list; default `0` |
| `cost_key` | Data | Cost Key |  | read-only; hidden |
| `cost_seeded` | Data | Cost Defaults Loaded For |  | read-only; hidden |
| `fixed_cost` | Currency | Fixed Cost | currency | read-only |
| `variable_cost` | Currency | Variable Cost | currency | read-only |
| `margin_percent` | Percent | Margin % |  | list; default `0` |
| `margin_amount` | Currency | Margin Amount | currency | read-only |
| `discount_percentage` | Percent | Discount % |  | bold |
| `discount_amount` | Currency | Discount Amount | currency | read-only |
| `amount` | Currency | Amount |  | read-only; bold |
| `net_amount` | Currency | Net Amount | currency | read-only; bold; tampil bila `discount_percentage` |
| `autocomplete` | Autocomplete | Autocomplete | A / B / C / D / E / F / G / H / I / J / K / L / M / N / O / P / Q / R / S / T / U / V / W / X / Y / Z |  |

#### `CRM Quotation`
jenis: **doctype** - title: `subject` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `number` | Data | Number |  | list; filter |
| `subject` | Data | Subject |  | wajib; list; fetch `inquiry.subject` |
| `state` | Select | Status | Draft / Sent / Waiting / Win / Lose / Converted | read-only; filter; default `Draft` |
| `date` | Date | Date |  | wajib; list; default `Today` |
| `disabled` | Check | Disabled |  | default `0` |
| `account` | Link | Account | CRM Organization | read-only; list; fetch `inquiry.organization` |
| `account_name` | Data | Account Name |  | fetch `account.organization_name` |
| `contact_name` | Link | Contact | Contact |  |
| `attention` | Data | Attention |  | wajib |
| `inquiry` | Link | Inquiry | CRM Inquiry | wajib |
| `inquiry_details` | HTML | Inquiry Details |  |  |
| `company` | Link | Company | Company |  |
| `cost_center` | Link | Cost Center | Cost Center |  |
| `currency` | Link | Currency | Currency | default `IDR` |
| `rate` | Float | Exchange Rate |  | default `1.0` |
| `cargo` | Data | Cargo |  | wajib |
| `packaging` | Data | Packaging |  | wajib |
| `loading` | Link | Loading | Fleet Location |  |
| `unloading` | Link | Unloading | Fleet Location |  |
| `loading_text` | Small Text | Loading (Teks Asli) |  | read-only; no-copy; tampil bila `eval:doc.loading_text` |
| `unloading_text` | Small Text | Unloading (Teks Asli) |  | read-only; no-copy; tampil bila `eval:doc.unloading_text` |
| `distance_km` | Float | KM |  |  |
| `get_km` | Button | Get KM |  |  |
| `check_gmap` | Button | Check in GMap |  |  |
| `products` | Table | Products | CRM Products | wajib |
| `cost_items` | Table | Variable Cost Items | CRM Cost Item | hidden |
| `net_total` | Currency | Net Total | currency | read-only; list |
| `validity` | Small Text | Validity Note |  |  |
| `validity_date` | Date | Validity Date |  |  |
| `validity_date_to` | Date | Validity Date To |  |  |
| `payterm` | Small Text | Payment Term |  |  |
| `additional1_title` | Data | Additional Title |  | default `Rate Include` |
| `additional1_item` | Text | Additional Item |  |  |
| `additional1_amount` | Text | Additional Amount |  |  |
| `additional2_title` | Data | Additional Title 2 |  | default `Rate Exclude` |
| `additional2_item` | Text | Additional Item 2 |  |  |
| `additional2_amount` | Text | Additional Amount 2 |  |  |
| `term_detail` | Text | Terms Detail |  |  |
| `rate_include` | Text | Rate Include |  |  |
| `rate_exclude` | Text | Rate Exclude |  |  |
| `remark` | Small Text | Remark |  |  |
| `printed_by` | Link | Printed By | User |  |
| `print_full_page` | Check | Print Full 1 Page |  | default `0` |
| `is_void` | Check | Void |  | read-only; filter; default `0` |
| `void_reason` | Small Text | Void Reason |  | read-only |
| `void_at` | Datetime | Voided At |  | read-only |
| `void_by` | Link | Voided By | User | read-only |
| `branch` | Data | Branch |  |  |
| `tac` | Data | Terms and Conditions Title |  | default `Terms and Conditions` |
| `tac_detail` | Text | Terms and Conditions Detail |  |  |
| `branch_office` | Link | Office | CMI Office |  |
| `rate_include_amount` | Text | Amount |  |  |
| `rate_exclude_amount` | Text | Amount |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, report, export, share, print, email) - Sales User (read, write, create, report, export, share, print, email)

#### `CRM Quotation Additional`
jenis: **child table** - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type` | Select | Type | additional1 / additional2 | wajib; list |
| `title` | Data | Title |  | list |
| `item_name` | Data | Item Name |  | wajib; list |
| `price` | Currency | Price |  | list |

#### `CRM Quotation Product`
jenis: **child table** - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `product` | Link | Product | Item | wajib; list |
| `remark` | Data | Remark |  | list |
| `qty` | Float | Qty |  | list; default `1` |
| `price` | Currency | Price |  | list |
| `amount` | Currency | Amount |  | read-only; list |

#### `CRM Rolling Response Time`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `response_time` | Duration | Response Time |  | read-only; list |
| `responded_on` | Datetime | Responded On |  | read-only; list |
| `status` | Select | Status | Fulfilled / Failed | read-only; list |

#### `CRM Service Day`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `workday` | Select | Workday | Monday / Tuesday / Wednesday / Thursday / Friday / Saturday / Sunday | wajib; list |
| `start_time` | Time | Start Time |  | wajib; list |
| `end_time` | Time | End Time |  | wajib; list |

#### `CRM Service Level Agreement`
jenis: **doctype** - autoname: `field:sla_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `sla_name` | Data | SLA Name |  | wajib; unique; list; filter |
| `enabled` | Check | Enabled |  | default `0` |
| `default` | Check | Default |  | default `0` |
| `condition` | Code | Condition | Python | tampil bila `eval: !doc.condition_json` |
| `apply_on` | Link | Apply On | DocType | wajib |
| `priorities` | Table | Priorities | CRM Service Level Priority | wajib |
| `working_hours` | Table | Working Hours | CRM Service Day | wajib |
| `start_date` | Date | Start Date |  |  |
| `end_date` | Date | End Date |  |  |
| `holiday_list` | Link | Holiday List | CRM Holiday List |  |
| `rolling_responses` | Check | Rolling Responses |  | default `0` |
| `condition_json` | Code | Condition |  | tampil bila `eval: doc.condition_json` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)

#### `CRM Service Level Priority`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `default_priority` | Check | Default Priority |  | list; default `0` |
| `priority` | Link | Priority | CRM Communication Status | wajib; list |
| `first_response_time` | Duration | First Response TIme |  | wajib; list |

#### `CRM Status Change Log`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `from` | Data | From |  | list |
| `from_date` | Datetime | From Date |  | list |
| `duration` | Duration | Duration |  | list |
| `to` | Data | To |  | list |
| `to_date` | Datetime | To Date |  | list |
| `last_status_change_log` | Link | Last Status Change Log | CRM Status Change Log |  |
| `log_owner` | Link | Owner | User |  |
| `from_type` | Data | From Type |  | list |
| `to_type` | Data | To Type |  | list |

#### `CRM Task`
jenis: **doctype** - autoname: `autoincrement`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `title` | Data | Title |  | wajib; list; filter |
| `priority` | Select | Priority | Low / Medium / High | filter |
| `start_date` | Date | Start Date |  |  |
| `assigned_to` | Link | Assigned To | User | filter |
| `status` | Select | Status | Backlog / Todo / In Progress / Done / Canceled | list; filter |
| `due_date` | Datetime | Due Date |  | filter |
| `description` | Text Editor | Description |  |  |
| `reference_doctype` | Link | Reference Document Type | DocType |  |
| `reference_docname` | Dynamic Link | Reference Doc | reference_doctype |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Telephony Agent`
jenis: **doctype** - autoname: `field:user` - title: `user_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `user` | Link | User | User | wajib; unique; list; filter |
| `mobile_no` | Data | Mobile No. |  | read-only; list; filter |
| `user_name` | Data | User Name |  | list; filter; fetch `user.full_name` |
| `exotel_number` | Data | Exotel Number |  |  |
| `twilio_number` | Data | Twilio Number |  |  |
| `phone_nos` | Table | Phone Numbers | CRM Telephony Phone |  |
| `default_medium` | Select | Default Medium |  / Twilio / Exotel |  |
| `call_receiving_device` | Select | Device | Computer / Phone | default `Computer` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Telephony Phone`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `number` | Data | Number |  | wajib; list |
| `is_primary` | Check | Is Primary |  | list; default `0` |

#### `CRM Territory`
jenis: **doctype** - autoname: `field:territory_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `territory_name` | Data | Territory Name |  | wajib; unique; list |
| `territory_manager` | Link | Territory Manager | User |  |
| `lft` | Int | Left |  | read-only; hidden; no-copy |
| `rgt` | Int | Right |  | read-only; hidden; no-copy |
| `is_group` | Check | Is Group |  | default `0` |
| `old_parent` | Link | Old Parent | CRM Territory |  |
| `parent_crm_territory` | Link | Parent CRM Territory | CRM Territory |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `CRM Transportation Mode`
jenis: **doctype** - autoname: `field:mode_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `mode_name` | Data | Transportation Mode |  | wajib; unique; list |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM Twilio Settings`
jenis: **single** - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `account_sid` | Data | Account SID |  | list; tampil bila `enabled` |
| `api_key` | Data | API Key |  | read-only; tampil bila `enabled` |
| `api_secret` | Password | API Secret |  | read-only; tampil bila `enabled` |
| `auth_token` | Password | Auth Token |  | list; tampil bila `enabled` |
| `twiml_sid` | Data | TwiML SID |  | tampil bila `enabled` |
| `record_calls` | Check | Record Calls |  | default `0`; tampil bila `enabled` |
| `enabled` | Check | Enabled |  | default `0` |
| `app_name` | Data | App Name |  |  |
| `twilio_apps` | Data | Twilio Apps |  | hidden |

Permission: System Manager (read, write, create, delete, share, print, email) - System Manager (read, write, delete, share, print, email) - Sales Manager (read, write, create, delete, share, print, email) - Sales Manager (read, write, delete, share, print, email)

#### `CRM Type Inquiry`
jenis: **doctype** - autoname: `field:inquiry_type`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `inquiry_type` | Data | Inquiry Type |  | wajib; unique; list |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, report, export, share, print, email)

#### `CRM View Settings`
jenis: **doctype** - autoname: `autoincrement` - title: `label` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `columns` | Code | Columns |  |  |
| `user` | Link | User | User |  |
| `rows` | Code | Rows |  |  |
| `filters` | Code | Filters |  |  |
| `label` | Data | Label |  | list; filter |
| `dt` | Link | DocType | DocType | list; filter |
| `order_by` | Code | Order By |  |  |
| `pinned` | Check | Pinned |  | default `0` |
| `route_name` | Data | Route Name |  |  |
| `load_default_columns` | Check | Load Default Columns |  | default `0` |
| `public` | Check | Public |  | default `0` |
| `icon` | Data | Icon |  |  |
| `type` | Select | Type | list / group_by / kanban | default `list` |
| `group_by_field` | Data | Group By Field |  |  |
| `column_field` | Data | Column Field |  |  |
| `kanban_columns` | Code | Kanban Columns |  |  |
| `kanban_fields` | Code | Kanban Fields |  |  |
| `title_field` | Data | Title Field |  |  |
| `is_standard` | Check | Is Standard |  | default `0` |
| `is_default` | Check | Is Default |  | default `0` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `ERPNext CRM Settings`
jenis: **single**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `api_key` | Data | API Key |  | tampil bila `eval:doc.enabled && doc.is_erpnext_in_different_site` |
| `api_secret` | Password | API Secret |  | tampil bila `eval:doc.enabled && doc.is_erpnext_in_different_site` |
| `erpnext_site_url` | Data | ERPNext Site URL |  | tampil bila `eval:doc.enabled && doc.is_erpnext_in_different_site` |
| `erpnext_company` | Data | Company in ERPNext site |  | tampil bila `enabled` |
| `enabled` | Check | Enabled |  | default `0` |
| `is_erpnext_in_different_site` | Check | Is ERPNext installed on a different site? |  | default `0`; tampil bila `enabled` |
| `create_customer_on_status_change` | Check | Create customer on status change |  | default `0`; tampil bila `enabled` |
| `deal_status` | Link | Deal Status | CRM Inquiry Status | tampil bila `eval:doc.enabled && doc.create_customer_on_status_change` |

Permission: System Manager (read, write, create, delete, share, print, email) - Sales Manager (read, write, create, delete, share, print, email) - Sales User (read, share, print, email)

#### `FCRM Note`
jenis: **doctype** - title: `title` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `title` | Data | Title |  | wajib; list; filter |
| `content` | Text Editor | Content |  | list; filter |
| `reference_doctype` | Link | Reference Document Type | DocType | default `CRM Lead` |
| `reference_docname` | Dynamic Link | Reference Doc | reference_doctype |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email) - Sales User (read, write, create, delete, report, export, share, print, email)

#### `FCRM Settings`
jenis: **single**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `restore_defaults` | Button | Restore Defaults |  |  |
| `dropdown_items` | Table |  | CRM Dropdown Item |  |
| `brand_logo` | Attach | Logo |  |  |
| `brand_name` | Data | Name |  |  |
| `favicon` | Attach | Favicon |  |  |
| `enable_forecasting` | Check | Enable Forecasting |  | default `0` |
| `currency` | Link | Currency | Currency | list |
| `service_provider` | Select | Service Provider | frankfurter.app / fawazahmed-exchange-api / exchangerate.host / exchangerate-api | default `frankfurter.app` |
| `access_key` | Data | Access Key |  | tampil bila `eval:doc.service_provider == 'exchangerate.host';` |
| `auto_update_expected_inquiry_value` | Check | Auto update Expected Inquiry Value |  | default `1` |
| `update_timestamp_on_new_communication` | Check | Update timestamp on new communication |  | default `1` |
| `auto_mark_replied_on_response` | Check | Mark lead/inquiry as replied on response |  | default `0` |
| `auto_reopen_on_new_communication` | Check | Reopen lead/inquiry on new communication |  | default `0` |
| `enable_crm_assistant` | Check | Assistant CRM |  | default `0` |
| `restore_demo_data` | Button | Restore Demo Data |  |  |

Permission: System Manager (read, write, create, delete, share, print, email) - Sales Manager (read, write, create, delete, share, print, email) - Sales User (read, share, print, email)

#### `Facebook Lead Form`
jenis: **doctype** - autoname: `field:id` - title: `form_name`  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `page` | Link | Page | Facebook Page | wajib; list |
| `id` | Data | ID |  | unique |
| `form_name` | Data | Form Name |  |  |
| `questions` | Table | Questions | Facebook Lead Form Question |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)

#### `Facebook Lead Form Question`
jenis: **child table**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `label` | Data | Label |  | list |
| `key` | Data | Key |  | wajib; list |
| `type` | Data | Type |  | list |
| `id` | Data | ID |  |  |
| `mapped_to_crm_field` | Autocomplete | Mapped to CRM Field |  | list |

#### `Facebook Page`
jenis: **doctype** - autoname: `field:id` - title: `page_name` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `category` | Data | Category |  |  |
| `id` | Data | ID |  | unique |
| `account_id` | Data | Account ID |  |  |
| `access_token` | Small Text | Access Token |  |  |
| `page_name` | Data | Page Name |  |  |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)

#### `Failed Lead Sync Log`
jenis: **doctype**  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type` | Select | Type | Duplicate / Failure / Synced | read-only; list; filter; default `Failure` |
| `lead_data` | Code | Lead Data | JSON | read-only |
| `source` | Link | Source | Lead Sync Source | read-only; list; filter |
| `traceback` | Code | Traceback |  | read-only |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)

#### `Lead Sync Source`
jenis: **doctype** - autoname: `prompt` - track changes  

| Field | Tipe | Label | Options | Keterangan |
|---|---|---|---|---|
| `type` | Select | Type | Facebook | wajib; list; default `Facebook` |
| `last_synced_at` | Datetime | Last Synced At |  | read-only |
| `access_token` | Password | Access Token |  | wajib |
| `facebook_page` | Link | Facebook Page | Facebook Page |  |
| `facebook_lead_form` | Link | Facebook Lead Form | Facebook Lead Form | unique |
| `enabled` | Check | Enabled? |  | default `1` |
| `background_sync_frequency` | Select | Background Sync Frequency | Every 5 Minutes / Every 10 Minutes / Every 15 Minutes / Hourly / Daily / Monthly | wajib; default `Hourly` |

Permission: System Manager (read, write, create, delete, report, export, share, print, email) - Sales Manager (read, write, create, delete, report, export, share, print, email)



---

---

## 6. Logika controller per doctype

Ringkasan setiap method controller: kapan jalan dan apa yang dikerjakan. Yang tidak
disebut di sini berarti controllernya kosong (`pass`).

### `CRM Lead` (`fcrm/doctype/crm_lead/crm_lead.py`)

| Method | Event | Isi |
|---|---|---|
| `autoname` | naming | `LD/{counter}/CMI/{yy}`, counter dari seri `LD-YY-.####.` |
| `before_validate` | | `set_sla()` |
| `validate` | | `validate_status`, `set_full_name`, `set_lead_name`, `set_title`, `validate_email`, `validate_lost_reason`; kalau `lead_owner` berubah maka share + assign; kalau `status` berubah maka `add_status_change_log` |
| `after_insert` | | share + assign ke `lead_owner` |
| `before_save` | | `apply_sla()` |
| `validate_status` | | `converted=1` memaksa status `Converted`; dokumen baru tanpa status memakai `New` atau status pertama bertipe Open |
| `set_full_name` | | `lead_name` = salutation + first + middle + last |
| `set_lead_name` | | fallback: organization, lalu bagian depan email, lalu `Unnamed Lead`; tanpa ketiganya melempar error kecuali `ignore_mandatory` |
| `set_title` | | `title` = organization atau lead_name |
| `validate_email` | | validasi format, larang email sama dengan `lead_owner`, ambil gravatar ke `image` |
| `validate_lost_reason` | | status bertipe Lost wajib `lost_reason`; `Other` wajib `lost_notes`; tambah/hapus section Lost Reason di side panel |
| `assign_agent` / `share_with_agent` | | ToDo assignment dan DocShare write; share user lain dicabut |
| `create_contact` / `create_organization` / `update_lead_contact` / `contact_exists` | konversi | lihat 3.1 |
| `create_inquiry` | konversi | salin field, insert `ignore_mandatory`, teruskan assignee |
| `set_sla` / `apply_sla` | | cari + terapkan SLA |
| `get_non_filterable_fields` | static | field yang tidak boleh jadi filter |
| `default_list_data` | static | kolom + rows default list view |
| `default_kanban_settings` | static | `column_field`, `title_field`, `kanban_fields` |

Fungsi modul: `normalize_account_name`, `account_name_score`, `find_similar_accounts`
(whitelisted), `convert_to_inquiry` (whitelisted).

### `CRM Inquiry` (`crm_inquiry.py`)

| Method | Event | Isi |
|---|---|---|
| `autoname` | | `INQ/{counter}/CMI/{yy}` |
| `before_validate` | | `set_sla()` |
| `validate` | | `validate_status`, `set_primary_contact`, `set_primary_email_mobile_no`; owner berubah maka share + assign; status berubah maka `add_status_change_log` dan (kalau tipe Won) isi `closed_date`; lalu `validate_forecasting_fields`, `validate_lost_reason`, `update_exchange_rate` |
| `after_insert` | | share + assign `inquiry_owner` |
| `before_save` | | `apply_sla()` |
| `validate_status` | | dokumen baru tanpa status memakai `Qualification` atau status pertama bertipe Open |
| `set_primary_contact` | | satu kontak berarti otomatis primary; kalau ada argumen, kontak itu yang primary |
| `set_primary_email_mobile_no` | | email/mobile/phone header diturunkan dari kontak primary; lebih dari satu primary ditolak |
| `update_closed_date` | | status `Won` mengisi `closed_date` |
| `update_default_probability` | | ambil `probability` dari master status bila masih 0 |
| `update_expected_inquiry_value` | | kalau `FCRM Settings.auto_update_expected_inquiry_value` aktif |
| `validate_forecasting_fields` | | tiga method di atas + wajib expected value/date kalau forecasting aktif |
| `validate_lost_reason` | | sama seperti Lead |
| `update_exchange_rate` | | `db_set` kurs terhadap `FCRM Settings.currency` |
| `default_list_data` / `default_kanban_settings` | static | konfigurasi list dan kanban |

Fungsi modul: `add_contact`, `remove_contact`, `set_primary_contact`, `create_inquiry`
(semua whitelisted), `create_organization`, `contact_exists`, `create_contact`.
File terpisah `crm_inquiry/api.py`: `get_inquiry_contacts`.

### `CRM Quotation` (`crm_quotation.py`)

| Method | Event | Isi |
|---|---|---|
| `autoname` | | `QT/{counter}/CMI/{YYYY}` |
| `validate` | | `validate_route`, `validate_distance`, dan tolak semua perubahan bila state tersimpan sudah `Converted` |
| `validate_route` | | Loading/Unloading wajib untuk dokumen baru atau kalau sebelumnya terisi |
| `validate_distance` | | `distance_km > 0` dengan pengecualian yang sama |
| `before_save` | | `calculate_costing()`, lalu `amount = qty x price x rate` tiap produk dan `net_total` |
| `calculate_costing` | | isi `cost_key`, `seed_cost_defaults`, buang `cost_items` yatim, hitung fixed/variable/margin/`procurement_price` |
| `seed_cost_defaults` | | salin komponen Variable produk sekali (`cost_seeded`); juga set `printed_by` default, `set_default_validity_date`, `validate_validity_range` |
| `validate_validity_range` | | `validity_date_to` tanpa `validity_date` ditolak; end < start ditolak; end == start dikosongkan |
| `get_validity_display` | | teks rentang untuk print |
| `set_default_validity_date` | | `date` + `CRM Settings.default_valid_till` |
| `after_insert` | | warisi assignee dari inquiry |
| `on_update` | | `sync_inquiry_status()` |
| `sync_inquiry_status` | | dorong status inquiry sesuai tabel di 3.3 |
| `default_list_data` | static | kolom list |

Fungsi modul: `_fmt_id_date`, `format_validity_range`, `_copy_assignees`,
`convert_to_estimation` (whitelisted). Konstanta: `INQUIRY_STATUS_BY_STATE`,
`INQUIRY_STATUS_IN_PROGRESS = "Proposal/Quotation"`, `INQUIRY_FINAL_STATUSES`.

### `CRM Estimation`

`autoname` (`EST/{counter}/CMI/{yy}`), `validate` (purpose wajib Customer/Agent kecuali
`flags.from_convert`), `before_save` (set `is_expense` per tabel, hitung `rev_inc_tax`
dan `est_profit`), `default_list_data`.

### `CRM Cost Component`

`before_validate` (`capture_rename`), `validate` (`block_edit_when_validated` +
`total_amount = compute_amount(items)`), `on_update` (`apply_rename` +
`refresh_linked_products`), `default_list_data`.
Modul: `behavior_of`, `resolve`, `resolve_for_product`, `refresh_linked_products`,
`set_validation` (whitelisted). Konstanta `FIXED`, `VARIABLE`, `VALIDATED`, `INVALIDATED`.

### `CRM Cost Item` (child)

`compute_amount(rows)` mengisi `amount = qty x rate` dan mengembalikan totalnya;
`copy_row(row, **overrides)` menyalin baris jadi dict siap append.

### `CRM Cost Type`

`before_validate` (`capture_rename`), `on_update` (`apply_rename`), `default_list_data`.

### `CRM Product`

`validate` -> `set_product_name` (isi `product_name` dari `product_code` bila kosong);
`default_list_data`, `parse_list_data` (static).

### `CRM Products` (child)

Controller kosong, tapi modulnya menyediakan `create_product_details_script(doctype)` dan
`get_product_details_script(doctype)`: **client script standar** yang dipasang otomatis
ke doctype pemilik grid produk (`CRM Form Script` bernama `Product Details Script for <doctype>`).
Isi scriptnya:

- `update_total()` di kelas induk menjumlahkan `amount` dan `net_amount` semua baris jadi
  `doc.total` dan `doc.net_total`;
- `products_add` / `products_remove` memicu `qty` dan `update_total`;
- `product_code(idx)` mengambil `standard_rate` dari `CRM Product` dan mengisinya ke
  `rate` bila masih kosong (nama produk sengaja **tidak** disalin ke Notes supaya print
  tidak menampilkan nama item dua kali);
- `qty(idx)` dan `rate()` menghitung `amount = qty * rate` lalu memicu diskon;
- `discount_percentage(idx)` menghitung `discount_amount` dan `net_amount`.

### `CRM Meeting`

`default_list_data`; fungsi modul `_set_geo`, `check_in`, `check_out` (whitelisted).
Waktu selalu diambil dari server, bukan jam klien.

### `CRM Task`

`after_insert` dan `validate` memanggil `assign_to()`; `unassign_from_previous_user()`
mencabut ToDo user lama saat `assigned_to` berubah; `default_list_data`,
`default_kanban_settings`.

### `CRM Call Log`

`before_insert`, `has_link`, `link_with_reference_doc`, `as_dict` (menambah
`_form_script` dan data terkait), `default_list_data`, `parse_list_data`.
Modul: `parse_call_log`, `get_call_log` (whitelisted),
`create_lead_from_call_log` (whitelisted).

### `CRM Notification`

`on_update` -> `frappe.publish_realtime("crm_notification", user=to_user)`.
`notify_user(notification)` (dict) membuat `CRM Notification` baru, melewati kalau
pengirim = penerima, dan menolak duplikat persis.

### `CRM Status Change Log` (child)

`get_duration(from_date, to_date)` dan `add_status_change_log(doc)`: menutup baris log
terakhir (isi `to`, `to_date`, `duration`) lalu membuka baris baru untuk status baru,
lengkap dengan `from_type`/`to_type` dan `log_owner`.

### `CRM Service Level Agreement`

Mesin SLA lengkap: `validate`, `validate_default`, `validate_condition`, `apply(doc)`,
`handle_creation`, `handle_communication_status`, `set_first_responded_on`,
`set_first_response_time`, `set_rolling_responses`, `handle_targets`, `set_response_by`,
`_update_rolling_response_by`, `set_rolling_response_by`, `handle_sla_status`,
`is_first_response_failed`, `handle_rolling_sla_status`, `is_rolling_response_failed`,
`_time_to_seconds`, `calc_time`, `calc_elapsed_time` (menghitung durasi kerja saja,
mengecualikan jam non-kerja dan hari libur), `get_priorities`, `get_default_priority`,
`get_workdays`, `get_working_days`, `get_working_hours`, `is_working_time`, `get_holidays`.
Helper `utils.py`: `get_sla(doc)` mencari SLA yang cocok (kondisi Python `safe_eval` atau
`condition_json`), `get_context(d)`.

### `CRM Holiday List`

`validate` -> `validate_values` + `validate_days`; `get_weekly_off_dates` (whitelisted
method dokumen) mengisi tabel dari `weekly_off`; `get_weekly_off_date_list`.

### `CRM View Settings`

Modul berisi seluruh manajemen view: `create`, `update`, `delete`, `public`, `pin`,
`set_as_default`, `create_or_update_standard_view`, `fetch_and_update_kanban_columns`
(semua whitelisted), plus `check_permission` (Administrator dan System Manager boleh
mengubah view siapa pun), `remove_duplicates`, `sync_default_rows`, `sync_default_columns`,
`get_route_name`.

### `CRM Fields Layout`

`get_fields_layout(doctype, type, parent_doctype)` (whitelisted) mengembalikan layout
tersimpan atau `get_default_layout(doctype)`; menandai field Date yang punya sibling
`<fieldname>_to` sebagai date-range (`tag_date_range_field`); menerapkan pembatasan
permlevel (`handle_perm_level_restrictions`, `get_permlevel_access`).
`get_sidepanel_sections(doctype)` dan `save_fields_layout(doctype, type, layout)`
juga whitelisted.

### `CRM Form Script`

`validate` memastikan script punya kelas yang benar; `get_form_script(dt, view='Form')`
mengembalikan script yang enabled untuk doctype itu.

### `FCRM Settings` (single)

`restore_defaults(force)` dan `restore_demo_data()` (whitelisted method dokumen),
`validate`, `do_not_allow_to_delete_if_standard`, `setup_forecasting`,
`make_currency_read_only`, `add_forecasting_section_in_sidepanel`,
`remove_forecasting_section_in_sidepanel`. Modul: `get_standard_dropdown_items`,
`after_migrate`, `sync_table`, `create_forecasting_script`, `get_forecasting_script`.

### `CRM Invitation`

`before_insert` (buat key), `after_insert` (`invite_via_email`), `accept_invitation`
(whitelisted method dokumen) -> `accept()` -> `create_user_if_not_exists()` +
`update_module_in_user()`. Modul `expire_invitations()` menghanguskan undangan setelah
3 hari (dipanggil scheduler Frappe).

### `ERPNext CRM Settings` (single)

`validate` -> `validate_if_erpnext_installed`, `add_quotation_to_option`,
`create_custom_fields` (lokal dan/atau remote site), `create_crm_form_script`.
Whitelisted: `reset_erpnext_form_script`, `get_external_companies`, `is_erpnext_installed`.
Modul: `get_erpnext_site_client`, `get_customer_link`, `get_quotation_url`,
`create_prospect_in_remote_site`, `get_primary_contact`, `get_contacts`,
`get_organization_address`, `create_customer_in_erpnext` (hook `on_update` CRM Inquiry),
`get_crm_form_script`.

### `CMI Branch Access` (single)

`on_update` membuang cache `cmi_branch_access` supaya perubahan level akses langsung
berlaku.

### Override doctype inti

- `overrides/contact.py` -> `CustomContact(Contact)`: menambah `default_list_data()`.
- `overrides/email_template.py` -> `CustomEmailTemplate(EmailTemplate)`: idem.

### Helper lintas doctype (`crm_cakra/utils/__init__.py`)

| Fungsi | Isi |
|---|---|
| `parse_phone_number`, `are_same_phone_number` | normalisasi nomor telepon (default region `IN`) |
| `seconds_to_duration` | format durasi |
| `is_admin`, `is_sales_user` | cek role |
| `sales_user_only(fn)` | decorator gerbang endpoint |
| `is_frappe_version` | pembanding versi |
| `create_lead_from_incoming_email` | email masuk tanpa referensi menjadi CRM Lead baru bila Email Account mengizinkan, lalu email itu ditaut ke lead |
| `on_comment_insert`, `on_communication_insert`, `on_communication_update` | perbarui `modified` dan `communication_status` Lead/Inquiry (di background), sesuai flag `update_timestamp_on_new_communication`, `auto_mark_replied_on_response`, `auto_reopen_on_new_communication` |
| `capture_rename(doc, fieldname)` / `apply_rename(doc)` | rename dokumen ber-`autoname: field:x` saat field kuncinya diubah lewat form |



---

## 7. Referensi endpoint whitelisted

Semua method ber-`@frappe.whitelist()`. Guard `sales_user_only` berarti hanya
pemegang role Sales User/Sales Manager yang boleh memanggil. Entri bertanda
`[method dokumen ...]` dipanggil lewat `run_doc_method`, bukan sebagai method biasa.


| Endpoint | Argumen | Guard | Keterangan |
|---|---|---|---|
| `crm_cakra.api.accept_invitation` | key=None | - |  |
| `crm_cakra.api.activities.get_lead_summary` | name | - | Everything hanging off a Lead, grouped per doctype, for the Summary tab. |
| `crm_cakra.api.activities.get_meeting_activities` | link_field, name, is_lead=False | - | CRM Meeting sebagai baris timeline tab Activity (activity_type='meeting'). |
| `crm_cakra.api.activities.get_organization_summary` | name | - | Everything hanging off an Organization/Account, grouped per doctype, for the Summary tab. |
| `crm_cakra.api.assignment_rule.duplicate_assignment_rule` | docname, new_name | - |  |
| `crm_cakra.api.assignment_rule.get_assignment_rules_list` | - | - |  |
| `crm_cakra.api.auth.oauth_providers` | - | - |  |
| `crm_cakra.api.comment.add_comment` | reference_doctype, reference_name, content, attachments=None | - | Add a comment to the given document  :param reference_doctype: Reference Doctype :param reference_name: Reference Document Name :param content: Comment Content (HTML) :param attachments: ... |
| `crm_cakra.api.contact.create_new` | contact, field, value | - | Create new email or phone for a contact |
| `crm_cakra.api.contact.get_linked_inquiries` | contact | - | Get linked inquiries for a contact |
| `crm_cakra.api.contact.search_emails` | txt | - |  |
| `crm_cakra.api.contact.set_as_primary` | contact, field, value | - | Set email or phone as primary for a contact |
| `crm_cakra.api.dashboard.get_allowed_scopes` | - | - | Scope yang boleh dipakai user ini, untuk switch di dashboard.  Sales User tidak diberi 'all' (lintas cabang), konsisten dengan pembatasan Lead/Inquiry/Quotation. Scope 'branch' disembunyi... |
| `crm_cakra.api.dashboard.get_chart` | name, type, from_date=None, to_date=None, user=None, scope=None, branch=None | sales_user_only | Get number chart data for the dashboard. |
| `crm_cakra.api.dashboard.get_dashboard` | from_date=None, to_date=None, user=None, scope=None, branch=None | sales_user_only | Get the dashboard data for the CRM dashboard. |
| `crm_cakra.api.dashboard.reset_to_default` | - | - |  |
| `crm_cakra.api.delete_attachment` | doctype, docname, file_url | - |  |
| `crm_cakra.api.doc.delete_bulk_docs` | doctype, items, delete_linked=False | - |  |
| `crm_cakra.api.doc.get_assigned_users` | doctype, name, default_assigned_to=None | - |  |
| `crm_cakra.api.doc.get_data` | doctype, filters, order_by, page_length=20, page_length_count=20, column_field=None, title_field=None, columns=None, rows=None, kanban_columns=None, kanban_fields=None, view=None, default_filters=None, search=None | - |  |
| `crm_cakra.api.doc.get_fields` | doctype, allow_all_fieldtypes=False | - |  |
| `crm_cakra.api.doc.get_filterable_fields` | doctype | - |  |
| `crm_cakra.api.doc.get_group_by_fields` | doctype | - |  |
| `crm_cakra.api.doc.get_linked_docs_of_document` | doctype, docname | - |  |
| `crm_cakra.api.doc.get_quick_filters` | doctype, cached=True | - |  |
| `crm_cakra.api.doc.global_search` | txt, limit=5 | - | Search every CRM doctype at once, grouped per doctype. |
| `crm_cakra.api.doc.remove_assignments` | doctype, name, assignees, ignore_permissions=False | - |  |
| `crm_cakra.api.doc.remove_linked_doc_reference` | items, remove_contact=False, delete=False | - |  |
| `crm_cakra.api.doc.sort_options` | doctype | - |  |
| `crm_cakra.api.doc.update_quick_filters` | quick_filters, old_filters, doctype | - |  |
| `crm_cakra.api.exchange_rate.get_exchange_rate` | from_currency, to_currency, date=None | - |  |
| `crm_cakra.api.get_file_uploader_defaults` | doctype | - |  |
| `crm_cakra.api.get_translations` | - | - |  |
| `crm_cakra.api.get_user_signature` | - | - |  |
| `crm_cakra.api.invite_by_email` | emails, role | - |  |
| `crm_cakra.api.live_demo.login` | - | - |  |
| `crm_cakra.api.notifications.get_notifications` | - | - |  |
| `crm_cakra.api.notifications.mark_as_read` | user=None, doc=None | - |  |
| `crm_cakra.api.onboarding.get_first_inquiry` | - | - |  |
| `crm_cakra.api.onboarding.get_first_lead` | - | - |  |
| `crm_cakra.api.permissions.get_my_branch` | - | - | Branch utama user login - untuk mengisi branch_office di form BARU (server tetap mengisinya lagi di before_insert; ini hanya supaya field read-only tak terlihat kosong). |
| `crm_cakra.api.procurement.add_comment` | quotation, content, reply_to=None | sales_user_only |  |
| `crm_cakra.api.procurement.delete_comment` | name | sales_user_only |  |
| `crm_cakra.api.procurement.get_comments` | quotation | sales_user_only | Thread komentar procurement untuk satu quotation, urut lama -> baru. |
| `crm_cakra.api.procurement.get_cost_defaults` | quotation, codes=None | sales_user_only | Komponen biaya default tiap produk yang dipakai quotation ini.  Fixed dipakai panel costing untuk ditampilkan read-only (angkanya milik master CRM Product). Variable dipakai panel untuk m... |
| `crm_cakra.api.procurement.get_discussions` | - | sales_user_only | Daftar quotation yang punya diskusi procurement, terbaru dulu (untuk menu Procurement). |
| `crm_cakra.api.quotation.get_available_inquiries` | search=None | - | Inquiry yang bisa dipilih untuk Quotation, milik user sendiri didahulukan.  Satu inquiry boleh dipakai banyak quotation, jadi yang sudah pernah dipakai TIDAK disembunyikan dari picker.  P... |
| `crm_cakra.api.quotation.get_inquiry_detail` | name | - | Detail CRM Inquiry untuk sidebar Quotation (read-only, dibaca langsung dari Inquiry sehingga selalu sinkron -- tidak disalin ke Quotation).  Dikembalikan sebagai daftar {label, value} aga... |
| `crm_cakra.api.quotation.get_quotation_contacts` | name | - | Get contacts linked to quotation's account (organization) |
| `crm_cakra.api.quotation.mark_quotation_lost` | quotation, lost_reason=None, lost_notes=None | - | Tandai quotation sebagai Lose, sekalian isi Lost Reason di inquiry-nya.  Digabung dalam satu panggilan supaya tidak ada keadaan setengah jadi: kalau alasan tersimpan tapi status gagal ber... |
| `crm_cakra.api.session.get_organizations` | - | - |  |
| `crm_cakra.api.session.get_users` | - | - |  |
| `crm_cakra.api.settings.create_email_account` | data | - |  |
| `crm_cakra.api.user.add_existing_users` | users, role='Sales User' | - | Add existing users to the CRM by assigning them a role (Sales User or Sales Manager). :param users: List of user names to be added |
| `crm_cakra.api.user.change_password` | old_password, new_password | rate_limit(limit=5, seconds=300) | Change password for the current logged-in user. Uses Frappe's LoginAttemptTracker for attempt counting/lockout, and rate_limit for API abuse protection. |
| `crm_cakra.api.user.remove_crm_roles_from_user` | user | - | Remove a user means removing Sales User & Sales Manager roles from the user. :param user: The name of the user to be removed |
| `crm_cakra.api.user.update_user_role` | user, new_role | - | Update the role of the user to Sales Manager, Sales User, or System Manager. :param user: The name of the user :param new_role: The new role to assign (Sales Manager or Sales User) |
| `crm_cakra.api.views.get_views` | doctype | - |  |
| `crm_cakra.api.views.reset_standard_views` | doctype=None, all_users=False | - | Drop the saved list/kanban state so every list falls back to its default columns.  Only touches is_standard views (the auto-saved per-user state) - custom saved views keep their columns a... |
| `crm_cakra.api.void.void_document` | doctype, name, void=1, reason=None | - | Tandai dokumen sebagai void (soft-cancel) atau batalkan void. Reversible. |
| `crm_cakra.api.whatsapp.create_whatsapp_message` | reference_doctype, reference_name, message, to, attach, reply_to, content_type='text' | - |  |
| `crm_cakra.api.whatsapp.get_whatsapp_messages` | reference_doctype, reference_name | - |  |
| `crm_cakra.api.whatsapp.is_whatsapp_enabled` | - | - |  |
| `crm_cakra.api.whatsapp.is_whatsapp_installed` | - | - |  |
| `crm_cakra.api.whatsapp.react_on_whatsapp_message` | emoji, reply_to_name | - |  |
| `crm_cakra.api.whatsapp.send_whatsapp_template` | reference_doctype, reference_name, template, to | - |  |
| `crm_cakra.demo.api.clear_demo_data` | - | - |  |
| `crm_cakra.demo.api.get_demo_state` | - | - |  |
| `crm_cakra.fcrm.doctype.crm_call_log.crm_call_log.create_lead_from_call_log` | call_log, lead_details=None | - |  |
| `crm_cakra.fcrm.doctype.crm_call_log.crm_call_log.get_call_log` | name | - |  |
| `crm_cakra.fcrm.doctype.crm_cost_component.crm_cost_component.set_validation` | name, action | - | Tombol Validate / Invalidate di halaman komponen. |
| `crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout` | doctype, type, parent_doctype=None | - |  |
| `crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections` | doctype | - |  |
| `crm_cakra.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout` | doctype, type, layout | - |  |
| `crm_cakra.fcrm.doctype.crm_holiday_list.crm_holiday_list.get_weekly_off_dates` | - | - | [method dokumen `CRMHolidayList`]  |
| `crm_cakra.fcrm.doctype.crm_inquiry.api.get_inquiry_contacts` | name | - |  |
| `crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry.add_contact` | inquiry, contact | - |  |
| `crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry.create_inquiry` | doc | - |  |
| `crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry.remove_contact` | inquiry, contact | - |  |
| `crm_cakra.fcrm.doctype.crm_inquiry.crm_inquiry.set_primary_contact` | inquiry, contact | - |  |
| `crm_cakra.fcrm.doctype.crm_invitation.crm_invitation.accept_invitation` | - | - | [method dokumen `CRMInvitation`]  |
| `crm_cakra.fcrm.doctype.crm_lead.crm_lead.convert_to_inquiry` | lead, doc=None, inquiry=None, existing_contact=None, existing_organization=None | - |  |
| `crm_cakra.fcrm.doctype.crm_lead.crm_lead.find_similar_accounts` | organization, limit=5 | - | Existing Accounts and Leads whose account name is the same or nearly the same. |
| `crm_cakra.fcrm.doctype.crm_meeting.crm_meeting.check_in` | meeting, latitude=None, longitude=None, address=None | - |  |
| `crm_cakra.fcrm.doctype.crm_meeting.crm_meeting.check_out` | meeting, latitude=None, longitude=None | - |  |
| `crm_cakra.fcrm.doctype.crm_quotation.crm_quotation.convert_to_estimation` | quotation | - | Konversi Quotation -> Estimation.  - Salin tiap produk quotation (type/item, qty, uom, amount, remark) ke tabel Revenue estimasi. - Rute (Loading, Unloading, KM) ikut disalin. - Kolom est... |
| `crm_cakra.fcrm.doctype.crm_twilio_settings.crm_twilio_settings.fetch_applications` | - | - | [method dokumen `CRMTwilioSettings`]  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.create` | view | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view` | view | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | name | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns` | name | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | name, value | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.public` | name, value | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default` | name=None, type=None, doctype=None | - |  |
| `crm_cakra.fcrm.doctype.crm_view_settings.crm_view_settings.update` | view | - |  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_crm_form_script` | - | - |  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_customer_link` | crm_inquiry | - |  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_external_companies` | - | - | [method dokumen `ERPNextCRMSettings`]  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_quotation_url` | crm_inquiry, organization=None | - |  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed` | - | - | [method dokumen `ERPNextCRMSettings`]  |
| `crm_cakra.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.reset_erpnext_form_script` | - | - | [method dokumen `ERPNextCRMSettings`]  |
| `crm_cakra.fcrm.doctype.fcrm_settings.fcrm_settings.restore_defaults` | force=False | - | [method dokumen `FCRMSettings`]  |
| `crm_cakra.fcrm.doctype.fcrm_settings.fcrm_settings.restore_demo_data` | - | - | [method dokumen `FCRMSettings`]  |
| `crm_cakra.integrations.api.add_note_to_call_log` | call_sid, note | - | Add/Update note to call log based on call sid. |
| `crm_cakra.integrations.api.add_task_to_call_log` | call_sid, task | - | Add/Update task to call log based on call sid. |
| `crm_cakra.integrations.api.get_contact_by_phone_number` | phone_number | - | Get contact by phone number. |
| `crm_cakra.integrations.api.get_contact_lead_or_inquiry_from_number` | number | - | Get contact, lead or inquiry from the given number. |
| `crm_cakra.integrations.api.get_recording_url` | call_log_name | - | Fetch and stream a call recording, authenticating with the provider's credentials. |
| `crm_cakra.integrations.api.is_call_integration_enabled` | - | - |  |
| `crm_cakra.integrations.api.set_default_calling_medium` | medium | - |  |
| `crm_cakra.integrations.exotel.handler.handle_request` | - | - |  |
| `crm_cakra.integrations.exotel.handler.is_integration_enabled` | - | - |  |
| `crm_cakra.integrations.exotel.handler.make_a_call` | to_number, from_number=None, caller_id=None | - |  |
| `crm_cakra.integrations.twilio.api.generate_access_token` | - | - | Returns access token that is required to authenticate Twilio Client SDK. |
| `crm_cakra.integrations.twilio.api.is_enabled` | - | - |  |
| `crm_cakra.integrations.twilio.api.twilio_incoming_call_handler` | - | - |  |
| `crm_cakra.integrations.twilio.api.update_call_status_info` | - | - |  |
| `crm_cakra.integrations.twilio.api.update_recording_info` | - | - |  |
| `crm_cakra.integrations.twilio.api.voice` | - | - | This is a webhook called by twilio to get instructions when the voice call request comes to twilio server. |
| `crm_cakra.lead_syncing.doctype.failed_lead_sync_log.failed_lead_sync_log.retry_sync` | - | - | [method dokumen `FailedLeadSyncLog`]  |
| `crm_cakra.lead_syncing.doctype.lead_sync_source.facebook.fetch_and_store_pages_from_facebook` | access_token | - |  |
| `crm_cakra.lead_syncing.doctype.lead_sync_source.facebook.get_pages_with_forms` | - | - |  |
| `crm_cakra.lead_syncing.doctype.lead_sync_source.lead_sync_source.sync_leads` | - | - | [method dokumen `LeadSyncSource`]  |
| `crm_cakra.www.crm.get_context_for_dev` | - | - |  |



---

## 8. Mesin konfigurasi UI

Karena UI-nya SPA, tampilan tidak diambil dari meta doctype. Ada lima mesin konfigurasi.

### 8.1 `CRM Fields Layout` — layout form

- Nama dokumen: `{dt}-{type}`, contoh `CRM Quotation-Data Fields`.
- `type`: `Quick Entry` | `Side Panel` | `Data Fields` | `Grid Row` | `Required Fields`.
- `layout` = JSON. Bentuknya array of tab, tiap tab punya `sections`, tiap section punya
  `columns`, tiap column punya `fields` (daftar fieldname).
- Endpoint: `get_fields_layout(doctype, type, parent_doctype)`,
  `get_sidepanel_sections(doctype)`, `save_fields_layout(doctype, type, layout)`.
- Server menambahkan info per field: tanda date-range (field Date yang punya sibling
  `<fieldname>_to`) dan pembatasan permlevel.
- **Penting**: `bench migrate` menyeed ulang layout default Frappe dan bisa menimpa
  layout custom. Karena itu layout Inquiry / Quotation / Lead / Estimation diekspor
  sebagai **fixture** (`crm_cakra/fixtures/crm_fields_layout.json`).

Layout yang dipakai produksi (ringkas, urutan section dan kolomnya):

| Layout | Isi |
|---|---|
| `CRM Inquiry-Quick Entry` | Basic (organization, subject / inquiry_date / inquiry_owner); Shipment (date_shipment, type_inquiry, transportation_mode, incoterms / shipper_consignee, origin, destination); Service (job_service, business_unit / service_type); Cargo (cargo_packaging, cargo_weight, cargo_commodity, qty_volume) |
| `CRM Inquiry-Data Fields` | Details (subject, inquiry_date, organization / probability, annual_revenue / communication_status, closed_date, status); Shipment; Service; Cargo (cargo_commodity, qty_volume, status_cargo / cargo_weight, cargo_packaging); Penentuan Harga Jual (estimasi_tarif, costing_procurement / reimburse_cost) |
| `CRM Inquiry-Side Panel` | Contacts; Organization Details (organization, probability) |
| `CRM Lead-Quick Entry` | person_section; organization_section; lead_section |
| `CRM Lead-Data Fields` | Details (organization, industry, lead_owner / website, job_title / territory, source); Person |
| `CRM Lead-Side Panel` | Details; Person; Company / Legal (nib, npwp, type_industry, target_goals); Address (address, village, sub_district, regency, city, postal_code) |
| `CRM Quotation-Data Fields` | tab Main: Inquiry (inquiry / account); Quote Information (subject, attention, cargo, packaging, loading, unloading / date, cost_center, currency, rate, distance_km, get_km, check_gmap); Product (products, net_total); Additionals + Additionals 2; Terms & Conditions (tac, tac_detail / validity, validity_date, payterm); Remark; Print |
| `CRM Quotation-Side Panel` | Print Out (printed_by, branch_office, print_full_page); Inquiry (inquiry_details); Organization (account, contact_name) |
| `CRM Estimation-Data Fields` | tab Main, Route (route1..8, loading, unloading, est_km / route_map), Details (Income/Expense) (revenue_items / expense_items), Approval & Profit, Account Manager |
| `CRM Estimation-Side Panel` | Estimation; Profit |

### 8.2 `CRM View Settings` — list, kanban, group by

Menyimpan per user (atau public) untuk tiap doctype: `columns`, `rows`, `filters`,
`order_by`, `type` (`list`/`group_by`/`kanban`), `group_by_field`, `column_field`,
`kanban_columns`, `kanban_fields`, `title_field`, `label`, `route_name`, `icon`,
`pinned`, `public`, `is_standard`, `is_default`, `load_default_columns`.

Aturan resolusi kolom di `api.doc.get_data`:

1. kalau caller mengirim `columns`/`rows` -> itu yang dipakai (custom view);
2. kalau ada `CRM View Settings` standar milik user untuk doctype+tipe itu **dan**
   `load_default_columns` = 0 -> pakai snapshot tersimpan;
3. kalau tidak, pakai `default_list_data()` di controller;
4. kalau doctype dari luar CRM (tidak punya `default_list_data`), susun dari field
   yang ber-`in_list_view`, ditambah kolom `name` di depan dan `modified` di belakang.

`api.views.reset_standard_views(doctype, all_users)` membuang snapshot itu supaya list
kembali ke default. Nilai filter `@me` dan `%@me%` diterjemahkan ke user login.

### 8.3 `CRM Form Script` — client script

Dua sumber, keduanya digabung oleh `frontend/src/data/script.js`:

- **DB**: record `CRM Form Script` (dt, view Form/List, script berupa kelas JS, enabled).
- **File**: `frontend/src/doctypes/<doctype_slug>/<view>.js` (mis.
  `crm_quotation/form.js`), di-glob oleh Vite. Nama kelas harus sama dengan doctype
  tanpa spasi (`CRMQuotation`); kelas tambahan dianggap controller child table.

Helper yang tersedia di dalam kelas script: `this.doc` (proxy reaktif), `this.call`,
`this.createDialog`, `this.toast`, `this.socket`, `this.router`, `this.formDialog`,
`this.throwError`, `this.getRow(parentField, idx)`, `this.getField(fieldname)`,
`this.setFieldProperty(target, property, value, rowName)`, `setFieldProperties`,
`removeFieldProperty`, `setFieldHtml`, `this.actions`, `this.statuses`.
Hook siklus hidup: `onLoad()`, `onRender()`, dan **method bernama sama dengan fieldname**
yang dipanggil saat field itu berubah (mis. `async inquiry()`).

Script standar yang dipasang otomatis saat install: `Product Details Script for CRM Lead`,
`Product Details Script for CRM Inquiry`, dan script forecasting.

### 8.4 `CRM Global Settings` — quick filter dan sidebar

Satu record per doctype, `type` = `Quick Filters` | `Sidebar Items`, isi `json`.
Default quick filter yang diseed saat install:

| Doctype | Quick filters |
|---|---|
| `CRM Lead` | lead_name, email, organization, status, source |
| `CRM Inquiry` | organization, status, probability, email |
| `CRM Quotation` | name, state, is_void (memakai `name`, bukan `number`, karena `number` tidak bisa dicari) |
| `Contact` | status, email_id, phone |
| `CRM Organization` | organization_name, no_of_employees, territory, industry |
| `CRM Task` | title, priority, assigned_to, status, due_date |
| `CRM Call Log` | telephony_medium, type, status, from, to |

Endpoint: `get_quick_filters(doctype, cached)`, `update_quick_filters(...)`
(juga mengubah `in_standard_filter` lewat Property Setter).

### 8.5 Pencarian

- Per list: parameter `search` pada `get_data` diubah jadi `or_filters` oleh
  `search_or_filters(doctype, txt)` — mencari di `name`, search fields, title field,
  dan semua field bertipe Data/Link/Select/Small Text/Text yang ber-`in_list_view` atau
  `in_standard_filter`; ditambah `owner` dan `_assign` (termasuk mencocokkan nama
  lengkap user, maksimal 10 user).
- Global (palette): `api.doc.global_search(txt, limit)` menyapu doctype di `SEARCH_ROUTES`
  = CRM Lead, CRM Inquiry, CRM Quotation, CRM Estimation, CRM Organization, Contact —
  hasilnya dikelompokkan per doctype lengkap dengan nama route dan nama parameter
  frontend, sehingga UI tinggal `router.push`.

---

## 9. Permission berbasis branch

Implementasi ada di `crm_cakra/api/permissions.py` dan dipasang lewat **hook wildcard**:

```python
permission_query_conditions = {"*": "crm_cakra.api.permissions.branch_query_conditions"}
has_permission            = {"*": "crm_cakra.api.permissions.branch_has_permission"}
doc_events = {"*": {"before_insert": "crm_cakra.api.permissions.set_branch_from_user"}}
```

Artinya: **setiap doctype yang punya field `branch_office` (Link `CMI Office`) otomatis
ter-scope**, tanpa mengubah kode. Menambah modul baru ke aturan ini = cukup menambahkan
field `branch_office`.

Konfigurasi di single `CMI Branch Access`:

| Field | Arti |
|---|---|
| `default_access` | level untuk role yang tidak terdaftar |
| `blank_branch` | dokumen tanpa branch: `Terlihat semua` atau `Tersembunyi` |
| `role_access` | tabel role -> level (`CMI Branch Access Role`) |

Level (konstanta): `See All` = 3, `Branch + Owner` = 2, `Owner Only` = 1.
User dengan banyak role memakai level **paling longgar**. `Administrator` dan
`System Manager` selalu See All. Config di-cache di key `cmi_branch_access`, dibuang
saat `CMI Branch Access.on_update`.

Branch user:

- `User.branch` (Custom Field, Link `CMI Office`) = branch **utama**, dipakai untuk
  menstempel dokumen baru;
- `User.custom_branches` (Table MultiSelect ke `CMI User Branch`) = branch tambahan yang
  boleh **dilihat**.

Kondisi query yang dibangun `_visible()` untuk level < See All:

```sql
(  `tabX`.owner = <user>
OR `tabX`._assign LIKE '%"<user>"%'
[OR `tabX`.branch_office IN (<branch utama + tambahan>)]        -- level >= Branch + Owner
[OR (`tabX`.branch_office IS NULL OR `tabX`.branch_office = '')] -- kalau blank_branch = Terlihat semua
)
```

`branch_has_permission` melakukan cek yang setara per dokumen, dan **wajib
mengembalikan True** untuk doctype tanpa `branch_office` (kalau falsy, Frappe menolak).

Turunan branch dari job (dipakai modul ERP, wire di `before_validate` doctype terkait):
`set_branch_from_job` mengambil branch dari `Shipment Type`, `Packing List Type`,
atau dari Shipping/Packing List yang ditaut Expense Note / Sales Invoice.
`backfill_job_branch()` mengisi ulang dokumen lama lewat UPDATE JOIN.

Endpoint bantu: `get_my_branch()` (untuk mengisi field read-only di form baru; server
tetap mengisinya lagi di `before_insert`).

Gerbang lain: decorator `@sales_user_only` (`crm_cakra/utils`) dan role
`Procurement Costing` untuk rincian costing.

---

## 10. Dashboard

- Layout disimpan di `CRM Dashboard` (record `Manager Dashboard`, field `layout` JSON).
- Tiap item: `{"name": "<key>", "type": "number_chart|axis_chart|donut_chart|outstanding_table", "layout": {x, y, w, h, i}}`.
- **Konvensi**: `get_dashboard()` memanggil fungsi `get_<name>` di
  `crm_cakra.api.dashboard` untuk tiap item. Menambah widget = menambah fungsi dengan
  tanda tangan `(from_date, to_date, users)` lalu memasukkan namanya ke layout.
- Tanpa range tanggal, defaultnya bulan berjalan (awal sampai akhir bulan).
- Tanggal bisnis: Inquiry memakai `COALESCE(inquiry_date, DATE(creation))`, Quotation
  memakai `COALESCE(date, DATE(creation))` — bukan `creation` mentah.
- Bucket trend adaptif: range <= 10 hari harian, <= 45 hari mingguan (label = awal
  minggu), selebihnya bulanan.

**Scope** (`get_allowed_scopes`, `_scope_users`): `mine` (default), `branch`, `all`.
`all` hanya untuk manager (`Sales Manager`, `Sales Master Manager`, `System Manager`).
`branch` tanpa `User.branch` diperlakukan sebagai `mine` (tidak diam-diam melebar).
Manager boleh memilih user mana pun; non-manager yang memilih user di luar haknya
dikembalikan ke dirinya sendiri.

Layout default produksi (15 widget, semuanya berbasis quotation kecuali dua):

`my_outstanding_quotations`, `my_outstanding_inquiries` (outstanding_table);
`open_quotations`, `quotation_value_won`, `quotation_win_rate`, `ongoing_inquiries`,
`expiring_quotations` (number_chart);
`funnel_conversion`, `quotations_by_status`, `quotation_trend_by_branch`, `top_accounts`,
`top_routes`, `top_cargo`, `quotation_value_trend`, `quotations_by_salesperson`
(axis_chart).

Fungsi chart yang tersedia (bisa ditambahkan lewat Add Chart):

| Kategori | Fungsi |
|---|---|
| Lead | `get_total_leads`, `get_leads_by_source`, `get_average_time_to_close_a_lead` |
| Inquiry angka | `get_ongoing_inquiries`, `get_average_ongoing_inquiry_value`, `get_won_inquiries`, `get_average_won_inquiry_value`, `get_average_inquiry_value`, `get_average_time_to_close_a_inquiry` |
| Inquiry sebaran | `get_inquiries_by_stage_axis`, `get_inquiries_by_stage_donut`, `get_lost_inquiry_reasons`, `get_inquiries_by_source`, `get_inquiries_by_territory`, `get_inquiries_by_salesperson`, `get_inquiries_by_job_service`, `get_inquiries_by_business_unit`, `get_inquiries_by_transportation_mode` |
| Inquiry tren | `get_inquiry_trend_by_branch`, `get_inquiry_trend_by_business_unit`, `get_inquiry_trend_by_transportation_mode`, `get_inquiry_trend_by_job_service` |
| Inquiry top-N | `get_top_business_unit`, `get_top_type_of_inquiry` |
| Quotation | `get_quotations_by_status`, `get_quotation_win_rate`, `get_quotation_value_won`, `get_open_quotations`, `get_expiring_quotations`, `get_quotation_trend_by_branch`, `get_quotation_value_trend`, `get_quotations_by_salesperson`, `get_top_accounts`, `get_top_routes`, `get_top_cargo`, `get_win_rate_by_business_unit` |
| Gabungan | `get_funnel_conversion` (cohort inquiry: Inquiries -> Quoted -> Sent -> Win), `get_sales_trend`, `get_forecasted_revenue` |
| Tabel | `get_my_outstanding_quotations`, `get_my_outstanding_inquiries` |

Endpoint: `get_dashboard(...)`, `get_chart(name, type, ...)`, `get_allowed_scopes()`,
`reset_to_default()`. Semua kecuali `reset_to_default` dan `get_allowed_scopes`
digerbangi `@sales_user_only`.

---

## 11. Notifikasi, aktivitas, dan SLA

### Notifikasi

`CRM Notification` (from_user, to_user, type Mention/Task/Assignment/WhatsApp, message,
notification_text, `notification_type_doctype`/`_doc` = sumber, `reference_doctype`/
`reference_name` = tujuan redirect, `read`). `on_update` memancarkan realtime event
`crm_notification` ke user tujuan. `notify_user(dict)` melewati kalau pengirim = penerima
dan menolak record duplikat persis.

Sumber notifikasi: mention di Comment (`api/comment.py` -> `extract_mentions`),
assignment ToDo (`api/todo.py`), pesan WhatsApp (`api/whatsapp.py` -> `notify_agent`),
komentar procurement (`api/procurement.py` -> `_notify`).
Endpoint: `get_notifications()`, `mark_as_read(user, doc)`.

### Timeline aktivitas

`api/activities.py` menyusun tab Activity/Email/Comment/Call/Task/Note/Attachment/WhatsApp
per dokumen:

- `get_activities(name)`, dan varian per doctype: `get_lead_activities`,
  `get_inquiry_activities`, `get_quotation_activities`, `get_estimation_activities`;
- `get_meeting_activities(link_field, name, is_lead)` menyisipkan CRM Meeting sebagai
  baris timeline `activity_type='meeting'`;
- riwayat perubahan diambil dari `Version` dan diproses `handle_multiple_versions` /
  `parse_grouped_versions`; perubahan baris child table dirender oleh
  `get_child_activities` + `child_table_labels`;
- `get_linked_calls`, `get_linked_notes`, `get_linked_tasks`, `get_attachments`,
  `parse_attachment_log`;
- `get_lead_summary(name)` dan `get_organization_summary(name)` mengembalikan semua
  dokumen yang menggantung di record itu, dikelompokkan per doctype (tab Summary).

### SLA

`CRM Service Level Agreement` (apply_on doctype, condition Python atau `condition_json`,
`priorities` -> `CRM Service Level Priority` dengan `first_response_time` per
Communication Status, `working_hours` -> `CRM Service Day`, `holiday_list`,
`rolling_responses`, `start_date`/`end_date`, `enabled`, `default`).

Yang ditulis SLA ke Lead/Inquiry: `sla`, `sla_creation`, `sla_status`
(First Response Due / Rolling Response Due / Failed / Fulfilled), `response_by`,
`first_responded_on`, `first_response_time`, `last_responded_on`, `last_response_time`,
dan tabel `rolling_responses` (`CRM Rolling Response Time`).
Perhitungan durasi mengecualikan jam non-kerja dan hari libur.

---

## 12. Integrasi eksternal

### Telephony

| Provider | Settings | Alur |
|---|---|---|
| Twilio | `CRM Twilio Settings` (single) | `generate_access_token` untuk Twilio Voice SDK di browser; webhook `voice`, `twilio_incoming_call_handler`, `update_recording_info`, `update_call_status_info`. Kelas `Twilio` mengurus API key, TwiML App, dial response ke telepon atau ke browser. `IncomingCall.process()` mencari pemilik nomor, memfilter user yang sedang login, memilih penerima |
| Exotel | `CRM Exotel Settings` (single) | `handle_request` (webhook), `make_a_call`, `is_integration_enabled`, `create_call_log`, `update_call_log` |

Bersama: `CRM Telephony Agent` (per user: nomor, medium default, device Computer/Phone,
tabel `CRM Telephony Phone`). `integrations/api.py`: `is_call_integration_enabled`,
`set_default_calling_medium`, `add_note_to_call_log`, `add_task_to_call_log`,
`get_contact_lead_or_inquiry_from_number`, `get_contact_by_phone_number`,
`get_recording_url` (mem-proxy rekaman dengan kredensial provider).

### WhatsApp

Butuh app `frappe_whatsapp`. `api/whatsapp.py`: `is_whatsapp_enabled`,
`is_whatsapp_installed`, `get_whatsapp_messages`, `create_whatsapp_message`,
`send_whatsapp_template`, `react_on_whatsapp_message`; hook `validate`/`on_update` pada
`WhatsApp Message` untuk validasi akses dan notifikasi agent; `add_roles()` dijalankan
di `after_migrate`.

### ERPNext

`ERPNext CRM Settings` (single): `enabled`, `is_erpnext_in_different_site` (+ site URL,
api_key/secret), `erpnext_company`, `create_customer_on_status_change` + `deal_status`.
Saat status Inquiry mencapai status itu, `create_customer_in_erpnext` membuat
Customer/Prospect (lokal atau lewat FrappeClient ke site lain).
`get_customer_link(crm_inquiry)` dan `get_quotation_url(crm_inquiry, organization)`
dipakai tombol di form.

### Facebook Lead Ads (module Lead Syncing)

`Lead Sync Source` (aktif/nonaktif, frekuensi), `Facebook Page`, `Facebook Lead Form`
(+ `Facebook Lead Form Question` sebagai pemetaan pertanyaan ke field CRM Lead),
`Failed Lead Sync Log` (dengan tombol `retry_sync`).
`FacebookSyncSource` menarik lead lewat Graph API, memetakan field, menolak duplikat
(`facebook_lead_id` unique), dan mencatat kegagalan.
Scheduler: `daily_long`, `hourly_long`, `monthly_long`, plus cron `*/5`, `*/10`, `*/15`.

### Kurs

`api/exchange_rate.py` -> `get_exchange_rate(from, to, date)` dengan provider yang dipilih
di `FCRM Settings.service_provider`: `frankfurter.app` (default),
`fawazahmed-exchange-api`, `exchangerate.host` (butuh `access_key`), `exchangerate-api`.

### Undangan user

`CRM Invitation` (email, role, key, status Pending/Accepted/Expired). `invite_by_email`
mengirim undangan; `accept_invitation(key)` membuat user bila belum ada dan memasang
role; undangan hangus setelah 3 hari.

---

## 13. Frontend

Lokasi: `frontend/`, alias `@` -> `frontend/src`, router history base `/crm`.

### 13.1 Route

| Path | Nama | Halaman |
|---|---|---|
| `/` | Home | redirect ke `Dashboard` |
| `/dashboard` | Dashboard | `Dashboard.vue` |
| `/assistant` | Assistant | `Assistant.vue` |
| `/manual` | ManualBook | `ManualBook.vue` |
| `/notifications` | Notifications | `MobileNotification.vue` |
| `/leads` , `/leads/view/:viewType?` | Leads | `Leads.vue` |
| `/leads/:leadId` | Lead | `Lead.vue` / `MobileLead.vue` |
| `/inquiries` , `/inquiries/view/:viewType?` | Inquiries | `Inquiries.vue` |
| `/inquiries/new` | NewInquiry | `InquiryNew.vue` |
| `/inquiries/:inquiryId` | Inquiry | `Inquiry.vue` / `MobileInquiry.vue` |
| `/quotations` , `/quotations/view/:viewType?` | Quotations | `Quotations.vue` |
| `/quotations/new` | NewQuotation | `QuotationNew.vue` |
| `/quotations/:quotationId` | Quotation | `Quotation.vue` / `MobileQuotation.vue` |
| `/procurement` | Procurement | `Procurement.vue` |
| `/estimations` , `/estimations/view/:viewType?` | Estimations | `Estimations.vue` |
| `/estimations/new` | NewEstimation | `EstimationNew.vue` |
| `/estimations/:estimationId` | Estimation | `Estimation.vue` / `MobileEstimation.vue` |
| `/meetings` , `/meetings/view/:viewType?` | Meetings | `Meetings.vue` |
| `/meetings/calendar` | MeetingsCalendar | `Meetings.vue` (mode kalender) |
| `/meetings/attendance` | MeetingAttendance | `MeetingAttendance.vue` |
| `/products` , `/locations` , `/cost-components` , `/cost-types` | master | `Products.vue`, `Locations.vue`, `CostComponents.vue`, `CostTypes.vue` |
| `/cost-components/new` , `/cost-components/:componentId` | | `CostComponentNew.vue`, `CostComponent.vue` |
| `/notes` , `/tasks` , `/contacts` , `/organizations` , `/call-logs` | list | `Notes.vue`, `Tasks.vue`, `Contacts.vue`, `Organizations.vue`, `CallLogs.vue` |
| `/contacts/:contactId` , `/organizations/:organizationId` | detail | `Contact.vue`, `Organization.vue` (+ varian Mobile) |
| `/data-import` , `/data-import/doctype/:doctype` , `/data-import/:importName` | | `DataImport.vue` |
| `/welcome` , `/not-permitted` , `/:invalidpath` | | `Welcome.vue`, `NotPermitted.vue`, `InvalidPage.vue` |

Detail penting router:

- Nama dokumen mengandung `/` (mis. `LD/4337/CMI/26`), jadi route detail memakai param
  satu segmen agar garis miringnya ter-encode `%2F`. `legacySlashRedirect` menangkap
  link lama yang masih polos dan mengalihkannya ke bentuk ter-encode.
- `handleMobileView()` memilih komponen `Mobile*` bila `window.innerWidth < 768`.
- Guard `beforeEach`: user bukan CRM user diarahkan ke `Not Permitted`; belum login
  diarahkan ke `/login?redirect-to=/crm`; route `Inquiry`/`Lead` tanpa hash dipaksa
  `#data`; halaman list tanpa `?view` menyelesaikan default view (dari `viewsStore`,
  standard view yang `is_default`, atau `list`).

### 13.2 Sidebar

```
Assistant (kalau FCRM Settings.enable_crm_assistant)
Dashboard
--- alur kerja ---
Leads -> Inquiries -> Quotations -> Procurement -> Estimations
--- master ---
Accounts, Contacts, Cost Types, Cost Components, Products, Locations
--- tambahan ---
Notes, Tasks, Meetings, Calendar, Call Logs
--- views tersimpan (pinned/public) ---
```

Sidebar juga memuat command palette (Ctrl+K) dan aksi cepat: buat Lead, undang user,
convert lead, buat Task/Note/Comment/Email.

### 13.3 Struktur `src/`

| Folder | Isi |
|---|---|
| `pages/` | 40 halaman (lihat tabel route) |
| `components/Layouts/` | `AppHeader`, `AppSidebar`, `DesktopLayout`, `MobileLayout`, `SettingsLayoutBase` |
| `components/FieldLayout/` | `FieldLayout`, `Section`, `Column`, `Field` — renderer layout dari `CRM Fields Layout` |
| `components/Controls/` | kontrol form: `Link`, `LinkField`, `Grid`, `GridRowModal`, `GridFieldsEditorModal`, `GridRowFieldsModal`, `TableMultiselectInput`, `MultiSelectEmailInput`, `MultiSelectUserInput`, `TextEditorControl`, `HtmlControl`, `AttachControl`, `ButtonControl`, `DurationInput`, `FormattedInput`, `GeolocationControl`, `ImageUploader`, `Password`, `RatingInput` |
| `components/ListViews/` | satu komponen per list: Leads, Inquiries, Quotations, Estimations, Meetings, Contacts, Organizations, Products, Tasks, CallLogs, LinkedDocs, plus `ListRows`, `EmptyState` |
| `components/Activities/` | timeline: `Activities`, `ActivityHeader`, `EmailArea`, `CommentArea`, `CallArea`, `TaskArea`, `NoteArea`, `MeetingArea`, `AttachmentArea`, `WhatsAppArea`, `WhatsAppBox`, `SummaryArea`, `DataFields`, `AudioPlayer`, `EmailContent`, `AllModals`, `PlaybackSpeedOption` |
| `components/Modals/` | 29 modal, antara lain `ConvertToInquiryModal`, `LostReasonModal`, `QuotationModal`, `QuotationTerms`, `InquiryModal`, `LeadModal`, `MeetingModal`, `OrganizationModal`, `ContactModal`, `FleetLocationModal`, `QuickEntryModal`, `SidePanelModal`, `FieldLayoutDialog`, `ViewModal`, `GlobalSearchModal`, `AssignmentModal`, `CreateDocumentModal`, `EditValueModal`, `DataFieldsModal`, `EmailTemplateSelectorModal`, `WhatsappTemplateSelectorModal`, `CallLogDetailModal`, `ChangePasswordModal`, `AddExistingUserModal`, `AboutModal` |
| `components/Quotation/` | `ProductsSection`, `QuotationProducts`, `QuotationCargo`, `QuotationAdditional`, `QuotationTerms`, `QuotationPrintContent`, `QuotationDetails`, `QuotationForm` (dua terakhir sudah tidak dipakai karena form dirender dari layout) |
| `components/Procurement/` | `ProcurementTab`, `CostingPanel` |
| `components/Dashboard/` | `DashboardGrid`, `DashboardItem`, `AddChartModal`, `OutstandingTable` |
| `components/Settings/` | 27 entri: `GeneralSettings`, `BrandSettings`, `DefaultsSettings`, `DashboardSettings`, `PreferencesSettings`, `ListViewSettings`, `Users`, `InviteUserPage`, `ERPNextSettings`, `WhatsAppSettings`, `ThemeSwitcher`, email (`EmailAccountList/Card/Add/Edit/Config`, `emailConfig.js`), plus subfolder `AssignmentRules/`, `EmailTemplate/`, `LeadSyncing/`, `Profile/`, `Sla/`, `Telephony/` |
| `components/Kanban/`, `ConditionsFilter/`, `FilesUploader/`, `Telephony/`, `Mobile/`, `Estimation/`, `Assistant/`, `Icons/` (111 ikon) | pendukung |
| `stores/` | `global`, `meta`, `session`, `settings`, `statuses`, `theme`, `users`, `views`, `organizations`, `notifications` |
| `composables/` | `document`, `doctypeModal`, `modals`, `settings`, `telephony`, `whatsapp`, `demoData`, `frappecloud`, `useActiveTabManager`, `useAttachments`, `useBroadcast`, `useKeyboardShortcuts` |
| `data/` | `document.js` (resource dokumen), `script.js` (loader form script) |
| `doctypes/` | form script berbasis file: `crm_quotation/form.js`, `crm_task/form.js`, `fcrm_note/form.js`, `fleet_location/form.js` |
| `utils/` | `index`, `model`, `view`, `callLog`, `dashboard.ts`, `dialogs.jsx`, `duplicate`, `expressions`, `fieldTransforms`, `gmap`, `numberFormat`, `renderFieldLayoutDialog`, `scriptHelpers`, `validityRange` |

### 13.4 Catatan penting frontend

- Form Quotation dan Inquiry **dirender dari `CRM Fields Layout`**, bukan dari komponen
  form statis. `QuotationDetails.vue` / `QuotationForm.vue` tinggal sisa dan tidak dipakai.
- Panel "Inquiry Details" di sidebar Quotation dan pengisian KM **tidak** dilakukan di
  `form.js`, melainkan di `pages/Quotation.vue`, karena `setupFormScript()` memanggil
  `triggerOnRender()` tanpa `await` sehingga kegagalan di dalamnya hilang sebagai
  unhandled rejection dan field diam-diam tetap kosong.
- Link field yang perlu menampilkan "kode - nama" diatur lewat map `CODE_NAME_DOCTYPES`
  di `Controls/Link.vue` (dengan `labelCache`).
- Print quotation memakai print format Jinja server (`Quotation Print Out`), bukan render
  di browser.

---

## 14. Wiring `hooks.py`

```python
app_name  = "crm_cakra"
app_icon_route = "/crm"
website_route_rules = [{"from_route": "/crm/<path:app_path>", "to_route": "crm"}]
add_to_apps_screen  = [{... "has_permission": "crm_cakra.api.check_app_permission"}]
get_site_info = "crm_cakra.activation.get_site_info"
export_python_type_annotations   = True
require_type_annotated_api_methods = True
ignore_links_on_delete = ["Failed Lead Sync Log"]
```

**Override class doctype**

| Doctype | Class |
|---|---|
| `Contact` | `crm_cakra.overrides.contact.CustomContact` |
| `Email Template` | `crm_cakra.overrides.email_template.CustomEmailTemplate` |

**`doc_events`**

| Doctype | Event | Handler |
|---|---|---|
| `*` | `before_insert` | `api.permissions.set_branch_from_user` |
| `Contact` | `validate` | `api.contact.validate` |
| `ToDo` | `after_insert`, `on_update` | `api.todo.after_insert`, `api.todo.on_update` |
| `Communication` | `after_insert`, `on_update` | `utils.on_communication_insert`, `utils.on_communication_update` |
| `Comment` | `after_insert`, `on_update` | `utils.on_comment_insert`, `api.comment.on_update` |
| `WhatsApp Message` | `validate`, `on_update` | `api.whatsapp.validate`, `api.whatsapp.on_update` |
| `CRM Inquiry` | `on_update` | `...erpnext_crm_settings.create_customer_in_erpnext` |
| `User` | `before_validate`, `validate_reset_password` | `api.live_demo.validate_user`, `api.live_demo.validate_reset_password` |

**Permission** — wildcard, lihat bab 9.

**Scheduler**

| Jadwal | Job |
|---|---|
| `daily_long` / `hourly_long` / `monthly_long` | `lead_syncing.background_sync.sync_leads_from_sources_{daily,hourly,monthly}` |
| cron `*/5`, `*/10`, `*/15 * * * *` | `sync_leads_from_sources_{5,10,15}_minutes` |

**Install / migrate**

```python
before_install = "crm_cakra.install.before_install"
after_install  = "crm_cakra.install.after_install"
before_uninstall = "crm_cakra.uninstall.before_uninstall"
setup_wizard_complete = "crm_cakra.demo.api.create_demo_data"
before_tests = "crm_cakra.tests.before_tests"
after_migrate = [
    "crm_cakra.fcrm.doctype.fcrm_settings.fcrm_settings.after_migrate",
    "crm_cakra.api.whatsapp.add_roles",
    "crm_cakra.install.after_migrate",
]
```

`install.after_migrate` **wajib** ada di `after_migrate`, bukan hanya `after_install`:
site yang sudah berjalan tidak pernah menjalankan `after_install` lagi, sehingga field
`User.custom_branches` dan seed `CMI Branch Access` tidak akan pernah muncul di server.

**`standard_dropdown_items`** (menu dropdown profil): `app_selector`, `settings`,
`login_to_fc`, `about`, separator, `logout`.

---

## 15. Install, migrate, patch, fixture

### `install.py` — yang diseed saat install

| Fungsi | Isi |
|---|---|
| `add_default_lead_statuses` | New (gray, Open, 1), Contacted (orange, Ongoing, 2), Nurture (blue, Ongoing, 3), Qualified (green, Won, 4), Converted (teal, Won, 5), Unqualified (red, Lost, 6), Junk (purple, Lost, 7) |
| `add_default_inquiry_statuses` | Qualification (gray, Open, 10%), Demo/Making (orange, Ongoing, 25%), Proposal/Quotation (blue, Ongoing, 50%), Negotiation (yellow, Ongoing, 70%), Ready to Close (purple, Ongoing, 90%), Won (green, Won, 100%), Lost (red, Lost, 0%) |
| `add_default_communication_statuses` | Open, Replied |
| `add_default_fields_layout` | layout Quick Entry / Side Panel / Data Fields bawaan |
| `add_default_quick_filters` | lihat 8.4 |
| `add_default_industries` / `add_default_lead_sources` / `add_default_lost_reasons` | master bawaan |
| `add_default_scripts` | `Product Details Script for CRM Lead` dan `... CRM Inquiry`, plus script forecasting |
| `add_property_setter`, `add_email_template_custom_fields`, `add_email_account_custom_field` | custom field `create_lead_from_incoming_email` di Email Account, dsb. |
| `add_assignment_rule_property_setters`, `create_assignment_rule_custom_fields` | dukungan Assignment Rule |
| `add_standard_dropdown_items` | dropdown profil |

`after_migrate()` (idempoten) menjalankan:

- `setup_user_branch_field()` — Custom Field `User.custom_branches` (Table MultiSelect ke
  `CMI User Branch`, label "Additional Branches");
- `setup_default_branch_access()` — seed `CMI Branch Access` sekali (default
  Branch + Owner; Sales Manager dan System Manager See All);
- `update_crm_inquiry_data_fields_layout()` — tambah section Shipment / Service / Cargo;
- `fix_crm_inquiry_doctype_validation_issues()`;
- rangkaian migrasi `type_inquiry`: `create_crm_type_inquiry_master_doctype`,
  `create_crm_inquiry_type_inquiry_child_doctype`, `populate_type_inquiry_master_records`
  (22 opsi), `migrate_existing_type_inquiry_data` (backup nilai Select lama),
  `change_type_inquiry_field_to_table_multiselect`, `restore_type_inquiry_data`,
  dibungkus `migrate_type_inquiry_to_multiselect()`.

### Patches (`patches/v1_0/`)

`add_email_in_default_lead_sources`, `add_fb_lead_source`, `add_fields_in_assignment_rule`,
`create_custom_fields_for_erpnext_in_crm`, `create_default_fields_layout`,
`create_default_lost_reasons`, `create_default_quick_filters`, `create_default_scripts`,
`create_default_sidebar_fields_layout`, `create_email_account_custom_field`,
`create_email_template_custom_fields`, `move_crm_note_data_to_fcrm_note`,
`move_twilio_agent_to_telephony_agent`, `rename_twilio_settings_to_crm_twilio_settings`,
`reset_erpnext_form_script`, `seed_cost_types` (dua tipe bawaan yang dipakai rumus
costing), `setup_dashboard_and_quotation_validity` (paksa layout dashboard ke default,
isi `default_valid_till`, backfill `validity_date`),
`update_inquiry_quick_entry_layout`, `update_inquiry_status_probabilities`,
`update_inquiry_status_type`, `update_layouts_to_new_format`, `update_lead_status_type`.

### Fixtures (`crm_cakra/fixtures/`, dideklarasikan di `hooks.py`)

| Fixture | Isi |
|---|---|
| `CRM Fields Layout` | hanya `dt in (CRM Inquiry, CRM Quotation, CRM Lead, CRM Estimation)` — supaya layout tidak hilang saat migrate |
| `CRM Inquiry Status` | status + warna + probability |
| `Translation` | `translated_text like "%Inquir%"` — relabel Deal menjadi Inquiry di UI tanpa mengubah doctype/route |
| `CRM Lead Source`, `CRM Transportation Mode`, `CRM Type Inquiry` | master pilihan |
| `Custom Field` | `Item-item_category`, `User-branch` |
| `CMI Office` | master kantor (alamat untuk print quotation) |
| `Role` | `Procurement Costing` |
| `Property Setter` | `CRM Quotation-main-default_print_format` |

### Demo data

`crm_cakra/demo/` membuat data contoh lengkap (users, leads, inquiries, tasks, notes,
call logs, activities) dengan backdating (`demo/utils.py`: `backdate`, `fix_auto_records`,
`insert_comment`, `insert_communication`, `insert_version`).
Endpoint: `demo.api.create_demo_data` (dipanggil `setup_wizard_complete`),
`clear_demo_data()`, `get_demo_state()`.

---

## 16. Penomoran dan print format

| Doctype | Format | Mekanisme |
|---|---|---|
| `CRM Lead` | `LD/0001/CMI/26` | `autoname()`, `make_autoname("LD-{yy}-.####.")` |
| `CRM Inquiry` | `INQ/0001/CMI/26` | `autoname()`, kunci `INQ-{yy}-` |
| `CRM Quotation` | `QT/0001/CMI/2026` | `autoname()`, kunci `QT-{YYYY}-` |
| `CRM Estimation` | `EST/0001/CMI/26` | `autoname()`, kunci `EST/CMI/{yy}/` (terlihat di Document Naming Settings) |
| `CRM Meeting` | `MTG-00001` | `autoname` doctype |
| `CRM Task`, `CRM View Settings` | autoincrement | |
| Master (`CMI Office`, `CRM Product`, `CRM Cost Type`, `CRM Cost Component`, status, dsb.) | `field:<nama>` | rename lewat `capture_rename`/`apply_rename` |

Semua kunci seri memuat tahun sehingga counter **reset otomatis tiap pergantian tahun**.

Print format (module FCRM, Jinja, `custom_format = 1`):

| Nama | Doctype | Catatan |
|---|---|---|
| `Quotation Print Out` | `CRM Quotation` | default lewat Property Setter `CRM Quotation-main-default_print_format`; font 14, margin 15/6, `pdf_generator = wkhtmltopdf`, page number Hide |
| `Inquiry Print Out` | `CRM Inquiry` | |

Catatan: kalau HTML print format diedit di file, **`modified`-nya harus dinaikkan**,
kalau tidak `bench migrate` melewatinya diam-diam.

---

## 17. Checklist build ulang

Urutan yang paling sedikit menimbulkan blokade:

1. **Master dan referensi dulu** — `CMI Office`, `CRM Industry`, `CRM Territory`,
   `CRM Lead Source`, `CRM Lead Status`, `CRM Inquiry Status`, `CRM Lost Reason`,
   `CRM Communication Status`, `CRM Type Inquiry`, `CRM Transportation Mode`.
   Tanpa status, Lead dan Inquiry tidak bisa disimpan.
2. **Costing** — `CRM Cost Type` (seed dua tipe: Fixed Cost, Variable Cost),
   `CRM Cost Item`, `CRM Cost Component`, `CRM Cost Component Link`, `CRM Product`.
   Uji dulu: validate komponen harus mengubah `fixed_cost_per_day` produk.
3. **Organization dan Contact** — `CRM Organization`, `CRM Contacts`, override Contact.
4. **Lead** lengkap dengan status change log, SLA opsional, dan konversi.
5. **Inquiry** — perhatikan `type_inquiry` sebagai Table MultiSelect sejak awal
   (di app asal ini hasil migrasi dari Select, jangan diulang).
6. **Quotation** — costing engine, validasi rute/KM yang "tidak boleh dikosongkan",
   sinkronisasi status ke inquiry, konversi ke estimation.
7. **Estimation**.
8. **Permission branch** — tambahkan `branch_office` ke setiap doctype transaksi,
   pasang hook wildcard, seed `CMI Branch Access`, buat Custom Field `User.branch`
   dan `User.custom_branches`.
9. **Mesin UI** — `CRM Fields Layout`, `CRM View Settings`, `CRM Form Script`,
   `CRM Global Settings`. Ekspor layout sebagai fixture sejak hari pertama.
10. **Frontend** — router + layout + FieldLayout renderer dulu, baru halaman per modul.
11. **Dashboard, notifikasi, aktivitas**.
12. **Integrasi opsional** — telephony, WhatsApp, ERPNext, Facebook sync, kurs.

Hal yang paling sering menggigit (semuanya sudah pernah terjadi di app asal):

- Field wajib baru pada doctype yang punya data lama = **seluruh dokumen lama terkunci**,
  bukan cuma field itu. Pola yang dipakai di sini: larang "dikosongkan", bukan "kosong".
- `bench migrate` menyeed ulang `CRM Fields Layout` -> layout custom hilang. Solusinya
  fixture.
- Rename doctype dengan `autoname: field:x` butuh `capture_rename` + `apply_rename`,
  kalau tidak nama dokumen tidak ikut berubah.
- `frappe.db.set_value` bentuk 3 argumen dengan objek (dari JS) gagal diam-diam; pakai
  bentuk 4 argumen per field.
- Nama dokumen mengandung `/` -> route SPA harus meng-encode-nya.
- `has_permission` wildcard **wajib** mengembalikan `True` untuk doctype yang tidak
  di-scope, kalau falsy Frappe menolak semuanya.
- Print format yang diedit di file butuh bump `modified`.


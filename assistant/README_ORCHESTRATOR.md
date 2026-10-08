# Orchestrator - README

Orchestrator mengubah kejadian menjadi **Agent Task** untuk orang yang harus bertindak. Kalau task didiamkan, task naik ke Controller lalu Admin. Cara penyelesaiannya disimpan sebagai pengetahuan untuk kejadian serupa. Per 2026-10-05.

Menu: Assistant > Orchestrator (`/app/orchestrator`). Kode: `assistant/assistant/orchestrator.py`.

## Alur

```
Kejadian -> Agent Task -> notifikasi PIC
  diam sampai Batas Action                -> Controller (severity naik)
  diam sampai Batas Controller            -> Admin (severity naik, berhenti)
  Tangani, tapi tidak selesai sampai Batas Selesai Sesudah Ditangani -> naik juga
  Selesai (isi cara penyelesaian)         -> jadi pengetahuan
  kondisi hilang sendiri                  -> ditutup otomatis oleh sistem
```

## Sumber kejadian

| Sumber | Dicek | Kejadian |
| --- | --- | --- |
| Email | tiap menit | Email customer tertaut ke transaksi, belum dibalas. Termasuk REVIEW dari email rules agent |
| Fleet | tiap 15 menit | Peringatan GPS (Fleet Status Rule) |
| Job | tiap 15 menit | Job di-assign lebih dari N jam, belum selesai |
| Document | tiap 15 menit | **Workflow rancangan sendiri**, untuk DocType apa pun |
| Manual | - | Dibuat Controller/Admin dari tombol Task Manual |

## Merancang workflow sendiri

Halaman Orchestrator > tab **Workflow** > **Workflow Baru** (hanya untuk role Orchestrator Controller, Orchestrator Admin, atau System Manager).

| Isian | Gunanya | Contoh |
| --- | --- | --- |
| Nama Workflow | Tampil di task dan monitoring | PO masih Draft |
| DocType | Dokumen yang diawasi | Purchase Order |
| Filter | Disaring di database. Tanpa akses baca DocType, diisi sebagai JSON | docstatus = 0 |
| Kondisi Tambahan | Python per dokumen, opsional. Field child table tidak tersedia | `doc.grand_total > 100000000` |
| Field Tanggal + Lewat Berapa Jam | Task dibuat kalau tanggal itu sudah lewat sekian jam. 0 = langsung | creation, 48 |
| Judul Task / Isi Task | Jinja, `doc` = dokumennya | `PO {{ doc.name }} masih draft ({{ doc.supplier }})` |
| PIC dari Field Dokumen | owner, _assign, atau field Link ke User. Kosong = Role Penanggung Jawab | owner |
| Batas Action, Batas Selesai Sesudah Ditangani, Controller, Admin | Rantai eskalasi | 240, 1440, Orchestrator Controller, Orchestrator Admin |

Klik **Uji** sebelum menyimpan. Hasilnya memperlihatkan jumlah dokumen yang akan jadi task sekarang, beserta contoh judul, isi, dan PIC-nya. Workflow baru tersimpan dalam keadaan mati sampai dicentang Aktif.

- Satu dokumen = satu task per workflow. Selama task-nya belum selesai, putaran berikutnya tidak membuat task baru.
- Dokumen yang sudah tidak memenuhi filter atau kondisi membuat task-nya ditutup otomatis ("Dokumen sudah tidak memenuhi kondisi workflow").
- Satu putaran membaca paling banyak 500 dokumen per workflow. Kalau lebih, task lama tidak ditutup otomatis pada putaran itu. Persempit filternya.
- Kondisi atau filter yang rusak tidak menghentikan workflow lain. Error-nya tampil merah di kartu workflow.

Contoh bawaan (semua mati): PO masih Draft, Sales Order lewat tanggal kirim, Sales Invoice lewat jatuh tempo, Purchase Invoice lewat jatuh tempo, Material Request belum dipesan, Expense Note belum divalidasi. Contoh ini ditambahkan saat migrate, sekali saja, selama belum ada workflow Document.

Workflow yang sama juga bisa diatur dari Assistant Settings > tab Orchestrator (baris bersumber Document).

## Pemeriksaan (sumber Audit)

Agent memeriksa data sendiri, mereview temuannya, dan menyusun laporan. User hanya melakukan final check. Kode: `assistant/assistant/audit.py`.

| Kode | Pemeriksaan | Tenggang bawaan | Keyakinan | Perbaikan yang disiapkan |
| --- | --- | --- | --- | --- |
| S1 | Sales Order lewat tanggal kirim, belum ditagih penuh | 1 hari | Pasti | Sales Invoice draft dari Delivery Note yang belum ditagih (kalau ada) |
| B1 | Purchase Order lewat tanggal terima, belum ada Purchase Invoice | 3 hari | Pasti | Purchase Invoice draft dari PO |
| E2 | Packing/Shipping List terbuka, biaya (EN tervalidasi) sudah keluar, belum ada Sales Invoice sama sekali | 14 hari | Pasti | - |
| E3 | Packing List terbuka tanpa Expense Note dan tanpa Sales Invoice | 30 hari | Perlu dicek | Close Packing List |
| E4 | Biaya dobel: EN beda, vendor dan job sama, item + container + nominal sama, selisih maksimal 7 hari | - | Perlu dicek | - |
| R1 | Expense Note reimburse tervalidasi yang barisnya belum masuk Sales Invoice Reimburse | 7 hari | Pasti | - |
| E1 | Biaya yang menurut riwayat estimasinya hampir selalu ada (90% dari minimal 5 job sebelumnya dengan estimasi sama) belum ada Expense Note-nya di Packing List terbuka | 14 hari | Perlu dicek | - |
| K1 | Voucher yang jurnalnya tidak seimbang (400 hari terakhir) | - | Pasti | - |
| K2 | Neraca saldo per company tidak seimbang | - | Pasti | - |
| K3 | Akun penampung bersaldo dan saldonya sudah ada sejak tenggang. Daftar akun di ERPNext Custom Setting > Orchestrator; kosong = akun bernama suspen/penampung/sementara | 30 hari | Perlu dicek | - |
| K4 | Buku pembantu piutang/hutang (Payment Ledger, tanda Payable dibalik) beda dengan saldo GL akunnya | - | Pasti | - |
| K5 | Akun kas/bank bersaldo minus | - | Perlu dicek | - |
| K6 | Payment Entry tervalidasi tanpa jurnal | - | Pasti | - |
| K7 | Jurnal bertanggal di masa depan | - | Perlu dicek | - |
| K8 | Company dengan tutup laba rugi bulanan (CMI Period Close, monthly_roll) yang bulan lalu belum ber-PCV | 10 hari | Pasti | - |

K1 sampai K8 = **Kesehatan Buku**. Keputusan yang dipakai: memberi tahu (tidak menolak transaksi), agent menjelaskan lewat Tanya Agent (tidak membuat jurnal), penerima = pembuat voucher atau Controller. K1, K2, K4 membaca seluruh GL sehingga paling sering sekali per jam.

Satu baris Orchestrator Rule bersumber Audit = satu pemeriksaan. Ditambahkan saat migrate dalam keadaan **mati + Uji Diam**. Ambang Waktu (jam) = tenggang.

Alur:

1. **Uji Diam** (bawaan): temuan dibuat tapi hanya terlihat Controller/Admin di Laporan > Uji Diam. Setuju di sini hanya dicatat, perbaikan tidak dijalankan. Putuskan beberapa temuan, lihat kolom Tepat, lalu klik **Akhiri Uji Diam** di tab Workflow.
2. **Reviewer** sebelum temuan masuk laporan: membuang temuan yang sudah dikecualikan Controller selama kondisinya sama persis, menurunkan pemeriksaan yang sering ditolak/dikoreksi (5 keputusan atau lebih, 20% atau lebih) ke "Perlu dicek", dan mengalihkan temuan tanpa PIC aktif (termasuk dokumen buatan Administrator/impor) ke Controller.
3. **Laporan** (tab Laporan, juga ringkasan email jam 07.00, satu per orang): PIC melihat temuannya, Controller melihat Tim, Admin melihat Uji Diam. Pemeriksaan yang error tampil sebagai "Pemeriksaan tidak jalan".
4. **Final check**: Setujui (menjalankan perbaikan sebagai user itu, dengan izinnya sendiri; draft tidak dibuat dua kali), Koreksi (wajib catatan), Tolak (wajib alasan, menjadi pengecualian setelah disetujui Controller). Setujui Semua hanya untuk temuan Pasti.
5. Temuan **tertutup sendiri** begitu kondisinya beres. Pengecualian yang disetujui dibuka lagi kalau nilai, tanggal, atau buktinya berubah.

Temuan tidak dieskalasi per menit dan tidak dikabari satu per satu: semuanya lewat laporan harian.

### Mode Otomatis (tahap 3)

Pemeriksaan yang punya perbaikan (S1, B1, E3) bisa dinaikkan dari Final check ke **Otomatis**: agent menjalankan perbaikannya sendiri tanpa menunggu user.

- **Syarat naik** (dihitung dari buku keputusan, tampil di Laporan > Tim, kolom Naik ke Otomatis): sudah selesai uji diam, minimal 30 keputusan user, 95% atau lebih Setuju tanpa koreksi, dan 20 keputusan terakhir tanpa Tolak maupun Batal.
- **Yang menaikkan**: hanya Orchestrator Admin atau System Manager, lewat tombol Jadikan Otomatis. Admin mengisi **Batas Nominal Otomatis**: temuan di atas nilai itu tetap ke final check. Agent tidak pernah menaikkan levelnya sendiri.
- **Cara jalan**: tiap putaran 15 menit, temuan Pasti yang belum diputuskan, punya PIC, dan masih dalam batas nominal diperbaiki atas nama PIC (izin dan pemilik dokumen = PIC). Hasilnya diverifikasi, lalu dicatat di riwayat task: sebelum, sesudah, dokumen yang dibuat.
- **Batalkan** (di Laporan, bagian Dikerjakan agent otomatis): draft dihapus atau Packing List dibuka lagi, dan temuan kembali ke final check. Batalkan juga tersedia untuk hasil Setujui manual.
- **Turun sendiri ke Final check** kalau hasil otomatis dibatalkan user, atau kalau eksekusi atau verifikasinya gagal. Admin diberi tahu, dan jejak naik/turun level tersimpan sebagai komentar di Assistant Settings.
- Submit dokumen, posting GL, pembayaran, dan Void tidak pernah dikerjakan otomatis.

Tes: `bench --site <situs> execute assistant.assistant.test_audit.run` (rollback, butuh minimal satu PO lewat tanggal tanpa PI).


## Monitoring

| Tab | Isi |
| --- | --- |
| Inbox Saya / Semua | Task yang menunggu, diurutkan menurut severity |
| Peta Kerja | Graf sumber, task, user, dan dokumen |
| Workflow | Tiap workflow: aktif atau mati, terakhir jalan (dicek, task baru, ditutup otomatis, atau error), task terbuka, dieskalasi, selesai 30 hari, rata-rata sampai selesai. Tombol Jalankan Sekarang, Ubah, Matikan, Hapus |
| Aktivitas | 200 kejadian terakhir: apa yang dikerjakan sistem (task dibuat, notifikasi, eskalasi, ditutup otomatis), user (tangani, catat langkah, selesai, oper), dan agent (chat dan email dari Agent History). Bisa disaring Agent dan Sistem / User |
| Pengetahuan | Task selesai beserta cara penyelesaiannya |

User biasa hanya melihat task miliknya atau task yang dikabarkan kepadanya. Daftar workflow dan angkanya terlihat untuk semua.

## Tes

```bash
bench --site <situs> execute assistant.assistant.test_orchestrator.run
```

Tes ini mencakup dedupe, rantai eskalasi, eskalasi task yang sudah ditangani, task manual tanpa rule Job, dan workflow Document (Uji, PIC dari field, tutup otomatis, monitoring, kondisi rusak).

## Belum ada

- Saluran WhatsApp (perlu penyedia dan akun).
- Rantai eskalasi lebih dari 3 tingkat.
- Workflow bertahap atau bercabang (langkah 1 lalu langkah 2). Satu workflow = satu kondisi.

## Rantai antar agent (sumber Chain)

Agent saling serah terima lewat Orchestrator, tidak saling memanggil. Kode: `assistant/assistant/chain.py`. Saklar per rantai di ERPNext Custom Setting > tab Orchestrator, **bawaan mati**.

| Rantai | Pemicu | Langkah |
| --- | --- | --- |
| Reimburse | Expense Note reimburse divalidasi | Agent Billing: Sales Invoice Reimburse draft untuk semua reimburse customer itu yang siap ditagih, lalu User: validasi, lalu Agent Accounting: periksa jurnal |
| Trading | Delivery Note divalidasi | Agent Billing: Sales Invoice draft dari DN (mapper Cakra), lalu User: validasi, lalu Agent Accounting: periksa jurnal |
| Pembelian | Purchase Invoice divalidasi | Agent Accounting: periksa jurnal (seimbang, hutang = total invoice, akun valid) |

- Tiap langkah = satu Agent Task (Inbox, Aktivitas, tab **Rantai**). Konteks langkah sebelumnya ikut di isi task.
- Agent Billing bekerja atas nama pemilik dokumen sumber (izin dan pemilik draft = dia). Pemilik Administrator/nonaktif = langkah user ke Controller.
- **Satu dokumen satu pemilik**: langkah agent menunggu selama dokumennya masih dipegang langkah lain.
- **Berhenti di langkah manusia**: user memvalidasi SI, baru Agent Accounting jalan. Kalau invoice Reimburse tervalidasi otomatis (setting auto validate), langkah user dilewati.
- Agent Accounting memeriksa: jurnal seimbang, piutang = total invoice, akun bukan grup/nonaktif dan milik company yang sama, PPN reimburse sesuai baris EN.
- Gagal atau ada temuan = rantai berhenti, task diserahkan ke Controller (tab Rantai menandai merah). Tidak ada percobaan ulang diam-diam; langkah agent yang belum tersentuh (antrean mati) dijalankan lagi tiap 15 menit.

Tes: `bench --site <situs> execute assistant.assistant.test_chain.run` (rollback).

## Penasihat (sumber Advisor)

Tanggal 1 tiap bulan jam 06.00 agent meninjau bulan sebelumnya dan memberi saran keputusan bisnis dengan angka. Agent tidak mengubah data. Kode: `assistant/assistant/advisor.py`. Saklar: ERPNext Custom Setting > tab Orchestrator > Aktifkan Tinjauan Bulanan (**bawaan mati**). Tombol **Jalankan Tinjauan Sekarang** di Laporan > Saran Bulanan tetap bisa dipakai Controller/Admin walau saklar mati.

| Saran | Muncul kalau |
| --- | --- |
| Customer piutang menua / mulai telat bayar | Piutang lewat jatuh tempo minimal Rp 1 juta dan tertua 60 hari atau lebih; atau rata-rata telat bayar (tanggal lunas di Payment Ledger dikurangi jatuh tempo) naik 15 hari atau lebih dibanding 3 bulan sebelumnya, minimal 2 invoice |
| Biaya vendor naik | Biaya Expense Note bulan ini naik 30% atau lebih dan minimal Rp 5 juta dibanding rata-rata 3 bulan sebelumnya |
| Vendor sering telat | 90 hari terakhir minimal 3 Purchase Invoice, rata-rata 7 hari atau lebih lewat tanggal terima PO |
| Margin rute turun / negatif | Per rute asal ke tujuan (Packing/Shipping List yang sudah ditagih): margin 3 bulan terakhir negatif, atau turun 10 poin atau lebih dari 3 bulan sebelumnya; minimal 2 job. Disebut juga vendor dengan biaya terbesar di rute itu |

Maksimal 10 saran per jenis, diurutkan menurut nilai. Controller memutuskan **Tindak lanjuti** (wajib tulis tindakan; boleh langsung diserahkan ke user lain sebagai task manual yang ikut eskalasi) atau **Abaikan** (wajib alasan). Tabel Kegunaan saran menghitung keputusan per jenis selama 12 bulan, untuk menyetel ambang. Saran bulan lalu yang belum diputuskan ditutup saat tinjauan berikutnya jalan.

Tes: `bench --site <situs> execute assistant.assistant.test_advisor.run` (rollback).

## Sampai ke user

- **Pintu masuk**: item **Laporan Saya** di sidebar desk semua user (di bawah Notification), angka = temuan yang menunggu keputusan (plus pengajuan pengecualian untuk Controller/Admin). File `assistant/public/js/audit_entry.js`, angka dari `audit.my_count`.
- **Pemberitahuan**: laporan jam 07.00 dan saran bulanan membuat Notification Log ber-link `/app/orchestrator?view=report`, sehingga muncul di lonceng, toast desk, dan popup aplikasi desktop (notification_badge.js), dan klik langsung membuka Laporan. Email ringkasan dikirim juga.
- **Tampilan user biasa**: judul halaman "Laporan Saya", tab Laporan, Inbox Saya, Rantai, Pengetahuan. Peta Kerja, Semua, Workflow, Aktivitas hanya untuk Controller/Admin; kotak angka atas hanya menghitung task miliknya.
- **Panduan**: Manual Book > **Manual Laporan Saya** (Roadmap, Cara Pakai, Contoh, Controller, FAQ); ditautkan dari bawah halaman Laporan.

## Laporan Saya dan Tugas Saya

- Halaman **Laporan Saya** (`/app/laporan-saya`, semua user) dan **Orchestrator** (`/app/orchestrator`, hanya System Manager, Orchestrator Controller, Orchestrator Admin, GPS Operator) memakai satu kode tampilan: `assistant/public/js/orchestrator_view.js`, mode `user` / `admin`. Dimuat sebagai `<script>` (bukan frappe.require); naikkan `?v=` di kedua file halaman setiap file itu berubah.
- Tab pertama Laporan Saya = **Tugas Saya** (`orchestrator.my_tasks`): semua task yang dipegang user dari sumber mana pun, dengan kalimat langkah berikutnya, siapa yang mengoper, tombol Tangani / Selesai / Setujui / Koreksi / Tolak / Buka dokumen langsung di baris. Controller/Admin juga mendapat pengajuan pengecualian, temuan tanpa PIC, dan saran bulanan. **Menunggu orang lain** = pengecualian yang diajukan dan task yang ia oper 14 hari terakhir.
- Angka di sidebar = jumlah Tugas Saya. Kotak angka di tab task menghitung isi daftar yang sedang dibuka (milik sendiri di Inbox Saya; seluruh perusahaan hanya di tab Semua Orchestrator).
- Tes: `bench --site <situs> execute assistant.assistant.test_my_tasks.run`.
- Penyelesaian = aksi user: di Tugas Saya tombol utama membawa user ke tempat kerjanya (`orchestrator._go`): Email = Mailbox `?open=<email>&compose=reply` (atau form dokumen kalau emailnya tidak ketemu), Job = Dispatch Order, Document = dokumennya; ketiganya tertutup sendiri. Klik tombol = Tangani (eskalasi berhenti). GPS/Manual = Selesai satu klik. `resolve()`: catatan opsional untuk Ditangani (tercatat "Diselesaikan oleh ..."), wajib untuk Normal / Tidak Valid.

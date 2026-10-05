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

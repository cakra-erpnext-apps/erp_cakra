# Oakglobal ERP Custom

Custom ERPNext untuk semua

This app contains custom business processes, reports, workflows, fixtures, and integrations for ERPNext.# Frappe Module Structure Generator

Script untuk generate struktur folder custom app Frappe / ERPNext secara otomatis.
Semua perubahan terpisah dari file bawaan ERPNext — aman saat update, history jelas di Git.

---

## Cara Pakai

```bash
chmod +x create_module.sh
bash create_module.sh
```

Script akan tanya beberapa hal:

```
Nama modul  : depo
Mau buat apa? [1/2/3]: 3
DocType yang mau di-override: Quotation,Sales Order
Nama DocType baru           : Isotank,Stacking
Tambah API? [y/n]: y
```

**Pilihan mode:**

| Pilihan | Keterangan |
|---------|------------|
| `1` | customize saja — override DocType bawaan ERPNext |
| `2` | new saja — buat DocType baru dari nol |
| `3` | keduanya |

Selesai — folder `apps/` langsung terbuat dengan semua file siap diedit.

---

## Struktur yang Dihasilkan

```
apps/                               ← root repo, ini yang di-push ke GitHub
├── setup.py                        ← konfigurasi package Python
├── modules.txt                     ← daftar nama modul yang terdaftar
├── .gitignore
├── README.md                       ← README otomatis per repo
│
└── depo/                           ← nama modul (sesuai input)
    ├── __init__.py
    ├── hooks.py                    ← pusat config: daftarkan semua override, JS, fixtures, API
    ├── patches.txt                 ← daftar migration script saat ada perubahan skema
    ├── api.py                      ← endpoint API (dibuat jika pilih y)
    │
    ├── customize/                  ← override modul bawaan ERPNext
    │   ├── overrides/              ← extend class Python bawaan (Quotation, Sales Order, dll)
    │   │   ├── __init__.py
    │   │   ├── quotation.py        ← tambah/ubah logic validate, submit, cancel
    │   │   └── sales_order.py
    │   ├── fixtures/               ← custom field & property setter dalam JSON — masuk Git
    │   │   ├── custom_field.json   ← field baru yang ditambah lewat UI Customize Form
    │   │   └── property_setter.json← perubahan property field existing (label, reqd, dll)
    │   └── public/
    │       ├── js/                 ← tambah tombol, hide/show field, event handler per DocType
    │       │   └── quotation.js
    │       └── css/
    │           └── custom.css      ← styling tambahan untuk form
    │
    └── new/                        ← DocType & modul baru dari nol
        ├── config/
        │   ├── __init__.py
        │   └── desktop.py          ← daftarkan modul ke halaman utama + urutan menu sidebar
        ├── public/
        │   ├── js/
        │   └── css/
        └── doctype/
            ├── isotank/            ← satu folder per DocType
            │   ├── isotank.json    ← definisi field & form (auto-generate, bisa diedit)
            │   ├── isotank.py      ← logic Python: validate, on_submit, on_cancel
            │   ├── isotank.js      ← logic JavaScript: tombol, event, UI form
            │   └── test_isotank.py ← unit test
            └── stacking/
                └── ...
```

---

## Penjelasan File Penting

### `hooks.py`
Pusat konfigurasi. Semua override Python, JS, CSS, fixtures, dan scheduler didaftarkan di sini.
Jangan diedit manual kecuali perlu tambah config baru.

### `customize/overrides/*.py`
Extend class bawaan ERPNext tanpa menyentuh file ERPNext.
Selalu panggil `super()` sebelum logic custom agar behavior asli tetap jalan.

### `customize/fixtures/`
Berisi custom field dan property setter dalam format JSON.
Di-generate otomatis lewat `bench export-fixtures` setelah tambah field lewat UI.
File ini yang memastikan custom field ikut terpasang saat deploy ke server lain.

### `new/config/desktop.py`
Daftarkan modul ke halaman utama ERPNext dan atur urutan menu sidebar via `idx`.

### `api.py`
Endpoint API siap pakai. Semua endpoint wajib pakai secret key kecuali `/status`.

---

## Urutan Menu Sidebar

Diatur lewat `idx` di `new/config/desktop.py`:

```python
"items": [
    {"name": "Isotank",  "idx": 1},   # ← muncul pertama
    {"name": "Stacking", "idx": 2},   # ← muncul kedua
]
```

Tukar nilai `idx` untuk reorder, lalu:

```bash
bench restart
```

---

## API (Secret Key)

Semua endpoint wajib pakai API key kecuali `/status`.

**Generate key:** ERPNext → User → [pilih user] → API Access → Generate Keys

**Format header:**
```
Authorization: token <api_key>:<api_secret>
```

**Endpoint:**

| Method | Path | Keterangan |
|--------|------|------------|
| GET | `/api/method/apps.<modul>.api.get_list` | Ambil list dokumen |
| GET | `/api/method/apps.<modul>.api.get_detail` | Ambil satu dokumen |
| POST | `/api/method/apps.<modul>.api.create` | Buat dokumen baru |
| POST | `/api/method/apps.<modul>.api.update` | Update dokumen |
| POST | `/api/method/apps.<modul>.api.delete` | Hapus dokumen |
| GET | `/api/method/apps.<modul>.api.status` | Health check (publik) |

**Contoh curl:**
```bash
curl -X GET "http://site/api/method/apps.depo.api.get_list?doctype=Isotank" \
  -H "Authorization: token abc123:xyz789"
```

**Dari JavaScript di dalam form ERPNext:**
```javascript
frappe.call({
    method: "apps.depo.api.get_list",
    args: { doctype: "Isotank" },
    callback(r) { console.log(r.message); }
});
```

---

## Setelah Script Selesai

```bash
# 1. Copy ke bench
cp -r apps ~/frappe-bench/apps/apps

# 2. Install ke site
cd ~/frappe-bench
bench --site nama_site install-app apps
bench --site nama_site migrate
bench restart

# 3. Aktifkan developer mode
bench --site nama_site set-config developer_mode 1
```

---

## Workflow Harian

| Ubah file | Perintah |
|-----------|----------|
| `.py` | `bench restart` |
| `.js` / `.css` | `bench build --app apps` atau `bench watch` |
| `.json` / field baru | `bench --site nama_site migrate` |
| Tambah custom field lewat UI | `bench --site nama_site export-fixtures` |
| Ubah urutan menu sidebar | Edit `idx` di `desktop.py` → `bench restart` |

---

## Push ke GitHub

```bash
cd apps
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/username/apps.git
git push -u origin main
```

Install di server lain:

```bash
bench get-app https://github.com/username/apps.git
bench --site nama_site install-app apps
bench --site nama_site migrate
bench restart
```
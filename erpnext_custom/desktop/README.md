# Aplikasi desktop ERP (Windows)

Jendela sendiri yang membuka ERP di server, hidup di tray seperti Outlook:
terbuka saat login Windows (langsung ke Inbox), ditutup = sembunyi di tray,
notifikasi ERP (email baru, assign, dll.) muncul sebagai popup Windows.
Isinya bukan salinan ERP, jadi perubahan fitur di server tidak perlu build ulang.

## Build (per server)

Alamat server ditanam saat build. Build di Windows:

```
cd erpnext_custom/desktop
npm install
npm version patch --no-git-tag-version
npm run dist -- -c.extraMetadata.erpUrl=https://app.contoh.com
```

- `npm version patch` wajib tiap rilis: update otomatis hanya jalan kalau versinya naik.
- Tanpa `-c.extraMetadata...` = `erpUrl` di package.json (localhost:8080, untuk lokal).
- `erpUrl` hanya alamat BAWAAN. Sejak 1.0.9 tiap laptop bisa mengganti alamat server sendiri di
  halaman **Server** (tombol Server di sidebar aplikasi, tray > Server..., menu Alt > View >
  Server..., atau otomatis saat server tidak terjangkau). Disimpan di
  `%APPDATA%\Cakra ERP\server.json`; aplikasi dibuka ulang ke alamat itu dan update otomatis ikut
  mengambil dari `/files/` server tersebut. Jadi satu installer bisa dipakai untuk semua server.
- Nama aplikasi: tambah `-c.productName="Nama ERP"`.
- Dari terminal VS Code: hapus dulu `ELECTRON_RUN_AS_NODE` dan `CHROME_CRASHPAD_PIPE_NAME`
  (warisan VS Code; yang pertama bikin Electron jadi Node biasa, yang kedua bikin macet).
- EPERM saat rename `win-unpacked.tmp` = berkas sedang dipindai antivirus, ulangi build.

## Deploy

Unggah lewat ERP: **ERPNext Custom Setting > tab Desktop App > Upload Installer**, pilih tiga
berkas dari `dist/` sekaligus (installer `.exe` boleh sudah diganti nama, misal `mail-v1.0.9.exe`):

- installer `.exe` : diunduh tombol **Access on Device** (menu Mail)
- `latest.yml` + `.blockmap` : dibaca update otomatis

Server (`erpnext_custom/desktop_app.py`) mengunggahnya per potongan 4 MB, mengecek sha512
installer terhadap `latest.yml` (berkas dari build berbeda ditolak) dan menolak versi yang lebih
lama dari yang sudah terbit. Disimpan di `/files/desktop/<versi>/`, `latest.yml` di `/files/`
menunjuk ke versi terbaru, dan hanya **3 versi terakhir** yang disimpan (yang lebih lama
dihapus tiap unggah). Satu installer bisa diunggah ke semua server (alamat server diatur di
aplikasi). Jangan unggah lewat tombol Attach biasa: Frappe mengganti nama berkas yang sudah ada.

Aplikasi terpasang mengecek `latest.yml` saat mulai dan tiap 6 jam, mengunduh di
latar, lalu memasangnya saat jendela di tray (hidup lagi tetap di tray). Hanya lewat
https (atau localhost). Jejaknya di `%APPDATA%\<nama aplikasi>\update.log`.

## Jadwal build ulang

Electron membawa Chromium sendiri dan hanya 3 versi major terakhir yang dapat tambalan
keamanan (sekitar 6 bulan per versi). Build ulang **tiap 2-3 bulan** dan tiap ada
pengumuman celah keamanan Chrome yang serius:

```
npm install -D electron@latest electron-builder@latest
npm install electron-updater@latest
```

lalu langkah Build + Deploy di atas.

Installer belum ditandatangani: Windows menampilkan "Windows protected your PC"
sekali saat instal manual (More info > Run anyway). Update otomatis tidak memunculkannya.

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
- Nama aplikasi: tambah `-c.productName="Nama ERP"`.
- Dari terminal VS Code: hapus dulu `ELECTRON_RUN_AS_NODE` dan `CHROME_CRASHPAD_PIPE_NAME`
  (warisan VS Code; yang pertama bikin Electron jadi Node biasa, yang kedua bikin macet).
- EPERM saat rename `win-unpacked.tmp` = berkas sedang dipindai antivirus, ulangi build.

## Deploy

Salin tiga berkas dari `dist/` ke `sites/<site>/public/files/` di server:

- `erp-desktop-setup.exe` : diunduh tombol **Access on Device** (menu Mail)
- `latest.yml` + `erp-desktop-setup.exe.blockmap` : dibaca update otomatis

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

<script setup>
import { computed, ref } from 'vue'
import { call, position } from '../api'
import Ikon from '../Ikon.vue'
import Kamera from '../Kamera.vue'
import Peringatan from '../Peringatan.vue'
import PilihKendaraan from '../PilihKendaraan.vue'
import Sibuk from '../Sibuk.vue'
import { stampedSelfie } from '../photo'
import { refresh, state } from '../store'

const busy = ref('')
const err = ref('')
const info = ref('')

// Di layar absensi semua penolakan berwarna merah, termasuk yang sebabnya aturan
// (truk sudah dipakai orang lain, terlalu jauh, sudah absensi). Kuning dulunya
// membedakan "bisa diperbaiki sendiri", tapi di sini bedanya tidak berguna: apa
// pun sebabnya sopir tidak bisa mulai kerja, dan kuning terbaca sebagai catatan.
const pasangError = (e) => (err.value = e.message)
// Nopol terakhir yang dipakai sudah terisi: sopir hampir selalu naik truk yang
// sama, dan mengetiknya ulang tiap pagi cuma menambah satu ketukan.
const vehicle = ref(state.me.last_vehicle || '')
const pilihBuka = ref(false)
const kameraBuka = ref(false)

// Tiga keadaan yang berdiri sendiri, bukan satu tangga. Sopir bisa sedang
// menjalankan job SEKALIGUS belum absen hari ini (job yang mulai kemarin), dan
// tombol absennya tetap harus muncul.
const belumAbsen = computed(() => !state.me.sudah_absen)

// Diperiksa SEBELUM tombolnya ditekan. Kalau kamera tidak mungkin dibuka,
// sopir harus tahu sebabnya sekarang, bukan menekan tombol yang diam saja.
const kameraTidakBisa = !navigator.mediaDevices?.getUserMedia
  ? window.isSecureContext
    ? 'Perangkat ini tidak punya kamera yang bisa diakses.'
    : 'Kamera diblokir browser karena alamatnya bukan HTTPS. Buka apps lewat alamat https.'
  : ''
const sedangJob = computed(() => state.me.on_job)

// Isi lencana di kartu status. Saat sedang job, nopolnya diambil dari job itu
// -- job yang mulai kemarin tidak punya check in hari ini, dan tanpa ini kartu
// sopir yang justru sedang di jalan malah kosong.
const lencanaKendaraan = computed(() => {
  const j = state.me.job
  const nopol = state.me.vehicle || (j && j.vehicle)
  if (!nopol) return ''
  return j && j.customer ? `${nopol} - ${j.customer}` : nopol
})
const siap = computed(() => state.me.siap)

// `busy` menyimpan NAMA aksi supaya labelnya bisa berbeda, dan string kosong saat
// idle. Vue menganggap string kosong sebagai TRUE untuk atribut boolean
// (`includeBooleanAttr = !!value || value === ''`), jadi `:disabled="busy"`
// mematikan tombol justru saat tidak ada apa-apa. Selalu pakai boolean ini.
const sibuk = computed(() => busy.value !== '')

const pesanSibuk = computed(() =>
  ({
    absen: 'Mengirim absensi...',
    checkin: 'Memeriksa lokasi kendaraan...',
    checkout: 'Mengirim data...',
  })[busy.value] || 'Mengirim data...',
)

// Lima terakhir saja. Dipotong di layar, BUKAN di server: `me()` memakai seluruh
// daftar hari ini untuk menentukan sudah absen / sedang siap, jadi memotongnya di
// sana akan merusak statusnya begitu sopir lewat dari lima kejadian.
const aktivitas = computed(() => state.me.attendance.slice(-5))

const keterangan = computed(() => {
  if (sedangJob.value) return 'Sedang menjalankan job'
  if (belumAbsen.value) return 'Belum absensi hari ini'
  if (siap.value) return 'Siap menerima job'
  if (state.me.status === 'Check Out') return 'Berhenti menerima job'
  return 'Sudah absen'
})

// Warna kartu status = warna titik di header. Amber berarti "sedang jalan",
// hijau "siap", abu "belum ada apa-apa" -- satu bahasa warna untuk seluruh apps.
const gayaStatus = computed(() => {
  if (sedangJob.value) return 'from-accent-500 to-accent-500 shadow-accent-500/25'
  if (belumAbsen.value) return 'from-slate-600 to-slate-800 shadow-slate-900/20'
  if (siap.value) return 'from-brand-500 to-brand-600 shadow-brand-500/25'
  return 'from-slate-500 to-slate-700 shadow-slate-900/20'
})

// "27 Agustus 2026 - 10:30". Jam disusun manual: toLocaleTimeString('id-ID')
// memakai titik sebagai pemisah jam-menit, bukan titik dua.
function tanggalJam(ts) {
  const d = new Date(ts)
  const tanggal = d.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' })
  const jam = String(d.getHours()).padStart(2, '0')
  const menit = String(d.getMinutes()).padStart(2, '0')
  return `${tanggal} - ${jam}:${menit}`
}

async function jalankan(label, fn) {
  busy.value = label
  err.value = ''
  info.value = ''
  try {
    await fn()
    await refresh()
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = ''
  }
}

// Satu tombol untuk absen SEKALIGUS check in: keduanya terjadi di titik dan
// menit yang sama, jadi jaraknya diperiksa sekali di server.
async function absen(video) {
  // Sibuk dinyalakan SEJAK frame diambil, bukan sejak unggahan mulai: membaca
  // GPS bisa makan beberapa detik dan selama itu layar tampak diam.
  busy.value = 'absen'
  err.value = ''
  info.value = ''
  try {
    const p = await position()
    // Frame diambil SEBELUM kamera ditutup: elemen video jadi kosong begitu
    // stream-nya dilepas, jadi menutup dulu berarti menyimpan gambar hitam.
    const photo = video
      ? await stampedSelfie(video, [
          state.me.driver.title,
          new Date().toLocaleString('id-ID'),
          p ? `${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)}` : 'Lokasi tidak terbaca',
        ])
      : null
    kameraBuka.value = false
    const r = await call('absensi', { vehicle: vehicle.value, photo, ...(p || {}) })
    info.value = r.gps_stale
      ? 'Absensi tercatat dan Anda siap menerima job, tapi GPS kendaraan sedang tidak aktif jadi jarak tidak diverifikasi.'
      : `Absensi tercatat, Anda siap menerima job dengan ${vehicle.value}.`
    await refresh()
  } catch (e) {
    kameraBuka.value = false
    pasangError(e)
  } finally {
    busy.value = ''
  }
}

// Tombol absen: buka kamera dulu kalau setelan foto nyala, kalau tidak langsung
// kirim. Kendaraan wajib dipilih karena absensinya diverifikasi ke posisi truk.
function mulaiAbsen() {
  if (!vehicle.value) {
    err.value = 'Pilih kendaraan dulu.'
    return
  }
  if (state.me.absen_foto) kameraBuka.value = true
  else absen(null)
}

async function checkIn() {
  if (!vehicle.value) {
    err.value = 'Pilih kendaraan dulu.'
    return
  }
  await jalankan('checkin', async () => {
    const p = await position()
    if (!p) throw new Error('Lokasi HP tidak terbaca. Nyalakan GPS lalu coba lagi.')
    const r = await call('check_in', { vehicle: vehicle.value, ...p })
    info.value = r.gps_stale
      ? 'Tercatat siap menerima job, tapi GPS kendaraan sedang tidak aktif jadi jarak tidak diverifikasi.'
      : `Siap menerima job, jarak ${r.distance_m} m dari kendaraan.`
  })
}

async function checkOut() {
  await jalankan('checkout', async () => {
    const p = await position()
    await call('check_out', p || {})
  })
}
</script>

<template>
  <Kamera v-if="kameraBuka" @ambil="absen" @tutup="kameraBuka = false" />
  <Sibuk v-if="busy" :teks="pesanSibuk" />
  <PilihKendaraan
    v-if="pilihBuka"
    :terpilih="vehicle"
    @pilih="(v) => ((vehicle = v), (pilihBuka = false))"
    @tutup="pilihBuka = false"
  />

  <div class="grid gap-4">
    <!-- Kartu status: satu-satunya hal yang harus terbaca dari jarak lengan. -->
    <div
      class="rounded-2xl bg-gradient-to-br p-4 text-white shadow-lg"
      :class="gayaStatus"
    >
      <div class="flex items-center gap-2 text-[0.7rem] font-semibold uppercase tracking-wider text-white/70">
        <span class="relative flex h-2 w-2">
          <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-white/70"></span>
          <span class="relative inline-flex h-2 w-2 rounded-full bg-white"></span>
        </span>
        Status hari ini
      </div>
      <div class="mt-1 text-2xl font-bold leading-tight">{{ keterangan }}</div>
      <div
        v-if="lencanaKendaraan"
        class="chip mt-3 bg-white/15 text-white ring-1 ring-white/20"
      >
        <Ikon n="truk" class="h-4 w-4" />
        {{ lencanaKendaraan }}
      </div>
    </div>

    <Peringatan :pesan="err" />
    <Peringatan :pesan="info" jenis="ok" />

    <!-- Absensi: muncul selama belum absensi hari ini, termasuk saat sedang job. -->
    <div v-if="belumAbsen" class="card grid gap-3">
      <div class="flex items-start gap-3">
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
          <Ikon n="kamera" />
        </span>
        <div>
          <div class="font-semibold">Absensi</div>
          <p class="mt-0.5 text-sm text-slate-500">
            Absensi di samping kendaraan, batas {{ state.me.radius_m }} m. Sekali tekan Anda
            tercatat absen sekaligus siap menerima job.
            <span v-if="state.me.absen_foto">
              Kamera depan akan terbuka, waktu dan lokasi ikut tercetak di foto.
            </span>
            <span v-if="sedangJob">Anda masih punya job berjalan, absensi dulu hari ini.</span>
          </p>
        </div>
      </div>
      <Peringatan v-if="state.me.absen_foto" :pesan="kameraTidakBisa" />

      <button class="field flex items-center justify-between text-left" @click="pilihBuka = true">
        <span :class="vehicle ? 'font-medium' : 'text-slate-400'">
          {{ vehicle || 'Pilih Kendaraan' }}
        </span>
        <span class="text-sm text-slate-400">Ubah</span>
      </button>

      <button
        class="btn-primary"
        :disabled="sibuk || (state.me.absen_foto && !!kameraTidakBisa)"
        @click="mulaiAbsen"
      >
        {{ busy === 'absen' ? 'Mengirim...' : 'Absensi & Siap Kerja' }}
      </button>
    </div>

    <!-- Siap / Berhenti: hanya setelah absen, dan tidak saat sedang job. -->
    <div v-if="!belumAbsen && !sedangJob" class="card grid gap-3">
      <div class="flex items-start gap-3">
        <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">
          <Ikon n="truk" />
        </span>
        <div>
          <div class="font-semibold">Kesiapan Kerja</div>
          <p class="mt-0.5 text-sm text-slate-500">
            <template v-if="!siap">
              Pilih kendaraan lalu nyatakan siap. Posisi HP dicocokkan dengan posisi
              kendaraan, batas {{ state.me.radius_m }} m.
            </template>
            <template v-else>
              Anda siap menerima job dengan kendaraan {{ state.me.vehicle }}.
            </template>
          </p>
        </div>
      </div>

      <!-- Satu tombol saja yang tampil: yang sudah check in tidak punya urusan
           dengan tombol check in, dan sebaliknya. -->
      <template v-if="!siap">
        <button class="field flex items-center justify-between text-left" @click="pilihBuka = true">
          <span :class="vehicle ? 'font-semibold' : 'text-slate-400'">
            {{ vehicle || 'Pilih Kendaraan' }}
          </span>
          <Ikon n="lanjut" class="h-4 w-4 text-slate-400" />
        </button>
        <button class="btn-primary" :disabled="sibuk" @click="checkIn">
          {{ busy === 'checkin' ? 'Memeriksa lokasi...' : 'Siap Menerima Job' }}
        </button>
      </template>

      <button v-else class="btn-ghost" :disabled="sibuk" @click="checkOut">
        {{ busy === 'checkout' ? 'Mengirim...' : 'Berhenti Menerima Job' }}
      </button>
    </div>

    <div v-if="!belumAbsen && sedangJob" class="card flex items-center gap-3">
      <span class="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-50 text-accent-600">
        <Ikon n="truk" />
      </span>
      <p class="text-sm text-slate-500">
        Anda sedang menjalankan job. Kesiapan kerja bisa diubah setelah job selesai.
      </p>
    </div>

    <div class="card grid gap-3">
      <div class="flex items-baseline justify-between gap-3">
        <div class="font-semibold">Aktivitas Hari Ini</div>
        <span
          v-if="state.me.attendance.length > aktivitas.length"
          class="text-xs text-slate-400"
        >
          {{ aktivitas.length }} dari {{ state.me.attendance.length }}
        </span>
      </div>

      <p v-if="!state.me.attendance.length" class="text-sm text-slate-500">
        Belum ada aktivitas hari ini.
      </p>

      <!-- Tanpa batas tinggi: `main` sudah menggulung sendiri, jadi membatasi di
           sini hanya menghasilkan gulungan di dalam gulungan -- yang di layar
           sentuh berarti daftar ikut bergeser saat sopir mau menggulung halaman. -->
      <!-- Garis waktu digambar dengan border kiri pada <li>, bukan elemen garis
           sendiri: garis absolut selalu meleset kalau satu baris jadi dua baris. -->
      <ul v-else class="grid">
        <li
          v-for="(a, i) in aktivitas"
          :key="a.name"
          class="relative flex items-baseline justify-between gap-3 border-l-2 border-slate-100 pb-4 pl-5 last:border-transparent last:pb-0"
        >
          <span
            class="absolute -left-[0.3rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white"
            :class="i === aktivitas.length - 1 ? 'bg-brand-600' : 'bg-slate-300'"
          ></span>
          <span>
            <span class="block text-sm font-semibold">{{ a.type }}</span>
            <span class="block text-xs text-slate-400">{{ tanggalJam(a.timestamp) }}</span>
          </span>
          <span v-if="a.vehicle" class="shrink-0 text-xs font-medium text-slate-500">
            {{ a.vehicle }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

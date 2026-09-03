<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { call, login } from './api'
import Ikon from './Ikon.vue'
import Peringatan from './Peringatan.vue'
import { koneksi, pesanKoneksi, refresh, state } from './store'
import Notifikasi from './Notifikasi.vue'
import { poll } from './poll'
import { start, stop } from './tracker'

const versi = __BUILD__
const notifBuka = ref(false)

// Notifikasi hanya terlihat saat apps dibuka, jadi badge-nya disegarkan tiap kali
// layar kembali menyala. Tanpa ini sopir yang membiarkan apps terbuka di saku
// tidak akan pernah melihat job baru sampai dia menekan sesuatu.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.me) refresh()
})

const router = useRouter()
const route = useRoute()

// Kredensial disimpan di HP sopir sendiri kalau dia mencentang "Ingatkan Saya".
// Password ikut tersimpan apa adanya -- itu memang risikonya, tapi apps ini
// dipakai berdiri di lapangan dengan sarung tangan dan password 5 karakter yang
// dibagikan kantor; mengetik ulang tiap pagi berakhir dengan password ditulis
// di stiker yang ditempel ke dashboard.
const INGAT = 'driver-login'
const tersimpan = (() => {
  try {
    return JSON.parse(localStorage.getItem(INGAT) || '{}')
  } catch {
    return {}
  }
})()

const usr = ref(tersimpan.usr || '')
const pwd = ref(tersimpan.pwd || '')
const ingat = ref(!!tersimpan.usr)
const busy = ref(false)
const err = ref('')

onMounted(refresh)

// Badge notifikasi disegarkan berkala selagi apps terbuka. Endpoint `unread`
// dipakai, bukan refresh() penuh: yang berubah cuma satu angka, dan me() ikut
// menghitung absensi, job berjalan, dan ketersediaan kendaraan.
poll(async () => {
  if (!state.me) return
  try {
    state.me.notif_baru = await call('unread')
  } catch {
    // gagal menyegarkan badge bukan alasan mengganggu sopir; putaran berikutnya coba lagi
  }
})

// Tracking berkala hanya saat sopir benar-benar bertugas.
watch(
  () => state.me && (state.me.siap || state.me.on_job),
  (bertugas) => (bertugas ? start(state.me.check_minutes) : stop()),
)

// Tengah malam absensi kemarin gugur: server menghitung kesiapan dari baris hari
// ini saja, jadi tidak ada yang perlu dijadwalkan di sana. Yang perlu dilakukan
// apps hanya bertanya lagi tepat saat tanggalnya berganti -- kalau tidak, sopir
// yang membiarkan apps terbuka semalaman masih melihat layar kemarin sampai dia
// menyentuh sesuatu. HP yang tidur menunda timer ini; refresh saat layar menyala
// yang menutup celah itu.
let jamGanti
function jadwalkanPergantianHari() {
  clearTimeout(jamGanti)
  const tengahMalam = new Date()
  // 00:00:05, bukan 00:00:00 pas: jam HP dan jam server tidak persis sama, dan
  // bertanya lima detik terlalu cepat dijawab dengan tanggal kemarin.
  tengahMalam.setHours(24, 0, 5, 0)
  jamGanti = setTimeout(async () => {
    if (state.me) await refresh()
    jadwalkanPergantianHari()
  }, tengahMalam - Date.now())
}
onMounted(jadwalkanPergantianHari)

// Layar pembuka mengikuti keadaan sopir: yang sudah siap atau sedang jalan
// membuka apps untuk melihat tugasnya, bukan untuk absen lagi. Sekali saja per
// login -- sesudah itu sopir bebas pindah tab tanpa dilempar balik.
let sudahDiarahkan = false
watch(
  () => state.me,
  (me) => {
    // Keluar mengosongkan state.me: pengarahan otomatis dibuka lagi supaya
    // login berikutnya tetap mendarat di tugasnya, bukan di layar absen.
    if (!me) return (sudahDiarahkan = false)

    // Belum absen hari ini: sopir dibawa ke layar absen tiap kali keadaannya
    // disegarkan, bukan sekali saat login. Server sudah menolak job baru tanpa
    // absensi hari ini; ini supaya sopir melihat SEBABNYA, bukan daftar job yang
    // diam saja. Halaman detail job dikecualikan -- job yang berangkat kemarin
    // harus tetap bisa ditutup, dan menariknya keluar dari sana berarti muatan
    // yang sudah sampai tidak pernah bisa dilaporkan.
    if (!me.sudah_absen) {
      if (!route.path.startsWith('/jobs/')) router.replace('/')
      return
    }

    if (sudahDiarahkan) return
    sudahDiarahkan = true
    if (me.siap || me.on_job) {
      if (route.path === '/') router.replace('/jobs')
    }
  },
)

// Titik keadaan di header memakai warna yang sama dengan kartu status di Home,
// jadi sopir cukup belajar sekali arti warnanya.
const nyala = computed(() =>
  state.me?.on_job ? 'bg-accent-400' : state.me?.siap ? 'bg-brand-200' : 'bg-white/40',
)

// Status dari server itu nama keadaan di sistem; yang dibaca sopir harus kalimat
// yang dia pakai sendiri. Belum absensi dan sudah check out sama-sama "Offline":
// bedanya urusan kantor, bagi sopir dua-duanya berarti dia sedang tidak dihitung
// siap kerja.
const STATUS = {
  'On Job': 'Sedang Mengerjakan Job',
  Ready: 'Ready',
  Absensi: 'Sudah Absensi',
  'Check Out': 'Offline',
  'Belum Absen': 'Offline',
  Izin: 'Izin',
  Sakit: 'Sakit',
}
const statusTeks = computed(() => STATUS[state.me?.status] || state.me?.status || '')

// Nopol yang sedang dipegang: dari check in hari ini, atau dari job berjalan
// kalau job itu mulai kemarin dan belum ada check in hari ini.
const nopol = computed(() => state.me?.vehicle || state.me?.job?.vehicle || '')

// Cabang dan kode bisa kosong (sopir yang belum dipetakan ke kantor mana pun);
// tanpa filter, barisnya jadi diawali atau diakhiri strip menggantung.
const namaBaris = computed(() =>
  [state.me?.driver.title, nopol.value].filter(Boolean).join(' - '),
)
const identitas = computed(() =>
  // Kode sopir cabang panjang (JKT-M23123123-001); di header cukup ekornya.
  [state.me?.driver.branch, (state.me?.driver.code || '').slice(-6)].filter(Boolean).join(' - '),
)

const TAB = [
  { ke: '/history', ikon: 'riwayat', teks: 'Riwayat' },
  { ke: '/jobs', ikon: 'tugas', teks: 'Tugas Saya' },
  { ke: '/', ikon: 'kamera', teks: 'Absensi', tepat: true },
]

async function submit() {
  busy.value = true
  err.value = ''
  state.alasanAuth = ''
  try {
    await login(usr.value.trim(), pwd.value)
    // Disimpan hanya setelah login benar-benar diterima: kredensial salah yang
    // ikut lengket berarti sopir mengulang kesalahan yang sama tiap pagi.
    try {
      if (ingat.value) {
        localStorage.setItem(INGAT, JSON.stringify({ usr: usr.value.trim(), pwd: pwd.value }))
      } else {
        localStorage.removeItem(INGAT)
      }
    } catch {
      // HP dengan penyimpanan situs dimatikan tetap boleh login
    }
    await refresh()
    // Login diterima tapi me() ditolak: alasan aslinya datang dari server (akun
    // tidak aktif, belum tertaut ke Driver, dan seterusnya). Menebak sendiri di
    // sini pernah membuat sopir yang akunnya baik-baik saja diberi tahu bahwa
    // akunnya belum tertaut, padahal sebabnya lain sama sekali.
    if (!state.me && !err.value) {
      err.value = state.alasanAuth || 'Akun ini belum tertaut ke data Driver.'
    }
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="phone">
    <!-- Spanduk koneksi menempel di atas segalanya: selama ini menyala, semua
         tombol lain memang tidak akan berhasil. -->
    <p
      v-if="pesanKoneksi()"
      class="z-50 flex items-center gap-2 bg-accent-500 px-4 py-2.5 text-sm font-medium text-white"
    >
      <Ikon n="silang" class="h-4 w-4" />
      {{ pesanKoneksi() }}
    </p>

    <p
      v-if="state.error"
      class="z-50 flex items-start gap-2 bg-red-600 px-4 py-2.5 text-sm text-white"
      @click="state.error = ''"
    >
      <Ikon n="silang" class="mt-0.5 h-4 w-4" />
      <span>{{ state.error }} <span class="opacity-70">(ketuk untuk menutup)</span></span>
    </p>

    <div v-if="!state.ready" class="grid flex-1 place-items-center bg-slate-100">
      <span
        class="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
    </div>

    <!-- Login: satu-satunya layar yang seluruhnya berwarna merek. -->
    <div v-else-if="!state.me" class="hero flex flex-1 flex-col justify-center overflow-y-auto p-6">
      <div class="mb-8 grid gap-3">
        <div class="grid h-14 w-14 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25">
          <Ikon n="truk" class="h-7 w-7" />
        </div>
        <div>
          <h1 class="text-3xl font-bold tracking-tight">Mitra Driver</h1>
          <p class="text-sm text-white/60">PT Cakraindo Mitra Internasional</p>
        </div>
      </div>

      <form class="grid gap-3" @submit.prevent="submit">
        <input
          v-model="usr"
          class="field border-transparent bg-white/10 text-white placeholder:text-white/50 focus:border-white/40 focus:bg-white/15 focus:ring-white/20"
          placeholder="Username"
          autocapitalize="none"
          required
        />
        <input
          v-model="pwd"
          type="password"
          class="field border-transparent bg-white/10 text-white placeholder:text-white/50 focus:border-white/40 focus:bg-white/15 focus:ring-white/20"
          placeholder="Password"
          required
        />
        <label class="flex items-center gap-3 px-1 py-1 text-sm text-white/80">
          <input v-model="ingat" type="checkbox" class="h-5 w-5 rounded accent-white" />
          Ingatkan Saya
        </label>

        <Peringatan :pesan="err" />
        <button
          class="btn mt-2 bg-white text-brand-700 shadow-lg shadow-brand-900/30 active:bg-white/90"
          :disabled="busy || !koneksi.online"
        >
          {{ busy ? 'Masuk...' : 'Masuk' }}
        </button>
      </form>

      <p class="mt-8 text-center text-xs text-white/40" :title="versi">
        &copy; PT Cakraindo Mitra Internasional 2026
      </p>
    </div>

    <template v-else>
      <!-- Isi halaman TIDAK menimpa header. Pernah ditumpuk supaya kartu pertama
           terlihat mengambang, tapi halaman yang diawali judul (Reward, Slip
           Gaji) jadi menaruh teks gelap di atas biru dan tidak terbaca. -->
      <header class="hero rounded-b-3xl px-4 pb-5 pt-4">
        <div class="flex items-center justify-between gap-3">
          <RouterLink to="/profil" class="flex min-w-0 items-center gap-3">
            <img
              v-if="state.me.driver.image"
              :src="state.me.driver.image"
              class="h-11 w-11 shrink-0 rounded-full object-cover ring-2 ring-white/30"
            />
            <span
              v-else
              class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/15 text-lg font-bold ring-1 ring-white/25"
            >
              {{ (state.me.driver.title || '?').charAt(0) }}
            </span>
            <span class="min-w-0">
              <span class="block truncate font-semibold leading-tight">
                {{ namaBaris }}
              </span>
              <span class="block truncate text-xs text-white/60">{{ identitas }}</span>
              <span
                class="mt-1 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2 py-0.5 text-[0.7rem] font-semibold ring-1 ring-white/20"
              >
                <span class="h-1.5 w-1.5 rounded-full" :class="nyala"></span>
                {{ statusTeks }}
              </span>
            </span>
          </RouterLink>

          <div class="flex shrink-0 items-center gap-1">
            <button
              class="relative grid h-10 w-10 place-items-center rounded-full text-white active:bg-white/15"
              aria-label="Notifikasi"
              @click="notifBuka = true"
            >
              <Ikon n="lonceng" />
              <span
                v-if="state.me.notif_baru"
                class="absolute right-0.5 top-0.5 min-w-[1.05rem] rounded-full bg-red-500 px-1 text-center text-[0.65rem] font-bold leading-4 ring-2 ring-brand-700"
              >
                {{ state.me.notif_baru }}
              </span>
            </button>
            <RouterLink
              to="/profil"
              class="grid h-10 w-10 place-items-center rounded-full text-white active:bg-white/15"
              aria-label="Profil"
            >
              <Ikon n="orang" />
            </RouterLink>
          </div>
        </div>
      </header>

      <Notifikasi v-if="notifBuka" @tutup="notifBuka = false" @terbaca="refresh" />

      <main class="min-h-0 flex-1 overflow-y-auto p-4"><RouterView /></main>

      <!-- Tab Absensi memakai exact-active: tanpa itu '/' cocok dengan semua route
           dan ketiga tab menyala bersamaan. -->
      <nav
        class="z-30 grid grid-cols-3 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)]"
      >
        <RouterLink
          v-for="t in TAB"
          :key="t.ke"
          :to="t.ke"
          class="grid place-items-center gap-1 py-2.5 text-[0.7rem] font-medium text-slate-400"
          :active-class="t.tepat ? '' : '!text-brand-600'"
          :exact-active-class="t.tepat ? '!text-brand-600' : ''"
        >
          <Ikon :n="t.ikon" />
          {{ t.teks }}
        </RouterLink>
      </nav>
    </template>
  </div>
</template>

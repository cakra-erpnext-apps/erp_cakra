<script setup>
/**
 * Kerangka apps mandor: login, header, tiga tab.
 *
 * Bentuknya sengaja sama persis dengan apps sopir (kolom selebar HP, header
 * berwarna merek, nav bawah) -- di lapangan kedua apps dipegang orang yang
 * duduk berdekatan, dan dua tata letak berbeda cuma menambah yang harus
 * diajarkan. Yang beda hanya isinya.
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { login } from '../api'
import Ikon from '../Ikon.vue'
import Peringatan from '../Peringatan.vue'
import { keluar, koneksi, pesanKoneksi, refresh, state } from '../store'

const versi = __BUILD__
const route = useRoute()

// Kredensial mandor boleh diingat dengan alasan yang sama seperti apps sopir:
// dibuka sambil berdiri di halaman kontainer, bukan di meja.
const INGAT = 'mandor-login'
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

// Layar HP yang menyala lagi = mandor kembali ke apps setelah menelepon atau
// membuka WA. Keadaan sesi disegarkan supaya dia tidak menekan tombol pada
// sesi yang sebenarnya sudah mati.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.me) refresh()
})

// Urutan tampil: Map - Driver - Dispatch. Yang memegang '/' adalah Dispatch,
// karena itulah layar pembuka -- urutan menu dan layar pembuka dua hal berbeda.
const TAB = [
  { ke: '/map', ikon: 'peta', teks: 'Map' },
  { ke: '/driver', ikon: 'orang', teks: 'Driver' },
  { ke: '/', ikon: 'tugas', teks: 'Dispatch' },
]

// Tab Dispatch tetap menyala saat halaman detail DPO dibuka. RouterLink
// active-class tidak bisa itu: '/' cocok dengan SEMUA route, jadi tanpa aturan
// sendiri ketiga tab menyala bersamaan.
const aktif = computed(() => (t) =>
  t.ke === '/' ? route.path === '/' || route.path.startsWith('/dpo') : route.path.startsWith(t.ke),
)

const inisial = computed(() => (state.me?.nama || '?').charAt(0).toUpperCase())

async function submit() {
  busy.value = true
  err.value = ''
  try {
    await login(usr.value.trim(), pwd.value)
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
    if (!state.me && !err.value) err.value = 'Akun ini belum berhak mengatur Dispatch Order.'
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="phone mandor">
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

    <div v-else-if="!state.me" class="hero flex flex-1 flex-col justify-center overflow-y-auto p-6">
      <div class="mb-8 grid gap-3">
        <div class="grid h-14 w-14 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25">
          <Ikon n="tugas" class="h-7 w-7" />
        </div>
        <div>
          <h1 class="text-3xl font-bold tracking-tight">Mandor</h1>
          <p class="text-sm text-white/60">PT Cakraindo Mitra Internasional</p>
        </div>
      </div>

      <form class="grid gap-3" @submit.prevent="submit">
        <input
          v-model="usr"
          class="field border-transparent bg-white/10 text-white placeholder:text-white/50 focus:border-white/40 focus:bg-white/15 focus:ring-white/20"
          placeholder="Email atau Username"
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
      <header class="hero rounded-b-3xl px-4 pb-5 pt-4">
        <div class="flex items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <img
              v-if="state.me.image"
              :src="state.me.image"
              class="h-11 w-11 shrink-0 rounded-full object-cover ring-2 ring-white/30"
            />
            <span
              v-else
              class="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/15 text-lg font-bold ring-1 ring-white/25"
            >
              {{ inisial }}
            </span>
            <span class="min-w-0">
              <span class="block truncate font-semibold leading-tight">{{ state.me.nama }}</span>
              <span class="block truncate text-xs text-white/60">
                Mandor - {{ state.me.cabang_label }}
              </span>
            </span>
          </div>

          <button
            class="grid h-10 w-10 shrink-0 place-items-center rounded-full text-white active:bg-white/15"
            aria-label="Keluar"
            @click="keluar()"
          >
            <Ikon n="keluar" />
          </button>
        </div>
      </header>

      <!-- overflow-x-hidden: `overflow-y: auto` membuat sumbu X ikut `auto`,
           jadi satu elemen yang kelebihan lebar langsung memunculkan geser
           kanan-kiri di seluruh halaman. Apps selebar HP tidak pernah butuh itu. -->
      <main class="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4"><RouterView /></main>

      <nav
        class="z-30 grid grid-cols-3 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)]"
      >
        <RouterLink
          v-for="t in TAB"
          :key="t.ke"
          :to="t.ke"
          class="grid place-items-center gap-1 py-2.5 text-[0.7rem] font-medium"
          :class="aktif(t) ? 'text-brand-600' : 'text-slate-400'"
        >
          <Ikon :n="t.ikon" />
          {{ t.teks }}
        </RouterLink>
      </nav>
    </template>
  </div>
</template>

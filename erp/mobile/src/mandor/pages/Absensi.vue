<script setup>
/**
 * Papan absensi sopir. LIHAT SAJA -- tidak ada satu pun tombol yang menulis.
 *
 * Satu kartu per sopir, bukan per record: mandor bertanya "si Anu sudah datang
 * belum", bukan "record apa saja yang masuk pagi ini". Sopir yang belum absen
 * ikut ditampilkan dan diurutkan paling atas oleh server -- daftar yang cuma
 * berisi yang sudah masuk tidak pernah bisa menjawab pertanyaan itu.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { call } from '../../api'
import Ikon from '../../Ikon.vue'
import Peringatan from '../../Peringatan.vue'
import { lazy } from '../../lazy'
import { poll } from '../../poll'
import { jam } from '../../waktu'

const hariIni = new Date().toLocaleDateString('sv') // sv = YYYY-MM-DD, tanpa geser zona
const PAGE = 5

const tanggal = ref(hariIni)
const q = ref('')
const rows = ref([])
const ringkas = ref({})
const total = ref(0)
const err = ref('')
const memuat = ref(true)
const foto = ref('')
let debounce

const GAYA = {
  'Belum Absen': 'bg-red-50 text-red-700',
  Absensi: 'bg-slate-100 text-slate-600',
  Ready: 'bg-ok-50 text-ok-700',
  'On Job': 'bg-accent-50 text-accent-700',
  'Check Out': 'bg-slate-100 text-slate-500',
  Izin: 'bg-slate-100 text-slate-600',
  Sakit: 'bg-slate-100 text-slate-600',
}

/**
 * `ulang = true` memuat ulang dari awal SEBANYAK yang sedang tampil, bukan
 * kembali ke 5: penyegaran otomatis tiap beberapa menit yang memotong daftar
 * akan menarik mandor yang sedang menggulir balik ke atas.
 */
async function muat(ulang = false) {
  if (memuat.value && !ulang) return
  if (!ulang && rows.value.length >= total.value && total.value) return
  memuat.value = true
  err.value = ''
  try {
    const d = await call('absensi', {
      tanggal: tanggal.value,
      q: q.value.trim(),
      start: ulang ? 0 : rows.value.length,
      limit: ulang ? Math.max(PAGE, rows.value.length) : PAGE,
    })
    rows.value = ulang ? d.rows : rows.value.concat(d.rows)
    ringkas.value = d.ringkas
    total.value = d.total
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

function awal() {
  rows.value = []
  total.value = 0
  muat(true)
}

const sentinel = lazy(() => muat())

onMounted(awal)
onBeforeUnmount(() => clearTimeout(debounce))

// Absensi berjalan sepanjang pagi; halaman yang dibiarkan terbuka harus ikut
// bertambah sendiri. Hanya untuk hari ini -- tanggal lampau tidak berubah lagi.
poll(() => {
  if (tanggal.value === hariIni && !foto.value) muat(true)
})

watch(tanggal, awal)
watch(q, () => {
  clearTimeout(debounce)
  debounce = setTimeout(awal, 350)
})
</script>

<template>
  <!-- Foto selfie dibuka sebagai lapisan di dalam kolom apps, bukan tab baru:
       stempel waktu/lokasi yang dibakar ke gambar memang untuk dilihat mandor,
       dan tab baru di HP berarti dia kehilangan posisi gulirannya. -->
  <div
    v-if="foto"
    class="lapis grid place-items-center bg-slate-900/80 p-4"
    @click="foto = ''"
  >
    <img :src="foto" class="max-h-full w-full rounded-2xl object-contain" />
  </div>

  <div class="grid gap-4">
    <div class="grid grid-cols-[auto_minmax(0,1fr)] gap-2">
      <label class="relative">
        <Ikon
          n="kalender"
          class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
        />
        <input v-model="tanggal" type="date" class="field w-auto py-3 pl-9 pr-3 text-sm" />
      </label>
      <div class="relative">
        <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input v-model="q" class="field py-3 pl-11 text-sm" type="search" placeholder="Cari sopir" />
      </div>
    </div>

    <div v-if="Object.keys(ringkas).length" class="flex flex-wrap gap-2">
      <span v-for="(n, s) in ringkas" :key="s" class="chip" :class="GAYA[s] || 'bg-slate-100 text-slate-600'">
        {{ s }} {{ n }}
      </span>
    </div>

    <Peringatan :pesan="err" />

    <div v-if="memuat && !rows.length" class="card grid place-items-center gap-3 py-8">
      <span class="h-7 w-7 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"></span>
      <p class="text-sm text-slate-400">Memuat absensi...</p>
    </div>

    <div
      v-else-if="!rows.length"
      class="card grid justify-items-center gap-2 py-8 text-center"
    >
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="orang" class="h-6 w-6" />
      </span>
      <p class="text-sm text-slate-500">
        {{ q ? 'Tidak ada sopir yang cocok.' : 'Belum ada sopir aktif di cabang Anda.' }}
      </p>
    </div>

    <div v-for="r in rows" :key="r.driver" class="card grid gap-3">
      <div class="flex items-start justify-between gap-3">
        <div class="flex min-w-0 items-center gap-2.5">
          <button
            v-if="r.absen_foto"
            class="h-10 w-10 shrink-0 overflow-hidden rounded-full ring-2 ring-ok-100"
            @click="foto = r.absen_foto"
          >
            <img :src="r.absen_foto" class="h-full w-full object-cover" />
          </button>
          <img
            v-else-if="r.image"
            :src="r.image"
            class="h-10 w-10 shrink-0 rounded-full object-cover ring-1 ring-slate-200"
          />
          <span
            v-else
            class="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-slate-100 font-bold text-slate-400"
          >
            {{ (r.nama || '?').charAt(0) }}
          </span>
          <span class="min-w-0">
            <span class="block truncate font-semibold">{{ r.nama }}</span>
            <span class="block truncate text-xs text-slate-400">
              {{ r.code }}<span v-if="r.job"> - {{ r.job }}</span>
            </span>
          </span>
        </div>
        <span class="chip" :class="GAYA[r.status] || 'bg-slate-100 text-slate-600'">
          {{ r.status }}
        </span>
      </div>

      <div v-if="r.absen_jam || r.check_in_jam" class="grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-sm">
        <div>
          <div class="label">Absen</div>
          <div>{{ jam(r.absen_jam) || '-' }}</div>
        </div>
        <div>
          <div class="label">Check In</div>
          <div>{{ jam(r.check_in_jam) || '-' }}</div>
        </div>
        <div>
          <div class="label">Check Out</div>
          <div>{{ jam(r.keluar_jam) || '-' }}</div>
        </div>
      </div>

      <div v-if="r.vehicle || r.trail" class="flex flex-wrap gap-2">
        <span v-if="r.vehicle" class="chip bg-slate-100 text-slate-600">
          <Ikon n="truk" class="h-4 w-4" />{{ r.vehicle }}
        </span>
        <span v-if="r.trail" class="chip bg-slate-100 text-slate-600">Chasis {{ r.trail }}</span>
        <!-- Jarak ikut ditampilkan: sudah dicatat saat check in, dan justru itu
             yang dipakai mandor kalau ada yang mengaku sudah di truk padahal
             belum. -->
        <span v-if="r.jarak_m != null" class="chip bg-slate-100 text-slate-600">
          {{ r.jarak_m }} m dari truk
        </span>
      </div>

      <p v-if="r.remark" class="text-sm text-slate-500">{{ r.remark }}</p>
    </div>

    <div ref="sentinel" class="grid place-items-center py-2 text-sm text-slate-400">
      <span
        v-if="memuat && rows.length"
        class="h-6 w-6 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
      <span v-else-if="rows.length && rows.length >= total">{{ total }} sopir, semua tampil</span>
    </div>
  </div>
</template>

<script setup>
/**
 * Peta seluruh armada cabang.
 *
 * Datanya diambil dari endpoint monitor GPS desk lewat `peta()`, bukan dihitung
 * ulang: status, warna, dan ikon truk harus sama persis dengan yang dilihat
 * kantor. Dua tempat yang menghitung status sendiri-sendiri pernah terjadi di
 * modul ini dan langsung menyimpang (lihat vehicle_status.py).
 */
import { onBeforeUnmount, onMounted, ref, shallowRef, computed, watch } from 'vue'
import { call } from '../../api'
import Ikon from '../../Ikon.vue'
import Peringatan from '../../Peringatan.vue'
import { lazy } from '../../lazy'

const wadah = ref(null)
const data = ref({ rows: [], status_colors: {}, status_icons: {} })
const err = ref('')
const memuat = ref(true)
const q = ref('')

const peta = shallowRef(null)
const marker = shallowRef({})
let timer

const PAGE = 5
const batas = ref(PAGE)

const cocok = computed(() => {
  const s = q.value.trim().toLowerCase()
  if (!s) return data.value.rows
  return data.value.rows.filter((r) =>
    [r.nopol, r.driver, r.job, r.status].some((v) => (v || '').toLowerCase().includes(s)),
  )
})

// Daftarnya dipotong dan tumbuh saat digulir; MARKER-nya tidak. Peta armada
// yang cuma memasang 5 truk dari 250 bukan peta yang lebih ringan, itu peta
// yang salah -- yang berat di HP adalah ratusan kartu, bukan titik di peta.
const terlihat = computed(() => cocok.value.slice(0, batas.value))
const sentinel = lazy(() => {
  if (batas.value < cocok.value.length) batas.value += PAGE
})

// Pencarian baru selalu mulai dari 5 lagi; tanpa ini hasil cari yang cuma 3
// baris tetap menyeret batas gulir sebelumnya.
watch(q, () => (batas.value = PAGE))

const hitung = computed(() => {
  const out = {}
  for (const r of data.value.rows) out[r.status] = (out[r.status] || 0) + 1
  return out
})

function isi(rows) {
  if (!peta.value) return
  for (const m of Object.values(marker.value)) m.remove()
  marker.value = {}

  const titik = []
  for (const r of rows) {
    if (!r.latitude || !r.longitude) continue
    const url = data.value.status_icons[r.status]
    const m = window.L.marker([r.latitude, r.longitude], {
      icon: url
        ? window.L.icon({ iconUrl: url, iconSize: [30, 30], iconAnchor: [15, 15] })
        : undefined,
    })
      .bindTooltip(r.nopol, { permanent: false, direction: 'top' })
      .bindPopup(
        `<b>${r.nopol}</b><br>${r.status}` +
          (r.driver ? `<br>Sopir: ${r.driver}` : '') +
          (r.job ? `<br>Job: ${r.job}` : '') +
          (r.route ? `<br>${r.route}` : '') +
          (r.note ? `<br><i>${r.note}</i>` : ''),
      )
      .addTo(peta.value)
    marker.value[r.name] = m
    titik.push([r.latitude, r.longitude])
  }
  if (titik.length) peta.value.fitBounds(titik, { padding: [30, 30], maxZoom: 13 })
}

async function muat() {
  err.value = ''
  try {
    data.value = await call('peta')
    isi(data.value.rows)
  } catch (e) {
    err.value = e.message
  } finally {
    memuat.value = false
  }
}

function sorot(r) {
  const m = marker.value[r.name]
  if (!m) return
  peta.value.setView(m.getLatLng(), 15)
  m.openPopup()
  // Peta ada di atas daftar; tanpa ini mandor menekan baris lalu tidak melihat
  // apa-apa berubah karena petanya sudah tergulir keluar layar.
  wadah.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  if (!window.L) {
    err.value = 'Peta tidak bisa dimuat. Periksa koneksi internet lalu buka lagi tab ini.'
    memuat.value = false
    return
  }
  peta.value = window.L.map(wadah.value, { attributionControl: false }).setView([-2.5, 118], 5)
  // Tile dari proxy server sendiri (`/tiles/`), sama dengan monitor GPS desk.
  // Bukan CDN pihak ketiga: peta yang gagal muat di lapangan tidak pernah bisa
  // dibedakan dari sinyal yang jelek.
  window.L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(peta.value)
  await muat()
  // Interval dari Fleet Settings, sama dengan monitor desk. Halaman peta dibuka
  // dan ditinggal terbuka; tanpa penyegaran ia diam-diam menampilkan posisi
  // setengah jam lalu.
  timer = setInterval(muat, (data.value.refresh_seconds || 180) * 1000)
})

onBeforeUnmount(() => {
  clearInterval(timer)
  if (peta.value) peta.value.remove()
})
</script>

<template>
  <div class="grid gap-4">
    <Peringatan :pesan="err" />

    <!-- z-0: pane Leaflet punya z-index sendiri yang bisa menimpa nav bawah. -->
    <div ref="wadah" class="relative z-0 h-[55vh] w-full overflow-hidden rounded-2xl bg-slate-200 ring-1 ring-slate-900/5"></div>

    <div class="flex flex-wrap gap-2">
      <span
        v-for="(n, s) in hitung"
        :key="s"
        class="chip"
        :style="data.status_colors[s]"
        >{{ s }} {{ n }}</span
      >
    </div>

    <div class="relative">
      <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input v-model="q" class="field py-3 pl-11 text-sm" type="search" placeholder="Cari nopol, sopir, DPO" />
    </div>

    <p v-if="memuat" class="text-center text-sm text-slate-400">Memuat armada...</p>

    <button
      v-for="r in terlihat"
      :key="r.name"
      class="card flex items-center justify-between gap-3 text-left active:bg-slate-50"
      @click="sorot(r)"
    >
      <span class="min-w-0">
        <span class="block truncate font-semibold">{{ r.nopol }}</span>
        <span class="block truncate text-xs text-slate-500">
          {{ r.driver || 'Belum ada sopir absen' }}<span v-if="r.job"> - {{ r.job }}</span>
        </span>
        <span class="block truncate text-xs text-slate-400">{{ r.note }}</span>
      </span>
      <span class="chip shrink-0" :style="data.status_colors[r.status]">{{ r.status }}</span>
    </button>

    <div ref="sentinel" class="grid place-items-center py-2 text-xs text-slate-400">
      <span v-if="terlihat.length && terlihat.length >= cocok.length">
        {{ cocok.length }} unit, semua tampil
      </span>
    </div>
  </div>
</template>

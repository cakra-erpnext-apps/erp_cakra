<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { call } from '../api'
import Ikon from '../Ikon.vue'
import Peringatan from '../Peringatan.vue'
import Rute from '../Rute.vue'

const PAGE = 5

const rows = ref([])
const q = ref('')
const err = ref('')
const memuat = ref(true)
const habis = ref(false)
const sentinel = ref(null)

let observer
let debounce

async function muat(reset = false) {
  if (memuat.value && !reset) return
  if (habis.value && !reset) return
  memuat.value = true
  err.value = ''
  try {
    const start = reset ? 0 : rows.value.length
    const batch = await call('history', { limit: PAGE, start, q: q.value.trim() })
    rows.value = reset ? batch : rows.value.concat(batch)
    // Batch tidak penuh berarti sudah dasar; tidak perlu satu panggilan kosong lagi.
    habis.value = batch.length < PAGE
  } catch (e) {
    err.value = e.message
    habis.value = true
  } finally {
    memuat.value = false
  }
}

// Sopir mengetik pelan di layar sentuh; tunggu ketikannya berhenti dulu supaya
// tidak satu permintaan per huruf.
watch(q, () => {
  clearTimeout(debounce)
  debounce = setTimeout(() => {
    habis.value = false
    muat(true)
  }, 350)
})

onMounted(async () => {
  await muat(true)
  observer = new IntersectionObserver(
    (entries) => entries[0].isIntersecting && muat(),
    { rootMargin: '200px' },
  )
  if (sentinel.value) observer.observe(sentinel.value)
})

onBeforeUnmount(() => {
  clearTimeout(debounce)
  if (observer) observer.disconnect()
})

const tanggal = (v) =>
  v ? new Date(v).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : null

// Mulai dan selesai job dipakai untuk menghitung lama kerja, jadi jamnya ikut.
const waktu = (v) => {
  if (!v) return null
  const d = new Date(String(v).replace(' ', 'T'))
  return `${tanggal(v)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="grid gap-3">
    <div class="relative">
      <Ikon n="cari" class="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        v-model="q"
        class="field pl-11 pr-11"
        type="search"
        placeholder="Cari kontainer, DPO, customer, nopol"
        autocapitalize="characters"
      />
      <button
        v-if="q"
        class="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-slate-400 active:bg-slate-100"
        aria-label="Hapus pencarian"
        @click="q = ''"
      >
        <Ikon n="silang" class="h-4 w-4" />
      </button>
    </div>

    <Peringatan :pesan="err" />

    <div
      v-if="!rows.length && !memuat"
      class="card grid justify-items-center gap-2 py-8 text-center"
    >
      <span class="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Ikon n="riwayat" class="h-6 w-6" />
      </span>
      <p class="text-sm text-slate-500">
        {{ q ? 'Tidak ada riwayat yang cocok.' : 'Belum ada riwayat job.' }}
      </p>
    </div>

    <div v-for="r in rows" :key="r.dpo_no || r.dpo" class="card grid gap-2 p-3">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="truncate font-semibold">{{ r.container_no || r.dpo_no || r.dpo }}</div>
          <div class="truncate text-xs text-slate-400">
            {{ r.dpo_no || r.dpo }}<span v-if="r.customer">  -  {{ r.customer }}</span>
          </div>
        </div>
        <span
          class="chip"
          :class="r.selesai ? 'bg-brand-50 text-brand-700' : 'bg-accent-50 text-accent-700'"
        >
          {{ r.selesai ? 'Selesai' : 'Berjalan' }}
        </span>
      </div>

      <Rute :muat="r.origin_location" :bongkar="r.destination_location" />

      <div class="grid grid-cols-3 items-end gap-2 border-t border-slate-100 pt-2 text-sm">
        <div>
          <div class="label">Mulai</div>
          <div>{{ waktu(r.accept) || 'belum' }}</div>
        </div>
        <div>
          <div class="label">Selesai</div>
          <div>{{ waktu(r.finish) || 'belum' }}</div>
        </div>
        <div class="min-w-0 text-right">
          <div class="label">Nopol</div>
          <div class="truncate">{{ r.vehicle || '-' }}</div>
        </div>
      </div>
    </div>

    <div ref="sentinel" class="grid place-items-center py-2 text-sm text-slate-400">
      <span
        v-if="memuat"
        class="h-6 w-6 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600"
      ></span>
      <span v-else-if="habis && rows.length">Semua riwayat sudah tampil</span>
    </div>
  </div>
</template>
